"""Regression test for a residual auth gap in artists_crud.py (#392 Phase
2 follow-up). Every other route in this file already requires
authentication; get_search_suggestions (GET /search/suggestions) was the
one route missed -- same tier as its siblings, no admin split needed.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.artists_crud import router
from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "artists_crud.py"
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


class TestSearchSuggestionsRequiresAuth:
    def test_route_requires_authentication(self):
        source = _function_source("get_search_suggestions")
        assert "Depends(require_authentication)" in source

    def test_every_route_in_file_requires_authentication(self):
        # Guards against another route slipping through unnoticed.
        for route in router.routes:
            source = _function_source(route.endpoint.__name__)
            assert (
                "Depends(require_authentication)" in source
            ), f"{route.endpoint.__name__} is missing Depends(require_authentication)"


class TestSearchSuggestionsBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        # get_search_suggestions declares session: Depends(get_db_session)
        # ahead of the auth dependency; FastAPI resolves get_db_session
        # first, so without a real db_manager its own RuntimeError would
        # mask the 401 under test. Matches real production behavior,
        # where db_manager is always initialized before any request is
        # served.
        app.dependency_overrides[get_db_session] = lambda: iter([MagicMock()])
        return TestClient(app)

    def test_route_401s_without_session(self):
        client = self._client()
        response = client.get("/search/suggestions", params={"q": "test"})
        assert response.status_code == 401

    def test_route_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/search/suggestions", params={"q": "test"})
        assert response.status_code != 401
