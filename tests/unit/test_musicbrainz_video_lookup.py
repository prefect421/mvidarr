from unittest.mock import patch

from src.services.musicbrainz_service import MusicBrainzService


class TestFindOfficialVideo:
    def test_finds_video_via_music_video_relationship(self):
        service = MusicBrainzService()
        search_response = {
            "recordings": [
                {
                    "id": "aaaa-bbbb",
                    "title": "Rats",
                    "score": 100,
                    "relations": [
                        {
                            "type": "music video",
                            "target-type": "recording",
                            "recording": {"id": "video-recording-id"},
                        }
                    ],
                }
            ]
        }
        video_recording_response = {
            "id": "video-recording-id",
            "relations": [
                {
                    "type": "free streaming",
                    "attributes": ["video"],
                    "url": {"resource": "https://www.youtube.com/watch?v=abc123"},
                }
            ],
        }

        with patch.object(
            service,
            "_make_request",
            side_effect=[search_response, video_recording_response],
        ):
            result = service.find_official_video("Ghost", "Rats")

        assert result == {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }

    def test_finds_video_via_direct_free_streaming_relationship(self):
        service = MusicBrainzService()
        search_response = {
            "recordings": [
                {
                    "id": "cccc-dddd",
                    "title": "Rats",
                    "score": 95,
                    "relations": [
                        {
                            "type": "free streaming",
                            "attributes": ["video"],
                            "url": {
                                "resource": "https://www.youtube.com/watch?v=xyz789"
                            },
                        }
                    ],
                }
            ]
        }

        with patch.object(service, "_make_request", return_value=search_response):
            result = service.find_official_video("Ghost", "Rats")

        assert result["video_url"] == "https://www.youtube.com/watch?v=xyz789"
        assert result["relationship_type"] == "free streaming"

    def test_returns_none_when_no_video_relationship_exists(self):
        service = MusicBrainzService()
        search_response = {
            "recordings": [
                {"id": "eeee-ffff", "title": "Rats", "score": 90, "relations": []}
            ]
        }

        with patch.object(service, "_make_request", return_value=search_response):
            result = service.find_official_video("Ghost", "Rats")

        assert result is None

    def test_returns_none_when_musicbrainz_disabled(self):
        service = MusicBrainzService()
        service.enabled = False

        with patch.object(service, "_make_request") as mock_request:
            result = service.find_official_video("Ghost", "Rats")

        mock_request.assert_not_called()
        assert result is None
