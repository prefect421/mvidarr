"""Tests for the startup reconciliation that guarantees the configured
simple_auth_username has a matching ADMIN User row.

Without it, installs that never ran the installation wizard have only
Setting rows, so SessionStore.create_session finds no user, fails closed to
READONLY, and the site's only admin account 403s on every admin endpoint.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.init_db import ensure_admin_user_for_credentials
from src.database.models import User, UserRole


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
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
        "src.database.connection.get_db", lambda: _fake_get_db(session_factory)
    )


def _seed_user(session_factory, username, role, password="Sup3rSecret!"):
    session = session_factory()
    user = User(
        username=username,
        email=f"{username}@test.local",
        password=password,
        role=role,
    )
    session.add(user)
    session.commit()
    session.close()


class TestEnsureAdminUserForCredentials:
    def test_creates_admin_user_when_missing(self, session_factory):
        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is True

        session = session_factory()
        users = session.query(User).filter(User.username == "admin").all()
        assert len(users) == 1
        assert users[0].role == UserRole.ADMIN
        assert users[0].email == "admin@localhost"
        # Password hash is a real hash of an unusable random secret, never blank.
        assert users[0].password_hash

    def test_leaves_existing_admin_untouched(self, session_factory):
        _seed_user(session_factory, "admin", UserRole.ADMIN)
        session = session_factory()
        original = session.query(User).filter(User.username == "admin").first()
        original_hash = original.password_hash
        original_email = original.email
        original_id = original.id
        session.close()

        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is True

        session2 = session_factory()
        users = session2.query(User).filter(User.username == "admin").all()
        assert len(users) == 1, "must not duplicate the existing row"
        assert users[0].id == original_id
        assert users[0].password_hash == original_hash, "must not overwrite password"
        assert users[0].email == original_email
        assert users[0].role == UserRole.ADMIN

    def test_does_not_overwrite_a_deliberately_downgraded_account(
        self, session_factory
    ):
        _seed_user(session_factory, "admin", UserRole.READONLY)

        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is True

        session = session_factory()
        user = session.query(User).filter(User.username == "admin").first()
        assert user.role == UserRole.READONLY

    def test_is_idempotent_across_repeated_boots(self, session_factory):
        with _patch_get_db(session_factory):
            ensure_admin_user_for_credentials("admin")
            ensure_admin_user_for_credentials("admin")
            ensure_admin_user_for_credentials("admin")

        session = session_factory()
        assert session.query(User).filter(User.username == "admin").count() == 1

    def test_returns_false_without_a_configured_username(self, session_factory):
        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("") is False
            assert ensure_admin_user_for_credentials(None) is False
