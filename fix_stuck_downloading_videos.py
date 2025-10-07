#!/usr/bin/env python3
"""
Fix videos stuck in DOWNLOADING status by checking for local files and updating to DOWNLOADED
"""

import os
import sys
from pathlib import Path

# Add the project directory to the Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from src.database.connection import get_db
from src.database.models import Video, VideoStatus
from src.services.settings_service import SettingsService

def find_video_file(artist_name: str, video_title: str, music_videos_path: str) -> str:
    """
    Find video file for given artist and title
    
    Args:
        artist_name: Artist name 
        video_title: Video title
        music_videos_path: Base path for music videos
        
    Returns:
        Path to video file if found, None otherwise
    """
    # Common video extensions
    video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv']
    
    # Sanitize names for filesystem
    def sanitize_name(name):
        import re
        sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
        sanitized = re.sub(r'[^\w\s-]', '', sanitized).strip()
        return sanitized[:100] if sanitized else "Unknown"
    
    artist_dir = os.path.join(music_videos_path, sanitize_name(artist_name))
    
    if not os.path.exists(artist_dir):
        return None
    
    # Look for video files with the title
    base_title = sanitize_name(video_title)
    
    for ext in video_extensions:
        # Try exact match first
        exact_file = os.path.join(artist_dir, f"{base_title}{ext}")
        if os.path.exists(exact_file):
            return exact_file
        
        # Try with various prefixes that might have been added
        possible_files = [
            f"{sanitize_name(artist_name)} - {base_title}{ext}",
            f"{base_title} - {sanitize_name(artist_name)}{ext}",
            f"{sanitize_name(artist_name)} - quot{base_title}quot{ext}",  # yt-dlp sometimes adds quotes
        ]
        
        for possible_file in possible_files:
            full_path = os.path.join(artist_dir, possible_file)
            if os.path.exists(full_path):
                return full_path
    
    # Last resort: look for any video file in the artist directory that might match
    try:
        for file in os.listdir(artist_dir):
            if any(file.lower().endswith(ext) for ext in video_extensions):
                # Simple title matching (contains most of the title words)
                title_words = base_title.lower().split()
                file_lower = file.lower()
                
                if len(title_words) > 0:
                    # If at least 70% of title words are in filename, consider it a match
                    matching_words = sum(1 for word in title_words if word in file_lower)
                    if matching_words >= len(title_words) * 0.7:
                        return os.path.join(artist_dir, file)
    except OSError:
        pass
    
    return None

def fix_stuck_downloading_videos():
    """
    Find videos stuck in DOWNLOADING status and update to DOWNLOADED if local file exists
    """
    print("🔧 Fixing videos stuck in DOWNLOADING status...")
    
    try:
        # Get settings
        settings = SettingsService()
        music_videos_path = settings.get("music_videos_path", "data/musicvideos")
        
        print(f"📁 Music videos path: {music_videos_path}")
        
        if not os.path.exists(music_videos_path):
            print(f"❌ Music videos directory does not exist: {music_videos_path}")
            return False
        
        # Find videos stuck in DOWNLOADING status
        with get_db() as session:
            downloading_videos = session.query(Video).filter(
                Video.status == VideoStatus.DOWNLOADING
            ).all()
            
            print(f"🔍 Found {len(downloading_videos)} videos stuck in DOWNLOADING status")
            
            if not downloading_videos:
                print("✅ No videos stuck in DOWNLOADING status!")
                return True
            
            fixed_count = 0
            not_found_count = 0
            
            for video in downloading_videos:
                artist_name = video.artist.name if video.artist else "Unknown Artist"
                video_title = video.title
                
                print(f"\n📹 Checking: {artist_name} - {video_title}")
                print(f"   🆔 Video ID: {video.id}")
                
                # Check if video has local_path set
                if video.local_path and os.path.exists(video.local_path):
                    print(f"   ✅ Local file found at: {video.local_path}")
                    video.status = VideoStatus.DOWNLOADED
                    fixed_count += 1
                    print(f"   🔄 Updated status to DOWNLOADED")
                    continue
                
                # Look for video file in expected location
                video_file_path = find_video_file(artist_name, video_title, music_videos_path)
                
                if video_file_path:
                    print(f"   ✅ Video file found: {video_file_path}")
                    
                    # Update status and local_path
                    video.status = VideoStatus.DOWNLOADED
                    video.local_path = video_file_path
                    fixed_count += 1
                    
                    print(f"   🔄 Updated status to DOWNLOADED")
                    print(f"   📂 Set local_path: {video_file_path}")
                else:
                    print(f"   ❌ No video file found for this video")
                    not_found_count += 1
            
            # Commit all changes
            session.commit()
            
            print(f"\n📊 Summary:")
            print(f"   ✅ Fixed videos: {fixed_count}")
            print(f"   ❌ Videos without files: {not_found_count}")
            print(f"   📈 Total processed: {len(downloading_videos)}")
            
            if fixed_count > 0:
                print(f"\n🎉 Successfully fixed {fixed_count} videos stuck in DOWNLOADING status!")
            
            return True
            
    except Exception as e:
        print(f"❌ Error fixing stuck downloading videos: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    print("🚀 Starting stuck DOWNLOADING videos fix...")
    
    success = fix_stuck_downloading_videos()
    
    if success:
        print("\n✅ Fix completed successfully!")
    else:
        print("\n❌ Fix failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()