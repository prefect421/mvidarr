"""Regression/feature test for #315: the webhooks management page
(frontend/templates/webhooks.html) exists and its API router
(src/api/fastapi/webhooks.py) is mounted, but no page route has ever
pointed at it -- confirmed via grep, zero hits for "webhooks" in
frontend_router.py before this change. GET /webhooks 404s today.

Matches the exact pattern every other authenticated page route already
uses (e.g. lastfm_manager/lidarr_manager in frontend_router.py):
@frontend_router.get(...) -> template_routes.<method>(request) in a
try/except that logs and raises HTTPException(500) on failure.
"""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "api" / "fastapi"


class TestWebhooksPageRoute:
    def setup_method(self):
        self.frontend_router_source = (SRC_DIR / "frontend_router.py").read_text()
        self.template_system_source = (SRC_DIR / "template_system.py").read_text()

    def test_frontend_router_registers_a_webhooks_route(self):
        assert '@frontend_router.get("/webhooks"' in self.frontend_router_source

    def test_webhooks_route_requires_authentication(self):
        start = self.frontend_router_source.index('@frontend_router.get("/webhooks"')
        end = self.frontend_router_source.index("\n\n", start)
        route_block = self.frontend_router_source[start:end]
        assert "Depends(require_authentication)" in route_block

    def test_webhooks_route_calls_template_routes_webhooks(self):
        start = self.frontend_router_source.index('@frontend_router.get("/webhooks"')
        end = self.frontend_router_source.index("\n\n", start)
        route_block = self.frontend_router_source[start:end]
        assert "template_routes.webhooks(request)" in route_block

    def test_template_system_has_a_webhooks_method(self):
        assert "async def webhooks(self, request: Request)" in self.template_system_source

    def test_webhooks_method_renders_webhooks_html(self):
        start = self.template_system_source.index(
            "async def webhooks(self, request: Request)"
        )
        end = self.template_system_source.index("\n\n", start)
        method_block = self.template_system_source[start:end]
        assert '"webhooks.html"' in method_block
