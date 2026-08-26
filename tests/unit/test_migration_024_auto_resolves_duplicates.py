"""Tests for migration 024's switch from hard-failing on pre-existing
duplicate youtube_id values (requiring an operator to run remediation SQL
by hand before the app would even start) to auto-resolving them.

_pick_survivor() is a pure function extracted specifically so this
decision logic is unit-testable without a database -- see
tests/unit/test_youtube_download_engine_pure_helpers.py and friends for
the established pattern of pulling migration/service decision logic out
of raw SQL or I/O so it can be tested directly.
"""

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parent.parent.parent
    / "migrations"
    / "024_add_youtube_id_unique_constraint.py"
)


def _load_migration_024():
    spec = importlib.util.spec_from_file_location(
        "migration_024_test_import", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(id, local_path=None, status="WANTED"):
    return {
        "id": id,
        "title": f"video {id}",
        "local_path": local_path,
        "status": status,
    }


class TestPickSurvivorPrefersADownloadedFile:
    def test_row_with_local_path_wins_over_one_without(self):
        migration_024 = _load_migration_024()
        rows = [_row(1, local_path=None), _row(2, local_path="/data/videos/2.mp4")]
        survivor = migration_024._pick_survivor(rows)
        assert survivor["id"] == 2

    def test_order_in_the_list_does_not_matter(self):
        migration_024 = _load_migration_024()
        rows = [_row(2, local_path="/data/videos/2.mp4"), _row(1, local_path=None)]
        survivor = migration_024._pick_survivor(rows)
        assert survivor["id"] == 2


class TestPickSurvivorFallsBackToStatus:
    def test_downloaded_status_wins_when_neither_has_a_local_path(self):
        # Edge case: status says DOWNLOADED but local_path is missing
        # (e.g. the file was later moved/deleted outside the app) --
        # still a better signal than a WANTED placeholder.
        migration_024 = _load_migration_024()
        rows = [_row(1, status="WANTED"), _row(2, status="DOWNLOADED")]
        survivor = migration_024._pick_survivor(rows)
        assert survivor["id"] == 2


class TestPickSurvivorFallsBackToOldestId:
    def test_oldest_id_wins_when_all_else_is_equal(self):
        migration_024 = _load_migration_024()
        rows = [_row(5), _row(2), _row(9)]
        survivor = migration_024._pick_survivor(rows)
        assert survivor["id"] == 2

    def test_three_way_tie_still_prefers_the_one_with_a_file(self):
        migration_024 = _load_migration_024()
        rows = [_row(1), _row(2, local_path="/data/videos/2.mp4"), _row(3)]
        survivor = migration_024._pick_survivor(rows)
        assert survivor["id"] == 2


class TestUpgradeNoLongerHardFailsOnDuplicates:
    """The whole point of this change: an operator upgrading through
    024 with pre-existing duplicates should not need to SSH into the
    database and run remediation SQL before the app will even start.
    """

    def test_upgrade_does_not_raise_runtimeerror_on_duplicates(self):
        source = MIGRATION_PATH.read_text()
        assert "raise RuntimeError" not in source

    def test_upgrade_still_finds_duplicate_groups(self):
        source = MIGRATION_PATH.read_text()
        assert "GROUP BY youtube_id HAVING COUNT(*) > 1" in source

    def test_resolution_clears_youtube_id_rather_than_deleting_the_row(self):
        # No data loss: the losing row keeps everything except the
        # youtube_id link.
        source = MIGRATION_PATH.read_text()
        assert "UPDATE videos SET youtube_id = NULL WHERE id = :id" in source
        assert "DELETE FROM videos" not in source
