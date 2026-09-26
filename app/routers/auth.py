"""Registration, login, token rotation, verification, and password reset."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_email_verification_token,
    create_password_reset_token,
    create_token_pair,
    credentials_exception,
    decode_token,
    hash_password_async,
    token_digest,
    verify_password_async,
)
from app.db.session import get_db
from app.repositories import users as repository
from app.schemas.user import (
    EmailRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRegister,
    UserResponse,
)
from app.services.email import send_password_reset_email, send_verification_email
from app.services.user_cache import UserCacheProtocol, get_user_cache

router = APIRouter(prefix="/api/auth", tags=["authentication"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]
UserCache = Annotated[UserCacheProtocol, Depends(get_user_cache)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user",
)
async def register_user(
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> UserResponse:
    """Register an unverified account and queue its verification message."""

    hashed_password = await hash_password_async(
        user_data.password.get_secret_value()
    )
    try:
        user = await repository.create_user(db, user_data, hashed_password)
    except repository.DuplicateUserError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username or email already exists",
        ) from error

    token = create_email_verification_token(user.id)
    background_tasks.add_task(send_verification_email, user.email, token)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive an access/refresh pair",
)
async def login_user(form_data: LoginForm, db: DatabaseSession) -> TokenResponse:
    """Authenticate by username or email and issue a rotating token pair."""

    user = await repository.get_user_by_identifier(db, form_data.username)
    password_matches = user is not None and await verify_password_async(
        form_data.password, user.hashed_password
    )
    if user is None or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not verified",
        )

    tokens = create_token_pair(user.id, user.auth_version)
    await repository.store_refresh_token_hash(
        db,
        user,
        token_digest(tokens.refresh_token),
    )
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate a refresh token",
)
async def refresh_tokens(
    request: RefreshTokenRequest,
    db: DatabaseSession,
) -> TokenResponse:
    """Consume one valid refresh token and return a fresh token pair."""

    raw_token = request.refresh_token.get_secret_value()
    try:
        claims = decode_token(raw_token, "refresh")
    except ValueError as error:
        raise credentials_exception() from error

    replacement = create_token_pair(claims.user_id, claims.auth_version)
    user = await repository.rotate_refresh_token_hash(
        db,
        user_id=claims.user_id,
        auth_version=claims.auth_version,
        current_hash=token_digest(raw_token),
        replacement_hash=token_digest(replacement.refresh_token),
    )
    if user is None or not user.is_verified:
        raise credentials_exception()
    return replacement


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
)
async def logout(request: RefreshTokenRequest, db: DatabaseSession) -> Response:
    """Revoke the submitted refresh token without storing it in plaintext."""

    raw_token = request.refresh_token.get_secret_value()
    try:
        claims = decode_token(raw_token, "refresh")
    except ValueError as error:
        raise credentials_exception() from error
    revoked = await repository.revoke_refresh_token(
        db,
        user_id=claims.user_id,
        token_hash=token_digest(raw_token),
    )
    if not revoked:
        raise credentials_exception()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/verify-email/{token}",
    response_model=MessageResponse,
    summary="Verify an email address",
)
async def verify_email(
    token: Annotated[str, Path(min_length=20)],
    db: DatabaseSession,
    cache: UserCache,
) -> MessageResponse:
    """Confirm the email address represented by a verification token."""

    try:
        claims = decode_token(token, "verify_email")
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        ) from error

    user = await repository.get_user(db, claims.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if not user.is_verified:
        await repository.verify_user_email(db, user)
        await cache.delete(user.id)
    return MessageResponse(message="Email address verified successfully")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend email verification",
)
async def resend_verification(
    request: EmailRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> MessageResponse:
    """Queue another verification message without revealing account existence."""

    user = await repository.get_user_by_email(db, str(request.email))
    if user is not None and not user.is_verified:
        token = create_email_verification_token(user.id)
        background_tasks.add_task(send_verification_email, user.email, token)
    return MessageResponse(
        message="If the account exists and is unverified, a new email was sent"
    )


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset",
)
async def request_password_reset(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> MessageResponse:
    """Create a short-lived one-time reset token without disclosing accounts."""

    user = await repository.get_user_by_email(db, str(request.email))
    if user is not None and user.is_verified:
        raw_token, digest = create_password_reset_token()
        settings = get_settings()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.password_reset_expire_minutes
        )
        await repository.store_password_reset_token(
            db,
            user,
            token_hash=digest,
            expires_at=expires_at,
        )
        background_tasks.add_task(send_password_reset_email, user.email, raw_token)
    return MessageResponse(
        message="If a verified account exists, password-reset instructions were sent"
    )


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    summary="Confirm a password reset",
)
async def confirm_password_reset(
    request: PasswordResetConfirm,
    db: DatabaseSession,
    cache: UserCache,
) -> MessageResponse:
    """Consume a one-time reset token, replace the password, and revoke sessions."""

    raw_token = request.token.get_secret_value()
    hashed_password = await hash_password_async(
        request.new_password.get_secret_value()
    )
    user = await repository.consume_password_reset_token(
        db,
        token_hash=token_digest(raw_token),
        now=datetime.now(timezone.utc),
        hashed_password=hashed_password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password-reset token",
        )
    await cache.delete(user.id)
    return MessageResponse(message="Password reset successfully")
