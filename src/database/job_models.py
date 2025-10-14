"""
Database Models for Background Job System
Provides persistent storage for job data, history, and recovery.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import validates

from src.database.models import Base
from src.services.job_queue import BackgroundJob, JobPriority, JobStatus, JobType

# Note: Using existing Base from main models to ensure consistency


class BackgroundJobModel(Base):
    """
    Database model for storing background jobs with full lifecycle tracking
    """

    __tablename__ = "background_jobs"

    # Primary identification
    id = Column(String(36), primary_key=True)  # UUID
    type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    priority = Column(Integer, default=2)

    # Job data
    payload = Column(JSON)  # Job input parameters
    result = Column(JSON)  # Job output results
    progress = Column(Integer, default=0)  # 0-100
    message = Column(Text)  # Current status message
    error_message = Column(Text)  # Error details if failed

    # Timing information
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Retry configuration
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    retry_delay = Column(Integer, default=60)  # seconds

    # User and tracking
    created_by = Column(String(50))  # User ID who created the job
    tags = Column(JSON)  # Additional metadata

    # Add database indexes for performance
    __table_args__ = (
        Index("idx_status_created", "status", "created_at"),
        Index("idx_created_by", "created_by"),
        Index("idx_type_status", "type", "status"),
        Index("idx_priority_created", "priority", "created_at"),
    )

    @validates("status")
    def validate_status(self, key, status):
        """Validate job status values"""
        valid_statuses = {s.value for s in JobStatus}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid job status: {status}. Must be one of: {valid_statuses}"
            )
        return status

    @validates("type")
    def validate_type(self, key, job_type):
        """Validate job type values"""
        valid_types = {t.value for t in JobType}
        if job_type not in valid_types:
            raise ValueError(
                f"Invalid job type: {job_type}. Must be one of: {valid_types}"
            )
        return job_type

    @validates("priority")
    def validate_priority(self, key, priority):
        """Validate priority values"""
        valid_priorities = {p.value for p in JobPriority}
        if priority not in valid_priorities:
            raise ValueError(
                f"Invalid priority: {priority}. Must be one of: {valid_priorities}"
            )
        return priority

    @validates("progress")
    def validate_progress(self, key, progress):
        """Validate progress is between 0 and 100"""
        if progress is not None and (progress < 0 or progress > 100):
            raise ValueError(f"Progress must be between 0 and 100, got: {progress}")
        return progress

    def to_background_job(self) -> BackgroundJob:
        """Convert database model to BackgroundJob dataclass"""
        return BackgroundJob(
            id=self.id,
            type=JobType(self.type),
            status=JobStatus(self.status),
            priority=JobPriority(self.priority),
            payload=self.payload or {},
            result=self.result,
            progress=self.progress or 0,
            message=self.message or "",
            error_message=self.error_message,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            retry_count=self.retry_count or 0,
            max_retries=self.max_retries or 3,
            retry_delay=self.retry_delay or 60,
            created_by=self.created_by,
            tags=self.tags or {},
        )

    @classmethod
    def from_background_job(cls, job: BackgroundJob) -> "BackgroundJobModel":
        """Create database model from BackgroundJob dataclass"""
        return cls(
            id=job.id,
            type=job.type.value,
            status=job.status.value,
            priority=job.priority.value,
            payload=job.payload,
            result=job.result,
            progress=job.progress,
            message=job.message,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            retry_delay=job.retry_delay,
            created_by=job.created_by,
            tags=job.tags,
        )

    def update_from_background_job(self, job: BackgroundJob):
        """Update database model fields from BackgroundJob"""
        self.type = job.type.value
        self.status = job.status.value
        self.priority = job.priority.value
        self.payload = job.payload
        self.result = job.result
        self.progress = job.progress
        self.message = job.message
        self.error_message = job.error_message
        self.started_at = job.started_at
        self.completed_at = job.completed_at
        self.retry_count = job.retry_count
        self.max_retries = job.max_retries
        self.retry_delay = job.retry_delay
        self.created_by = job.created_by
        self.tags = job.tags

    def __repr__(self):
        return f"<BackgroundJobModel(id='{self.id}', type='{self.type}', status='{self.status}')>"


class JobExecutionLog(Base):
    """
    Detailed execution log for debugging and monitoring job processing
    """

    __tablename__ = "job_execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False)  # Foreign key to background_jobs
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    level = Column(String(10), nullable=False)  # DEBUG, INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    worker_name = Column(String(50))  # Which worker processed this
    step = Column(String(100))  # Current processing step
    data = Column(JSON)  # Additional structured data

    __table_args__ = (
        Index("idx_job_id_timestamp", "job_id", "timestamp"),
        Index("idx_level_timestamp", "level", "timestamp"),
    )

    @classmethod
    def create_log(
        cls,
        job_id: str,
        level: str,
        message: str,
        worker_name: str = None,
        step: str = None,
        data: Dict[str, Any] = None,
    ) -> "JobExecutionLog":
        """Create a new job execution log entry"""
        return cls(
            job_id=job_id,
            level=level.upper(),
            message=message,
            worker_name=worker_name,
            step=step,
            data=data,
        )

    def __repr__(self):
        return f"<JobExecutionLog(job_id='{self.job_id}', level='{self.level}', message='{self.message[:50]}...')>"


class JobSchedule(Base):
    """
    Scheduled/recurring job definitions (for future enhancement)
    """

    __tablename__ = "job_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    job_type = Column(String(50), nullable=False)
    cron_expression = Column(String(100))  # Cron-style schedule
    payload_template = Column(JSON)  # Template for job payload
    enabled = Column(Integer, default=1)  # Boolean: 1=enabled, 0=disabled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_run_at = Column(DateTime)
    next_run_at = Column(DateTime)

    # Statistics
    total_runs = Column(Integer, default=0)
    successful_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_enabled_next_run", "enabled", "next_run_at"),
        Index("idx_job_type", "job_type"),
    )

    def __repr__(self):
        return f"<JobSchedule(name='{self.name}', type='{self.job_type}', enabled={bool(self.enabled)})>"


# Database utility functions


def get_job_by_id(session, job_id: str) -> Optional[BackgroundJobModel]:
    """Get job by ID from database"""
    return (
        session.query(BackgroundJobModel)
        .filter(BackgroundJobModel.id == job_id)
        .first()
    )


def get_jobs_by_status(session, status: JobStatus, limit: int = 100) -> list:
    """Get jobs by status from database"""
    return (
        session.query(BackgroundJobModel)
        .filter(BackgroundJobModel.status == status.value)
        .order_by(BackgroundJobModel.created_at.desc())
        .limit(limit)
        .all()
    )


def get_jobs_by_user(session, user_id: str, limit: int = 50) -> list:
    """Get recent jobs for a specific user"""
    return (
        session.query(BackgroundJobModel)
        .filter(BackgroundJobModel.created_by == user_id)
        .order_by(BackgroundJobModel.created_at.desc())
        .limit(limit)
        .all()
    )


def get_job_logs(session, job_id: str, limit: int = 100) -> list:
    """Get execution logs for a specific job"""
    return (
        session.query(JobExecutionLog)
        .filter(JobExecutionLog.job_id == job_id)
        .order_by(JobExecutionLog.timestamp.asc())
        .limit(limit)
        .all()
    )


def cleanup_old_jobs(session, days_to_keep: int = 7) -> int:
    """Remove old completed/failed jobs from database"""
    from datetime import timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

    # Delete old jobs
    deleted_jobs = (
        session.query(BackgroundJobModel)
        .filter(
            BackgroundJobModel.status.in_(["completed", "failed", "cancelled"]),
            BackgroundJobModel.completed_at < cutoff_date,
        )
        .delete(synchronize_session=False)
    )

    # Delete associated logs
    deleted_logs = (
        session.query(JobExecutionLog)
        .filter(JobExecutionLog.timestamp < cutoff_date)
        .delete(synchronize_session=False)
    )

    session.commit()
    return deleted_jobs


def get_job_statistics(session) -> Dict[str, Any]:
    """Get overall job statistics from database"""
    total_jobs = session.query(BackgroundJobModel).count()

    # Count by status
    status_counts = {}
    for status in JobStatus:
        count = (
            session.query(BackgroundJobModel)
            .filter(BackgroundJobModel.status == status.value)
            .count()
        )
        status_counts[status.value] = count

    # Count by type
    type_counts = {}
    for job_type in JobType:
        count = (
            session.query(BackgroundJobModel)
            .filter(BackgroundJobModel.type == job_type.value)
            .count()
        )
        type_counts[job_type.value] = count

    return {
        "total_jobs": total_jobs,
        "status_counts": status_counts,
        "type_counts": type_counts,
    }
