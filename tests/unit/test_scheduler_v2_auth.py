"""Tests for scheduler_v2.py's auth fix (#392 Phase 2). Every route in this
file had zero authentication -- full scheduler control (start/stop/trigger
discovery/trigger downloads/retry-or-cancel any job/reload settings) was
reachable by anyone who could hit the app. Fixed by applying the real
require_authentication/require_admin dependencies (src.api.fastapi.
auth_dependencies), split by sensitivity: read-only routes get
require_authentication, state-changing routes get require_admin --
mirroring the same split already used in settings.py and Phase 1's other
fixed files.
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
from src.api.fastapi.scheduler_v2 import router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "scheduler_v2.py"
)

# function_name -> "admin" | "auth"
EXPECTED_TIER = {
    "get_scheduler_status": "auth",
    "start_scheduler": "admin",
    "stop_scheduler": "admin",
    "trigger_discovery": "admin",
    "trigger_downloads": "admin",
    "get_job_history": "auth",
    "get_job_details": "auth",
    "retry_job": "admin",
    "cancel_job": "admin",
    "get_scheduler_health": "auth",
    "reload_settings": "admin",
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


class TestSchedulerV2AllRoutesHaveCorrectTier:
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

    def test_all_eleven_routes_are_covered_by_this_mapping(self):
        # Guards against a route being added/renamed without updating
        # EXPECTED_TIER above -- every route on the live router must
        # appear in the mapping, and vice versa.
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        assert route_function_names == set(EXPECTED_TIER.keys())


class TestSchedulerV2BehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/v2/scheduler/status")
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.post("/api/v2/scheduler/start")
        assert response.status_code == 401

    def test_admin_tier_route_403s_for_non_admin_authenticated_user(self):
        app = FastAPI()
        app.include_router(router)
        # require_admin depends on get_current_user directly (see
        # auth_dependencies.py), not on require_authentication -- so to
        # reach require_admin's own role-check branch we must override
        # get_current_user itself, not require_authentication (overriding
        # the latter would be a no-op for this route and this test would
        # pass for the wrong reason, or rather not exercise the branch at
        # all).
        app.dependency_overrides[get_current_user] = lambda: {
            "authenticated": True,
            "role": "user",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.post("/api/v2/scheduler/start")
        # Authenticated but non-admin: require_admin's role check
        # (role != ADMIN) must reject with 403, not 401.
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
        response = client.post("/api/v2/scheduler/start")
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
        response = client.get("/api/v2/scheduler/status")
        assert response.status_code != 401
