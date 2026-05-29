"""Agent key resolution with Redis-backed caching."""

from __future__ import annotations

import json
from urllib import error, parse, request

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import load_settings
from app.security import hash_token


CACHE_TTL_SECONDS = 300
CACHE_NAMESPACE = "kernlog:keys:"


def _redis_get(cache_key: str) -> str | None:
    settings = load_settings()
    url = settings.upstash_redis_rest_url.rstrip("/") + "/get/" + parse.quote(cache_key, safe="")
    req = request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {settings.upstash_redis_rest_token}")
    try:
        with request.urlopen(req, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    value = body.get("result")
    return value if isinstance(value, str) and value else None


def _redis_setex(cache_key: str, value: str, ttl_seconds: int) -> None:
    settings = load_settings()
    encoded_key = parse.quote(cache_key, safe="")
    encoded_value = parse.quote(value, safe="")
    url = settings.upstash_redis_rest_url.rstrip("/") + f"/setex/{encoded_key}/{ttl_seconds}/{encoded_value}"
    req = request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {settings.upstash_redis_rest_token}")
    try:
        with request.urlopen(req, timeout=5):
            return
    except error.URLError:
        return


def resolve_agent_key_to_tenant_id(raw_agent_key: str, db: Session) -> str | None:
    key_hash = hash_token(raw_agent_key)
    cache_key = f"{CACHE_NAMESPACE}{key_hash}"
    cached_tenant_id = _redis_get(cache_key)
    if cached_tenant_id:
        return cached_tenant_id

    row = db.execute(
        text(
            """
            SELECT tenant_id
            FROM app.agent_keys
            WHERE key_hash = :key_hash AND revoked_at IS NULL
            """
        ),
        {"key_hash": key_hash},
    ).first()
    if not row:
        return None

    tenant_id = str(row.tenant_id)
    _redis_setex(cache_key, tenant_id, CACHE_TTL_SECONDS)
    return tenant_id
