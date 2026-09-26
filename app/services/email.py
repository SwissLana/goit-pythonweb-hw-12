"""Email-verification delivery through console or SMTP backends."""

import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from anyio import to_thread

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _send_smtp_message(recipient: str, subject: str, body: str) -> None:
    """Send one plain-text message with authenticated SMTP."""

    settings = get_settings()
    if settings.smtp_host is None or settings.smtp_username is None:
        raise RuntimeError("SMTP is not fully configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(body)

    password = (
        settings.smtp_password.get_secret_value()
        if settings.smtp_password is not None
        else ""
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        if settings.smtp_use_tls:
            server.starttls()
        server.login(settings.smtp_username, password)
        server.send_message(message)


async def send_verification_email(recipient: str, token: str) -> None:
    """Deliver an expiring email-verification link without blocking the loop."""

    settings = get_settings()
    base_url = settings.api_base_url.rstrip("/")
    verification_url = f"{base_url}/api/auth/verify-email/{token}"

    if settings.email_backend == "console":
        logger.warning(
            "Development email verification link for %s: %s",
            recipient,
            verification_url,
        )
        return

    body = (
        "Welcome to the Contact Management API.\n\n"
        f"Verify your email address: {verification_url}\n\n"
        "If you did not create this account, you can ignore this message."
    )
    try:
        await to_thread.run_sync(
            _send_smtp_message,
            recipient,
            "Verify your contact API account",
            body,
        )
    except Exception:
        logger.exception("Could not send verification email to %s", recipient)


async def send_password_reset_email(recipient: str, token: str) -> None:
    """Deliver a password-reset link without blocking the event loop."""

    settings = get_settings()
    reset_url = f"{settings.frontend_reset_url}?token={quote(token)}"
    if settings.email_backend == "console":
        logger.warning(
            "Development password-reset link for %s: %s",
            recipient,
            reset_url,
        )
        return

    body = (
        "A password reset was requested for your Contact Management API account.\n\n"
        f"Reset your password: {reset_url}\n\n"
        "This link expires soon and can be used only once. If you did not request "
        "a reset, you can ignore this message."
    )
    try:
        await to_thread.run_sync(
            _send_smtp_message,
            recipient,
            "Reset your contact API password",
            body,
        )
    except Exception:
        logger.exception("Could not send password-reset email to %s", recipient)
