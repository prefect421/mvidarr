#!/usr/bin/env python3
"""
Verify that the stuck DOWNLOADING videos were properly fixed
"""

import sys
from pathlib import Path

# Add the project directory to the Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from src.database.connection import get_db
from src.database.models import Video, VideoStatus

def verify_fix():
    """Verify that videos are no longer stuck in DOWNLOADING status"""
    
    print("🔍 Verifying video status fix...")
    
    try:
        with get_db() as session:
            # Check for remaining DOWNLOADING videos
            downloading_videos = session.query(Video).filter(
                Video.status == VideoStatus.DOWNLOADING
            ).all()
            
            print(f"📊 Videos still in DOWNLOADING status: {len(downloading_videos)}")
            
            if downloading_videos:
                print("\n⚠️ Remaining DOWNLOADING videos:")
                for video in downloading_videos:
                    artist_name = video.artist.name if video.artist else "Unknown Artist"
                    print(f"   📹 {video.id}: {artist_name} - {video.title}")
            
            # Check recently fixed videos (should now be DOWNLOADED)
            downloaded_videos = session.query(Video).filter(
                Video.status == VideoStatus.DOWNLOADED
            ).count()
            
            wanted_videos = session.query(Video).filter(
                Video.status == VideoStatus.WANTED  
            ).count()
            
            failed_videos = session.query(Video).filter(
                Video.status == VideoStatus.FAILED
            ).count()
            
            print(f"\n📈 Video status summary:")
            print(f"   ✅ DOWNLOADED: {downloaded_videos}")
            print(f"   🎯 WANTED: {wanted_videos}")
            print(f"   🔄 DOWNLOADING: {len(downloading_videos)}")
            print(f"   ❌ FAILED: {failed_videos}")
            
            return len(downloading_videos) < 5  # Success if very few remain stuck
            
    except Exception as e:
        print(f"❌ Error verifying fix: {e}")
        return False

if __name__ == "__main__":
    success = verify_fix()
    if success:
        print("\n✅ Video status fix verification successful!")
    else:
        print("\n⚠️ Some videos may still need attention")