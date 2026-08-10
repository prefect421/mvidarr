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
