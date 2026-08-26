"""#317, final slice: SchedulerWorker (151 lines,
src/services/workers/scheduler_worker.py) had zero test coverage. It's
almost entirely orchestration -- delegating to job_queue,
video_batch_service, and a FastAPI discovery function -- so most of
what's testable here is real branching/counting logic and error
handling around those calls, not pure computation. Lower intrinsic
value than the rest of this issue's slices (confirmed via a full
review before starting), but real gaps worth closing: the
enqueue-failure counting in _handle_scheduled_download() (one failed
enqueue must not abort the rest of the batch) and process()'s
dispatch/error-propagation contract (a scheduler job must both report
failure to the job queue AND re-raise, so its own caller sees it).

BaseWorker.__init__(job_queue, job) does no I/O -- safe to construct
directly with lightweight fakes for both arguments.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.workers.scheduler_worker import SchedulerWorker


def _run(coro):
    return asyncio.run(coro)


def _job(job_type, payload=None):
    return SimpleNamespace(
        id="job-1",
        type=SimpleNamespace(value=job_type),
        payload=payload or {},
        created_by=None,
    )


def _worker(job_type, payload=None):
    job_queue = SimpleNamespace(
        update_progress=AsyncMock(),
        complete_job=AsyncMock(),
        fail_job=AsyncMock(),
    )
    worker = SchedulerWorker(job_queue=job_queue, job=_job(job_type, payload))
    return worker


class TestProcessDispatch:
    def test_scheduled_download_job_type_calls_the_download_handler_and_completes(
        self,
    ):
        worker = _worker("scheduled_download")
        with patch.object(
            worker,
            "_handle_scheduled_download",
            AsyncMock(return_value={"status": "success"}),
        ) as mock_handler:
            _run(worker.process())
        mock_handler.assert_called_once()
        worker.job_queue.complete_job.assert_called_once_with(
            "job-1", {"status": "success"}
        )

    def test_scheduled_discovery_job_type_calls_the_discovery_handler_and_completes(
        self,
    ):
        worker = _worker("scheduled_discovery")
        with patch.object(
            worker,
            "_handle_scheduled_discovery",
            AsyncMock(return_value={"status": "success"}),
        ) as mock_handler:
            _run(worker.process())
        mock_handler.assert_called_once()
        worker.job_queue.complete_job.assert_called_once()

    def test_unknown_job_type_fails_the_job_and_re_raises(self):
        worker = _worker("not_a_real_scheduler_job_type")
        with pytest.raises(ValueError):
            _run(worker.process())
        worker.job_queue.fail_job.assert_called_once()
        assert "Unknown scheduler job type" in worker.job_queue.fail_job.call_args[0][1]

    def test_a_handler_exception_fails_the_job_and_re_raises(self):
        # process()'s error handling must do BOTH: report the failure
        # to the job queue (so it's visible in job history/status) AND
        # re-raise (so the worker framework's own retry/logging sees
        # it too) -- not just one or the other.
        worker = _worker("scheduled_download")
        with patch.object(
            worker,
            "_handle_scheduled_download",
            AsyncMock(side_effect=RuntimeError("db unreachable")),
        ):
            with pytest.raises(RuntimeError):
                _run(worker.process())
        worker.job_queue.fail_job.assert_called_once()
        assert "db unreachable" in worker.job_queue.fail_job.call_args[0][1]


class TestHandleScheduledDownload:
    def test_no_wanted_videos_reports_zero_downloaded_without_touching_the_job_queue(
        self,
    ):
        worker = _worker("scheduled_download", {"max_downloads": 5})
        with patch(
            "src.services.video_batch_service.get_wanted_videos_for_download",
            return_value=[],
        ):
            result = _run(worker._handle_scheduled_download({"max_downloads": 5}))
        assert result["downloaded"] == 0
        assert result["status"] == "success"

    def test_enqueues_one_download_job_per_wanted_video(self):
        worker = _worker("scheduled_download")
        wanted = [{"id": 1, "title": "Song A"}, {"id": 2, "title": "Song B"}]
        fake_job_queue_module = SimpleNamespace(enqueue=AsyncMock(return_value="q-1"))
        with patch(
            "src.services.video_batch_service.get_wanted_videos_for_download",
            return_value=wanted,
        ), patch(
            "src.services.job_queue.get_job_queue",
            AsyncMock(return_value=fake_job_queue_module),
        ):
            result = _run(worker._handle_scheduled_download({}))

        assert result["downloaded"] == 2
        assert result["failed"] == 0
        assert result["total"] == 2
        assert fake_job_queue_module.enqueue.call_count == 2

    def test_one_failed_enqueue_does_not_abort_the_rest_of_the_batch(self):
        worker = _worker("scheduled_download")
        wanted = [{"id": 1, "title": "Song A"}, {"id": 2, "title": "Song B"}]

        call_count = {"n": 0}

        async def _enqueue_second_call_fails(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("queue full")
            return "q-2"

        fake_job_queue_module = SimpleNamespace(enqueue=_enqueue_second_call_fails)
        with patch(
            "src.services.video_batch_service.get_wanted_videos_for_download",
            return_value=wanted,
        ), patch(
            "src.services.job_queue.get_job_queue",
            AsyncMock(return_value=fake_job_queue_module),
        ):
            result = _run(worker._handle_scheduled_download({}))

        assert result["downloaded"] == 1
        assert result["failed"] == 1
        assert result["total"] == 2

    def test_respects_the_max_downloads_payload_field(self):
        worker = _worker("scheduled_download")
        with patch(
            "src.services.video_batch_service.get_wanted_videos_for_download",
            return_value=[],
        ) as mock_get:
            _run(worker._handle_scheduled_download({"max_downloads": 25}))
        mock_get.assert_called_once_with(limit=25)

    def test_defaults_max_downloads_to_10_when_not_in_payload(self):
        worker = _worker("scheduled_download")
        with patch(
            "src.services.video_batch_service.get_wanted_videos_for_download",
            return_value=[],
        ) as mock_get:
            _run(worker._handle_scheduled_download({}))
        mock_get.assert_called_once_with(limit=10)


class TestHandleScheduledDiscovery:
    def test_passes_payload_fields_through_and_marks_the_run_as_scheduled(self):
        worker = _worker("scheduled_discovery")
        with patch(
            "src.api.fastapi.video_discovery.discover_videos_for_artists",
            AsyncMock(return_value={"artists_processed": 3, "videos_discovered": 7}),
        ) as mock_discover:
            result = _run(
                worker._handle_scheduled_discovery(
                    {"max_artists": 2, "max_videos_per_artist": 1}
                )
            )

        mock_discover.assert_called_once_with(
            max_artists=2, max_videos_per_artist=1, scheduled=True
        )
        assert result["artists_processed"] == 3
        assert result["videos_discovered"] == 7

    def test_defaults_when_payload_omits_the_fields(self):
        worker = _worker("scheduled_discovery")
        with patch(
            "src.api.fastapi.video_discovery.discover_videos_for_artists",
            AsyncMock(return_value={}),
        ) as mock_discover:
            _run(worker._handle_scheduled_discovery({}))

        mock_discover.assert_called_once_with(
            max_artists=5, max_videos_per_artist=3, scheduled=True
        )
