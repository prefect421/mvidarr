"""
Migration 024: Add unique constraint on videos.youtube_id

Closes a duplicate-video-creation race (#377): two concurrent imports
of the same YouTube video could each pass the "does this video already
exist" pre-check and create two separate video rows, each independently
triggering its own download. Video.imvdb_id already had this
protection (unique=True); youtube_id did not.

MariaDB/MySQL unique indexes treat each NULL as distinct, so existing
videos without a youtube_id are unaffected.

Before adding the constraint, this migration auto-resolves any
pre-existing duplicate youtube_id values rather than requiring the
operator to run remediation SQL by hand before upgrading (the original
version of this migration hard-failed with instructions -- a manual DB
step is a bad fit for this project's self-hosting audience, and a
failed migration is fatal to application startup, so a duplicate the
operator didn't know about would just brick the upgrade). For each
group of rows sharing a youtube_id, _pick_survivor() keeps it on
whichever row actually has a downloaded file (or failing that, whichever
is DOWNLOADED, or failing that, the oldest row) and clears it (NULL,
never a delete) on the rest -- no data is lost, the losing rows just
stop being linked by that youtube_id. Each resolution is printed so an
operator can review what happened.

Date: 2026-08-18
"""

from sqlalchemy import text


def _pick_survivor(rows):
    """Given candidate rows that share a duplicate youtube_id (each a
    mapping with 'id', 'local_path', 'status'), decide which one keeps
    it. Priority: has an actual downloaded file (local_path set) >
    status is DOWNLOADED > oldest id (first discovered) as the final
    tiebreaker. Pulled out as a pure function so the decision itself is
    unit-testable without a database.
    """

    def sort_key(row):
        return (
            0 if row["local_path"] else 1,
            0 if row["status"] == "DOWNLOADED" else 1,
            row["id"],
        )

    return min(rows, key=sort_key)


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

    # Auto-resolve pre-existing duplicates before the ALTER TABLE below,
    # which would otherwise fail with a bare, unhelpful MariaDB
    # "Duplicate entry" error.
    duplicate_youtube_ids = connection.execute(text("""
        SELECT youtube_id FROM videos
        WHERE youtube_id IS NOT NULL AND youtube_id != ''
        GROUP BY youtube_id HAVING COUNT(*) > 1
    """)).fetchall()

    if duplicate_youtube_ids:
        print(
            f"⚠️  Found {len(duplicate_youtube_ids)} duplicate youtube_id "
            f"value(s) -- auto-resolving before adding the unique index"
        )
        for (yt_id,) in duplicate_youtube_ids:
            rows = [
                dict(row._mapping)
                for row in connection.execute(
                    text(
                        "SELECT id, title, local_path, status FROM videos "
                        "WHERE youtube_id = :yt_id"
                    ),
                    {"yt_id": yt_id},
                ).fetchall()
            ]
            survivor = _pick_survivor(rows)
            for row in rows:
                if row["id"] == survivor["id"]:
                    continue
                connection.execute(
                    text("UPDATE videos SET youtube_id = NULL WHERE id = :id"),
                    {"id": row["id"]},
                )
                print(
                    f"   youtube_id {yt_id}: kept on video #{survivor['id']} "
                    f"({survivor['title']!r}), cleared on duplicate "
                    f"video #{row['id']} ({row['title']!r})"
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
    # #385: seq_in_index = 1 + ORDER BY make this deterministic. Without
    # them, a composite unique index containing youtube_id as a
    # non-first column (none exists today, but nothing prevents one
    # being added later) could be nondeterministically selected instead
    # of the intended single-column index.
    result = connection.execute(text("""
        SELECT index_name FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'videos'
        AND column_name = 'youtube_id'
        AND non_unique = 0
        AND seq_in_index = 1
        ORDER BY index_name
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
