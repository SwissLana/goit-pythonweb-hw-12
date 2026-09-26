"""Administrative command-line utilities for trusted operators."""

import argparse
import asyncio

from app.db.session import AsyncSessionFactory, engine
from app.models.user import UserRole
from app.repositories.users import get_user_by_email, update_role
from app.services.user_cache import close_user_cache, user_cache


def parse_arguments() -> argparse.Namespace:
    """Parse a safe, explicit administrative action."""

    parser = argparse.ArgumentParser(description="Contact API administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    promote = subparsers.add_parser(
        "promote-admin",
        help="grant administrator privileges to an existing user",
    )
    promote.add_argument("--email", required=True, help="registered user email")
    return parser.parse_args()


async def promote_admin(email: str) -> None:
    """Promote one existing account and invalidate its cached profile."""

    async with AsyncSessionFactory() as session:
        user = await get_user_by_email(session, email)
        if user is None:
            raise SystemExit(f"No registered user found for {email}")
        await update_role(session, user, UserRole.ADMIN)
        await user_cache.delete(user.id)
        print(f"Promoted {user.email} to admin")


async def run() -> None:
    """Dispatch the selected administrative command and close resources."""

    arguments = parse_arguments()
    try:
        if arguments.command == "promote-admin":
            await promote_admin(arguments.email)
    finally:
        await close_user_cache()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
