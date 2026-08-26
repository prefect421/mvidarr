"""Regression test for a real authentication bypass found by background
security review of #417: monitoring_dashboard.py's WebSocket endpoint
(/ws) was left unauthenticated on the reasoning that WebSocket routes
need different auth machinery than Depends(require_authentication)/
Depends(require_admin) -- true, but that just meant it needed its own
equivalent check, not that it could be skipped.

The bypass was serious: the moment *any* client connects to /ws, the
server's background broadcast loop (DashboardWebSocketManager.
_broadcast_updates()) automatically pushes get_dashboard_summary()
data every 5 seconds with no request needed -- the exact data
require_admin protects on GET /summary. The connection's message
handler also serves get_metric_history() for any metric name on
request -- the exact data require_admin protects on GET
/metrics/{metric_name}/history. Both REST siblings were fixed to
require_admin in #417; the WebSocket sibling was a complete,
unauthenticated bypass of both.

Fix: resolve the connection's session_token cookie (WebSocket, like
Request, inherits .cookies from Starlette's HTTPConnection) against
the same SessionStore.validate_session() that
auth_dependencies.get_current_user_session() uses, and reject with a
close (code 1008, Policy Violation) *before* accept() if the
connection isn't an authenticated admin -- so a rejected connection
never joins active_connections, never receives the broadcast, and
never gets a chance to send a request_metric_history message.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.fastapi.monitoring_dashboard import (
    _get_websocket_admin_user,
    router,
    websocket_endpoint,
)


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestWebSocketRejectsUnauthorizedConnections:
    """These exercise the real close-before-accept path end to end --
    no service mocking needed, since a rejected connection never
    reaches websocket_manager.connect() (and so never starts the
    broadcast loop that would otherwise need get_analytics_service()/
    get_scaling_status())."""

    # Note on close codes: a pre-accept rejection (close() called before
    # accept(), which is exactly what the fix does -- deliberately, so a
    # rejected connection never joins active_connections or starts
    # receiving broadcasts) has no completed WebSocket handshake yet, so
    # ASGI servers -- and Starlette's TestClient -- can't transmit a real
    # close *frame* carrying a custom code; it surfaces as the generic
    # disconnect code 1000 regardless of what close(code=...) was passed.
    # What actually matters for this fix is verified here: the connection
    # never succeeds. The exact rejection code is verified precisely
    # against _get_websocket_admin_user() directly in
    # TestGetWebsocketAdminUser below.

    def test_connection_with_no_session_cookie_is_rejected(self):
        client = _client()
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value=None,
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws"):
                    pass

    def test_connection_with_a_non_admin_session_is_rejected(self):
        client = _client()
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value={"authenticated": True, "role": "USER", "user_id": 1},
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws", cookies={"session_token": "fake-user-token"}
                ):
                    pass

    def test_connection_with_an_unauthenticated_flag_is_rejected(self):
        # A session that resolves but was somehow left un-flagged as
        # authenticated (mirrors require_admin's own "not
        # current_user.get('authenticated')" branch) must still reject.
        client = _client()
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value={"authenticated": False, "role": "ADMIN", "user_id": 1},
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws", cookies={"session_token": "fake-token"}
                ):
                    pass


class TestWebsocketEndpointClosesWithPolicyViolation:
    """Calls websocket_endpoint() directly against a mock WebSocket,
    outside the ASGI stack, so the exact close code passed to
    close() -- lost by the time it reaches a TestClient, per the note
    above -- can be asserted precisely."""

    def test_closes_with_code_1008_and_never_connects_when_unauthorized(self):
        ws = MagicMock()
        ws.cookies = {}
        ws.close = AsyncMock()

        with patch(
            "src.api.fastapi.monitoring_dashboard.websocket_manager.connect",
            new_callable=AsyncMock,
        ) as mock_connect:
            asyncio.run(websocket_endpoint(ws))

        ws.close.assert_awaited_once_with(code=1008)
        mock_connect.assert_not_awaited()


class TestGetWebsocketAdminUser:
    """Direct unit tests of the auth-resolution helper, avoiding the
    fragility of driving the full connection lifecycle (which also
    spins up the real broadcast loop's service calls) just to prove
    the admin path returns the user dict."""

    def _fake_websocket(self, cookies):
        ws = MagicMock()
        ws.cookies = cookies
        return ws

    def test_returns_the_user_dict_for_a_valid_admin_session(self):
        ws = self._fake_websocket({"session_token": "fake-admin-token"})
        admin_user = {"authenticated": True, "role": "ADMIN", "user_id": 1}
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value=admin_user,
        ):
            result = asyncio.run(_get_websocket_admin_user(ws))
        assert result == admin_user

    def test_returns_none_with_no_cookie_at_all(self):
        ws = self._fake_websocket({})
        result = asyncio.run(_get_websocket_admin_user(ws))
        assert result is None

    def test_returns_none_for_a_non_admin_role(self):
        ws = self._fake_websocket({"session_token": "fake-user-token"})
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value={"authenticated": True, "role": "USER", "user_id": 1},
        ):
            result = asyncio.run(_get_websocket_admin_user(ws))
        assert result is None

    def test_returns_none_when_validate_session_finds_nothing(self):
        ws = self._fake_websocket({"session_token": "expired-or-bogus-token"})
        with patch(
            "src.services.session_store.SessionStore.validate_session",
            return_value=None,
        ):
            result = asyncio.run(_get_websocket_admin_user(ws))
        assert result is None
