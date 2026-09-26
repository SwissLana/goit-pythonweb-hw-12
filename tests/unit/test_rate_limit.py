"""Unit tests for the fixed-window route limiter."""

import pytest
from fastapi import HTTPException

from app.services.rate_limit import InMemoryRateLimiter

pytestmark = pytest.mark.anyio


async def test_limiter_rejects_excess_and_can_be_reset() -> None:
    limiter = InMemoryRateLimiter(requests=1, window_seconds=60)
    await limiter.check("user-1")

    with pytest.raises(HTTPException) as raised:
        await limiter.check("user-1")
    assert raised.value.status_code == 429
    assert "Retry-After" in raised.value.headers

    await limiter.reset()
    await limiter.check("user-1")
