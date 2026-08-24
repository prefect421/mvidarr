"""Tests for videos_import.py's auth fix (closes #386's original scope)."""

import ast
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_import import router as videos_import_router
from src.database.connection import get_db_session

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "videos_import.py"
)

EXPECTED_AUTHENTICATED_ROUTES = ["import_from_youtube", "import_from_imvdb"]


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


class TestVideosImportAllRoutesAuthenticated:
    def test_every_route_requires_authentication(self):
        for function_name in EXPECTED_AUTHENTICATED_ROUTES:
            source = _function_source(function_name)
            assert "Depends(require_authentication)" in source


class TestVideosImportBehavioralAuth:
    def test_import_from_youtube_401s_without_session(self):
        app = FastAPI()
        app.include_router(videos_import_router)
        client = TestClient(app)
        response = client.post("/import-from-youtube", json={"url": "x"})
        assert response.status_code == 401

    def test_import_from_youtube_succeeds_for_authenticated_session(self):
        # #393: hermetic (get_db_session overridden too, passes in
        # isolation) and asserts real pass-through into the route's own
        # business logic, not just "not 401". A youtube_id is included
        # in the payload -- without one, the route 400s before ever
        # calling session.query(), which would make the assertion below
        # fail for an unrelated reason.
        app = FastAPI()
        app.include_router(videos_import_router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        # get_db_session is a generator dependency (yields a session);
        # this override is a plain callable, so FastAPI injects whatever
        # it *returns* directly rather than unwrapping a generator --
        # must return the session itself, not an iterator wrapping it.
        mock_session = MagicMock()
        app.dependency_overrides[get_db_session] = lambda: mock_session
        client = TestClient(app)
        response = client.post(
            "/import-from-youtube",
            json={"youtube_id": "abc123", "url": "https://youtube.com/watch?v=abc123"},
        )
        assert response.status_code != 401
        mock_session.query.assert_called()
