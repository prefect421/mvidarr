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

    def test_finds_video_among_multiple_candidates_when_not_top_result(self):
        # Live-reported (2026-09-23): MusicBrainz recording search often
        # returns many same-title/same-artist candidates (DJ-mix inclusions,
        # live versions, remasters) tied at the top relevance score -- the
        # actual video-carrying recording is frequently NOT first. Verified
        # against the real API for Rick Astley - "Never Gonna Give You Up":
        # 83 candidate recordings, only checking the single top-scored one
        # missed the one flagged "Official Music Video" entirely.
        service = MusicBrainzService()
        search_response = {
            "recordings": [
                {
                    "id": "dj-mix-inclusion",
                    "title": "Rats",
                    "score": 100,
                    "relations": [],
                },
                {"id": "live-version", "title": "Rats", "score": 100, "relations": []},
                {
                    "id": "official-video-recording",
                    "title": "Rats",
                    "score": 100,
                    "relations": [
                        {
                            "type": "free streaming",
                            "attributes": ["video"],
                            "url": {
                                "resource": "https://www.youtube.com/watch?v=abc123"
                            },
                        }
                    ],
                },
            ]
        }

        with patch.object(service, "_make_request", return_value=search_response):
            result = service.find_official_video("Ghost", "Rats")

        assert result is not None
        assert result["video_url"] == "https://www.youtube.com/watch?v=abc123"
        assert result["recording_id"] == "official-video-recording"

    def test_prioritizes_recording_musicbrainz_itself_flags_as_video(self):
        # MusicBrainz recordings carry their own "video": true flag when the
        # recording IS a video (vs. audio) -- confirmed live on the real
        # Rick Astley recording carrying the "Official Music Video"
        # disambiguation. When multiple candidates have a valid video
        # relationship, prefer the one MusicBrainz itself flags as video.
        service = MusicBrainzService()
        search_response = {
            "recordings": [
                {
                    "id": "some-other-video-edit",
                    "title": "Rats",
                    "score": 100,
                    "video": None,
                    "relations": [
                        {
                            "type": "free streaming",
                            "attributes": ["video"],
                            "url": {
                                "resource": "https://www.youtube.com/watch?v=wrong111"
                            },
                        }
                    ],
                },
                {
                    "id": "official-video-recording",
                    "title": "Rats",
                    "score": 100,
                    "video": True,
                    "disambiguation": "Official Music Video",
                    "relations": [
                        {
                            "type": "free streaming",
                            "attributes": ["video"],
                            "url": {
                                "resource": "https://www.youtube.com/watch?v=right222"
                            },
                        }
                    ],
                },
            ]
        }

        with patch.object(service, "_make_request", return_value=search_response):
            result = service.find_official_video("Ghost", "Rats")

        assert result["video_url"] == "https://www.youtube.com/watch?v=right222"
        assert result["recording_id"] == "official-video-recording"

    def test_follows_up_with_direct_lookup_when_video_flagged_recording_has_no_inline_relations(
        self,
    ):
        # Live-reported (2026-09-23): MusicBrainz's recording *search*
        # endpoint never actually inlines `relations`, even when
        # `inc=url-rels+recording-rels` is requested -- confirmed against
        # the real API on multiple queries. Only a direct entity GET
        # (`recording/{id}`) reliably returns them. Verified live: Rick
        # Astley - "Never Gonna Give You Up" has recordings flagged
        # `video: true` whose search-result relations are always empty,
        # but a direct GET on the same ID returns the real
        # free-streaming+video relation.
        service = MusicBrainzService()
        search_response = {
            "recordings": [
                {"id": "audio-take-1", "title": "Rats", "score": 100, "relations": []},
                {
                    "id": "official-video-recording",
                    "title": "Rats",
                    "score": 100,
                    "video": True,
                    "disambiguation": "Official Music Video",
                    "relations": [],  # search endpoint never inlines these
                },
            ]
        }
        direct_lookup_response = {
            "id": "official-video-recording",
            "relations": [
                {
                    "type": "free streaming",
                    "attributes": ["video"],
                    "url": {"resource": "https://www.youtube.com/watch?v=real123"},
                }
            ],
        }

        with patch.object(
            service,
            "_make_request",
            side_effect=[search_response, direct_lookup_response],
        ) as mock_request:
            result = service.find_official_video("Ghost", "Rats")

        assert result["video_url"] == "https://www.youtube.com/watch?v=real123"
        assert result["recording_id"] == "official-video-recording"
        # Bounded cost: only the video-flagged candidate gets a follow-up
        # direct lookup, not every candidate in the search results.
        assert mock_request.call_count == 2

    def test_does_not_follow_up_on_non_video_flagged_candidates_with_empty_relations(
        self,
    ):
        # Bounds the extra-request cost: candidates MusicBrainz doesn't
        # flag as video get no follow-up lookup even if their inline
        # relations are empty (the common case for most candidates).
        service = MusicBrainzService()
        search_response = {
            "recordings": [
                {"id": "audio-take-1", "title": "Rats", "score": 100, "relations": []},
                {"id": "audio-take-2", "title": "Rats", "score": 100, "relations": []},
            ]
        }

        with patch.object(
            service, "_make_request", return_value=search_response
        ) as mock_request:
            result = service.find_official_video("Ghost", "Rats")

        assert result is None
        assert mock_request.call_count == 1

    def test_returns_none_when_musicbrainz_disabled(self):
        service = MusicBrainzService()
        service.enabled = False

        with patch.object(service, "_make_request") as mock_request:
            result = service.find_official_video("Ghost", "Rats")

        mock_request.assert_not_called()
        assert result is None
