"""Regression test: GET /api/auth/oauth/{provider}/callback returned raw
JSON on a successful login instead of redirecting into the app.

This endpoint is only ever reached via a real, top-level browser
navigation — the OAuth provider's own server-side redirect after the
user authorizes, not a fetch()/XHR call from MVidarr's own frontend JS
(confirmed: nothing in frontend/templates calls this URL). Returning
JSONResponse meant a successful login left the user staring at a raw
JSON blob (visible via Firefox's built-in JSON viewer) instead of being
dropped back into the app — reported live 2026-08-12 testing Google
OAuth: "acts like it is starting to work then returns" JSON.

The session_token cookie WAS being set correctly either way — this was
purely a wrong response type for a navigation-triggered endpoint, not a
failure to authenticate.
"""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class _FakeUser:
    id = 1
    username = "oauth_test_user"
    email = "test@example.com"

    class _Role:
        value = "USER"

    role = _Role()

    def can_access_admin(self):
        return False

    def can_modify_content(self):
        return True

    def can_delete_content(self):
        return False


class _FakeSession:
    pass


class TestOAuthCallbackRedirectsOnSuccess:
    def test_successful_callback_redirects_instead_of_returning_json(self):
        client = _make_client()
        client.cookies.set("oauth_state", "abc123")

        with patch(
            "src.api.fastapi.auth.oauth_service.handle_oauth_callback",
            return_value=(True, "OK", _FakeUser(), _FakeSession()),
        ), patch(
            "src.api.fastapi.auth.SessionStore.create_session",
            return_value="a-real-session-token",
        ):
            response = client.get(
                "/api/auth/oauth/authentik/callback?code=fake&state=abc123",
                follow_redirects=False,
            )

        assert response.status_code in (302, 303, 307)
        assert response.headers["location"] == "/"

    def test_successful_callback_still_sets_the_session_cookie(self):
        client = _make_client()
        client.cookies.set("oauth_state", "abc123")

        with patch(
            "src.api.fastapi.auth.oauth_service.handle_oauth_callback",
            return_value=(True, "OK", _FakeUser(), _FakeSession()),
        ), patch(
            "src.api.fastapi.auth.SessionStore.create_session",
            return_value="a-real-session-token",
        ):
            response = client.get(
                "/api/auth/oauth/authentik/callback?code=fake&state=abc123",
                follow_redirects=False,
            )

        assert response.cookies.get("session_token") == "a-real-session-token"
