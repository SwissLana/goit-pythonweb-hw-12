"""Unit tests for SMTP and Cloudinary adapters without network access."""

import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import cloudinary as cloudinary_service
from app.services import email as email_service

pytestmark = pytest.mark.anyio


async def test_cloudinary_requires_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(
        update={
            "cloudinary_cloud_name": None,
            "cloudinary_api_key": None,
            "cloudinary_api_secret": None,
        }
    )
    monkeypatch.setattr(cloudinary_service, "get_settings", lambda: settings)

    with pytest.raises(cloudinary_service.CloudinaryNotConfiguredError):
        await cloudinary_service.upload_avatar(b"image", 1)


async def test_cloudinary_returns_secure_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(
        update={
            "cloudinary_cloud_name": "demo",
            "cloudinary_api_key": "key",
            "cloudinary_api_secret": SecretStr("secret"),
        }
    )
    captured: dict[str, object] = {}

    def fake_config(**kwargs: object) -> None:
        captured["config"] = kwargs

    def fake_upload(image: bytes, **kwargs: object) -> dict[str, str]:
        captured["image"] = image
        captured["upload"] = kwargs
        return {"secure_url": "https://res.cloudinary.com/demo/avatar.png"}

    monkeypatch.setattr(cloudinary_service, "get_settings", lambda: settings)
    monkeypatch.setattr(cloudinary_service.cloudinary, "config", fake_config)
    monkeypatch.setattr(cloudinary_service.cloudinary.uploader, "upload", fake_upload)

    result = await cloudinary_service.upload_avatar(b"real-image", 7)
    assert result.startswith("https://")
    assert captured["image"] == b"real-image"


async def test_cloudinary_rejects_response_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(
        update={
            "cloudinary_cloud_name": "demo",
            "cloudinary_api_key": "key",
            "cloudinary_api_secret": SecretStr("secret"),
        }
    )
    monkeypatch.setattr(cloudinary_service, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cloudinary_service.cloudinary.uploader,
        "upload",
        lambda *_args, **_kwargs: {},
    )

    with pytest.raises(RuntimeError, match="secure URL"):
        await cloudinary_service.upload_avatar(b"image", 1)


async def test_smtp_backends_build_verification_and_reset_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(update={"email_backend": "smtp"})
    messages: list[tuple[str, str, str]] = []

    def capture(recipient: str, subject: str, body: str) -> None:
        messages.append((recipient, subject, body))

    monkeypatch.setattr(email_service, "get_settings", lambda: settings)
    monkeypatch.setattr(email_service, "_send_smtp_message", capture)

    await email_service.send_verification_email("ada@example.com", "verify-token")
    await email_service.send_password_reset_email("ada@example.com", "reset-token")

    assert len(messages) == 2
    assert "verify-token" in messages[0][2]
    assert "reset-token" in messages[1][2]
