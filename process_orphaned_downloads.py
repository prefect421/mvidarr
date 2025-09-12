#!/usr/bin/env python3
"""
Process orphaned downloads that don't have background jobs
"""
import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

async def process_orphaned_downloads():
    """Create background jobs for existing queued downloads"""
    try:
        # Import after adding to path
        from src.database.connection import get_db_session
        from src.database.models import Download, Video
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
                    # Get video info
                    video = session.query(Video).filter(Video.id == download.video_id).first()
                    if not video:
                        print(f"❌ Video {download.video_id} not found for download {download.id}")
                        continue
                    
                    print(f"📹 Processing download {download.id}: {download.title} (Video ID: {download.video_id})")
                    
                    # Create background job for each queued download
                    download_job = BackgroundJob(
                        type=JobType.VIDEO_DOWNLOAD,
                        priority=JobPriority.NORMAL,
                        payload={
                            'video_id': download.video_id,
                            'download_id': download.id,
                            'quality': 'best',
                            'force_redownload': True  # Force redownload since these are orphaned
                        },
                        created_by=f"orphaned-download-{download.id}"
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
        print(f"💥 Error processing orphaned downloads: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Initialize database first
    try:
        from src.database.connection import get_db_session
        from src.config.config import Config
        from src.database.connection import DatabaseManager
        import src.database.connection as db_conn
        
        # Initialize database manager
        config = Config()
        db_conn.db_manager = DatabaseManager(config)
        
        # Create engine and session factory
        db_conn.engine = db_conn.db_manager.create_engine()
        db_conn.SessionLocal = db_conn.db_manager.create_session_factory()
        
        print("✅ Database initialized")
        
        # Run the processing
        asyncio.run(process_orphaned_downloads())
        
    except Exception as e:
        print(f"💥 Database initialization failed: {e}")
        sys.exit(1)