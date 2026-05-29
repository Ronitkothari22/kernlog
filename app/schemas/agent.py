"""Agent registration schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentRegisterRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=255)
    label: str | None = Field(default=None, max_length=255)
    os: str | None = Field(default=None, max_length=100)
    arch: str | None = Field(default=None, max_length=100)
    agent_version: str | None = Field(default=None, max_length=100)


class AgentRegisterResponse(BaseModel):
    tenant_id: str
    host_id: str
    registered: bool
