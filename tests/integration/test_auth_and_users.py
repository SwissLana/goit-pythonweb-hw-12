"""Integration tests for authentication, profiles, roles, and recovery."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security as security_module
from app.core.security import create_access_token, create_email_verification_token
from app.models.user import UserRole
from app.repositories import users as user_repository
from app.routers import auth as auth_router
from app.services import cloudinary as cloudinary_service
from tests.helpers import (
    DEFAULT_PASSWORD,
    authenticated_user,
    login_tokens,
    login_user,
    register_user,
    verify_user,
)

pytestmark = pytest.mark.anyio


async def test_health_and_security_documentation_are_available(
    client: AsyncClient,
) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    openapi = (await client.get("/openapi.json")).json()
    assert openapi["info"]["title"] == "Secure Contact Management API"
    assert "OAuth2PasswordBearer" in openapi["components"]["securitySchemes"]


async def test_registration_hashes_password_and_rejects_duplicates(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_data = await register_user(client)
    assert user_data["email"] == "ada@example.com"
    assert user_data["is_verified"] is False
    assert "password" not in user_data
    assert "hashed_password" not in user_data

    stored = await user_repository.get_user(db_session, user_data["id"])
    assert stored is not None
    assert stored.hashed_password != DEFAULT_PASSWORD
    assert stored.hashed_password.startswith("$argon2")

    duplicate_email = await client.post(
        "/api/auth/register",
        json={
            "username": "different",
            "email": "ADA@EXAMPLE.COM",
            "password": DEFAULT_PASSWORD,
        },
    )
    assert duplicate_email.status_code == 409


async def test_verification_and_login_flow(client: AsyncClient) -> None:
    user = await register_user(client)

    unverified = await client.post(
        "/api/auth/login",
        data={"username": user["email"], "password": DEFAULT_PASSWORD},
    )
    assert unverified.status_code == 403

    wrong_password = await client.post(
        "/api/auth/login",
        data={"username": user["email"], "password": "WrongPassword123"},
    )
    assert wrong_password.status_code == 401

    await verify_user(client, user["id"])
    access_token = await login_user(client, identifier="ada")
    me = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me.status_code == 200
    assert me.json()["is_verified"] is True


async def test_invalid_and_wrong_purpose_tokens_are_rejected(
    client: AsyncClient,
) -> None:
    assert (
        await client.get("/api/auth/verify-email/not-a-valid-token-value")
    ).status_code == 400

    user = await register_user(client)
    access_token = create_access_token(user["id"])
    wrong_purpose = await client.get(f"/api/auth/verify-email/{access_token}")
    assert wrong_purpose.status_code == 400

    verification_token = create_email_verification_token(user["id"])
    protected = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {verification_token}"},
    )
    assert protected.status_code == 401


async def test_resend_verification_does_not_disclose_accounts(
    client: AsyncClient,
) -> None:
    await register_user(client)
    existing = await client.post(
        "/api/auth/resend-verification",
        json={"email": "ada@example.com"},
    )
    missing = await client.post(
        "/api/auth/resend-verification",
        json={"email": "missing@example.com"},
    )
    assert existing.status_code == missing.status_code == 202
    assert existing.json() == missing.json()


async def test_me_route_is_rate_limited_per_user(client: AsyncClient) -> None:
    _, headers = await authenticated_user(client)
    for _ in range(5):
        assert (await client.get("/api/users/me", headers=headers)).status_code == 200

    limited = await client.get("/api/users/me", headers=headers)
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


async def test_cors_preflight_allows_configured_frontend(client: AsyncClient) -> None:
    response = await client.options(
        "/api/contacts",
        headers={
            "Origin": "http://test-frontend",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://test-frontend"


async def test_avatar_upload_updates_only_current_user(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    memory_user_cache,
) -> None:
    user_data, headers = await authenticated_user(client)

    async def fake_upload_avatar(image: bytes, user_id: int) -> str:
        assert image == b"fake-png"
        assert user_id > 0
        return "https://res.cloudinary.com/demo/image/upload/avatar.png"

    monkeypatch.setattr(cloudinary_service, "upload_avatar", fake_upload_avatar)
    denied = await client.patch(
        "/api/users/me/avatar",
        headers=headers,
        files={"avatar": ("avatar.png", b"fake-png", "image/png")},
    )
    assert denied.status_code == 403

    user = await user_repository.get_user(db_session, user_data["id"])
    assert user is not None
    await user_repository.update_role(db_session, user, UserRole.ADMIN)
    await memory_user_cache.delete(user.id)

    # Log in again and use an uncached identity carrying the new role.
    access_token = await login_user(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.patch(
        "/api/users/me/avatar",
        headers=headers,
        files={"avatar": ("avatar.png", b"fake-png", "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"].startswith("https://res.cloudinary.com/")

    invalid = await client.patch(
        "/api/users/me/avatar",
        headers=headers,
        files={"avatar": ("avatar.txt", b"not-image", "text/plain")},
    )
    assert invalid.status_code == 415


async def test_refresh_tokens_rotate_and_logout_revokes_them(
    client: AsyncClient,
) -> None:
    user = await register_user(client)
    await verify_user(client, user["id"])
    first = await login_tokens(client)

    rotated = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["access_token"] != first["access_token"]
    assert second["refresh_token"] != first["refresh_token"]

    replay = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert replay.status_code == 401

    logout = await client.post(
        "/api/auth/logout",
        json={"refresh_token": second["refresh_token"]},
    )
    assert logout.status_code == 204
    assert (
        await client.post(
            "/api/auth/refresh",
            json={"refresh_token": second["refresh_token"]},
        )
    ).status_code == 401


async def test_password_reset_is_single_use_and_revokes_sessions(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await register_user(client)
    await verify_user(client, user["id"])
    tokens = await login_tokens(client)
    captured: dict[str, str] = {}

    async def capture_reset_token(recipient: str, token: str) -> None:
        captured["recipient"] = recipient
        captured["token"] = token

    monkeypatch.setattr(auth_router, "send_password_reset_email", capture_reset_token)
    requested = await client.post(
        "/api/auth/password-reset/request",
        json={"email": user["email"]},
    )
    assert requested.status_code == 202
    assert captured["recipient"] == user["email"]

    replacement_password = "NewSecurePassword456"
    confirmed = await client.post(
        "/api/auth/password-reset/confirm",
        json={
            "token": captured["token"],
            "new_password": replacement_password,
        },
    )
    assert confirmed.status_code == 200

    old_access = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get("/api/users/me", headers=old_access)).status_code == 401
    assert (
        await client.post(
            "/api/auth/login",
            data={"username": user["email"], "password": DEFAULT_PASSWORD},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/auth/login",
            data={"username": user["email"], "password": replacement_password},
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/auth/password-reset/confirm",
            json={
                "token": captured["token"],
                "new_password": "AnotherPassword789",
            },
        )
    ).status_code == 400


async def test_password_reset_request_does_not_disclose_accounts(
    client: AsyncClient,
) -> None:
    existing = await client.post(
        "/api/auth/password-reset/request",
        json={"email": "missing@example.com"},
    )
    missing = await client.post(
        "/api/auth/password-reset/request",
        json={"email": "another-missing@example.com"},
    )
    assert existing.status_code == missing.status_code == 202
    assert existing.json() == missing.json()


async def test_current_user_is_read_from_cache_after_first_request(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await authenticated_user(client)
    original = user_repository.get_user
    calls = 0

    async def counted_get_user(db: AsyncSession, user_id: int):
        nonlocal calls
        calls += 1
        return await original(db, user_id)

    monkeypatch.setattr(security_module.user_repository, "get_user", counted_get_user)
    assert (await client.get("/api/users/me", headers=headers)).status_code == 200
    assert (await client.get("/api/users/me", headers=headers)).status_code == 200
    assert calls == 1


async def test_only_admin_can_manage_roles(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin_data, admin_headers = await authenticated_user(client)
    admin = await user_repository.get_user(db_session, admin_data["id"])
    assert admin is not None
    await user_repository.update_role(db_session, admin, UserRole.ADMIN)

    target = await register_user(
        client,
        username="grace",
        email="grace@example.com",
    )
    promoted = await client.patch(
        f"/api/users/{target['id']}/role",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    await verify_user(client, target["id"])
    target_token = await login_user(client, identifier="grace@example.com")
    target_headers = {"Authorization": f"Bearer {target_token}"}
    demoted = await client.patch(
        f"/api/users/{target['id']}/role",
        json={"role": "user"},
        headers=target_headers,
    )
    assert demoted.status_code == 200

    forbidden = await client.patch(
        f"/api/users/{admin_data['id']}/role",
        json={"role": "user"},
        headers=target_headers,
    )
    assert forbidden.status_code == 403
