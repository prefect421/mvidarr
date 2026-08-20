"""Tests for system_health.py's auth fix. All 9 routes exposed internal
infra detail (disk/memory/CPU/DB/celery/redis, plus a genuine arbitrary
file read via /logs -- see test_health_monitoring_log_sandboxing.py for
that part) with zero authentication. The 8 JSON API routes are gated
behind auth_dependencies.require_admin (401 JSON on failure).

system_health_page is the exception: it renders an HTML page
(response_class=HTMLResponse), so it must use
template_system.require_admin instead (imported here under the alias
require_admin_page, mirroring frontend_router.py's inverse alias of
auth_dependencies.require_authentication as require_api_authentication).
Using the JSON-style auth_dependencies.require_admin on an HTML page
route meant a logged-out browser hitting /system-health saw a raw JSON
401 blob instead of being redirected to /auth/login -- fixed in the
final-review fix wave.
"""

import ast
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_admin
from src.api.fastapi.system_health import page_router
from src.api.fastapi.system_health import router as health_router
from src.api.fastapi.template_system import require_admin as require_admin_page

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


class TestSystemHealthPageUsesTemplateSystemAuth:
    """system_health_page renders HTML and must redirect (302 to
    /auth/login) on failure, not 401 with a JSON body -- the JSON
    variant is for the file's other 8 (API) routes only.
    """

    def test_system_health_page_uses_the_aliased_page_dependency(self):
        source = _function_source("system_health_page")
        assert "Depends(require_admin_page)" in source
        assert "Depends(require_admin)" not in source

    def test_system_health_page_redirects_not_401s_without_session(self):
        app = FastAPI()
        app.include_router(page_router)
        client = TestClient(app, follow_redirects=False)
        response = client.get("/system-health")
        assert response.status_code == 302
        assert "/auth/login" in response.headers["location"]


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
