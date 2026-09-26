"""Small in-process fixed-window limiter for the current-user route."""

import asyncio
from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, status

from app.core.config import get_settings


class InMemoryRateLimiter:
    """Limit requests per key inside one API process."""

    def __init__(self, requests: int, window_seconds: int) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        """Record a request or raise HTTP 429 when the limit is exhausted."""

        now = monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests:
                retry_after = max(1, int(events[0] + self.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests to /me",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

    async def reset(self) -> None:
        """Clear limiter state, primarily for isolated tests."""

        async with self._lock:
            self._events.clear()


settings = get_settings()
me_rate_limiter = InMemoryRateLimiter(
    requests=settings.me_rate_limit_requests,
    window_seconds=settings.me_rate_limit_window_seconds,
)
