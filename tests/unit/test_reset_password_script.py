"""Tests for the password-reset CLI script's core logic, factored out of
the script itself so it's testable without shelling out.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.reset_password import reset_user_password
from src.database.connection import Base
from src.database.models import User, UserRole
from src.services.settings_service import SettingsService
from src.services.simple_auth_service import SimpleAuthService


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


def _seed_user(session_factory, username):
    session = session_factory()
    user = User(
        username=username,
        email=f"{username}@test.local",
        password="SecureK9m!Zx7P",
        role=UserRole.USER,
    )
    session.add(user)
    session.commit()
    session.close()


class TestResetUserPassword:
    def test_resets_password_for_existing_user(self, session_factory):
        _seed_user(session_factory, "someone")
        session = session_factory()

        success, message = reset_user_password(session, "someone", "NewK7j!Qw9Vb2")

        assert success is True
        user = session.query(User).filter(User.username == "someone").first()
        assert user.check_password("NewK7j!Qw9Vb2")
        assert not user.check_password("SecureK9m!Zx7P")

    def test_returns_false_for_unknown_username(self, session_factory):
        session = session_factory()
        success, message = reset_user_password(session, "nobody", "N3wPassw0rd!")
        assert success is False
        assert "not found" in message.lower()

    def test_rejects_weak_password(self, session_factory):
        _seed_user(session_factory, "someone")
        session = session_factory()

        success, message = reset_user_password(session, "someone", "weak")

        assert success is False


class TestSimpleAuthCredentialSync:
    """The login form authenticates via SimpleAuthService against the
    Settings table, not the users table. Resetting User.password_hash alone
    leaves the operator locked out, so the script must keep the two in sync.
    """

    @pytest.fixture
    def calls(self, monkeypatch):
        recorded = []

        def _fake_set_credentials(username, password):
            recorded.append((username, password))
            return True, "Credentials updated successfully"

        monkeypatch.setattr(
            SimpleAuthService, "set_credentials", staticmethod(_fake_set_credentials)
        )
        return recorded

    def _stub_configured_username(self, monkeypatch, value):
        monkeypatch.setattr(
            SettingsService,
            "get",
            staticmethod(
                lambda key, default=None: value if key == "simple_auth_username" else ""
            ),
        )

    def test_syncs_login_credential_when_username_matches(
        self, session_factory, monkeypatch, calls
    ):
        self._stub_configured_username(monkeypatch, "someone")
        _seed_user(session_factory, "someone")
        session = session_factory()

        success, message = reset_user_password(session, "someone", "NewK7j!Qw9Vb2")

        assert success is True
        assert calls == [("someone", "NewK7j!Qw9Vb2")]
        assert "synced" in message.lower()

    def test_warns_when_username_is_not_the_login_account(
        self, session_factory, monkeypatch, calls
    ):
        self._stub_configured_username(monkeypatch, "admin")
        _seed_user(session_factory, "someone")
        session = session_factory()

        success, message = reset_user_password(session, "someone", "NewK7j!Qw9Vb2")

        # The users-table update did succeed...
        assert success is True
        user = session.query(User).filter(User.username == "someone").first()
        assert user.check_password("NewK7j!Qw9Vb2")
        # ...but the operator must be told login access was NOT restored.
        assert calls == []
        assert "WARNING" in message
        assert "does NOT" in message
        assert "admin" in message

    def test_reports_failure_when_credential_sync_fails(
        self, session_factory, monkeypatch
    ):
        self._stub_configured_username(monkeypatch, "someone")
        monkeypatch.setattr(
            SimpleAuthService,
            "set_credentials",
            staticmethod(
                lambda u, p: (False, "Password must be at least 8 characters long")
            ),
        )
        _seed_user(session_factory, "someone")
        session = session_factory()

        success, message = reset_user_password(session, "someone", "NewK7j!Qw9Vb2")

        assert success is False
        assert "OLD password" in message
