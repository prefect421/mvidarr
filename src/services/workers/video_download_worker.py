"""
Video Download Background Worker
Handles video download jobs with progress tracking and error recovery.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError

from ...database.connection import get_db
from ...database.models import Download, Video, VideoStatus
from ...services.ytdlp_service import ytdlp_service
from ...utils.logger import get_logger
from ..background_worker_base import BaseWorker

logger = get_logger(__name__)


class VideoDownloadWorker(BaseWorker):
    """
    Background worker for video download operations
    """

    async def process(self):
        """Process video download job"""
        try:
            # Extract job payload
            video_id = self.job.payload.get("video_id")
            quality = self.job.payload.get("quality", "best")
            force_redownload = self.job.payload.get("force_redownload", False)

            if not video_id:
                raise ValueError("Missing video_id in job payload")

            logger.info(f"Starting video download job for video {video_id}")
            await self.update_progress(5, f"Initializing download for video {video_id}")

            # Get video from database
            from ...database.connection import get_db_session

            session_gen = get_db_session()
            session = next(session_gen)
            try:
                video = session.query(Video).filter(Video.id == video_id).first()
                if not video:
                    raise ValueError(f"Video {video_id} not found")

                video_title = video.title or f"Video {video_id}"
                video_url = video.url
                artist_name = video.artist.name if video.artist else "Unknown Artist"
            finally:
                session.close()

            await self.update_progress(10, f"Starting download: {video_title}")

            # Check if video is already downloaded and not forcing redownload
            if not force_redownload:
                with get_db() as session:
                    video = session.query(Video).filter(Video.id == video_id).first()
                    if (
                        video
                        and video.local_path
                        and video.status == VideoStatus.DOWNLOADED
                    ):
                        # Check if file actually exists
                        import os

                        if os.path.exists(video.local_path):
                            await self.complete(
                                {
                                    "video_id": video_id,
                                    "message": f"Video already downloaded: {video_title}",
                                    "file_path": video.local_path,
                                    "skipped": True,
                                }
                            )
                            return

            await self.update_progress(15, f"Preparing download for: {video_title}")

            # Create or update download record
            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                download = (
                    session.query(Download)
                    .filter(Download.video_id == video_id)
                    .first()
                )

                if not download:
                    download = Download(
                        artist_id=video.artist_id,
                        video_id=video_id,
                        title=video.title,
                        original_url=video.url or "Unknown URL",
                        status="downloading",
                        progress=0,
                    )
                    session.add(download)
                else:
                    download.status = "downloading"
                    download.progress = 0
                    download.error_message = None

                session.commit()
                download_id = download.id

            await self.update_progress(
                20, f"Download record created for: {video_title}"
            )

            # Set up progress callback
            async def progress_callback(progress_data: Dict[str, Any]):
                """Handle download progress updates"""
                try:
                    if "percent" in progress_data:
                        # Map download progress to job progress (20-95%)
                        download_progress = float(progress_data["percent"].rstrip("%"))
                        job_progress = int(
                            20 + (download_progress * 0.75)
                        )  # 20% to 95%

                        status_msg = (
                            f"Downloading {video_title}: {download_progress:.1f}%"
                        )
                        if "speed" in progress_data:
                            status_msg += f" at {progress_data['speed']}"

                        await self.update_progress(job_progress, status_msg)

                        # Update download record
                        with get_db() as session:
                            download = (
                                session.query(Download)
                                .filter(Download.id == download_id)
                                .first()
                            )
                            if download:
                                download.progress = download_progress
                                session.commit()

                except Exception as e:
                    logger.warning(f"Error updating download progress: {e}")

            # Perform the actual download using ytdlp service
            try:
                logger.info(
                    f"Starting ytdlp download for video {video_id}: {video_url}"
                )

                # Use the existing ytdlp service but run in async context
                loop = asyncio.get_event_loop()
                download_result = await loop.run_in_executor(
                    None,
                    self._sync_download_video,
                    video_id,
                    video_url,
                    quality,
                    progress_callback,
                )

                if not download_result or not download_result.get("success"):
                    raise Exception(download_result.get("error", "Download failed"))

                # The ytdlp service runs asynchronously, so we need to wait for completion
                # and then get the result from the database
                file_path = None
                download_completed = False
                max_wait_time = 300  # 5 minutes max wait
                wait_interval = 2  # Check every 2 seconds
                elapsed_time = 0

                while not download_completed and elapsed_time < max_wait_time:
                    await asyncio.sleep(wait_interval)
                    elapsed_time += wait_interval

                    # Check if download completed by checking video status in database
                    with get_db() as session:
                        updated_video = (
                            session.query(Video).filter(Video.id == video_id).first()
                        )
                        if (
                            updated_video
                            and updated_video.local_path
                            and updated_video.status == VideoStatus.DOWNLOADED
                        ):
                            file_path = updated_video.local_path
                            download_completed = True
                            # Get additional info for return value
                            download_result = {
                                "success": True,
                                "file_path": file_path,
                                "duration": updated_video.duration,
                                "file_size": (
                                    updated_video.video_metadata.get("file_size")
                                    if updated_video.video_metadata
                                    else None
                                ),
                                "technical_metadata": updated_video.video_metadata
                                or {},
                            }
                            break
                        elif (
                            updated_video and updated_video.status == VideoStatus.FAILED
                        ):
                            raise Exception("Download failed - video status is FAILED")

                    # Update progress during wait
                    progress_percent = min(
                        90, 20 + int((elapsed_time / max_wait_time) * 70)
                    )
                    await self.update_progress(
                        progress_percent,
                        f"Downloading {video_title}... ({elapsed_time}s)",
                    )

                if not download_completed:
                    raise Exception(f"Download timed out after {max_wait_time} seconds")

                if not file_path:
                    raise Exception("No file path found after download completion")

                await self.update_progress(95, f"Download completed: {video_title}")

                # Note: Video record is already updated by ytdlp service
                logger.info(
                    f"Video {video_id} download completed, file saved to: {file_path}"
                )

                # Update download record as completed
                with get_db() as session:
                    download = (
                        session.query(Download)
                        .filter(Download.id == download_id)
                        .first()
                    )
                    if download:
                        download.status = "completed"
                        download.progress = 100.0
                        download.completed_at = asyncio.get_event_loop().time()
                        session.commit()

                await self.complete(
                    {
                        "video_id": video_id,
                        "file_path": file_path,
                        "message": f"Successfully downloaded: {video_title}",
                        "artist": artist_name,
                        "file_size": download_result.get("file_size"),
                        "duration": download_result.get("duration"),
                    }
                )

            except Exception as download_error:
                logger.error(f"Download failed for video {video_id}: {download_error}")

                # Update download record as failed
                with get_db() as session:
                    download = (
                        session.query(Download)
                        .filter(Download.id == download_id)
                        .first()
                    )
                    if download:
                        download.status = "failed"
                        download.error_message = str(download_error)
                        session.commit()

                raise download_error

        except Exception as e:
            logger.error(f"Video download job {self.job.id} failed: {e}")
            await self.fail(f"Video download failed: {str(e)}")

    def _sync_download_video(
        self, video_id: int, video_url: str, quality: str, progress_callback
    ) -> Dict[str, Any]:
        """
        Synchronous video download using ytdlp service
        This runs in a thread pool to avoid blocking the async event loop
        """
        try:
            # Get video info from database to get artist and title
            from ...database.connection import get_db_session

            session_gen = get_db_session()
            session = next(session_gen)
            try:
                video = session.query(Video).filter(Video.id == video_id).first()
                if not video:
                    raise ValueError(f"Video {video_id} not found")

                artist_name = video.artist.name if video.artist else "Unknown Artist"
                video_title = video.title or f"Video {video_id}"
            finally:
                session.close()

            # Use the existing ytdlp_service with correct method
            result = ytdlp_service.add_music_video_download(
                artist=artist_name,
                title=video_title,
                url=video_url,
                quality=quality,
                video_id=video_id,
            )

            # Convert ytdlp service response to expected format
            if result.get("success"):
                return {
                    "success": True,
                    "file_path": result.get("file_path"),
                    "file_size": result.get("file_size"),
                    "duration": result.get("duration"),
                    "technical_metadata": result.get("metadata", {}),
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Download failed"),
                }

        except Exception as e:
            logger.error(f"Sync download failed for video {video_id}: {e}")
            return {"success": False, "error": str(e)}
