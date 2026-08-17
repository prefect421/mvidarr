"""Regression/feature test for #329: _update_database_failure() set
video.status = FAILED and overwrote the most recent Download row
unconditionally, with no check for whether the video already reached a
terminal DOWNLOADED state. A late-arriving failure from a duplicate
dispatch (see claim_video_for_download() and its two call sites, added
earlier in this same plan) could silently erase a real, already-persisted
success.

The static source-assertion tests below cannot catch every bug in this
guard -- notably they passed against a version of the guard that compared
`video.status == VideoStatus.DOWNLOADED.value`, which is *always False*:
`Video.status` is `Column(SQLEnum(VideoStatus))` and `VideoStatus` is a
plain `Enum` (not a `str` mixin), so SQLAlchemy hydrates the attribute as
a `VideoStatus` *member*, never a string. That made the entire guard dead
code -- it could never fire. `TestDownloadedStatusComparisonBugClass`
below is a real, DB-backed behavioral test added specifically to catch
that class of bug: it evaluates the actual guard expression currently
present in the source file against a genuinely ORM-hydrated `Video` row
(status set via a committed session, exactly the way
_update_database_failure()'s own query would load it -- not a raw string
assignment).

unified_download_service.py itself still cannot be imported in this test
venv (module-level yt-dlp-dependent singleton, same constraint as #370's
tests for this file), which is why the guard expression is evaluated out
of the source text rather than by calling the real function directly.
"""

import re
from pathlib import Path

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "services"


class TestFailureWriteProtectsDownloadedStatus:
    def setup_method(self):
        self.source = (SRC_DIR / "unified_download_service.py").read_text()

    def _function_body(self, name):
        start = self.source.index(f"def {name}(")
        next_def = self.source.index("\n    def ", start + 10)
        return self.source[start:next_def]

    def test_checks_current_status_before_writing(self):
        body = self._function_body("_update_database_failure")
        assert "if video.status == VideoStatus.DOWNLOADED:" in body

    def test_the_downloaded_check_happens_before_any_status_or_download_row_write(self):
        body = self._function_body("_update_database_failure")
        check_index = body.index("if video.status == VideoStatus.DOWNLOADED:")
        status_write_index = body.index("video.status = VideoStatus.FAILED.value")
        assert check_index < status_write_index


@pytest.fixture
def downloaded_video():
    """A real, committed DOWNLOADED video row -- hydrated by the ORM the
    same way _update_database_failure()'s own query would load it, not a
    raw string assignment.
    """
    with get_db() as session:
        artist = Artist(name="Test Artist For Failure Guard")
        session.add(artist)
        session.flush()
        video = Video(
            artist_id=artist.id,
            title="Test Video For Failure Guard",
            status=VideoStatus.DOWNLOADED,
        )
        session.add(video)
        session.commit()
        video_id = video.id
        artist_id = artist.id
    yield video_id
    with get_db() as session:
        session.query(Video).filter(Video.id == video_id).delete()
        session.query(Artist).filter(Artist.id == artist_id).delete()
        session.commit()


class TestDownloadedStatusComparisonBugClass:
    """Directly proves the comparison bug class Finding 1 describes,
    against a real SQLite-backed, ORM-hydrated Video row.
    """

    def _guard_expression(self):
        source = (SRC_DIR / "unified_download_service.py").read_text()
        start = source.index("def _update_database_failure(")
        body = source[start : source.index("\n    def ", start + 10)]
        match = re.search(
            r"if (video\.status == VideoStatus\.DOWNLOADED(?:\.value)?):", body
        )
        assert (
            match
        ), "Could not locate the DOWNLOADED guard in _update_database_failure()"
        return match.group(1)

    def test_real_hydrated_downloaded_video_satisfies_the_actual_source_guard(
        self, downloaded_video
    ):
        """Evaluates the *actual guard expression currently in the source
        file* against a real, ORM-hydrated DOWNLOADED video. Fails
        against the buggy `.value`-suffixed comparison (which is always
        False), passes once Finding 1's fix drops the `.value` suffix.
        """
        with get_db() as session:
            video = session.query(Video).filter(Video.id == downloaded_video).first()
            assert video.status is VideoStatus.DOWNLOADED  # sanity: real ORM hydration

            expr = self._guard_expression()
            # eval() is safe here: `expr` is not external/untrusted input --
            # it's a substring matched by a fixed regex out of this repo's
            # own source file, deliberately re-evaluated (rather than
            # reimplemented) so this test tracks the guard's real text.
            result = eval(expr, {"video": video, "VideoStatus": VideoStatus})

            assert result is True, (
                f"_update_database_failure()'s guard expression `{expr}` "
                "evaluated False against a real DOWNLOADED video -- the "
                "safety net cannot fire (Finding 1)."
            )

    def test_the_value_suffixed_comparison_is_always_false(self, downloaded_video):
        """Directly demonstrates the bug class: comparing the hydrated
        enum member against VideoStatus.DOWNLOADED.value's plain string
        is never True, no matter the row's actual status -- while the
        bare-member comparison correctly reflects it."""
        with get_db() as session:
            video = session.query(Video).filter(Video.id == downloaded_video).first()
            assert (video.status == VideoStatus.DOWNLOADED) is True
            assert (video.status == VideoStatus.DOWNLOADED.value) is False
