"""
Background Worker Manager
Manages a pool of background workers that process jobs from the job queue.
"""

import asyncio
import logging
import signal
import sys
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type

from .job_queue import BackgroundJob, JobQueue, JobType, get_job_queue

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """
    Abstract base class for background job workers
    """

    def __init__(self, job_queue: JobQueue, job: BackgroundJob):
        self.job_queue = job_queue
        self.job = job
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def process(self):
        """Process the job - must be implemented by subclasses"""
        pass

    async def update_progress(self, progress: int, message: str = ""):
        """Update job progress"""
        await self.job_queue.update_progress(self.job.id, progress, message)
        self.logger.debug(f"Job {self.job.id} progress: {progress}% - {message}")

    async def complete(self, result: Optional[Dict] = None):
        """Mark job as completed"""
        await self.job_queue.complete_job(self.job.id, result)
        self.logger.info(f"Job {self.job.id} completed successfully")

    async def fail(self, error: str, retry: bool = True):
        """Mark job as failed"""
        await self.job_queue.fail_job(self.job.id, error, retry)
        self.logger.error(f"Job {self.job.id} failed: {error}")


class DummyWorker(BaseWorker):
    """
    Dummy worker for testing purposes
    """

    async def process(self):
        """Simulate work with progress updates"""
        self.logger.info(f"Starting dummy work for job {self.job.id}")

        try:
            # Simulate various stages of work
            await self.update_progress(10, "Initializing...")
            await asyncio.sleep(1)

            await self.update_progress(30, "Processing data...")
            await asyncio.sleep(2)

            await self.update_progress(60, "Analyzing results...")
            await asyncio.sleep(1.5)

            await self.update_progress(90, "Finalizing...")
            await asyncio.sleep(0.5)

            # Complete with result
            result = {"items_processed": 42, "duration": 5.0, "status": "success"}
            await self.complete(result)

        except Exception as e:
            await self.fail(f"Dummy worker error: {str(e)}")


