"""Tests for OAuth CSRF state handling — now browser-bound via cookie at
the route layer (auth.py), not server-side dict storage in oauth_service.py.
Per RFC 9700 / OWASP OAuth2 Cheat Sheet: state must be securely bound to
the user agent, which a server-only store cannot provide. See the
2026-08-10 Part D revision for why the original dict approach (Part A)
was replaced.
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth import router
from src.services.oauth_service import OAuthService


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestOAuthLoginSetsCookie:
    def test_oauth_login_sets_oauth_state_cookie(self):
        client = _make_client()

        with patch(
            "src.api.fastapi.auth.oauth_service.initiate_oauth_flow",
            return_value=(
                True,
                "https://provider.example/authorize?state=abc123",
                "abc123",
            ),
        ):
            response = client.get(
                "/api/auth/oauth/authentik/login",
                headers={"x-forwarded-proto": "https"},
            )

        assert response.status_code == 200
        assert response.cookies.get("oauth_state") == "abc123"

        # Pin the cookie's security attributes directly, not just its
        # value — httponly/secure/samesite are exactly what commit
        # 27798c67 exists to guarantee, and response.cookies alone can't
        # see them (those flags aren't exposed via Cookies, only the raw
        # Set-Cookie header). x-forwarded-proto: https above exercises
        # the is_https=True branch so `Secure` is actually asserted, not
        # skipped.
        set_cookie_header = response.headers.get("set-cookie")
        assert set_cookie_header is not None
        assert "httponly" in set_cookie_header.lower()
        assert "secure" in set_cookie_header.lower()
        assert "samesite=lax" in set_cookie_header.lower()


class TestOAuthCallbackValidatesCookie:
    # Failure responses redirect to /auth/login?oauth_error=... rather
    # than returning a JSON error body — see test_oauth_callback_error_
    # redirect.py's module docstring (#353) for why: this endpoint is
    # only ever reached via a real browser navigation, not a fetch()/XHR
    # call, so a JSON body just showed the user a raw JSON blob.
    def test_callback_rejects_missing_cookie(self):
        client = _make_client()
        response = client.get(
            "/api/auth/oauth/authentik/callback?code=fake&state=abc123",
            follow_redirects=False,
        )
        assert response.status_code in (302, 303, 307)
        assert response.headers["location"].startswith("/auth/login?oauth_error=")

    def test_callback_rejects_mismatched_cookie(self):
        client = _make_client()
        client.cookies.set("oauth_state", "different-value")
        response = client.get(
            "/api/auth/oauth/authentik/callback?code=fake&state=abc123",
            follow_redirects=False,
        )
        assert response.status_code in (302, 303, 307)
        assert response.headers["location"].startswith("/auth/login?oauth_error=")

    def test_callback_accepts_matching_cookie(self):
        client = _make_client()
        client.cookies.set("oauth_state", "abc123")

        with patch(
            "src.api.fastapi.auth.oauth_service.handle_oauth_callback",
            return_value=(False, "Failed to obtain access token", None, None),
        ):
            response = client.get(
                "/api/auth/oauth/authentik/callback?code=fake&state=abc123",
                follow_redirects=False,
            )

        # Cookie matched, so the request proceeds past the CSRF check
        # into the actual OAuth exchange (which fails here for an
        # unrelated, mocked reason). Still a redirect, but carrying the
        # downstream failure's message — pins "got past the CSRF gate,
        # failed for the downstream reason" rather than a looser check
        # that would also pass on the CSRF failure itself.
        assert response.status_code in (302, 303, 307)
        location = response.headers["location"]
        query = parse_qs(urlparse(location).query)
        assert query["oauth_error"][0] == "Failed to obtain access token"


def test_handle_oauth_callback_passes_ip_and_user_agent_through():
    service = OAuthService.__new__(OAuthService)
    service.providers = {"authentik": _FakeProvider()}
    success, auth_url, state = service.initiate_oauth_flow("authentik")

    with patch.object(
        OAuthService, "_find_or_create_oauth_user"
    ) as mock_find_or_create:
        mock_find_or_create.return_value = (_FakeUser(), _FakeSession())
        service.handle_oauth_callback(
            "authentik",
            "fake-code",
            state,
            ip_address="203.0.113.5",
            user_agent="TestAgent/1.0",
        )

    mock_find_or_create.assert_called_once_with(
        "authentik",
        {"id": "123", "email": "test@example.com"},
        ip_address="203.0.113.5",
        user_agent="TestAgent/1.0",
    )


class _FakeProvider:
    def get_authorization_url(self, state):
        return f"https://example.com/authorize?state={state}"

    def exchange_code_for_token(self, code, state):
        return {"access_token": "fake-token"}

    def get_user_info(self, access_token):
        return {"id": "123", "email": "test@example.com"}


class _FakeUser:
    username = "oauth_test_user"


class _FakeSession:
    pass
