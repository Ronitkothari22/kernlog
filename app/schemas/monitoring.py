"""Monitoring API schemas for hosts, metrics, logs, alerts, and alert rules."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AlertRuleOperator = Literal["gt", "lt", "gte", "lte"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "resolved"]


class HostLatestSnapshot(BaseModel):
    metric_name: str | None = None
    metric_value: float | None = None
    ts: datetime | None = None


class HostItemResponse(BaseModel):
    host_id: str
    label: str | None
    os: str | None
    arch: str | None
    agent_version: str | None
    last_seen_at: datetime | None
    created_at: datetime
    latest: HostLatestSnapshot


class HostListResponse(BaseModel):
    items: list[HostItemResponse]
    page: int
    page_size: int


class MetricPointResponse(BaseModel):
    ts: datetime
    avg: float
    min: float
    max: float
    count: int


class HostMetricsResponse(BaseModel):
    host_id: str
    metric: str
    interval: str
    points: list[MetricPointResponse]


class HostLogItemResponse(BaseModel):
    id: int
    file_path: str | None
    line: str
    severity: str
    ts: datetime


class HostLogsResponse(BaseModel):
    items: list[HostLogItemResponse]
    next_cursor: str | None = None


class AlertItemResponse(BaseModel):
    id: str
    rule_id: str | None
    host_id: str | None
    severity: str
    message: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class AlertRuleItemResponse(BaseModel):
    id: str
    name: str
    metric_name: str
    operator: AlertRuleOperator
    threshold: float
    severity: AlertSeverity
    host_id: str | None
    enabled: bool
    created_at: datetime


class AlertRuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    metric_name: str = Field(min_length=1, max_length=120)
    operator: AlertRuleOperator
    threshold: float
    severity: AlertSeverity = "warning"
    host_id: str | None = Field(default=None, max_length=255)
    enabled: bool = True


class AlertRuleUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    metric_name: str = Field(min_length=1, max_length=120)
    operator: AlertRuleOperator
    threshold: float
    severity: AlertSeverity
    host_id: str | None = Field(default=None, max_length=255)
    enabled: bool
