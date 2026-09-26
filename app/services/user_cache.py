"""Redis-backed cache for authenticated user profiles."""

import logging
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.models.user import User
from app.schemas.user import AuthenticatedUser

logger = logging.getLogger(__name__)
settings = get_settings()


class UserCacheProtocol(Protocol):
    """Operations required by the authentication dependency."""

    async def get(self, user_id: int) -> AuthenticatedUser | None:
        """Return a cached user when present."""

    async def set(self, user: User | AuthenticatedUser) -> AuthenticatedUser:
        """Cache and return a validated user representation."""

    async def delete(self, user_id: int) -> None:
        """Invalidate one cached user."""


class RedisUserCache:
    """Store minimal public authentication state in Redis with a bounded TTL."""

    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _key(user_id: int) -> str:
        return f"auth:user:{user_id}"

    async def get(self, user_id: int) -> AuthenticatedUser | None:
        """Read and validate a cached user, tolerating Redis outages."""

        try:
            payload = await self.client.get(self._key(user_id))
        except RedisError:
            logger.exception("Redis user-cache read failed")
            return None
        if payload is None:
            return None
        try:
            return AuthenticatedUser.model_validate_json(payload)
        except ValueError:
            await self.delete(user_id)
            return None

    async def set(self, user: User | AuthenticatedUser) -> AuthenticatedUser:
        """Serialize a user without credentials and cache it with expiration."""

        cached = AuthenticatedUser.model_validate(user)
        try:
            await self.client.set(
                self._key(cached.id),
                cached.model_dump_json(),
                ex=self.ttl_seconds,
            )
        except RedisError:
            logger.exception("Redis user-cache write failed")
        return cached

    async def delete(self, user_id: int) -> None:
        """Remove stale user state, tolerating Redis outages."""

        try:
            await self.client.delete(self._key(user_id))
        except RedisError:
            logger.exception("Redis user-cache invalidation failed")


redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
user_cache = RedisUserCache(redis_client, settings.user_cache_ttl_seconds)


def get_user_cache() -> UserCacheProtocol:
    """Provide the shared user cache as an injectable FastAPI dependency."""

    return user_cache


async def close_user_cache() -> None:
    """Close the Redis connection pool during application shutdown."""

    await redis_client.aclose()
