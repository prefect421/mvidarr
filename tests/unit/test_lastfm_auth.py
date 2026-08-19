"""Tests for lastfm.py's auth fix (#386 follow-up). Same bug class and fix
shape as spotify.py (see test_spotify_auth.py): OAuth-link-mutating routes
get require_admin, read-only routes get require_authentication. Unlike
spotify.py, this file already had require_authentication imported and
applied to one route (import_top_artists) before this fix -- that route is
untouched here.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_admin, require_authentication
from src.api.fastapi.lastfm import router as lastfm_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "lastfm.py"
)

EXPECTED_TIER = {
    "get_lastfm_status": "auth",
    "test_lastfm_connection": "admin",
    "get_auth_url": "admin",
    "handle_callback": "admin",
    "get_profile": "auth",
    "get_top_artists": "auth",
    "get_top_tracks": "auth",
    "get_recent_tracks": "auth",
    "get_loved_tracks": "auth",
    "get_artist_info": "auth",
    "get_listening_stats": "auth",
    "import_top_artists": "auth",  # already done pre-fix, unchanged
    "import_loved_tracks": "auth",
    "sync_history": "auth",
    "disconnect": "admin",
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


class TestLastfmAllRoutesHaveCorrectTier:
    def test_every_route_has_the_expected_dependency(self):
        for function_name, tier in EXPECTED_TIER.items():
            source = _function_source(function_name)
            expected = (
                "Depends(require_admin)"
                if tier == "admin"
                else "Depends(require_authentication)"
            )
            assert (
                expected in source
            ), f"{function_name} should use {expected}, got:\n{source}"


class TestLastfmBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(lastfm_router)
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/lastfm/status")
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/lastfm/auth/url")
        assert response.status_code == 401

    def test_admin_tier_route_succeeds_for_admin_session(self):
        app = FastAPI()
        app.include_router(lastfm_router)
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.get("/api/lastfm/auth/url")
        assert response.status_code != 401
        assert response.status_code != 403
