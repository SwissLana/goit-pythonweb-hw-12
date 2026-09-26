"""Pydantic schemas for registration, authentication, and user responses."""

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

from app.models.user import UserRole


class UserRegister(BaseModel):
    """Payload accepted when creating a user account."""

    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[A-Za-z0-9_.-]+$",
        examples=["ada_lovelace"],
    )
    email: EmailStr = Field(examples=["ada@example.com"])
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        """Normalize usernames for predictable uniqueness and login."""

        return value.lower()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normalize email addresses for predictable uniqueness and login."""

        return str(value).lower()


class UserResponse(BaseModel):
    """Public user data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    avatar_url: str | None
    is_verified: bool
    role: UserRole
    created_at: datetime
    updated_at: datetime


class AuthenticatedUser(UserResponse):
    """Validated user representation stored in the Redis authentication cache."""

    auth_version: int


class TokenResponse(BaseModel):
    """OAuth2 bearer access and rotating refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class EmailRequest(BaseModel):
    """Request a new verification message without exposing account existence."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class MessageResponse(BaseModel):
    """Simple operation-result message."""

    message: str


class RefreshTokenRequest(BaseModel):
    """Refresh token submitted for rotation or logout."""

    refresh_token: SecretStr = Field(min_length=20)


class PasswordResetRequest(BaseModel):
    """Email address for a non-disclosing password-reset request."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normalize an email before lookup."""

        return str(value).lower()


class PasswordResetConfirm(BaseModel):
    """One-time reset token and replacement password."""

    token: SecretStr = Field(min_length=32)
    new_password: SecretStr = Field(min_length=8, max_length=128)


class RoleUpdate(BaseModel):
    """Administrative request to replace a user's role."""

    role: Literal[UserRole.USER, UserRole.ADMIN]
