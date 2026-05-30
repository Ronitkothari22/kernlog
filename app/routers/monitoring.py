"""Tenant-scoped monitoring REST endpoints for Phase 7."""

from __future__ import annotations

import base64
import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error, parse, request

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import load_settings
from app.db import get_db
from app.db import SessionLocal
from app.deps.auth import require_auth
from app.security import decode_access_token
from app.schemas.monitoring import (
    AlertItemResponse,
    AlertRuleCreateRequest,
    AlertRuleItemResponse,
    AlertRuleUpdateRequest,
    HostItemResponse,
    HostLatestSnapshot,
    HostListResponse,
    HostLogItemResponse,
    HostLogsResponse,
    HostMetricsResponse,
    MetricPointResponse,
)

router = APIRouter(prefix="/api/v1", tags=["monitoring"])
LOGGER = logging.getLogger("kernlog.ws")

INTERVAL_BUCKETS: dict[str, str] = {
    "1m": "date_trunc('minute', ts)",
    "5m": "to_timestamp(floor(extract(epoch from ts) / 300) * 300)",
    "1h": "date_trunc('hour', ts)",
}


def _redis_get(cache_key: str) -> str | None:
    settings = load_settings()
    encoded = parse.quote(cache_key, safe="")
    url = settings.upstash_redis_rest_url.rstrip("/") + f"/get/{encoded}"
    req = request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {settings.upstash_redis_rest_token}")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            result = payload.get("result")
            return result if isinstance(result, str) else None
    except (error.URLError, json.JSONDecodeError):
        return None


def _get_latest_snapshot(tenant_id: str, host_id: str) -> HostLatestSnapshot:
    raw = _redis_get(f"{tenant_id}:{host_id}:latest")
    if not raw:
        return HostLatestSnapshot()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return HostLatestSnapshot()

    ts_value = parsed.get("ts")
    ts = None
    if isinstance(ts_value, str):
        try:
            ts = datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
        except ValueError:
            ts = None

    metric_value = parsed.get("metric_value")
    value = None
    if isinstance(metric_value, (int, float, str)):
        try:
            value = float(metric_value)
        except ValueError:
            value = None

    return HostLatestSnapshot(
        metric_name=parsed.get("metric_name") if isinstance(parsed.get("metric_name"), str) else None,
        metric_value=value,
        ts=ts,
    )


