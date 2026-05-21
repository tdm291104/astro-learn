"""Promote (or demote) a user account to admin via email lookup.

There is intentionally no self-serve "make me admin" endpoint — the first
admin must be created out-of-band, then promotes others through the UI.

Usage::

    # Grant admin privileges to an existing account.
    python -m scripts.promote_admin user@example.com

    # Revoke admin privileges.
    python -m scripts.promote_admin user@example.com --revoke

The account must already exist (register through the normal flow first).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from core.db import AsyncSessionLocal
from repositories.user_repository import UserRepository


async def _run(email: str, *, revoke: bool) -> int:
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_email(email)
        if user is None:
            print(f"No account with email {email!r}.", file=sys.stderr)
            return 1
        if user.is_admin == (not revoke):
            verb = "is already" if not revoke else "is already not"
            print(f"{email} {verb} an admin — nothing to do.")
            return 0
        user.is_admin = not revoke
        await session.commit()
        verb = "revoked from" if revoke else "granted to"
        print(f"Admin {verb} {email}.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote or demote an admin.")
    parser.add_argument("email", help="Email of the existing user account.")
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Remove admin privileges instead of granting them.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.email, revoke=args.revoke)))


if __name__ == "__main__":
    main()
