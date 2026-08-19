"""
Migration 024: Add unique constraint on videos.youtube_id

Closes a duplicate-video-creation race (#377): two concurrent imports
of the same YouTube video could each pass the "does this video already
exist" pre-check and create two separate video rows, each independently
triggering its own download. Video.imvdb_id already had this
protection (unique=True); youtube_id did not.

MariaDB/MySQL unique indexes treat each NULL as distinct, so existing
videos without a youtube_id are unaffected.

Before adding the constraint, this migration checks for pre-existing
duplicate youtube_id values and raises a RuntimeError naming exactly
which values collide, plus the exact remediation SQL -- rather than
letting the raw ALTER TABLE fail with a bare MariaDB "Duplicate entry"
error and leave the operator with nothing actionable. Note this is
still a hard-fail on a database with real duplicates: a failed
migration is fatal to application startup (MigrationManager.migrate()
treats any migration failure as fatal and init_db.py does not start
the app), so any operator upgrading through this migration should run
the duplicate-check query below against production *before* deploying.

Date: 2026-08-18
"""

from sqlalchemy import text


def upgrade(connection):
    """Add unique index on videos.youtube_id"""
    # Idempotence check (#377 Finding 6): column-and-uniqueness-based,
    # not name-based. On a fresh install, create_all() already creates
    # the unique index from the unique=True column definition in
    # models.py *before* migrations run, under an auto-generated
    # SQLAlchemy name -- not this migration's own 'ux_videos_youtube_id'.
    # A name-based existence check would miss that and add a second,
    # differently-named unique index on the same column.
    result = connection.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'videos'
        AND column_name = 'youtube_id'
        AND non_unique = 0
    """))
    if result.scalar() > 0:
        print("✅ Unique index on videos.youtube_id already exists (skipped)")
        return

    # Duplicate pre-check: on any database that already has colliding
    # youtube_id values, the bare ALTER TABLE below fails with an
    # unhelpful "Duplicate entry" error -- and that failure is fatal to
    # application startup. Fail loudly here instead, naming exactly
    # which values collide and the exact remediation SQL.
    duplicates = connection.execute(text("""
        SELECT youtube_id, COUNT(*) as cnt FROM videos
        WHERE youtube_id IS NOT NULL AND youtube_id != ''
        GROUP BY youtube_id HAVING cnt > 1
    """)).fetchall()
    if duplicates:
        duplicate_list = ", ".join(f"{row[0]} ({row[1]}x)" for row in duplicates)
        raise RuntimeError(
            f"Cannot add unique index on videos.youtube_id: "
            f"{len(duplicates)} duplicate value(s) found: {duplicate_list}. "
            f"Resolve these first, e.g. by keeping the oldest row per "
            f"youtube_id and nulling out youtube_id on the others: "
            f"UPDATE videos v1 JOIN videos v2 ON v1.youtube_id = v2.youtube_id "
            f"AND v1.id > v2.id SET v1.youtube_id = NULL WHERE v1.youtube_id "
            f"IS NOT NULL; -- then re-run migrations."
        )

    connection.execute(text("""
        ALTER TABLE videos
        ADD UNIQUE INDEX ux_videos_youtube_id (youtube_id)
    """))
    print("✅ Added unique index ux_videos_youtube_id on videos.youtube_id")


def downgrade(connection):
    """Remove the unique index on videos.youtube_id, whatever it's
    actually named. #379.5: this used to hardcode DROP INDEX
    ux_videos_youtube_id, which fails on a fresh install where
    create_all() auto-created the unique index under a different,
    SQLAlchemy-generated name (upgrade() was already fixed to handle
    this asymmetry -- #377 Finding 6 -- but downgrade() was not).
    """
    result = connection.execute(text("""
        SELECT index_name FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'videos'
        AND column_name = 'youtube_id'
        AND non_unique = 0
        LIMIT 1
    """))
    row = result.fetchone()
    if not row:
        print("✅ No unique index on videos.youtube_id to remove (skipped)")
        return

    index_name = row[0]
    connection.execute(text(f"""
        ALTER TABLE videos
        DROP INDEX {index_name}
    """))
    print(f"✅ Removed unique index {index_name} from videos.youtube_id")
