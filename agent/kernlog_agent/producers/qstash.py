"""Upstash QStash producer with retries."""

from __future__ import annotations

from dataclasses import dataclass
import time

import requests


@dataclass(slots=True)
class PublishResult:
    success: bool
    topic: str
    attempts: int
    status_code: int | None
    message_id: str | None
    error: str | None = None


class QStashProducer:
    def __init__(self, base_url: str, token: str, signing_key: str, max_retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.signing_key = signing_key
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Upstash-Signing-Key": self.signing_key,
            }
        )

    def publish(self, topic: str, body: dict) -> PublishResult:
        url = f"{self.base_url}/v2/publish/{topic}"
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(url, json=body, timeout=10)
                if 200 <= response.status_code < 300:
                    payload = response.json() if response.content else {}
                    return PublishResult(
                        success=True,
                        topic=topic,
                        attempts=attempt,
                        status_code=response.status_code,
                        message_id=payload.get("messageId"),
                    )
                if response.status_code >= 500:
                    last_error = f"upstream server error: {response.status_code}"
                else:
                    return PublishResult(
                        success=False,
                        topic=topic,
                        attempts=attempt,
                        status_code=response.status_code,
                        message_id=None,
                        error=response.text[:400],
                    )
            except requests.RequestException as exc:
                last_error = str(exc)

            if attempt < self.max_retries:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        return PublishResult(
            success=False,
            topic=topic,
            attempts=self.max_retries,
            status_code=None,
            message_id=None,
            error=last_error or "publish failed",
        )

    def close(self) -> None:
        self.session.close()
