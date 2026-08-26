"""#317: final SchedulerServiceV2 slice -- the two remaining methods
that need a real database: get_status() (recent-job statistics) and
get_scheduled_jobs_history() (job history listing/filtering). Uses a
real, temp-file SQLite-backed session rather than mocking the ORM
query chain, following this session's established pattern (e.g.
test_playlist_update_stats_flush.py) for exercising real query/
filter/aggregate logic instead of just asserting mocks were called
with the right arguments.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import ScheduledJob
from src.services.scheduler_service_v2 import SchedulerServiceV2


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ScheduledJob.__table__])
    return sessionmaker(bind=engine)


def _service(session_factory, monkeypatch):
    service = SchedulerServiceV2()
    service.celery = MagicMock()
    monkeypatch.setattr(service, "_check_celery_connection", lambda: True)
    monkeypatch.setattr(service, "is_enabled", lambda: True)
    monkeypatch.setattr(service, "get_current_schedules", lambda: {})

    @contextmanager
    def _fake_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr("src.services.scheduler_service_v2.get_db", _fake_get_db)
    return service


def _job(session_factory, status, created_at=None):
    session = session_factory()
    job = ScheduledJob(
        job_type="discovery",
        status=status,
        created_at=created_at or datetime.utcnow(),
    )
    session.add(job)
    session.commit()
    job_id = job.id  # capture before closing -- the ORM object is
    # detached (and attribute access would raise DetachedInstanceError)
    # once its session closes.
    session.close()
    return job_id


class TestGetStatus:
    def test_empty_history_reports_zero_jobs_and_zero_success_rate(
        self, session_factory, monkeypatch
    ):
        service = _service(session_factory, monkeypatch)
        result = service.get_status()
        assert result["statistics"]["total_jobs_24h"] == 0
        assert result["statistics"]["success_rate"] == 0

    def test_counts_jobs_by_status_within_the_last_24_hours(
        self, session_factory, monkeypatch
    ):
        _job(session_factory, "completed")
        _job(session_factory, "completed")
        _job(session_factory, "failed")
        _job(session_factory, "running")
        service = _service(session_factory, monkeypatch)

        result = service.get_status()

        stats = result["statistics"]
        assert stats["total_jobs_24h"] == 4
        assert stats["completed"] == 2
        assert stats["failed"] == 1
        assert stats["running"] == 1
        assert stats["success_rate"] == 50.0

    def test_jobs_older_than_24_hours_are_excluded(self, session_factory, monkeypatch):
        _job(
            session_factory,
            "completed",
            created_at=datetime.utcnow() - timedelta(hours=25),
        )
        _job(session_factory, "completed")  # within the window
        service = _service(session_factory, monkeypatch)

        result = service.get_status()

        assert result["statistics"]["total_jobs_24h"] == 1

    def test_reports_running_state_and_enabled_flag(self, session_factory, monkeypatch):
        service = _service(session_factory, monkeypatch)
        service._is_running = True
        result = service.get_status()
        assert result["status"] == "running"
        assert result["enabled"] is True

    def test_a_db_error_returns_safe_defaults_not_a_crash(
        self, session_factory, monkeypatch
    ):
        service = _service(session_factory, monkeypatch)

        @contextmanager
        def _broken_get_db():
            raise RuntimeError("db unreachable")
            yield  # pragma: no cover -- unreachable, makes this a generator

        monkeypatch.setattr("src.services.scheduler_service_v2.get_db", _broken_get_db)

        result = service.get_status()
        assert result["status"] == "error"
        assert result["statistics"]["total_jobs_24h"] == 0


class TestGetScheduledJobsHistory:
    def test_returns_jobs_ordered_most_recent_first(self, session_factory, monkeypatch):
        older = _job(
            session_factory,
            "completed",
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
        newer = _job(session_factory, "completed")
        service = _service(session_factory, monkeypatch)
        service.db = session_factory()

        result = service.get_scheduled_jobs_history()

        ids = [job["id"] for job in result]
        assert ids.index(newer) < ids.index(older)

    def test_respects_the_limit_parameter(self, session_factory, monkeypatch):
        for _ in range(5):
            _job(session_factory, "completed")
        service = _service(session_factory, monkeypatch)
        service.db = session_factory()

        result = service.get_scheduled_jobs_history(limit=2)

        assert len(result) == 2

    def test_filters_by_job_type_when_given(self, session_factory, monkeypatch):
        session = session_factory()
        session.add(ScheduledJob(job_type="discovery", status="completed"))
        session.add(ScheduledJob(job_type="download", status="completed"))
        session.commit()
        session.close()
        service = _service(session_factory, monkeypatch)
        service.db = session_factory()

        result = service.get_scheduled_jobs_history(job_type="download")

        assert len(result) == 1
        assert result[0]["job_type"] == "download"

    def test_a_db_error_returns_an_empty_list_not_a_crash(
        self, session_factory, monkeypatch
    ):
        service = _service(session_factory, monkeypatch)

        class _BrokenSession:
            def query(self, *args, **kwargs):
                raise RuntimeError("db unreachable")

        service.db = _BrokenSession()

        result = service.get_scheduled_jobs_history()
        assert result == []
