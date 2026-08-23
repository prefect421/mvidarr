"""Tests for video_quality.py's auth fix (#392 Phase 2). 3 of this
router's 6 routes already had require_authentication (upgrade_video_quality,
analyze_video_quality, bulk_upgrade_videos). The other 3
(find_upgradeable_videos, get_quality_preferences, get_quality_statistics)
had zero authentication -- all read-only library/settings data, same tier
as their already-protected siblings, so they get require_authentication
too with no admin split.
"""

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.video_quality import router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "video_quality.py"
)

ALREADY_PROTECTED_ROUTES = {
    "upgrade_video_quality",
    "analyze_video_quality",
    "bulk_upgrade_videos",
}

NEWLY_GATED_ROUTES = {
    "find_upgradeable_videos",
    "get_quality_preferences",
    "get_quality_statistics",
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


class TestVideoQualityAllRoutesRequireAuth:
    def test_every_route_requires_authentication(self):
        for function_name in ALREADY_PROTECTED_ROUTES | NEWLY_GATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_all_routes_are_covered_by_this_mapping(self):
        route_function_names = {route.endpoint.__name__ for route in router.routes}
        assert route_function_names == (ALREADY_PROTECTED_ROUTES | NEWLY_GATED_ROUTES)


class TestVideoQualityBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_newly_gated_route_401s_without_session(self):
        client = self._client()
        response = client.get("/api/video-quality/statistics")
        assert response.status_code == 401

    def test_newly_gated_route_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/api/video-quality/statistics")
        assert response.status_code != 401
