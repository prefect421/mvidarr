"""Tests for genres.py's auth fix (#392 Phase 2). All 3 routes had zero
authentication. All are read-only genre-listing/stats endpoints (no
host/system data, no admin-only config) -- same tier as other regular
content-browsing endpoints across the app, so all 3 get
require_authentication with no admin split. simple_genres is a leftover
debug/smoke-test endpoint ("test if genres router works at all") but gets
the same treatment -- no reason to leave a live route unauthenticated just
because it started life as a debug probe.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.genres import router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "genres.py"
)

EXPECTED_ROUTES = {
    "get_all_genres",
    "simple_genres",
    "get_popular_genres",
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


class TestGenresAllRoutesRequireAuth:
    def test_every_route_requires_authentication(self):
        for function_name in EXPECTED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_all_routes_are_covered_by_this_mapping(self):
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        assert route_function_names == EXPECTED_ROUTES


class TestGenresBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/genres/simple")
        assert response.status_code == 401

    def test_route_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.get("/api/genres/simple")
        assert response.status_code != 401
