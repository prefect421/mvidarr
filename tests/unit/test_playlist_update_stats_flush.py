"""Live-reported: a newly-created dynamic playlist ("test", filter
"High definition videos (720p and above)") showed "0 videos" even
though its filter genuinely matched 3 videos -- confirmed live: the 3
correct PlaylistEntry rows were actually created and committed, but
playlists.video_count was stuck at 0.

Root cause: the app's real session factory
(DatabaseManager.create_session_factory() in
src/database/connection.py) configures autoflush=False. Every
create-a-dynamic-playlist code path adds new PlaylistEntry rows via
session.add(...)/session.add_all(...), then immediately calls
playlist.update_stats() (Playlist.update_stats() in
src/database/models.py) in the SAME uncommitted transaction, without
an intervening flush. update_stats() queries
`session.query(func.count(PlaylistEntry.id))...` for an "accurate"
count (a comment there cites #177, an EARLIER staleness bug this
method was written to fix) -- but with autoflush disabled, that COUNT
query runs against the database's pre-transaction state, missing the
still-pending, unflushed inserts, and returns 0. The entries
themselves get flushed correctly moments later at session.commit(),
but by then video_count has already been computed and cached as 0 on
the Python object.

Fix: update_stats() now flushes its own session (if it has one)
before running its count/duration queries, guaranteeing an accurate
result regardless of caller flush discipline or autoflush
configuration -- fixing this at the one shared method rather than at
each of the 6 call sites across playlists_crud.py, playlists_features.py,
and dynamic_playlist_service.py that add entries and then call it.
"""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import Playlist, PlaylistEntry, PlaylistType, Video


def _session_with_autoflush_disabled():
    # Matches the real app's DatabaseManager.create_session_factory():
    # sessionmaker(autocommit=False, autoflush=False, bind=engine).
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Playlist.__table__, PlaylistEntry.__table__, Video.__table__],
    )
    return sessionmaker(bind=engine, autoflush=False)()


class TestPlaylistUpdateStatsFlushesBeforeCounting:
    def test_counts_entries_added_earlier_in_the_same_unflushed_transaction(self):
        session = _session_with_autoflush_disabled()
        playlist = Playlist(
            name="test",
            user_id=1,
            playlist_type=PlaylistType.DYNAMIC,
            filter_criteria={"quality": ["1080p"]},
        )
        session.add(playlist)
        session.flush()  # only to obtain playlist.id, mirrors both real call sites

        for i, video_id in enumerate((171, 93, 21), start=1):
            session.add(
                PlaylistEntry(
                    playlist_id=playlist.id,
                    video_id=video_id,
                    position=i,
                    added_at=datetime.utcnow(),
                )
            )
        # Deliberately no flush here -- reproduces the live bug exactly:
        # autoflush is off, and update_stats() must not depend on the
        # caller having flushed.

        playlist.update_stats()

        assert playlist.video_count == 3

    def test_zero_entries_still_yields_zero_not_an_error(self):
        session = _session_with_autoflush_disabled()
        playlist = Playlist(name="empty", user_id=1, playlist_type=PlaylistType.STATIC)
        session.add(playlist)
        session.flush()

        playlist.update_stats()

        assert playlist.video_count == 0