def _require_host_in_tenant(db: Session, tenant_id: str, host_id: str):
    row = db.execute(
        text(
            """
            SELECT host_id, label, os, arch, agent_version, last_seen_at, created_at
            FROM app.hosts
            WHERE tenant_id = :tenant_id AND host_id = :host_id
            """
        ),
        {"tenant_id": tenant_id, "host_id": host_id},
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found")
    return row


def _encode_cursor(ts: datetime, row_id: int) -> str:
    payload = json.dumps({"ts": ts.isoformat(), "id": row_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        parsed = json.loads(payload)
        ts = datetime.fromisoformat(parsed["ts"].replace("Z", "+00:00"))
        row_id = int(parsed["id"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor") from exc
    return ts, row_id


def _publish_rule_invalidation(tenant_id: str) -> None:
    settings = load_settings()
    channel = parse.quote(f"kernlog:{tenant_id}:alert_rules", safe="")
    payload = parse.quote(json.dumps({"type": "invalidate", "tenant_id": tenant_id}), safe="")
    url = settings.upstash_redis_rest_url.rstrip("/") + f"/publish/{channel}/{payload}"
    req = request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {settings.upstash_redis_rest_token}")
    req.add_header("Content-Type", "application/json")
    try:
        request.urlopen(req, timeout=3).read()
    except error.URLError:
        return
    _redis_set(f"kernlog:{tenant_id}:alert_rules:version", str(int(time.time())))


def _redis_set(cache_key: str, value: str) -> None:
    settings = load_settings()
    encoded_key = parse.quote(cache_key, safe="")
    encoded_value = parse.quote(value, safe="")
    url = settings.upstash_redis_rest_url.rstrip("/") + f"/set/{encoded_key}/{encoded_value}"
    req = request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {settings.upstash_redis_rest_token}")
    req.add_header("Content-Type", "application/json")
    try:
        request.urlopen(req, timeout=3).read()
    except error.URLError:
        return


def _redis_subscribe_once(channel: str) -> list[dict[str, Any]]:
    settings = load_settings()
    encoded_channel = parse.quote(channel, safe="")
    url = settings.upstash_redis_rest_url.rstrip("/") + f"/subscribe/{encoded_channel}"
    req = request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {settings.upstash_redis_rest_token}")
    req.add_header("Accept", "text/event-stream")

    try:
        with request.urlopen(req, timeout=35) as resp:
            body = resp.read().decode("utf-8")
    except (TimeoutError, error.URLError):
        return []

    events: list[dict[str, Any]] = []
    for line in body.splitlines():
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
                events.append(parsed)
    return events


def _decode_ws_token(token: str) -> dict[str, Any]:
    try:
        return decode_access_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid websocket token") from exc


def _require_ws_host_in_tenant(tenant_id: str, host_id: str) -> None:
    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT 1
                FROM app.hosts
                WHERE tenant_id = :tenant_id AND host_id = :host_id
                """
            ),
            {"tenant_id": tenant_id, "host_id": host_id},
        ).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found")


class WsBridgeManager:
    def __init__(self) -> None:
        self._clients: dict[str, set[WebSocket]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def register(self, tenant_id: str, host_id: str, websocket: WebSocket) -> None:
        key = f"{tenant_id}:{host_id}"
        async with self._lock:
            clients = self._clients.setdefault(key, set())
            clients.add(websocket)
            if key not in self._tasks:
                self._tasks[key] = asyncio.create_task(self._relay_loop(tenant_id, host_id), name=f"ws-relay-{key}")

    async def unregister(self, tenant_id: str, host_id: str, websocket: WebSocket) -> None:
        key = f"{tenant_id}:{host_id}"
        async with self._lock:
            clients = self._clients.get(key, set())
            clients.discard(websocket)
            if not clients:
                self._clients.pop(key, None)
                task = self._tasks.pop(key, None)
                if task:
                    task.cancel()

    async def _relay_loop(self, tenant_id: str, host_id: str) -> None:
        key = f"{tenant_id}:{host_id}"
        channels = [f"kernlog:{tenant_id}:{host_id}", f"kernlog:{tenant_id}:{host_id}:logs"]
        try:
            while True:
                for channel in channels:
                    events = await asyncio.to_thread(_redis_subscribe_once, channel)
                    if not events:
                        continue
                    await self._broadcast(key, events)
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            LOGGER.exception("WebSocket relay loop crashed for %s", key)

    async def _broadcast(self, key: str, events: list[dict[str, Any]]) -> None:
        clients = self._clients.get(key, set()).copy()
        for payload in events:
            dead_clients: list[WebSocket] = []
            for ws in clients:
                try:
                    await ws.send_json(payload)
                except Exception:  # noqa: BLE001
                    dead_clients.append(ws)
            if dead_clients:
                async with self._lock:
                    current = self._clients.get(key, set())
                    for ws in dead_clients:
                        current.discard(ws)


ws_bridge_manager = WsBridgeManager()


@router.websocket("/ws/{host_id}")
async def host_ws(websocket: WebSocket, host_id: str) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return

    try:
        auth_payload = _decode_ws_token(token)
        tenant_id = str(auth_payload["tenant_id"])
        _require_ws_host_in_tenant(tenant_id, host_id)
    except HTTPException as exc:
        await websocket.close(code=4403 if exc.status_code != status.HTTP_404_NOT_FOUND else 4404, reason=exc.detail)
        return

    await websocket.accept()
    await ws_bridge_manager.register(tenant_id, host_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_bridge_manager.unregister(tenant_id, host_id, websocket)


@router.get("/hosts", response_model=HostListResponse)
def list_hosts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> HostListResponse:
    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            """
            SELECT host_id, label, os, arch, agent_version, last_seen_at, created_at
            FROM app.hosts
            WHERE tenant_id = :tenant_id
            ORDER BY last_seen_at DESC NULLS LAST, created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"tenant_id": auth_ctx["tenant_id"], "limit": page_size, "offset": offset},
    ).all()

    items = [
        HostItemResponse(
            host_id=row.host_id,
            label=row.label,
            os=row.os,
            arch=row.arch,
            agent_version=row.agent_version,
            last_seen_at=row.last_seen_at,
            created_at=row.created_at,
            latest=_get_latest_snapshot(auth_ctx["tenant_id"], row.host_id),
        )
        for row in rows
    ]
    return HostListResponse(items=items, page=page, page_size=page_size)


@router.get("/hosts/{host_id}", response_model=HostItemResponse)
def get_host(
    host_id: str,
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> HostItemResponse:
    row = _require_host_in_tenant(db, auth_ctx["tenant_id"], host_id)
    return HostItemResponse(
        host_id=row.host_id,
        label=row.label,
        os=row.os,
        arch=row.arch,
        agent_version=row.agent_version,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
        latest=_get_latest_snapshot(auth_ctx["tenant_id"], host_id),
    )


@router.get("/hosts/{host_id}/metrics", response_model=HostMetricsResponse)
def host_metrics(
    host_id: str,
    metric: str = Query(min_length=1),
    from_ts: datetime = Query(alias="from"),
    to_ts: datetime = Query(alias="to"),
    interval: str = Query(default="1m"),
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> HostMetricsResponse:
    _require_host_in_tenant(db, auth_ctx["tenant_id"], host_id)

    if interval not in INTERVAL_BUCKETS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported interval")
    if to_ts <= from_ts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid time range")
    if (to_ts - from_ts) > timedelta(days=7):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Max query window is 7 days")

    if from_ts.tzinfo is None:
        from_ts = from_ts.replace(tzinfo=UTC)
    if to_ts.tzinfo is None:
        to_ts = to_ts.replace(tzinfo=UTC)

    bucket_expr = INTERVAL_BUCKETS[interval]
    sql = text(
        f"""
        SELECT {bucket_expr} AS bucket,
               AVG(metric_value) AS avg,
               MIN(metric_value) AS min,
               MAX(metric_value) AS max,
               COUNT(*) AS count
        FROM metrics.metrics
        WHERE tenant_id = :tenant_id
          AND host_id = :host_id
          AND metric_name = :metric_name
          AND ts >= :from_ts
          AND ts <= :to_ts
        GROUP BY bucket
        ORDER BY bucket ASC
        """
    )
    rows = db.execute(
        sql,
        {
            "tenant_id": auth_ctx["tenant_id"],
            "host_id": host_id,
            "metric_name": metric,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    ).all()

    points = [
        MetricPointResponse(
            ts=row.bucket,
            avg=float(row.avg),
            min=float(row.min),
            max=float(row.max),
            count=int(row.count),
        )
        for row in rows
    ]
    return HostMetricsResponse(host_id=host_id, metric=metric, interval=interval, points=points)


@router.get("/hosts/{host_id}/logs", response_model=HostLogsResponse)
def host_logs(
    host_id: str,
    search: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> HostLogsResponse:
    _require_host_in_tenant(db, auth_ctx["tenant_id"], host_id)

    where = ["tenant_id = :tenant_id", "host_id = :host_id"]
    params: dict[str, Any] = {"tenant_id": auth_ctx["tenant_id"], "host_id": host_id, "limit": limit + 1}

    if severity:
        where.append("upper(severity) = upper(:severity)")
        params["severity"] = severity
    if search:
        where.append("line ILIKE :search")
        params["search"] = f"%{search}%"
    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        where.append("(ts < :cursor_ts OR (ts = :cursor_ts AND id < :cursor_id))")
        params["cursor_ts"] = cursor_ts
        params["cursor_id"] = cursor_id

    sql = text(
        f"""
        SELECT id, file_path, line, severity, ts
        FROM metrics.logs
        WHERE {' AND '.join(where)}
        ORDER BY ts DESC, id DESC
        LIMIT :limit
        """
    )
    rows = db.execute(sql, params).all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = _encode_cursor(last.ts, int(last.id))

    return HostLogsResponse(
        items=[
            HostLogItemResponse(
                id=int(row.id), file_path=row.file_path, line=row.line, severity=row.severity, ts=row.ts
            )
            for row in page_rows
        ],
        next_cursor=next_cursor,
    )


@router.get("/alerts", response_model=list[AlertItemResponse])
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    host_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[AlertItemResponse]:
    where = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": auth_ctx["tenant_id"], "limit": limit}

    if status_filter:
        where.append("status = :status")
        params["status"] = status_filter
    if host_id:
        _require_host_in_tenant(db, auth_ctx["tenant_id"], host_id)
        where.append("host_id = :host_id")
        params["host_id"] = host_id

    rows = db.execute(
        text(
            f"""
            SELECT id, rule_id, host_id, severity, message, status, created_at, resolved_at
            FROM app.alerts
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).all()

    return [
        AlertItemResponse(
            id=str(row.id),
            rule_id=str(row.rule_id) if row.rule_id else None,
            host_id=row.host_id,
            severity=row.severity,
            message=row.message,
            status=row.status,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]


@router.get("/alert-rules", response_model=list[AlertRuleItemResponse])
def list_alert_rules(auth_ctx: dict[str, str] = Depends(require_auth), db: Session = Depends(get_db)) -> list[AlertRuleItemResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, name, metric_name, COALESCE(operator, comparator) AS operator,
                   threshold, severity, host_id, enabled, created_at
            FROM app.alert_rules
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
            """
        ),
        {"tenant_id": auth_ctx["tenant_id"]},
    ).all()
    return [
        AlertRuleItemResponse(
            id=str(row.id),
            name=row.name,
            metric_name=row.metric_name,
            operator=row.operator,
            threshold=float(row.threshold),
            severity=row.severity,
            host_id=row.host_id,
            enabled=bool(row.enabled),
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/alert-rules", response_model=AlertRuleItemResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreateRequest,
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> AlertRuleItemResponse:
    if payload.host_id:
        _require_host_in_tenant(db, auth_ctx["tenant_id"], payload.host_id)

    row = db.execute(
        text(
            """
            INSERT INTO app.alert_rules (tenant_id, name, metric_name, comparator, operator, threshold, severity, host_id, enabled)
            VALUES (:tenant_id, :name, :metric_name, :operator, :operator, :threshold, :severity, :host_id, :enabled)
            RETURNING id, name, metric_name, operator, threshold, severity, host_id, enabled, created_at
            """
        ),
        {
            "tenant_id": auth_ctx["tenant_id"],
            "name": payload.name,
            "metric_name": payload.metric_name,
            "operator": payload.operator,
            "threshold": payload.threshold,
            "severity": payload.severity,
            "host_id": payload.host_id,
            "enabled": payload.enabled,
        },
    ).first()
    db.commit()
    _publish_rule_invalidation(auth_ctx["tenant_id"])

    return AlertRuleItemResponse(
        id=str(row.id),
        name=row.name,
        metric_name=row.metric_name,
        operator=row.operator,
        threshold=float(row.threshold),
        severity=row.severity,
        host_id=row.host_id,
        enabled=bool(row.enabled),
        created_at=row.created_at,
    )


@router.put("/alert-rules/{rule_id}", response_model=AlertRuleItemResponse)
def update_alert_rule(
    rule_id: str,
    payload: AlertRuleUpdateRequest,
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> AlertRuleItemResponse:
    if payload.host_id:
        _require_host_in_tenant(db, auth_ctx["tenant_id"], payload.host_id)

    existing = db.execute(
        text("SELECT id FROM app.alert_rules WHERE id = :rule_id AND tenant_id = :tenant_id"),
        {"rule_id": rule_id, "tenant_id": auth_ctx["tenant_id"]},
    ).first()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    row = db.execute(
        text(
            """
            UPDATE app.alert_rules
            SET name = :name,
                metric_name = :metric_name,
                comparator = :operator,
                operator = :operator,
                threshold = :threshold,
                severity = :severity,
                host_id = :host_id,
                enabled = :enabled
            WHERE id = :rule_id AND tenant_id = :tenant_id
            RETURNING id, name, metric_name, operator, threshold, severity, host_id, enabled, created_at
            """
        ),
        {
            "rule_id": rule_id,
            "tenant_id": auth_ctx["tenant_id"],
            "name": payload.name,
            "metric_name": payload.metric_name,
            "operator": payload.operator,
            "threshold": payload.threshold,
            "severity": payload.severity,
            "host_id": payload.host_id,
            "enabled": payload.enabled,
        },
    ).first()
    db.commit()
    _publish_rule_invalidation(auth_ctx["tenant_id"])

    return AlertRuleItemResponse(
        id=str(row.id),
        name=row.name,
        metric_name=row.metric_name,
        operator=row.operator,
        threshold=float(row.threshold),
        severity=row.severity,
        host_id=row.host_id,
        enabled=bool(row.enabled),
        created_at=row.created_at,
    )


@router.delete("/alert-rules/{rule_id}")
def delete_alert_rule(
    rule_id: str,
    auth_ctx: dict[str, str] = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    existing = db.execute(
        text("SELECT id FROM app.alert_rules WHERE id = :rule_id AND tenant_id = :tenant_id"),
        {"rule_id": rule_id, "tenant_id": auth_ctx["tenant_id"]},
    ).first()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    db.execute(
        text("DELETE FROM app.alert_rules WHERE id = :rule_id AND tenant_id = :tenant_id"),
        {"rule_id": rule_id, "tenant_id": auth_ctx["tenant_id"]},
    )
    db.commit()
    _publish_rule_invalidation(auth_ctx["tenant_id"])
    return {"ok": True}
