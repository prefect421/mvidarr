"""Tests for migrations/025_drop_redundant_youtube_id_index.py (#379.4)."""

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parent.parent.parent
    / "migrations"
    / "025_drop_redundant_youtube_id_index.py"
)


class TestMigration025Structure:
    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists()

    def test_has_upgrade_and_downgrade_functions(self):
        source = MIGRATION_PATH.read_text()
        assert "def upgrade(connection):" in source
        assert "def downgrade(connection):" in source

    def test_upgrade_checks_for_existence_before_dropping(self):
        source = MIGRATION_PATH.read_text()
        assert "information_schema.statistics" in source
        assert "idx_video_youtube_id" in source

    def test_upgrade_is_idempotent_guarded(self):
        source = MIGRATION_PATH.read_text()
        # Must not unconditionally DROP INDEX without a preceding check
        drop_pos = source.index("DROP INDEX idx_video_youtube_id")
        check_pos = source.index("information_schema.statistics")
        assert check_pos < drop_pos
