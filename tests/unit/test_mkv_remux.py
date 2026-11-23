"""#633 (optional cleanup): remux existing .mkv downloads to .mp4 with ffmpeg -c copy."""

import json
import subprocess

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Download, Video
from src.services.mkv_remux_service import remux_mkv_to_mp4


@pytest.fixture
def lib(tmp_path):
    with get_db() as s:
        a = Artist(name="Remux Artist")
        s.add(a)
        s.commit()
        aid = a.id
    yield aid, tmp_path
    with get_db() as s:
        s.query(Download).filter(Download.artist_id == aid).delete()
        s.query(Video).filter(Video.artist_id == aid).delete()
        s.query(Artist).filter(Artist.id == aid).delete()
        s.commit()


def _video(aid, path, yid):
    with get_db() as s:
        v = Video(
            artist_id=aid,
            title=path.stem,
            youtube_id=yid,
            url="u",
            local_path=str(path),
        )
        s.add(v)
        s.commit()
        return v.id


def fake_runner(duration_in="200.0", duration_out="200.0", ffmpeg_rc=0, has_video=True):
    """Stands in for subprocess.run: ffprobe returns JSON, ffmpeg writes its output."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            is_out = str(cmd[-1]).endswith(".part") or str(cmd[-1]).endswith(".mp4")
            streams = (
                [{"codec_type": "video", "codec_name": "h264"}] if has_video else []
            ) + [{"codec_type": "audio", "codec_name": "opus"}]
            out = json.dumps(
                {
                    "format": {"duration": duration_out if is_out else duration_in},
                    "streams": streams,
                }
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        if ffmpeg_rc == 0:
            open(cmd[-1], "wb").write(b"m" * 90)
        return subprocess.CompletedProcess(
            cmd, ffmpeg_rc, stdout="", stderr="boom" if ffmpeg_rc else ""
        )

    run.calls = calls
    return run


def _mkv(root, name="Song"):
    p = root / f"{name}.mkv"
    p.write_bytes(b"k" * 100)
    return p


def _row(vid):
    with get_db() as s:
        v = s.get(Video, vid)
        return v.local_path


def test_dry_run_changes_nothing_and_runs_no_ffmpeg(lib):
    aid, root = lib
    mkv = _mkv(root)
    vid = _video(aid, mkv, "DRYRUN00001")
    run = fake_runner()
    with get_db() as s:
        rep = remux_mkv_to_mp4(s, apply=False, runner=run)
    assert rep["candidates"] >= 1
    assert mkv.exists() and not (root / "Song.mp4").exists()
    assert _row(vid) == str(mkv)
    assert not any(c[0] == "ffmpeg" for c in run.calls)


def test_apply_remuxes_updates_db_and_removes_original(lib):
    aid, root = lib
    mkv = _mkv(root)
    vid = _video(aid, mkv, "APPLY000001")
    with get_db() as s:
        s.add(
            Download(
                artist_id=aid,
                video_id=vid,
                title="t",
                original_url="u",
                status="completed",
                file_path=str(mkv),
            )
        )
        s.commit()
    run = fake_runner()
    with get_db() as s:
        rep = remux_mkv_to_mp4(s, apply=True, runner=run)
    mp4 = root / "Song.mp4"
    assert rep["errors"] == [] and rep["remuxed"] == 1
    assert mp4.exists() and not mkv.exists()
    assert _row(vid) == str(mp4)
    with get_db() as s:
        assert s.query(Download).filter(
            Download.video_id == vid
        ).one().file_path == str(mp4)
    ff = [c for c in run.calls if c[0] == "ffmpeg"][0]
    assert "-c" in ff and ff[ff.index("-c") + 1] == "copy"  # lossless stream copy


def test_keep_original_leaves_the_mkv(lib):
    aid, root = lib
    mkv = _mkv(root)
    _video(aid, mkv, "KEEP0000001")
    with get_db() as s:
        remux_mkv_to_mp4(s, apply=True, keep_original=True, runner=fake_runner())
    assert mkv.exists() and (root / "Song.mp4").exists()


def test_ffmpeg_failure_leaves_original_and_db_untouched(lib):
    aid, root = lib
    mkv = _mkv(root)
    vid = _video(aid, mkv, "FAIL0000001")
    with get_db() as s:
        rep = remux_mkv_to_mp4(s, apply=True, runner=fake_runner(ffmpeg_rc=1))
    assert rep["remuxed"] == 0 and rep["errors"]
    assert mkv.exists() and not list(root.glob("*.mp4*"))
    assert _row(vid) == str(mkv)


def test_duration_mismatch_is_rejected_and_cleaned_up(lib):
    aid, root = lib
    mkv = _mkv(root)
    vid = _video(aid, mkv, "DURA0000001")
    with get_db() as s:
        rep = remux_mkv_to_mp4(s, apply=True, runner=fake_runner(duration_out="120.0"))
    assert rep["remuxed"] == 0 and any("duration" in e for e in rep["errors"])
    assert mkv.exists() and not list(root.glob("*.mp4*"))
    assert _row(vid) == str(mkv)


def test_existing_mp4_target_is_a_conflict_not_overwritten(lib):
    aid, root = lib
    mkv = _mkv(root)
    (root / "Song.mp4").write_bytes(b"precious")
    _video(aid, mkv, "CONF0000001")
    with get_db() as s:
        rep = remux_mkv_to_mp4(s, apply=True, runner=fake_runner())
    assert any("exists" in c for c in rep["conflicts"])
    assert (root / "Song.mp4").read_bytes() == b"precious" and mkv.exists()
