"""Tests for videos_import.py's auth fix (closes #386's original scope)."""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_import import router as videos_import_router

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
        app = FastAPI()
        app.include_router(videos_import_router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.post("/import-from-youtube", json={"url": "x"})
        assert response.status_code != 401
