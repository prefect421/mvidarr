"""Tests for system_health.py's auth fix. All 9 routes exposed internal
infra detail (disk/memory/CPU/DB/celery/redis, plus a genuine arbitrary
file read via /logs -- see test_health_monitoring_log_sandboxing.py for
that part) with zero authentication. Gated behind require_admin.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_admin
from src.api.fastapi.system_health import page_router
from src.api.fastapi.system_health import router as health_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "system_health.py"
)

EXPECTED_ADMIN_ROUTES = [
    "get_health_summary",
    "get_disk_health",
    "get_memory_health",
    "get_cpu_health",
    "get_db_health",
    "get_celery_health",
    "get_redis_health",
    "get_logs",
    "system_health_page",
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


class TestSystemHealthAllRoutesAdmin:
    def test_every_route_requires_admin(self):
        for function_name in EXPECTED_ADMIN_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_admin)" in source
            ), f"{function_name} should use Depends(require_admin), got:\n{source}"


class TestSystemHealthBehavioralAuth:
    def test_health_summary_401s_without_session(self):
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        response = client.get("/api/system-health/")
        assert response.status_code == 401

    def test_logs_401s_without_session(self):
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        response = client.get("/api/system-health/logs")
        assert response.status_code == 401

    def test_health_summary_succeeds_for_admin_session(self):
        app = FastAPI()
        app.include_router(health_router)
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.get("/api/system-health/")
        assert response.status_code != 401
        assert response.status_code != 403
