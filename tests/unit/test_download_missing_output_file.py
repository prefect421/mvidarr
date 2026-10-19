"""#540: a download must not be marked DOWNLOADED when no output file exists."""

from src.services.ytdlp_download_manager import _resolve_downloaded_file


def test_existing_file_returned_as_is(tmp_path):
    f = tmp_path / "Song.mp4"
    f.write_bytes(b"x")
    assert _resolve_downloaded_file(str(f)) == str(f)


def test_missing_mp4_falls_back_to_same_stem_webm(tmp_path):
    webm = tmp_path / "Song.webm"
    webm.write_bytes(b"x")
    assert _resolve_downloaded_file(str(tmp_path / "Song.mp4")) == str(webm)


def test_format_id_fragments_are_not_playable_fallbacks(tmp_path):
    (tmp_path / "Song.f251.webm").write_bytes(b"x")
    (tmp_path / "Song.info.json").write_bytes(b"{}")
    assert _resolve_downloaded_file(str(tmp_path / "Song.mp4")) is None


def test_none_and_empty_paths():
    assert _resolve_downloaded_file(None) is None
    assert _resolve_downloaded_file("") is None
