"""Tests for advanced_image_processing.py's auth fix (#392 Phase 2). All 6
routes had zero authentication -- including endpoints that accept
arbitrary filesystem paths (image_paths/source_paths) for analysis,
format conversion, and quality enhancement, the same risk class fixed for
bulk_operations.py (#408) and image_processing.py (#410).
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.advanced_image_processing import router
from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_admin,
    require_authentication,
)

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "advanced_image_processing.py"
)

# function_name -> "admin" | "auth"
EXPECTED_TIER = {
    "bulk_image_analysis": "admin",
    "convert_image_formats": "admin",
    "enhance_image_quality": "admin",
    "get_supported_formats": "auth",
    "get_enhancement_options": "auth",
    "analyze_image_quality_only": "admin",
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


class TestAdvancedImageProcessingAllRoutesHaveCorrectTier:
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


class TestAdvancedImageProcessingBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_authenticated_tier_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/advanced-image-processing/formats/supported")
        assert response.status_code == 401

    def test_admin_tier_route_401s_without_session(self):
        client = self._client()
        response = client.post(
            "/api/advanced-image-processing/analyze/bulk",
            json={"image_paths": ["/tmp/x.jpg"]},
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
            "/api/advanced-image-processing/analyze/bulk",
            json={"image_paths": ["/tmp/x.jpg"]},
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
            "/api/advanced-image-processing/analyze/bulk",
            json={"image_paths": ["/tmp/x.jpg"]},
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
        response = client.get("/api/advanced-image-processing/formats/supported")
        assert response.status_code != 401
