"""
Focused tests for the IMVDb -> MusicBrainz migration of
src/api/fastapi/video_indexing.py (Phase 2 of the IMVDb removal plan,
GitHub issue #525).

GET /imvdb/test (the endpoint #520 was originally filed against) is
deleted entirely per the plan, not just fixed.

search_metadata() (POST /metadata/search): the specific artist+title
branch migrates to MusicBrainzService.find_official_video(); the bulk
artist-only branch has no MusicBrainz equivalent (find_official_video()
needs a known track name) and now returns an empty list, same gap already
found at other bulk-discovery call sites in #524/#525.
"""

from unittest.mock import patch

import pytest

from src.api.fastapi.video_indexing import (
    MetadataSearchRequest,
    router,
    search_metadata,
)


class TestImvdbTestConnectionRouteRemoved:
    def test_no_imvdb_test_route_remains(self):
        paths = {route.path for route in router.routes}
        assert "/api/video-indexing/imvdb/test" not in paths


class TestSearchMetadataMusicBrainzLookup:
    @pytest.mark.asyncio
    async def test_specific_title_uses_musicbrainz_match(self):
        video_match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
        }

        with patch(
            "src.api.fastapi.video_indexing.musicbrainz_service.find_official_video",
            return_value=video_match,
        ) as mock_find:
            result = await search_metadata(
                MetadataSearchRequest(artist="Ghost", title="Rats"),
                current_user={"user_id": 1, "username": "tester"},
                session=None,
            )

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert result.success is True
        assert (
            result.metadata["youtube_url"] == "https://www.youtube.com/watch?v=abc123"
        )

    @pytest.mark.asyncio
    async def test_specific_title_no_match_returns_failure(self):
        with patch(
            "src.api.fastapi.video_indexing.musicbrainz_service.find_official_video",
            return_value=None,
        ):
            result = await search_metadata(
                MetadataSearchRequest(artist="Ghost", title="Unknown Song"),
                current_user={"user_id": 1, "username": "tester"},
                session=None,
            )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_artist_only_search_returns_empty(self):
        result = await search_metadata(
            MetadataSearchRequest(artist="Ghost", title=None),
            current_user={"user_id": 1, "username": "tester"},
            session=None,
        )

        assert result.success is True
        assert result.videos == []
        assert result.count == 0
