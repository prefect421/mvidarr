#!/usr/bin/env python3
"""
Password reset script for MVidarr.

Resets a user's password directly against the database. No email
infrastructure required — matches the existing scripts/index_videos.py
pattern for admin CLI operations.

Usage:
    python scripts/reset_password.py <username> <new_password>
    python scripts/reset_password.py --list
"""

import argparse
import sys
from pathlib import Path
from typing import Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, init_db_standalone
from src.database.models import User
from src.services.settings_service import SettingsService
from src.services.simple_auth_service import SimpleAuthService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.reset_password_script")


def reset_user_password(session, username: str, new_password: str) -> Tuple[bool, str]:
    """
    Reset a user's password.

    Args:
        session: SQLAlchemy session
        username: Username of the account to reset
        new_password: New plaintext password (validated for strength before hashing)

    Returns:
        (success, message)
    """
    user = session.query(User).filter(User.username == username).first()
    if not user:
        return False, f"User '{username}' not found"

    try:
        user.set_password(new_password)
    except ValueError as e:
        return False, str(e)

    session.commit()

    # The users table is NOT what the login form authenticates against.
    # Both /api/auth/simple-login and /api/auth/login go through
    # SimpleAuthService.authenticate, which reads the single
    # simple_auth_username / simple_auth_password pair out of the Settings
    # table. Resetting User.password_hash alone therefore does not restore
    # the ability to log in — the Settings credential must be synced too.
    try:
        configured_username = SettingsService.get("simple_auth_username")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not read simple_auth_username: {e}")
        configured_username = None

    if configured_username and username == configured_username:
        synced, sync_message = SimpleAuthService.set_credentials(username, new_password)
        if not synced:
            return (
                False,
                f"Password updated in the users table, but the login "
                f"credential could not be synced: {sync_message}. "
                f"Login will still use the OLD password.",
            )
        return True, f"Password reset for '{username}' (login credential synced)"

    return (
        True,
        f"Password reset for '{username}' in the users table.\n"
        f"WARNING: '{username}' is NOT the account the login form uses. "
        f"MVidarr's login accepts exactly one username, currently "
        f"'{configured_username or '<none configured>'}'. This reset does NOT "
        f"restore login access for '{username}' — to change the password you "
        f"actually log in with, re-run this script against "
        f"'{configured_username or 'the configured login username'}'.",
    )


def list_usernames(session) -> list:
    """Return all usernames, for use with --list when a forgotten username is the issue."""
    return [u.username for u in session.query(User.username).all()]


def main():
    parser = argparse.ArgumentParser(description="Reset a user's MVidarr password")
    parser.add_argument("username", nargs="?", help="Username to reset")
    parser.add_argument("new_password", nargs="?", help="New password")
    parser.add_argument(
        "--list", action="store_true", help="List all usernames instead of resetting"
    )
    args = parser.parse_args()

    init_db_standalone()

    with get_db() as session:
        if args.list:
            usernames = list_usernames(session)
            print("Existing usernames:")
            for name in usernames:
                print(f"  - {name}")
            return

        if not args.username or not args.new_password:
            parser.error("username and new_password are required unless --list is used")

        success, message = reset_user_password(
            session, args.username, args.new_password
        )
        print(message)
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
