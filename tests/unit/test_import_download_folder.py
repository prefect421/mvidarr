"""#629: an imported video must download into its ARTIST's folder, not a folder
named after the uploading YouTube channel ("... - Topic", label names)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.api.fastapi.videos_import import import_from_youtube
from src.database.connection import get_db
from src.database.models import Artist, Video


@pytest.fixture
def artist():
    with get_db() as s:
        a = Artist(name="The Prodigy", auto_download=True)
        s.add(a)
        s.commit()
        aid = a.id
    yield aid
    with get_db() as s:
        s.query(Video).filter(Video.artist_id == aid).delete()
        s.query(Artist).filter(Artist.id == aid).delete()
        s.commit()


def _import(request):
    ytdlp = MagicMock()
    ytdlp.add_music_video_download.return_value = {"success": True, "id": 1}
    from src.services import settings_service, ytdlp_service

    with patch.object(ytdlp_service, "ytdlp_service", ytdlp), patch.object(
        settings_service.settings, "get_bool", return_value=False
    ), patch.object(settings_service.settings, "get", return_value="en"):
        with get_db() as session:
            asyncio.run(
                import_from_youtube(
                    request=request, current_user={"user_id": 1}, session=session
                )
            )
    return ytdlp.add_music_video_download


def test_selected_artist_wins_over_the_channel_name(artist):
    dl = _import(
        {
            "youtube_id": "prodigy0001",
            "title": "Smack My Bitch Up",
            "artist": "The Prodigy - Topic",  # what the page sends: the channel
            "artist_id": artist,
            "auto_download": True,
        }
    )
    assert dl.call_args.kwargs["artist"] == "The Prodigy"


def test_artist_found_by_name_uses_the_stored_name(artist):
    dl = _import(
        {
            "youtube_id": "prodigy0002",
            "title": "Firestarter",
            "artist": "The Prodigy",
            "auto_download": True,
        }
    )
    assert dl.call_args.kwargs["artist"] == "The Prodigy"
