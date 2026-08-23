"""Tests for production_monitoring.py's auth fix (#392 Phase 2). All 6
routes had zero authentication. Four reveal host/system resource details
(CPU/memory/disk, DB pool stats, security-alert counts) -- the same class
of data health.py (#407) and performance.py (#414) gated with
require_admin: comprehensive_health_check, get_system_status,
get_detailed_metrics, get_active_alerts. The other two (readiness_probe,
liveness_probe) look like Kubernetes-style infra probes, but unlike
health.py's public 3 (which Docker's own HEALTHCHECK genuinely depends
on -- see Dockerfile), nothing in this repo's Docker/Compose config calls
these specific routes. With no infra reason to leave them open, and a
nonzero leak (DB-up/down status, process pid), they get
require_authentication rather than staying public.
"""

import ast
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

# security_audit_service.py instantiates a module-level SecurityAuditService()
# that unconditionally mkdir()s a hardcoded "/app/data/logs/security" path at
# import time -- fine in the real Docker container (which runs as /app), but
# fatal here since this dev checkout isn't rooted at /app. Shimming the
# module before production_monitoring imports it avoids that unrelated
# import-time side effect without touching production code for an auth-only
# change.
_MODULE_NAME = "src.services.security_audit_service"
_already_imported = _MODULE_NAME in sys.modules
if not _already_imported:
    _fake_security_audit_service = types.ModuleType(_MODULE_NAME)
    _fake_security_audit_service.get_security_audit_service = AsyncMock()
    sys.modules[_MODULE_NAME] = _fake_security_audit_service

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_admin,
    require_authentication,
)
from src.api.fastapi.production_monitoring import router

# production_monitoring already bound its own reference to
# get_security_audit_service via the shimmed module above -- remove the
# shim afterwards so it doesn't leak into other test modules collected in
# the same pytest session that need the real thing.
if not _already_imported:
    del sys.modules[_MODULE_NAME]

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "production_monitoring.py"
)

ADMIN_ROUTES = {
    "comprehensive_health_check",
    "get_system_status",
    "get_detailed_metrics",
    "get_active_alerts",
}

AUTH_ROUTES = {
    "readiness_probe",
    "liveness_probe",
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


class TestProductionMonitoringRoutesRequireAuth:
    def test_host_metric_routes_require_admin(self):
        for function_name in ADMIN_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_admin)" in source
            ), f"{function_name} should use Depends(require_admin), got:\n{source}"

    def test_probe_routes_require_authentication(self):
        for function_name in AUTH_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_all_six_routes_are_accounted_for(self):
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        assert route_function_names == (ADMIN_ROUTES | AUTH_ROUTES)


class TestProductionMonitoringBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_admin_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/monitoring/metrics")
        assert response.status_code == 401

    def test_admin_route_403s_for_non_admin_session(self):
        client = self._client()
        client.app.dependency_overrides[get_current_user] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/api/monitoring/metrics")
        assert response.status_code == 403

    def test_auth_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/monitoring/liveness")
        assert response.status_code == 401

    def test_auth_route_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/api/monitoring/liveness")
        assert response.status_code != 401
