"""Tests for playlists_features.py's auth fix (#392 Phase 2). Of the 8
routes on this router, 3 already genuinely enforce authentication via
get_current_user_from_session() (which delegates to the real
auth_dependencies.get_current_user(), raising 401 if unauthenticated,
plus resolves the actual DB user record) -- create_dynamic_playlist,
update_dynamic_playlist_filters, and get_user_playlists. Those 3 are
correctly implemented already and are deliberately left untouched here
(replacing their auth call with Depends(require_authentication) would
lose the DB user-record lookup those routes actually use).

The other 5 had zero authentication at all -- three of them
(refresh_dynamic_playlist, upload_playlist_thumbnail_url,
upload_playlist_thumbnail_file) even carry a "Permission check would
go here when auth system is implemented" comment (refresh_dynamic_
playlist's presence in that group was caught by this test file itself
during initial development -- an earlier draft misclassified it as
already-secure based on its proximity to routes that do call
get_current_user_from_session(), not its own body). All 5 get
require_authentication, matching the tier already used throughout
playlists_crud.py (this file's sibling, already fully protected) --
playlists are regular per-user content, not admin-only config, so no
admin split is needed here either.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.playlists_features import router
from src.database.connection import get_db_session

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "playlists_features.py"
)

NEWLY_GATED_ROUTES = {
    "preview_dynamic_playlist",
    "refresh_dynamic_playlist",
    "get_playlist_thumbnail",
    "upload_playlist_thumbnail_url",
    "upload_playlist_thumbnail_file",
}

ALREADY_SECURE_VIA_SESSION_LOOKUP = {
    "create_dynamic_playlist",
    "update_dynamic_playlist_filters",
    "get_user_playlists",
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


class TestPlaylistsFeaturesNewlyGatedRoutes:
    def test_every_previously_open_route_now_requires_authentication(self):
        for function_name in NEWLY_GATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_already_secure_routes_still_use_the_session_lookup(self):
        # Guards against a future edit accidentally removing the
        # existing, correctly-working auth call on these 4 while
        # "cleaning up" -- they were deliberately left alone here.
        for function_name in ALREADY_SECURE_VIA_SESSION_LOOKUP:
            source = _function_source(function_name)
            assert "get_current_user_from_session(" in source

    def test_all_eight_routes_are_accounted_for(self):
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        assert route_function_names == (
            NEWLY_GATED_ROUTES | ALREADY_SECURE_VIA_SESSION_LOOKUP
        )


class TestPlaylistsFeaturesBehavioralAuth:
    # get_playlist_thumbnail declares session: Depends(get_db_session)
    # ahead of current_user: Depends(require_authentication) in its
    # signature; FastAPI resolves dependencies in that order, so in this
    # bare test app (no real db_manager) get_db_session's own
    # RuntimeError("Database not initialized") would fire before
    # require_authentication gets a chance to reject -- masking the
    # very thing under test. Overriding get_db_session with a working
    # fake (never actually queried; the request should be rejected
    # before the route body runs) lets require_authentication's real
    # 401 surface, matching real production behavior where db_manager
    # is always initialized before any request is served.
    def _client(self, override_db=True):
        app = FastAPI()
        app.include_router(router)
        if override_db:
            app.dependency_overrides[get_db_session] = lambda: iter([MagicMock()])
        return TestClient(app)

    def test_newly_gated_route_401s_without_session(self):
        client = self._client()
        response = client.get("/1/thumbnail")
        assert response.status_code == 401

    def test_newly_gated_route_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/1/thumbnail")
        assert response.status_code != 401
