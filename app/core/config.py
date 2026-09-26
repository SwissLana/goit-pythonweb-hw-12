"""Validated application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration supplied through the environment or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(min_length=1)
    app_name: str = "Secure Contact Management API"
    app_version: str = "4.0.0"

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "secure-contact-api"
    jwt_audience: str = "secure-contact-api-users"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)
    email_verification_expire_hours: int = Field(default=24, ge=1, le=168)
    password_reset_expire_minutes: int = Field(default=30, ge=5, le=1440)

    redis_url: str = "redis://localhost:6379/0"
    user_cache_ttl_seconds: int = Field(default=900, ge=30, le=3600)

    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str = "noreply@example.com"
    smtp_use_tls: bool = True
    api_base_url: str = "http://localhost:8000"
    frontend_reset_url: str = "http://localhost:3000/reset-password"

    cors_origins: list[str] = ["http://localhost:3000"]

    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: SecretStr | None = None
    cloudinary_folder: str = "contact-api/avatars"
    max_avatar_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)

    me_rate_limit_requests: int = Field(default=5, ge=1)
    me_rate_limit_window_seconds: int = Field(default=60, ge=1)

    @field_validator("database_url", mode="before")
    @classmethod
    def select_async_postgres_driver(cls, value: object) -> object:
        """Adapt provider PostgreSQL URLs to SQLAlchemy's async Psycopg dialect."""

        if isinstance(value, str):
            if value.startswith("postgres://"):
                return value.replace("postgres://", "postgresql+psycopg://", 1)
            if value.startswith("postgresql://"):
                return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator(
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "cloudinary_cloud_name",
        "cloudinary_api_key",
        "cloudinary_api_secret",
        mode="before",
    )
    @classmethod
    def empty_strings_are_none(cls, value: object) -> object:
        """Treat empty optional environment variables as unconfigured."""

        return None if value == "" else value

    @model_validator(mode="after")
    def validate_service_settings(self) -> "Settings":
        """Require complete SMTP settings when the SMTP backend is selected."""

        if "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS cannot contain '*' when credentialed requests are enabled"
            )
        if self.email_backend == "smtp":
            required = (self.smtp_host, self.smtp_username, self.smtp_password)
            if any(value is None for value in required):
                raise ValueError(
                    "SMTP_HOST, SMTP_USERNAME, and SMTP_PASSWORD are required "
                    "when EMAIL_BACKEND=smtp"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance for the application process."""

    return Settings()  # type: ignore[call-arg]
