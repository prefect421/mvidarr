"""
Migration 026: Widen videos.view_count and videos.like_count to BIGINT

Many popular music videos have more than 2,147,483,647 views (the INT maximum).
Storing such a count raised "Out of range value for column 'view_count'" and,
because playlist sync committed once at the end, rolled back the whole sync
(#630). Widening is lossless for existing data.

Date: 2026-11-23
"""

from sqlalchemy import text

COLUMNS = ("view_count", "like_count")


def _column_types(connection):
    rows = connection.execute(text("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = 'videos'
            AND column_name IN ('view_count', 'like_count')
            """)).fetchall()
    return {name: str(dtype).lower() for name, dtype in rows}


def upgrade(connection):
    """MODIFY each count column to BIGINT NULL unless it already is"""
    types = _column_types(connection)
    for column in COLUMNS:
        if column not in types:
            print(f"⚠️ videos.{column} not found (skipped)")
            continue
        if types[column] == "bigint":
            print(f"✅ videos.{column} already BIGINT (skipped)")
            continue
        connection.execute(text(f"ALTER TABLE videos MODIFY {column} BIGINT NULL"))
        print(f"✅ Widened videos.{column} to BIGINT")


def downgrade(connection):
    """Back to INT, clamping values that no longer fit so the ALTER succeeds"""
    types = _column_types(connection)
    for column in COLUMNS:
        if types.get(column) == "int":
            continue
        connection.execute(
            text(f"UPDATE videos SET {column} = 2147483647 WHERE {column} > 2147483647")
        )
        connection.execute(text(f"ALTER TABLE videos MODIFY {column} INT NULL"))
        print(f"✅ Reverted videos.{column} to INT (values above 2147483647 clamped)")
