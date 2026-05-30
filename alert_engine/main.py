"""Alert engine worker process for threshold evaluation."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import error, parse, request

from sqlalchemy import text

from app.config import load_settings
from app.db import SessionLocal

LOGGER = logging.getLogger("kernlog.alert_engine")


@dataclass
class MetricEvent:
    tenant_id: str
    host_id: str
    metric_name: str
    metric_value: float
    ts: datetime


@dataclass
class AlertRule:
    id: str
    tenant_id: str
    name: str
    metric_name: str
    operator: str
    threshold: float
    severity: str
    host_id: str | None
    consecutive: int
    enabled: bool


class RedisRest:
    def __init__(self) -> None:
        settings = load_settings()
        self.base_url = settings.upstash_redis_rest_url.rstrip("/")
        self.token = settings.upstash_redis_rest_token

    def _request(self, method: str, path: str, timeout: int = 8) -> dict[str, Any] | None:
        req = request.Request(self.base_url + path, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "text/event-stream")
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except (TimeoutError, error.URLError):
            return None

        if path.startswith("/subscribe/"):
            return {"result": body}

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def get(self, key: str) -> str | None:
        data = self._request("GET", f"/get/{parse.quote(key, safe='')}")
        if not data:
            return None
        value = data.get("result")
        return value if isinstance(value, str) else None

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        self._request(
            "POST",
            f"/setex/{parse.quote(key, safe='')}/{ttl_seconds}/{parse.quote(value, safe='')}",
        )

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        encoded_payload = parse.quote(json.dumps(payload, separators=(",", ":")), safe="")
        self._request("POST", f"/publish/{parse.quote(channel, safe='')}/{encoded_payload}")

    def subscribe_once(self, channel: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/subscribe/{parse.quote(channel, safe='')}", timeout=35)
        if not data:
            return []

        raw_stream = data.get("result")
        if not isinstance(raw_stream, str):
            return []

        out: list[dict[str, Any]] = []
        for line in raw_stream.splitlines():
            if not line.startswith("data:"):
                continue
            payload_raw = line.removeprefix("data:").strip()
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                continue
            message = payload.get("message")
            if isinstance(message, str):
                try:
                    parsed = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
        return out


class RuleCache:
    def __init__(self, redis_client: RedisRest, ttl_seconds: int = 30) -> None:
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, str | None, list[AlertRule]]] = {}

    def get_rules(self, tenant_id: str, host_id: str, metric_name: str) -> list[AlertRule]:
        version_key = f"kernlog:{tenant_id}:alert_rules:version"
        version = self.redis.get(version_key)
        now = time.time()

        cached = self._cache.get(tenant_id)
        if cached and cached[0] > now and cached[1] == version:
            return [
                r
                for r in cached[2]
                if r.enabled and r.metric_name == metric_name and (r.host_id is None or r.host_id == host_id)
            ]

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    """
                    SELECT id, tenant_id, name, metric_name, COALESCE(operator, comparator) AS operator,
                           threshold, severity, host_id,
                           COALESCE(consecutive, 3) AS consecutive, enabled
                    FROM app.alert_rules
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": tenant_id},
            ).all()

        all_rules = [
            AlertRule(
                id=str(r.id),
                tenant_id=str(r.tenant_id),
                name=r.name,
                metric_name=r.metric_name,
                operator=r.operator,
                threshold=float(r.threshold),
                severity=r.severity,
                host_id=r.host_id,
                consecutive=max(1, int(r.consecutive)),
                enabled=bool(r.enabled),
            )
            for r in rows
        ]

        self._cache[tenant_id] = (now + self.ttl_seconds, version, all_rules)
        return [
            r
            for r in all_rules
            if r.enabled and r.metric_name == metric_name and (r.host_id is None or r.host_id == host_id)
        ]


