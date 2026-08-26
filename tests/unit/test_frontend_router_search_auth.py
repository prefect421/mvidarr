"""Tests for frontend_router.py's GET /api/search auth fix. This proxies
to the real search_all(q) service and returns live library search
results, unauthenticated. Uses auth_dependencies.require_authentication
(the JSON-API-style 401 variant), not template_system's redirect-style
(302) require_authentication already used elsewhere in this file for HTML
pages -- a 302 to a fetch() call would be followed transparently and
return the login page's HTML where JSON was expected.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "frontend_router.py"
)


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


class TestFrontendSearchUsesApiStyleAuth:
    def test_search_uses_the_401_variant_not_the_302_redirect_variant(self):
        source = _function_source("frontend_search")
        assert "require_api_authentication" in source

    def test_frontend_router_imports_the_aliased_api_dependency(self):
        source = SOURCE_PATH.read_text()
        assert (
            "from src.api.fastapi.auth_dependencies import" in source
            and "require_authentication as require_api_authentication" in source
        )


class TestFrontendSearchBehavioralAuth:
    def test_search_401s_without_session(self):
        from src.api.fastapi.frontend_router import frontend_router

        app = FastAPI()
        app.include_router(frontend_router)
        client = TestClient(app, follow_redirects=False)
        response = client.get("/api/search", params={"q": "test"})
        assert response.status_code == 401
