"""FastAPI application entry point and resource lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.session import engine
from app.routers.auth import router as auth_router
from app.routers.contacts import router as contacts_router
from app.routers.users import router as users_router
from app.schemas.service import HealthResponse
from app.services.user_cache import close_user_cache

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release pooled database connections when the application stops."""

    yield
    await close_user_cache()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=(
        "An asynchronous REST API with verified accounts, rotating JWT tokens, "
        "Redis caching, role-based access, owner-isolated contacts, and secure "
        "password recovery."
    ),
    version=settings.app_version,
    contact={"name": "Repository maintainer"},
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(contacts_router)


@app.get("/", tags=["service"], summary="API information")
async def api_information() -> dict[str, str]:
    """Point clients to the interactive documentation."""

    return {
        "name": settings.app_name,
        "documentation": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["service"])
async def health_check() -> HealthResponse:
    """Return a lightweight process health check."""

    return HealthResponse(status="ok")
