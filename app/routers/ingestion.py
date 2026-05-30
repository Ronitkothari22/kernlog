"""QStash ingestion webhook endpoints."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import load_settings
from app.ingestion import IngestionError, IngestionWorker, parse_ingest_message


router = APIRouter(prefix="/api/v1/ingest", tags=["ingestion"])
worker = IngestionWorker()


@router.post("/qstash")
async def qstash_ingest(
    request: Request,
    x_topic: str = Header(..., alias="x-topic"),
    x_message_id: str = Header(default="", alias="x-message-id"),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = load_settings()
    expected = f"Bearer {settings.upstash_qstash_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized publisher")

    raw_body = await request.body()
    try:
        message = parse_ingest_message(x_topic, raw_body, x_message_id)
        await worker.enqueue_and_wait(message)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ingestion failed") from exc

    return {"ok": True}
