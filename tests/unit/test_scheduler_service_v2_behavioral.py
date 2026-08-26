"""#317: second pass on SchedulerServiceV2 (566 lines), this issue's
own stated top concern. #467 covered _parse_schedule(); this covers
the rest of the file's real, branching logic -- state transitions
(start/stop), health-status combining, Celery Beat schedule
read/write, and manual trigger dispatch. All previously untested.

SchedulerServiceV2.__init__() does no I/O (just plain attribute
assignment, including binding self.celery to the already-constructed
module-level celery_app singleton) -- safe to construct directly, then
swap self.celery for a fake for isolated testing rather than touching
the real app's Celery config.
"""

from unittest.mock import MagicMock, patch

from src.services.scheduler_service_v2 import SchedulerServiceV2


def _service():
    service = SchedulerServiceV2()
    service.celery = MagicMock()
    service.celery.conf.beat_schedule = {}
    return service


class TestGetHealth:
    """Pure state-combining logic given 3 inputs (enabled, running,
    celery_connected) -- no DB/Celery I/O once those are mocked."""

    def test_enabled_running_and_connected_is_healthy(self):
        service = _service()
        with patch.object(
            service, "_check_celery_connection", return_value=True
        ), patch.object(service, "is_enabled", return_value=True):
            service._is_running = True
            result = service.get_health()
        assert result["status"] == "healthy"

    def test_enabled_but_not_running_is_stopped_regardless_of_celery(self):
        service = _service()
        with patch.object(
            service, "_check_celery_connection", return_value=True
        ), patch.object(service, "is_enabled", return_value=True):
            service._is_running = False
            result = service.get_health()
        assert result["status"] == "stopped"

    def test_celery_disconnected_while_running_is_degraded(self):
        service = _service()
        with patch.object(
            service, "_check_celery_connection", return_value=False
        ), patch.object(service, "is_enabled", return_value=True):
            service._is_running = True
            result = service.get_health()
        assert result["status"] == "degraded"

    def test_result_includes_the_raw_component_flags(self):
        service = _service()
        with patch.object(
            service, "_check_celery_connection", return_value=True
        ), patch.object(service, "is_enabled", return_value=True):
            service._is_running = True
            result = service.get_health()
        assert result["enabled"] is True
        assert result["running"] is True
        assert result["celery_connected"] is True
        assert "timestamp" in result

    def test_an_internal_exception_reports_error_status_not_a_crash(self):
        service = _service()
        with patch.object(
            service, "_check_celery_connection", side_effect=RuntimeError("boom")
        ):
            result = service.get_health()
        assert result["status"] == "error"
        assert "timestamp" in result


class TestStartStop:
    def test_start_refuses_when_disabled_in_settings(self):
        service = _service()
        with patch.object(service, "is_enabled", return_value=False):
            result = service.start()
        assert result["status"] == "disabled"
        assert service._is_running is False

    def test_start_refuses_when_already_running(self):
        service = _service()
        service._is_running = True
        with patch.object(service, "is_enabled", return_value=True):
            result = service.start()
        assert result["status"] == "already_running"

    def test_start_updates_schedules_and_flips_the_running_flag(self):
        service = _service()
        with patch.object(service, "is_enabled", return_value=True), patch.object(
            service, "update_schedule_from_settings", return_value={}
        ) as mock_update, patch.object(
            service, "get_current_schedules", return_value={"x": {}}
        ):
            result = service.start()
        assert result["status"] == "started"
        assert service._is_running is True
        mock_update.assert_called_once()

    def test_start_that_raises_reports_error_and_does_not_flip_the_flag(self):
        service = _service()
        with patch.object(service, "is_enabled", return_value=True), patch.object(
            service,
            "update_schedule_from_settings",
            side_effect=RuntimeError("db down"),
        ):
            result = service.start()
        assert result["status"] == "error"
        assert service._is_running is False

    def test_stop_refuses_when_not_running(self):
        service = _service()
        result = service.stop()
        assert result["status"] == "not_running"

    def test_stop_flips_the_running_flag(self):
        service = _service()
        service._is_running = True
        result = service.stop()
        assert result["status"] == "stopped"
        assert service._is_running is False


class TestGetCurrentSchedules:
    def test_only_includes_scheduled_and_artist_prefixed_entries(self):
        service = _service()
        service.celery.conf.beat_schedule = {
            "scheduled-discovery": {"task": "x.discovery", "schedule": "daily"},
            "artist-42-check": {"task": "x.artist_check", "schedule": "weekly"},
            "some-unrelated-celery-internal-entry": {
                "task": "celery.backend_cleanup",
                "schedule": "hourly",
            },
        }
        result = service.get_current_schedules()
        assert set(result.keys()) == {"scheduled-discovery", "artist-42-check"}

    def test_returns_empty_dict_on_internal_error_rather_than_raising(self):
        service = _service()
        service.celery.conf.beat_schedule = None  # .items() will raise
        result = service.get_current_schedules()
        assert result == {}


