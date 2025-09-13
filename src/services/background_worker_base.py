"""
Base Worker Classes
Abstract base classes and utilities for background job workers.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from src.database.connection import get_db

from .job_queue import BackgroundJob, JobQueue

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """
    Abstract base class for all background job workers

    Provides common functionality for progress updates, completion handling,
    error management, and database session management.
    """

    def __init__(self, job_queue: JobQueue, job: BackgroundJob):
        self.job_queue = job_queue
        self.job = job
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def process(self):
        """
        Process the job - must be implemented by subclasses

        This method should:
        1. Extract job data from self.job.payload
        2. Perform the work with progress updates
        3. Call self.complete() or self.fail() when done
        """
        pass

    async def update_progress(self, progress: int, message: str = ""):
        """Update job progress with validation"""
        # Clamp progress to valid range
        progress = max(0, min(100, progress))

        await self.job_queue.update_progress(self.job.id, progress, message)
        self.logger.debug(f"Job {self.job.id} progress: {progress}% - {message}")

    async def complete(self, result: Optional[Dict[str, Any]] = None):
        """Mark job as completed with optional result data"""
        await self.job_queue.complete_job(self.job.id, result)
        self.logger.info(
            f"Job {self.job.id} ({self.job.type.value}) completed successfully"
        )

    async def fail(self, error: str, retry: bool = True):
        """Mark job as failed with error message and retry option"""
        await self.job_queue.fail_job(self.job.id, error, retry)
        self.logger.error(f"Job {self.job.id} ({self.job.type.value}) failed: {error}")

    @asynccontextmanager
    async def database_session(self):
        """
        Provide isolated database session for job processing

        Usage:
            async with self.database_session() as session:
                # Use session for database operations
                result = session.query(Model).filter(...).first()
                session.commit()
        """
        session = None
        try:
            session = get_db()
            yield session
            session.commit()
        except Exception as e:
            if session:
                session.rollback()
            self.logger.error(f"Database error in job {self.job.id}: {e}")
            raise
        finally:
            if session:
                session.close()

    def validate_payload(self, required_fields: list) -> bool:
        """
        Validate that job payload contains required fields

        Args:
            required_fields: List of field names that must be present

        Returns:
            True if all required fields are present, False otherwise
        """
        missing_fields = []
        for field in required_fields:
            if field not in self.job.payload:
                missing_fields.append(field)

        if missing_fields:
            error_msg = f"Missing required payload fields: {', '.join(missing_fields)}"
            self.logger.error(f"Job {self.job.id} validation failed: {error_msg}")
            return False

        return True

    async def run_with_timeout(self, coro, timeout_seconds: int = 300):
        """
        Run a coroutine with timeout

        Args:
            coro: Coroutine to run
            timeout_seconds: Maximum time to wait

        Returns:
            Result of coroutine

        Raises:
            asyncio.TimeoutError: If operation times out
        """
        try:
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            error_msg = f"Operation timed out after {timeout_seconds} seconds"
            self.logger.error(f"Job {self.job.id}: {error_msg}")
            raise

    async def sleep_with_progress(
        self,
        total_seconds: float,
        progress_start: int,
        progress_end: int,
        message: str = "Waiting...",
    ):
        """
        Sleep with progress updates

        Args:
            total_seconds: Total time to sleep
            progress_start: Starting progress percentage
            progress_end: Ending progress percentage
            message: Progress message to display
        """
        steps = 10
        step_duration = total_seconds / steps
        progress_step = (progress_end - progress_start) / steps

        for i in range(steps):
            current_progress = progress_start + (progress_step * i)
            await self.update_progress(
                int(current_progress), f"{message} ({i+1}/{steps})"
            )
            await asyncio.sleep(step_duration)

        await self.update_progress(progress_end, message)


class DatabaseWorker(BaseWorker):
    """
    Base class for workers that primarily perform database operations
    """

    async def process(self):
        """Default process method with database session management"""
        try:
            await self.update_progress(10, "Starting database operation...")

            async with self.database_session() as session:
                await self.process_with_database(session)

        except Exception as e:
            await self.fail(f"Database operation failed: {str(e)}")

    @abstractmethod
    async def process_with_database(self, session):
        """Process job with database session - must be implemented by subclasses"""
        pass


class NetworkWorker(BaseWorker):
    """
    Base class for workers that make external network requests
    """

    def __init__(self, job_queue: JobQueue, job: BackgroundJob):
        super().__init__(job_queue, job)
        self.default_timeout = 30  # seconds
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    async def make_request_with_retry(self, request_func, *args, **kwargs):
        """
        Make network request with retry logic

        Args:
            request_func: Async function to call
            *args, **kwargs: Arguments to pass to function

        Returns:
            Result of request function
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                self.logger.debug(
                    f"Network request attempt {attempt + 1}/{self.max_retries}"
                )
                return await self.run_with_timeout(
                    request_func(*args, **kwargs), self.default_timeout
                )
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Network request failed (attempt {attempt + 1}): {e}"
                )

                if attempt < self.max_retries - 1:
                    await self.update_progress(
                        self.job.progress,
                        f"Request failed, retrying in {self.retry_delay}s...",
                    )
                    await asyncio.sleep(self.retry_delay)

        # All retries exhausted
        raise last_exception


class HybridWorker(DatabaseWorker, NetworkWorker):
    """
    Base class for workers that perform both database and network operations

    Provides functionality from both DatabaseWorker and NetworkWorker
    """

    def __init__(self, job_queue: JobQueue, job: BackgroundJob):
        BaseWorker.__init__(self, job_queue, job)
        NetworkWorker.__init__(self, job_queue, job)

    async def process(self):
        """Override to provide custom process flow for hybrid operations"""
        try:
            await self.update_progress(5, "Initializing hybrid operation...")
            await self.process_hybrid()
        except Exception as e:
            await self.fail(f"Hybrid operation failed: {str(e)}")

    async def process_with_database(self, session):
        """
        Default implementation for DatabaseWorker compatibility
        Delegates to process_hybrid() method
        """
        await self.process_hybrid()

    @abstractmethod
    async def process_hybrid(self):
        """Process hybrid job - must be implemented by subclasses"""
        pass
