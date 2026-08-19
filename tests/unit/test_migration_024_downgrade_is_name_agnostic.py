"""Test for migration 024's downgrade() fix (#379.5): must look up the
actual unique index name on videos.youtube_id rather than assuming a
hardcoded name, mirroring upgrade()'s existing column-based approach.
"""

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parent.parent.parent
    / "migrations"
    / "024_add_youtube_id_unique_constraint.py"
)


class TestMigration024DowngradeIsNameAgnostic:
    def test_downgrade_no_longer_hardcodes_the_index_name_in_a_bare_drop(self):
        source = MIGRATION_PATH.read_text()
        downgrade_source = source[source.index("def downgrade(connection):") :]
        # The old bug: an unconditional DROP INDEX ux_videos_youtube_id
        # with no lookup first. The fix must look up the actual index
        # name via information_schema before dropping.
        assert "information_schema.statistics" in downgrade_source
