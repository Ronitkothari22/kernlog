"""FastAPI entrypoint for kernlog backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.config import load_settings
from app.deps.auth import require_auth
from app.routers.agent import router as agent_router
from app.routers.auth import router as auth_router
from app.routers.org import router as org_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail-fast on startup if required configuration is missing.
    load_settings()
    yield


app = FastAPI(title="Kernlog Backend", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(org_router)
app.include_router(agent_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me(auth_ctx: dict = Depends(require_auth)) -> dict:
    return auth_ctx
