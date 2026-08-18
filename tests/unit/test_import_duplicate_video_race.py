"""Tests for the import duplicate-video race fix (#377): a DB-level
unique constraint on Video.youtube_id, plus graceful IntegrityError
handling so a losing concurrent import gets an "already exists"
response instead of a raw 500. See tests/unit/conftest.py's
_REAL_DB_MODULES for why this module gets a real, unpatched get_db().
"""

import ast
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from src.api.fastapi.videos_import import _find_existing_video_after_integrity_error
from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "videos_import.py"
)


@pytest.fixture
def artist_id():
    """Creates a real Artist row, yields its id, cleans up after.

    NOTE: deviates from the brief's verbatim test body -- Video.artist_id
    is a NOT NULL foreign key, so Video rows cannot be created without one.
    The brief's example Video(...) calls omitted artist_id, which fails
    with `NOT NULL constraint failed: videos.artist_id` before the
    youtube_id constraint is ever exercised. Following the established
    pattern from test_claim_video_for_download.py's wanted_video fixture.
    """
    with get_db() as session:
        artist = Artist(name="Test Artist For Import Race")
        session.add(artist)
        session.commit()
        created_id = artist.id
    yield created_id
    with get_db() as session:
        session.query(Video).filter(Video.artist_id == created_id).delete()
        session.query(Artist).filter(Artist.id == created_id).delete()
        session.commit()


class TestYoutubeIdUniqueConstraint:
    def test_second_video_with_same_youtube_id_raises_integrity_error(self, artist_id):
        """Proves the DB-level constraint this task adds actually
        exists and is enforced -- this is what makes graceful
        duplicate-handling necessary and sufficient (#329 taught us
        that Python-level pre-checks alone don't close TOCTOU races;
        only a DB constraint does)."""
        with get_db() as session:
            session.add(
                Video(
                    artist_id=artist_id,
                    title="First",
                    youtube_id="dup123",
                    url="https://youtube.com/watch?v=dup123",
                    status=VideoStatus.MONITORED,
                    discovered_date=datetime.utcnow(),
                )
            )
            session.commit()

        with pytest.raises(IntegrityError):
            with get_db() as session:
                session.add(
                    Video(
                        artist_id=artist_id,
                        title="Second",
                        youtube_id="dup123",
                        url="https://youtube.com/watch?v=dup123",
                        status=VideoStatus.MONITORED,
                        discovered_date=datetime.utcnow(),
                    )
                )
                session.commit()

    def test_null_youtube_id_does_not_collide(self, artist_id):
        """MariaDB/SQLite unique indexes treat NULL as distinct --
        multiple untagged videos must still be insertable."""
        with get_db() as session:
            session.add(
                Video(
                    artist_id=artist_id,
                    title="No YouTube ID 1",
                    youtube_id=None,
                    status=VideoStatus.MONITORED,
                    discovered_date=datetime.utcnow(),
                )
            )
            session.add(
                Video(
                    artist_id=artist_id,
                    title="No YouTube ID 2",
                    youtube_id=None,
                    status=VideoStatus.MONITORED,
                    discovered_date=datetime.utcnow(),
                )
            )
            session.commit()  # must not raise


class TestImportEndpointsHandleIntegrityErrorGracefully:
    """Static source-assertion checks that both import endpoints
    actually catch IntegrityError and re-query rather than letting it
    500 -- see #329's precedent for why source-assertion is used here
    instead of importing this module directly."""

    def _function_source(self, function_name: str) -> str:
        text = SOURCE_PATH.read_text()
        tree = ast.parse(text)
        lines = text.splitlines(keepends=True)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
                start = node.lineno - 1
                end = node.end_lineno
                return "".join(lines[start:end])
        raise AssertionError(f"Could not find function {function_name!r}")

    def test_import_from_youtube_catches_integrity_error(self):
        source = self._function_source("import_from_youtube")
        assert "IntegrityError" in source

    def test_import_from_imvdb_catches_integrity_error(self):
        source = self._function_source("import_from_imvdb")
        assert "IntegrityError" in source

    def test_import_from_imvdb_uses_dual_field_requery_helper(self):
        """Strengthened per #377 Finding 5: the previous version of this
        test only checked for the bare presence of 'IntegrityError' in
        the source, which would still pass against the original,
        imvdb_id-only re-query bug. Assert the except handler actually
        calls the dual-field re-query helper, not a single-field
        `Video.imvdb_id == imvdb_id` query."""
        source = self._function_source("import_from_imvdb")
        except_pos = source.index("except IntegrityError:")
        except_to_end = source[except_pos:]
        assert "_find_existing_video_after_integrity_error(" in except_to_end


class TestFindExistingVideoAfterIntegrityErrorHelper:
    """Real, SQLite-backed behavioral coverage for the actual
    rollback -> re-query -> response-shape path in
    import_from_imvdb()'s IntegrityError handler (#377 Finding 5).

    import_from_imvdb() itself can't be exercised end-to-end here (it's
    an async FastAPI route needing a live IMVDb service call and a
    Request body), so this proves the dual-field re-query it now calls
    -- _find_existing_video_after_integrity_error() -- actually returns
    the right video for BOTH collision types: a pre-existing imvdb_id
    match, and a pre-existing youtube_id match (the case the original
    bug missed entirely, see Finding 4)."""

    def test_finds_existing_video_by_imvdb_id_match(self, artist_id):
        with get_db() as session:
            video = Video(
                artist_id=artist_id,
                title="IMVDb Match",
                imvdb_id="imvdb999",
                youtube_id=None,
                status=VideoStatus.MONITORED,
                discovered_date=datetime.utcnow(),
            )
            session.add(video)
            session.commit()
            expected_id = video.id

            found = _find_existing_video_after_integrity_error(
                session, imvdb_id="imvdb999", youtube_id=None
            )
            assert found is not None
            assert found.id == expected_id

    def test_finds_existing_video_by_youtube_id_match(self, artist_id):
        """The exact scenario Finding 4 fixes: a video discovered via
        YouTube first (so it has a youtube_id but no imvdb_id yet), then
        an IMVDb import for the same video collides on youtube_id, not
        imvdb_id. The old imvdb_id-only re-query found nothing here and
        surfaced as a 500; the new helper must find it."""
        with get_db() as session:
            video = Video(
                artist_id=artist_id,
                title="YouTube-First Match",
                imvdb_id=None,
                youtube_id="yt777",
                status=VideoStatus.MONITORED,
                discovered_date=datetime.utcnow(),
            )
            session.add(video)
            session.commit()
            expected_id = video.id

            # A different (non-colliding) imvdb_id is being imported for
            # this same video -- only youtube_id actually collides.
            found = _find_existing_video_after_integrity_error(
                session, imvdb_id="imvdb-does-not-collide", youtube_id="yt777"
            )
            assert found is not None
            assert found.id == expected_id

    def test_returns_none_when_neither_field_matches(self, artist_id):
        with get_db() as session:
            found = _find_existing_video_after_integrity_error(
                session, imvdb_id="nope", youtube_id="also-nope"
            )
            assert found is None
