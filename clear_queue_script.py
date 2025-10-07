#!/usr/bin/env python3
"""
Script to clear stuck downloads from the database
"""

import sys
from datetime import datetime, timedelta

from src.database.connection import get_db_session
from src.database.models import Download, Video, VideoStatus
from src.database.init_db import initialize_database
from src.utils.logger import get_logger

logger = get_logger(__name__)


def clear_stuck_downloads(minutes_threshold=10):
    """Clear downloads stuck in queued/downloading status"""
    try:
        # Initialize database
        if not initialize_database():
            raise Exception("Failed to initialize database")
        
        session_gen = get_db_session()
        session = next(session_gen)
        
        try:
            # Calculate cutoff time
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes_threshold)
            
            # Find stuck downloads
            stuck_downloads = (
                session.query(Download)
                .filter(
                    Download.status.in_(["queued", "downloading"]),
                    Download.created_at < cutoff_time
                )
                .all()
            )
            
            print(f"Found {len(stuck_downloads)} stuck downloads older than {minutes_threshold} minutes")
            
            cleared_count = 0
            for download in stuck_downloads:
                print(f"Clearing download {download.id}: {download.title}")
                
                # Update download status to failed
                download.status = "failed"
                download.error_message = f"Cleared as stuck after {minutes_threshold} minutes"
                download.completed_at = datetime.utcnow()
                
                # Reset associated video status back to WANTED
                if download.video_id:
                    video = session.query(Video).filter(Video.id == download.video_id).first()
                    if video and video.status == VideoStatus.DOWNLOADING:
                        video.status = VideoStatus.WANTED
                        print(f"  - Reset video {video.id} status to WANTED")
                
                cleared_count += 1
            
            session.commit()
            print(f"✅ Cleared {cleared_count} stuck downloads")
            return {"success": True, "cleared_count": cleared_count}
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error clearing stuck downloads: {e}")
        print(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}


def force_clear_all():
    """Force clear ALL queued/downloading downloads"""
    try:
        # Initialize database
        if not initialize_database():
            raise Exception("Failed to initialize database")
        
        session_gen = get_db_session()
        session = next(session_gen)
        
        try:
            # Find ALL queued/downloading downloads
            all_downloads = (
                session.query(Download)
                .filter(Download.status.in_(["queued", "downloading"]))
                .all()
            )
            
            print(f"Found {len(all_downloads)} downloads to clear")
            
            cleared_count = 0
            for download in all_downloads:
                print(f"Force clearing download {download.id}: {download.title}")
                
                # Update download status to failed
                download.status = "cancelled"
                download.error_message = "Force cleared by user"
                download.completed_at = datetime.utcnow()
                
                # Reset associated video status back to WANTED
                if download.video_id:
                    video = session.query(Video).filter(Video.id == download.video_id).first()
                    if video and video.status == VideoStatus.DOWNLOADING:
                        video.status = VideoStatus.WANTED
                        print(f"  - Reset video {video.id} status to WANTED")
                
                cleared_count += 1
            
            session.commit()
            print(f"✅ Force cleared {cleared_count} downloads")
            return {"success": True, "cleared_count": cleared_count}
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error force clearing downloads: {e}")
        print(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "force":
        print("🧹 Force clearing ALL downloads...")
        result = force_clear_all()
    else:
        minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 10
        print(f"🧹 Clearing stuck downloads older than {minutes} minutes...")
        result = clear_stuck_downloads(minutes)
    
    print("\nResult:", result)