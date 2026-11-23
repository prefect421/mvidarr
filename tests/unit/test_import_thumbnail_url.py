"""#613: thumbnail URL for imported YouTube videos is rebuilt from a validated
ID, never taken from the client (the server later fetches it -> SSRF)."""

import pytest

from src.utils.youtube_urls import youtube_thumbnail_url


def test_valid_id_gives_canonical_hqdefault():
    assert (
        youtube_thumbnail_url("dQw4w9WgXcQ")
        == "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    )


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "short",
        "dQw4w9WgXcQx",  # 12 chars
        "dQw4w9WgXc/",  # path char
        "..%2f..%2fadm",
        "a@evil.test/x",
        "evil.test\\@x",  # backslash host-confusion shape
        "dQw4w9WgXc\n",
        "dQw4w9WgXc ",
        12345678901,
    ],
)
def test_bad_ids_give_none(bad):
    assert youtube_thumbnail_url(bad) is None
