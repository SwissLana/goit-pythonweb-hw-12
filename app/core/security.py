"""Password hashing, JWT creation, authorization, and token digests."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated, Literal
from uuid import uuid4

import jwt
from anyio import to_thread
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import UserRole
from app.repositories import users as user_repository
from app.schemas.user import AuthenticatedUser, TokenResponse
from app.services.user_cache import UserCacheProtocol, get_user_cache

settings = get_settings()
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Security-relevant claims extracted from a validated JWT."""

    user_id: int
    token_type: str
    auth_version: int
    token_id: str


def hash_password(password: str) -> str:
    """Hash a plaintext password with the recommended Argon2 settings."""

    return password_hash.hash(password)


async def hash_password_async(password: str) -> str:
    """Hash a password in a worker thread to avoid blocking the event loop."""

    return await to_thread.run_sync(hash_password, password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Safely compare a plaintext password with a stored hash."""

    try:
        return password_hash.verify(password, hashed_password)
    except (UnknownHashError, ValueError, TypeError):
        return False


async def verify_password_async(password: str, hashed_password: str) -> bool:
    """Verify an Argon2 password in a worker thread."""

    return await to_thread.run_sync(verify_password, password, hashed_password)


def token_digest(token: str) -> str:
    """Return a deterministic SHA-256 digest for server-side token storage."""

    return sha256(token.encode("utf-8")).hexdigest()


def create_password_reset_token() -> tuple[str, str]:
    """Create a high-entropy opaque reset token and its storage digest."""

    token = token_urlsafe(48)
    return token, token_digest(token)


def _create_token(
    subject: int,
    token_type: Literal["access", "refresh", "verify_email"],
    expires_delta: timedelta,
    *,
    auth_version: int = 0,
) -> str:
    """Create a signed JWT with purpose, version, issuer, and audience claims."""

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "ver": auth_version,
        "jti": str(uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user_id: int, auth_version: int = 1) -> str:
    """Create a short-lived bearer access token for an authenticated user."""

    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        auth_version=auth_version,
    )


def create_refresh_token(user_id: int, auth_version: int = 1) -> str:
    """Create a longer-lived refresh token that must be rotated after use."""

    return _create_token(
        user_id,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        auth_version=auth_version,
    )


def create_token_pair(user_id: int, auth_version: int = 1) -> TokenResponse:
    """Create a matching access and refresh token pair."""

    return TokenResponse(
        access_token=create_access_token(user_id, auth_version),
        refresh_token=create_refresh_token(user_id, auth_version),
    )


def create_email_verification_token(user_id: int) -> str:
    """Create a purpose-limited token for confirming an email address."""

    return _create_token(
        user_id,
        "verify_email",
        timedelta(hours=settings.email_verification_expire_hours),
    )


def decode_token(token: str, expected_type: str) -> TokenClaims:
    """Validate a JWT and return its typed security claims."""

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": ["sub", "type", "ver", "jti", "iss", "aud", "iat", "exp"]
            },
        )
        if payload.get("type") != expected_type:
            raise InvalidTokenError("unexpected token type")
        user_id = int(payload["sub"])
        auth_version = int(payload["ver"])
        token_id = str(payload["jti"])
        if user_id < 1 or auth_version < 0 or not token_id:
            raise InvalidTokenError("invalid token claims")
        return TokenClaims(user_id, expected_type, auth_version, token_id)
    except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid or expired token") from error


def credentials_exception() -> HTTPException:
    """Return the standard OAuth2 authentication failure response."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cache: Annotated[UserCacheProtocol, Depends(get_user_cache)],
) -> AuthenticatedUser:
    """Resolve an access token from Redis first and PostgreSQL on cache miss."""

    try:
        claims = decode_token(token, "access")
    except ValueError as error:
        raise credentials_exception() from error

    cached_user = await cache.get(claims.user_id)
    if cached_user is not None:
        if cached_user.auth_version != claims.auth_version:
            raise credentials_exception()
        return cached_user

    user = await user_repository.get_user(db, claims.user_id)
    if user is None or user.auth_version != claims.auth_version:
        raise credentials_exception()
    return await cache.set(user)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> AuthenticatedUser:
    """Allow an operation only for users holding the administrator role."""

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return current_user


AdminUser = Annotated[AuthenticatedUser, Depends(require_admin)]
