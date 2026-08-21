"""Tests for health.py's auth fix (#392 Phase 2). Every route in this file
had zero authentication. Unlike a typical file in this sweep, not every
route can simply be gated: GET /api/health/ is exactly what the Dockerfile's
own container HEALTHCHECK and docker-compose's healthcheck both curl
unauthenticated (`curl -f http://localhost:5000/api/health`) -- gating it
would mark the container permanently unhealthy. /liveness and /readiness
follow the same Kubernetes-style probe convention and must stay
unauthenticated too.

Tier split:
- public (no Depends at all): health_check, readiness_check, liveness_check
- require_authentication (basic status, low sensitivity): get_health_status,
  check_database, check_imvdb, check_metube, get_version_info,
  get_performance_stats, get_background_jobs_health
- require_admin (real operational detail: host resource metrics, backup
  file paths/sizes, migration revision, DB error messages, service
  topology): get_system_metrics, get_production_health,
  get_v1_components_health, get_monitoring_dashboard
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
from src.api.fastapi.health import health_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "health.py"
)

# function_name -> "public" | "auth" | "admin"
EXPECTED_TIER = {
    "health_check": "public",
    "readiness_check": "public",
    "liveness_check": "public",
    "get_health_status": "auth",
    "check_database": "auth",
    "check_imvdb": "auth",
    "check_metube": "auth",
    "get_version_info": "auth",
    "get_performance_stats": "auth",
    "get_background_jobs_health": "auth",
    "get_system_metrics": "admin",
    "get_production_health": "admin",
    "get_v1_components_health": "admin",
    "get_monitoring_dashboard": "admin",
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


class TestHealthAllRoutesHaveCorrectTier:
    def test_every_route_has_the_expected_dependency(self):
        for function_name, tier in EXPECTED_TIER.items():
            source = _function_source(function_name)
            if tier == "public":
                assert "Depends(require_authentication)" not in source
                assert "Depends(require_admin)" not in source
            else:
                expected = f"Depends(require_{'admin' if tier == 'admin' else 'authentication'})"
                assert (
                    expected in source
                ), f"{function_name} should use {expected}, got:\n{source}"

    def test_all_routes_are_covered_by_this_mapping(self):
        route_function_names = {
            route.endpoint.__name__ for route in health_router.routes
        }
        assert route_function_names == set(EXPECTED_TIER.keys())


class TestHealthDockerAndProbeRoutesStayPublic:
    """The one hard constraint in this file: these three MUST NOT require
    auth, or the container's own healthcheck (and any k8s-style probe)
    starts failing and the container gets marked unhealthy/restarted."""

    def _client(self):
        app = FastAPI()
        app.include_router(health_router, prefix="/api")
        # health_check() and readiness_check() do a real DB query via
        # Depends(get_db_session), which raises RuntimeError("Database not
        # initialized") outside a running app -- in production that becomes
        # a 500 via Starlette's exception-handling middleware; TestClient's
        # default re-raises it into the test process instead. What matters
        # here is only that these routes are never rejected with 401/403
        # (i.e. no auth gate was added), not that the underlying DB check
        # succeeds -- raise_server_exceptions=False matches the real
        # production behavior.
        return TestClient(app, raise_server_exceptions=False)

    def test_docker_healthcheck_route_works_with_no_session(self):
        client = self._client()
        response = client.get("/api/health/")
        assert response.status_code not in (401, 403)

    def test_readiness_route_works_with_no_session(self):
        client = self._client()
        response = client.get("/api/health/readiness")
        assert response.status_code not in (401, 403)

    def test_liveness_route_works_with_no_session(self):
        client = self._client()
        response = client.get("/api/health/liveness")
        assert response.status_code == 200


class TestHealthBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(health_router, prefix="/api")
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/health/version")
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/health/system")
        assert response.status_code == 401

    def test_admin_tier_route_403s_for_non_admin_authenticated_user(self):
        app = FastAPI()
        app.include_router(health_router, prefix="/api")
        # require_admin depends on get_current_user directly, not on
        # require_authentication -- override get_current_user itself to
        # reach require_admin's own role-check branch.
        app.dependency_overrides[get_current_user] = lambda: {
            "authenticated": True,
            "role": "user",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.get("/api/health/system")
        assert response.status_code == 403

    def test_admin_tier_route_succeeds_for_admin_session(self):
        app = FastAPI()
        app.include_router(health_router, prefix="/api")
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.get("/api/health/system")
        assert response.status_code != 401
        assert response.status_code != 403

    def test_authenticated_tier_route_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(health_router, prefix="/api")
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.get("/api/health/version")
        assert response.status_code != 401
