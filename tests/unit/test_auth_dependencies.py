"""Tests confirming get_current_user_session relies only on SessionStore
(the Flask-session fallback is dead code — no Flask app context is ever
pushed in the live process — and must not silently grant access).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.fastapi.auth_dependencies import get_current_user_session


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
