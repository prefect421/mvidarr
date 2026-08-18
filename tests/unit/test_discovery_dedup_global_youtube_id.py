"""Behavioral tests for #377 Finding 1: video_discovery_service's
_store_discovered_video() dedup filter must be global on youtube_id,
not scoped per-artist, now that Video.youtube_id is a DB-level unique
column. Also proves the IntegrityError backstop added alongside it
actually recovers gracefully (rollback + no-op) rather than poisoning
the caller's session.

See tests/unit/conftest.py's _REAL_DB_MODULES for why this module gets
a real, unpatched get_db() backed by a throwaway SQLite file instead of
mocks -- this needs a real unique constraint to violate.
"""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.video_discovery_service import video_discovery_service


@pytest.fixture
def two_artists():
    """Creates two real Artist rows (A and B), yields their ids, cleans
    up after. Mirrors test_import_duplicate_video_race.py's artist_id
    fixture pattern."""
    with get_db() as session:
        artist_a = Artist(name="Discovery Dedup Artist A")
        artist_b = Artist(name="Discovery Dedup Artist B")
        session.add(artist_a)
        session.add(artist_b)
        session.commit()
        ids = (artist_a.id, artist_b.id)
    yield ids
    with get_db() as session:
        session.query(Video).filter(Video.artist_id.in_(ids)).delete(
            synchronize_session=False
        )
        session.query(Artist).filter(Artist.id.in_(ids)).delete(
            synchronize_session=False
        )
        session.commit()


class TestDiscoveryDedupGlobalYoutubeId:
    def test_same_youtube_id_under_different_artist_is_recognized_as_existing(
        self, two_artists
    ):
        """(a) A video already stored under artist A must be recognized
        as 'already exists' -- not re-inserted -- when artist B's
        discovery encounters the same youtube_id. Before the fix, the
        dedup filter included `Video.artist_id == artist_id`, so this
        lookup would find nothing (wrong artist), fall through to
        session.add()/flush(), and raise IntegrityError against the
        global unique constraint on youtube_id."""
        artist_a_id, artist_b_id = two_artists

        with get_db() as session:
            existing_video = Video(
                artist_id=artist_a_id,
                title="Collab Video",
                youtube_id="collab123",
                url="https://youtube.com/watch?v=collab123",
                status=VideoStatus.MONITORED,
                discovered_date=datetime.utcnow(),
            )
            session.add(existing_video)
            session.commit()

            # Artist B's discovery encounters the same YouTube video
            # (e.g. a collaboration officially uploaded to artist A's
            # channel that also surfaces in a search for artist B).
            video_discovery_service._store_discovered_video(
                session,
                artist_b_id,
                {
                    "title": "Artist B - Collab Video",
                    "youtube_id": "collab123",
                    "url": "https://youtube.com/watch?v=collab123",
                    "source": "youtube",
                },
            )
            session.commit()

            # No duplicate row was created, no exception was raised, and
            # the session is still usable afterward.
            matches = session.query(Video).filter(Video.youtube_id == "collab123").all()
            assert len(matches) == 1
            assert matches[0].artist_id == artist_a_id

    def test_integrity_error_on_flush_is_caught_and_session_recovers(self, two_artists):
        """(b) Exercises the `except IntegrityError` backstop directly:
        pre-insert a colliding video, then bypass the dedup check (by
        stubbing session.query for the Video model only) to force
        _store_discovered_video() to reach session.add()/flush()
        against an already-colliding youtube_id. The function must
        catch the IntegrityError, roll back, and return without raising
        -- and critically, the session must remain usable afterward
        (not left in a pending-rollback state), which is what actually
        protects the rest of a discovery run's loop."""
        artist_a_id, artist_b_id = two_artists

        with get_db() as session:
            existing_video = Video(
                artist_id=artist_a_id,
                title="Race Video",
                youtube_id="race123",
                url="https://youtube.com/watch?v=race123",
                status=VideoStatus.MONITORED,
                discovered_date=datetime.utcnow(),
            )
            session.add(existing_video)
            session.commit()

            real_query = session.query

            class _NoMatchQuery:
                """Stand-in for the dedup query only -- always reports
                'nothing found', simulating the TOCTOU window where a
                concurrent insert commits between the check and this
                function's own flush()."""

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
                # Must not raise -- the IntegrityError from the flush
                # below is caught internally.
                video_discovery_service._store_discovered_video(
                    session,
                    artist_b_id,
                    {
                        "title": "Artist B - Race Video",
                        "youtube_id": "race123",
                        "url": "https://youtube.com/watch?v=race123",
                        "source": "youtube",
                    },
                )
            finally:
                session.query = real_query

            # Session must still be usable -- proves session.rollback()
            # inside the except branch actually ran (a PendingRollbackError
            # here would mean the session was left poisoned, exactly the
            # bug this finding closes).
            matches = session.query(Video).filter(Video.youtube_id == "race123").all()
            assert len(matches) == 1  # still just the original row
            assert matches[0].artist_id == artist_a_id

            # And a completely unrelated write on the same session must
            # still succeed -- the strongest proof the session isn't
            # poisoned.
            session.add(
                Video(
                    artist_id=artist_b_id,
                    title="Unrelated Video",
                    youtube_id="unrelated123",
                    status=VideoStatus.MONITORED,
                    discovered_date=datetime.utcnow(),
                )
            )
            session.commit()
