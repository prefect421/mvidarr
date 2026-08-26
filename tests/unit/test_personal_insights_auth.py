"""Tests for personal_insights.py's auth fix (#392 Phase 2). All 8 routes
had zero authentication. All are read-only collection-analytics queries
(summary/stats/top-artists/top-genres/health/recent/CSV export) plus an
accompanying page-shell route, none state-changing -- so every route
gets the same require_authentication tier, no require_admin split
needed. Matches maintenance.py's (#413) precedent for gating a page-shell
route with the same Depends(require_authentication) mechanism as API
routes.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.personal_insights import page_router, router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "personal_insights.py"
)

EXPECTED_ROUTES = {
    "get_summary",
    "get_collection_stats",
    "get_top_artists_list",
    "get_top_genres_list",
    "get_health",
    "get_recent",
    "export_csv",
    "analytics_page",
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


class TestPersonalInsightsAllRoutesRequireAuth:
    def test_every_route_requires_authentication(self):
        for function_name in EXPECTED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_all_routes_are_covered_by_this_mapping(self):
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        route_function_names |= {
            route.endpoint.__name__ for route in page_router.routes
        }
        assert route_function_names == EXPECTED_ROUTES


class TestPersonalInsightsBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        app.include_router(page_router)
        return TestClient(app)

    def test_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/analytics/summary")
        assert response.status_code == 401

    def test_route_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.get("/api/analytics/summary")
        assert response.status_code != 401
