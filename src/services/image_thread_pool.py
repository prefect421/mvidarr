"""
MVidarr Image Thread Pool Service - Phase 2 Week 20
Advanced thread pool management for concurrent image processing operations
"""

import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import psutil
from src.utils.logger import get_logger

logger = get_logger("mvidarr.image_thread_pool")


@dataclass
class ThreadPoolConfig:
    """Configuration for image thread pool"""

    max_workers: int
    queue_size: int = 1000
    thread_name_prefix: str = "ImageWorker"
    enable_monitoring: bool = True
    memory_limit_mb: Optional[int] = None

    @classmethod
    def auto_configure(cls) -> "ThreadPoolConfig":
        """Auto-configure based on system resources"""
        cpu_count = os.cpu_count() or 4

        # Conservative threading for image processing (I/O + CPU bound)
        max_workers = min(cpu_count * 2, 16)  # Cap at 16 threads

        # Memory-based adjustment
        total_memory_gb = psutil.virtual_memory().total / (1024**3)
        if total_memory_gb < 4:
            max_workers = min(max_workers, 4)  # Low memory systems
        elif total_memory_gb > 16:
            max_workers = min(max_workers * 2, 32)  # High memory systems

        return cls(
            max_workers=max_workers,
            queue_size=max_workers * 50,  # 50 jobs per worker max
            memory_limit_mb=int(
                total_memory_gb * 1024 * 0.7
            ),  # Use 70% of available memory
        )


@dataclass
class ThreadPoolStats:
    """Statistics for thread pool operations"""

    threads_active: int = 0
    threads_idle: int = 0
    jobs_submitted: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    jobs_pending: int = 0
    average_job_time: float = 0.0
    memory_usage_mb: float = 0.0
    uptime_seconds: float = 0.0


