"""#634: enrichment must never replace a video's existing YouTube ID (it
identifies the downloaded file), and must never assign an ID another video owns."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.metadata_video_enricher import enrich_video_metadata

MB = "src.services.metadata_video_enricher"


def _video(youtube_id):
    artist = SimpleNamespace(
        name="Basement Jaxx", spotify_id=None, lastfm_name=None, genres=None
    )
    return SimpleNamespace(
        id=101,
        artist=artist,
        title="Where's Your Head At",
        youtube_id=youtube_id,
        youtube_url=(
            f"https://www.youtube.com/watch?v={youtube_id}" if youtube_id else None
        ),
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


def _db(video, id_taken_by_other):
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = (
        video
    )
    # "does another video already own this youtube_id?"
    db.query.return_value.filter.return_value.first.return_value = (
        (999,) if id_taken_by_other else None
    )
    db.merge.side_effect = lambda v: v
    return db


async def _run(video, *, taken=False, force=True):
    mb_match = {
        "video_url": "https://www.youtube.com/watch?v=NEWMBID0001",
        "score": 100,
    }
    yt = MagicMock()
    yt.search_video_by_title.return_value = {
        "videos": [
            {
                "youtube_id": "NEWSRCH0001",
                "youtube_url": "https://www.youtube.com/watch?v=NEWSRCH0001",
                "title": "Basement Jaxx Where's Your Head At official video",
            }
        ]
    }
    db = _db(video, taken)
    with ExitStack() as st:
        st.enter_context(
            patch(
                f"{MB}.get_db",
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=db),
                    __exit__=MagicMock(return_value=False),
                ),
            )
        )
        st.enter_context(
            patch(
                f"{MB}.musicbrainz_service.find_official_video", return_value=mb_match
            )
        )
        st.enter_context(
            patch(f"{MB}.discogs_service.get_track_release_date", return_value=None)
        )
        st.enter_context(
            patch(
                f"{MB}.musicbrainz_service.get_recording_release_date",
                return_value=None,
            )
        )
        st.enter_context(patch(f"{MB}.search_lyrics_azlyrics", return_value=None))
        st.enter_context(
            patch(f"{MB}.requests.head", return_value=MagicMock(status_code=404))
        )
        return await enrich_video_metadata(101, yt, force_refresh=force)


@pytest.mark.asyncio
class TestExistingYoutubeIdIsNeverReplaced:
    async def test_force_refresh_keeps_existing_id_against_musicbrainz_match(self):
        v = _video("5rAOyh7YmEc")
        await _run(v, force=True)
        assert v.youtube_id == "5rAOyh7YmEc"
        assert v.youtube_url == "https://www.youtube.com/watch?v=5rAOyh7YmEc"

    async def test_force_refresh_keeps_existing_id_against_title_search(self):
        v = _video("5rAOyh7YmEc")
        await _run(v, force=True)
        assert v.youtube_id == "5rAOyh7YmEc"


@pytest.mark.asyncio
class TestEmptyYoutubeIdStillGetsFilled:
    async def test_empty_id_is_filled_from_musicbrainz(self):
        v = _video(None)
        res = await _run(v, taken=False, force=False)
        assert v.youtube_id == "NEWMBID0001"
        assert "youtube_id" in res.enriched_fields


@pytest.mark.asyncio
class TestIdOwnedByAnotherVideoIsSkipped:
    async def test_taken_id_is_not_assigned_and_does_not_error(self):
        v = _video(None)
        res = await _run(v, taken=True, force=False)
        assert v.youtube_id is None
        assert not any("IntegrityError" in e or "Duplicate" in e for e in (res.errors or []))
