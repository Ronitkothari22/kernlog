"""FastAPI middleware helper for publishing API latency metrics to QStash."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request

from kernlog_agent.producers.qstash import QStashProducer


def install_kernlog_middleware(app: FastAPI, *, producer: QStashProducer, tenant_id_getter) -> None:
    @app.middleware("http")
    async def _kernlog_metrics(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        tenant_id = tenant_id_getter(request)
        host_id = request.headers.get("x-host-id", "api")
        payload = {
            "tenant_id": tenant_id,
            "host_id": host_id,
            "route": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "latency_ms": duration_ms,
            "ts_monotonic": time.monotonic(),
        }
        producer.publish("metrics.api", payload)
        return response
