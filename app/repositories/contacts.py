"""Asynchronous data-access operations and birthday queries for contacts."""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactUpdate


class DuplicateContactEmailError(ValueError):
    """Raised when a contact email is already stored."""


async def get_owned_contact(
    db: AsyncSession,
    contact_id: int,
    owner_id: int,
) -> Contact | None:
    """Return a contact only when it belongs to the specified owner."""

    statement = select(Contact).where(
        Contact.id == contact_id,
        Contact.owner_id == owner_id,
    )
    return await db.scalar(statement)


async def get_contacts(
    db: AsyncSession,
    *,
    owner_id: int,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
) -> list[Contact]:
    """Return contacts with optional case-insensitive search filters."""

    statement = select(Contact).where(Contact.owner_id == owner_id)

    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                Contact.first_name.ilike(pattern),
                Contact.last_name.ilike(pattern),
                Contact.email.ilike(pattern),
            )
        )
    if first_name:
        statement = statement.where(Contact.first_name.ilike(f"%{first_name}%"))
    if last_name:
        statement = statement.where(Contact.last_name.ilike(f"%{last_name}%"))
    if email:
        statement = statement.where(Contact.email.ilike(f"%{email}%"))

    statement = statement.order_by(Contact.id).offset(skip).limit(limit)
    result = await db.scalars(statement)
    return list(result)


async def _commit_contact(db: AsyncSession, contact: Contact) -> Contact:
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise DuplicateContactEmailError from error
    await db.refresh(contact)
    return contact


async def create_contact(
    db: AsyncSession,
    contact_data: ContactCreate,
    owner_id: int,
) -> Contact:
    """Create and persist a contact."""

    contact = Contact(owner_id=owner_id, **contact_data.model_dump(mode="python"))
    db.add(contact)
    return await _commit_contact(db, contact)


async def replace_contact(
    db: AsyncSession,
    contact: Contact,
    contact_data: ContactCreate,
) -> Contact:
    """Replace every editable field on a contact."""

    for field, value in contact_data.model_dump(mode="python").items():
        setattr(contact, field, value)
    return await _commit_contact(db, contact)


async def update_contact(
    db: AsyncSession,
    contact: Contact,
    contact_data: ContactUpdate,
) -> Contact:
    """Update only fields included in the request."""

    for field, value in contact_data.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    return await _commit_contact(db, contact)


async def delete_contact(db: AsyncSession, contact: Contact) -> None:
    """Delete a contact."""

    await db.delete(contact)
    await db.commit()


def _birthday_for_year(birthday: date, year: int) -> date:
    """Map a birthday to a year, observing Feb 29 on Feb 28 in non-leap years."""

    try:
        return birthday.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def next_birthday(birthday: date, today: date) -> date:
    """Calculate the next occurrence of a birthday on or after today."""

    occurrence = _birthday_for_year(birthday, today.year)
    if occurrence < today:
        occurrence = _birthday_for_year(birthday, today.year + 1)
    return occurrence


async def get_upcoming_birthdays(
    db: AsyncSession,
    *,
    owner_id: int,
    days: int = 7,
    today: date | None = None,
) -> list[Contact]:
    """Return birthdays occurring today or within the configured window."""

    reference_date = today or date.today()
    result = await db.scalars(select(Contact).where(Contact.owner_id == owner_id))
    contacts = result.all()
    upcoming = [
        contact
        for contact in contacts
        if 0
        <= (next_birthday(contact.birthday, reference_date) - reference_date).days
        < days
    ]
    return sorted(
        upcoming,
        key=lambda contact: (
            next_birthday(contact.birthday, reference_date),
            contact.id,
        ),
    )
