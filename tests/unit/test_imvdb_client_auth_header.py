"""Live-reported (#520): after entering a valid IMVDb API key, every
request fails with

    IMVDb API access forbidden for search/videos. Your API key may
    lack permissions for this endpoint.

Root cause: IMVDbClient sends the key as `Authorization: Bearer
<key>`. IMVDb's API does not use Bearer auth at all -- per
https://imvdb.com/developers/api the key must be sent in an
`IMVDB-APP-KEY` header (query-string `key=` is also legal). Any
request missing that header is unconditionally rejected with 403,
regardless of how valid the key is -- exactly the symptom reported.

Fix: send the key via the `IMVDB-APP-KEY` header instead of
`Authorization: Bearer`.
"""

from unittest.mock import MagicMock, patch

from src.services.imvdb.imvdb_client import IMVDbClient


class TestIMVDbClientAuthHeader:
    def test_make_request_sends_imvdb_app_key_header(self):
        client = IMVDbClient()
        client._api_key = "my-test-key"

        with patch(
            "src.services.imvdb.imvdb_client.requests.get"
        ) as mock_get, patch.object(
            IMVDbClient, "get_api_key", return_value="my-test-key"
        ):
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: {"results": []}
            )
            client._make_request("search/videos", {"q": "test"})

        _, kwargs = mock_get.call_args
        headers = kwargs["headers"]
        assert headers.get("IMVDB-APP-KEY") == "my-test-key"
        assert "Authorization" not in headers

    def test_test_api_key_sends_imvdb_app_key_header(self):
        client = IMVDbClient()

        with patch("src.services.imvdb.imvdb_client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: {"results": []}
            )
            client.test_api_key("another-test-key")

        _, kwargs = mock_get.call_args
        headers = kwargs["headers"]
        assert headers.get("IMVDB-APP-KEY") == "another-test-key"
        assert "Authorization" not in headers
