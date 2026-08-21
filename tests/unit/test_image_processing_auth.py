"""Tests for image_processing.py's auth fix (#392 Phase 2). All 8 routes
had zero authentication -- including endpoints that accept arbitrary
filesystem paths (source_paths, output_dir) and write or delete files at
them, the same risk class fixed for bulk_operations.py in #408.
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
from src.api.fastapi.image_processing import router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "image_processing.py"
)

# function_name -> "admin" | "auth"
EXPECTED_TIER = {
    "generate_thumbnails": "admin",
    "optimize_images": "admin",
    "analyze_images": "admin",
    "get_processing_stats": "auth",
    "get_thumbnail_presets": "auth",
    "generate_preset_thumbnails": "admin",
    "clear_thumbnail_cache": "admin",
    "get_cache_stats": "auth",
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


class TestImageProcessingAllRoutesHaveCorrectTier:
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

    def test_all_routes_are_covered_by_this_mapping(self):
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        assert route_function_names == set(EXPECTED_TIER.keys())


class TestImageProcessingBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/image-processing/presets")
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.delete(
            "/api/image-processing/cache/thumbnails?output_dir=/tmp"
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
        response = client.delete(
            "/api/image-processing/cache/thumbnails?output_dir=/tmp"
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
        response = client.delete(
            "/api/image-processing/cache/thumbnails?output_dir=/tmp"
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
        response = client.get("/api/image-processing/presets")
        assert response.status_code != 401
