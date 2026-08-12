"""Regression tests for #334: disabling 2FA checked the wrong password
store, and (found while fixing it) the endpoint didn't even pass a
password through — it forwarded the request's optional `token` field to
TwoFactorService.disable_two_factor's `password` parameter instead.

Root cause: the live login system (SimpleAuthService) authenticates
against `simple_auth_username`/`simple_auth_password` in the Settings
table. `User.password_hash` is a separate, independently-writable column
that the Settings > Credentials panel never updates — it can silently
drift out of sync. TwoFactorService.disable_two_factor checked
User.password_hash via werkzeug's check_password_hash, so a user who'd
changed their real login password would have to supply their OLD
password to turn off 2FA — or, combined with the argument-swap bug below,
couldn't disable 2FA via this endpoint at all regardless of which
password they typed.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.two_factor_auth import router
from src.database.connection import Base, get_db_session
from src.database.models import User, UserRole
from src.services.two_factor_service import TwoFactorService


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: get_db_session is a sync
    # generator dependency, dispatched to a worker thread by anyio while
    # the async route handler runs on the event-loop thread — needed for
    # TestDisableEndpointForwardsThePasswordField's TestClient requests.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


@contextmanager
def _fake_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _patch_get_db(session_factory):
    return patch(
        "src.services.two_factor_service.get_db",
        lambda: _fake_get_db(session_factory),
    )


def _seed_user(session_factory, stale_password="OldSecret9!"):
    """Seed a user whose User.password_hash is a password the user no
    longer actually logs in with — simulating a credentials update that
    only touched SimpleAuthService's store, not this row (see #334's
    description of how the two stores drift apart)."""
    session = session_factory()
    user = User(
        username="someone",
        email="someone@test.local",
        password=stale_password,
        role=UserRole.USER,
    )
    user.two_factor_enabled = True
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id


class TestServiceChecksLiveCredentialStore:
    def test_current_real_password_disables_2fa(self, session_factory):
        user_id = _seed_user(session_factory)

        with _patch_get_db(session_factory), patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(True, "OK"),
        ) as mock_auth:
            success, message = TwoFactorService.disable_two_factor(
                user_id, "CurrentSecret9!"
            )

        assert success is True
        assert message == "Two-factor authentication disabled successfully"
        # Confirms the check went through the live store, not
        # check_password_hash(user.password_hash, ...).
        mock_auth.assert_called_once_with("someone", "CurrentSecret9!")

    def test_stale_user_password_hash_value_is_rejected(self, session_factory):
        """The user's OLD password (still sitting in User.password_hash)
        must NOT work — proving the check isn't silently falling back to
        that stale column."""
        user_id = _seed_user(session_factory, stale_password="OldSecret9!")

        with _patch_get_db(session_factory), patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(False, "Invalid username or password"),
        ):
            success, message = TwoFactorService.disable_two_factor(
                user_id, "OldSecret9!"
            )

        assert success is False
        assert message == "Incorrect password"


class TestDisableEndpointForwardsThePasswordField:
    """Regression for the argument-swap bug found while fixing #334:
    disable_two_factor(request) called
    TwoFactorService.disable_two_factor(user.id, disable_request.token) —
    the TOTP token field, not .password — so the service's password check
    was always being handed the wrong value (or None)."""

    def _make_client(self, session_factory, user_id):
        app = FastAPI()
        app.include_router(router)

        def _override_db():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db_session] = _override_db
        app.dependency_overrides[require_authentication] = lambda: {
            "user_id": user_id,
            "username": "someone",
            "role": "USER",
            "authenticated": True,
        }
        return TestClient(app)

    def test_disable_call_receives_the_password_not_the_token(self, session_factory):
        user_id = _seed_user(session_factory)
        client = self._make_client(session_factory, user_id)

        with patch(
            "src.api.fastapi.two_factor_auth.TwoFactorService.disable_two_factor",
            return_value=(True, "Two-factor authentication disabled successfully"),
        ) as mock_disable:
            response = client.post(
                "/2fa/api/disable",
                json={"password": "CurrentSecret9!", "token": "123456"},
            )

        assert response.status_code == 200
        # The regression: this used to be called with the token
        # ("123456") in the password slot.
        mock_disable.assert_called_once_with(user_id, "CurrentSecret9!")
