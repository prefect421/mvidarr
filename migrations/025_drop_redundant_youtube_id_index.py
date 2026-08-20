"""
Migration 025: Drop redundant idx_video_youtube_id index

#377 added a unique index (ux_videos_youtube_id) on videos.youtube_id
and removed the old non-unique Index("idx_video_youtube_id", ...)
declaration from the SQLAlchemy model -- but never dropped the
physical index itself from databases that already had it (i.e.
existing/production databases; fresh installs never had the old index
in the first place, since create_all() only ever reflects the current
model). Harmless (MariaDB permits duplicate indexes on the same
column) but wasteful (#379.4).

Date: 2026-08-18
"""

from sqlalchemy import text


def upgrade(connection):
    """Drop the old non-unique idx_video_youtube_id index if present"""
    result = connection.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'videos'
        AND index_name = 'idx_video_youtube_id'
    """))
    if result.scalar() == 0:
        print("✅ idx_video_youtube_id already absent (skipped)")
        return

    connection.execute(text("""
        ALTER TABLE videos
        DROP INDEX idx_video_youtube_id
    """))
    print("✅ Dropped redundant idx_video_youtube_id index from videos.youtube_id")


def downgrade(connection):
    """Recreate the old non-unique index, if not already present.

    #385: guards symmetrically with upgrade() above -- without this
    check, re-running downgrade() (or downgrading when the index is
    already present) errors with MariaDB 1061 (duplicate key name).
    """
    result = connection.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'videos'
        AND index_name = 'idx_video_youtube_id'
    """))
    if result.scalar() > 0:
        print("✅ idx_video_youtube_id already present (skipped)")
        return

    connection.execute(text("""
        ALTER TABLE videos
        ADD INDEX idx_video_youtube_id (youtube_id)
    """))
    print("✅ Recreated idx_video_youtube_id index on videos.youtube_id")
