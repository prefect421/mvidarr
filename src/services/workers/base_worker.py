"""
Base Worker Module
Provides base worker classes with async service execution support for workers.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Optional

# Import the actual BaseWorker from parent module
from src.services.background_worker_base import BaseWorker as _BaseWorker
from src.services.background_worker_base import (
    DatabaseWorker,
    HybridWorker,
    NetworkWorker,
)

logger = logging.getLogger(__name__)


class BaseWorker(_BaseWorker):
    """
    Extended BaseWorker with run_async_service support for running synchronous
    functions in a thread pool to avoid blocking the async event loop.
    """

    async def run_async_service(self, func: Callable, *args, **kwargs) -> Any:
        """
        Run a synchronous service function in a thread pool to avoid blocking
        the async event loop.

        Args:
            func: Synchronous function to run
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Result from the function

        Example:
            result = await self.run_async_service(
                lambda: some_sync_service.process_data(param1, param2)
            )
        """
        try:
            # Use asyncio.to_thread() to run synchronous code in thread pool
            # This is the modern Python 3.9+ way to run sync code in a thread
            result = await asyncio.to_thread(func, *args, **kwargs)
            return result
        except Exception as e:
            self.logger.error(f"Error running async service for job {self.job.id}: {e}")
            raise

    async def get_data(self, query_func: Callable) -> Any:
        """
        Execute a database query function and return the result.

        This is a convenience method for getting data from the database
        without needing to manage the session context.

        Args:
            query_func: Function that takes a session and returns query result

        Returns:
            Query result

        Example:
            video = await self.get_data(
                lambda session: session.query(Video).filter(Video.id == video_id).first()
            )
        """
        async with self.database_session() as session:
            result = query_func(session)
            return result


# Re-export all worker types
__all__ = ["BaseWorker", "DatabaseWorker", "NetworkWorker", "HybridWorker"]
