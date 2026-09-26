"""Pydantic schemas and validation rules for contacts."""

import re
from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

PHONE_PATTERN = re.compile(r"^[0-9+() .-]+$")


def validate_phone_value(value: str) -> str:
    """Validate common phone formatting and a realistic digit count."""

    if not PHONE_PATTERN.fullmatch(value):
        raise ValueError("phone number contains unsupported characters")
    digit_count = sum(character.isdigit() for character in value)
    if not 7 <= digit_count <= 15:
        raise ValueError("phone number must contain between 7 and 15 digits")
    return value


def validate_birthday_value(value: date) -> date:
    """Reject valid calendar dates that are still in the future."""

    if value > date.today():
        raise ValueError("birthday cannot be in the future")
    return value


class ContactFields(BaseModel):
    """Fields shared by create and response schemas."""

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(min_length=1, max_length=50, examples=["Ada"])
    last_name: str = Field(min_length=1, max_length=50, examples=["Lovelace"])
    email: EmailStr = Field(examples=["ada@example.com"])
    phone: str = Field(min_length=7, max_length=30, examples=["+44 20 7946 0958"])
    birthday: date = Field(examples=["1815-12-10"])
    additional_data: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Store email addresses in lowercase for consistent uniqueness."""

        return str(value).lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_phone_value(value)

    @field_validator("birthday")
    @classmethod
    def validate_birthday(cls, value: date) -> date:
        return validate_birthday_value(value)


class ContactCreate(ContactFields):
    """Payload for creating or fully replacing a contact."""


class ContactUpdate(BaseModel):
    """Payload for partially updating a contact."""

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    birthday: date | None = None
    additional_data: str | None = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def validate_patch_fields(cls, data: object) -> object:
        """Require a change and reject null for non-nullable contact fields."""

        if not isinstance(data, dict):
            return data
        if not data:
            raise ValueError("at least one field must be provided")

        required_fields = {
            "first_name",
            "last_name",
            "email",
            "phone",
            "birthday",
        }
        null_fields = sorted(
            field for field in required_fields if field in data and data[field] is None
        )
        if null_fields:
            fields = ", ".join(null_fields)
            raise ValueError(f"these fields cannot be null: {fields}")
        return data

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).lower() if value is not None else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return validate_phone_value(value) if value is not None else None

    @field_validator("birthday")
    @classmethod
    def validate_birthday(cls, value: date | None) -> date | None:
        return validate_birthday_value(value) if value is not None else None


class ContactResponse(ContactFields):
    """Contact returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
