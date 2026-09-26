"""Shared asynchronous test fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-longer-than-32-characters"
os.environ["EMAIL_BACKEND"] = "console"
os.environ["CORS_ORIGINS"] = '["http://test-frontend"]'
os.environ["ME_RATE_LIMIT_REQUESTS"] = "5"
os.environ["ME_RATE_LIMIT_WINDOW_SECONDS"] = "60"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.user import AuthenticatedUser  # noqa: E402
from app.services.rate_limit import me_rate_limiter  # noqa: E402
from app.services.user_cache import get_user_cache  # noqa: E402


class MemoryUserCache:
    """Small deterministic cache used by API integration tests."""

    def __init__(self) -> None:
        self.users: dict[int, AuthenticatedUser] = {}

    async def get(self, user_id: int) -> AuthenticatedUser | None:
        """Return a cached user."""

        return self.users.get(user_id)

    async def set(self, user: object) -> AuthenticatedUser:
        """Validate and cache a user."""

        cached = AuthenticatedUser.model_validate(user)
        self.users[cached.id] = cached
        return cached

    async def delete(self, user_id: int) -> None:
        """Invalidate a cached user."""

        self.users.pop(user_id, None)


@pytest.fixture
def memory_user_cache() -> MemoryUserCache:
    """Provide an isolated authentication cache for each integration test."""

    return MemoryUserCache()


@pytest.fixture
def anyio_backend() -> str:
    """Run asynchronous tests on the asyncio backend used by the application."""

    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an isolated asynchronous in-memory database for each test."""

    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = async_sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with testing_session() as session:
        yield session

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def client(
    db_session: AsyncSession,
    memory_user_cache: MemoryUserCache,
) -> AsyncGenerator[AsyncClient, None]:
    """Return an async API client wired to the isolated database."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    await me_rate_limiter.reset()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_user_cache] = lambda: memory_user_cache
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
    await me_rate_limiter.reset()
