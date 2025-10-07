#!/usr/bin/env python3
"""
Fix Missing Video Metadata Script
Identifies and fixes videos marked as DOWNLOADED but missing essential metadata.
"""

import os
import sys
import json
import subprocess
import glob
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config.config import Config
from src.utils.logger import get_logger
from sqlalchemy import create_engine, text

logger = get_logger("mvidarr.scripts.fix_missing_metadata")


def get_video_technical_details(file_path: str) -> Optional[Dict]:
    """Extract technical details from video file using FFprobe"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', 
               '-show_format', '-show_streams', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return None
            
        data = json.loads(result.stdout)
        
        # Extract duration from format
        format_info = data.get('format', {})
        duration = float(format_info.get('duration', 0))
        
        # Extract video stream info
        video_stream = next((s for s in data.get('streams', []) 
                           if s.get('codec_type') == 'video'), None)
        
        if not video_stream:
            return None
            
        width = video_stream.get('width', 0)
        height = video_stream.get('height', 0)
        codec = video_stream.get('codec_name', 'unknown')
        
        # Determine quality based on height
        if height >= 2160:
            quality = "4K"
        elif height >= 1440:
            quality = "1440p"
        elif height >= 1080:
            quality = "1080p"
        elif height >= 720:
            quality = "720p"
        elif height >= 480:
            quality = "480p"
        else:
            quality = "SD"
        
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        
        return {
            'duration': duration,
            'quality': quality,
            'width': width,
            'height': height,
            'codec': codec,
            'file_size': file_size
        }
        
    except Exception as e:
        logger.error(f"Failed to extract metadata from {file_path}: {e}")
        return None


def find_video_file(video_id: int, title: str, artist_name: str, 
                   music_videos_path: str) -> Optional[str]:
    """Find the actual video file for a database record"""
    
    def sanitize_filename(filename):
        import re
        sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
        sanitized = re.sub(r'[^\w\s-]', '', sanitized)
        return sanitized.strip()
    
    clean_title = sanitize_filename(title)
    clean_artist = sanitize_filename(artist_name)
    
    # Search patterns for video files
    search_patterns = [
        # Organized location: data/musicvideos/Artist/Title.ext
        os.path.join(music_videos_path, clean_artist, f"*{clean_title[:20]}*"),
        os.path.join(music_videos_path, clean_artist, f"*{clean_title.split()[0]}*"),
        # YouTube download location: data/musicvideos/YouTube/Date-Title/file
        os.path.join(music_videos_path, "YouTube", f"*{clean_title[:20]}*", "*.mp4"),
        os.path.join(music_videos_path, "YouTube", f"*{clean_title[:20]}*", "*.webm"),
        # Search all subdirectories
        os.path.join(music_videos_path, "*", f"*{clean_title[:20]}*"),
        # Alternative patterns
        os.path.join(music_videos_path, "*", f"*{clean_artist}*{clean_title[:15]}*"),
    ]
    
    video_exts = ['.mp4', '.webm', '.mkv', '.avi', '.mov']
    
    for pattern in search_patterns:
        try:
            potential_files = glob.glob(pattern, recursive=True)
            for file_path in potential_files:
                if any(file_path.endswith(ext) for ext in video_exts):
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:  # > 1KB
                        return file_path
        except Exception as e:
            logger.debug(f"Search pattern failed {pattern}: {e}")
    
    return None


def fix_missing_metadata():
    """Main function to fix videos with missing metadata"""
    config = Config()
    db_url = f'mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}'
    engine = create_engine(db_url)
    
    music_videos_path = "data/musicvideos"  # Default path
    
    logger.info("🔍 Starting missing video metadata repair...")
    
    with engine.connect() as conn:
        # Find videos with missing metadata
        result = conn.execute(text('''
            SELECT v.id, v.title, v.local_path, v.duration, v.quality, v.artist_id, a.name as artist_name
            FROM videos v
            JOIN artists a ON v.artist_id = a.id
            WHERE v.status = 'DOWNLOADED' 
            AND (v.local_path IS NULL OR v.duration IS NULL OR v.quality IS NULL)
            ORDER BY v.artist_id, v.id
            LIMIT 50
        '''))
        videos = result.fetchall()
        
        if not videos:
            logger.info("✅ No videos with missing metadata found!")
            return
        
        logger.info(f"📋 Found {len(videos)} videos with missing metadata")
        
        fixed_count = 0
        failed_count = 0
        
        for video in videos:
            video_id, title, local_path, duration, quality, artist_id, artist_name = video
            
            logger.info(f"\n🎬 Processing Video {video_id}: {title}")
            logger.info(f"   Artist: {artist_name}")
            
            missing_items = []
            if not local_path:
                missing_items.append("file_path")
            if not duration:
                missing_items.append("duration")
            if not quality:
                missing_items.append("quality")
            
            logger.info(f"   Missing: {missing_items}")
            
            # Find the video file if path is missing
            file_path = local_path
            if not file_path:
                logger.info(f"   🔍 Searching for video file...")
                file_path = find_video_file(video_id, title, artist_name, music_videos_path)
                
                if not file_path:
                    logger.warning(f"   ❌ Could not find video file for {video_id}")
                    failed_count += 1
                    continue
                else:
                    logger.info(f"   ✅ Found file: {os.path.basename(file_path)}")
            
            # Extract technical details
            logger.info(f"   📊 Extracting technical metadata...")
            tech_details = get_video_technical_details(file_path)
            
            if not tech_details:
                logger.warning(f"   ❌ Could not extract metadata from {file_path}")
                failed_count += 1
                continue
            
            # Update database
            logger.info(f"   💾 Updating database...")
            update_data = {
                'video_id': video_id,
                'local_path': file_path,
                'duration': tech_details['duration'],
                'quality': tech_details['quality']
            }
            
            # Create video_metadata JSON
            video_metadata = {
                'width': tech_details['width'],
                'height': tech_details['height'],
                'video_codec': tech_details['codec'],
                'file_size': tech_details['file_size'],
                'repair_date': datetime.utcnow().isoformat(),
                'repair_source': 'missing_metadata_fix_script'
            }
            
            query = '''
                UPDATE videos 
                SET local_path = :local_path,
                    duration = :duration,
                    quality = :quality,
                    video_metadata = :video_metadata,
                    updated_at = NOW()
                WHERE id = :video_id
            '''
            
            conn.execute(text(query), {
                **update_data,
                'video_metadata': json.dumps(video_metadata)
            })
            conn.commit()
            
            logger.info(f"   ✅ Fixed Video {video_id}:")
            logger.info(f"      Duration: {tech_details['duration']:.1f}s")
            logger.info(f"      Quality: {tech_details['quality']} ({tech_details['width']}x{tech_details['height']})")
            logger.info(f"      File: {os.path.basename(file_path)}")
            
            fixed_count += 1
        
        logger.info(f"\n📈 Repair Summary:")
        logger.info(f"   ✅ Fixed: {fixed_count} videos")
        logger.info(f"   ❌ Failed: {failed_count} videos")
        logger.info(f"   📊 Success Rate: {fixed_count/(fixed_count+failed_count)*100:.1f}%")


if __name__ == "__main__":
    fix_missing_metadata()