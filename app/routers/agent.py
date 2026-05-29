"""Agent ingestion and registration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.rate_limit import agent_register_limiter
from app.schemas.agent import AgentRegisterRequest, AgentRegisterResponse
from app.security import hash_token
from app.services.key_resolver import resolve_agent_key_to_tenant_id

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/register", response_model=AgentRegisterResponse)
def register_agent(
    payload: AgentRegisterRequest,
    db: Session = Depends(get_db),
    agent_key: str = Header(..., alias="agent_key"),
) -> AgentRegisterResponse:
    key_hash = hash_token(agent_key)
    limit_result = agent_register_limiter.hit(key_hash, max_requests=10, window_seconds=60)
    if not limit_result.allowed:
        headers = {}
        if limit_result.retry_after_seconds is not None:
            headers["Retry-After"] = str(limit_result.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=headers,
        )

    tenant_id = resolve_agent_key_to_tenant_id(agent_key, db)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent key")

    row = db.execute(
        text(
            """
            INSERT INTO app.hosts (tenant_id, host_id, label, os, arch, agent_version, last_seen_at)
            VALUES (:tenant_id, :host_id, :label, :os, :arch, :agent_version, now())
            ON CONFLICT (tenant_id, host_id)
            DO UPDATE SET
                label = EXCLUDED.label,
                os = EXCLUDED.os,
                arch = EXCLUDED.arch,
                agent_version = EXCLUDED.agent_version,
                last_seen_at = now()
            RETURNING tenant_id, host_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "host_id": payload.host_id,
            "label": payload.label,
            "os": payload.os,
            "arch": payload.arch,
            "agent_version": payload.agent_version,
        },
    ).first()

    db.execute(
        text(
            """
            UPDATE app.agent_keys
            SET last_used_at = now()
            WHERE key_hash = :key_hash AND revoked_at IS NULL
            """
        ),
        {"key_hash": key_hash},
    )
    db.commit()

    return AgentRegisterResponse(tenant_id=str(row.tenant_id), host_id=row.host_id, registered=True)
