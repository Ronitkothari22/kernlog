"""QStash ingestion pipeline for metrics and logs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import error, parse, request

from sqlalchemy import text

from app.config import load_settings


LOGGER = logging.getLogger("kernlog.ingestion")
SEVERITY_RE = re.compile(r"\b(ERROR|WARN|INFO|DEBUG)\b", re.IGNORECASE)


class IngestionError(Exception):
    """Raised when a message cannot be safely ingested."""


@dataclass
class IngestMessage:
    topic: str
    payload: dict[str, Any]
    message_id: str


@dataclass
class IngestWorkItem:
    message: IngestMessage
    done: asyncio.Future[None]


class IngestionWorker:
    """Background queue worker for ingestion events."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[IngestWorkItem] = asyncio.Queue(maxsize=1000)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(), name="qstash-ingestion-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def enqueue_and_wait(self, message: IngestMessage) -> None:
        loop = asyncio.get_running_loop()
        done: asyncio.Future[None] = loop.create_future()
        await self.queue.put(IngestWorkItem(message=message, done=done))
        await done

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                work = await self.queue.get()
            except asyncio.CancelledError:
                break

            try:
                await _process_with_retries(work.message)
                if not work.done.done():
                    work.done.set_result(None)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Failed to ingest topic=%s message_id=%s", work.message.topic, work.message.message_id)
                if not work.done.done():
                    work.done.set_exception(exc)
            finally:
                self.queue.task_done()


async def _process_with_retries(message: IngestMessage, max_attempts: int = 3) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            await asyncio.to_thread(process_message, message)
            return
        except IngestionError:
            raise
        except Exception:  # noqa: BLE001
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(0.25 * attempt)


def parse_ingest_message(topic: str, raw_body: bytes, message_id: str) -> IngestMessage:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestionError("Malformed JSON payload") from exc

    if not isinstance(payload, dict):
        raise IngestionError("Payload must be a JSON object")

    tenant_id = payload.get("tenant_id")
    host_id = payload.get("host_id")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise IngestionError("Missing required field tenant_id")
    if not isinstance(host_id, str) or not host_id.strip():
        raise IngestionError("Missing required field host_id")

    return IngestMessage(topic=topic, payload=payload, message_id=message_id)


def infer_severity(line: str) -> str:
    match = SEVERITY_RE.search(line)
    if match:
        return match.group(1).upper()
    return "INFO"


def _redis_call(method: str, path: str) -> dict[str, Any] | None:
    settings = load_settings()
    url = settings.upstash_redis_rest_url.rstrip("/") + path
    req = request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {settings.upstash_redis_rest_token}")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except (error.URLError, json.JSONDecodeError):
        return None


def _redis_get(cache_key: str) -> str | None:
    encoded = parse.quote(cache_key, safe="")
    data = _redis_call("GET", f"/get/{encoded}")
    if not data:
        return None
    value = data.get("result")
    return value if isinstance(value, str) else None


def _redis_setex(cache_key: str, ttl_seconds: int, value: str) -> None:
    encoded_key = parse.quote(cache_key, safe="")
    encoded_value = parse.quote(value, safe="")
    _redis_call("POST", f"/setex/{encoded_key}/{ttl_seconds}/{encoded_value}")


def _redis_hset(mapping_key: str, mapping: dict[str, str]) -> None:
    encoded_key = parse.quote(mapping_key, safe="")
    query = "&".join(
        f"{parse.quote(k, safe='')}={parse.quote(v, safe='')}" for k, v in mapping.items()
    )
    _redis_call("POST", f"/hset/{encoded_key}?{query}")


def _redis_expire(cache_key: str, ttl_seconds: int) -> None:
    encoded_key = parse.quote(cache_key, safe="")
    _redis_call("POST", f"/expire/{encoded_key}/{ttl_seconds}")


def _redis_publish(channel: str, payload: dict[str, Any]) -> None:
    encoded_channel = parse.quote(channel, safe="")
    message = parse.quote(json.dumps(payload, separators=(",", ":")), safe="")
    _redis_call("POST", f"/publish/{encoded_channel}/{message}")


def _is_duplicate_message(message_id: str) -> bool:
    if not message_id:
        return False
    key = f"kernlog:ingest:processed:{message_id}"
    existing = _redis_get(key)
    if existing == "1":
        return True
    _redis_setex(key, 86400, "1")
    return False


def _validate_tenant_host(db, tenant_id: str, host_id: str) -> None:
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
        raise IngestionError("Unknown tenant/host combination")


