"""Organization and agent key management endpoints."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import require_auth
from app.schemas.org import (
    AgentKeyCreateRequest,
    AgentKeyCreateResponse,
    AgentKeyItemResponse,
    OrganizationProfileResponse,
)
from app.security import hash_token

router = APIRouter(tags=["organization"])


@router.get("/org", response_model=OrganizationProfileResponse)
def get_org(auth_ctx: dict = Depends(require_auth), db: Session = Depends(get_db)) -> OrganizationProfileResponse:
    row = db.execute(
        text(
            """
            SELECT id, name, slug, plan, host_limit, retention_days, created_at
            FROM app.organizations
            WHERE id = :tenant_id
            """
        ),
        {"tenant_id": auth_ctx["tenant_id"]},
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    return OrganizationProfileResponse(
        id=str(row.id),
        name=row.name,
        slug=row.slug,
        plan=row.plan,
        host_limit=row.host_limit,
        retention_days=row.retention_days,
        created_at=row.created_at,
    )


@router.get("/org/agent-keys", response_model=list[AgentKeyItemResponse])
def list_agent_keys(auth_ctx: dict = Depends(require_auth), db: Session = Depends(get_db)) -> list[AgentKeyItemResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, key_prefix, label, last_used_at, revoked_at, created_at
            FROM app.agent_keys
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
            """
        ),
        {"tenant_id": auth_ctx["tenant_id"]},
    ).all()

    return [
        AgentKeyItemResponse(
            id=str(row.id),
            key_prefix=row.key_prefix,
            label=row.label,
            last_used_at=row.last_used_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/org/agent-keys", response_model=AgentKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_agent_key(
    payload: AgentKeyCreateRequest,
    auth_ctx: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> AgentKeyCreateResponse:
    raw_key = f"kl_live_{secrets.token_hex(16)}"
    key_hash = hash_token(raw_key)
    key_prefix = raw_key[:16]

    row = db.execute(
        text(
            """
            INSERT INTO app.agent_keys (tenant_id, key_hash, key_prefix, label)
            VALUES (:tenant_id, :key_hash, :key_prefix, :label)
            RETURNING id, key_prefix, label, created_at
            """
        ),
        {
            "tenant_id": auth_ctx["tenant_id"],
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "label": payload.label,
        },
    ).first()
    db.commit()

    return AgentKeyCreateResponse(
        id=str(row.id),
        key_prefix=row.key_prefix,
        label=row.label,
        key=raw_key,
        created_at=row.created_at,
    )


@router.delete("/org/agent-keys/{key_id}")
def revoke_agent_key(key_id: str, auth_ctx: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict[str, bool]:
    existing = db.execute(
        text(
            """
            SELECT id
            FROM app.agent_keys
            WHERE id = :key_id AND tenant_id = :tenant_id
            """
        ),
        {"key_id": key_id, "tenant_id": auth_ctx["tenant_id"]},
    ).first()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent key not found")

    db.execute(
        text(
            """
            UPDATE app.agent_keys
            SET revoked_at = now()
            WHERE id = :key_id AND tenant_id = :tenant_id AND revoked_at IS NULL
            """
        ),
        {"key_id": key_id, "tenant_id": auth_ctx["tenant_id"]},
    )
    db.commit()
    return {"ok": True}
