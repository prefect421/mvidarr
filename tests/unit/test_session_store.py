"""Tests for SessionStore correctly storing and returning a user's real role.

Before this fix, every session was hardcoded to role="admin" regardless of
the authenticating user's actual UserRole in the database — see issue #310.
"""

from unittest.mock import patch
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import User, UserRole
from src.services.session_store import SessionStore, _memory_sessions


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


def patch_get_db(session_factory):
    return patch(
        "src.database.connection.get_db", lambda: _fake_get_db(session_factory)
    )


def _seed_user(session_factory, username, role):
    session = session_factory()
    user = User(username=username, email=f"{username}@test.local", password="Sup3rSecret!", role=role)
    session.add(user)
    session.commit()
    session.close()


@pytest.fixture(autouse=True)
def _clear_memory_sessions():
    _memory_sessions.clear()
    yield
    _memory_sessions.clear()


class TestCreateSessionRole:
    def test_stores_real_role_for_readonly_user(self, session_factory):
        _seed_user(session_factory, "viewer", UserRole.READONLY)

        with patch_get_db(session_factory):
            token = SessionStore.create_session("viewer", "127.0.0.1")
            data = SessionStore.validate_session(token)

        assert data["role"] == "READONLY"

    def test_stores_real_role_for_admin_user(self, session_factory):
        _seed_user(session_factory, "boss", UserRole.ADMIN)

        with patch_get_db(session_factory):
            token = SessionStore.create_session("boss", "127.0.0.1")
            data = SessionStore.validate_session(token)

        assert data["role"] == "ADMIN"

    def test_unknown_username_falls_back_to_lowest_privilege(self, session_factory):
        # No user seeded — simulates a lookup miss. Must fail closed, not open.
        with patch_get_db(session_factory):
            token = SessionStore.create_session("ghost", "127.0.0.1")
            data = SessionStore.validate_session(token)

        assert data["role"] == "READONLY"

    def test_db_lookup_error_falls_back_to_lowest_privilege(self, session_factory):
        with patch(
            "src.database.connection.get_db",
            side_effect=RuntimeError("db unavailable"),
        ):
            token = SessionStore.create_session("viewer", "127.0.0.1")
            data = SessionStore.validate_session(token)

        assert data["role"] == "READONLY"
