"""Tests for users.py's role-gating now checking real UserRole values,
and confirming the broken role-update endpoint is gone.

Before this fix: current_user.get("role") != "admin" always failed (or
always trivially matched by luck) because the session's role field was
hardcoded — see #310. The role-update endpoint also wrote to a
non-existent `is_admin` column that silently never persisted — see #310.
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
from src.api.fastapi.users import router
from src.database.connection import Base, get_db_session
from src.database.models import User, UserRole


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: users.py's get_db_session is a
    # sync generator dependency, so FastAPI runs it via anyio's threadpool
    # while the async route handler runs on the event-loop thread. A plain
    # in-memory sqlite engine binds its single connection to whichever
    # thread created it (SingletonThreadPool) and raises
    # "SQLite objects created in a thread can only be used in that same
    # thread" the moment the route touches the session. StaticPool shares
    # one connection across threads instead, which is safe here since each
    # test uses a single-threaded TestClient request at a time.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


def _seed_user(session_factory, username, role):
    session = session_factory()
    user = User(
        username=username,
        email=f"{username}@test.local",
        password="Sup3rSecret!",
        role=role,
    )
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id


def _make_client(session_factory, current_user):
    app = FastAPI()
    app.include_router(router)

    def _override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[require_authentication] = lambda: current_user
    return TestClient(app)


class TestRoleGating:
    def test_non_admin_cannot_list_users(self, session_factory):
        client = _make_client(session_factory, {"role": "USER", "user_id": 1})
        response = client.get("/api/users")
        assert response.status_code == 403

    def test_admin_can_list_users(self, session_factory):
        _seed_user(session_factory, "someone", UserRole.USER)
        client = _make_client(session_factory, {"role": "ADMIN", "user_id": 1})
        response = client.get("/api/users")
        assert response.status_code == 200


class TestRoleUpdateEndpointRemoved:
    def test_role_update_route_no_longer_exists(self, session_factory):
        client = _make_client(session_factory, {"role": "ADMIN", "user_id": 1})
        response = client.put("/api/users/1/role", json={"role": "admin"})
        assert response.status_code == 404