class TestUpdateScheduleFromSettings:
    def test_adds_a_discovery_entry_when_enabled(self):
        service = _service()
        with patch(
            "src.services.scheduler_service_v2.SettingsService"
        ) as mock_settings:
            mock_settings.get_bool.side_effect = lambda key, default: {
                "auto_discovery_schedule_enabled": True,
                "auto_download_schedule_enabled": False,
            }.get(key, default)
            mock_settings.get.side_effect = lambda key, default: {
                "auto_discovery_schedule_time": "06:00",
                "auto_discovery_schedule_days": "daily",
            }.get(key, default)

            result = service.update_schedule_from_settings()

        assert "scheduled-discovery" in result["schedules"]
        assert "scheduled-downloads" not in result["schedules"]
        assert "scheduled-discovery" in service.celery.conf.beat_schedule

    def test_skips_both_entries_when_both_disabled(self):
        service = _service()
        with patch(
            "src.services.scheduler_service_v2.SettingsService"
        ) as mock_settings:
            mock_settings.get_bool.return_value = False
            mock_settings.get.return_value = "06:00"

            result = service.update_schedule_from_settings()

        assert result["schedules_updated"] == 0
        assert result["schedules"] == {}

    def test_an_unparseable_schedule_is_silently_skipped_not_an_error(self):
        # frequency "not-a-real-frequency" -> _parse_schedule() returns
        # None -> the entry is skipped, but the overall call still
        # succeeds (status "updated", not "error").
        service = _service()
        with patch(
            "src.services.scheduler_service_v2.SettingsService"
        ) as mock_settings:
            mock_settings.get_bool.side_effect = lambda key, default: {
                "auto_discovery_schedule_enabled": True,
                "auto_download_schedule_enabled": False,
            }.get(key, default)
            mock_settings.get.side_effect = lambda key, default: {
                "auto_discovery_schedule_time": "06:00",
                "auto_discovery_schedule_days": "not-a-real-frequency",
            }.get(key, default)

            result = service.update_schedule_from_settings()

        assert result["status"] == "updated"
        assert result["schedules_updated"] == 0


class TestCheckCeleryConnection:
    def test_true_when_celery_inspect_reports_active_workers(self):
        service = _service()
        service.celery.control.inspect.return_value.stats.return_value = {
            "worker1@host": {}
        }
        assert service._check_celery_connection() is True

    def test_falls_back_to_a_process_check_when_inspect_finds_nothing(self):
        service = _service()
        service.celery.control.inspect.return_value.stats.return_value = None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="user 123 ... celery worker -A src.jobs.celery_app\n"
            )
            assert service._check_celery_connection() is True

    def test_false_when_neither_check_finds_anything(self):
        service = _service()
        service.celery.control.inspect.return_value.stats.return_value = None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="no relevant processes here\n")
            assert service._check_celery_connection() is False

    def test_false_when_inspect_itself_raises(self):
        service = _service()
        service.celery.control.inspect.side_effect = RuntimeError("no broker")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="")
            assert service._check_celery_connection() is False


class TestTriggerDiscoveryNow:
    def test_global_discovery_dispatches_the_global_task(self):
        service = _service()
        fake_result = MagicMock(id="task-123")
        with patch("src.tasks.scheduled_tasks.scheduled_discovery_task") as mock_task:
            mock_task.apply_async.return_value = fake_result
            result = service.trigger_discovery_now()

        assert result["status"] == "triggered"
        assert result["task_id"] == "task-123"
        mock_task.apply_async.assert_called_once_with(queue="scheduler")

    def test_artist_specific_discovery_dispatches_with_the_artist_id(self):
        service = _service()
        fake_result = MagicMock(id="task-456")
        with patch(
            "src.tasks.scheduled_tasks.artist_specific_discovery_task"
        ) as mock_task:
            mock_task.apply_async.return_value = fake_result
            result = service.trigger_discovery_now(artist_id=42)

        assert result["status"] == "triggered"
        assert result["artist_id"] == 42
        mock_task.apply_async.assert_called_once_with(args=[42], queue="scheduler")

    def test_a_dispatch_failure_reports_a_real_error_not_a_crash(self):
        service = _service()
        with patch("src.tasks.scheduled_tasks.scheduled_discovery_task") as mock_task:
            mock_task.apply_async.side_effect = RuntimeError("broker unreachable")
            result = service.trigger_discovery_now()

        assert result["status"] == "error"
        assert result["celery_failed"] is True


class TestTriggerDownloadsNow:
    def test_dispatches_the_downloads_task(self):
        service = _service()
        fake_result = MagicMock(id="task-789")
        with patch("src.tasks.scheduled_tasks.scheduled_downloads_task") as mock_task:
            mock_task.apply_async.return_value = fake_result
            result = service.trigger_downloads_now()

        assert result["status"] == "triggered"
        assert result["task_id"] == "task-789"

    def test_a_dispatch_failure_reports_a_real_error_not_a_crash(self):
        service = _service()
        with patch("src.tasks.scheduled_tasks.scheduled_downloads_task") as mock_task:
            mock_task.apply_async.side_effect = RuntimeError("broker unreachable")
            result = service.trigger_downloads_now()

        assert result["status"] == "error"
        assert result["celery_failed"] is True
