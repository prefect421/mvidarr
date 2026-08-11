"""Regression test for GET /2fa/api/status returning 500 for every caller.

Root cause: the endpoint called TwoFactorService.get_user_two_factor_status
(src/api/fastapi/two_factor_auth.py:306), a method that has never existed
on TwoFactorService — the real method is get_two_factor_status. This went
unnoticed because nothing in the frontend ever called this endpoint until
a Settings page fix wired it up (2026-08-11), immediately surfacing the
crash via the browser console.

Also fixed: even with the correct method name, the endpoint read a
"backup_codes_remaining" key that the real method never returns — it
returns "backup_codes_count" instead. Confirmed by reading
TwoFactorService.get_two_factor_status directly, not guessed.
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


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: get_db_session is a sync
    # generator dependency, dispatched to a worker thread by anyio while
    # the async route handler runs on the event-loop thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


def _seed_user(session_factory, two_factor_enabled=False, backup_codes=None):
    session = session_factory()
    user = User(
        username="someone",
        email="someone@test.local",
        password="Sup3rSecret!",
        role=UserRole.USER,
    )
    user.two_factor_enabled = two_factor_enabled
    if backup_codes is not None:
        import json

        user.backup_codes = json.dumps(backup_codes)
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id


@contextmanager
def _fake_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _patch_get_db(session_factory):
    # TwoFactorService.get_two_factor_status uses get_db() internally — a
    # completely separate access path from the FastAPI-injected
    # get_db_session dependency overridden below. two_factor_service.py
    # imports get_db via `from src.database.connection import get_db` at
    # module level, which binds its OWN name in that module's namespace —
    # patching src.database.connection.get_db does not affect it, since
    # that patch only rebinds the name where it was originally defined,
    # not everywhere it was already imported. Must patch it where it's
    # actually looked up: src.services.two_factor_service.get_db.
    return patch(
        "src.services.two_factor_service.get_db",
        lambda: _fake_get_db(session_factory),
    )


def _make_client(session_factory, user_id):
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
        "role": "USER",
        "authenticated": True,
    }
    return TestClient(app)


class TestTwoFactorStatusEndpoint:
    def test_returns_200_not_500_for_a_user_without_2fa(self, session_factory):
        user_id = _seed_user(session_factory, two_factor_enabled=False)
        client = _make_client(session_factory, user_id)

        with _patch_get_db(session_factory):
            response = client.get("/2fa/api/status")

        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_returns_correct_backup_codes_remaining_for_enabled_user(
        self, session_factory
    ):
        user_id = _seed_user(
            session_factory,
            two_factor_enabled=True,
            backup_codes=["code1", "code2", "code3"],
        )
        client = _make_client(session_factory, user_id)

        with _patch_get_db(session_factory):
            response = client.get("/2fa/api/status")

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        # Regression pin: the endpoint used to read "backup_codes_remaining"
        # from the service's response dict, which only ever has
        # "backup_codes_count" — silently always defaulting to 0.
        assert body["backup_codes_remaining"] == 3
