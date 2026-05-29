"""Organization and agent key schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationProfileResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    host_limit: int
    retention_days: int
    created_at: datetime


class AgentKeyCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)


class AgentKeyItemResponse(BaseModel):
    id: str
    key_prefix: str
    label: str | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class AgentKeyCreateResponse(BaseModel):
    id: str
    key_prefix: str
    label: str | None
    key: str
    created_at: datetime
