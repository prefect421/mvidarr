"""Tests for mobile_access.py's auth fix. 12 of 13 routes were
unauthenticated -- most handlers are inert stubs (hardcoded sample data),
but POST /register-device is real: it calls
network_share.set_device_access_level(...), genuinely granting network
streaming access to the caller's IP. All non-stub AND stub routes get
require_authentication uniformly (cheap now, prevents a repeat of this bug
class if a stub gets filled in later without anyone re-checking auth) --
EXCEPT GET /manifest.json, deliberately left public (PWA manifest,
no sensitive data, commonly fetched without credentials by browsers).
"""

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# mobile_access.py imports src.services.local_network_share, which does a
# module-level `import netifaces`. netifaces isn't installed in the test
# venv (it's a real runtime dependency, just not present here), so a direct
# import of mobile_access raises ModuleNotFoundError at import time. Shim it
# out before importing -- this only affects import-time module resolution,
# not any behavior under test.
sys.modules.setdefault("netifaces", MagicMock())

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.mobile_access import mobile_router

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "mobile_access.py"
)

EXPECTED_AUTHENTICATED_ROUTES = [
    "mobile_discover_server",
    "get_mobile_server_status",
    "get_mobile_collections",
    "get_mobile_collection_videos",
    "mobile_search_videos",
    "stream_video_mobile",
    "get_mobile_thumbnail",
    "download_video_mobile",
    "get_mobile_playlists",
    "get_mobile_playlist_videos",
    "get_mobile_app_interface",
    "register_mobile_device",
]


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


class TestMobileAccessAllRoutesAuthenticated:
    def test_every_route_requires_authentication(self):
        for function_name in EXPECTED_AUTHENTICATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_manifest_route_deliberately_left_unauthenticated(self):
        source = _function_source("get_mobile_app_manifest")
        assert "Depends(require_authentication)" not in source


class TestMobileAccessBehavioralAuth:
    def test_register_device_401s_without_session(self):
        app = FastAPI()
        app.include_router(mobile_router)
        client = TestClient(app)
        response = client.post("/mobile/register-device", json={"device_name": "x"})
        assert response.status_code == 401

    def test_manifest_succeeds_without_session(self):
        app = FastAPI()
        app.include_router(mobile_router)
        client = TestClient(app)
        response = client.get("/mobile/manifest.json")
        assert response.status_code != 401

    def test_register_device_succeeds_for_authenticated_session(self):
        app = FastAPI()
        app.include_router(mobile_router)
        app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        client = TestClient(app)
        response = client.post("/mobile/register-device", json={"device_name": "x"})
        assert response.status_code != 401
