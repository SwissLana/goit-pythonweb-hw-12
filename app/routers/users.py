"""Authenticated user-profile endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import AdminUser, CurrentUser
from app.db.session import get_db
from app.repositories import users as repository
from app.schemas.user import AuthenticatedUser, RoleUpdate, UserResponse
from app.services import cloudinary as cloudinary_service
from app.services.rate_limit import me_rate_limiter
from app.services.user_cache import UserCacheProtocol, get_user_cache

router = APIRouter(prefix="/api/users", tags=["users"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AvatarFile = Annotated[UploadFile, File(description="JPEG, PNG, WebP, or GIF image")]
UserCache = Annotated[UserCacheProtocol, Depends(get_user_cache)]


async def rate_limited_current_user(
    current_user: CurrentUser,
) -> AuthenticatedUser:
    """Apply the configured per-user limit to the `/me` endpoint."""

    await me_rate_limiter.check(str(current_user.id))
    return current_user


RateLimitedUser = Annotated[AuthenticatedUser, Depends(rate_limited_current_user)]


@router.get("/me", response_model=UserResponse, summary="Get the current user")
async def get_me(current_user: RateLimitedUser) -> AuthenticatedUser:
    """Return the authenticated user's public profile with rate limiting."""

    return current_user


@router.patch(
    "/me/avatar",
    response_model=UserResponse,
    summary="Update the current user's avatar",
)
async def update_avatar(
    avatar: AvatarFile,
    current_user: AdminUser,
    db: DatabaseSession,
    cache: UserCache,
) -> UserResponse:
    """Allow an administrator to validate and replace their Cloudinary avatar."""

    if avatar.content_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Avatar must be a JPEG, PNG, WebP, or GIF image",
        )

    settings = get_settings()
    image = await avatar.read(settings.max_avatar_bytes + 1)
    await avatar.close()
    if not image:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Avatar file is empty",
        )
    if len(image) > settings.max_avatar_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Avatar exceeds the configured file-size limit",
        )

    try:
        avatar_url = await cloudinary_service.upload_avatar(image, current_user.id)
    except cloudinary_service.CloudinaryNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Avatar storage is not configured",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Avatar upload failed",
        ) from error

    user = await repository.update_avatar_by_id(db, current_user.id, avatar_url)
    await cache.delete(user.id)
    return user


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Change a user's role",
)
async def change_user_role(
    role_data: RoleUpdate,
    db: DatabaseSession,
    _: AdminUser,
    cache: UserCache,
    user_id: Annotated[int, Path(ge=1)],
) -> UserResponse:
    """Allow an administrator to grant or revoke administrator privileges."""

    user = await repository.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    updated = await repository.update_role(db, user, role_data.role)
    await cache.delete(user_id)
    return updated
