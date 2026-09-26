"""
Regression tests for the IMVDb removal from src/api/fastapi/wizard.py
(Phase 2 of the IMVDb removal plan, GitHub issue #525) -- a previously
unscoped file found via a fresh grep audit during #525 execution.

POST /api/wizard/test-api used to let the installation wizard test an
IMVDb API key (imvdb_service.test_api_key()) alongside YouTube cookies.
Per the full-removal decision for IMVDb, that option is dropped: "imvdb"
is no longer a valid api_type, and the wizard's status endpoint no longer
pre-populates an IMVDB_API_KEY from the environment.
"""

from unittest.mock import MagicMock

import pytest

from src.api.fastapi.wizard import APITestRequest
from src.api.fastapi.wizard import test_api as wizard_test_api


class TestApiTestRequestNoLongerAcceptsImvdb:
    def test_imvdb_is_rejected_as_an_api_type(self):
        with pytest.raises(ValueError):
            APITestRequest(api_type="imvdb", api_key="fake-key")

    def test_youtube_is_still_accepted(self):
        request = APITestRequest(api_type="youtube", cookies_content="youtube.com=1")
        assert request.api_type == "youtube"


class TestTestApiEndpointHasNoImvdbBranch:
    @pytest.mark.asyncio
    async def test_unknown_api_type_falls_through_to_generic_error(self):
        # api_type validation now only allows "youtube" at the Pydantic
        # layer, but construct the request object directly (bypassing
        # validation) to prove the *handler* itself has no imvdb branch
        # left to fall into.
        request = MagicMock(api_type="imvdb", api_key="fake-key")

        result = await wizard_test_api(request, session=None, _wizard_gate=None)

        assert result.success is False
        assert "Unknown API type" in result.message
