"""Tests for videos_downloads.py's auth fix (closes #386's original
scope). All 5 routes imported get_current_user but never applied it --
every call was unauthenticated despite the module docstring claiming auth
was required.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_downloads import router as videos_downloads_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "videos_downloads.py"
)

EXPECTED_AUTHENTICATED_ROUTES = [
    "bulk_download_videos",
    "queue_video_download",
    "queue_video_download_debug",
    "queue_download_video",
    "bulk_download_wanted_videos",
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


class TestVideosDownloadsAllRoutesAuthenticated:
    def test_every_route_requires_authentication(self):
        for function_name in EXPECTED_AUTHENTICATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_no_longer_imports_the_unused_get_current_user(self):
        source = SOURCE_PATH.read_text()
        assert "import get_current_user" not in source


class TestVideosDownloadsBehavioralAuth:
    def test_bulk_download_401s_without_session(self):
        app = FastAPI()
        app.include_router(videos_downloads_router)
        client = TestClient(app)
        response = client.post("/bulk/download", json={"video_ids": [1]})
        assert response.status_code == 401
