"""Tests wiring SimpleAuthService.is_default_password() into the template
context AsyncTemplateSystem._get_auth_context builds for every page render
-- this is what drives the default-password warning banner in base.html.
"""

from unittest.mock import patch

import pytest
from starlette.requests import Request

from src.api.fastapi.template_system import AsyncTemplateSystem

IS_DEFAULT_PASSWORD = (
    "src.services.simple_auth_service.SimpleAuthService.is_default_password"
)


def _make_request(path="/"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"host", b"localhost")],
        "query_string": b"",
        "server": ("localhost", 5000),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "app": None,
    }
    return Request(scope)


@pytest.fixture
def template_system():
    return AsyncTemplateSystem()


class TestDefaultPasswordActiveInAuthContext:
    @pytest.mark.asyncio
    async def test_flag_is_true_when_default_password_still_set(self, template_system):
        request = _make_request()
        with patch(IS_DEFAULT_PASSWORD, return_value=True):
            context = await template_system._get_auth_context(request)
        assert context["default_password_active"] is True

    @pytest.mark.asyncio
    async def test_flag_is_false_once_password_changed(self, template_system):
        request = _make_request()
        with patch(IS_DEFAULT_PASSWORD, return_value=False):
            context = await template_system._get_auth_context(request)
        assert context["default_password_active"] is False

    @pytest.mark.asyncio
    async def test_lookup_error_does_not_break_page_rendering(self, template_system):
        # _get_auth_context must never raise -- every authenticated page
        # renders through this method. A broken settings lookup should
        # degrade to "no warning shown", not a 500 on every page.
        request = _make_request()
        with patch(IS_DEFAULT_PASSWORD, side_effect=RuntimeError("db down")):
            context = await template_system._get_auth_context(request)
        assert context["default_password_active"] is False
        assert "current_user" in context
