"""Unit tests for schema-level boundary validation."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.contact import ContactCreate, ContactUpdate
from app.schemas.user import UserRegister


def test_registration_normalizes_identity_fields() -> None:
    user = UserRegister(
        username="Ada_Lovelace",
        email="ADA@EXAMPLE.COM",
        password="SecurePassword123",
    )
    assert user.username == "ada_lovelace"
    assert str(user.email) == "ada@example.com"


def test_contact_rejects_future_birthdays_and_short_phone_numbers() -> None:
    with pytest.raises(ValidationError):
        ContactCreate(
            first_name="Future",
            last_name="Person",
            email="future@example.com",
            phone="1234567",
            birthday=date.today() + timedelta(days=1),
        )
    with pytest.raises(ValidationError):
        ContactCreate(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="123",
            birthday=date(1815, 12, 10),
        )


def test_patch_requires_a_field_and_rejects_null_required_values() -> None:
    with pytest.raises(ValidationError):
        ContactUpdate()
    with pytest.raises(ValidationError):
        ContactUpdate(first_name=None)
    assert ContactUpdate(additional_data=None).additional_data is None
