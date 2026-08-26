"""Regression test for residual auth gaps in artists_thumbnails.py (#392
Phase 2 follow-up). Every other route in this file already requires
authentication; the two image-serving routes (get_artist_thumbnail,
get_artist_thumbnail_with_size) were missed. Both are only ever referenced
same-origin (frontend/templates/*.html uses plain <img
src="/api/artists/{id}/thumbnail">), so the browser attaches the session
cookie automatically -- there's no external, unauthenticated consumer
(confirmed: this app deliberately omits thumbnail URLs from Discord/
webhook embeds specifically because a self-hosted instance is often not
publicly reachable -- see discord_notification_formatter.py's docstring).
Same tier as their siblings (require_authentication, no admin split).
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.artists_thumbnails import router
from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "artists_thumbnails.py"
)

NEWLY_GATED_ROUTES = {
    "get_artist_thumbnail",
    "get_artist_thumbnail_with_size",
}


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


class TestThumbnailServingRoutesRequireAuth:
    def test_every_newly_gated_route_requires_authentication(self):
        for function_name in NEWLY_GATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_every_route_in_file_requires_authentication(self):
        # Guards against another route slipping through unnoticed.
        for route in router.routes:
            source = _function_source(route.endpoint.__name__)
            assert (
                "Depends(require_authentication)" in source
            ), f"{route.endpoint.__name__} is missing Depends(require_authentication)"


class TestThumbnailServingBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db_session] = lambda: iter([MagicMock()])
        return TestClient(app)

    def test_thumbnail_route_401s_without_session(self):
        client = self._client()
        response = client.get("/1/thumbnail")
        assert response.status_code == 401

    def test_thumbnail_with_size_route_401s_without_session(self):
        client = self._client()
        response = client.get("/1/thumbnail/small")
        assert response.status_code == 401

    def test_thumbnail_route_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/1/thumbnail")
        assert response.status_code != 401
