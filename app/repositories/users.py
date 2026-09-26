"""Asynchronous persistence operations for users and security state."""

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.schemas.user import UserRegister


class DuplicateUserError(ValueError):
    """Raised when a username or email is already registered."""


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    """Return a user by primary key."""

    return await db.get(User, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Return a user by normalized email address."""

    statement = select(User).where(func.lower(User.email) == email.lower())
    return await db.scalar(statement)


async def get_user_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    """Find a user by either username or email address."""

    normalized = identifier.strip().lower()
    statement = select(User).where(
        or_(
            func.lower(User.username) == normalized,
            func.lower(User.email) == normalized,
        )
    )
    return await db.scalar(statement)


async def create_user(
    db: AsyncSession,
    user_data: UserRegister,
    hashed_password: str,
) -> User:
    """Create an unverified user while handling uniqueness races."""

    user = User(
        username=user_data.username,
        email=str(user_data.email),
        hashed_password=hashed_password,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise DuplicateUserError from error
    await db.refresh(user)
    return user


async def verify_user_email(db: AsyncSession, user: User) -> User:
    """Mark a user's email as verified."""

    user.is_verified = True
    await db.commit()
    await db.refresh(user)
    return user


async def update_avatar(db: AsyncSession, user: User, avatar_url: str) -> User:
    """Persist a user's Cloudinary avatar URL."""

    user.avatar_url = avatar_url
    await db.commit()
    await db.refresh(user)
    return user


async def update_avatar_by_id(
    db: AsyncSession,
    user_id: int,
    avatar_url: str,
) -> User:
    """Update an avatar when authentication supplied a cached user object."""

    user = await get_user(db, user_id)
    if user is None:
        raise LookupError("user not found")
    return await update_avatar(db, user, avatar_url)


async def store_refresh_token_hash(
    db: AsyncSession,
    user: User,
    token_hash: str,
) -> None:
    """Store only the digest of the latest valid refresh token."""

    user.refresh_token_hash = token_hash
    await db.commit()


async def rotate_refresh_token_hash(
    db: AsyncSession,
    *,
    user_id: int,
    auth_version: int,
    current_hash: str,
    replacement_hash: str,
) -> User | None:
    """Atomically consume one refresh token and store its replacement."""

    statement = (
        update(User)
        .where(
            User.id == user_id,
            User.auth_version == auth_version,
            User.refresh_token_hash == current_hash,
        )
        .values(refresh_token_hash=replacement_hash)
        .returning(User)
    )
    result = await db.execute(statement)
    user = result.scalar_one_or_none()
    await db.commit()
    return user


async def revoke_refresh_token(
    db: AsyncSession,
    *,
    user_id: int,
    token_hash: str,
) -> bool:
    """Revoke a refresh token only when its digest matches the stored value."""

    statement = (
        update(User)
        .where(User.id == user_id, User.refresh_token_hash == token_hash)
        .values(refresh_token_hash=None)
    )
    result = await db.execute(statement)
    await db.commit()
    return bool(result.rowcount)


async def store_password_reset_token(
    db: AsyncSession,
    user: User,
    *,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """Store a one-time password-reset digest and expiration timestamp."""

    user.password_reset_token_hash = token_hash
    user.password_reset_expires_at = expires_at
    await db.commit()


async def consume_password_reset_token(
    db: AsyncSession,
    *,
    token_hash: str,
    now: datetime,
    hashed_password: str,
) -> User | None:
    """Atomically consume a reset token, replace the password, and revoke sessions."""

    statement = (
        update(User)
        .where(
            User.password_reset_token_hash == token_hash,
            User.password_reset_expires_at > now,
        )
        .values(
            hashed_password=hashed_password,
            auth_version=User.auth_version + 1,
            refresh_token_hash=None,
            password_reset_token_hash=None,
            password_reset_expires_at=None,
        )
        .returning(User)
    )
    result = await db.execute(statement)
    user = result.scalar_one_or_none()
    await db.commit()
    return user


async def update_role(db: AsyncSession, user: User, role: UserRole) -> User:
    """Replace a user's authorization role."""

    user.role = role
    await db.commit()
    await db.refresh(user)
    return user
