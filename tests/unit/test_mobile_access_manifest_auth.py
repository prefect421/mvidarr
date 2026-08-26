"""Regression test for a residual auth gap in mobile_access.py (#392
Phase 2 follow-up). Every real route in this file already requires
authentication (get_mobile_optimized_config is a plain helper function,
not a route -- it has no @mobile_router decorator and is only ever called
internally by other route handlers); get_mobile_app_manifest (GET
/mobile/manifest.json) was the one route missed.

The only page that links to this manifest is get_mobile_app_interface's
own HTML (<link rel="manifest" href="/mobile/manifest.json">), and that
page (GET /mobile/app) is itself already require_authentication-gated.
Browsers include same-origin cookies for <link rel="manifest"> fetches,
so gating the manifest itself doesn't break anything for an
already-logged-in user -- and there's no other, unauthenticated consumer
of this specific route (unlike frontend/templates/base.html's <link
rel="manifest">, which points at a static file, not this one). Same tier
as its siblings (require_authentication, no admin split).
"""

import ast
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# mobile_access.py imports local_network_share, which imports netifaces --
# a C extension not installable in this dev/test environment (no compiler
# toolchain available for it here). Shim both modules before importing the
# router; restored immediately after import so it doesn't leak into other
# test modules collected in the same pytest session.
_NETIFACES = "netifaces"
_LOCAL_NETWORK_SHARE = "src.services.local_network_share"
_already_imported = {
    name: name in sys.modules for name in (_NETIFACES, _LOCAL_NETWORK_SHARE)
}
if not _already_imported[_NETIFACES]:
    sys.modules[_NETIFACES] = MagicMock()
if not _already_imported[_LOCAL_NETWORK_SHARE]:
    _fake_local_network_share = types.ModuleType(_LOCAL_NETWORK_SHARE)
    _fake_local_network_share.get_local_network_share = MagicMock()
    sys.modules[_LOCAL_NETWORK_SHARE] = _fake_local_network_share

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.mobile_access import mobile_router

for _name, _was_imported in _already_imported.items():
    if not _was_imported:
        del sys.modules[_name]

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "mobile_access.py"
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


class TestMobileManifestRequiresAuth:
    def test_route_requires_authentication(self):
        source = _function_source("get_mobile_app_manifest")
        assert "Depends(require_authentication)" in source

    def test_every_route_in_file_requires_authentication(self):
        # Guards against another route slipping through unnoticed.
        for route in mobile_router.routes:
            source = _function_source(route.endpoint.__name__)
            assert (
                "Depends(require_authentication)" in source
            ), f"{route.endpoint.__name__} is missing Depends(require_authentication)"


class TestMobileManifestBehavioralAuth:
    def _client(self):
        app = FastAPI()
        app.include_router(mobile_router)
        return TestClient(app)

    def test_route_401s_without_session(self):
        client = self._client()
        response = client.get("/mobile/manifest.json")
        assert response.status_code == 401

    def test_route_succeeds_for_authenticated_session(self):
        client = self._client()
        client.app.dependency_overrides[require_authentication] = lambda: {
            "authenticated": True,
            "role": "user",
        }
        response = client.get("/mobile/manifest.json")
        assert response.status_code != 401
