from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, *, bucket: str, subject: str, limit: int, window_seconds: int) -> RateLimitResult:
        if limit <= 0 or window_seconds <= 0:
            return RateLimitResult(allowed=True, retry_after_seconds=0, remaining=max(limit, 0))

        now = monotonic()
        key = f"{bucket}:{subject}"
        with self._lock:
            events = self._events[key]
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= limit:
                retry_after = max(1, int(events[0] + window_seconds - now))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after, remaining=0)

            events.append(now)
            return RateLimitResult(
                allowed=True,
                retry_after_seconds=0,
                remaining=max(0, limit - len(events)),
            )
