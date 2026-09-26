"""Contact database model."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Contact(TimestampMixin, Base):
    """A person stored in the contact book."""

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("owner_id", "email", name="uq_contacts_owner_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    first_name: Mapped[str] = mapped_column(String(50), index=True)
    last_name: Mapped[str] = mapped_column(String(50), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(30))
    birthday: Mapped[date] = mapped_column(Date, index=True)
    additional_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped["User"] = relationship(back_populates="contacts", lazy="raise")

    def __repr__(self) -> str:
        return f"Contact(id={self.id!r}, email={self.email!r})"
