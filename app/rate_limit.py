"""Simple in-process rate limiting helpers."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int | None


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, max_requests: int, window_seconds: int) -> RateLimitResult:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            q = self._hits[key]
            while q and q[0] <= cutoff:
                q.popleft()

            if len(q) >= max_requests:
                retry_after = max(1, int(q[0] + window_seconds - now))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

            q.append(now)
            return RateLimitResult(allowed=True, retry_after_seconds=None)


agent_register_limiter = InMemoryRateLimiter()
