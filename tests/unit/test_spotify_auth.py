"""Tests for spotify.py's auth fix (#386 follow-up). Zero routes were
protected -- the file's only auth-related import was a dead, commented-out
line referencing a different, disabled middleware module. Sibling file
spotify_enhanced.py already did this correctly; this backports that
pattern, split by sensitivity: routes that create/complete/destroy the
shared instance-wide Spotify OAuth link use require_admin (mirroring
auth.py's POST /credentials, hardened after a real dev-testing finding
that any authenticated non-admin session could change instance-wide
credentials); read-only routes use require_authentication.

spotify_callback is deliberately excluded from EXPECTED_TIER below: #391
found that Depends(require_admin) there bypassed the route's own
friendly redirect-based OAuth-error UX (Depends() failures raise before
the route body's try/except can see them). It still enforces the exact
same authenticated+ADMIN check -- just replicated inline via
Depends(get_optional_user) instead, so a failure can produce the same
RedirectResponse as every other failure mode in that function. See
test_spotify_callback_redirect_on_auth_failure.py for its real coverage.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_admin, require_authentication
from src.api.fastapi.spotify import router as spotify_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "spotify.py"
)

EXPECTED_TIER = {
    "search_artists": "auth",
    "get_artist": "auth",
    "get_artist_albums": "auth",
    "get_artist_top_tracks": "auth",
    "get_related_artists": "auth",
    "get_user_playlists": "auth",
    "get_playlist": "auth",
    "get_playlist_tracks": "auth",
    "search_tracks": "auth",
    "search_albums": "auth",
    "get_user_profile": "auth",
    "get_spotify_status": "auth",
    "test_spotify_integration": "admin",
    "authorize_spotify": "admin",
    "disconnect_spotify": "admin",
    "import_playlist": "auth",
    "import_all_playlists": "auth",
    "sync_followed_artists": "auth",
    "get_top_artists": "auth",
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


class TestSpotifyAllRoutesHaveCorrectTier:
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


class TestSpotifyBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(spotify_router)
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/spotify/status")
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.post("/api/spotify/authorize")
        assert response.status_code == 401

    def test_admin_tier_route_succeeds_for_admin_session(self):
        app = FastAPI()
        app.include_router(spotify_router)
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.post("/api/spotify/authorize")
        assert response.status_code != 401
        assert response.status_code != 403

    def test_authenticated_tier_route_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(spotify_router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.get("/api/spotify/status")
        assert response.status_code != 401
