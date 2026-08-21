"""Tests for bulk_operations.py's auth fix (#392 Phase 2). All 9 REST
routes had zero authentication -- including endpoints that accept
arbitrary filesystem paths (media_paths, source_directory,
target_directory) and destructive cleanup_rules, letting an
unauthenticated caller scan, import, or clean up directories anywhere
readable by the app process.

The 10th route on this router, the WebSocket progress endpoint
(/progress/{operation_id}), is intentionally NOT covered here.
WebSocket routes use different dependency-injection machinery than
regular HTTP routes -- require_authentication ultimately depends on
`Request`-typed cookie access, and FastAPI's WebSocket routes provide
a `WebSocket`-typed scope instead, so the same Depends(...) pattern
used on every other route in this sweep isn't guaranteed to resolve
correctly there without dedicated testing this sweep doesn't have
time for right now. Its risk is materially lower than the 9 REST
routes fixed here: it can only observe progress for an operation_id
that must already be known (a UUID, not enumerable), not start or
control any operation.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_admin,
    require_authentication,
)
from src.api.fastapi.bulk_operations import router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "bulk_operations.py"
)

# function_name -> "admin" | "auth"
EXPECTED_TIER = {
    "enrich_metadata_bulk": "admin",
    "import_collection": "admin",
    "cleanup_collection": "admin",
    "get_operation_status": "auth",
    "cancel_operation": "admin",
    "get_active_operations": "auth",
    "create_collection": "admin",
    "get_collection_statistics": "auth",
    "get_system_statistics": "auth",
    "cleanup_operation": "admin",
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


class TestBulkOperationsAllRestRoutesHaveCorrectTier:
    def test_every_route_has_the_expected_dependency(self):
        for function_name, tier in EXPECTED_TIER.items():
            source = _function_source(function_name)
            expected = (
                "Depends(require_admin)"
                if tier == "admin"
                else "Depends(require_authentication)"
            )
            assert (
                expected in source
            ), f"{function_name} should use {expected}, got:\n{source}"

    def test_all_rest_routes_are_covered_by_this_mapping(self):
        # The websocket route (websocket_progress_updates) is
        # deliberately excluded -- see module docstring.
        rest_route_names = {
            route.endpoint.__name__
            for route in router.routes
            if hasattr(route, "methods")  # excludes the WebSocketRoute
        }
        assert rest_route_names == set(EXPECTED_TIER.keys())


class TestBulkOperationsBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get(
            "/api/bulk-operations/collections/somecollection/statistics"
        )
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.post(
            "/api/bulk-operations/collections/cleanup",
            json={
                "collection_id": "x",
                "target_directory": "/tmp",
                "cleanup_rules": {},
            },
        )
        assert response.status_code == 401

    def test_admin_tier_route_403s_for_non_admin_authenticated_user(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: {
            "authenticated": True,
            "role": "user",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.post(
            "/api/bulk-operations/collections/cleanup",
            json={
                "collection_id": "x",
                "target_directory": "/tmp",
                "cleanup_rules": {},
            },
        )
        assert response.status_code == 403

    def test_admin_tier_route_succeeds_for_admin_session(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        client = TestClient(app)
        response = client.post(
            "/api/bulk-operations/collections/cleanup",
            json={
                "collection_id": "x",
                "target_directory": "/tmp",
                "cleanup_rules": {},
            },
        )
        assert response.status_code != 401
        assert response.status_code != 403

    def test_authenticated_tier_route_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.get(
            "/api/bulk-operations/collections/somecollection/statistics"
        )
        assert response.status_code != 401
