"""Confirms FastAPITemplateRoutes.login() passes a random bg_index (1-8)
into the render context, driving the paired background-photo/logo-image
rotation added for #351 (frontend/static/music/BG/bg{N}.jpg and
frontend/static/music/Logo/{N}.png, N sharing the same value so the two
stay paired as originally uploaded).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.api.fastapi.template_system import FastAPITemplateRoutes


@pytest.mark.asyncio
async def test_login_context_includes_a_bg_index_in_range():
    fake_template_system = AsyncMock()
    fake_template_system.render_response = AsyncMock(return_value="rendered")
    routes = FastAPITemplateRoutes(fake_template_system)

    with patch(
        "src.services.oauth_service.oauth_service.get_available_providers",
        return_value={},
    ):
        await routes.login(request=None)

    context = fake_template_system.render_response.call_args[0][2]
    assert "bg_index" in context
    assert isinstance(context["bg_index"], int)
    assert 1 <= context["bg_index"] <= 8


@pytest.mark.asyncio
async def test_login_context_bg_index_uses_random_randint_1_to_8():
    """Pins the exact call shape (not just the output range) so a future
    refactor that swaps in e.g. random.choice(range(0, 8)) -- silently
    shifting the valid image-file numbering off by one -- fails loudly."""
    fake_template_system = AsyncMock()
    fake_template_system.render_response = AsyncMock(return_value="rendered")
    routes = FastAPITemplateRoutes(fake_template_system)

    with patch(
        "src.services.oauth_service.oauth_service.get_available_providers",
        return_value={},
    ), patch(
        "src.api.fastapi.template_system.random.randint", return_value=5
    ) as mock_randint:
        await routes.login(request=None)

    mock_randint.assert_called_once_with(1, 8)
    context = fake_template_system.render_response.call_args[0][2]
    assert context["bg_index"] == 5