def _update_last_seen(db, tenant_id: str, host_id: str) -> None:
    gate_key = f"{tenant_id}:{host_id}:lastseen"
    if _redis_get(gate_key):
        return

    db.execute(
        text(
            """
            UPDATE app.hosts
            SET last_seen_at = now()
            WHERE tenant_id = :tenant_id AND host_id = :host_id
            """
        ),
        {"tenant_id": tenant_id, "host_id": host_id},
    )
    _redis_setex(gate_key, 30, "1")


def _ingest_metric(db, message: IngestMessage) -> None:
    payload = message.payload
    metric_name = payload.get("metric_name")
    metric_value = payload.get("metric_value")
    labels = payload.get("labels")

    if not isinstance(metric_name, str) or not metric_name.strip():
        raise IngestionError("metrics payload missing metric_name")
    if not isinstance(metric_value, (int, float)):
        raise IngestionError("metrics payload missing numeric metric_value")
    if labels is None:
        labels = {}
    if not isinstance(labels, dict):
        raise IngestionError("metrics payload labels must be object")

    ts = payload.get("ts")
    if isinstance(ts, str):
        try:
            parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            parsed_ts = datetime.now(UTC)
    else:
        parsed_ts = datetime.now(UTC)

    db.execute(
        text(
            """
            INSERT INTO metrics.metrics (tenant_id, host_id, metric_name, metric_value, labels, ts)
            VALUES (:tenant_id, :host_id, :metric_name, :metric_value, CAST(:labels AS jsonb), :ts)
            """
        ),
        {
            "tenant_id": payload["tenant_id"],
            "host_id": payload["host_id"],
            "metric_name": metric_name,
            "metric_value": float(metric_value),
            "labels": json.dumps(labels),
            "ts": parsed_ts,
        },
    )

    snapshot_key = f"{payload['tenant_id']}:{payload['host_id']}:latest"
    _redis_hset(
        snapshot_key,
        {
            "metric_name": metric_name,
            "metric_value": str(float(metric_value)),
            "ts": parsed_ts.isoformat(),
        },
    )
    _redis_expire(snapshot_key, 60)

    _redis_publish(
        f"kernlog:{payload['tenant_id']}:{payload['host_id']}",
        {
            "type": "metric",
            "tenant_id": payload["tenant_id"],
            "host_id": payload["host_id"],
            "metric_name": metric_name,
            "metric_value": float(metric_value),
            "labels": labels,
            "ts": parsed_ts.isoformat(),
        },
    )
    _redis_publish(
        message.topic,
        {
            "type": "metric",
            "tenant_id": payload["tenant_id"],
            "host_id": payload["host_id"],
            "metric_name": metric_name,
            "metric_value": float(metric_value),
            "labels": labels,
            "ts": parsed_ts.isoformat(),
        },
    )


def _ingest_log(db, message: IngestMessage) -> None:
    payload = message.payload
    line = payload.get("line")
    file_path = payload.get("file_path")

    if not isinstance(line, str) or not line:
        raise IngestionError("logs payload missing line")
    if file_path is not None and not isinstance(file_path, str):
        raise IngestionError("logs payload file_path must be string")

    ts = payload.get("ts")
    if isinstance(ts, str):
        try:
            parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            parsed_ts = datetime.now(UTC)
    else:
        parsed_ts = datetime.now(UTC)

    severity = infer_severity(line)

    db.execute(
        text(
            """
            INSERT INTO metrics.logs (tenant_id, host_id, file_path, line, severity, ts)
            VALUES (:tenant_id, :host_id, :file_path, :line, :severity, :ts)
            """
        ),
        {
            "tenant_id": payload["tenant_id"],
            "host_id": payload["host_id"],
            "file_path": file_path,
            "line": line,
            "severity": severity,
            "ts": parsed_ts,
        },
    )

    _redis_publish(
        f"kernlog:{payload['tenant_id']}:{payload['host_id']}:logs",
        {
            "type": "log",
            "tenant_id": payload["tenant_id"],
            "host_id": payload["host_id"],
            "file_path": file_path,
            "line": line,
            "severity": severity,
            "ts": parsed_ts.isoformat(),
        },
    )


def process_message(message: IngestMessage) -> None:
    """Process and commit a single ingestion message."""
    from app.db import SessionLocal

    if _is_duplicate_message(message.message_id):
        LOGGER.info("Skipping duplicate message_id=%s", message.message_id)
        return

    with SessionLocal() as db:
        _validate_tenant_host(db, message.payload["tenant_id"], message.payload["host_id"])

        if message.topic in ("metrics.system", "metrics.api"):
            _ingest_metric(db, message)
        elif message.topic == "logs.app":
            _ingest_log(db, message)
        else:
            raise IngestionError(f"Unsupported topic: {message.topic}")

        _update_last_seen(db, message.payload["tenant_id"], message.payload["host_id"])
        db.commit()
