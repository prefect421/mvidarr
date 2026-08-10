"""End-to-end auth regression coverage for the v1.0.0 auth cluster fix
(#310, #311, #312, #313, #314, #319). Exercises the real login flow,
role enforcement, 2FA, and password reset together rather than mocking
adjacent pieces, unlike the per-task unit tests.
"""

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.reset_password import reset_user_password
from src.api.fastapi.auth import router as auth_router
from src.api.fastapi.two_factor_auth import router as two_factor_router
from src.api.fastapi.users import router as users_router
from src.database.connection import Base, get_db_session
from src.database.models import User, UserRole
from src.services.settings_service import SettingsService
from src.services.simple_auth_service import SimpleAuthService
from src.services.two_factor_service import TwoFactorService


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: FastAPI's TestClient dispatches
    # requests through a separate worker thread, and a bare
    # "sqlite:///:memory:" engine hands out a distinct (and therefore empty)
    # in-memory database per thread. This keeps every session on the same
    # underlying connection regardless of which thread opens it — the
    # standard pattern for testing FastAPI + SQLAlchemy with in-memory
    # SQLite (see FastAPI's own testing docs).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


def _make_client(session_factory):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(two_factor_router)
    app.include_router(users_router)

    def _override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = _override_db
    return TestClient(app)


def _seed_user(session_factory, username, password, role, two_factor_enabled=False):
    session = session_factory()
    user = User(
        username=username, email=f"{username}@test.local", password=password, role=role
    )
    user.two_factor_enabled = two_factor_enabled
    session.add(user)
    session.commit()
    session.close()


@contextmanager
def _fake_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _patch_get_db(session_factory):
    # SessionStore.create_session() looks up the user's real role via the
    # module-level src.database.connection.get_db() directly — it does not
    # go through FastAPI's dependency-injected get_db_session, so the
    # dependency_overrides wiring in _make_client doesn't reach it. Without
    # this patch the lookup misses the seeded user entirely and (correctly,
    # per #310's fail-closed design) falls back to READONLY regardless of
    # the user's actual role. Same pattern already established in
    # tests/unit/test_session_store.py for Task 1.
    from unittest.mock import patch

    return patch(
        "src.database.connection.get_db", lambda: _fake_get_db(session_factory)
    )


@contextmanager
def _settings_store(initial=None):
    """Back SettingsService with an in-memory dict.

    SimpleAuthService (the thing the login endpoints actually authenticate
    against) stores its single credential pair in the Settings table. The
    in-memory SQLite fixture only creates the users table, and
    SettingsService binds get_db at import time, so stubbing get/set is the
    cheapest way to exercise the REAL SimpleAuthService end to end.
    """
    from unittest.mock import patch

    store = dict(initial or {})

    def _get(key, default=None):
        value = store.get(key)
        if value is None:
            return "" if default is None else str(default)
        return value

    def _set(key, value, *args, **kwargs):
        store[key] = value
        return True

    with patch.object(SettingsService, "get", staticmethod(_get)), patch.object(
        SettingsService, "set", staticmethod(_set)
    ):
        yield store


class TestFullLoginFlow:
    def test_readonly_user_session_cannot_access_admin_only_endpoint(
        self, session_factory
    ):
        """Regression test for #310: role must actually be enforced, not hardcoded admin."""
        _seed_user(session_factory, "viewer", "Sup3rSecret!", UserRole.READONLY)
        client = _make_client(session_factory)

        from unittest.mock import patch

        with patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(True, "OK"),
        ), _patch_get_db(session_factory):
            login_response = client.post(
                "/api/auth/simple-login",
                json={"username": "viewer", "password": "Sup3rSecret!"},
            )
        assert login_response.status_code == 200

        client.cookies.set("session_token", login_response.cookies["session_token"])
        users_response = client.get("/api/users")
        assert users_response.status_code == 403

    def test_admin_user_session_can_access_admin_only_endpoint(self, session_factory):
        _seed_user(session_factory, "boss", "Sup3rSecret!", UserRole.ADMIN)
        client = _make_client(session_factory)

        from unittest.mock import patch

        with patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(True, "OK"),
        ), _patch_get_db(session_factory):
            login_response = client.post(
                "/api/auth/simple-login",
                json={"username": "boss", "password": "Sup3rSecret!"},
            )

        client.cookies.set("session_token", login_response.cookies["session_token"])
        users_response = client.get("/api/users")
        assert users_response.status_code == 200


class TestTwoFactorFlow:
    def test_login_with_2fa_requires_verification_step(self, session_factory):
        _seed_user(
            session_factory,
            "twofa_user",
            "Sup3rSecret!",
            UserRole.USER,
            two_factor_enabled=True,
        )
        client = _make_client(session_factory)

        from unittest.mock import patch

        with patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(True, "OK"),
        ), _patch_get_db(session_factory):
            login_response = client.post(
                "/api/auth/simple-login",
                json={"username": "twofa_user", "password": "Sup3rSecret!"},
            )
        assert login_response.status_code == 202
        assert "session_token" not in login_response.cookies
        ticket = login_response.json()["ticket"]

        with patch.object(
            TwoFactorService, "verify_two_factor_login", return_value=(True, "OK")
        ), _patch_get_db(session_factory):
            verify_response = client.post(
                "/2fa/api/verify-login",
                json={"ticket": ticket, "token": "123456"},
            )
        assert verify_response.status_code == 200
        assert "session_token" in verify_response.cookies


class TestPasswordReset:
    def test_reset_then_login_with_new_password(self, session_factory):
        """The reset must restore ACTUAL login access, not just rewrite
        users.password_hash. Checking user.check_password() alone is what let
        the credential-store mismatch ship unnoticed, so this drives the real
        /api/auth/simple-login endpoint with the real SimpleAuthService.
        """
        _seed_user(session_factory, "forgetful", "Sup3rSecretOld!", UserRole.USER)

        with _settings_store({"simple_auth_username": "forgetful"}):
            # Seed the credential the login form actually reads.
            SimpleAuthService.set_credentials("forgetful", "Sup3rSecretOld!")

            session = session_factory()
            success, _ = reset_user_password(session, "forgetful", "Sup3rSecretNew!")
            assert success is True

            session2 = session_factory()
            user = session2.query(User).filter(User.username == "forgetful").first()
            assert user.check_password("Sup3rSecretNew!")
            assert not user.check_password("Sup3rSecretOld!")

            client = _make_client(session_factory)
            with _patch_get_db(session_factory):
                login_response = client.post(
                    "/api/auth/simple-login",
                    json={"username": "forgetful", "password": "Sup3rSecretNew!"},
                )
            assert login_response.status_code == 200
            assert "session_token" in login_response.cookies

            with _patch_get_db(session_factory):
                stale_response = client.post(
                    "/api/auth/simple-login",
                    json={"username": "forgetful", "password": "Sup3rSecretOld!"},
                )
            assert stale_response.status_code == 401

    def test_reset_does_not_affect_other_users(self, session_factory):
        _seed_user(session_factory, "user_a", "Sup3rSecretA!", UserRole.USER)
        _seed_user(session_factory, "user_b", "Sup3rSecretB!", UserRole.USER)
        session = session_factory()
        reset_user_password(session, "user_a", "Sup3rSecretC!")

        session2 = session_factory()
        user_b = session2.query(User).filter(User.username == "user_b").first()
        assert user_b.check_password("Sup3rSecretB!")
