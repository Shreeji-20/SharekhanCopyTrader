import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request) -> None:
        limit = get_settings().broker_rate_limit_per_minute
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self._events[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Broker rate limit exceeded")
        window.append(now)


rate_limiter = InMemoryRateLimiter()

