"""Tests for video_indexing_page.py's auth fix (#392 Phase 2). Its single
route (video_indexing_page) is a page-shell route serving the video
indexing management HTML page -- same class of route as maintenance.py's
maintenance_page (#413) and personal_insights.py's analytics_page (#418),
both gated with require_authentication to match frontend_router.py's
precedent for management-page routes.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.video_indexing_page import page_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "video_indexing_page.py"
)

EXPECTED_ROUTES = {"video_indexing_page"}


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


class TestVideoIndexingPageRequiresAuth:
    def test_route_requires_authentication(self):
        source = _function_source("video_indexing_page")
        assert "Depends(require_authentication)" in source

    def test_all_routes_are_covered_by_this_mapping(self):
        route_function_names = {route.endpoint.__name__ for route in page_router.routes}
        assert route_function_names == EXPECTED_ROUTES


class TestVideoIndexingPageBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(page_router)
        return TestClient(app)

    def test_route_401s_without_session(self):
        client = self._client()
        response = client.get("/video-indexing")
        assert response.status_code == 401

    def test_route_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(page_router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.get("/video-indexing")
        assert response.status_code != 401
