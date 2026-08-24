"""Regression test for residual auth gaps in themes.py (#392 Phase 2
follow-up). Every other route in this file already requires
authentication; delete_theme (DELETE /{theme_id}, a destructive
state-changing action) and export_all_themes (GET /export/all, a bulk
data export) were missed. Same tier as their siblings
(require_authentication, no admin split anywhere else in this file).
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.themes import router
from src.database.connection import get_db_session

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "themes.py"
)

NEWLY_GATED_ROUTES = {
    "delete_theme",
    "export_all_themes",
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


class TestThemesRoutesRequireAuth:
    def test_every_newly_gated_route_requires_authentication(self):
        for function_name in NEWLY_GATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_every_route_in_file_requires_authentication(self):
        # Guards against another route slipping through unnoticed.
        for route in router.routes:
            source = _function_source(route.endpoint.__name__)
            assert (
                "Depends(require_authentication)" in source
            ), f"{route.endpoint.__name__} is missing Depends(require_authentication)"


class TestThemesBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db_session] = lambda: iter([MagicMock()])
        return TestClient(app)

    def test_delete_theme_401s_without_session(self):
        client = self._client()
        response = client.delete("/api/themes/1")
        assert response.status_code == 401

    def test_export_all_themes_401s_without_session(self):
        client = self._client()
        response = client.get("/api/themes/export/all")
        assert response.status_code == 401

    def test_export_all_themes_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
            # user_id is required since #392's fail-open-default fix
            # (_require_user_id): a session dict missing it now 401s
            # instead of silently defaulting to a fixed fallback user.
            "user_id": 1,
        }
        response = client.get("/api/themes/export/all")
        assert response.status_code != 401
