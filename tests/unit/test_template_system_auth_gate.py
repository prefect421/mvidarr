"""Tests for template_system.py's require_authentication/require_admin —
found broken during manual dev testing ahead of v1.0.0 (2026-08-11), in
three rounds as each fix exposed the next layer:

1. require_authentication tried to enforce a redirect by *returning* a
   RedirectResponse from a FastAPI Depends() callable. A value returned
   from a dependency is just an ordinary parameter passed to the route
   handler — it is never used as the actual HTTP response unless the
   handler explicitly checks and returns it. None of the 9 frontend
   routes using this dependency did (settings, scheduler dashboard/jobs,
   youtube-playlists, spotify/lastfm/lidarr managers, enrichment, 2FA
   setup), so every one of them rendered normally for fully anonymous
   requests. Fixed by raising an HTTPException instead.

2. The "require_authentication" setting is stored as the string "false"
   in the database and was checked with plain Python truthiness, where
   any non-empty string (including the literal text "false") is truthy.
   Fixed by using SettingsService.get_bool().

3. Fixing #1 immediately exposed a third, pre-existing bug: this file's
   user-resolution logic depended on request.state.user (and, briefly,
   request.state.session_user too) — attributes JWTAuthMiddleware only
   populates for paths OUTSIDE its own public_paths list. /settings,
   /admin, and every other page this file protects are ALL listed as
   public there, so the middleware never touches request.state for them
   regardless of whether a valid session cookie is present. Real
   logged-in users were bounced to /auth/login exactly like anonymous
   visitors (reported directly by the user testing dev immediately after
   the round-2 fix shipped). Fixed by delegating to
   auth_dependencies.get_optional_user, which validates the session_token
   cookie directly via SessionStore — the same, already-hardened logic
   every /api/* route already depends on — instead of maintaining a
   second, independently-buggy copy of session resolution here.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.api.fastapi.template_system import require_admin, require_authentication
from src.database.models import UserRole


def _make_request():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/settings",
        "headers": [(b"host", b"localhost")],
        "query_string": b"",
        "server": ("localhost", 5000),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "app": None,
    }
    return Request(scope)


def _session_user(role="USER"):
    """SessionStore.validate_session's real return shape."""
    return {
        "username": "someone",
        "authenticated": True,
        "user_id": 1,
        "role": role,
    }


TEMPLATE_SYSTEM_GET_OPTIONAL_USER = (
    "src.api.fastapi.auth_dependencies.get_optional_user"
)


class TestRequireAuthenticationRaisesInsteadOfReturning:
    @pytest.mark.asyncio
    async def test_anonymous_request_raises_a_redirect_when_auth_required(self):
        request = _make_request()
        with patch(TEMPLATE_SYSTEM_GET_OPTIONAL_USER, return_value=None), patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_authentication(request)
        assert exc_info.value.status_code == 302
        assert exc_info.value.headers["Location"] == "/auth/login"

    @pytest.mark.asyncio
    async def test_anonymous_request_passes_through_when_auth_not_required(self):
        request = _make_request()
        with patch(TEMPLATE_SYSTEM_GET_OPTIONAL_USER, return_value=None), patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=False
        ):
            result = await require_authentication(request)
        assert result is None


class TestRequireAuthenticationValidatesTheSessionCookieDirectly:
    """The real-world bug: /settings (and every page this file protects)
    is in JWTAuthMiddleware's public_paths, so request.state is never
    populated for it — this function must resolve the session itself.
    """

    @pytest.mark.asyncio
    async def test_valid_session_passes_through(self):
        request = _make_request()
        user = _session_user(role="USER")
        with patch(TEMPLATE_SYSTEM_GET_OPTIONAL_USER, return_value=user), patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            result = await require_authentication(request)
        assert result == user

    @pytest.mark.asyncio
    async def test_valid_session_is_not_redirected_to_login(self):
        # Regression pin for the exact bug reported during manual testing:
        # a genuinely logged-in user kept getting bounced back to
        # /auth/login when visiting /settings, on a page that
        # JWTAuthMiddleware itself never blocks (it's in public_paths).
        request = _make_request()
        user = _session_user(role="ADMIN")
        with patch(TEMPLATE_SYSTEM_GET_OPTIONAL_USER, return_value=user), patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            try:
                await require_authentication(request)
            except HTTPException:
                pytest.fail(
                    "a request with a valid session cookie must not be "
                    "redirected to login"
                )


class TestRequireAdminStillEnforcesRoleForRealUsers:
    @pytest.mark.asyncio
    async def test_admin_user_passes(self):
        request = _make_request()
        user = _session_user(role=UserRole.ADMIN.value)
        with patch(TEMPLATE_SYSTEM_GET_OPTIONAL_USER, return_value=user), patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            result = await require_admin(request)
        assert result == user

    @pytest.mark.asyncio
    async def test_non_admin_user_is_rejected(self):
        request = _make_request()
        user = _session_user(role=UserRole.USER.value)
        with patch(TEMPLATE_SYSTEM_GET_OPTIONAL_USER, return_value=user), patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_anonymous_request_is_redirected_not_silently_admitted(self):
        request = _make_request()
        with patch(TEMPLATE_SYSTEM_GET_OPTIONAL_USER, return_value=None), patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(request)
        assert exc_info.value.status_code == 302


class TestRequireAuthenticationSettingBoolParsing:
    def test_stored_false_string_is_not_truthy(self):
        # Regression pin for the settings.get() vs settings.get_bool()
        # bug: SettingsService.get() returns the raw string "false", and
        # `if "false":` is True in Python (non-empty string). get_bool()
        # must be used everywhere this setting gates behavior.
        from src.services.settings_service import SettingsService

        with patch.object(SettingsService, "get", return_value="false"):
            assert SettingsService.get_bool("require_authentication", True) is False

    def test_stored_true_string_is_truthy(self):
        from src.services.settings_service import SettingsService

        with patch.object(SettingsService, "get", return_value="true"):
            assert SettingsService.get_bool("require_authentication", False) is True
