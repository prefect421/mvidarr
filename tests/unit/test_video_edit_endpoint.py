"""#635: the Edit Video form silently dropped Year, Album, Duration, Description
and Video URL, and 'Move file to artist folder' did nothing."""

import asyncio

import pytest
from fastapi import HTTPException

from src.api.fastapi.videos_crud import get_video, update_video
from src.api.fastapi.videos_models import VideoUpdateRequest
from src.database.connection import get_db
from src.database.models import Artist, Video
from src.services import video_file_mover as mover


@pytest.fixture
def lib(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    (root / "Old Artist").mkdir(parents=True)
    monkeypatch.setattr(mover, "_library_root", lambda: str(root))
    media = root / "Old Artist" / "Song.mp4"
    media.write_bytes(b"v")
    (root / "Old Artist" / "Song.info.json").write_text("{}")
    with get_db() as s:
        old = Artist(name="Old Artist")
        s.add(old)
        s.commit()
        v = Video(
            artist_id=old.id,
            title="Song",
            youtube_id="editvid0001",
            url="u",
            youtube_url="https://www.youtube.com/watch?v=editvid0001",
            local_path=str(media),
        )
        other = Video(
            artist_id=old.id, title="Other", youtube_id="editvid0002", url="u"
        )
        s.add_all([v, other])
        s.commit()
        ids = (old.id, v.id, other.id)
    yield root, ids
    with get_db() as s:
        s.query(Video).filter(
            Video.artist_id.in_(
                [ids[0]]
                + [a.id for a in s.query(Artist).filter(Artist.name == "New Artist")]
            )
        ).delete(synchronize_session=False)
        s.query(Artist).filter(Artist.name.in_(["Old Artist", "New Artist"])).delete(
            synchronize_session=False
        )
        s.commit()


def _put(video_id, **fields):
    with get_db() as s:
        return asyncio.run(
            update_video(
                video_id=video_id,
                update_data=VideoUpdateRequest(**fields),
                current_user={"user_id": 1},
                session=s,
            )
        )


def _row(video_id):
    with get_db() as s:
        v = s.get(Video, video_id)
        return {
            c: getattr(v, c)
            for c in (
                "year",
                "album",
                "duration",
                "description",
                "url",
                "youtube_id",
                "youtube_url",
                "artist_id",
                "local_path",
            )
        }


def test_year_album_duration_description_are_saved_and_returned(lib):
    _, (_, vid, _) = lib
    res = _put(
        vid, year=1999, album="Greatest", duration=215, description="A long note"
    )
    row = _row(vid)
    assert (row["year"], row["album"], row["duration"], row["description"]) == (
        1999,
        "Greatest",
        215,
        "A long note",
    )
    assert res.description == "A long note" and res.duration == 215


def test_get_video_returns_description_so_the_form_can_show_it(lib):
    _, (_, vid, _) = lib
    _put(vid, description="hello")
    with get_db() as s:
        res = asyncio.run(
            get_video(video_id=vid, current_user={"user_id": 1}, session=s)
        )
    assert res.description == "hello"


def test_youtube_video_url_rederives_the_id_and_url(lib):
    _, (_, vid, _) = lib
    _put(vid, video_url="https://youtu.be/NEWYTID0001?t=10")
    row = _row(vid)
    assert row["youtube_id"] == "NEWYTID0001"
    assert row["youtube_url"] == "https://www.youtube.com/watch?v=NEWYTID0001"
    assert row["url"] == "https://www.youtube.com/watch?v=NEWYTID0001"


def test_video_url_owned_by_another_video_is_a_409(lib):
    _, (_, vid, _) = lib
    with pytest.raises(HTTPException) as e:
        _put(vid, video_url="https://www.youtube.com/watch?v=editvid0002")
    assert e.value.status_code == 409
    assert _row(vid)["youtube_id"] == "editvid0001"  # nothing changed


def test_non_youtube_video_url_only_sets_url(lib):
    _, (_, vid, _) = lib
    _put(vid, video_url="https://vimeo.com/12345")
    row = _row(vid)
    assert (
        row["url"] == "https://vimeo.com/12345" and row["youtube_id"] == "editvid0001"
    )


def test_changing_artist_with_move_file_moves_the_files(lib):
    root, (_, vid, _) = lib
    _put(vid, artist_name="New Artist", move_file=True)
    assert (root / "New Artist" / "Song.mp4").exists()
    assert (root / "New Artist" / "Song.info.json").exists()
    assert not (root / "Old Artist" / "Song.mp4").exists()
    assert _row(vid)["local_path"] == str(root / "New Artist" / "Song.mp4")


def test_changing_artist_without_move_file_leaves_the_files(lib):
    root, (_, vid, _) = lib
    _put(vid, artist_name="New Artist", move_file=False)
    assert (root / "Old Artist" / "Song.mp4").exists()


def test_move_conflict_is_a_409_and_the_artist_change_is_not_saved(lib):
    root, (old, vid, _) = lib
    (root / "New Artist").mkdir()
    (root / "New Artist" / "Song.mp4").write_bytes(b"precious")
    with pytest.raises(HTTPException) as e:
        _put(vid, artist_name="New Artist", move_file=True)
    assert e.value.status_code == 409
    assert (root / "New Artist" / "Song.mp4").read_bytes() == b"precious"
    assert (root / "Old Artist" / "Song.mp4").exists()
    assert _row(vid)["artist_id"] == old


def test_move_file_with_no_file_on_disk_is_not_an_error(lib):
    root, (_, vid, other) = lib
    _put(
        other, artist_name="New Artist", move_file=True
    )  # `other` was never downloaded


def test_edit_form_sends_description_and_reports_http_errors():
    html = open("frontend/templates/video_detail.html", encoding="utf-8").read()
    start = html.index("editForm.addEventListener('submit'")
    body = html[start : start + 4500]
    assert "description: formData.get('description')" in body
    assert "thumbnail_url: formData.get" not in body  # ignored by the API by design
    assert "response.ok" in body and "result.detail" in body
