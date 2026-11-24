"""#635: safe move of a video's media + sidecars into another artist's folder."""

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Download, Video
from src.services import video_file_mover as mover


@pytest.fixture
def setup(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    (lib / "Old Artist").mkdir(parents=True)
    monkeypatch.setattr(mover, "_library_root", lambda: str(lib))
    with get_db() as s:
        old = Artist(name="Old Artist")
        new = Artist(name="New Artist")
        s.add_all([old, new])
        s.commit()
        ids = (old.id, new.id)
    yield lib, ids
    with get_db() as s:
        s.query(Download).filter(Download.artist_id.in_(ids)).delete(
            synchronize_session=False
        )
        s.query(Video).filter(Video.artist_id.in_(ids)).delete(
            synchronize_session=False
        )
        s.query(Artist).filter(Artist.id.in_(ids)).delete(synchronize_session=False)
        s.commit()


def _video(artist_id, lib, name="Song", with_sidecars=True, yid="moverv00001"):
    d = lib / "Old Artist"
    media = d / f"{name}.mp4"
    media.write_bytes(b"video")
    if with_sidecars:
        (d / f"{name}.info.json").write_text("{}")
        (d / f"{name}.en.vtt").write_text("WEBVTT")
        (d / f"{name} (other).mp4").write_bytes(b"different video, similar name")
    with get_db() as s:
        v = Video(
            artist_id=artist_id,
            title=name,
            youtube_id=yid,
            url="u",
            local_path=str(media),
        )
        s.add(v)
        s.commit()
        return v.id


def test_moves_media_and_sidecars_and_updates_paths(setup):
    lib, (old, new) = setup
    vid = _video(old, lib)
    with get_db() as s:
        s.add(
            Download(
                artist_id=old,
                video_id=vid,
                title="t",
                original_url="u",
                status="completed",
                file_path=str(lib / "Old Artist" / "Song.mp4"),
            )
        )
        s.commit()
        v = s.get(Video, vid)
        res = mover.move_video_to_artist_folder(s, v, "New Artist")
        s.commit()
    dest = lib / "New Artist"
    assert res["moved"] is True and res["error"] is None
    assert (dest / "Song.mp4").read_bytes() == b"video"
    assert (dest / "Song.info.json").exists() and (dest / "Song.en.vtt").exists()
    assert not (lib / "Old Artist" / "Song.mp4").exists()
    # a different video whose name merely starts with the same words is NOT moved
    assert (lib / "Old Artist" / "Song (other).mp4").exists()
    with get_db() as s:
        assert s.get(Video, vid).local_path == str(dest / "Song.mp4")
        assert s.query(Download).filter(
            Download.video_id == vid
        ).one().file_path == str(dest / "Song.mp4")


def test_target_exists_is_a_conflict_and_nothing_moves(setup):
    lib, (old, new) = setup
    vid = _video(old, lib)
    (lib / "New Artist").mkdir()
    (lib / "New Artist" / "Song.info.json").write_text("precious")
    with get_db() as s:
        res = mover.move_video_to_artist_folder(s, s.get(Video, vid), "New Artist")
    assert res["moved"] is False and "exists" in res["error"]
    assert (lib / "Old Artist" / "Song.mp4").exists()
    assert (lib / "New Artist" / "Song.info.json").read_text() == "precious"
    with get_db() as s:
        assert s.get(Video, vid).local_path == str(lib / "Old Artist" / "Song.mp4")


def test_missing_file_is_skipped_not_an_error(setup):
    lib, (old, new) = setup
    with get_db() as s:
        v = Video(
            artist_id=old,
            title="x",
            youtube_id="moverv00002",
            url="u",
            local_path=str(lib / "Old Artist" / "ghost.mp4"),
        )
        s.add(v)
        s.commit()
        res = mover.move_video_to_artist_folder(s, v, "New Artist")
    assert (
        res["moved"] is False
        and res["error"] is None
        and res["skipped"] == "no file on disk"
    )


def test_already_in_the_right_folder_is_a_noop(setup):
    lib, (old, new) = setup
    vid = _video(old, lib, with_sidecars=False)
    with get_db() as s:
        res = mover.move_video_to_artist_folder(s, s.get(Video, vid), "Old Artist")
    assert res["moved"] is False and res["error"] is None
    assert (lib / "Old Artist" / "Song.mp4").exists()


def test_a_failure_part_way_restores_everything(setup, monkeypatch):
    lib, (old, new) = setup
    vid = _video(old, lib)
    real_move = mover.shutil.move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full")
        return real_move(src, dst)

    monkeypatch.setattr(mover.shutil, "move", flaky)
    with get_db() as s:
        res = mover.move_video_to_artist_folder(s, s.get(Video, vid), "New Artist")
    assert res["moved"] is False and "disk full" in res["error"]
    old_dir = lib / "Old Artist"
    assert {p.name for p in old_dir.iterdir()} >= {
        "Song.mp4",
        "Song.info.json",
        "Song.en.vtt",
    }
    assert (
        not list((lib / "New Artist").glob("Song*"))
        if (lib / "New Artist").exists()
        else True
    )
