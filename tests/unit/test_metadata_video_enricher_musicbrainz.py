"""
Focused tests for enrich_video_metadata()'s MusicBrainz official-video lookup.

Covers the IMVDb -> MusicBrainz migration of the video-match enrichment step
in src/services/metadata_video_enricher.py (Task 1a of the IMVDb removal
plan, GitHub issue #524). The old IMVDb step populated year/directors/
producers/thumbnail from a video match; MusicBrainz's find_official_video()
only yields a video URL, so this step now sets youtube_id/youtube_url and
lets the existing YouTube-thumbnail step (7) and Discogs/MusicBrainz
release-date steps (2-3) fill in the rest.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.metadata_video_enricher import enrich_video_metadata


def _make_video():
    artist = SimpleNamespace(
        name="Ghost", spotify_id=None, lastfm_name=None, genres=None
    )
    return SimpleNamespace(
        id=1,
        artist=artist,
        title="Rats",
        youtube_id=None,
        youtube_url=None,
        year=None,
        directors=None,
        producers=None,
        thumbnail_url=None,
        thumbnail_source=None,
        album=None,
        release_date=None,
        genres=None,
        video_metadata=None,
        duration=None,
        local_path=None,
        lyrics=None,
        last_enriched=None,
        quality=None,
    )


def _make_db(video):
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = (
        video
    )
    db.merge.side_effect = lambda v: v
    return db


@pytest.mark.asyncio
class TestEnrichVideoMetadataMusicBrainzVideoLookup:
    async def test_musicbrainz_match_sets_youtube_id_and_skips_heuristic_search(self):
        video = _make_video()
        db = _make_db(video)
        match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }
        youtube_search_service = MagicMock()

        with patch(
            "src.services.metadata_video_enricher.get_db",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=db),
                __exit__=MagicMock(return_value=False),
            ),
        ), patch(
            "src.services.metadata_video_enricher.musicbrainz_service.find_official_video",
            return_value=match,
        ) as mock_find, patch(
            "src.services.metadata_video_enricher.discogs_service.get_track_release_date",
            return_value=None,
        ), patch(
            "src.services.metadata_video_enricher.musicbrainz_service.get_recording_release_date",
            return_value=None,
        ), patch(
            "src.services.metadata_video_enricher.search_lyrics_azlyrics",
            return_value=None,
        ), patch(
            "src.services.metadata_video_enricher.requests.head",
            return_value=MagicMock(status_code=404),
        ):
            result = await enrich_video_metadata(1, youtube_search_service)

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert video.youtube_id == "abc123"
        assert video.youtube_url == "https://www.youtube.com/watch?v=abc123"
        assert "youtube_id" in result.enriched_fields
        assert "musicbrainz_video" in result.sources_used
        youtube_search_service.search_video_by_title.assert_not_called()

    async def test_no_musicbrainz_match_falls_back_to_heuristic_search(self):
        video = _make_video()
        db = _make_db(video)
        youtube_search_service = MagicMock()
        youtube_search_service.search_video_by_title.return_value = None

        with patch(
            "src.services.metadata_video_enricher.get_db",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=db),
                __exit__=MagicMock(return_value=False),
            ),
        ), patch(
            "src.services.metadata_video_enricher.musicbrainz_service.find_official_video",
            return_value=None,
        ) as mock_find, patch(
            "src.services.metadata_video_enricher.discogs_service.get_track_release_date",
            return_value=None,
        ), patch(
            "src.services.metadata_video_enricher.musicbrainz_service.get_recording_release_date",
            return_value=None,
        ), patch(
            "src.services.metadata_video_enricher.search_lyrics_azlyrics",
            return_value=None,
        ), patch(
            "src.services.metadata_video_enricher.requests.head",
            return_value=MagicMock(status_code=404),
        ):
            result = await enrich_video_metadata(1, youtube_search_service)

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert video.youtube_id is None
        assert "musicbrainz_video" not in result.sources_used
        youtube_search_service.search_video_by_title.assert_called_once_with(
            "Rats", "Ghost", limit=5
        )
