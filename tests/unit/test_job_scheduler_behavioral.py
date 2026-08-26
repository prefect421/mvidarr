"""#317: JobScheduler (238 lines, src/services/job_scheduler.py) had
zero test coverage despite being live-wired into fastapi_app.py's own
startup/shutdown lifespan (a second, asyncio-based scheduler running
alongside the Celery-based SchedulerServiceV2 -- confirmed via grep,
not an assumption). Covers its state machine (start/stop), the
before/after-count diffing logic in _process_scheduled_jobs()/
_process_dependency_jobs() (a real, non-trivial counting pattern with
genuine off-by-one/negative-count risk if a caller ever gets the
before/after ordering wrong), get_stats(), and force_check().

The module-level singleton helpers (get_job_scheduler(),
start_job_scheduler(), stop_job_scheduler(), get_scheduler_stats(),
force_scheduler_check()) are thin wrappers around the already-tested
instance methods, and touch a shared global (_global_scheduler) that
would need careful fixture/teardown discipline to test without risking
cross-test pollution -- left untested here as lower value for the
added complexity.
"""

import asyncio

import pytest

from src.services.job_scheduler import JobScheduler


def _run(coro):
    return asyncio.run(coro)


def _fake_job(status_value):
    class _Job:
        class _Status:
            def __init__(self, value):
                self.value = value

        def __init__(self, value):
            self.status = self._Status(value)

    return _Job(status_value)


class _FakeJobQueue:
    def __init__(self, jobs=None):
        self._jobs = jobs or {}
        self.process_scheduled_jobs_called = False
        self.process_waiting_jobs_called = False

    async def process_scheduled_jobs(self):
        self.process_scheduled_jobs_called = True
        # Simulate real processing: any "scheduled" job flips to "running".
        for job in self._jobs.values():
            if job.status.value == "scheduled":
                job.status.value = "running"

    async def process_waiting_jobs(self):
        self.process_waiting_jobs_called = True
        for job in self._jobs.values():
            if job.status.value == "waiting_dependencies":
                job.status.value = "running"


class TestGetStats:
    def test_reports_not_running_with_no_uptime_before_start(self):
        scheduler = JobScheduler()
        stats = scheduler.get_stats()
        assert stats["running"] is False
        assert stats["uptime_seconds"] is None
        assert stats["uptime_start"] is None
        assert stats["last_check"] is None

    def test_reports_the_configured_check_interval(self):
        scheduler = JobScheduler(check_interval=45)
        assert scheduler.get_stats()["check_interval"] == 45

    def test_reports_accumulated_processed_counts(self):
        scheduler = JobScheduler()
        scheduler.stats["scheduled_jobs_processed"] = 3
        scheduler.stats["dependency_jobs_processed"] = 7
        stats = scheduler.get_stats()
        assert stats["scheduled_jobs_processed"] == 3
        assert stats["dependency_jobs_processed"] == 7


class TestProcessScheduledJobs:
    def test_counts_jobs_that_transition_out_of_scheduled(self):
        scheduler = JobScheduler()
        job_queue = _FakeJobQueue(
            {
                "a": _fake_job("scheduled"),
                "b": _fake_job("scheduled"),
                "c": _fake_job("running"),  # unaffected, not scheduled
            }
        )
        count = _run(scheduler._process_scheduled_jobs(job_queue))
        assert count == 2
        assert job_queue.process_scheduled_jobs_called is True

    def test_zero_scheduled_jobs_returns_zero(self):
        scheduler = JobScheduler()
        job_queue = _FakeJobQueue({"a": _fake_job("running")})
        count = _run(scheduler._process_scheduled_jobs(job_queue))
        assert count == 0

    def test_an_internal_error_is_caught_and_returns_zero_not_a_crash(self):
        scheduler = JobScheduler()

        class _BrokenJobQueue:
            @property
            def _jobs(self):
                raise RuntimeError("db unavailable")

        count = _run(scheduler._process_scheduled_jobs(_BrokenJobQueue()))
        assert count == 0


class TestProcessDependencyJobs:
    def test_counts_jobs_that_transition_out_of_waiting(self):
        scheduler = JobScheduler()
        job_queue = _FakeJobQueue(
            {
                "a": _fake_job("waiting_dependencies"),
                "b": _fake_job("running"),
            }
        )
        count = _run(scheduler._process_dependency_jobs(job_queue))
        assert count == 1
        assert job_queue.process_waiting_jobs_called is True


class TestStartStop:
    def test_start_flips_running_and_records_uptime_start(self):
        scheduler = JobScheduler()

        async def _noop_loop():
            pass

        scheduler._scheduler_loop = _noop_loop
        _run(scheduler.start())
        try:
            assert scheduler.running is True
            assert scheduler.stats["uptime_start"] is not None
        finally:
            _run(scheduler.stop())

    def test_starting_twice_is_a_no_op_the_second_time(self):
        scheduler = JobScheduler()

        async def _noop_loop():
            pass

        scheduler._scheduler_loop = _noop_loop
        _run(scheduler.start())
        first_task = scheduler.scheduler_task
        try:
            _run(scheduler.start())  # should warn and return, not replace the task
            assert scheduler.scheduler_task is first_task
        finally:
            _run(scheduler.stop())

    def test_stop_flips_running_off_and_cancels_the_task(self):
        scheduler = JobScheduler()

        async def _noop_loop():
            await asyncio.sleep(30)  # long enough that stop() must cancel it

        scheduler._scheduler_loop = _noop_loop
        _run(scheduler.start())
        _run(scheduler.stop())
        assert scheduler.running is False
        assert scheduler.scheduler_task.cancelled() or scheduler.scheduler_task.done()

    def test_stopping_when_never_started_is_a_safe_no_op(self):
        scheduler = JobScheduler()
        _run(scheduler.stop())  # must not raise
        assert scheduler.running is False


class TestForceCheck:
    def test_delegates_to_process_ready_jobs(self):
        scheduler = JobScheduler()
        called = {}

        async def _fake_process_ready_jobs():
            called["yes"] = True

        scheduler._process_ready_jobs = _fake_process_ready_jobs
        _run(scheduler.force_check())
        assert called.get("yes") is True
