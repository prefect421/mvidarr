"""Regression test for a live bug (2026-08-13): Wikipedia-sourced artist
thumbnails were found by search but always failed to download, silently
making #320's bulk/scan thumbnail features look like they found nothing.

Root cause: _enhance_thumbnail_url() rewrote every thumbnail URL's width
segment to a hardcoded "/800px-" via regex, regardless of whether
Wikimedia's thumb-serving proxy actually supports that width for the
specific source image. Wikimedia only serves a fixed set of valid widths
per image (confirmed live: requesting the real API-computed width, e.g.
960px, downloads fine with HTTP 200; the hardcoded 800px substitution
gets HTTP 400 "Use thumbnail sizes listed on...").

The correct way to request a larger thumbnail is via the API's own
pithumbsize parameter, which Wikipedia itself rounds to a size it can
actually generate — not by string-hacking the returned CDN URL
afterward.
"""

from unittest.mock import MagicMock, patch

from src.services.wikipedia_service import WikipediaService


class TestPageThumbnailDoesNotForceAnInvalidWidth:
    def test_returns_the_api_provided_url_unmodified(self):
        """The API-computed URL (whatever width Wikipedia decided to
        generate) must be returned as-is -- not string-hacked into a
        width Wikipedia never offered for this image."""
        service = WikipediaService()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {
                "pages": {
                    "123": {
                        "thumbnail": {
                            "source": (
                                "https://upload.wikimedia.org/wikipedia/commons/thumb/"
                                "d/d8/Linkin_Park.jpg/960px-Linkin_Park.jpg"
                                "?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail"
                            )
                        }
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.session, "get", return_value=mock_response):
            url = service._get_page_thumbnail("Linkin Park")

        assert "/960px-" in url
        assert "/800px-" not in url

    def test_requests_the_desired_size_via_the_api_parameter_not_url_rewriting(self):
        service = WikipediaService()

        mock_response = MagicMock()
        mock_response.json.return_value = {"query": {"pages": {}}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            service.session, "get", return_value=mock_response
        ) as mock_get:
            service._get_page_thumbnail("Linkin Park")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["pithumbsize"] >= 500

    def test_a_500px_source_url_is_also_returned_unmodified(self):
        """A smaller image than the requested pithumbsize is a normal,
        valid Wikipedia response (not every image has a large source) --
        must not be rewritten either."""
        service = WikipediaService()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {
                "pages": {
                    "123": {
                        "thumbnail": {
                            "source": (
                                "https://upload.wikimedia.org/wikipedia/commons/thumb/"
                                "a/b/Some_Band.jpg/500px-Some_Band.jpg"
                            )
                        }
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.session, "get", return_value=mock_response):
            url = service._get_page_thumbnail("Some Band")

        assert "/500px-" in url
