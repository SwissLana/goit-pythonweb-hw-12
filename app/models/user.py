"""Registered API user model and authorization roles."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.contact import Contact


class UserRole(str, Enum):
    """Roles supported by the application authorization policy."""

    USER = "user"
    ADMIN = "admin"


class User(TimestampMixin, Base):
    """An account that owns contacts and authenticates with a password."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        String(20), default=UserRole.USER, nullable=False
    )
    auth_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r})"
