"""Regression/feature test for #370: webhook events were never actually
triggered by real application activity -- webhook_service.py defines 17
trigger_* convenience functions with zero call sites anywhere else in
src/. This wires the three highest-value, unambiguous ones (per the
brainstorming conversation): video.downloaded, video.download_failed
(both in UnifiedDownloadService._execute_download(), the one real
download orchestration point), and artist.added (in create_artist()).
download.started/completed/failed and the remaining 12 event types are
deliberately deferred -- see the issue for the full scope discussion.

Static source-text assertions rather than real function calls, for two
different environmental reasons per file:

- unified_download_service.py cannot be imported at all in this test
  venv: it instantiates a module-level UnifiedDownloadService() singleton
  that requires a real yt-dlp binary (RuntimeError: yt-dlp executable
  not found) -- the same root cause as the 4 pre-existing environmentally
  broken test files this session's test runs already exclude.
- create_artist() has heavy SQLAlchemy session / auto-processing-service
  dependencies with no existing mocking precedent in this test suite to
  build a real behavioral test against without substantial new
  infrastructure disproportionate to a one-line trigger call.
"""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src"


class TestVideoDownloadEventsWired:
    def setup_method(self):
        self.source = (SRC_DIR / "services" / "unified_download_service.py").read_text()

    def test_imports_the_trigger_functions(self):
        assert "trigger_video_downloaded" in self.source
        assert "trigger_video_download_failed" in self.source

    def test_success_path_triggers_video_downloaded_after_db_update(self):
        # _update_database_success() marks the video DOWNLOADED in the DB;
        # the trigger call must come after that, not before, so a
        # notification never fires for a video the DB doesn't yet show
        # as downloaded.
        marker = "self._update_database_success(context.video_id, result)"
        start = self.source.index(marker)
        # Look at the ~15 lines following the DB update for the trigger call.
        window = self.source[start : start + 600]
        assert "trigger_video_downloaded(" in window

    def test_failure_path_triggers_video_download_failed(self):
        # Both failure call sites in _execute_download(): the normal
        # (result.success is False) path and the caught-exception path.
        failure_markers = [
            m for m in self.source.split("_update_database_failure(")[1:]
        ]
        assert len(failure_markers) >= 2, (
            "expected both the normal-failure and exception-path calls "
            "to _update_database_failure() to be present"
        )
        # trigger_video_download_failed must appear at least twice --
        # once following each _update_database_failure() call site.
        assert self.source.count("trigger_video_download_failed(") >= 2

    def test_triggered_video_data_includes_title_and_artist_name(self):
        # Discord/Apprise's description-building both read data["title"]
        # and data["artist_name"] specifically (not e.g. "artist") --
        # confirmed against discord_notification_formatter.py's
        # _description_for().
        start = self.source.index("trigger_video_downloaded(")
        end = self.source.index(")", start)
        call_site = self.source[start : end + 1]
        assert '"title"' in call_site
        assert '"artist_name"' in call_site


class TestArtistAddedEventWired:
    def setup_method(self):
        self.source = (SRC_DIR / "api" / "fastapi" / "artists_crud.py").read_text()

    def test_imports_the_trigger_function(self):
        assert "trigger_artist_added" in self.source

    def test_fires_after_commit_not_before(self):
        # Firing before session.commit() would notify about an artist
        # that a concurrent failure could still roll back.
        commit_index = self.source.index(
            "session.commit()", self.source.index("def create_artist")
        )
        trigger_index = self.source.index(
            "trigger_artist_added(", self.source.index("def create_artist")
        )
        assert trigger_index > commit_index

    def test_triggered_artist_data_includes_name(self):
        start = self.source.index("trigger_artist_added(")
        end = self.source.index(")", start)
        call_site = self.source[start : end + 1]
        assert '"name"' in call_site
