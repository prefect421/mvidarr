#!/usr/bin/env python3
"""
Re-download Videos Without Audio Script
Identifies videos missing audio streams and re-downloads them with audio-guaranteed format strings.
"""

import os
import sys
import subprocess
import json
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config.config import Config
from src.utils.logger import get_logger
from sqlalchemy import create_engine, text

logger = get_logger("mvidarr.scripts.redownload_without_audio")

def has_audio_stream(file_path: str) -> Tuple[bool, Dict]:
    """Check if video file has audio streams"""
    if not os.path.exists(file_path):
        return False, {'error': 'File not found'}
    
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', file_path
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            return False, {'error': f'FFprobe failed: {result.stderr}'}
            
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        
        video_streams = [s for s in streams if s.get('codec_type') == 'video']
        audio_streams = [s for s in streams if s.get('codec_type') == 'audio']
        
        return len(audio_streams) > 0, {
            'video_streams': len(video_streams),
            'audio_streams': len(audio_streams),
            'video_codec': video_streams[0].get('codec_name') if video_streams else None,
            'audio_codec': audio_streams[0].get('codec_name') if audio_streams else None
        }
    except Exception as e:
        return False, {'error': str(e)}

def download_video_with_audio(video_url: str, output_path: str, title: str) -> Tuple[bool, str]:
    """Download video using audio-guaranteed format string"""
    try:
        # Audio-guaranteed format string (prioritizes combined formats with audio)
        format_string = "best[height<=2160][ext=mp4]/best[height<=2160]/bv[height<=2160]+ba/bestvideo[height<=2160]+bestaudio/best"
        
        # Create temporary download location
        temp_dir = tempfile.mkdtemp()
        temp_output = os.path.join(temp_dir, f"{title}.%(ext)s")
        
        cmd = [
            "yt-dlp",
            "--format", format_string,
            "--output", temp_output,
            "--no-playlist",
            "--write-info-json",
            "--embed-metadata",
            "--ignore-errors",
            video_url
        ]
        
        logger.info(f"Downloading with command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # 30 minutes timeout
        
        if result.returncode == 0:
            # Find the downloaded file
            downloaded_files = []
            for ext in ['.mp4', '.webm', '.mkv', '.avi']:
                potential_file = temp_output.replace('%(ext)s', ext.lstrip('.'))
                if os.path.exists(potential_file):
                    downloaded_files.append(potential_file)
                    break
            
            if downloaded_files:
                temp_file = downloaded_files[0]
                
                # Check if the new file has audio
                has_audio, audio_info = has_audio_stream(temp_file)
                
                if has_audio:
                    # Move the file to the final location
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    
                    # Backup original file if it exists
                    if os.path.exists(output_path):
                        backup_path = f"{output_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        os.rename(output_path, backup_path)
                        logger.info(f"Backed up original file to: {backup_path}")
                    
                    # Move new file to final location
                    import shutil
                    shutil.move(temp_file, output_path)
                    
                    # Clean up temp directory
                    import shutil
                    shutil.rmtree(temp_dir)
                    
                    return True, f"Successfully downloaded with audio: {audio_info}"
                else:
                    # Clean up temp directory
                    import shutil
                    shutil.rmtree(temp_dir)
                    return False, f"Downloaded file still missing audio: {audio_info}"
            else:
                return False, "No output file found after download"
        else:
            return False, f"yt-dlp failed: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "Download timed out after 30 minutes"
    except Exception as e:
        return False, f"Download failed: {str(e)}"

def update_video_metadata(video_id: int, file_path: str):
    """Update video metadata after successful re-download"""
    try:
        config = Config()
        db_url = f'mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}'
        engine = create_engine(db_url)
        
        # Extract technical metadata from the new file
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', file_path
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                probe_data = json.loads(result.stdout)
                
                # Extract duration from format
                format_info = probe_data.get('format', {})
                duration = float(format_info.get('duration', 0))
                
                # Extract video stream info
                video_stream = next((s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video'), None)
                audio_stream = next((s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio'), None)
                
                if video_stream:
                    width = video_stream.get('width', 0)
                    height = video_stream.get('height', 0)
                    video_codec = video_stream.get('codec_name', 'unknown')
                    
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
                    
                    # Create video_metadata JSON
                    video_metadata = {
                        'width': width,
                        'height': height,
                        'video_codec': video_codec,
                        'audio_codec': audio_stream.get('codec_name') if audio_stream else None,
                        'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else None,
                        'redownload_date': datetime.utcnow().isoformat(),
                        'redownload_reason': 'missing_audio_stream_fix',
                        'has_audio': audio_stream is not None
                    }
                    
                    with engine.connect() as conn:
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
                            'video_id': video_id,
                            'local_path': file_path,
                            'duration': duration,
                            'quality': quality,
                            'video_metadata': json.dumps(video_metadata)
                        })
                        conn.commit()
                        
                        logger.info(f"✅ Updated database for video {video_id}:")
                        logger.info(f"   Duration: {duration:.1f}s")
                        logger.info(f"   Quality: {quality} ({width}x{height})")
                        logger.info(f"   Video Codec: {video_codec}")
                        logger.info(f"   Audio Codec: {video_metadata['audio_codec']}")
                        
        except Exception as e:
            logger.error(f"Failed to update metadata for video {video_id}: {e}")
            
    except Exception as e:
        logger.error(f"Failed to update video metadata: {e}")

def main():
    """Main function to re-download videos without audio"""
    config = Config()
    db_url = f'mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}'
    engine = create_engine(db_url)
    
    logger.info("🔍 Starting re-download of videos without audio...")
    
    # First, identify videos without audio
    videos_without_audio = []
    
    with engine.connect() as conn:
        result = conn.execute(text('''
            SELECT v.id, v.title, v.local_path, v.youtube_url, a.name as artist_name
            FROM videos v
            JOIN artists a ON v.artist_id = a.id
            WHERE v.status = 'DOWNLOADED' 
            AND v.local_path IS NOT NULL
            AND v.youtube_url IS NOT NULL
            AND v.id IN (320, 321, 324, 325)
            ORDER BY v.id
        '''))
        videos = result.fetchall()
        
        for video in videos:
            video_id, title, local_path, youtube_url, artist_name = video
            has_audio, info = has_audio_stream(local_path)
            
            if not has_audio:
                videos_without_audio.append({
                    'id': video_id,
                    'title': title,
                    'local_path': local_path,
                    'youtube_url': youtube_url,
                    'artist_name': artist_name
                })
                logger.info(f"🔇 Video {video_id} needs re-download: {artist_name} - {title}")
    
    if not videos_without_audio:
        logger.info("✅ No videos found without audio!")
        return
    
    logger.info(f"📋 Found {len(videos_without_audio)} videos to re-download")
    
    # Re-download each video
    success_count = 0
    failed_count = 0
    
    for video_info in videos_without_audio:
        video_id = video_info['id']
        title = video_info['title']
        local_path = video_info['local_path']
        youtube_url = video_info['youtube_url']
        artist_name = video_info['artist_name']
        
        logger.info(f"\\n🎬 Re-downloading Video {video_id}: {artist_name} - {title}")
        logger.info(f"   URL: {youtube_url}")
        
        # Clean filename for download
        import re
        clean_title = re.sub(r'[<>:"/\\\\|?*]', '', title)
        clean_title = re.sub(r'[^\\w\\s-]', '', clean_title).strip()
        
        success, message = download_video_with_audio(youtube_url, local_path, clean_title)
        
        if success:
            logger.info(f"   ✅ {message}")
            
            # Update database metadata
            update_video_metadata(video_id, local_path)
            
            # Verify audio is present
            has_audio, audio_info = has_audio_stream(local_path)
            if has_audio:
                logger.info(f"   🔊 Verified: Audio stream present ({audio_info['audio_codec']})")
                success_count += 1
            else:
                logger.warning(f"   ⚠️ Warning: Still no audio after re-download")
                failed_count += 1
        else:
            logger.error(f"   ❌ {message}")
            failed_count += 1
    
    logger.info(f"\\n📈 Re-download Summary:")
    logger.info(f"   ✅ Successful: {success_count} videos")
    logger.info(f"   ❌ Failed: {failed_count} videos")
    logger.info(f"   📊 Success Rate: {success_count/(success_count+failed_count)*100:.1f}%")

if __name__ == "__main__":
    main()