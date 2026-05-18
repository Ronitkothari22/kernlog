"""Application configuration and startup validation."""

from __future__ import annotations

import os
from dataclasses import dataclass


REQUIRED_ENV_VARS = (
    "NEON_DATABASE_URL",
    "UPSTASH_KAFKA_REST_URL",
    "UPSTASH_KAFKA_REST_USERNAME",
    "UPSTASH_KAFKA_REST_PASSWORD",
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
    upstash_kafka_rest_url: str
    upstash_kafka_rest_username: str
    upstash_kafka_rest_password: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str
    jwt_secret: str
    jwt_refresh_secret: str
    port: str
    environment: str
    cors_origin: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and set all required values."
        )
    return value


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
        upstash_kafka_rest_url=_required("UPSTASH_KAFKA_REST_URL"),
        upstash_kafka_rest_username=_required("UPSTASH_KAFKA_REST_USERNAME"),
        upstash_kafka_rest_password=_required("UPSTASH_KAFKA_REST_PASSWORD"),
        upstash_redis_rest_url=_required("UPSTASH_REDIS_REST_URL"),
        upstash_redis_rest_token=_required("UPSTASH_REDIS_REST_TOKEN"),
        jwt_secret=_required("JWT_SECRET"),
        jwt_refresh_secret=_required("JWT_REFRESH_SECRET"),
        port=_required("PORT"),
        environment=_required("ENVIRONMENT"),
        cors_origin=_required("CORS_ORIGIN"),
    )
