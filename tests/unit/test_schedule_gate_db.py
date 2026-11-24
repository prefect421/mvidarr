"""#631: due_jobs() reads the SAVED settings, runs each job once, and a changed
setting takes effect without a restart (needs the settings cache to expire)."""

from datetime import datetime, timedelta

import pytest

from src.database.connection import get_db
from src.database.models import Setting
from src.services import schedule_gate
from src.services.schedule_gate import JOBS, _claim, _read_last_run, due_jobs
from src.services.settings_service import SettingsService

NOW = datetime(2026, 11, 23, 12, 0, 0)  # a Monday, 12:00 UTC


def _set(key, value):
    with get_db() as s:
        row = s.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            s.add(Setting(key=key, value=value))
        s.commit()
    SettingsService.reload_cache()


def _last(job):
    with get_db() as s:
        return _read_last_run(s, JOBS[job])[1]


@pytest.fixture(autouse=True)
def clean():
    with get_db() as s:
        s.query(Setting).delete()
        s.commit()
    SettingsService.reload_cache()
    yield
    with get_db() as s:
        s.query(Setting).delete()
        s.commit()
    SettingsService.reload_cache()


def test_first_sighting_starts_the_clock_and_does_not_run():
    assert due_jobs(NOW) == []
    assert _last("discovery") == NOW and _last("downloads") == NOW


def test_hourly_downloads_run_once_when_due_then_not_again():
    due_jobs(NOW)  # start the clocks
    _set("auto_download_schedule_days", "hourly")
    later = NOW + timedelta(minutes=61)
    assert JOBS["downloads"].task in due_jobs(later)
    assert JOBS["downloads"].task not in due_jobs(
        later + timedelta(minutes=1)
    )  # claimed


def test_disabled_job_never_runs():
    due_jobs(NOW)
    _set("auto_download_schedule_enabled", "false")
    assert JOBS["downloads"].task not in due_jobs(NOW + timedelta(hours=5))


def test_changed_setting_takes_effect_on_the_next_tick():
    due_jobs(NOW)
    # default downloads schedule is hourly: not due after 30 minutes...
    assert JOBS["downloads"].task not in due_jobs(NOW + timedelta(minutes=30))
    # ...the user switches it to every 6 hours; still not due at +3h
    _set("auto_download_schedule_days", "every_6_hours")
    assert JOBS["downloads"].task not in due_jobs(NOW + timedelta(hours=3))
    assert JOBS["downloads"].task in due_jobs(NOW + timedelta(hours=6, minutes=1))


def test_daily_discovery_runs_at_the_saved_time():
    due_jobs(NOW)  # last_run = 12:00 Mon
    _set("auto_discovery_schedule_days", "daily")
    _set("auto_discovery_schedule_time", "18:00")
    assert JOBS["discovery"].task not in due_jobs(NOW.replace(hour=17, minute=59))
    assert JOBS["discovery"].task in due_jobs(NOW.replace(hour=18, minute=1))


def test_playlist_sync_uses_the_saved_interval_in_minutes():
    due_jobs(NOW)
    _set("youtube_playlist_sync_interval", "60")
    assert JOBS["playlist-sync"].task not in due_jobs(NOW + timedelta(minutes=59))
    assert JOBS["playlist-sync"].task in due_jobs(NOW + timedelta(minutes=61))


def test_unparseable_saved_schedule_is_skipped_not_fatal():
    due_jobs(NOW)
    _set("auto_download_schedule_days", "sometimes")
    assert JOBS["downloads"].task not in due_jobs(NOW + timedelta(days=3))


def test_two_processes_cannot_both_claim_the_same_run():
    due_jobs(NOW)
    with get_db() as s:
        raw, _ = _read_last_run(s, JOBS["downloads"])
        assert _claim(s, JOBS["downloads"], raw, NOW + timedelta(hours=2)) is True
        # a second worker that read the same old value loses the race
        assert _claim(s, JOBS["downloads"], raw, NOW + timedelta(hours=2)) is False


class TestSettingsCacheExpires:
    """The Celery worker is a separate process: without expiry it never sees a
    change saved through the web UI until restarted (also affects #604's cap)."""

    def test_cache_refreshes_after_the_ttl(self):
        _set("some_key", "old")
        assert SettingsService.get("some_key") == "old"
        with get_db() as s:  # changed by ANOTHER process: this cache is not told
            s.query(Setting).filter(Setting.key == "some_key").update({"value": "new"})
            s.commit()
        assert SettingsService.get("some_key") == "old"  # still inside the TTL
        SettingsService._loaded_at -= SettingsService.CACHE_TTL_SECONDS + 1
        assert SettingsService.get("some_key") == "new"

    def test_a_failed_refresh_keeps_the_last_known_settings(self, monkeypatch):
        _set("some_key", "kept")
        SettingsService._loaded_at -= SettingsService.CACHE_TTL_SECONDS + 1
        monkeypatch.setattr(
            schedule_gate.SettingsService, "load_cache", SettingsService.load_cache
        )
        import src.services.settings_service as ss

        def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(ss, "get_db", boom)
        assert SettingsService.get("some_key") == "kept"
