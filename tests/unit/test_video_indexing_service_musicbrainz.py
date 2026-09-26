"""
Focused tests for VideoIndexingService's MusicBrainz official-video lookup.

Covers the IMVDb -> MusicBrainz migration of fetch_imvdb_metadata() and its
consumption in create_video_record() in src/services/video_indexing_service.py
(Phase 1 of the IMVDb removal plan, GitHub issue #524). The old IMVDb match
populated imvdb_id/year/directors/producers/thumbnail_url/raw_metadata;
MusicBrainzService.find_official_video() only yields a video URL, so this
step now sets youtube_id/youtube_url (and derives a YouTube thumbnail URL
from youtube_id), matching the precedent set in metadata_video_enricher.py.
"""

from unittest.mock import MagicMock, patch

from src.database.models import Video
from src.services.video_indexing_service import VideoIndexingService


class TestFetchImvdbMetadataMusicBrainzLookup:
    def test_musicbrainz_match_returns_youtube_fields(self):
        service = VideoIndexingService()
        match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }

        with patch(
            "src.services.video_indexing_service.musicbrainz_service.find_official_video",
            return_value=match,
        ) as mock_find:
            result = service.fetch_imvdb_metadata("Ghost", "Rats")

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert result == {
            "youtube_id": "abc123",
            "youtube_url": "https://www.youtube.com/watch?v=abc123",
            "title": "Rats",
            "musicbrainz_recording_id": "aaaa-bbbb",
        }

    def test_no_musicbrainz_match_returns_none(self):
        service = VideoIndexingService()

        with patch(
            "src.services.video_indexing_service.musicbrainz_service.find_official_video",
            return_value=None,
        ) as mock_find:
            result = service.fetch_imvdb_metadata("Ghost", "Unknown Song")

        mock_find.assert_called_once_with("Ghost", "Unknown Song")
        assert result is None


class TestCreateVideoRecordMusicBrainzMetadata:
    def _make_session(self):
        session = MagicMock()
        session.add.side_effect = lambda obj: None
        session.flush.side_effect = lambda: setattr(
            session.add.call_args[0][0], "id", 1
        )
        return session

    def test_sets_youtube_fields_and_downloads_thumbnail(self):
        service = VideoIndexingService()
        session = self._make_session()
        file_metadata = {
            "extracted_title": "Rats",
            "filename": "ghost_rats.mp4",
            "file_path": "/videos/ghost_rats.mp4",
        }
        video_match = {
            "youtube_id": "abc123",
            "youtube_url": "https://www.youtube.com/watch?v=abc123",
            "title": "Rats",
            "musicbrainz_recording_id": "aaaa-bbbb",
        }

        with patch(
            "src.services.video_indexing_service.thumbnail_service.download_video_thumbnail",
            return_value="/thumbnails/videos/ghost_rats.jpg",
        ) as mock_download:
            video = service.create_video_record(
                artist_id=1,
                artist_name="Ghost",
                file_metadata=file_metadata,
                imvdb_metadata=video_match,
                session=session,
            )

        assert video.youtube_id == "abc123"
        assert video.youtube_url == "https://www.youtube.com/watch?v=abc123"
        assert video.title == "Rats"
        assert video.thumbnail_path == "/thumbnails/videos/ghost_rats.jpg"
        mock_download.assert_called_once_with(
            "Ghost", "Rats", "https://img.youtube.com/vi/abc123/maxresdefault.jpg"
        )

    def test_no_metadata_leaves_youtube_fields_unset(self):
        service = VideoIndexingService()
        session = self._make_session()
        file_metadata = {
            "extracted_title": "Rats",
            "filename": "ghost_rats.mp4",
            "file_path": "/videos/ghost_rats.mp4",
        }

        with patch(
            "src.services.video_indexing_service.thumbnail_service.download_video_thumbnail",
        ) as mock_download:
            video = service.create_video_record(
                artist_id=1,
                artist_name="Ghost",
                file_metadata=file_metadata,
                imvdb_metadata=None,
                session=session,
            )

        assert video.youtube_id is None
        assert video.youtube_url is None
        mock_download.assert_not_called()
