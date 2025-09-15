"""
Bulk Operations Background Worker
Handles bulk video operations like batch downloads, deletions, and status updates.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from ...database.connection import get_db
from ...database.models import Video
from ...utils.logger import get_logger
from ..background_worker_base import BaseWorker
from ..job_queue import BackgroundJob, JobPriority, JobType, get_job_queue

logger = get_logger(__name__)


class BulkOperationsWorker(BaseWorker):
    """
    Background worker for bulk video operations
    """

    async def process(self):
        """Process bulk operation job"""
        try:
            # Extract job payload
            operation_type = self.job.payload.get("operation_type")
            video_ids = self.job.payload.get("video_ids", [])
            operation_params = self.job.payload.get("params", {})

            if not operation_type:
                raise ValueError("Missing operation_type in job payload")

            if not video_ids:
                raise ValueError("Missing video_ids in job payload")

            logger.info(
                f"Starting bulk {operation_type} job for {len(video_ids)} videos"
            )
            await self.update_progress(
                5, f"Initializing bulk {operation_type} for {len(video_ids)} videos"
            )

            # Dispatch to appropriate bulk operation handler
            if operation_type == "download":
                result = await self._handle_bulk_download(video_ids, operation_params)
            elif operation_type == "delete":
                result = await self._handle_bulk_delete(video_ids, operation_params)
            elif operation_type == "status_update":
                result = await self._handle_bulk_status_update(
                    video_ids, operation_params
                )
            elif operation_type == "quality_check":
                result = await self._handle_bulk_quality_check(
                    video_ids, operation_params
                )
            elif operation_type == "quality_upgrade":
                result = await self._handle_bulk_quality_upgrade(
                    video_ids, operation_params
                )
            elif operation_type == "metadata_refresh":
                result = await self._handle_bulk_metadata_refresh(
                    video_ids, operation_params
                )
            else:
                raise ValueError(f"Unsupported bulk operation type: {operation_type}")

            await self.complete(result)

        except Exception as e:
            logger.error(f"Bulk operation job {self.job.id} failed: {e}")
            await self.fail(f"Bulk operation failed: {str(e)}")

    async def _handle_bulk_download(
        self, video_ids: List[int], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bulk video download by creating individual download jobs"""
        quality = params.get("quality", "best")
        force_redownload = params.get("force_redownload", False)

        total_videos = len(video_ids)
        successful_queues = 0
        failed_queues = 0

        job_queue = await get_job_queue()

        for i, video_id in enumerate(video_ids):
            try:
                # Create individual download job with high priority
                download_job = BackgroundJob(
                    type=JobType.VIDEO_DOWNLOAD,
                    priority=JobPriority.HIGH,
                    payload={
                        "video_id": video_id,
                        "quality": quality,
                        "force_redownload": force_redownload,
                    },
                    tags={"bulk_operation": True, "parent_job": self.job.id},
                )

                await job_queue.enqueue(download_job)
                successful_queues += 1

                # Update progress
                progress = int(10 + (i / total_videos) * 80)  # 10% to 90%
                await self.update_progress(
                    progress, f"Queued download {i+1}/{total_videos}"
                )

            except Exception as e:
                logger.error(f"Failed to queue download for video {video_id}: {e}")
                failed_queues += 1

        await self.update_progress(
            95, f"Queued {successful_queues} downloads, {failed_queues} failed"
        )

        return {
            "operation_type": "download",
            "total_videos": total_videos,
            "successful_queues": successful_queues,
            "failed_queues": failed_queues,
            "message": f"Queued {successful_queues} video downloads",
        }

    async def _handle_bulk_delete(
        self, video_ids: List[int], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bulk video deletion"""
        delete_files = params.get("delete_files", True)
        blacklist = params.get("blacklist", False)

        total_videos = len(video_ids)
        successful_deletes = 0
        failed_deletes = 0

        for i, video_id in enumerate(video_ids):
            try:
                # Delete video using existing service logic
                await self._delete_single_video(video_id, delete_files, blacklist)
                successful_deletes += 1

                # Update progress
                progress = int(10 + (i / total_videos) * 80)  # 10% to 90%
                await self.update_progress(
                    progress, f"Deleted video {i+1}/{total_videos}"
                )

            except Exception as e:
                logger.error(f"Failed to delete video {video_id}: {e}")
                failed_deletes += 1

        await self.update_progress(
            95, f"Deleted {successful_deletes} videos, {failed_deletes} failed"
        )

        return {
            "operation_type": "delete",
            "total_videos": total_videos,
            "successful_deletes": successful_deletes,
            "failed_deletes": failed_deletes,
            "message": f"Deleted {successful_deletes} videos",
        }

    async def _handle_bulk_status_update(
        self, video_ids: List[int], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bulk video status updates"""
        new_status = params.get("status")
        if not new_status:
            raise ValueError("Missing status parameter for bulk status update")

        total_videos = len(video_ids)
        successful_updates = 0
        failed_updates = 0

        # Process in batches to avoid overwhelming the database
        batch_size = 50
        for batch_start in range(0, total_videos, batch_size):
            batch_end = min(batch_start + batch_size, total_videos)
            batch_ids = video_ids[batch_start:batch_end]

            try:
                with get_db() as session:
                    updated_count = (
                        session.query(Video)
                        .filter(Video.id.in_(batch_ids))
                        .update({"status": new_status}, synchronize_session="fetch")
                    )
                    session.commit()

                    successful_updates += updated_count

                # Update progress
                progress = int(10 + (batch_end / total_videos) * 80)  # 10% to 90%
                await self.update_progress(
                    progress, f"Updated status for {batch_end}/{total_videos} videos"
                )

            except Exception as e:
                logger.error(
                    f"Failed to update status for batch {batch_start}-{batch_end}: {e}"
                )
                failed_updates += len(batch_ids)

        await self.update_progress(
            95, f"Updated {successful_updates} videos, {failed_updates} failed"
        )

        return {
            "operation_type": "status_update",
            "total_videos": total_videos,
            "successful_updates": successful_updates,
            "failed_updates": failed_updates,
            "new_status": new_status,
            "message": f"Updated status to '{new_status}' for {successful_updates} videos",
        }

    async def _handle_bulk_quality_check(
        self, video_ids: List[int], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bulk video quality checks"""
        from ...services.video_quality_service import video_quality_service

        total_videos = len(video_ids)
        successful_checks = 0
        failed_checks = 0
        quality_issues = []

        for i, video_id in enumerate(video_ids):
            try:
                # Run quality check in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                quality_result = await loop.run_in_executor(
                    None, video_quality_service.check_video_quality, video_id
                )

                if quality_result.get("issues"):
                    quality_issues.extend(quality_result["issues"])

                successful_checks += 1

                # Update progress
                progress = int(10 + (i / total_videos) * 80)  # 10% to 90%
                await self.update_progress(
                    progress, f"Checked quality {i+1}/{total_videos}"
                )

            except Exception as e:
                logger.error(f"Failed to check quality for video {video_id}: {e}")
                failed_checks += 1

        await self.update_progress(
            95, f"Checked {successful_checks} videos, {failed_checks} failed"
        )

        return {
            "operation_type": "quality_check",
            "total_videos": total_videos,
            "successful_checks": successful_checks,
            "failed_checks": failed_checks,
            "quality_issues": quality_issues,
            "message": f"Quality checked {successful_checks} videos, found {len(quality_issues)} issues",
        }

    async def _handle_bulk_quality_upgrade(
        self, video_ids: List[int], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bulk video quality upgrades by creating download jobs"""
        target_quality = params.get("target_quality", "best")

        # Similar to bulk download but with force_redownload=True for quality upgrade
        return await self._handle_bulk_download(
            video_ids, {"quality": target_quality, "force_redownload": True}
        )

    async def _handle_bulk_metadata_refresh(
        self, video_ids: List[int], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle bulk metadata refresh by creating individual metadata jobs"""
        force_refresh = params.get("force_refresh", True)

        total_videos = len(video_ids)
        successful_queues = 0
        failed_queues = 0

        job_queue = await get_job_queue()

        for i, video_id in enumerate(video_ids):
            try:
                # Create individual metadata enrichment job
                metadata_job = BackgroundJob(
                    type=JobType.METADATA_ENRICHMENT,
                    priority=JobPriority.NORMAL,
                    payload={
                        "video_id": video_id,
                        "force_refresh": force_refresh,
                        "enrichment_type": "video",
                    },
                    tags={"bulk_operation": True, "parent_job": self.job.id},
                )

                await job_queue.enqueue(metadata_job)
                successful_queues += 1

                # Update progress
                progress = int(10 + (i / total_videos) * 80)  # 10% to 90%
                await self.update_progress(
                    progress, f"Queued metadata refresh {i+1}/{total_videos}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to queue metadata refresh for video {video_id}: {e}"
                )
                failed_queues += 1

        await self.update_progress(
            95, f"Queued {successful_queues} metadata refreshes, {failed_queues} failed"
        )

        return {
            "operation_type": "metadata_refresh",
            "total_videos": total_videos,
            "successful_queues": successful_queues,
            "failed_queues": failed_queues,
            "message": f"Queued {successful_queues} metadata refresh jobs",
        }

    async def _delete_single_video(
        self, video_id: int, delete_files: bool = True, blacklist: bool = False
    ):
        """Delete a single video with file cleanup and optional blacklisting"""
        import os

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            if not video:
                logger.warning(f"Video {video_id} not found for deletion")
                return

            # Delete physical file if requested and exists
            if delete_files and video.file_path and os.path.exists(video.file_path):
                try:
                    os.remove(video.file_path)
                    logger.info(f"Deleted file: {video.file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete file {video.file_path}: {e}")

            # Add to blacklist if requested
            if blacklist and video.url:
                # This would integrate with existing blacklist functionality
                # For now, we'll just log it
                logger.info(f"Video {video_id} should be blacklisted: {video.url}")

            # Delete video record
            session.delete(video)
            session.commit()
            logger.info(f"Deleted video {video_id} from database")
