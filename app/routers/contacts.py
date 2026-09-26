"""Asynchronous HTTP endpoints for contact management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.db.session import get_db
from app.repositories import contacts as repository
from app.schemas.contact import ContactCreate, ContactResponse, ContactUpdate

router = APIRouter(prefix="/api/contacts", tags=["contacts"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
ContactId = Annotated[int, Path(ge=1, description="Contact identifier")]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Contact not found",
    )


def _email_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A contact with this email already exists",
    )


@router.post(
    "",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a contact",
)
async def create_contact(
    contact_data: ContactCreate,
    db: DatabaseSession,
    current_user: CurrentUser,
):
    """Create a contact with a unique, normalized email address."""

    try:
        return await repository.create_contact(db, contact_data, current_user.id)
    except repository.DuplicateContactEmailError as error:
        raise _email_conflict() from error


@router.get(
    "",
    response_model=list[ContactResponse],
    summary="List and search contacts",
)
async def list_contacts(
    db: DatabaseSession,
    current_user: CurrentUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
            description="Search first name, last name, and email at once",
        ),
    ] = None,
    first_name: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    last_name: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    email: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
):
    """List contacts, optionally filtering by name or email."""

    return await repository.get_contacts(
        db,
        owner_id=current_user.id,
        skip=skip,
        limit=limit,
        search=search,
        first_name=first_name,
        last_name=last_name,
        email=email,
    )


@router.get(
    "/upcoming-birthdays",
    response_model=list[ContactResponse],
    summary="List upcoming birthdays",
)
async def upcoming_birthdays(
    db: DatabaseSession,
    current_user: CurrentUser,
    days: Annotated[
        int,
        Query(ge=1, le=30, description="Size of the birthday window in days"),
    ] = 7,
):
    """Return birthdays from today through the next six days by default."""

    return await repository.get_upcoming_birthdays(
        db,
        owner_id=current_user.id,
        days=days,
    )


@router.get(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Get a contact",
)
async def get_contact(
    contact_id: ContactId,
    db: DatabaseSession,
    current_user: CurrentUser,
):
    """Return one contact by identifier."""

    contact = await repository.get_owned_contact(db, contact_id, current_user.id)
    if contact is None:
        raise _not_found()
    return contact


@router.put(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Replace a contact",
)
async def replace_contact(
    contact_id: ContactId,
    contact_data: ContactCreate,
    db: DatabaseSession,
    current_user: CurrentUser,
):
    """Replace all editable fields on an existing contact."""

    contact = await repository.get_owned_contact(db, contact_id, current_user.id)
    if contact is None:
        raise _not_found()
    try:
        return await repository.replace_contact(db, contact, contact_data)
    except repository.DuplicateContactEmailError as error:
        raise _email_conflict() from error


@router.patch(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Update part of a contact",
)
async def update_contact(
    contact_id: ContactId,
    contact_data: ContactUpdate,
    db: DatabaseSession,
    current_user: CurrentUser,
):
    """Update only the supplied fields on an existing contact."""

    contact = await repository.get_owned_contact(db, contact_id, current_user.id)
    if contact is None:
        raise _not_found()
    try:
        return await repository.update_contact(db, contact, contact_data)
    except repository.DuplicateContactEmailError as error:
        raise _email_conflict() from error


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a contact",
)
async def delete_contact(
    contact_id: ContactId,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    """Permanently delete a contact."""

    contact = await repository.get_owned_contact(db, contact_id, current_user.id)
    if contact is None:
        raise _not_found()
    await repository.delete_contact(db, contact)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
