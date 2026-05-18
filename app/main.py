"""FastAPI entrypoint for kernlog backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail-fast on startup if required configuration is missing.
    load_settings()
    yield


app = FastAPI(title="Kernlog Backend", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
