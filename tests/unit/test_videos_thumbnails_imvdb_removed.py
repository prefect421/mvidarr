"""
Regression test for the IMVDb removal from
src/api/fastapi/videos_thumbnails.py's search_thumbnail() (Phase 2 of the
IMVDb removal plan, GitHub issue #525) -- a previously unscoped file
found via a fresh grep audit during #525 execution.

The IMVDb thumbnail branch called imvdb_service.get_video_by_id() /
find_best_video_match() / extract_metadata() to pull a thumbnail URL --
no MusicBrainz equivalent exists (MusicBrainz doesn't provide thumbnails
at all, an established fact from #524's other migrations). Removed
outright; YouTube and Google Images thumbnails remain.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.api.fastapi.videos_models import ThumbnailSearchRequest
from src.api.fastapi.videos_thumbnails import search_thumbnail


def _make_session(video):
    session = MagicMock()
    session.query.return_value.options.return_value.filter.return_value.first.return_value = (
        video
    )
    return session


class TestSearchThumbnailImvdbRemoved:
    @pytest.mark.asyncio
    async def test_no_imvdb_source_in_results(self):
        artist = SimpleNamespace(name="Ghost")
        video = SimpleNamespace(
            id=1,
            title="Rats",
            url=None,
            imvdb_id="imvdb999",
            artist=artist,
        )
        session = _make_session(video)

        with patch(
            "src.api.fastapi.videos_thumbnails.youtube_service.search_videos",
            return_value={"success": False, "results": []},
        ), patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, text="")

            result = await search_thumbnail(
                video_id=1,
                search_request=ThumbnailSearchRequest(),
                current_user={"user_id": 1},
                session=session,
            )

        sources = {r["source"] for r in result["results"]}
        assert "imvdb" not in sources