class ImageThreadPool:
    """Thread pool specifically optimized for image processing operations"""

    def __init__(self, config: Optional[ThreadPoolConfig] = None):
        """
        Initialize image thread pool

        Args:
            config: Thread pool configuration (auto-configured if None)
        """
        self.config = config or ThreadPoolConfig.auto_configure()
        self.executor: Optional[ThreadPoolExecutor] = None
        self.stats = ThreadPoolStats()
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._job_times: List[float] = []
        self._shutdown = False

        logger.info(
            f"🧵 Image thread pool configured: {self.config.max_workers} workers, {self.config.queue_size} queue size"
        )

    def start(self):
        """Start the thread pool"""
        if self.executor is not None:
            logger.warning("⚠️ Thread pool already started")
            return

        self.executor = ThreadPoolExecutor(
            max_workers=self.config.max_workers,
            thread_name_prefix=self.config.thread_name_prefix,
        )
        self._shutdown = False
        self._start_time = time.time()

        logger.info(
            f"✅ Image thread pool started with {self.config.max_workers} workers"
        )

    def shutdown(self, wait: bool = True):
        """Shutdown the thread pool"""
        if self.executor is None:
            return

        self._shutdown = True
        self.executor.shutdown(wait=wait)
        self.executor = None

        logger.info("🔄 Image thread pool shut down")

    def is_running(self) -> bool:
        """Check if thread pool is running"""
        return self.executor is not None and not self._shutdown

    def submit_job(self, func: Callable, *args, **kwargs) -> Future:
        """
        Submit a job to the thread pool

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Future object for the submitted job
        """
        if not self.is_running():
            raise RuntimeError("Thread pool not started")

        with self._lock:
            self.stats.jobs_submitted += 1
            self.stats.jobs_pending += 1

        # Submit job with timing wrapper
        future = self.executor.submit(self._timed_execution, func, *args, **kwargs)

        # Add completion callback
        future.add_done_callback(self._job_completed)

        return future

    def _timed_execution(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with timing"""
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            execution_time = time.time() - start_time
            with self._lock:
                self._job_times.append(execution_time)
                # Keep only last 1000 job times for average calculation
                if len(self._job_times) > 1000:
                    self._job_times = self._job_times[-1000:]

    def _job_completed(self, future: Future):
        """Callback for when a job completes"""
        with self._lock:
            self.stats.jobs_pending -= 1

            if future.exception() is None:
                self.stats.jobs_completed += 1
            else:
                self.stats.jobs_failed += 1
                logger.error(f"❌ Image processing job failed: {future.exception()}")

    def get_stats(self) -> ThreadPoolStats:
        """Get current thread pool statistics"""
        with self._lock:
            stats = ThreadPoolStats(
                threads_active=self.config.max_workers if self.is_running() else 0,
                threads_idle=self.config.max_workers
                - min(self.stats.jobs_pending, self.config.max_workers),
                jobs_submitted=self.stats.jobs_submitted,
                jobs_completed=self.stats.jobs_completed,
                jobs_failed=self.stats.jobs_failed,
                jobs_pending=self.stats.jobs_pending,
                average_job_time=(
                    sum(self._job_times) / len(self._job_times)
                    if self._job_times
                    else 0.0
                ),
                memory_usage_mb=psutil.Process().memory_info().rss / 1024 / 1024,
                uptime_seconds=time.time() - self._start_time,
            )

        return stats

    @contextmanager
    def batch_execution(self, jobs: List[tuple]):
        """
        Context manager for batch job execution

        Args:
            jobs: List of (function, args, kwargs) tuples

        Yields:
            Generator of completed futures
        """
        if not self.is_running():
            raise RuntimeError("Thread pool not started")

        futures = []

        try:
            # Submit all jobs
            for job_spec in jobs:
                if len(job_spec) == 3:
                    func, args, kwargs = job_spec
                elif len(job_spec) == 2:
                    func, args = job_spec
                    kwargs = {}
                else:
                    func = job_spec[0]
                    args = ()
                    kwargs = {}

                future = self.submit_job(func, *args, **kwargs)
                futures.append(future)

            logger.info(f"📦 Submitted {len(futures)} jobs for batch execution")

            # Yield completed futures
            for future in as_completed(futures):
                yield future

        except Exception as e:
            logger.error(f"❌ Batch execution error: {e}")
            # Cancel remaining futures
            for future in futures:
                if not future.done():
                    future.cancel()
            raise

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all pending jobs to complete

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if all jobs completed, False if timeout
        """
        if not self.is_running():
            return True

        start_time = time.time()

        while self.stats.jobs_pending > 0:
            if timeout and (time.time() - start_time) > timeout:
                return False
            time.sleep(0.1)

        return True

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.shutdown(wait=True)


class ImageProcessingPool:
    """High-level interface for image processing with thread pools"""

    def __init__(self, pool_config: Optional[ThreadPoolConfig] = None):
        """Initialize image processing pool"""
        self.pool = ImageThreadPool(pool_config)
        self._active_batches: Dict[str, List[Future]] = {}

    async def start(self):
        """Start the processing pool (async interface)"""
        self.pool.start()

    async def shutdown(self):
        """Shutdown the processing pool (async interface)"""
        self.pool.shutdown(wait=True)

    async def process_images_batch(
        self,
        processing_func: Callable,
        image_paths: List[Path],
        batch_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> List[Any]:
        """
        Process a batch of images concurrently

        Args:
            processing_func: Function to apply to each image
            image_paths: List of image file paths
            batch_id: Optional identifier for the batch
            progress_callback: Optional callback for progress updates

        Returns:
            List of processing results
        """
        if not self.pool.is_running():
            await self.start()

        batch_id = batch_id or f"batch_{int(time.time())}"
        results = []

        logger.info(f"🖼️ Processing {len(image_paths)} images in batch '{batch_id}'")

        # Submit all jobs
        jobs = [(processing_func, (path,), {}) for path in image_paths]

        completed = 0
        with self.pool.batch_execution(jobs) as batch_futures:
            for future in batch_futures:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"❌ Image processing failed: {e}")
                    results.append({"error": str(e)})

                completed += 1
                if progress_callback:
                    progress_callback(completed, len(image_paths))

        logger.info(
            f"✅ Batch '{batch_id}' completed: {completed}/{len(image_paths)} images processed"
        )
        return results

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics"""
        stats = self.pool.get_stats()

        return {
            "thread_pool": {
                "active_threads": stats.threads_active,
                "idle_threads": stats.threads_idle,
                "max_workers": self.pool.config.max_workers,
            },
            "jobs": {
                "submitted": stats.jobs_submitted,
                "completed": stats.jobs_completed,
                "failed": stats.jobs_failed,
                "pending": stats.jobs_pending,
                "success_rate": (stats.jobs_completed / max(stats.jobs_submitted, 1))
                * 100,
            },
            "performance": {
                "average_job_time": stats.average_job_time,
                "jobs_per_second": stats.jobs_completed / max(stats.uptime_seconds, 1),
                "uptime_hours": stats.uptime_seconds / 3600,
            },
            "resources": {
                "memory_usage_mb": stats.memory_usage_mb,
                "memory_limit_mb": self.pool.config.memory_limit_mb,
            },
        }

    def __enter__(self):
        """Context manager entry"""
        self.pool.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.pool.shutdown(wait=True)


# Global image processing pool instance
_global_pool: Optional[ImageProcessingPool] = None


def get_image_processing_pool() -> ImageProcessingPool:
    """Get global image processing pool instance"""
    global _global_pool

    if _global_pool is None:
        config = ThreadPoolConfig.auto_configure()
        _global_pool = ImageProcessingPool(config)
        logger.info(
            f"🎯 Global image processing pool initialized: {config.max_workers} workers"
        )

    return _global_pool


async def shutdown_global_pool():
    """Shutdown global image processing pool"""
    global _global_pool

    if _global_pool is not None:
        await _global_pool.shutdown()
        _global_pool = None
        logger.info("🔄 Global image processing pool shut down")


# Convenience functions for common image processing operations
async def process_thumbnails_concurrent(
    image_paths: List[Path],
    thumbnail_func: Callable,
    progress_callback: Optional[Callable] = None,
) -> List[Any]:
    """Process thumbnails concurrently using the global pool"""
    pool = get_image_processing_pool()
    return await pool.process_images_batch(
        processing_func=thumbnail_func,
        image_paths=image_paths,
        batch_id="thumbnails",
        progress_callback=progress_callback,
    )


async def optimize_images_concurrent(
    image_paths: List[Path],
    optimization_func: Callable,
    progress_callback: Optional[Callable] = None,
) -> List[Any]:
    """Optimize images concurrently using the global pool"""
    pool = get_image_processing_pool()
    return await pool.process_images_batch(
        processing_func=optimization_func,
        image_paths=image_paths,
        batch_id="optimization",
        progress_callback=progress_callback,
    )
