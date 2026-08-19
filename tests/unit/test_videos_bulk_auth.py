"""Tests for videos_bulk.py's auth fix (closes #386's original scope).
Includes normalizing the one route that already had SOME dependency
(refresh_video_thumbnails, bare Depends(get_current_user)) to the real
enforcing dependency, require_authentication -- get_current_user alone
does not raise on an unauthenticated request.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.videos_bulk import router as videos_bulk_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "videos_bulk.py"
)

EXPECTED_AUTHENTICATED_ROUTES = [
    "bulk_delete_videos",
    "bulk_update_status",
    "bulk_update_status_debug",
    "bulk_edit_videos",
    "bulk_organize_videos",
    "bulk_refresh_all_thumbnails",
    "refresh_video_thumbnails",
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


class TestVideosBulkAllRoutesAuthenticated:
    def test_every_route_requires_authentication(self):
        for function_name in EXPECTED_AUTHENTICATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_refresh_video_thumbnails_no_longer_uses_bare_get_current_user(self):
        source = _function_source("refresh_video_thumbnails")
        assert "Depends(get_current_user)" not in source


class TestVideosBulkBehavioralAuth:
    def test_bulk_delete_401s_without_session(self):
        app = FastAPI()
        app.include_router(videos_bulk_router)
        client = TestClient(app)
        response = client.post("/bulk/delete", json={"video_ids": [1]})
        assert response.status_code == 401
