"""Regression test for a residual auth gap in videos_thumbnails.py (#392
Phase 2 follow-up). Every metadata/management route in this file already
requires authentication (thumbnail/info, search, upload, PUT thumbnail);
the route that actually serves the image bytes (get_video_thumbnail) was
missed -- same class of gap as artists_thumbnails.py's sibling routes
(#392 Phase 2 follow-up, get_artist_thumbnail/get_artist_thumbnail_with_
size). Only ever referenced same-origin (frontend/templates/*.html uses
plain <img src="/api/videos/{id}/thumbnail">), so the browser attaches
the session cookie automatically -- and this app deliberately omits
thumbnail URLs from Discord/webhook embeds specifically because a
self-hosted instance is often not publicly reachable (see
discord_notification_formatter.py's docstring), so there's no external
unauthenticated consumer either. Same tier as its siblings
(require_authentication, no admin split).
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_thumbnails import router
from src.database.connection import get_db_session

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "videos_thumbnails.py"
)


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


class TestVideoThumbnailServingRequiresAuth:
    def test_route_requires_authentication(self):
        source = _function_source("get_video_thumbnail")
        assert "Depends(require_authentication)" in source

    def test_every_route_in_file_requires_authentication(self):
        # Guards against another route slipping through unnoticed.
        for route in router.routes:
            source = _function_source(route.endpoint.__name__)
            assert (
                "Depends(require_authentication)" in source
            ), f"{route.endpoint.__name__} is missing Depends(require_authentication)"


class TestVideoThumbnailServingBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db_session] = lambda: iter([MagicMock()])
        return TestClient(app)

    def test_route_401s_without_session(self):
        client = self._client()
        response = client.get("/1/thumbnail")
        assert response.status_code == 401

    def test_route_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/1/thumbnail")
        assert response.status_code != 401
