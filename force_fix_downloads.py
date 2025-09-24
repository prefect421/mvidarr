#!/usr/bin/env python3
"""
Force Fix Downloads - Aggressive repair for download linking issues
This script forces all downloads to be properly linked, regardless of current status
"""

import os
import sys
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.insert(0, '/home/mike/mvidarr')

from src.database.connection import get_db
from src.database.models import Video, VideoStatus, Artist, Download
from src.jobs.simple_download_task import _update_video_after_download

def force_fix_all_downloads():
    """Aggressively fix ALL videos that have completed downloads but issues with linking"""
    
    print(f"🔧 Starting aggressive download repair at {datetime.now()}")
    
    fixed_count = 0
    failed_count = 0
    
    with get_db() as session:
        # Get ALL videos that have completed downloads but potential linking issues
        problem_videos = session.query(Video)\
            .join(Download, Video.id == Download.video_id)\
            .filter(Video.status == VideoStatus.DOWNLOADED)\
            .filter(Download.status == 'completed')\
            .all()
        
        print(f"📊 Found {len(problem_videos)} videos with completed downloads")
        
        for video in problem_videos:
            try:
                print(f"\n🔍 Checking video {video.id}: {video.title}")
                
                # Get the most recent completed download
                download = session.query(Download)\
                    .filter(Download.video_id == video.id)\
                    .filter(Download.status == 'completed')\
                    .order_by(Download.download_date.desc())\
                    .first()
                
                if not download:
                    print(f"  ❌ No completed download found")
                    continue
                
                # Check if video has proper local_path
                needs_fix = False
                
                if not video.local_path:
                    print(f"  🚨 Video has no local_path - needs fixing")
                    needs_fix = True
                elif not os.path.exists(video.local_path):
                    print(f"  🚨 Video local_path points to missing file: {video.local_path}")
                    needs_fix = True
                else:
                    print(f"  ✅ Video properly linked to: {video.local_path}")
                
                # Force fix if needed
                if needs_fix:
                    print(f"  🔧 Force-fixing video {video.id}")
                    
                    # Clear the current local_path to force re-linking
                    original_path = video.local_path
                    video.local_path = None
                    session.commit()
                    
                    # Call the linking function
                    _update_video_after_download(video, download, session)
                    session.commit()
                    
                    # Check if it worked
                    session.refresh(video)
                    if video.local_path and os.path.exists(video.local_path):
                        print(f"  ✅ FIXED: {video.local_path}")
                        fixed_count += 1
                    else:
                        print(f"  ❌ FAILED to fix video {video.id}")
                        # Restore original path if available
                        if original_path and os.path.exists(original_path):
                            video.local_path = original_path
                            session.commit()
                            print(f"  🔄 Restored original path: {original_path}")
                        failed_count += 1
                
            except Exception as e:
                print(f"  ❌ Error processing video {video.id}: {e}")
                failed_count += 1
                session.rollback()
    
    print(f"\n📈 Repair Summary:")
    print(f"  ✅ Fixed: {fixed_count}")
    print(f"  ❌ Failed: {failed_count}")
    print(f"  🕐 Completed at: {datetime.now()}")

if __name__ == '__main__':
    force_fix_all_downloads()