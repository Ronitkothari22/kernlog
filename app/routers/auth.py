"""Authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, TokenPairResponse
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPairResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    existing = db.execute(
        text("SELECT id FROM app.users WHERE email = :email"),
        {"email": payload.email.lower()},
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    org = db.execute(
        text(
            """
            INSERT INTO app.organizations (name, slug)
            VALUES (:name, :slug)
            RETURNING id
            """
        ),
        {"name": payload.organization_name, "slug": payload.organization_slug},
    ).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create organization")

    user = db.execute(
        text(
            """
            INSERT INTO app.users (tenant_id, email, password_hash, role)
            VALUES (:tenant_id, :email, :password_hash, 'owner')
            RETURNING id, email, role
            """
        ),
        {
            "tenant_id": org.id,
            "email": payload.email.lower(),
            "password_hash": hash_password(payload.password),
        },
    ).first()
    db.commit()

    access_token = create_access_token(user_id=str(user.id), tenant_id=str(org.id), email=user.email, role=user.role)
    refresh_token, refresh_expires_at = create_refresh_token(
        user_id=str(user.id), tenant_id=str(org.id), email=user.email, role=user.role
    )

    db.execute(
        text(
            """
            INSERT INTO app.refresh_tokens (tenant_id, user_id, token_hash, expires_at)
            VALUES (:tenant_id, :user_id, :token_hash, :expires_at)
            """
        ),
        {
            "tenant_id": org.id,
            "user_id": user.id,
            "token_hash": hash_token(refresh_token),
            "expires_at": refresh_expires_at,
        },
    )
    db.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token, tenant_id=str(org.id))


@router.post("/login", response_model=TokenPairResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    user = db.execute(
        text("SELECT id, tenant_id, email, role, password_hash FROM app.users WHERE email = :email"),
        {"email": payload.email.lower()},
    ).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(
        user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email, role=user.role
    )
    refresh_token, refresh_expires_at = create_refresh_token(
        user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email, role=user.role
    )

    db.execute(
        text(
            """
            INSERT INTO app.refresh_tokens (tenant_id, user_id, token_hash, expires_at)
            VALUES (:tenant_id, :user_id, :token_hash, :expires_at)
            """
        ),
        {
            "tenant_id": user.tenant_id,
            "user_id": user.id,
            "token_hash": hash_token(refresh_token),
            "expires_at": refresh_expires_at,
        },
    )
    db.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token, tenant_id=str(user.tenant_id))


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    claims = decode_refresh_token(payload.refresh_token)
    old_hash = hash_token(payload.refresh_token)

    row = db.execute(
        text(
            """
            SELECT user_id, tenant_id, revoked_at, expires_at
            FROM app.refresh_tokens
            WHERE token_hash = :token_hash
            """
        ),
        {"token_hash": old_hash},
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown refresh token")

    if row.revoked_at is not None or row.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired or revoked")

    if str(row.user_id) != str(claims.get("user_id")) or str(row.tenant_id) != str(claims.get("tenant_id")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token claims mismatch")

    user = db.execute(
        text("SELECT id, tenant_id, email, role FROM app.users WHERE id = :id"),
        {"id": str(row.user_id)},
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(
        user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email, role=user.role
    )
    new_refresh_token, refresh_expires_at = create_refresh_token(
        user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email, role=user.role
    )
    new_hash = hash_token(new_refresh_token)

    db.execute(
        text(
            """
            UPDATE app.refresh_tokens
            SET revoked_at = now(), replaced_by_token_hash = :new_hash
            WHERE token_hash = :old_hash
            """
        ),
        {"old_hash": old_hash, "new_hash": new_hash},
    )
    db.execute(
        text(
            """
            INSERT INTO app.refresh_tokens (tenant_id, user_id, token_hash, expires_at)
            VALUES (:tenant_id, :user_id, :token_hash, :expires_at)
            """
        ),
        {
            "tenant_id": user.tenant_id,
            "user_id": user.id,
            "token_hash": new_hash,
            "expires_at": refresh_expires_at,
        },
    )
    db.commit()

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        tenant_id=str(user.tenant_id),
    )


@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> dict[str, bool]:
    _ = decode_refresh_token(payload.refresh_token)
    token_hash = hash_token(payload.refresh_token)

    db.execute(
        text(
            """
            UPDATE app.refresh_tokens
            SET revoked_at = now()
            WHERE token_hash = :token_hash AND revoked_at IS NULL
            """
        ),
        {"token_hash": token_hash},
    )
    db.commit()
    return {"ok": True}
