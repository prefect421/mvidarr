"""#629 repair: move files sitting in a channel-named folder into their artist's folder."""

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Video
from src.services import video_file_mover as mover
from src.services.misfiled_videos_service import repair_misfiled_videos


@pytest.fixture
def lib(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setattr(mover, "_library_root", lambda: str(root))
    with get_db() as s:
        a = Artist(name="The Prodigy")
        s.add(a)
        s.commit()
        aid = a.id
    yield root, aid
    with get_db() as s:
        s.query(Video).filter(Video.artist_id == aid).delete(synchronize_session=False)
        s.query(Artist).filter(Artist.id == aid).delete(synchronize_session=False)
        s.commit()


def _video(aid, folder, name, yid):
    d = folder
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.mp4"
    f.write_bytes(b"v")
    with get_db() as s:
        v = Video(artist_id=aid, title=name, youtube_id=yid, url="u", local_path=str(f))
        s.add(v)
        s.commit()
        return v.id


def test_dry_run_lists_but_moves_nothing(lib):
    root, aid = lib
    _video(aid, root / "The Prodigy - Topic", "Smack", "misfile0001")
    with get_db() as s:
        rep = repair_misfiled_videos(s, apply=False)
    assert rep["to_move"] >= 1 and (root / "The Prodigy - Topic" / "Smack.mp4").exists()


def test_apply_moves_into_the_artists_folder(lib):
    root, aid = lib
    vid = _video(aid, root / "ChannelVEVO", "Firestarter", "misfile0002")
    with get_db() as s:
        rep = repair_misfiled_videos(s, apply=True)
    assert rep["errors"] == []
    assert (root / "The Prodigy" / "Firestarter.mp4").exists()
    with get_db() as s:
        assert s.get(Video, vid).local_path == str(
            root / "The Prodigy" / "Firestarter.mp4"
        )


def test_files_already_in_the_artist_folder_are_left_alone(lib):
    root, aid = lib
    _video(aid, root / "The Prodigy", "Already", "misfile0003")
    with get_db() as s:
        rep = repair_misfiled_videos(s, apply=True)
    assert rep["to_move"] == 0 and (root / "The Prodigy" / "Already.mp4").exists()
