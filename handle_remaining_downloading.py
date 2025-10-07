#!/usr/bin/env python3
"""
Handle the remaining video in DOWNLOADING status that has no local file
"""

import sys
from pathlib import Path

# Add the project directory to the Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from src.database.connection import get_db
from src.database.models import Video, VideoStatus

def handle_remaining_downloading():
    """Handle remaining videos in DOWNLOADING status without local files"""
    
    print("🔧 Handling remaining videos in DOWNLOADING status...")
    
    try:
        with get_db() as session:
            downloading_videos = session.query(Video).filter(
                Video.status == VideoStatus.DOWNLOADING
            ).all()
            
            print(f"🔍 Found {len(downloading_videos)} videos in DOWNLOADING status")
            
            if not downloading_videos:
                print("✅ No videos in DOWNLOADING status!")
                return True
            
            for video in downloading_videos:
                artist_name = video.artist.name if video.artist else "Unknown Artist"
                print(f"\n📹 Video: {artist_name} - {video.title}")
                print(f"   🆔 ID: {video.id}")
                print(f"   📂 Local path: {video.local_path}")
                
                # Since this video has been stuck and no file exists, mark as WANTED 
                # so it can be downloaded again properly
                video.status = VideoStatus.WANTED
                video.local_path = None  # Clear any invalid path
                
                print(f"   🔄 Updated status to WANTED for re-download")
            
            session.commit()
            
            print(f"\n✅ Successfully updated {len(downloading_videos)} videos to WANTED status")
            return True
            
    except Exception as e:
        print(f"❌ Error handling remaining videos: {e}")
        return False

if __name__ == "__main__":
    success = handle_remaining_downloading()
    if success:
        print("\n🎉 All DOWNLOADING videos have been handled!")
    else:
        print("\n❌ Failed to handle remaining videos")