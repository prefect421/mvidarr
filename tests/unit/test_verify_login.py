"""Tests for the real POST /2fa/api/verify-login implementation.

Before this fix, this endpoint unconditionally returned 501 — 2FA was
fully built (TwoFactorService.verify_two_factor_login already existed
and is used by the setup-verification flow) but never reachable from an
actual login (#311/#312 investigation).

Updated 2026-08-10 (security revision): the endpoint now requires a
short-lived, single-use ticket from TwoFactorService.create_pending_ticket
instead of a bare username — see tests/unit/test_two_factor_pending_ticket.py
and the "Task 9 revision" section of the plan for why a bare username let
anyone with a guessed/stolen TOTP code log in without a password at all.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.two_factor_auth import router
from src.database.connection import Base, get_db_session
from src.database.models import User, UserRole
from src.services.two_factor_service import TwoFactorService, _pending_2fa_tickets


def setup_function():
    _pending_2fa_tickets.clear()


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: get_db_session is a sync
    # generator dependency, so FastAPI runs it via anyio's threadpool while
    # the async route handler runs on the event-loop thread. A plain
    # in-memory sqlite engine binds its single connection to whichever
    # thread created it (SingletonThreadPool) and raises "SQLite objects
    # created in a thread can only be used in that same thread" the moment
    # the route touches the session. StaticPool shares one connection
    # across threads instead, which is safe here since each test uses a
    # single-threaded TestClient request at a time. (Same pattern as
    # tests/unit/test_users_api.py.)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


def _seed_user(session_factory, username, two_factor_enabled=True):
    session = session_factory()
    user = User(
        username=username,
        email=f"{username}@test.local",
        password="Sup3rSecret!",
        role=UserRole.USER,
    )
    user.two_factor_enabled = two_factor_enabled
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id


def _make_client(session_factory):
    app = FastAPI()
    app.include_router(router)

    def _override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = _override_db
    return TestClient(app)


class TestVerifyLogin:
    def test_valid_token_creates_session(self, session_factory):
        user_id = _seed_user(session_factory, "twofa_user")
        ticket = TwoFactorService.create_pending_ticket(user_id)
        client = _make_client(session_factory)

        with patch(
            "src.services.two_factor_service.TwoFactorService.verify_two_factor_login",
            return_value=(True, "Verified"),
        ):
            response = client.post(
                "/2fa/api/verify-login",
                json={"ticket": ticket, "token": "123456"},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert "session_token" in response.cookies

    def test_invalid_token_returns_401(self, session_factory):
        user_id = _seed_user(session_factory, "twofa_user")
        ticket = TwoFactorService.create_pending_ticket(user_id)
        client = _make_client(session_factory)

        with patch(
            "src.services.two_factor_service.TwoFactorService.verify_two_factor_login",
            return_value=(False, "Invalid code"),
        ):
            response = client.post(
                "/2fa/api/verify-login",
                json={"ticket": ticket, "token": "000000"},
            )

        assert response.status_code == 401

    def test_unknown_ticket_returns_401(self, session_factory):
        client = _make_client(session_factory)
        response = client.post(
            "/2fa/api/verify-login",
            json={"ticket": "never-issued", "token": "123456"},
        )
        assert response.status_code == 401

    def test_ticket_is_burned_after_a_failed_attempt(self, session_factory):
        """The whole point of this revision: a ticket must be consumed on
        every attempt, right or wrong, so a bad code guess can't just be
        retried against the same ticket. If a future refactor moves ticket
        consumption to only happen on success, this test must fail."""
        user_id = _seed_user(session_factory, "twofa_user")
        ticket = TwoFactorService.create_pending_ticket(user_id)
        client = _make_client(session_factory)

        with patch(
            "src.services.two_factor_service.TwoFactorService.verify_two_factor_login",
            return_value=(False, "Invalid code"),
        ):
            first = client.post(
                "/2fa/api/verify-login",
                json={"ticket": ticket, "token": "000000"},
            )

        assert first.status_code == 401

        # Re-POST the same ticket, this time with a token that would
        # succeed if the ticket were still valid.
        with patch(
            "src.services.two_factor_service.TwoFactorService.verify_two_factor_login",
            return_value=(True, "Verified"),
        ):
            second = client.post(
                "/2fa/api/verify-login",
                json={"ticket": ticket, "token": "123456"},
            )

        assert second.status_code == 401

    def test_eight_character_token_reaches_verify_two_factor_login(
        self, session_factory
    ):
        """Backup codes are 8 characters (see TwoFactorService.generate_backup_codes
        and the "Check if token is a backup code" branch in
        verify_two_factor_login). LoginVerificationRequest.token must accept
        them, not just 6-digit TOTP codes, or a self-hoster who loses their
        authenticator has no recovery path through this endpoint."""
        user_id = _seed_user(session_factory, "twofa_user")
        ticket = TwoFactorService.create_pending_ticket(user_id)
        client = _make_client(session_factory)

        with patch(
            "src.services.two_factor_service.TwoFactorService.verify_two_factor_login",
            return_value=(True, "Backup code accepted"),
        ) as mock_verify:
            response = client.post(
                "/2fa/api/verify-login",
                json={"ticket": ticket, "token": "ABCD1234"},
            )

        assert response.status_code == 200
        mock_verify.assert_called_once_with(user_id, "ABCD1234")
