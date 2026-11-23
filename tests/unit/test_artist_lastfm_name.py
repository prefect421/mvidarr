"""#640: an artist's Last.fm match could not be corrected: no field in the UI, the
update API ignored lastfm_name, and renaming the artist kept the wrong match."""

import asyncio

import pytest

from src.api.fastapi.artists_crud import get_artist, update_artist
from src.api.fastapi.artists_models import ArtistUpdateRequest
from src.database.connection import get_db
from src.database.models import Artist


@pytest.fixture
def artist():
    with get_db() as s:
        a = Artist(
            name="vanillaice",
            lastfm_name="VanillaIce",
            musicbrainz_id="mb-1",
            spotify_id="sp-1",
        )
        s.add(a)
        s.commit()
        aid = a.id
    yield aid
    with get_db() as s:
        s.query(Artist).filter(Artist.id == aid).delete()
        s.commit()


def _put(aid, **fields):
    with get_db() as s:
        return asyncio.run(
            update_artist(
                artist_id=aid,
                update_data=ArtistUpdateRequest(**fields),
                current_user={"user_id": 1},
                session=s,
            )
        )


def _row(aid):
    with get_db() as s:
        a = s.get(Artist, aid)
        return a.name, a.lastfm_name, a.musicbrainz_id, a.spotify_id


def test_get_artist_returns_lastfm_name_so_the_form_can_show_it(artist):
    with get_db() as s:
        res = asyncio.run(
            get_artist(artist_id=artist, current_user={"user_id": 1}, session=s)
        )
    assert res.lastfm_name == "VanillaIce"


def test_update_accepts_and_returns_lastfm_name(artist):
    res = _put(artist, lastfm_name="Vanilla Ice")
    assert (
        _row(artist)[1] == "Vanilla Ice"
        and res["artist"]["lastfm_name"] == "Vanilla Ice"
    )


def test_blank_clears_the_external_ids_instead_of_storing_empty_strings(artist):
    _put(artist, lastfm_name="  ", musicbrainz_id="", spotify_id="")
    assert _row(artist)[1:] == (None, None, None)


def test_renaming_the_artist_drops_the_stale_lastfm_match(artist):
    # the wrong match is re-found, by the NEW name, on the next Auto-match
    _put(artist, name="Vanilla Ice")
    name, lastfm, mb, sp = _row(artist)
    assert name == "Vanilla Ice" and lastfm is None
    assert (mb, sp) == ("mb-1", "sp-1")  # only Last.fm is name-derived


def test_case_or_spacing_only_rename_keeps_the_match(artist):
    _put(artist, name="  VanillaIce ")
    assert _row(artist)[1] == "VanillaIce"
    _put(artist, name="vanillaice")
    assert _row(artist)[1] == "VanillaIce"


def test_an_explicit_lastfm_name_in_the_same_request_wins_over_the_rename(artist):
    _put(artist, name="Vanilla Ice", lastfm_name="Vanilla Ice")
    assert _row(artist)[:2] == ("Vanilla Ice", "Vanilla Ice")


def test_saving_other_fields_does_not_touch_the_match(artist):
    _put(artist, biography="hello")
    assert _row(artist)[1] == "VanillaIce"


def test_artist_page_has_editable_match_fields_sent_only_when_changed():
    html = open("frontend/templates/artist_detail.html", encoding="utf-8").read()
    assert 'name="lastfm_name"' in html and 'name="musicbrainz_id"' in html
    assert "artist.lastfm_name" in html  # populated from the API
    start = html.index("const storedArtist")
    block = html[start : start + 500]
    # only sent when the user changed it, so renaming still resets the match
    assert "!== (storedArtist[key] || '')" in block
