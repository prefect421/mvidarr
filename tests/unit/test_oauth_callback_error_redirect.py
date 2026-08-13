"""Regression test for #353: every failure path in
GET /api/auth/oauth/{provider}/callback returned a raw JSONResponse
(via HTTPException) instead of redirecting into the app.

This endpoint is only ever reached via a real, top-level browser
navigation — the OAuth provider's own server-side redirect after the
user authorizes (or denies) access, not a fetch()/XHR call from
MVidarr's own frontend JS (confirmed: nothing in frontend/templates
calls this URL). PR #347 already fixed the SUCCESS path for the same
reason; this covers the failure paths, which #347 didn't touch.

All failures now redirect to /auth/login?oauth_error=<message> instead.
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _oauth_error(response):
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    return query.get("oauth_error", [None])[0]


class TestOAuthCallbackFailuresRedirectInsteadOfReturningJson:
    def test_provider_error_redirects_to_login(self):
        client = _make_client()
        response = client.get(
            "/api/auth/oauth/google/callback?error=access_denied",
            follow_redirects=False,
        )

        assert response.status_code in (302, 303, 307)
        assert response.headers["location"].startswith("/auth/login?")
        assert _oauth_error(response) is not None

    def test_missing_code_and_state_redirects_to_login(self):
        client = _make_client()
        response = client.get("/api/auth/oauth/google/callback", follow_redirects=False)

        assert response.status_code in (302, 303, 307)
        assert response.headers["location"].startswith("/auth/login?")

    def test_state_mismatch_redirects_to_login(self):
        client = _make_client()
        client.cookies.set("oauth_state", "wrong-value")
        response = client.get(
            "/api/auth/oauth/google/callback?code=fake&state=abc123",
            follow_redirects=False,
        )

        assert response.status_code in (302, 303, 307)
        assert response.headers["location"].startswith("/auth/login?")

    def test_signup_denied_redirects_with_the_real_reason(self):
        """The exact case reported live: a user not on the OAuth
        allowlist (#350) gets a real, readable reason instead of a
        JSON blob."""
        client = _make_client()
        client.cookies.set("oauth_state", "abc123")

        with patch(
            "src.api.fastapi.auth.oauth_service.handle_oauth_callback",
            return_value=(False, "Failed to create or find user", None, None),
        ):
            response = client.get(
                "/api/auth/oauth/google/callback?code=fake&state=abc123",
                follow_redirects=False,
            )

        assert response.status_code in (302, 303, 307)
        assert _oauth_error(response) == "Failed to create or find user"

    def test_unexpected_exception_redirects_with_a_generic_message(self):
        """Internal exception details must not leak into the redirect
        (matches the pre-existing 500 branch's generic message)."""
        client = _make_client()
        client.cookies.set("oauth_state", "abc123")

        with patch(
            "src.api.fastapi.auth.oauth_service.handle_oauth_callback",
            side_effect=RuntimeError("some internal detail"),
        ):
            response = client.get(
                "/api/auth/oauth/google/callback?code=fake&state=abc123",
                follow_redirects=False,
            )

        assert response.status_code in (302, 303, 307)
        error = _oauth_error(response)
        assert error is not None
        assert "some internal detail" not in error
