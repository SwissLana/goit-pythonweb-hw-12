"""SQLAlchemy models exposed for application and migration discovery."""

from app.models.contact import Contact
from app.models.user import User, UserRole

__all__ = ["Contact", "User", "UserRole"]
