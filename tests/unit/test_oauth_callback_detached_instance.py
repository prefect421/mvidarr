"""Regression test for a live incident (2026-08-12): OAuth login via
Authentik got all the way through the browser-side authorization and the
server-side token exchange successfully, then failed with:

    Error handling OAuth callback: Instance <User at 0x...> is not bound
    to a Session; attribute refresh operation cannot proceed

Root cause: DatabaseManager.get_session()'s context manager calls
session.commit() on normal exit, and SQLAlchemy's default
expire_on_commit=True marks every attribute already loaded on any object
touched in that session as stale, to be refreshed from the database on
next access. _find_or_create_oauth_user calls session.commit() itself
(to persist the new UserSession), then returns the User object — and the
instant its own `with get_db() as session:` block exits right after,
that session closes for good. The very next attribute access anywhere
downstream (handle_oauth_callback's own log line: `user.username`) tries
to trigger a refresh against a session that no longer exists.

Same root cause the codebase has already fixed elsewhere under the same
name (e.g. commit 41132210, "Fix SQLAlchemy DetachedInstanceError in
IMVDb search") — capture needed attributes before the session goes away.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import User, UserRole, UserSession
from src.services.oauth_service import OAuthService


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, UserSession.__table__])
    return sessionmaker(bind=engine)


@contextmanager
def _real_get_db(session_factory):
    """Mirrors DatabaseManager.get_session()'s real commit-then-close
    behavior exactly — a plain in-memory fake that just yields a fresh
    session and closes it would NOT reproduce this bug, since the bug is
    specifically that commit() expires attributes before close()."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _patch_get_db(session_factory):
    return patch(
        "src.services.oauth_service.get_db",
        lambda: _real_get_db(session_factory),
    )


class TestOAuthCallbackSurvivesSessionClose:
    def test_new_user_attributes_are_readable_after_the_session_closes(
        self, session_factory
    ):
        service = OAuthService.__new__(OAuthService)

        # OAuth-created users get a random, unused password
        # (secrets.token_urlsafe(32)) — pinned here to a value that
        # reliably passes PasswordValidator so this test isn't flaky on
        # the rare draw that fails complexity/sequential-character
        # checks (a separate, real gap noted but out of scope here).
        with _patch_get_db(session_factory), patch(
            "src.services.oauth_service.secrets.token_urlsafe",
            return_value="Xk9#mQ7z!vR2wL",
        ):
            user, user_session = service._find_or_create_oauth_user(
                "google",
                {"email": "newperson@example.test", "id": "provider-id-1"},
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        # The session _find_or_create_oauth_user used is now closed.
        # Reading these must not raise DetachedInstanceError-style
        # errors — this is exactly what handle_oauth_callback's log
        # line and auth.py's response-building code do next.
        assert user.username == "newperson"
        assert user.email == "newperson@example.test"
        assert user.role == UserRole.USER
        assert isinstance(user.id, int)

    def test_existing_user_attributes_are_readable_after_the_session_closes(
        self, session_factory
    ):
        session = session_factory()
        existing = User(
            username="alreadyhere",
            email="alreadyhere@example.test",
            password="Sup3rSecret!",
            role=UserRole.USER,
        )
        session.add(existing)
        session.commit()
        session.close()

        service = OAuthService.__new__(OAuthService)

        with _patch_get_db(session_factory):
            user, user_session = service._find_or_create_oauth_user(
                "google",
                {"email": "alreadyhere@example.test", "id": "provider-id-2"},
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user.username == "alreadyhere"
        assert user.email == "alreadyhere@example.test"
        assert user.role == UserRole.USER
