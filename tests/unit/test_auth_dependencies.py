"""Tests confirming get_current_user_session relies only on SessionStore
(the Flask-session fallback is dead code — no Flask app context is ever
pushed in the live process — and must not silently grant access).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.fastapi.auth_dependencies import get_current_user_session, require_admin
from src.database.models import UserRole


class _FakeRequest:
    def __init__(self, cookies):
        self.cookies = cookies


@pytest.mark.asyncio
async def test_returns_none_with_no_session_cookie():
    request = _FakeRequest(cookies={})
    result = await get_current_user_session(request)
    assert result is None


@pytest.mark.asyncio
async def test_returns_real_role_from_session_store():
    request = _FakeRequest(cookies={"session_token": "abc123"})

    with patch(
        "src.services.session_store.SessionStore.validate_session"
    ) as mock_validate:
        mock_validate.return_value = {
            "username": "viewer",
            "authenticated": True,
            "user_id": 5,
            "role": "READONLY",
        }
        result = await get_current_user_session(request)

    assert result["role"] == "READONLY"
    assert result["username"] == "viewer"


@pytest.mark.asyncio
async def test_invalid_session_token_returns_none():
    request = _FakeRequest(cookies={"session_token": "bad-token"})

    with patch(
        "src.services.session_store.SessionStore.validate_session"
    ) as mock_validate:
        mock_validate.return_value = None
        result = await get_current_user_session(request)

    assert result is None


class TestRequireAdmin:
    """require_admin used to check an `is_admin` key that SessionStore no
    longer returns, so it denied every user including real admins.
    """

    @pytest.mark.asyncio
    async def test_admin_role_is_allowed(self):
        session = {
            "username": "boss",
            "authenticated": True,
            "role": UserRole.ADMIN.value,
        }
        assert await require_admin(session) is session

    @pytest.mark.parametrize(
        "role",
        [UserRole.MANAGER.value, UserRole.USER.value, UserRole.READONLY.value],
    )
    @pytest.mark.asyncio
    async def test_non_admin_roles_are_denied(self, role):
        session = {"username": "someone", "authenticated": True, "role": role}
        with pytest.raises(HTTPException) as exc:
            await require_admin(session)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_role_is_denied(self):
        session = {"username": "someone", "authenticated": True}
        with pytest.raises(HTTPException) as exc:
            await require_admin(session)
        assert exc.value.status_code == 403
