#!/usr/bin/env python3
"""
Fix stuck downloads by properly submitting them to the job queue system
This addresses the issue where downloads get stuck in "queued" status in the database
but never get submitted to Celery for actual processing.
"""

import asyncio
import sys
from datetime import datetime

from sqlalchemy.orm import Session

from src.database.connection import get_db, get_db_session
from src.database.models import Download, Video, VideoStatus
from src.services.job_queue import BackgroundJob, JobPriority, JobType, get_job_queue
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def fix_stuck_downloads():
    """Fix stuck downloads by resubmitting them to the job queue"""
    try:
        # Initialize database first
        from src.database.init_db import initialize_database
        if not initialize_database():
            raise Exception("Failed to initialize database")
        
        logger.info("Starting stuck download fix process...")
        
        # Get database session
        session_gen = get_db_session()
        session = next(session_gen)
        
        try:
            # Find all downloads stuck in "queued" status
            stuck_downloads = (
                session.query(Download)
                .filter(Download.status == "queued")
                .all()
            )
            
            if not stuck_downloads:
                logger.info("No stuck downloads found")
                return
            
            logger.info(f"Found {len(stuck_downloads)} stuck downloads")
            
            # Get job queue
            job_queue = await get_job_queue()
            
            fixed_count = 0
            error_count = 0
            
            for download in stuck_downloads:
                try:
                    # Get the associated video
                    video = session.query(Video).filter(Video.id == download.video_id).first()
                    if not video:
                        logger.warning(f"Video {download.video_id} not found for download {download.id}")
                        continue
                    
                    logger.info(f"Processing stuck download {download.id}: {download.title}")
                    
                    # Create background job for download processing
                    download_job = BackgroundJob(
                        type=JobType.VIDEO_DOWNLOAD,
                        priority=JobPriority.NORMAL,
                        payload={
                            "video_id": video.id,
                            "download_id": download.id,
                            "quality": download.quality or "best",
                            "force_redownload": False,
                        },
                        created_by=f"fix-stuck-downloads-{download.id}",
                    )
                    
                    # Enqueue the job
                    job_id = await job_queue.enqueue(download_job)
                    logger.info(f"Created background job {job_id} for download {download.id}")
                    
                    # Update download status to show it's been resubmitted
                    download.status = "downloading"
                    download.updated_at = datetime.utcnow()
                    
                    # Make sure video is in downloading status
                    video.status = VideoStatus.DOWNLOADING
                    video.updated_at = datetime.utcnow()
                    
                    fixed_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to fix download {download.id}: {e}")
                    error_count += 1
                    continue
            
            # Commit all changes
            session.commit()
            
            logger.info(f"Fixed {fixed_count} downloads, {error_count} errors")
            print(f"✅ Fixed {fixed_count} stuck downloads")
            if error_count > 0:
                print(f"⚠️  {error_count} downloads had errors")
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error in fix_stuck_downloads: {e}")
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("🔧 Fixing stuck downloads...")
    asyncio.run(fix_stuck_downloads())