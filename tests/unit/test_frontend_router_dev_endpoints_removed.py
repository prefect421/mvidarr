"""Tests proving frontend_router.py's two leftover debug endpoints are
gone. /dev/template-info dumped internal Jinja2 template engine state;
/dev/context-preview dumped the full per-request template context (which
may include session/user data). No legitimate ongoing production use;
removed entirely rather than gated.
"""

from pathlib import Path

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
