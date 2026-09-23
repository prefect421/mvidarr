"""
Focused tests for CrossPlatformVideoIntelligence._search_musicbrainz.

Covers the IMVDb -> MusicBrainz migration of the IMVDb "platform" search slot
(Task 1a of the IMVDb removal plan, GitHub issue #524).
"""

from unittest.mock import patch

import pytest

from src.services.cross_platform_video_intelligence import (
    CrossPlatformVideoIntelligence,
    Platform,
)


@pytest.mark.asyncio
class TestSearchMusicBrainz:
    async def test_returns_single_item_list_on_match(self):
        service = CrossPlatformVideoIntelligence()
        match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }

        with patch(
            "src.services.cross_platform_video_intelligence.musicbrainz_service.find_official_video",
            return_value=match,
        ) as mock_find:
            results = await service._search_musicbrainz("Ghost", "Rats")

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert results == [
            {
                "title": "Rats",
                "artist": "Ghost",
                "url": "https://www.youtube.com/watch?v=abc123",
                "platform": Platform.IMVDB.value,
                "metadata_source": True,
                "relationship_type": "music video",
                "match_score": 100,
            }
        ]

    async def test_returns_empty_list_when_no_match(self):
        service = CrossPlatformVideoIntelligence()

        with patch(
            "src.services.cross_platform_video_intelligence.musicbrainz_service.find_official_video",
            return_value=None,
        ):
            results = await service._search_musicbrainz("Unknown Artist", "No Video")

        assert results == []

    async def test_returns_empty_list_on_exception(self):
        service = CrossPlatformVideoIntelligence()

        with patch(
            "src.services.cross_platform_video_intelligence.musicbrainz_service.find_official_video",
            side_effect=RuntimeError("boom"),
        ):
            results = await service._search_musicbrainz("Ghost", "Rats")

        assert results == []