class AlertEvaluator:
    def __init__(self, redis_client: RedisRest, rule_cache: RuleCache) -> None:
        self.redis = redis_client
        self.rule_cache = rule_cache

    def evaluate(self, event: MetricEvent) -> None:
        rules = self.rule_cache.get_rules(event.tenant_id, event.host_id, event.metric_name)
        for rule in rules:
            breached = self._is_breached(rule.operator, event.metric_value, rule.threshold)
            streak_key = f"alert_streak:{event.tenant_id}:{event.host_id}:{rule.id}"
            if breached:
                count = int(self.redis.get(streak_key) or "0") + 1
                self.redis.setex(streak_key, 3600, str(count))
                if count >= rule.consecutive:
                    self._fire_if_not_open(event, rule)
            else:
                self.redis.setex(streak_key, 60, "0")
                self._resolve_if_open(event, rule)

    @staticmethod
    def _is_breached(operator: str, value: float, threshold: float) -> bool:
        return {
            "gt": value > threshold,
            "gte": value >= threshold,
            "lt": value < threshold,
            "lte": value <= threshold,
        }.get(operator, False)

    def _fire_if_not_open(self, event: MetricEvent, rule: AlertRule) -> None:
        with SessionLocal() as db:
            existing = db.execute(
                text(
                    """
                    SELECT id FROM app.alerts
                    WHERE tenant_id = :tenant_id
                      AND rule_id = :rule_id
                      AND host_id = :host_id
                      AND status = 'open'
                    LIMIT 1
                    """
                ),
                {"tenant_id": event.tenant_id, "rule_id": rule.id, "host_id": event.host_id},
            ).first()
            if existing:
                return

            row = db.execute(
                text(
                    """
                    INSERT INTO app.alerts (tenant_id, rule_id, host_id, severity, message, status)
                    VALUES (:tenant_id, :rule_id, :host_id, :severity, :message, 'open')
                    RETURNING id, created_at
                    """
                ),
                {
                    "tenant_id": event.tenant_id,
                    "rule_id": rule.id,
                    "host_id": event.host_id,
                    "severity": rule.severity,
                    "message": f"{rule.name}: {event.metric_name}={event.metric_value} breached {rule.operator} {rule.threshold}",
                },
            ).first()
            db.commit()

        self.redis.publish(
            f"kernlog:{event.tenant_id}:alerts",
            {
                "type": "alert_fired",
                "id": str(row.id),
                "tenant_id": event.tenant_id,
                "host_id": event.host_id,
                "rule_id": rule.id,
                "severity": rule.severity,
                "status": "open",
                "created_at": row.created_at.isoformat(),
            },
        )

    def _resolve_if_open(self, event: MetricEvent, rule: AlertRule) -> None:
        with SessionLocal() as db:
            row = db.execute(
                text(
                    """
                    UPDATE app.alerts
                    SET status = 'resolved', resolved_at = now()
                    WHERE tenant_id = :tenant_id
                      AND rule_id = :rule_id
                      AND host_id = :host_id
                      AND status = 'open'
                    RETURNING id, resolved_at
                    """
                ),
                {"tenant_id": event.tenant_id, "rule_id": rule.id, "host_id": event.host_id},
            ).first()
            db.commit()

        if not row:
            return

        self.redis.publish(
            f"kernlog:{event.tenant_id}:alerts",
            {
                "type": "alert_resolved",
                "id": str(row.id),
                "tenant_id": event.tenant_id,
                "host_id": event.host_id,
                "rule_id": rule.id,
                "status": "resolved",
                "resolved_at": row.resolved_at.isoformat(),
            },
        )


def _parse_metric_event(payload: dict[str, Any]) -> MetricEvent | None:
    tenant_id = payload.get("tenant_id")
    host_id = payload.get("host_id")
    metric_name = payload.get("metric_name")
    metric_value = payload.get("metric_value")

    if not isinstance(tenant_id, str) or not isinstance(host_id, str) or not isinstance(metric_name, str):
        return None
    if not isinstance(metric_value, (int, float)):
        return None

    ts_raw = payload.get("ts")
    if isinstance(ts_raw, str):
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(UTC)
    else:
        ts = datetime.now(UTC)

    return MetricEvent(
        tenant_id=tenant_id,
        host_id=host_id,
        metric_name=metric_name,
        metric_value=float(metric_value),
        ts=ts,
    )


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    LOGGER.info("alert engine worker starting")

    redis_client = RedisRest()
    cache = RuleCache(redis_client=redis_client, ttl_seconds=30)
    evaluator = AlertEvaluator(redis_client=redis_client, rule_cache=cache)
    channels = ("metrics.system", "metrics.api")

    while True:
        for channel in channels:
            try:
                for payload in redis_client.subscribe_once(channel):
                    event = _parse_metric_event(payload)
                    if not event:
                        continue
                    evaluator.evaluate(event)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Error processing channel=%s", channel)
        time.sleep(0.1)


def main() -> None:
    try:
        run_forever()
    except KeyboardInterrupt:
        LOGGER.info("alert engine worker stopped")


if __name__ == "__main__":
    main()
