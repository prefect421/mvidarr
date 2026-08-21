"""Tests for monitoring_dashboard.py's auth fix (#392 Phase 2). All 7 REST
routes had zero authentication. Routes that reveal host resource metrics
(get_dashboard_summary, get_metric_history -- the latter serves history
for *any* metric name, including the system.cpu/memory/disk ones listed
by get_available_metrics) are require_admin, matching health.py's (#407)
and performance.py's (#414) precedent for the same category of info
disclosure. create_alert_rule is require_admin as a state-changing
action. The rest (static config/metric-name lists, alert list, dashboard
status, the demo page shell) are require_authentication.

The 8th route on this router, the WebSocket endpoint (/ws), is
intentionally NOT covered here -- same reasoning as bulk_operations.py
(#408): WebSocket routes use different dependency-injection machinery
than regular HTTP routes, and this sweep doesn't have time for dedicated
testing of that path right now.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_admin,
    require_authentication,
)
from src.api.fastapi.monitoring_dashboard import router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "monitoring_dashboard.py"
)

# function_name -> "admin" | "auth"
EXPECTED_TIER = {
    "get_dashboard_summary": "admin",
    "get_metric_history": "admin",
    "get_available_metrics": "auth",
    "get_active_alerts": "auth",
    "create_alert_rule": "admin",
    "get_dashboard_config": "auth",
    "get_dashboard_status": "auth",
    "get_dashboard_demo": "auth",
}


def _function_source(function_name: str) -> str:
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError(f"Could not find function {function_name!r} in {SOURCE_PATH}")


class TestMonitoringDashboardAllRestRoutesHaveCorrectTier:
    def test_every_route_has_the_expected_dependency(self):
        for function_name, tier in EXPECTED_TIER.items():
            source = _function_source(function_name)
            expected = (
                "Depends(require_admin)"
                if tier == "admin"
                else "Depends(require_authentication)"
            )
            assert (
                expected in source
            ), f"{function_name} should use {expected}, got:\n{source}"

    def test_all_rest_routes_are_covered_by_this_mapping(self):
        # The websocket route (websocket_endpoint) is deliberately
        # excluded -- see module docstring.
        rest_route_names = {
            route.endpoint.__name__
            for route in router.routes
            if hasattr(route, "methods")  # excludes the WebSocketRoute
        }
        assert rest_route_names == set(EXPECTED_TIER.keys())


class TestMonitoringDashboardBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/dashboard/config")
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 401

    def test_admin_tier_route_403s_for_non_admin_authenticated_user(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: {
            "authenticated": True,
            "role": "user",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 403

    def test_admin_tier_route_succeeds_for_admin_session(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.get("/api/dashboard/summary")
        assert response.status_code != 401
        assert response.status_code != 403

    def test_authenticated_tier_route_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.get("/api/dashboard/config")
        assert response.status_code != 401
