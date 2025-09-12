#!/usr/bin/env python3
"""
Process existing queued downloads as background jobs
"""
import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

async def process_existing_downloads():
    """Convert existing queued downloads to background jobs"""
    try:
        from src.database.connection import get_db_session
        from src.database.models import Download
        from src.services.job_queue import get_job_queue, BackgroundJob, JobType, JobPriority
        
        # Get database session
        session_gen = get_db_session()
        session = next(session_gen)
        
        try:
            # Find all queued downloads
            queued_downloads = session.query(Download).filter(
                Download.status == "queued"
            ).all()
            
            print(f"🔍 Found {len(queued_downloads)} queued downloads")
            
            if not queued_downloads:
                print("✅ No queued downloads to process")
                return
            
            # Get job queue
            job_queue = await get_job_queue()
            
            processed_count = 0
            for download in queued_downloads:
                try:
                    # Create background job for each queued download
                    download_job = BackgroundJob(
                        type=JobType.VIDEO_DOWNLOAD,
                        priority=JobPriority.NORMAL,
                        payload={
                            'video_id': download.video_id,
                            'download_id': download.id,
                            'quality': 'best',
                            'force_redownload': False
                        },
                        created_by=f"existing-download-{download.id}"
                    )
                    
                    job_id = await job_queue.enqueue(download_job)
                    print(f"✅ Created job {job_id} for download {download.id}: {download.title}")
                    processed_count += 1
                    
                except Exception as e:
                    print(f"❌ Failed to create job for download {download.id}: {e}")
            
            print(f"🎉 Successfully created {processed_count} background jobs")
            
        finally:
            session.close()
            
    except Exception as e:
        print(f"💥 Error processing existing downloads: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(process_existing_downloads())