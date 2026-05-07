"""
Bulk Video Metadata Enrichment Background Worker
Handles bulk video metadata enrichment operations with progress tracking.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from src.database.connection import get_db
from src.database.models import Video
from src.services.background_worker_base import HybridWorker
from src.services.job_queue import BackgroundJob, JobQueue
from src.services.metadata_enrichment_service import MetadataEnrichmentService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BulkVideoMetadataWorker(HybridWorker):
    """
    Background worker for bulk video metadata enrichment

    Processes multiple videos through the metadata enrichment pipeline,
    gathering data from MusicBrainz, Discogs, Spotify, Last.fm, IMVDb,
    YouTube, and local FFmpeg analysis.
    """

    def __init__(self, job_queue: JobQueue, job: BackgroundJob):
        super().__init__(job_queue, job)
        self.enrichment_service = None

    async def process_hybrid(self):
        """Process bulk video metadata enrichment with database and network operations"""

        # Extract job parameters
        force_refresh = self.job.payload.get("force_refresh", True)
        days_since_enriched = self.job.payload.get("days_since_enriched", 7)
        limit = self.job.payload.get("limit", None)
        video_ids = self.job.payload.get("video_ids", None)

        logger.info(
            f"Starting bulk video metadata enrichment: "
            f"force_refresh={force_refresh}, "
            f"days_since_enriched={days_since_enriched}, "
            f"limit={limit}, "
            f"specific_videos={len(video_ids) if video_ids else 'all'}"
        )

        try:
            await self.update_progress(5, "Initializing enrichment service...")

            # Initialize enrichment service
            self.enrichment_service = MetadataEnrichmentService()

            await self.update_progress(10, "Querying videos to process...")

            # Get videos to process
            async with self.database_session() as session:
                query = session.query(Video).options(joinedload(Video.artist))

                # Filter by specific video IDs if provided
                if video_ids:
                    query = query.filter(Video.id.in_(video_ids))
                    logger.info(f"Processing {len(video_ids)} specific video IDs")
                else:
                    # Filter by last_enriched date if days_since_enriched > 0
                    if days_since_enriched > 0:
                        cutoff_date = datetime.utcnow() - timedelta(
                            days=days_since_enriched
                        )
                        query = query.filter(
                            or_(
                                Video.last_enriched == None,
                                Video.last_enriched < cutoff_date,
                            )
                        )
                        logger.info(
                            f"Filtering videos not enriched since {cutoff_date}"
                        )

                if limit:
                    query = query.limit(limit)

                videos = query.all()

            if not videos:
                await self.complete(
                    {
                        "processed": 0,
                        "updated": 0,
                        "errors": 0,
                        "message": "No videos found to process",
                    }
                )
                return

            total_videos = len(videos)
            logger.info(f"Found {total_videos} videos to enrich")

            await self.update_progress(15, f"Processing {total_videos} videos...")

            # Process videos with real enrichment service
            processed = 0
            updated = 0
            errors = 0
            error_details = []

            for video in videos:
                try:
                    # Calculate progress (15-95% range for video processing)
                    progress = int(15 + (processed / total_videos) * 80)
                    await self.update_progress(
                        progress,
                        f"Enriching {video.title} ({processed + 1}/{total_videos})",
                    )

                    logger.info(f"Enriching video {video.id}: {video.title}")

                    # Call the REAL enrichment service
                    enrichment_result = (
                        await self.enrichment_service.enrich_video_metadata(
                            video.id, force_refresh=force_refresh
                        )
                    )

                    if enrichment_result.success:
                        if enrichment_result.enriched_fields:
                            updated += 1
                            logger.info(
                                f"Video {video.id} enriched successfully. "
                                f"Fields updated: {enrichment_result.enriched_fields}"
                            )
                        else:
                            logger.info(
                                f"Video {video.id} processed but no fields updated"
                            )
                    else:
                        errors += 1
                        error_msg = (
                            "; ".join(enrichment_result.errors)
                            if enrichment_result.errors
                            else "Unknown error"
                        )
                        error_details.append(
                            {
                                "video_id": video.id,
                                "title": video.title,
                                "error": error_msg,
                            }
                        )
                        logger.warning(
                            f"Video {video.id} enrichment completed with errors: {error_msg}"
                        )

                    processed += 1

                    # Commit progress periodically (every 10 videos)
                    if processed % 10 == 0:
                        async with self.database_session() as session:
                            session.commit()
                        logger.info(
                            f"Committed progress: {processed}/{total_videos} videos"
                        )

                    # Yield control to event loop to prevent blocking
                    await asyncio.sleep(0)

                except Exception as e:
                    errors += 1
                    error_msg = str(e)
                    error_details.append(
                        {"video_id": video.id, "title": video.title, "error": error_msg}
                    )
                    logger.error(
                        f"Error enriching video {video.id}: {e}", exc_info=True
                    )
                    # Yield control even on errors
                    await asyncio.sleep(0)

            # Final commit
            async with self.database_session() as session:
                session.commit()

            await self.update_progress(95, "Finalizing results...")

            logger.info(
                f"Bulk video metadata enrichment completed: "
                f"{processed} processed, {updated} updated, {errors} errors"
            )

            # Complete with results
            await self.complete(
                {
                    "processed": processed,
                    "updated": updated,
                    "errors": errors,
                    "total_videos": total_videos,
                    "error_details": error_details if error_details else [],
                    "message": f"Processed {processed} videos ({updated} updated, {errors} errors)",
                }
            )

        except Exception as e:
            logger.error(
                f"Bulk video metadata enrichment job {self.job.id} failed: {e}",
                exc_info=True,
            )
            await self.fail(f"Bulk enrichment failed: {str(e)}")
