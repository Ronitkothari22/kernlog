"""Agent configuration loader."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import socket

import yaml


class AgentConfigError(RuntimeError):
    """Raised when the agent config is invalid."""


@dataclass(slots=True)
class AgentConfig:
    backend_base_url: str
    agent_key: str
    upstash_qstash_url: str
    upstash_qstash_token: str
    upstash_qstash_current_signing_key: str
    host_id: str
    host_label: str | None
    log_file_paths: list[str]
    collection_interval_seconds: int = 15


def _require_text(cfg: dict, key: str) -> str:
    value = cfg.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentConfigError(f"Missing required config key: {key}")
    return value.strip()


def load_config(path: str = "/etc/kernlog/config.yaml") -> AgentConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise AgentConfigError(f"Config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AgentConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise AgentConfigError("Config root must be a mapping/object")

    backend_base_url = _require_text(raw, "backend_base_url")
    agent_key = _require_text(raw, "agent_key")
    qstash_url = _require_text(raw, "upstash_qstash_url")
    qstash_token = _require_text(raw, "upstash_qstash_token")
    qstash_signing_key = _require_text(raw, "upstash_qstash_current_signing_key")

    host_id = raw.get("host_id") or socket.gethostname()
    if not isinstance(host_id, str) or not host_id.strip():
        raise AgentConfigError("host_id must be a non-empty string")

    host_label = raw.get("host_label")
    if host_label is not None and not isinstance(host_label, str):
        raise AgentConfigError("host_label must be a string when provided")

    log_file_paths = raw.get("log_file_paths", [])
    if not isinstance(log_file_paths, list) or any(not isinstance(p, str) for p in log_file_paths):
        raise AgentConfigError("log_file_paths must be a list of file paths")

    for file_path in log_file_paths:
        p = Path(file_path)
        if not p.exists():
            raise AgentConfigError(f"Configured log file does not exist: {file_path}")
        if not p.is_file():
            raise AgentConfigError(f"Configured log path is not a file: {file_path}")
        if not os.access(p, os.R_OK):
            raise AgentConfigError(f"Configured log file is not readable: {file_path}")

    interval = raw.get("collection_interval_seconds", 15)
    if not isinstance(interval, int) or interval < 1:
        raise AgentConfigError("collection_interval_seconds must be an integer >= 1")

    return AgentConfig(
        backend_base_url=backend_base_url.rstrip("/"),
        agent_key=agent_key,
        upstash_qstash_url=qstash_url.rstrip("/"),
        upstash_qstash_token=qstash_token,
        upstash_qstash_current_signing_key=qstash_signing_key,
        host_id=host_id.strip(),
        host_label=host_label.strip() if isinstance(host_label, str) and host_label.strip() else None,
        log_file_paths=log_file_paths,
        collection_interval_seconds=interval,
    )