class BackgroundWorkerManager:
    """
    Manages a pool of background workers that process jobs from the queue
    """

    def __init__(self, job_queue: JobQueue, num_workers: int = 3):
        self.job_queue = job_queue
        self.num_workers = num_workers
        self.workers: Dict[JobType, Type[BaseWorker]] = {}
        self.running = False
        self.worker_tasks: List[asyncio.Task] = []
        self.shutdown_event = asyncio.Event()

        # Register workers
        self._register_default_workers()

    def _register_default_workers(self):
        """Register default worker implementations"""
        # Import workers here to avoid circular imports
        try:
            from .workers.metadata_enrichment_worker import MetadataEnrichmentWorker

            self.register_worker(JobType.METADATA_ENRICHMENT, MetadataEnrichmentWorker)
        except ImportError as e:
            logger.warning(f"Could not import MetadataEnrichmentWorker: {e}")
            self.register_worker(JobType.METADATA_ENRICHMENT, DummyWorker)  # Fallback

        # Import and register new workers
        try:
            from .workers.video_download_worker import VideoDownloadWorker

            self.register_worker(JobType.VIDEO_DOWNLOAD, VideoDownloadWorker)
        except ImportError as e:
            logger.warning(f"Could not import VideoDownloadWorker: {e}")
            self.register_worker(JobType.VIDEO_DOWNLOAD, DummyWorker)

        try:
            from .workers.bulk_operations_worker import BulkOperationsWorker

            self.register_worker(JobType.BULK_VIDEO_DELETE, BulkOperationsWorker)
            # Note: Bulk operations worker handles multiple operation types based on payload
        except ImportError as e:
            logger.warning(f"Could not import BulkOperationsWorker: {e}")
            self.register_worker(JobType.BULK_VIDEO_DELETE, DummyWorker)

        # Video quality workers
        try:
            from .workers.video_quality_worker import VideoQualityWorker

            self.register_worker(JobType.VIDEO_QUALITY_ANALYZE, VideoQualityWorker)
            self.register_worker(JobType.VIDEO_QUALITY_UPGRADE, VideoQualityWorker)
            self.register_worker(JobType.VIDEO_QUALITY_BULK_UPGRADE, VideoQualityWorker)
            self.register_worker(JobType.VIDEO_QUALITY_CHECK_ALL, VideoQualityWorker)
        except ImportError as e:
            logger.warning(f"Could not import VideoQualityWorker: {e}")
            self.register_worker(JobType.VIDEO_QUALITY_ANALYZE, DummyWorker)
            self.register_worker(JobType.VIDEO_QUALITY_UPGRADE, DummyWorker)
            self.register_worker(JobType.VIDEO_QUALITY_BULK_UPGRADE, DummyWorker)
            self.register_worker(JobType.VIDEO_QUALITY_CHECK_ALL, DummyWorker)

        # Video indexing workers
        try:
            from .workers.video_indexing_worker import VideoIndexingWorker

            self.register_worker(JobType.VIDEO_INDEX_ALL, VideoIndexingWorker)
            self.register_worker(JobType.VIDEO_INDEX_SINGLE, VideoIndexingWorker)
        except ImportError as e:
            logger.warning(f"Could not import VideoIndexingWorker: {e}")
            self.register_worker(JobType.VIDEO_INDEX_ALL, DummyWorker)
            self.register_worker(JobType.VIDEO_INDEX_SINGLE, DummyWorker)

        # Video organization workers
        try:
            from .workers.video_organization_worker import VideoOrganizationWorker

            self.register_worker(JobType.VIDEO_ORGANIZE_ALL, VideoOrganizationWorker)
            self.register_worker(JobType.VIDEO_ORGANIZE_SINGLE, VideoOrganizationWorker)
            self.register_worker(
                JobType.VIDEO_REORGANIZE_EXISTING, VideoOrganizationWorker
            )
        except ImportError as e:
            logger.warning(f"Could not import VideoOrganizationWorker: {e}")
            self.register_worker(JobType.VIDEO_ORGANIZE_ALL, DummyWorker)
            self.register_worker(JobType.VIDEO_ORGANIZE_SINGLE, DummyWorker)
            self.register_worker(JobType.VIDEO_REORGANIZE_EXISTING, DummyWorker)

        # Scheduler workers
        try:
            from .workers.scheduler_worker import SchedulerWorker

            self.register_worker(JobType.SCHEDULED_DOWNLOAD, SchedulerWorker)
            self.register_worker(JobType.SCHEDULED_DISCOVERY, SchedulerWorker)
        except ImportError as e:
            logger.warning(f"Could not import SchedulerWorker: {e}")
            self.register_worker(JobType.SCHEDULED_DOWNLOAD, DummyWorker)
            self.register_worker(JobType.SCHEDULED_DISCOVERY, DummyWorker)

        # Other workers use dummy for now until implemented
        self.register_worker(
            JobType.BULK_ARTIST_IMPORT, DummyWorker
        )  # TODO: Implement BulkImportWorker
        self.register_worker(
            JobType.THUMBNAIL_GENERATION, DummyWorker
        )  # TODO: Implement ThumbnailWorker
        self.register_worker(
            JobType.PLAYLIST_SYNC, DummyWorker
        )  # TODO: Implement PlaylistSyncWorker

        # Statistics
        self.stats = {
            "workers_started": 0,
            "workers_stopped": 0,
            "jobs_processed": 0,
            "jobs_failed": 0,
            "start_time": None,
            "stop_time": None,
        }

    def register_worker(self, job_type: JobType, worker_class: Type[BaseWorker]):
        """Register a worker class for a specific job type"""
        self.workers[job_type] = worker_class
        logger.info(
            f"Registered worker {worker_class.__name__} for job type {job_type.value}"
        )

    async def start(self):
        """Start the background worker pool"""
        if self.running:
            logger.warning("Worker manager is already running")
            return

        self.running = True
        self.shutdown_event.clear()
        self.stats["start_time"] = asyncio.get_event_loop().time()

        logger.info(f"Starting {self.num_workers} background workers...")

        # Start worker tasks
        for i in range(self.num_workers):
            worker_name = f"worker-{i+1}"
            task = asyncio.create_task(self._worker_loop(worker_name))
            self.worker_tasks.append(task)
            self.stats["workers_started"] += 1

        logger.info(
            f"Background worker manager started with {len(self.worker_tasks)} workers"
        )

    async def stop(self):
        """Stop all background workers gracefully"""
        if not self.running:
            logger.warning("Worker manager is not running")
            return

        self.running = False
        self.shutdown_event.set()
        self.stats["stop_time"] = asyncio.get_event_loop().time()

        logger.info("Stopping background workers...")

        # Cancel all worker tasks
        for task in self.worker_tasks:
            task.cancel()

        # Wait for all tasks to complete with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.worker_tasks, return_exceptions=True), timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning("Some worker tasks did not stop gracefully within timeout")

        self.worker_tasks.clear()
        self.stats["workers_stopped"] = self.stats["workers_started"]

        logger.info("Background worker manager stopped")

    async def _worker_loop(self, worker_name: str):
        """Main worker loop - processes jobs from queue"""
        logger.info(f"{worker_name} started")

        while self.running and not self.shutdown_event.is_set():
            try:
                # Get next job from queue (with timeout to allow shutdown)
                job = await self.job_queue.get_next_job()

                if not job:
                    continue  # Timeout occurred, check shutdown flag

                # Check if we have a worker for this job type
                worker_class = self.workers.get(job.type)
                if not worker_class:
                    await self.job_queue.fail_job(
                        job.id,
                        f"No worker available for job type {job.type.value}",
                        retry=False,
                    )
                    self.stats["jobs_failed"] += 1
                    logger.error(f"No worker available for job type {job.type.value}")
                    continue

                # Process the job
                logger.info(f"{worker_name} processing job {job.id} ({job.type.value})")

                try:
                    # Create worker instance and process job
                    worker = worker_class(self.job_queue, job)
                    await worker.process()
                    self.stats["jobs_processed"] += 1

                except Exception as e:
                    logger.error(f"{worker_name} error processing job {job.id}: {e}")
                    await self.job_queue.fail_job(job.id, f"Worker error: {str(e)}")
                    self.stats["jobs_failed"] += 1

            except asyncio.CancelledError:
                logger.info(f"{worker_name} cancelled")
                break
            except Exception as e:
                logger.error(f"{worker_name} unexpected error: {e}")
                # Continue running after unexpected errors
                await asyncio.sleep(1)

        logger.info(f"{worker_name} stopped")

    def get_stats(self) -> Dict:
        """Get worker manager statistics"""
        uptime = None
        if self.stats["start_time"]:
            end_time = self.stats["stop_time"] or asyncio.get_event_loop().time()
            uptime = end_time - self.stats["start_time"]

        return {
            "running": self.running,
            "num_workers": len(self.worker_tasks),
            "registered_job_types": list(self.workers.keys()),
            "jobs_processed": self.stats["jobs_processed"],
            "jobs_failed": self.stats["jobs_failed"],
            "workers_started": self.stats["workers_started"],
            "workers_stopped": self.stats["workers_stopped"],
            "uptime_seconds": uptime,
            "queue_stats": self.job_queue.get_queue_stats(),
        }

    async def health_check(self) -> Dict:
        """Perform health check on worker system"""
        queue_stats = self.job_queue.get_queue_stats()
        worker_stats = self.get_stats()

        # Determine health status
        health_issues = []

        if not self.running:
            health_issues.append("Worker manager not running")

        if len(self.worker_tasks) < self.num_workers:
            health_issues.append(
                f"Only {len(self.worker_tasks)}/{self.num_workers} workers active"
            )

        if queue_stats["failed_jobs"] > queue_stats["completed_jobs"]:
            health_issues.append("More failed jobs than completed jobs")

        # Overall health
        health_status = "healthy" if not health_issues else "unhealthy"

        return {
            "status": health_status,
            "issues": health_issues,
            "worker_stats": worker_stats,
            "queue_stats": queue_stats,
            "timestamp": asyncio.get_event_loop().time(),
        }


# Global worker manager instance
_global_worker_manager: Optional[BackgroundWorkerManager] = None


async def get_worker_manager() -> BackgroundWorkerManager:
    """Get global worker manager instance"""
    global _global_worker_manager
    if _global_worker_manager is None:
        job_queue = await get_job_queue()
        _global_worker_manager = BackgroundWorkerManager(job_queue)
        logger.info("Created global background worker manager")
    return _global_worker_manager


async def start_background_workers(num_workers: int = 3):
    """Start global background workers"""
    worker_manager = await get_worker_manager()
    if num_workers != worker_manager.num_workers:
        worker_manager.num_workers = num_workers
    await worker_manager.start()


async def stop_background_workers():
    """Stop global background workers"""
    global _global_worker_manager
    if _global_worker_manager:
        await _global_worker_manager.stop()


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(stop_background_workers())

    # Register signal handlers for graceful shutdown
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
