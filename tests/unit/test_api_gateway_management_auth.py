"""Tests for api_gateway_management.py's auth fix. All 13 routes (service
registration/deregistration, routing-rule management) were unauthenticated
infra-management endpoints. Gated behind require_admin.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.api_gateway_management import router as gateway_router
from src.api.fastapi.auth_dependencies import require_admin

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "api_gateway_management.py"
)

EXPECTED_ADMIN_ROUTES = [
    "register_service",
    "list_services",
    "deregister_service",
    "check_service_health",
    "create_route_rule",
    "list_routes",
    "delete_route_rule",
    "get_gateway_statistics",
    "gateway_health_check",
    "list_api_versions",
    "get_version_info",
    "get_migration_recommendations",
    "test_route_matching",
]


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


class TestApiGatewayAllRoutesAdmin:
    def test_every_route_requires_admin(self):
        for function_name in EXPECTED_ADMIN_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_admin)" in source
            ), f"{function_name} should use Depends(require_admin), got:\n{source}"


class TestApiGatewayBehavioralAuth:
    def test_list_services_401s_without_session(self):
        app = FastAPI()
        app.include_router(gateway_router)
        client = TestClient(app)
        response = client.get("/api/gateway/services")
        assert response.status_code == 401

    def test_list_services_succeeds_for_admin_session(self):
        app = FastAPI()
        app.include_router(gateway_router)
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.get("/api/gateway/services")
        assert response.status_code != 401
        assert response.status_code != 403
