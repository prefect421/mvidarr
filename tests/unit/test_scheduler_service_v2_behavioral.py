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
    """Effective schedules = the saved settings (applied by the scheduler tick,
    #631) plus beat's remaining fixed artist-* entries. Unrelated celery
    entries are excluded."""

    def test_reports_effective_job_schedules_and_artist_entries_only(self):
        service = _service()
        service.celery.conf.beat_schedule = {
            "artist-42-check": {"task": "x.artist_check", "schedule": "weekly"},
            "scheduler-tick": {"task": "x.tick", "schedule": "5m"},
            "some-unrelated-celery-internal-entry": {
                "task": "celery.backend_cleanup",
                "schedule": "hourly",
            },
        }
        with patch(
            "src.services.schedule_gate.rule_for",
            return_value=(True, object(), "daily at 06:00 UTC"),
        ):
            result = service.get_current_schedules()
        assert set(result.keys()) == {
            "scheduled-discovery",
            "scheduled-downloads",
            "scheduled-playlist-sync",
            "artist-42-check",
        }
        assert result["scheduled-discovery"]["schedule"] == "daily at 06:00 UTC"

    def test_returns_empty_dict_on_internal_error_rather_than_raising(self):
        service = _service()
        service.celery.conf.beat_schedule = None  # .items() will raise
        with patch(
            "src.services.schedule_gate.rule_for",
            return_value=(True, object(), "daily at 06:00 UTC"),
        ):
            result = service.get_current_schedules()
        assert result == {}


class TestUpdateScheduleFromSettings:
    """update_schedule_from_settings() used to edit beat_schedule in the WEB
    process's memory, which beat (a separate program) never saw (#631). It now
    reports the effective schedules; the scheduler tick applies them."""

    def _gate(self, enabled_by_job, rule_by_job=None):
        def rule_for(spec):
            ok = enabled_by_job.get(spec.key, True)
            rule = (rule_by_job or {}).get(spec.key, object())
            return ok, rule, f"{spec.key} schedule"

        return patch("src.services.schedule_gate.rule_for", side_effect=rule_for)

    def test_reports_discovery_enabled_and_downloads_disabled(self):
        service = _service()
        with self._gate({"discovery": True, "downloads": False}):
            result = service.update_schedule_from_settings()

        assert result["schedules"]["scheduled-discovery"]["enabled"] is True
        assert result["schedules"]["scheduled-downloads"]["enabled"] is False
        # the web process's beat_schedule is NOT the schedule and is left alone
        assert service.celery.conf.beat_schedule == {}

    def test_both_disabled_are_reported_disabled(self):
        service = _service()
        with self._gate({"discovery": False, "downloads": False}):
            result = service.update_schedule_from_settings()

        assert result["status"] == "updated"
        assert not result["schedules"]["scheduled-discovery"]["enabled"]
        assert not result["schedules"]["scheduled-downloads"]["enabled"]

    def test_an_unparseable_schedule_is_reported_disabled_not_an_error(self):
        # rule None == "not-a-real-frequency": the job never runs, the call
        # still succeeds, and the UI can show it as not scheduled.
        service = _service()
        with self._gate({}, rule_by_job={"discovery": None}):
            result = service.update_schedule_from_settings()

        assert result["status"] == "updated"
        assert result["schedules"]["scheduled-discovery"]["enabled"] is False


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
