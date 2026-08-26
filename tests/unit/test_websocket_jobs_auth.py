"""Fix for a live, unauthenticated WebSocket found during a systematic
re-audit of #392's actual current status: websocket_jobs.py's /ws/jobs
endpoint accepted every connection unauthenticated ("Authentication
simplified for now"). Once connected, the server's Redis subscriber
broadcasts real-time progress for every Celery job in the system to every
connected client with no further gating -- a complete, unauthenticated
exposure of live download/job activity, the same class of bug already
fixed for monitoring_dashboard.py's /ws in #392 Phase 2 follow-up (PR
#419).

/ws/jobs/test (a debug HTML page for the above) had the same gap.

Fix: extract the connection handler and test page out of
setup_websocket_routes()'s closures into module-level functions (needed
for direct testability -- mirrors monitoring_dashboard.py's own
websocket_endpoint refactor), gate /ws/jobs with a new
_get_websocket_authenticated_user() helper (mirrors
monitoring_dashboard.py's _get_websocket_admin_user, but accepts any
authenticated role -- job/download progress is regular library content,
not host-system metrics, so no admin split needed), and gate
/ws/jobs/test with the standard Depends(require_authentication).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.fastapi.websocket_jobs import (
    _get_websocket_authenticated_user,
    setup_websocket_routes,
    websocket_job_progress,
)


def _client():
    app = FastAPI()
    setup_websocket_routes(app)
    return TestClient(app)


class TestWebSocketJobsRejectsUnauthorizedConnections:
    """End-to-end via TestClient.websocket_connect -- only checks
    WebSocketDisconnect is raised, not the exact close code (a pre-accept
    rejection has no completed handshake yet, so ASGI servers -- and
    Starlette's TestClient -- can't transmit a real close *frame* carrying
    a custom code; see TestWebsocketJobProgressClosesWithPolicyViolation
    below for the precise code assertion)."""

    def test_connection_with_no_session_cookie_is_rejected(self):
        client = _client()
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value=None,
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/jobs"):
                    pass

    def test_connection_with_an_unauthenticated_flag_is_rejected(self):
        client = _client()
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value={"authenticated": False, "user_id": 1},
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws/jobs", cookies={"session_token": "fake-token"}
                ):
                    pass


class TestWebsocketJobProgressClosesWithPolicyViolation:
    def test_closes_with_code_1008_and_never_connects_when_unauthorized(self):
        ws = MagicMock()
        ws.cookies = {}
        ws.close = AsyncMock()

        with patch(
            "src.api.fastapi.websocket_jobs.websocket_manager.connect_user",
            new_callable=AsyncMock,
        ) as mock_connect:
            asyncio.run(websocket_job_progress(ws))

        ws.close.assert_awaited_once_with(code=1008)
        mock_connect.assert_not_awaited()


class TestGetWebsocketAuthenticatedUser:
    def _fake_websocket(self, cookies):
        ws = MagicMock()
        ws.cookies = cookies
        return ws

    def test_returns_the_user_dict_for_any_valid_authenticated_role(self):
        ws = self._fake_websocket({"session_token": "fake-user-token"})
        user = {"authenticated": True, "role": "USER", "user_id": 5}
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value=user,
        ):
            result = asyncio.run(_get_websocket_authenticated_user(ws))
        assert result == user

    def test_returns_none_with_no_cookie_at_all(self):
        ws = self._fake_websocket({})
        result = asyncio.run(_get_websocket_authenticated_user(ws))
        assert result is None

    def test_returns_none_when_validate_session_finds_nothing(self):
        ws = self._fake_websocket({"session_token": "expired-or-bogus-token"})
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value=None,
        ):
            result = asyncio.run(_get_websocket_authenticated_user(ws))
        assert result is None


class TestWebsocketTestPageRequiresAuth:
    def test_401s_without_session(self):
        client = _client()
        response = client.get("/ws/jobs/test")
        assert response.status_code == 401
