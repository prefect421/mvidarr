"""Confirms FastAPITemplateRoutes.login() passes real OAuth providers into
the render context — previously never set, so the login template's OAuth
button section could never appear regardless of configuration (#312).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.api.fastapi.template_system import FastAPITemplateRoutes


@pytest.mark.asyncio
async def test_login_context_includes_configured_oauth_providers():
    fake_template_system = AsyncMock()
    fake_template_system.render_response = AsyncMock(return_value="rendered")
    routes = FastAPITemplateRoutes(fake_template_system)

    with patch(
        "src.services.oauth_service.oauth_service.get_available_providers",
        return_value={"authentik": "Authentik", "google": "Google"},
    ):
        await routes.login(request=None)

    context = fake_template_system.render_response.call_args[0][2]
    assert context["oauth_providers"] == {"authentik": "Authentik", "google": "Google"}
