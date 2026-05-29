"""Application configuration and startup validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


REQUIRED_ENV_VARS = (
    "NEON_DATABASE_URL",
    "UPSTASH_QSTASH_URL",
    "UPSTASH_QSTASH_TOKEN",
    "UPSTASH_QSTASH_CURRENT_SIGNING_KEY",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "JWT_SECRET",
    "JWT_REFRESH_SECRET",
    "PORT",
    "ENVIRONMENT",
    "CORS_ORIGIN",
)


@dataclass(frozen=True)
class AppSettings:
    neon_database_url: str
    upstash_qstash_url: str
    upstash_qstash_token: str
    upstash_qstash_current_signing_key: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str
    jwt_secret: str
    jwt_refresh_secret: str
    port: str
    environment: str
    cors_origin: str


ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and set all required values."
        )
    return value


@lru_cache(maxsize=1)
def load_settings() -> AppSettings:
    """Load and validate required runtime settings."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name, "").strip()]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variables: {joined}. "
            "Copy .env.example to .env and set all required values before starting the app."
        )

    return AppSettings(
        neon_database_url=_required("NEON_DATABASE_URL"),
        upstash_qstash_url=_required("UPSTASH_QSTASH_URL"),
        upstash_qstash_token=_required("UPSTASH_QSTASH_TOKEN"),
        upstash_qstash_current_signing_key=_required("UPSTASH_QSTASH_CURRENT_SIGNING_KEY"),
        upstash_redis_rest_url=_required("UPSTASH_REDIS_REST_URL"),
        upstash_redis_rest_token=_required("UPSTASH_REDIS_REST_TOKEN"),
        jwt_secret=_required("JWT_SECRET"),
        jwt_refresh_secret=_required("JWT_REFRESH_SECRET"),
        port=_required("PORT"),
        environment=_required("ENVIRONMENT"),
        cors_origin=_required("CORS_ORIGIN"),
    )
