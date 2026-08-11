"""Tests for template_system.py's require_authentication/require_admin —
found broken during manual dev testing ahead of v1.0.0 (2026-08-11).

Two independent bugs, both fixed here:

1. require_authentication tried to enforce a redirect by *returning* a
   RedirectResponse from a FastAPI Depends() callable. A value returned
   from a dependency is just an ordinary parameter passed to the route
   handler — it is never used as the actual HTTP response unless the
   handler explicitly checks and returns it. None of the 9 frontend
   routes using this dependency did (settings, scheduler dashboard/jobs,
   youtube-playlists, spotify/lastfm/lidarr managers, enrichment, 2FA
   setup), so every one of them rendered normally for fully anonymous
   requests. Fixed by raising an HTTPException instead — that halts the
   request unconditionally regardless of what the handler does with the
   dependency's return value.

2. The "require_authentication" setting is stored as the string "false"
   in the database. `if settings.get("require_authentication", True):`
   checks Python truthiness on that STRING, and any non-empty string
   (including the literal text "false") is truthy — so this check always
   took the "auth is required" branch regardless of the setting's actual
   value. Fixed by using SettingsService.get_bool(), which parses the
   string content instead of checking non-emptiness.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.api.fastapi.template_system import require_admin, require_authentication


def _make_anonymous_request():
    """A request with no request.state.user set at all — the state of
    every real anonymous request that never goes through the JWT/session
    middleware's authenticated branch.
    """
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


def _make_authenticated_request(role="USER"):
    request = _make_anonymous_request()
    user = MagicMock()
    user.role = role
    request.state.user = user
    return request


class TestRequireAuthenticationRaisesInsteadOfReturning:
    @pytest.mark.asyncio
    async def test_anonymous_request_raises_a_redirect_when_auth_required(self):
        request = _make_anonymous_request()
        with patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_authentication(request)
        assert exc_info.value.status_code == 302
        assert exc_info.value.headers["Location"] == "/auth/login"

    @pytest.mark.asyncio
    async def test_anonymous_request_passes_through_when_auth_not_required(self):
        request = _make_anonymous_request()
        with patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=False
        ):
            result = await require_authentication(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticated_request_passes_through_regardless_of_setting(self):
        request = _make_authenticated_request(role="USER")
        with patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            result = await require_authentication(request)
        assert result is request.state.user


class TestRequireAdminStillEnforcesRoleForRealUsers:
    @pytest.mark.asyncio
    async def test_admin_user_passes(self):
        request = _make_authenticated_request(role="admin")
        with patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            result = await require_admin(request)
        assert result is request.state.user

    @pytest.mark.asyncio
    async def test_non_admin_user_is_rejected(self):
        request = _make_authenticated_request(role="user")
        with patch(
            "src.api.fastapi.template_system.settings.get_bool", return_value=True
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_anonymous_request_is_redirected_not_silently_admitted(self):
        # Regression pin: before the fix, require_authentication's ignored
        # RedirectResponse return value was truthy and had no .role
        # attribute, so require_admin happened to 403 anonymous users by
        # accident. Now it must raise the same 302 require_authentication
        # itself raises, for the correct reason.
        request = _make_anonymous_request()
        with patch(
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
