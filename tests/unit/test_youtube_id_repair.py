"""#634: restore youtube_id/youtube_url from each downloaded file's .info.json."""

import json

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Video
from src.services.youtube_id_repair_service import repair_youtube_ids


@pytest.fixture
def lib(tmp_path):
    with get_db() as session:
        a = Artist(name="Repair Artist")
        session.add(a)
        session.commit()
        aid = a.id
    yield aid, tmp_path
    with get_db() as session:
        session.query(Video).filter(Video.artist_id == aid).delete()
        session.query(Artist).filter(Artist.id == aid).delete()
        session.commit()


def _video(aid, root, name, db_id, file_id, with_info=True):
    media = root / f"{name}.mp4"
    media.write_bytes(b"x")
    if with_info:
        (root / f"{name}.info.json").write_text(
            json.dumps(
                {
                    "id": file_id,
                    "webpage_url": f"https://www.youtube.com/watch?v={file_id}",
                }
            )
        )
    with get_db() as session:
        v = Video(
            artist_id=aid,
            title=name,
            youtube_id=db_id,
            youtube_url=f"https://www.youtube.com/watch?v={db_id}" if db_id else None,
            url=f"https://youtube.com/watch?v={db_id}" if db_id else None,
            local_path=str(media),
        )
        session.add(v)
        session.commit()
        return v.id


def _get(vid):
    with get_db() as session:
        v = session.get(Video, vid)
        return v.youtube_id, v.youtube_url


def test_dry_run_reports_but_changes_nothing(lib):
    aid, root = lib
    vid = _video(aid, root, "a", "WRONGID0001", "RIGHTID0001")
    with get_db() as session:
        rep = repair_youtube_ids(session, apply=False)
    assert rep["to_fix"] >= 1
    assert _get(vid)[0] == "WRONGID0001"


def test_apply_restores_id_and_url_from_info_json(lib):
    aid, root = lib
    vid = _video(aid, root, "b", "WRONGID0002", "RIGHTID0002")
    with get_db() as session:
        rep = repair_youtube_ids(session, apply=True)
    assert rep["errors"] == []
    assert _get(vid) == ("RIGHTID0002", "https://www.youtube.com/watch?v=RIGHTID0002")


def test_matching_videos_and_missing_info_are_left_alone(lib):
    aid, root = lib
    ok = _video(aid, root, "c", "SAMEID00001", "SAMEID00001")
    noinfo = _video(aid, root, "d", "KEEPID00001", "IGNORED", with_info=False)
    with get_db() as session:
        repair_youtube_ids(session, apply=True)
    assert _get(ok)[0] == "SAMEID00001"
    assert _get(noinfo)[0] == "KEEPID00001"


def test_two_videos_whose_files_share_an_id_only_one_is_fixed(lib):
    # the real-world case: videos 854/1223 both point at file RIYbzM2w0gg
    aid, root = lib
    v1 = _video(aid, root, "e1", "WRONGA00001", "DUPFILEID01")
    v2 = _video(aid, root, "e2", "WRONGB00001", "DUPFILEID01")
    with get_db() as session:
        rep = repair_youtube_ids(session, apply=True)
    ids = {_get(v1)[0], _get(v2)[0]}
    assert "DUPFILEID01" in ids and len(ids) == 2  # exactly one claimed it
    assert any("DUPFILEID01" in c for c in rep["conflicts"])
    assert rep["errors"] == []


def test_id_held_by_a_video_that_is_also_being_fixed_is_freed_first(lib):
    # A currently holds B's correct id, and B holds A's: both fixable, no error
    aid, root = lib
    a = _video(aid, root, "f1", "SWAPIDBBB01", "SWAPIDAAA01")
    b = _video(aid, root, "f2", "SWAPIDAAA01", "SWAPIDBBB01")
    with get_db() as session:
        rep = repair_youtube_ids(session, apply=True)
    assert rep["errors"] == []
    assert _get(a)[0] == "SWAPIDAAA01" and _get(b)[0] == "SWAPIDBBB01"


def test_videos_with_no_id_are_only_filled_on_request(lib):
    aid, root = lib
    vid = _video(aid, root, "g", None, "FILLID00001")
    with get_db() as session:
        rep = repair_youtube_ids(session, apply=True)
    assert rep["missing_not_filled"] >= 1 and _get(vid)[0] is None
    with get_db() as session:
        repair_youtube_ids(session, apply=True, fill_missing=True)
    assert _get(vid)[0] == "FILLID00001"
