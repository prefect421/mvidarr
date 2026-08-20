"""Tests proving frontend_router.py's two leftover debug endpoints are
gone. /dev/template-info dumped internal Jinja2 template engine state;
/dev/context-preview dumped the full per-request template context (which
may include session/user data). No legitimate ongoing production use;
removed entirely rather than gated.
"""

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


class TestDevEndpointsRemoved:
    def test_template_info_route_gone(self):
        source = SOURCE_PATH.read_text()
        assert "/dev/template-info" not in source
        assert "template_development_info" not in source

    def test_context_preview_route_gone(self):
        source = SOURCE_PATH.read_text()
        assert "/dev/context-preview" not in source
        assert "template_context_preview" not in source


class TestDevEndpointsActuallyReturn404:
    """Source-string assertions above prove the route registrations were
    deleted, but not that the routes are actually unreachable -- a route
    registered elsewhere (or under a different decorator form the string
    check missed) could still resolve. Confirm behaviorally via a real
    TestClient request.
    """

    def _client(self):
        from src.api.fastapi.frontend_router import frontend_router

        app = FastAPI()
        app.include_router(frontend_router)
        return TestClient(app)

    def test_template_info_returns_404(self):
        client = self._client()
        response = client.get("/dev/template-info")
        assert response.status_code == 404

    def test_context_preview_returns_404(self):
        client = self._client()
        response = client.get("/dev/context-preview")
        assert response.status_code == 404
