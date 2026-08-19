"""Real (SQLite-backed) test proving the savepoint fix for #379.1:
video_discovery_service.py's IntegrityError backstop (#377) must only
discard the ONE failed insert, not every video flushed earlier in the
same discovery batch.

Forcing a genuine IntegrityError via a pre-committed colliding row
doesn't reliably trigger the dedup-miss-then-flush-collision path in
SQLite the way it does in MariaDB, so -- mirroring the proven pattern in
test_discovery_dedup_global_youtube_id.py's
test_integrity_error_on_flush_is_caught_and_session_recovers -- the
dedup query's `existing` result is monkeypatched to `None` for the
colliding call only, forcing _store_discovered_video() to reach
session.add()/flush() against an already-colliding youtube_id.
"""

from datetime import datetime

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.video_discovery_service import VideoDiscoveryService


@pytest.fixture
def artist():
    with get_db() as session:
        a = Artist(name="Test Artist")
        session.add(a)
        session.flush()
        return a.id


class TestDiscoverySavepointPreservesEarlierInserts:
    def test_a_collision_only_discards_the_colliding_insert(self, artist):
        service = VideoDiscoveryService()

        with get_db() as session:
            # Simulate the caller's loop: one video stores successfully
            # (flushed, not yet committed -- discover_videos_for_artist()
            # only commits once, after its whole loop).
            service._store_discovered_video(
                session,
                artist,
                {
                    "title": "First Video",
                    "youtube_id": "first123",
                    "url": "https://youtube.com/watch?v=first123",
                },
            )

            # A second video collides (simulating a concurrent insert
            # that already landed this youtube_id -- forced directly in
            # this same session/transaction for a deterministic test.
            # Note: a genuinely separate, still-open session can't be
            # used here -- SQLite's file-level write lock means a
            # second session trying to insert while this session still
            # holds an uncommitted write (the "First Video" flush above)
            # would just block/raise "database is locked" rather than
            # cleanly simulating a concurrent commit. The unique
            # constraint on youtube_id is enforced at flush time
            # regardless of whether the colliding row is committed, so
            # inserting it directly here reproduces the same collision
            # the flush below needs to hit.)
            session.add(
                Video(
                    artist_id=artist,
                    title="Concurrent Insert",
                    youtube_id="dup456",
                    url="https://youtube.com/watch?v=dup456",
                    status=VideoStatus.MONITORED,
                    discovered_date=datetime.utcnow(),
                )
            )
            session.flush()

            # Bypass the dedup check (Video model only) so the colliding
            # call falls through to session.add()/flush() and actually
            # hits the IntegrityError backstop, mirroring the TOCTOU
            # race the check-first dedup can't fully close.
            real_query = session.query

            class _NoMatchQuery:
                def filter(self, *args, **kwargs):
                    return self

                def first(self):
                    return None

            def _query_stub(model, *args, **kwargs):
                if model is Video:
                    return _NoMatchQuery()
                return real_query(model, *args, **kwargs)

            session.query = _query_stub
            try:
                service._store_discovered_video(
                    session,
                    artist,
                    {
                        "title": "Colliding Video",
                        "youtube_id": "dup456",
                        "url": "https://youtube.com/watch?v=dup456-different-path",
                    },
                )
            finally:
                session.query = real_query

            # The first video must still be present in this session
            # after the collision -- proving the savepoint rolled back
            # only the failed insert, not the whole session.
            first = session.query(Video).filter(Video.youtube_id == "first123").first()
            assert first is not None
            assert first.title == "First Video"

            # The caller's eventual commit must succeed and actually
            # persist the first video.
            session.commit()

        with get_db() as verify_session:
            persisted = (
                verify_session.query(Video)
                .filter(Video.youtube_id == "first123")
                .first()
            )
            assert persisted is not None
