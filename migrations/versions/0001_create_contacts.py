"""Create contacts table.

Revision ID: 0001
Revises:
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the contacts table and searchable indexes."""

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=50), nullable=False),
        sa.Column("last_name", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("birthday", sa.Date(), nullable=False),
        sa.Column("additional_data", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_contacts"),
        sa.UniqueConstraint("email", name="uq_contacts_email"),
    )
    op.create_index("ix_contacts_birthday", "contacts", ["birthday"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_first_name", "contacts", ["first_name"])
    op.create_index("ix_contacts_last_name", "contacts", ["last_name"])


def downgrade() -> None:
    """Remove the contacts table."""

    op.drop_index("ix_contacts_last_name", table_name="contacts")
    op.drop_index("ix_contacts_first_name", table_name="contacts")
    op.drop_index("ix_contacts_email", table_name="contacts")
    op.drop_index("ix_contacts_birthday", table_name="contacts")
    op.drop_table("contacts")
