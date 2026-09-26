"""Reusable API-test helpers."""

from datetime import date

from httpx import AsyncClient

from app.core.security import create_email_verification_token

DEFAULT_PASSWORD = "SecurePassword123"


def contact_payload(
    *,
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    email: str = "ada.contact@example.com",
    birthday: str = "1815-12-10",
) -> dict[str, str]:
    """Build a valid contact request."""

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": "+44 20 7946 0958",
        "birthday": birthday,
        "additional_data": "Mathematician and writer",
    }


async def register_user(
    client: AsyncClient,
    *,
    username: str = "ada",
    email: str = "ada@example.com",
    password: str = DEFAULT_PASSWORD,
) -> dict:
    """Register a user and return the response document."""

    response = await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def verify_user(client: AsyncClient, user_id: int) -> None:
    """Verify a registered user through the public endpoint."""

    token = create_email_verification_token(user_id)
    response = await client.get(f"/api/auth/verify-email/{token}")
    assert response.status_code == 200, response.text


async def login_user(
    client: AsyncClient,
    *,
    identifier: str = "ada@example.com",
    password: str = DEFAULT_PASSWORD,
) -> str:
    """Authenticate and return the access token."""

    response = await client.post(
        "/api/auth/login",
        data={"username": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def login_tokens(
    client: AsyncClient,
    *,
    identifier: str = "ada@example.com",
    password: str = DEFAULT_PASSWORD,
) -> dict[str, str]:
    """Authenticate and return the complete access/refresh pair."""

    response = await client.post(
        "/api/auth/login",
        data={"username": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def authenticated_user(
    client: AsyncClient,
    *,
    username: str = "ada",
    email: str = "ada@example.com",
    password: str = DEFAULT_PASSWORD,
) -> tuple[dict, dict[str, str]]:
    """Register, verify, and authenticate a user."""

    user = await register_user(
        client,
        username=username,
        email=email,
        password=password,
    )
    await verify_user(client, user["id"])
    token = await login_user(client, identifier=email, password=password)
    return user, {"Authorization": f"Bearer {token}"}


def birthday_in_year(day: date, year: int = 2000) -> str:
    """Map a month and day to a stable historical year for test payloads."""

    return str(date(year, day.month, day.day))
