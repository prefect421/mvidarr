"""Fix for #391: spotify_callback's custom OAuth-error redirect UX was
bypassed by require_admin.

spotify_callback()'s own body has careful error handling that redirects
the browser to /settings?spotify_error=... on an OAuth failure (declined
consent, Spotify returned an error param, token exchange failed, etc).
But require_admin runs as a FastAPI Depends() BEFORE the route body
executes -- Depends() failures raise during FastAPI's dependency-
resolution phase, which the route's own try/except can never see. An
admin-session check failure (e.g. the admin's session expired during the
OAuth consent flow on Spotify's own site) short-circuited straight to a
raw JSON 401/403, bypassing the friendlier redirect-based error UX
entirely -- right as the browser lands back on this app fresh off
Spotify's redirect.

Fix: replace Depends(require_admin) with Depends(get_optional_user) (which
never raises -- returns None instead of a session dict) and replicate
require_admin's exact check (authenticated AND role == ADMIN) inline, as
the first thing the route body does, so a failure there gets caught by
the same RedirectResponse pattern as every other failure mode in this
function. Security semantics are unchanged -- same authenticated+ADMIN
check, just relocated so it can produce the friendly response instead of
a bare exception.

lastfm.py's handle_callback -- which #391 named as sharing "the same
shape" -- turns out not to: unlike spotify_callback, it has NO existing
redirect-based UX to preserve. Every branch (success and failure alike)
already returns a plain dict or raises HTTPException; there's no
RedirectResponse anywhere in that function for require_admin to bypass.
Applying "the same fix" there would introduce new, inconsistent
behavior (a redirect on exactly one failure mode, JSON on every other),
not restore anything that used to work. Left untouched -- a genuine UX
improvement for that endpoint (matching spotify_callback's more complete
redirect-based flow) is a separate, larger change than what #391 asked
for.
"""

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from src.api.fastapi.spotify import spotify_callback

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "spotify.py"
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


class TestSpotifyCallbackNoLongerUsesRequireAdmin:
    def test_does_not_use_depends_require_admin(self):
        source = _function_source("spotify_callback")
        assert "Depends(require_admin)" not in source

    def test_uses_get_optional_user_instead(self):
        source = _function_source("spotify_callback")
        assert "Depends(get_optional_user)" in source

    def test_replicates_the_authenticated_and_admin_role_check_inline(self):
        source = _function_source("spotify_callback")
        assert "UserRole.ADMIN.value" in source


class TestSpotifyCallbackBehavioralAuthFailure:
    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    # NOTE: these pass a code= value (unlike the "no session" case a real
    # unauthenticated request would have) specifically so that, against
    # the OLD implementation, calling this function directly (bypassing
    # FastAPI's real Depends() resolution, which direct calls always do)
    # would fall through past the "no code" branch and into the token-
    # exchange logic instead of coincidentally producing a same-shaped
    # redirect for an unrelated reason. Only the NEW inline auth check
    # can catch these before that point.

    def test_redirects_to_settings_when_no_session_exists(self):
        result = self._run(
            spotify_callback(
                request=None,
                code="fake-auth-code",
                error=None,
                current_user=None,
            )
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "admin" in result.headers["location"].lower()

    def test_redirects_to_settings_when_session_is_not_admin(self):
        result = self._run(
            spotify_callback(
                request=None,
                code="fake-auth-code",
                error=None,
                current_user={"authenticated": True, "role": "USER", "user_id": 2},
            )
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "admin" in result.headers["location"].lower()

    def test_redirects_to_settings_when_session_is_unauthenticated_flag(self):
        # A session that resolves but was somehow left un-flagged as
        # authenticated (mirrors require_admin's own "not
        # current_user.get('authenticated')" branch) must still be
        # rejected, not silently admitted.
        result = self._run(
            spotify_callback(
                request=None,
                code="fake-auth-code",
                error=None,
                current_user={"authenticated": False, "role": "ADMIN", "user_id": 1},
            )
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "admin" in result.headers["location"].lower()

    def test_does_not_redirect_early_for_a_genuine_admin_session(self):
        # A real admin session must reach the function's own OAuth-error
        # handling (error param present here), not get bounced by the
        # auth check itself.
        result = self._run(
            spotify_callback(
                request=None,
                code=None,
                error="access_denied",
                current_user={"authenticated": True, "role": "ADMIN", "user_id": 1},
            )
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "spotify_error=access_denied" in result.headers["location"]
