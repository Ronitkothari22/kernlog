"""FastAPI entrypoint for kernlog backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_settings
from app.deps.auth import require_auth
from app.routers.agent import router as agent_router
from app.routers.auth import router as auth_router
from app.routers.ingestion import router as ingestion_router
from app.routers.ingestion import worker as ingestion_worker
from app.routers.monitoring import router as monitoring_router
from app.routers.org import router as org_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail-fast on startup if required configuration is missing.
    load_settings()
    ingestion_worker.start()
    try:
        yield
    finally:
        await ingestion_worker.stop()


app = FastAPI(title="Kernlog Backend", lifespan=lifespan)
settings = load_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(org_router)
app.include_router(agent_router)
app.include_router(ingestion_router)
app.include_router(monitoring_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me(auth_ctx: dict = Depends(require_auth)) -> dict:
    return auth_ctx
