"""Add users, authentication fields, and contact ownership.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users and make every contact belong to one user."""

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    op.add_column("contacts", sa.Column("owner_id", sa.Integer(), nullable=True))

    connection = op.get_bind()
    contact_count = connection.scalar(sa.text("SELECT COUNT(*) FROM contacts"))
    if contact_count:
        legacy_user_id = connection.scalar(
            sa.text(
                """
                INSERT INTO users (
                    username,
                    email,
                    hashed_password,
                    is_verified,
                    created_at,
                    updated_at
                )
                VALUES (
                    'legacy_owner',
                    'legacy-owner@invalid.local',
                    '!legacy-account-disabled!',
                    TRUE,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                RETURNING id
                """
            )
        )
        connection.execute(
            sa.text("UPDATE contacts SET owner_id = :owner_id"),
            {"owner_id": legacy_user_id},
        )

    op.alter_column(
        "contacts",
        "owner_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_contacts_owner_id_users",
        "contacts",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_contacts_owner_id", "contacts", ["owner_id"])
    op.drop_constraint("uq_contacts_email", "contacts", type_="unique")
    op.create_unique_constraint(
        "uq_contacts_owner_email",
        "contacts",
        ["owner_id", "email"],
    )


def downgrade() -> None:
    """Remove users and restore globally unique contact emails."""

    op.drop_constraint("uq_contacts_owner_email", "contacts", type_="unique")
    op.create_unique_constraint("uq_contacts_email", "contacts", ["email"])
    op.drop_index("ix_contacts_owner_id", table_name="contacts")
    op.drop_constraint(
        "fk_contacts_owner_id_users",
        "contacts",
        type_="foreignkey",
    )
    op.drop_column("contacts", "owner_id")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
