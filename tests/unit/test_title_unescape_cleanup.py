"""#612: one-off cleanup of HTML-escaped titles and the files named after them."""

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Download, Video
from src.services.title_unescape_service import cleanup_escaped_titles, unescape_text


def test_unescape_text():
    assert unescape_text("A &amp; B &#39;x&#39;") == "A & B 'x'"
    assert unescape_text("plain") == "plain"
    assert unescape_text(None) is None


@pytest.fixture
def lib(tmp_path):
    with get_db() as session:
        a = Artist(name="Cleanup Artist")
        session.add(a)
        session.commit()
        aid = a.id
    yield aid, tmp_path
    with get_db() as session:
        session.query(Download).filter(Download.artist_id == aid).delete()
        session.query(Video).filter(Video.artist_id == aid).delete()
        session.query(Artist).filter(Artist.id == aid).delete()
        session.commit()


def _video(aid, yid, title, path=None):
    with get_db() as session:
        v = Video(
            artist_id=aid,
            title=title,
            youtube_id=yid,
            url=f"https://youtube.com/watch?v={yid}",
            local_path=str(path) if path else None,
        )
        session.add(v)
        session.commit()
        return v.id


def test_dry_run_changes_nothing(lib):
    aid, root = lib
    f = root / "A &amp; B.mp4"
    f.write_bytes(b"x")
    vid = _video(aid, "dry1", "A &amp; B", f)
    with get_db() as session:
        report = cleanup_escaped_titles(session, apply=False)
    assert report["titles_to_fix"] >= 1
    assert f.exists()
    with get_db() as session:
        assert session.get(Video, vid).title == "A &amp; B"


def test_apply_fixes_title_renames_files_and_updates_paths(lib):
    aid, root = lib
    main = root / "MACK &amp; RYAN - Where&#39;s.mp4"
    info = root / "MACK &amp; RYAN - Where&#39;s.info.json"
    main.write_bytes(b"video")
    info.write_bytes(b"{}")
    vid = _video(aid, "app1", "MACK &amp; RYAN - Where&#39;s", main)
    with get_db() as session:
        session.add(
            Download(
                artist_id=aid,
                video_id=vid,
                title="t",
                original_url="u",
                status="completed",
                file_path=str(main),
            )
        )
        session.commit()

    with get_db() as session:
        report = cleanup_escaped_titles(session, apply=True)
    assert report["errors"] == []

    new_main = root / "MACK & RYAN - Where's.mp4"
    assert new_main.read_bytes() == b"video"
    assert (root / "MACK & RYAN - Where's.info.json").exists()
    assert not main.exists() and not info.exists()
    with get_db() as session:
        v = session.get(Video, vid)
        assert v.title == "MACK & RYAN - Where's"
        assert v.local_path == str(new_main)
        d = session.query(Download).filter(Download.video_id == vid).one()
        assert d.file_path == str(new_main)


def test_rename_conflict_keeps_files_and_still_fixes_title(lib):
    aid, root = lib
    old = root / "A &amp; B.mp4"
    clash = root / "A & B.mp4"
    old.write_bytes(b"old")
    clash.write_bytes(b"other")
    vid = _video(aid, "clash1", "A &amp; B", old)
    with get_db() as session:
        report = cleanup_escaped_titles(session, apply=True)
    assert old.read_bytes() == b"old" and clash.read_bytes() == b"other"
    assert any("exists" in c for c in report["conflicts"])
    with get_db() as session:
        v = session.get(Video, vid)
        assert v.title == "A & B"
        assert v.local_path == str(old)  # still points at the real file


def test_missing_file_still_fixes_title_and_is_idempotent(lib):
    aid, root = lib
    vid = _video(aid, "gone1", "X &amp; Y", root / "X &amp; Y.mp4")
    with get_db() as session:
        cleanup_escaped_titles(session, apply=True)
        second = cleanup_escaped_titles(session, apply=True)
    assert second["titles_to_fix"] == 0
    with get_db() as session:
        assert session.get(Video, vid).title == "X & Y"


def test_entity_that_would_create_a_path_separator_is_not_renamed(lib):
    aid, root = lib
    f = root / "AC&#47;DC.mp4"
    f.write_bytes(b"x")
    vid = _video(aid, "sep1", "AC&#47;DC", f)
    with get_db() as session:
        report = cleanup_escaped_titles(session, apply=True)
    assert f.exists()
    assert any("separator" in c for c in report["conflicts"])
