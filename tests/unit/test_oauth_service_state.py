"""Tests for oauth_service's CSRF state storage, now server-side instead
of Flask-session-based (Flask has no request context in this FastAPI-only
process, so the old flask_session code always failed — see #312 / the
2026-08-09 Task 5 audit)."""

from unittest.mock import patch

from src.services.oauth_service import OAuthService, _oauth_states


def setup_function():
    _oauth_states.clear()


def test_initiate_oauth_flow_stores_state_without_flask():
    service = OAuthService.__new__(OAuthService)
    service.providers = {"authentik": _FakeProvider()}

    success, auth_url, state = service.initiate_oauth_flow("authentik")

    assert success is True
    assert state in _oauth_states
    assert _oauth_states[state]["provider"] == "authentik"


def test_handle_oauth_callback_accepts_matching_state():
    service = OAuthService.__new__(OAuthService)
    service.providers = {"authentik": _FakeProvider()}
    success, auth_url, state = service.initiate_oauth_flow("authentik")

    with patch.object(
        OAuthService,
        "_find_or_create_oauth_user",
        return_value=(_FakeUser(), _FakeSession()),
    ):
        success, message, user, session_obj = service.handle_oauth_callback(
            "authentik", "fake-code", state
        )

    assert success is True
    assert state not in _oauth_states  # cleaned up after use


def test_handle_oauth_callback_rejects_unknown_state():
    service = OAuthService.__new__(OAuthService)
    service.providers = {"authentik": _FakeProvider()}

    success, message, user, session_obj = service.handle_oauth_callback(
        "authentik", "fake-code", "state-that-was-never-issued"
    )

    assert success is False
    assert "state" in message.lower()


def test_handle_oauth_callback_rejects_provider_mismatch():
    service = OAuthService.__new__(OAuthService)
    service.providers = {"authentik": _FakeProvider(), "google": _FakeProvider()}
    success, auth_url, state = service.initiate_oauth_flow("authentik")

    success, message, user, session_obj = service.handle_oauth_callback(
        "google", "fake-code", state
    )

    assert success is False


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
