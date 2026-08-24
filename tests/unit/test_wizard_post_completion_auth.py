"""Fix for issue #405: wizard.py is only partially self-disabling after
setup completes. Only create_admin_user() checked WizardStatus.COMPLETED;
the other 5 endpoints named in the issue stayed callable by anyone,
indefinitely, post-setup:

  - POST /validate-directory
  - POST /test-api
  - POST /import/start
  - POST /upload-videos
  - POST /import/custom-directory/start

The issue's suggested fix ("extend the same WizardStatus.COMPLETED guard
... to the other five endpoints") turns out to be wrong for 3 of the 5:
grepping the frontend showed /import/start, /upload-videos, and
/import/custom-directory/start are ALSO called by settings.html's
"Settings > System" video import feature (startVideoImport(), the
upload-then-import flow) -- a normal, ongoing, POST-setup feature, not
just a wizard step. wizard.js (the actual wizard frontend) only calls
/status, /steps/{step}/complete, /create-admin, /validate-directory,
/test-api, /import/start, and /skip -- notably NOT /upload-videos or
/import/custom-directory/start.

Blindly gating all 5 behind "wizard not completed" would have 403'd
Settings > System's import feature on every real, post-setup deployment
(every wizard is COMPLETED by then). The actual fix:

  - validate_directory, test_api: wizard-only, no other caller -> gated
    with require_wizard_incomplete (403 once WizardStatus.COMPLETED,
    matching create_admin_user's existing precedent).
  - upload_videos, start_custom_directory_import: Settings-only, never
    called pre-setup -> gated with the standard require_authentication
    (same tier as every other authenticated API route in this app).
  - start_video_import (/import/start): genuinely dual-purpose (called
    by both wizard.js pre-setup and settings.html post-setup) -> gated
    with require_wizard_incomplete_or_authenticated, which passes
    through untouched while the wizard is incomplete (pre-setup, no
    session exists yet) and otherwise requires a real authenticated
    session (post-setup Settings caller).
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.api.fastapi.wizard import (
    require_wizard_incomplete,
    require_wizard_incomplete_or_authenticated,
    router,
)
from src.database.connection import Base, get_db_session
from src.database.models import WizardState, WizardStatus

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "wizard.py"
)

WIZARD_ONLY_ROUTES = {"validate_directory", "test_api"}
SETTINGS_ONLY_ROUTES = {"upload_videos", "start_custom_directory_import"}
DUAL_PURPOSE_ROUTES = {"start_video_import"}


def _function_source(function_name: str) -> str:
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError(f"Could not find function {function_name!r} in {SOURCE_PATH}")


class TestRouteWiring:
    def test_wizard_only_routes_use_require_wizard_incomplete(self):
        for function_name in WIZARD_ONLY_ROUTES:
            source = _function_source(function_name)
            assert "Depends(require_wizard_incomplete)" in source

    def test_settings_only_routes_use_require_authentication(self):
        for function_name in SETTINGS_ONLY_ROUTES:
            source = _function_source(function_name)
            assert "Depends(require_authentication)" in source

    def test_dual_purpose_route_uses_the_either_or_dependency(self):
        for function_name in DUAL_PURPOSE_ROUTES:
            source = _function_source(function_name)
            # Depends(...) is line-wrapped by black for this long name --
            # check the pieces are both present rather than exact spacing.
            assert "Depends(" in source
            assert "require_wizard_incomplete_or_authenticated" in source


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[WizardState.__table__])
    return sessionmaker(bind=engine)


def _seed_wizard(session_factory, status):
    session = session_factory()
    session.add(WizardState(status=status))
    session.commit()
    session.close()


def _make_request(cookies=None):
    headers = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/wizard/import/start",
        "headers": headers,
        "query_string": b"",
        "server": ("localhost", 5000),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "app": None,
    }
    return Request(scope)


def _run(coro):
    import asyncio

    return asyncio.run(coro)


class TestRequireWizardIncomplete:
    def test_passes_when_no_wizard_row_exists(self, session_factory):
        session = session_factory()
        result = _run(require_wizard_incomplete(session=session))
        assert result is None

    def test_passes_while_wizard_is_in_progress(self, session_factory):
        _seed_wizard(session_factory, WizardStatus.IN_PROGRESS)
        session = session_factory()
        result = _run(require_wizard_incomplete(session=session))
        assert result is None

    def test_rejects_once_wizard_has_completed(self, session_factory):
        _seed_wizard(session_factory, WizardStatus.COMPLETED)
        session = session_factory()
        with pytest.raises(HTTPException) as exc_info:
            _run(require_wizard_incomplete(session=session))
        assert exc_info.value.status_code in (400, 403)


class TestRequireWizardIncompleteOrAuthenticated:
    def test_passes_while_wizard_is_incomplete_even_with_no_session(
        self, session_factory
    ):
        session = session_factory()
        request = _make_request(cookies=None)
        result = _run(
            require_wizard_incomplete_or_authenticated(request=request, session=session)
        )
        assert result is None

    def test_rejects_completed_wizard_with_no_session(self, session_factory):
        _seed_wizard(session_factory, WizardStatus.COMPLETED)
        session = session_factory()
        request = _make_request(cookies=None)
        with pytest.raises(HTTPException) as exc_info:
            _run(
                require_wizard_incomplete_or_authenticated(
                    request=request, session=session
                )
            )
        assert exc_info.value.status_code == 401

    def test_accepts_completed_wizard_with_a_valid_session(
        self, session_factory, monkeypatch
    ):
        _seed_wizard(session_factory, WizardStatus.COMPLETED)
        session = session_factory()
        request = _make_request(cookies={"session_token": "fake-valid-token"})

        async def _fake_get_current_user_session(req):
            return {"authenticated": True, "user_id": 1, "role": "USER"}

        monkeypatch.setattr(
            "src.api.fastapi.wizard.get_current_user_session",
            _fake_get_current_user_session,
        )

        result = _run(
            require_wizard_incomplete_or_authenticated(request=request, session=session)
        )
        assert result == {"authenticated": True, "user_id": 1, "role": "USER"}


class TestSettingsOnlyRoutesBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db_session] = lambda: iter([MagicMock()])
        return TestClient(app)

    def test_upload_videos_401s_without_session(self):
        client = self._client()
        response = client.post(
            "/api/wizard/upload-videos",
            files={"files": ("test.mp4", b"fake video data", "video/mp4")},
        )
        assert response.status_code == 401

    def test_custom_directory_import_401s_without_session(self):
        client = self._client()
        response = client.post(
            "/api/wizard/import/custom-directory/start",
            json={"directory": "/tmp"},
        )
        assert response.status_code == 401
