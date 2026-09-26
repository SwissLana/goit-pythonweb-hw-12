"""Unit tests for Redis user-cache serialization and invalidation."""

from datetime import datetime, timezone

import fakeredis.aioredis
import pytest

from app.models.user import UserRole
from app.schemas.user import AuthenticatedUser
from app.services.user_cache import RedisUserCache

pytestmark = pytest.mark.anyio


def cached_user() -> AuthenticatedUser:
    """Build a representative cache-safe user profile."""

    now = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=1,
        username="ada",
        email="ada@example.com",
        avatar_url=None,
        is_verified=True,
        role=UserRole.USER,
        auth_version=3,
        created_at=now,
        updated_at=now,
    )


async def test_cache_round_trip_and_invalidation() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = RedisUserCache(client, ttl_seconds=60)
    user = cached_user()

    await cache.set(user)
    loaded = await cache.get(user.id)
    assert loaded == user
    assert await client.ttl("auth:user:1") > 0

    await cache.delete(user.id)
    assert await cache.get(user.id) is None
    await client.aclose()


async def test_corrupted_cache_entry_is_removed() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = RedisUserCache(client, ttl_seconds=60)
    await client.set("auth:user:1", "not-json")

    assert await cache.get(1) is None
    assert await client.exists("auth:user:1") == 0
    await client.aclose()
