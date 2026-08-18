"""
Migration 023: Add last_known_video_id to playlist_monitors for incremental sync

This migration adds a field to track the last known video ID in each monitored playlist,
enabling incremental sync that only fetches new videos instead of re-downloading the
entire playlist every time.

Benefit: Reduces YouTube API quota usage by 75% for playlist syncs
(from 4 full syncs/day to 1 full + 3 incremental syncs/day)

Date: 2026-01-30
"""

from sqlalchemy import text


def upgrade(connection):
    """Add last_known_video_id column to playlist_monitors table"""
    # Check if column already exists (create_all may have added it from the model)
    result = connection.execute(
        text(
            """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'playlist_monitors'
        AND column_name = 'last_known_video_id'
    """
        )
    )
    if result.scalar() == 0:
        connection.execute(
            text(
                """
            ALTER TABLE playlist_monitors
            ADD COLUMN last_known_video_id VARCHAR(20) NULL
            COMMENT 'Last known video ID for incremental sync - YouTube quota optimization'
        """
            )
        )
        print("✅ Added last_known_video_id column to playlist_monitors table")
    else:
        print("✅ last_known_video_id column already exists (skipped)")


def downgrade(connection):
    """Remove last_known_video_id column from playlist_monitors table"""
    connection.execute(
        text(
            """
        ALTER TABLE playlist_monitors
        DROP COLUMN last_known_video_id
    """
        )
    )
    print("✅ Removed last_known_video_id column from playlist_monitors table")
