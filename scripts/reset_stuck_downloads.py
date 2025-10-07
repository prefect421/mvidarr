#!/usr/bin/env python3
"""
Reset Stuck Downloads Script
Runs at system startup to clean up any downloads stuck in 'pending', 'queued', or 'downloading' status
and moves them back to 'wanted' so they can be properly re-queued.
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def reset_stuck_downloads():
    """Reset stuck downloads to wanted status"""
    try:
        from src.database.connection import get_db
        from src.database.models import Download
        from sqlalchemy import func
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting download cleanup...")
        
        with get_db() as session:
            # Find downloads stuck in intermediate states
            stuck_statuses = ['pending', 'queued', 'downloading']
            stuck_downloads = session.query(Download).filter(
                Download.status.in_(stuck_statuses)
            ).all()
            
            if not stuck_downloads:
                print("✅ No stuck downloads found. All downloads are in clean state.")
                return True
                
            print(f"📊 Found {len(stuck_downloads)} stuck downloads:")
            
            # Group by status for reporting
            status_counts = session.query(
                Download.status, 
                func.count(Download.id)
            ).filter(
                Download.status.in_(stuck_statuses)
            ).group_by(Download.status).all()
            
            for status, count in status_counts:
                print(f"   - {status}: {count} downloads")
            
            # Reset all stuck downloads to 'wanted'
            reset_count = 0
            for download in stuck_downloads:
                try:
                    old_status = download.status
                    download.status = 'wanted'
                    download.progress = 0
                    download.error_message = f"Reset from '{old_status}' at startup on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    download.updated_at = datetime.now()
                    reset_count += 1
                    
                    print(f"🔄 Reset download {download.id}: '{download.title[:50]}...' ({old_status} → wanted)")
                    
                except Exception as e:
                    print(f"❌ Failed to reset download {download.id}: {e}")
            
            # Commit all changes
            session.commit()
            
            print(f"✅ Successfully reset {reset_count}/{len(stuck_downloads)} downloads to 'wanted' status")
            print("🎯 Downloads can now be properly re-queued through the web interface")
            
            return True
            
    except Exception as e:
        print(f"❌ Error during download cleanup: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main entry point"""
    print("=" * 60)
    print("MVidarr Download Cleanup - System Startup")
    print("=" * 60)
    
    success = reset_stuck_downloads()
    
    if success:
        print("=" * 60)
        print("✅ Download cleanup completed successfully")
        exit(0)
    else:
        print("=" * 60)
        print("❌ Download cleanup failed")
        exit(1)

if __name__ == "__main__":
    main()