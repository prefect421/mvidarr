"""
Focused tests for import_videos()'s MusicBrainz URL-lookup fallback.

Covers the IMVDb -> MusicBrainz migration of the "no URL found, try to
find one before rejecting the video" path in src/services/import_operations.py
(Task 1a of the IMVDb removal plan, GitHub issue #524).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.database.import_export_models import (
    ImportMode,
    ImportOptions,
    ProcessingProgress,
)
from src.database.models import Artist, Video
from src.services.import_operations import import_videos


def _make_progress() -> ProcessingProgress:
    return ProcessingProgress(
        current_phase="processing",
        total_phases=1,
        current_phase_progress=0.0,
        overall_progress=0.0,
        records_processed=0,
        total_records=1,
        records_per_second=0.0,
    )


def _make_db(artist_name="Ghost", artist_id=42):
    """A MagicMock Session that finds no existing video and one existing artist."""
    db = MagicMock()
    artist = SimpleNamespace(id=artist_id, name=artist_name)

    def fake_query(model):
        query_mock = MagicMock()
        if model is Video:
            query_mock.filter.return_value.first.return_value = None
        elif model is Artist:
            query_mock.filter.return_value.first.return_value = artist
        return query_mock

    db.query.side_effect = fake_query
    return db


class TestImportVideosMusicBrainzFallback:
    def test_urlless_video_resolved_via_musicbrainz(self):
        video_data = SimpleNamespace(
            id=1,
            artist_id=42,
            title="Rats",
            imvdb_id=None,
            imvdb_metadata=None,
            youtube_id=None,
            youtube_url=None,
            url=None,
            playlist_id=None,
            thumbnail_url=None,
            duration=None,
            year=None,
            release_date=None,
            description=None,
            view_count=None,
            like_count=None,
            genres=None,
            directors=None,
            producers=None,
            status="WANTED",
            quality=None,
            video_metadata=None,
            ffmpeg_extracted=False,
            width=None,
            height=None,
            video_codec=None,
            audio_codec=None,
            fps=None,
            bitrate=None,
            local_path=None,
        )

        db = _make_db()
        import_options = ImportOptions(
            mode=ImportMode.MERGE_UPDATE, create_missing_artists=True
        )
        progress = _make_progress()

        match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }

        with patch(
            "src.services.import_operations.musicbrainz_service.find_official_video",
            return_value=match,
        ) as mock_find:
            results = import_videos(
                db, [video_data], import_options, progress, lambda p: None
            )

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert results == {
            "videos_imported": 1,
            "videos_updated": 0,
            "videos_skipped": 0,
        }
        assert video_data.url == "https://www.youtube.com/watch?v=abc123"
        assert video_data.youtube_url == "https://www.youtube.com/watch?v=abc123"
        assert video_data.youtube_id == "abc123"
        # MusicBrainz has no metadata equivalent for IMVDb's id/metadata fields
        assert video_data.imvdb_id is None
        assert video_data.imvdb_metadata is None

        db.add.assert_called_once()
        added_video = db.add.call_args[0][0]
        assert added_video.url == "https://www.youtube.com/watch?v=abc123"

    def test_urlless_video_skipped_when_musicbrainz_finds_nothing(self):
        video_data = SimpleNamespace(
            id=2,
            artist_id=42,
            title="No Match Here",
            imvdb_id=None,
            imvdb_metadata=None,
            youtube_id=None,
            youtube_url=None,
            url=None,
            playlist_id=None,
            thumbnail_url=None,
            duration=None,
            year=None,
            release_date=None,
            description=None,
            view_count=None,
            like_count=None,
            genres=None,
            directors=None,
            producers=None,
            status="WANTED",
            quality=None,
            video_metadata=None,
            ffmpeg_extracted=False,
            width=None,
            height=None,
            video_codec=None,
            audio_codec=None,
            fps=None,
            bitrate=None,
            local_path=None,
        )

        db = _make_db()
        import_options = ImportOptions(
            mode=ImportMode.MERGE_UPDATE, create_missing_artists=True
        )
        progress = _make_progress()

        with patch(
            "src.services.import_operations.musicbrainz_service.find_official_video",
            return_value=None,
        ):
            results = import_videos(
                db, [video_data], import_options, progress, lambda p: None
            )

        assert results == {
            "videos_imported": 0,
            "videos_updated": 0,
            "videos_skipped": 1,
        }
        db.add.assert_not_called()
