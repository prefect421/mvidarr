"""#617: LastFmService.get_track_info() never existed, so video enrichment
raised AttributeError for every video and never filled album/genres/duration."""

from unittest.mock import patch

from src.services.lastfm_service import LastFmService


def _svc():
    return LastFmService.__new__(LastFmService)


def test_get_track_info_calls_track_getinfo_with_autocorrect():
    track = {
        "name": "Song 2",
        "album": {"title": "Blur"},
        "duration": "121000",
        "toptags": {"tag": [{"name": "rock"}]},
        "playcount": "5",
        "listeners": "3",
        "url": "https://last.fm/x",
    }
    svc = _svc()
    with patch.object(svc, "_make_request", return_value={"track": track}) as req:
        out = svc.get_track_info("Blur", "Song 2")
    req.assert_called_once_with(
        "track.getInfo", {"artist": "Blur", "track": "Song 2", "autocorrect": 1}
    )
    assert out["album"]["title"] == "Blur"
    assert out["duration"] == "121000"


def test_track_not_found_returns_empty_dict_not_an_exception():
    svc = _svc()
    with patch.object(
        svc,
        "_make_request",
        side_effect=ValueError("Last.fm API error: Track not found"),
    ):
        assert svc.get_track_info("Nobody", "Nothing") == {}


def test_missing_track_key_returns_empty_dict():
    svc = _svc()
    with patch.object(svc, "_make_request", return_value={}):
        assert svc.get_track_info("A", "B") == {}


def test_enricher_searches_with_the_cleaned_title():
    import inspect

    from src.services import metadata_video_enricher as mve

    src = inspect.getsource(mve)
    start = src.index("# 5. Enhanced Last.fm enrichment")
    block = src[start : start + 900]
    assert "clean_title_for_metadata_search" in block
