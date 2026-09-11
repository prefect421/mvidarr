"""Tests for playlists_features.py's auth fix (#392 Phase 2, updated for
#500). Of the 8 routes on this router, 6 now genuinely enforce
authentication via get_current_user_from_session() (which delegates to
the real auth_dependencies.get_current_user(), raising 401 if
unauthenticated, plus resolves the actual DB user record) --
create_dynamic_playlist, update_dynamic_playlist_filters,
get_user_playlists, refresh_dynamic_playlist, upload_playlist_thumbnail_url,
and upload_playlist_thumbnail_file.

The first 3 were already correctly implemented under #392. The latter 3
were widened from a bare Depends(require_authentication) (added under
#392 Phase 2, replacing "Permission check would go here when auth system
is implemented" placeholders) to the session-based lookup as part of
#500: those routes act on a specific playlist_id and had *no ownership
check at all* -- any authenticated user could modify/delete another
user's playlist. Fixing that requires the real UserInfo (with .id and
.can_access_admin()) that only get_current_user_from_session() provides,
plus a can_modify_playlist(playlist, current_user) check in the route
body -- require_authentication's bare dict isn't enough for that.

The remaining 2 (preview_dynamic_playlist, get_playlist_thumbnail) don't
act on a caller-owned resource in a way that needs an identity check
(preview takes no playlist_id; thumbnail-serving is read-only) and
correctly stay on require_authentication, matching the tier used
throughout playlists_crud.py for non-ownership-sensitive routes.
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
    "get_playlist_thumbnail",
}

ALREADY_SECURE_VIA_SESSION_LOOKUP = {
    "create_dynamic_playlist",
    "update_dynamic_playlist_filters",
    "get_user_playlists",
    "refresh_dynamic_playlist",
    "upload_playlist_thumbnail_url",
    "upload_playlist_thumbnail_file",
}

OWNERSHIP_CHECKED_ROUTES = {
    "refresh_dynamic_playlist",
    "update_dynamic_playlist_filters",
    "upload_playlist_thumbnail_url",
    "upload_playlist_thumbnail_file",
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
        # Guards against a future edit accidentally removing the real
        # session-based identity lookup on these routes while "cleaning
        # up". Two call styles are both valid here: an explicit
        # `await get_current_user_from_session(request)` (used where the
        # route needs the user before other logic runs), or FastAPI
        # resolving it via `Depends(get_current_user_from_session)` in
        # the signature -- both end up calling the same function and
        # getting the same real UserInfo. Check for the name generically
        # rather than one specific calling convention.
        for function_name in ALREADY_SECURE_VIA_SESSION_LOOKUP:
            source = _function_source(function_name)
            assert "get_current_user_from_session" in source

    def test_all_eight_routes_are_accounted_for(self):
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        assert route_function_names == (
            NEWLY_GATED_ROUTES | ALREADY_SECURE_VIA_SESSION_LOOKUP
        )

    def test_ownership_checked_routes_call_can_modify_playlist(self):
        # #500: these routes act on a specific playlist_id and must reject
        # a caller who doesn't own the playlist (and isn't an admin/manager).
        for function_name in OWNERSHIP_CHECKED_ROUTES:
            source = _function_source(function_name)
            assert (
                "can_modify_playlist(" in source
            ), f"{function_name} should check can_modify_playlist(), got:\n{source}"


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
