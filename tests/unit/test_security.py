"""Unit tests for password, JWT, and opaque-token primitives."""

import pytest

from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password_async,
    token_digest,
    verify_password_async,
)

pytestmark = pytest.mark.anyio


async def test_password_hashing_never_returns_plaintext() -> None:
    password = "A-Very-Secure-Password-123"
    hashed = await hash_password_async(password)

    assert hashed != password
    assert hashed.startswith("$argon2")
    assert await verify_password_async(password, hashed) is True
    assert await verify_password_async("incorrect", hashed) is False
    assert await verify_password_async(password, "not-a-valid-hash") is False


async def test_tokens_are_typed_and_include_authentication_version() -> None:
    access = create_access_token(42, auth_version=7)
    refresh = create_refresh_token(42, auth_version=7)

    claims = decode_token(access, "access")
    assert claims.user_id == 42
    assert claims.auth_version == 7
    assert claims.token_id
    with pytest.raises(ValueError, match="invalid or expired"):
        decode_token(refresh, "access")


async def test_password_reset_token_is_opaque_and_stored_as_digest() -> None:
    token, digest = create_password_reset_token()

    assert len(token) >= 64
    assert digest == token_digest(token)
    assert token not in digest
    assert len(digest) == 64
