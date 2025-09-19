"""
Advanced Job Scheduler Service
Manages scheduled jobs, dependencies, and background processing
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.services.job_queue import get_job_queue
from src.utils.structured_logger import get_structured_logger

logger = get_structured_logger("mvidarr.services.job_scheduler")


class JobScheduler:
    """
    Job scheduler that handles periodic processing of scheduled jobs and dependencies
    """
    
    def __init__(self, check_interval: int = 30):
        """
        Initialize job scheduler
        
        Args:
            check_interval: How often to check for ready jobs (in seconds)
        """
        self.check_interval = check_interval
        self.running = False
        self.scheduler_task: Optional[asyncio.Task] = None
        self.stats = {
            "scheduled_jobs_processed": 0,
            "dependency_jobs_processed": 0,
            "last_check": None,
            "uptime_start": None
        }
    
    async def start(self):
        """Start the job scheduler"""
        if self.running:
            logger.warning("Job scheduler is already running")
            return
        
        self.running = True
        self.stats["uptime_start"] = datetime.utcnow()
        
        logger.info(f"Starting job scheduler with {self.check_interval}s check interval")
        
        # Start the main scheduler loop
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("✅ Job scheduler started successfully")
    
    async def stop(self):
        """Stop the job scheduler"""
        if not self.running:
            return
        
        logger.info("Stopping job scheduler...")
        self.running = False
        
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ Job scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop that processes jobs periodically"""
        try:
            while self.running:
                try:
                    await self._process_ready_jobs()
                    self.stats["last_check"] = datetime.utcnow()
                    
                    # Sleep for the check interval
                    await asyncio.sleep(self.check_interval)
                    
                except Exception as e:
                    logger.error(f"Error in scheduler loop: {e}")
                    # Continue running even if there's an error
                    await asyncio.sleep(5)  # Short delay before retrying
                    
        except asyncio.CancelledError:
            logger.info("Scheduler loop cancelled")
            raise
    
    async def _process_ready_jobs(self):
        """Process jobs that are ready for execution"""
        try:
            job_queue = await get_job_queue()
            
            # Process scheduled jobs that are ready
            scheduled_count = await self._process_scheduled_jobs(job_queue)
            if scheduled_count > 0:
                self.stats["scheduled_jobs_processed"] += scheduled_count
                logger.info(f"Processed {scheduled_count} scheduled jobs")
            
            # Process jobs waiting for dependencies
            dependency_count = await self._process_dependency_jobs(job_queue)
            if dependency_count > 0:
                self.stats["dependency_jobs_processed"] += dependency_count
                logger.info(f"Processed {dependency_count} dependency jobs")
            
            # Log periodic status if there's activity
            if scheduled_count > 0 or dependency_count > 0:
                logger.debug(f"Scheduler check complete: {scheduled_count} scheduled, {dependency_count} dependency jobs processed")
            
        except Exception as e:
            logger.error(f"Error processing ready jobs: {e}")
    
    async def _process_scheduled_jobs(self, job_queue) -> int:
        """Process jobs that are scheduled for execution"""
        try:
            initial_scheduled = len([j for j in job_queue._jobs.values() if j.status.value == "scheduled"])
            
            await job_queue.process_scheduled_jobs()
            
            final_scheduled = len([j for j in job_queue._jobs.values() if j.status.value == "scheduled"])
            
            # Return the number of jobs that were processed
            return initial_scheduled - final_scheduled
            
        except Exception as e:
            logger.error(f"Error processing scheduled jobs: {e}")
            return 0
    
    async def _process_dependency_jobs(self, job_queue) -> int:
        """Process jobs waiting for dependencies"""
        try:
            initial_waiting = len([j for j in job_queue._jobs.values() if j.status.value == "waiting_dependencies"])
            
            await job_queue.process_waiting_jobs()
            
            final_waiting = len([j for j in job_queue._jobs.values() if j.status.value == "waiting_dependencies"])
            
            # Return the number of jobs that were processed
            return initial_waiting - final_waiting
            
        except Exception as e:
            logger.error(f"Error processing dependency jobs: {e}")
            return 0
    
    def get_stats(self) -> dict:
        """Get scheduler statistics"""
        uptime = None
        if self.stats["uptime_start"]:
            uptime = (datetime.utcnow() - self.stats["uptime_start"]).total_seconds()
        
        return {
            "running": self.running,
            "check_interval": self.check_interval,
            "scheduled_jobs_processed": self.stats["scheduled_jobs_processed"],
            "dependency_jobs_processed": self.stats["dependency_jobs_processed"],
            "last_check": self.stats["last_check"].isoformat() if self.stats["last_check"] else None,
            "uptime_seconds": uptime,
            "uptime_start": self.stats["uptime_start"].isoformat() if self.stats["uptime_start"] else None
        }
    
    async def force_check(self):
        """Force an immediate check for ready jobs"""
        logger.info("Force checking for ready jobs")
        await self._process_ready_jobs()


# Global scheduler instance
_global_scheduler: Optional[JobScheduler] = None
_scheduler_lock = asyncio.Lock()


async def get_job_scheduler() -> JobScheduler:
    """Get global job scheduler instance"""
    global _global_scheduler
    if _global_scheduler is None:
        async with _scheduler_lock:
            if _global_scheduler is None:
                _global_scheduler = JobScheduler(check_interval=30)  # Check every 30 seconds
                logger.info("Created global job scheduler instance")
    return _global_scheduler


async def start_job_scheduler():
    """Start the global job scheduler"""
    scheduler = await get_job_scheduler()
    await scheduler.start()


async def stop_job_scheduler():
    """Stop the global job scheduler"""
    global _global_scheduler
    if _global_scheduler:
        await _global_scheduler.stop()
        logger.info("Job scheduler shutdown completed")


async def get_scheduler_stats() -> dict:
    """Get scheduler statistics"""
    scheduler = await get_job_scheduler()
    return scheduler.get_stats()


async def force_scheduler_check():
    """Force an immediate scheduler check"""
    scheduler = await get_job_scheduler()
    await scheduler.force_check()