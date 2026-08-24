"""Tests for frontend_router.py's remaining unauthenticated content pages
(#392 Phase 2 follow-up). 9 sibling pages in this same file already use
template_system.require_authentication (settings, scheduler dashboard/
jobs, youtube-playlists, spotify/lastfm/webhooks/lidarr managers,
enrichment, 2FA setup) -- the app's own main content pages (the actual
dashboard/videos/artists/playlists/discover/mvtv/jobs pages, plus the two
modal-fragment components embedded in them) had no such gate at all,
showing full page content to fully anonymous visitors.

Left deliberately public (not touched here):
- wizard_page (/wizard): explicitly pre-setup, no admin account can exist
  yet to authenticate as. Tracked separately (#405).
- login_page, simple_login_page: must be reachable to log in at all.
- logout: safe regardless of auth state -- clears whatever session
  exists (or none) and redirects to login either way.
- not_found_handler, internal_server_error_handler: framework exception
  handlers (not @frontend_router-decorated routes), must render for any
  visitor including anonymous ones hitting a bad URL.
- frontend_health (/health) and web_app_manifest (/manifest.json):
  neither reveals sensitive data (booleans about template/static dirs
  existing; static app branding metadata) and both match established
  public-probe/PWA-manifest conventions (health.py's own public liveness/
  readiness routes; browsers fetch PWA manifests before a user has ever
  logged in, e.g. to evaluate installability from the login page itself).

frontend_navigation (/api/navigation) is a JSON API endpoint returning
static menu structure, not an HTML page (mirrors frontend_search, its
sibling in this same file, already fixed with the API-style 401 variant
in an earlier PR) -- gated the same way, not with the redirect-style
dependency the HTML pages use, since a 302 to a fetch() call would be
followed transparently and return the login page's HTML where JSON was
expected.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.frontend_router import frontend_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "frontend_router.py"
)

PAGE_STYLE_ROUTES = {
    "index": "/",
    "dashboard": "/dashboard",
    "videos": "/videos",
    "video_detail": "/videos/1",
    "video_detail_singular": "/video/1",
    "artists": "/artists",
    "artist_detail": "/artist/1",
    "playlists": "/playlists",
    "playlist_detail": "/playlist/1",
    "discover": "/discover",
    "mvtv": "/mvtv",
    "jobs": "/jobs",
    "add_video_modal_component": "/components/add-video-modal",
    "job_dashboard_modal_component": "/components/job-dashboard-modal",
}

API_STYLE_ROUTES = {
    "frontend_navigation": "/api/navigation",
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


class TestFrontendRouterPagesRequireAuth:
    def test_every_page_style_route_uses_template_systems_require_authentication(
        self,
    ):
        for function_name in PAGE_STYLE_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_every_api_style_route_uses_the_401_variant(self):
        for function_name in API_STYLE_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_api_authentication)" in source
            ), f"{function_name} should use Depends(require_api_authentication), got:\n{source}"


class TestFrontendRouterPagesBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(frontend_router)
        return TestClient(app, follow_redirects=False)

    def test_every_page_style_route_redirects_anonymous_visitors_to_login(self):
        client = self._client()
        for function_name, path in PAGE_STYLE_ROUTES.items():
            response = client.get(path)
            assert response.status_code == 302, (
                f"{function_name} ({path}) should 302 for an anonymous "
                f"visitor, got {response.status_code}"
            )
            assert response.headers["location"] == "/auth/login"

    def test_every_api_style_route_401s_for_anonymous_visitors(self):
        client = self._client()
        for function_name, path in API_STYLE_ROUTES.items():
            response = client.get(path)
            assert response.status_code == 401, (
                f"{function_name} ({path}) should 401 for an anonymous "
                f"visitor, got {response.status_code}"
            )


class TestDeliberatelyPublicRoutesStayPublic:
    """Regression guard: none of these should ever pick up an auth
    dependency by accident during future edits to this file."""

    def _client(self):
        app = FastAPI()
        app.include_router(frontend_router)
        return TestClient(app, follow_redirects=False)

    def test_wizard_page_stays_reachable_without_a_session(self):
        client = self._client()
        response = client.get("/wizard")
        assert response.status_code != 302

    def test_login_page_stays_reachable_without_a_session(self):
        client = self._client()
        response = client.get("/auth/login")
        assert response.status_code != 302

    def test_logout_stays_reachable_without_a_session(self):
        client = self._client()
        response = client.get("/auth/logout")
        assert response.status_code != 401
