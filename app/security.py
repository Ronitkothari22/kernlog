"""Password and JWT helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, status

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, load_settings


ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(*, user_id: str, tenant_id: str, email: str, role: str) -> str:
    settings = load_settings()
    exp = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "type": "access",
        "exp": exp,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(*, user_id: str, tenant_id: str, email: str, role: str) -> tuple[str, datetime]:
    settings = load_settings()
    exp = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    jti = secrets.token_urlsafe(32)
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "type": "refresh",
        "jti": jti,
        "exp": exp,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_refresh_secret, algorithm=ALGORITHM), exp


def decode_access_token(token: str) -> dict:
    settings = load_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token type")
    return payload


def decode_refresh_token(token: str) -> dict:
    settings = load_settings()
    try:
        payload = jwt.decode(token, settings.jwt_refresh_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")
    return payload
