"""Tests confirming password-only login no longer issues a session when
the user has 2FA enabled (#311) — previously neither login endpoint ever
checked this, so 2FA provided no actual protection. Also confirms the
2FA-required response carries a pending ticket (not the raw username) —
see the 2026-08-10 security revision to Task 9 for why: verify-login
must be bound to a prior password check, not just told who to check.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.auth import router
from src.database.connection import Base, get_db_session
from src.database.models import User, UserRole


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
    # tests/unit/test_verify_login.py.)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


def _seed_user(session_factory, username, password, two_factor_enabled):
    session = session_factory()
    user = User(
        username=username,
        email=f"{username}@test.local",
        password=password,
        role=UserRole.USER,
    )
    user.two_factor_enabled = two_factor_enabled
    session.add(user)
    session.commit()
    session.close()


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


class TestSimpleLoginTwoFactorGate:
    def test_password_only_success_without_2fa_creates_session(self, session_factory):
        _seed_user(session_factory, "no2fa", "Sup3rSecret!", two_factor_enabled=False)
        client = _make_client(session_factory)

        with patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(True, "OK"),
        ):
            response = client.post(
                "/api/auth/simple-login",
                json={"username": "no2fa", "password": "Sup3rSecret!"},
            )

        assert response.status_code == 200
        assert "session_token" in response.cookies

    def test_password_success_with_2fa_returns_a_ticket_not_a_session(
        self, session_factory
    ):
        _seed_user(session_factory, "has2fa", "Sup3rSecret!", two_factor_enabled=True)
        client = _make_client(session_factory)

        with patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(True, "OK"),
        ):
            response = client.post(
                "/api/auth/simple-login",
                json={"username": "has2fa", "password": "Sup3rSecret!"},
            )

        assert response.status_code == 202
        assert response.json()["requires_2fa"] is True
        assert isinstance(response.json()["ticket"], str)
        assert len(response.json()["ticket"]) > 20  # a real token, not a placeholder
        assert "session_token" not in response.cookies

    def test_ticket_actually_resolves_to_the_correct_user(self, session_factory):
        """The whole point of the ticket — confirm it round-trips through
        TwoFactorService to the right user_id, not just that a string is present."""
        _seed_user(session_factory, "has2fa", "Sup3rSecret!", two_factor_enabled=True)
        session = session_factory()
        user_id = session.query(User).filter(User.username == "has2fa").first().id
        session.close()

        client = _make_client(session_factory)
        with patch(
            "src.services.simple_auth_service.SimpleAuthService.authenticate",
            return_value=(True, "OK"),
        ):
            response = client.post(
                "/api/auth/simple-login",
                json={"username": "has2fa", "password": "Sup3rSecret!"},
            )

        from src.services.two_factor_service import TwoFactorService

        ticket = response.json()["ticket"]
        assert TwoFactorService.consume_pending_ticket(ticket) == user_id
