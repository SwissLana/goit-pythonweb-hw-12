"""Authenticated contact endpoint and ownership tests."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.repositories.contacts import next_birthday
from tests.helpers import authenticated_user, birthday_in_year, contact_payload

pytestmark = pytest.mark.anyio


async def create_contact(
    client: AsyncClient,
    headers: dict[str, str],
    **overrides: str,
) -> dict:
    """Create an authenticated contact and return its response document."""

    response = await client.post(
        "/api/contacts",
        json=contact_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_contact_routes_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/contacts")).status_code == 401
    assert (
        await client.post("/api/contacts", json=contact_payload())
    ).status_code == 401


async def test_complete_crud_lifecycle(client: AsyncClient) -> None:
    _, headers = await authenticated_user(client)
    created = await create_contact(client, headers)
    contact_id = created["id"]

    listed = await client.get("/api/contacts", headers=headers)
    assert [contact["id"] for contact in listed.json()] == [contact_id]

    fetched = await client.get(f"/api/contacts/{contact_id}", headers=headers)
    assert fetched.json()["first_name"] == "Ada"

    replacement = contact_payload(
        first_name="Grace",
        last_name="Hopper",
        email="grace.contact@example.com",
        birthday="1906-12-09",
    )
    replaced = await client.put(
        f"/api/contacts/{contact_id}", json=replacement, headers=headers
    )
    assert replaced.status_code == 200
    assert replaced.json()["first_name"] == "Grace"

    patched = await client.patch(
        f"/api/contacts/{contact_id}",
        json={"additional_data": "Computer science pioneer"},
        headers=headers,
    )
    assert patched.json()["additional_data"] == "Computer science pioneer"

    deleted = await client.delete(f"/api/contacts/{contact_id}", headers=headers)
    assert deleted.status_code == 204
    assert (
        await client.get(f"/api/contacts/{contact_id}", headers=headers)
    ).status_code == 404


async def test_users_can_access_only_their_own_contacts(client: AsyncClient) -> None:
    _, owner_headers = await authenticated_user(client)
    owner_contact = await create_contact(client, owner_headers)

    _, stranger_headers = await authenticated_user(
        client,
        username="grace",
        email="grace@example.com",
    )
    contact_url = f"/api/contacts/{owner_contact['id']}"

    assert (await client.get(contact_url, headers=stranger_headers)).status_code == 404
    assert (
        await client.patch(
            contact_url,
            json={"first_name": "Stolen"},
            headers=stranger_headers,
        )
    ).status_code == 404
    assert (
        await client.delete(contact_url, headers=stranger_headers)
    ).status_code == 404
    assert (await client.get("/api/contacts", headers=stranger_headers)).json() == []

    duplicate_for_other_owner = await client.post(
        "/api/contacts",
        json=contact_payload(),
        headers=stranger_headers,
    )
    assert duplicate_for_other_owner.status_code == 201


async def test_search_and_owner_scoped_email_uniqueness(client: AsyncClient) -> None:
    _, headers = await authenticated_user(client)
    await create_contact(client, headers)
    await create_contact(
        client,
        headers,
        first_name="Grace",
        last_name="Hopper",
        email="grace.contact@navy.example",
        birthday="1906-12-09",
    )

    first_name_results = await client.get(
        "/api/contacts?first_name=ada", headers=headers
    )
    last_name_results = await client.get("/api/contacts?last_name=HOP", headers=headers)
    email_results = await client.get("/api/contacts?email=navy", headers=headers)
    assert len(first_name_results.json()) == 1
    assert len(last_name_results.json()) == 1
    assert len(email_results.json()) == 1
    assert (
        await client.post("/api/contacts", json=contact_payload(), headers=headers)
    ).status_code == 409


async def test_validation_and_patch_rules(client: AsyncClient) -> None:
    _, headers = await authenticated_user(client)
    contact = await create_contact(client, headers)
    endpoint = f"/api/contacts/{contact['id']}"

    invalid_email = contact_payload(email="not-an-email")
    assert (
        await client.post("/api/contacts", json=invalid_email, headers=headers)
    ).status_code == 422

    future = contact_payload(email="future@example.com")
    future["birthday"] = str(date.today() + timedelta(days=1))
    assert (
        await client.post("/api/contacts", json=future, headers=headers)
    ).status_code == 422

    assert (await client.patch(endpoint, json={}, headers=headers)).status_code == 422
    assert (
        await client.patch(endpoint, json={"email": None}, headers=headers)
    ).status_code == 422
    cleared = await client.patch(
        endpoint,
        json={"additional_data": None},
        headers=headers,
    )
    assert cleared.json()["additional_data"] is None


async def test_upcoming_birthdays_are_filtered_and_ordered(
    client: AsyncClient,
) -> None:
    _, headers = await authenticated_user(client)
    today = date.today()
    soon = today + timedelta(days=2)
    later = today + timedelta(days=10)

    await create_contact(
        client,
        headers,
        first_name="Soon",
        email="soon@example.com",
        birthday=birthday_in_year(soon),
    )
    await create_contact(
        client,
        headers,
        first_name="Later",
        email="later@example.com",
        birthday=birthday_in_year(later),
    )

    response = await client.get("/api/contacts/upcoming-birthdays", headers=headers)
    assert [contact["first_name"] for contact in response.json()] == ["Soon"]


async def test_next_birthday_handles_year_boundary_and_leap_day() -> None:
    assert next_birthday(date(2000, 1, 2), date(2026, 12, 29)) == date(2027, 1, 2)
    assert next_birthday(date(2000, 2, 29), date(2025, 2, 20)) == date(2025, 2, 28)
