"""Add roles, refresh-token state, and password-reset state.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add authorization roles and revocable authentication state."""

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            server_default="user",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_reset_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "password_reset_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_users_role_valid",
        "users",
        "role IN ('user', 'admin')",
    )
    op.create_index(
        "ix_users_password_reset_token_hash",
        "users",
        ["password_reset_token_hash"],
        unique=False,
    )


def downgrade() -> None:
    """Remove role and token-revocation state."""

    op.drop_index("ix_users_password_reset_token_hash", table_name="users")
    op.drop_constraint("ck_users_role_valid", "users", type_="check")
    op.drop_column("users", "password_reset_expires_at")
    op.drop_column("users", "password_reset_token_hash")
    op.drop_column("users", "refresh_token_hash")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "role")
