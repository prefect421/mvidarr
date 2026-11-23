"""#608: Video has local_path, not file_path; nothing may read Video.file_path."""

import pathlib
import re

from src.database.models import Video


def test_video_model_has_local_path_only():
    assert hasattr(Video, "local_path")
    assert not hasattr(Video, "file_path")


def test_no_source_reads_video_file_path():
    offenders = [
        str(p)
        for p in pathlib.Path("src").rglob("*.py")
        if re.search(r"\bvideo\.file_path\b|\bVideo\.file_path\b", p.read_text())
    ]
    assert offenders == []


def test_find_relocated_video_missing_file_returns_none_not_500():
    import asyncio

    from src.api.fastapi.videos_streaming import find_relocated_video

    video = Video(id=9, title="x", local_path="data/musicvideos/nope/missing.mp4")
    assert asyncio.run(find_relocated_video(video)) is None
