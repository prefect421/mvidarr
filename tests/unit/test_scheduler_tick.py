"""#631: beat fires one cheap tick; the tick dispatches whichever jobs the saved
settings say are due. The old hard-coded beat entries must be gone."""

from unittest.mock import MagicMock, patch

from src.jobs.celery_app import celery_app


def test_beat_has_a_tick_and_no_hard_coded_job_schedules():
    beat = celery_app.conf.beat_schedule
    assert "scheduler-tick" in beat
    assert (
        beat["scheduler-tick"]["task"]
        == "src.tasks.scheduled_tasks.scheduler_tick_task"
    )
    assert beat["scheduler-tick"]["schedule"].total_seconds() <= 300
    # these used to be fixed intervals that ignored the Settings page
    for name in ("scheduled-discovery", "scheduled-downloads", "playlist-sync"):
        assert name not in beat


def test_tick_dispatches_exactly_the_due_jobs_to_the_scheduler_queue():
    from src.tasks import scheduled_tasks

    with patch(
        "src.services.schedule_gate.due_jobs", return_value=["a.task", "b.task"]
    ), patch.object(scheduled_tasks.celery_app, "send_task") as send:
        result = scheduled_tasks.scheduler_tick_task.run()
    assert [c.args[0] for c in send.call_args_list] == ["a.task", "b.task"]
    assert all(c.kwargs["queue"] == "scheduler" for c in send.call_args_list)
    assert result["dispatched"] == ["a.task", "b.task"]


def test_tick_with_nothing_due_dispatches_nothing():
    from src.tasks import scheduled_tasks

    with patch("src.services.schedule_gate.due_jobs", return_value=[]), patch.object(
        scheduled_tasks.celery_app, "send_task"
    ) as send:
        result = scheduled_tasks.scheduler_tick_task.run()
    send.assert_not_called()
    assert result["dispatched"] == []


def test_one_failed_dispatch_does_not_stop_the_others():
    from src.tasks import scheduled_tasks

    def flaky(name, **kw):
        if name == "a.task":
            raise RuntimeError("broker hiccup")

    with patch(
        "src.services.schedule_gate.due_jobs", return_value=["a.task", "b.task"]
    ), patch.object(scheduled_tasks.celery_app, "send_task", side_effect=flaky):
        result = scheduled_tasks.scheduler_tick_task.run()
    assert result["dispatched"] == ["b.task"] and result["errors"]


def test_saving_settings_no_longer_pretends_to_edit_beat():
    from src.services.scheduler_service_v2 import SchedulerServiceV2

    svc = SchedulerServiceV2.__new__(SchedulerServiceV2)
    svc.celery = MagicMock()
    svc.celery.conf.beat_schedule = {}
    with patch(
        "src.services.schedule_gate.rule_for",
        return_value=(True, object(), "daily at 06:00 UTC"),
    ):
        result = svc.update_schedule_from_settings()
    assert (
        svc.celery.conf.beat_schedule == {}
    )  # the web process's memory was never the schedule
    assert result["status"] == "updated"
    assert "scheduled-discovery" in result["schedules"]
    assert "tick" in result["note"].lower()
