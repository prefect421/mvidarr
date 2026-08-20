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


class TestMigration024DowngradeIndexLookupSafety:
    """#385: the index-name lookup filters on column_name and
    non_unique alone, with no seq_in_index/ORDER BY safety. If a
    composite unique index containing youtube_id as a non-first column
    were ever added, this could nondeterministically pick the wrong
    index to drop. Low likelihood today, cheap to tighten."""

    def test_filters_to_the_first_column_position_in_the_index(self):
        source = MIGRATION_PATH.read_text()
        downgrade_source = source[source.index("def downgrade(connection):") :]
        assert "seq_in_index = 1" in downgrade_source

    def test_orders_results_for_determinism(self):
        source = MIGRATION_PATH.read_text()
        downgrade_source = source[source.index("def downgrade(connection):") :]
        assert "order by" in downgrade_source.lower()
