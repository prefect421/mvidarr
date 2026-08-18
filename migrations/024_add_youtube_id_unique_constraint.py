"""
Migration 024: Add unique constraint on videos.youtube_id

Closes a duplicate-video-creation race (#377): two concurrent imports
of the same YouTube video could each pass the "does this video already
exist" pre-check and create two separate video rows, each independently
triggering its own download. Video.imvdb_id already had this
protection (unique=True); youtube_id did not.

MariaDB/MySQL unique indexes treat each NULL as distinct, so existing
videos without a youtube_id are unaffected.

Date: 2026-08-18
"""

from sqlalchemy import text


def upgrade(connection):
    """Add unique index on videos.youtube_id"""
    result = connection.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'videos'
        AND index_name = 'ux_videos_youtube_id'
    """))
    if result.scalar() == 0:
        connection.execute(text("""
            ALTER TABLE videos
            ADD UNIQUE INDEX ux_videos_youtube_id (youtube_id)
        """))
        print("✅ Added unique index ux_videos_youtube_id on videos.youtube_id")
    else:
        print("✅ ux_videos_youtube_id index already exists (skipped)")


def downgrade(connection):
    """Remove the unique index"""
    connection.execute(text("""
        ALTER TABLE videos
        DROP INDEX ux_videos_youtube_id
    """))
    print("✅ Removed unique index ux_videos_youtube_id from videos.youtube_id")
