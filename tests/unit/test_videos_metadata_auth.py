"""Tests for videos_metadata.py's auth fix (closes #386's original scope)."""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_metadata import router as videos_metadata_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "videos_metadata.py"
)

EXPECTED_AUTHENTICATED_ROUTES = [
    "bulk_refresh_metadata",
    "bulk_enhanced_refresh_metadata",
    "enhanced_refresh_all_metadata",
    "enhanced_refresh_metadata",
    "extract_video_year",
    "bulk_extract_years",
]


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


class TestVideosMetadataAllRoutesAuthenticated:
    def test_every_route_requires_authentication(self):
        for function_name in EXPECTED_AUTHENTICATED_ROUTES:
            source = _function_source(function_name)
            assert "Depends(require_authentication)" in source


class TestVideosMetadataBehavioralAuth:
    def test_bulk_refresh_metadata_401s_without_session(self):
        app = FastAPI()
        app.include_router(videos_metadata_router)
        client = TestClient(app)
        response = client.post("/bulk/refresh-metadata", json={"video_ids": [1]})
        assert response.status_code == 401

    def test_bulk_refresh_metadata_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(videos_metadata_router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.post("/bulk/refresh-metadata", json={"video_ids": [1]})
        assert response.status_code != 401
