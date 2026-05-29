"""Backend registration client for agent startup."""

from __future__ import annotations

from dataclasses import dataclass
import platform
import time

import requests


@dataclass(slots=True)
class RegistrationResult:
    tenant_id: str
    host_id: str
    registered: bool


def register_agent(base_url: str, agent_key: str, host_id: str, label: str | None, agent_version: str, retries: int = 4) -> RegistrationResult:
    url = f"{base_url.rstrip('/')}/api/v1/agent/register"
    payload = {
        "host_id": host_id,
        "label": label,
        "os": platform.system().lower(),
        "arch": platform.machine().lower(),
        "agent_version": agent_version,
    }
    headers = {"agent_key": agent_key}

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code in (401, 403):
                raise RuntimeError("Agent key is invalid or revoked")
            if 200 <= response.status_code < 300:
                data = response.json()
                return RegistrationResult(
                    tenant_id=str(data["tenant_id"]),
                    host_id=str(data["host_id"]),
                    registered=bool(data.get("registered", True)),
                )
            if 400 <= response.status_code < 500:
                raise RuntimeError(f"Registration failed: {response.status_code} {response.text[:200]}")
            last_error = f"server error {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < retries:
            time.sleep(0.5 * (2 ** (attempt - 1)))

    raise RuntimeError(f"Registration failed after {retries} attempts: {last_error}")
