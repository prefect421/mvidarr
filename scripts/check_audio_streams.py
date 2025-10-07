#!/usr/bin/env python3
"""
Check Audio Streams Script
Identifies videos that are missing audio streams.
"""

import subprocess
import json
import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config.config import Config
from sqlalchemy import create_engine, text

def has_audio_stream(file_path):
    """Check if video file has audio streams"""
    if not os.path.exists(file_path):
        return None, 'File not found'
    
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', file_path
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            return None, f'FFprobe failed: {result.stderr}'
            
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
        return None, str(e)

def main():
    config = Config()
    db_url = f'mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}'
    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Check recent videos that might have audio issues
        result = conn.execute(text('''
            SELECT v.id, v.title, v.local_path, a.name as artist_name
            FROM videos v
            JOIN artists a ON v.artist_id = a.id
            WHERE v.status = 'DOWNLOADED' 
            AND v.local_path IS NOT NULL
            AND v.id >= 320
            ORDER BY v.id
            LIMIT 20
        '''))
        videos = result.fetchall()
        
        print('🔍 Audio Stream Analysis:')
        videos_without_audio = []
        
        for video in videos:
            video_id, title, local_path, artist_name = video
            has_audio, info = has_audio_stream(local_path)
            
            status_icon = '🔊' if has_audio else '🔇' if has_audio == False else '❓'
            print(f'{status_icon} Video {video_id}: {artist_name} - {title[:50]}')
            
            if has_audio == False:
                videos_without_audio.append(video_id)
                print(f'   📁 {local_path}')
                print(f'   📊 {info}')
            elif has_audio is None:
                print(f'   ❌ {info}')
            
            print()
        
        if videos_without_audio:
            print(f'📝 Videos without audio: {videos_without_audio}')
        else:
            print('✅ All videos have audio streams!')

if __name__ == "__main__":
    main()