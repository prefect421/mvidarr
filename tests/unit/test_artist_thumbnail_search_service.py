"""Tests for the unified artist thumbnail source search (#320).

Consolidates what were two separate, drifting cascades — the
single-artist search endpoint and the bulk-scan endpoint — into one
shared function with one priority order, and adds live Spotify/Last.fm
image lookups ahead of Wikipedia (previously the only real image
source tried; #320 reported it "is not always reliable").

MusicBrainz is deliberately NOT a source here: its API provides
metadata and cross-service links, not artist photography — there is no
MusicBrainz-hosted artist image to fetch, confirmed by reading
musicbrainz_service.py's actual methods before assuming otherwise.
"""

from types import SimpleNamespace
from unittest.mock import patch

from src.services.artist_thumbnail_search_service import search_artist_thumbnails


def _artist(imvdb_metadata=None):
    return SimpleNamespace(imvdb_metadata=imvdb_metadata)


class TestAutoModePriorityOrder:
    def test_spotify_result_appears_before_wikipedia(self):
        with patch(
            "src.services.artist_thumbnail_search_service.spotify_service"
        ) as mock_spotify, patch(
            "src.services.artist_thumbnail_search_service.lastfm_service"
        ) as mock_lastfm, patch(
            "src.services.artist_thumbnail_search_service.wikipedia_service"
        ) as mock_wikipedia, patch(
            "src.services.artist_thumbnail_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_spotify.enabled = True
            mock_spotify.search_artist.return_value = {
                "artists": {
                    "items": [
                        {
                            "images": [
                                {
                                    "url": "https://spotify.example/img.jpg",
                                    "width": 640,
                                    "height": 640,
                                }
                            ]
                        }
                    ]
                }
            }
            mock_lastfm.enabled = False
            mock_wikipedia.search_artist_thumbnail.return_value = (
                "https://wikipedia.example/img.jpg"
            )
            mock_youtube.search_artist_channel_thumbnail.return_value = None

            results = search_artist_thumbnails("Some Artist")

        sources = [r["source"] for r in results]
        assert sources.index("spotify") < sources.index("wikipedia")

    def test_unconfigured_sources_are_silently_skipped(self):
        with patch(
            "src.services.artist_thumbnail_search_service.spotify_service"
        ) as mock_spotify, patch(
            "src.services.artist_thumbnail_search_service.lastfm_service"
        ) as mock_lastfm, patch(
            "src.services.artist_thumbnail_search_service.wikipedia_service"
        ) as mock_wikipedia, patch(
            "src.services.artist_thumbnail_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_spotify.enabled = False
            mock_lastfm.enabled = False
            mock_wikipedia.search_artist_thumbnail.return_value = None
            mock_youtube.search_artist_channel_thumbnail.return_value = None

            results = search_artist_thumbnails("Some Artist")

        assert results == []
        mock_spotify.search_artist.assert_not_called()

    def test_a_failing_source_does_not_prevent_others_from_running(self):
        with patch(
            "src.services.artist_thumbnail_search_service.spotify_service"
        ) as mock_spotify, patch(
            "src.services.artist_thumbnail_search_service.lastfm_service"
        ) as mock_lastfm, patch(
            "src.services.artist_thumbnail_search_service.wikipedia_service"
        ) as mock_wikipedia, patch(
            "src.services.artist_thumbnail_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_spotify.enabled = True
            mock_spotify.search_artist.side_effect = RuntimeError("Spotify down")
            mock_lastfm.enabled = False
            mock_wikipedia.search_artist_thumbnail.return_value = (
                "https://wikipedia.example/img.jpg"
            )
            mock_youtube.search_artist_channel_thumbnail.return_value = None

            results = search_artist_thumbnails("Some Artist")

        assert any(r["source"] == "wikipedia" for r in results)


class TestSourceFilter:
    def test_restricting_to_a_single_source_skips_the_others(self):
        with patch(
            "src.services.artist_thumbnail_search_service.wikipedia_service"
        ) as mock_wikipedia, patch(
            "src.services.artist_thumbnail_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_wikipedia.search_artist_thumbnail.return_value = (
                "https://wikipedia.example/img.jpg"
            )

            results = search_artist_thumbnails("Some Artist", source_filter="wikipedia")

        assert [r["source"] for r in results] == ["wikipedia"]
        mock_youtube.search_artist_channel_thumbnail.assert_not_called()


class TestStopAtFirstResult:
    def test_stops_after_the_first_source_with_results(self):
        with patch(
            "src.services.artist_thumbnail_search_service.spotify_service"
        ) as mock_spotify, patch(
            "src.services.artist_thumbnail_search_service.lastfm_service"
        ) as mock_lastfm:
            mock_spotify.enabled = True
            mock_spotify.search_artist.return_value = {
                "artists": {
                    "items": [
                        {
                            "images": [
                                {
                                    "url": "https://spotify.example/img.jpg",
                                    "width": 640,
                                    "height": 640,
                                }
                            ]
                        }
                    ]
                }
            }
            mock_lastfm.enabled = True

            results = search_artist_thumbnails("Some Artist", stop_at_first_result=True)

        assert [r["source"] for r in results] == ["spotify"]
        mock_lastfm.get_artist_info.assert_not_called()


class TestPlaceholderFiltering:
    def test_known_lastfm_placeholder_is_excluded_from_spotify_and_lastfm_results(self):
        with patch(
            "src.services.artist_thumbnail_search_service.spotify_service"
        ) as mock_spotify, patch(
            "src.services.artist_thumbnail_search_service.lastfm_service"
        ) as mock_lastfm, patch(
            "src.services.artist_thumbnail_search_service.wikipedia_service"
        ) as mock_wikipedia, patch(
            "src.services.artist_thumbnail_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_spotify.enabled = True
            mock_spotify.search_artist.return_value = {"artists": {"items": []}}
            mock_lastfm.enabled = True
            mock_lastfm.get_artist_info.return_value = {
                "image": [
                    {
                        "#text": "https://lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png",
                        "size": "large",
                    }
                ]
            }
            mock_wikipedia.search_artist_thumbnail.return_value = None
            mock_youtube.search_artist_channel_thumbnail.return_value = None

            results = search_artist_thumbnails("Some Artist")

        assert results == []


class TestCachedMetadataFallback:
    def test_falls_back_to_cached_imvdb_metadata_images(self):
        artist = _artist(
            imvdb_metadata={
                "images": [{"#text": "https://cached.example/img.jpg", "size": "large"}]
            }
        )

        with patch(
            "src.services.artist_thumbnail_search_service.spotify_service"
        ) as mock_spotify, patch(
            "src.services.artist_thumbnail_search_service.lastfm_service"
        ) as mock_lastfm, patch(
            "src.services.artist_thumbnail_search_service.wikipedia_service"
        ) as mock_wikipedia, patch(
            "src.services.artist_thumbnail_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_spotify.enabled = False
            mock_lastfm.enabled = False
            mock_wikipedia.search_artist_thumbnail.return_value = None
            mock_youtube.search_artist_channel_thumbnail.return_value = None

            results = search_artist_thumbnails("Some Artist", artist=artist)

        assert any(r["url"] == "https://cached.example/img.jpg" for r in results)

    def test_no_artist_row_means_no_cached_metadata_results(self):
        with patch(
            "src.services.artist_thumbnail_search_service.spotify_service"
        ) as mock_spotify, patch(
            "src.services.artist_thumbnail_search_service.lastfm_service"
        ) as mock_lastfm, patch(
            "src.services.artist_thumbnail_search_service.wikipedia_service"
        ) as mock_wikipedia, patch(
            "src.services.artist_thumbnail_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_spotify.enabled = False
            mock_lastfm.enabled = False
            mock_wikipedia.search_artist_thumbnail.return_value = None
            mock_youtube.search_artist_channel_thumbnail.return_value = None

            results = search_artist_thumbnails("Some Artist", artist=None)

        assert results == []
