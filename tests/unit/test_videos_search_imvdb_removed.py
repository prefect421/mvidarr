"""
Regression test for the IMVDb removal from
src/api/fastapi/videos_search.py's universal_search() (Phase 2 of the
IMVDb removal plan, GitHub issue #525).

The IMVDb half of this combined local/IMVDb/YouTube search was a
free-text bulk artist-video search with no MusicBrainz equivalent --
find_official_video() needs a known artist+track pair, not a free-text
query -- same gap already found at other bulk-discovery call sites
throughout #524/#525. Removed outright; YouTube search remains.
"""

from unittest.mock import patch

import pytest

from src.api.fastapi.videos_search import universal_search


class TestUniversalSearchImvdbRemoved:
    @pytest.mark.asyncio
    async def test_no_imvdb_source_in_external_results(self):
        youtube_response = {
            "videos": [
                {
                    "youtube_id": "abc123",
                    "title": "Rats",
                    "channel_title": "Ghost",
                    "thumbnail_url": "https://img.example/abc123.jpg",
                }
            ]
        }

        with patch(
            "src.services.youtube_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_youtube.api_key = "fake-key"
            mock_youtube.search_artist_videos.return_value = youtube_response

            result = await universal_search(
                q="ghost",
                extended=True,
                current_user={"user_id": 1},
                session=None,
            )

        sources = {r.get("source") for r in result["external"]}
        assert "IMVDb" not in sources
        assert "YouTube" in sources
