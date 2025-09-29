#!/usr/bin/env python3
"""
Fix Unlinked Videos Utility
Identifies and fixes videos that were downloaded but not properly linked to local files.
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.insert(0, '/home/mike/mvidarr')

from src.database.connection import get_db
from src.database.models import Video, VideoStatus, Artist, Download
# Note: _update_video_after_download was removed during Celery consolidation
# This script may need updating to work with the new ytdlp_service system
def logger_info(msg):
    print(f"[INFO] {msg}")

def logger_warning(msg):
    print(f"[WARNING] {msg}")
    
def logger_error(msg):
    print(f"[ERROR] {msg}")

class logger:
    @staticmethod
    def info(msg):
        logger_info(msg)
    
    @staticmethod
    def warning(msg):
        logger_warning(msg)
    
    @staticmethod
    def error(msg):
        logger_error(msg)

def find_unlinked_videos(session, video_ids=None, hours_back=24):
    """Find videos that are marked as downloaded but have no local_path"""
    query = session.query(Video).filter(
        Video.status == VideoStatus.DOWNLOADED,
        Video.local_path.is_(None)
    )
    
    if video_ids:
        query = query.filter(Video.id.in_(video_ids))
    
    if hours_back:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        query = query.filter(Video.created_at >= cutoff_time)
    
    return query.all()

def fix_video_linking(video, session, dry_run=False):
    """Fix a single video's file linking"""
    logger.info(f"Attempting to fix video {video.id}: {video.title}")
    
    # Find the corresponding download record
    download = session.query(Download).filter(
        Download.video_id == video.id,
        Download.status == 'completed'
    ).order_by(Download.download_date.desc()).first()
    
    if not download:
        logger.warning(f"No completed download record found for video {video.id}")
        return False
    
    if dry_run:
        logger.info(f"[DRY RUN] Would attempt to link video {video.id} using download {download.id}")
        return True
    
    try:
        # Use the existing function to update the video
        _update_video_after_download(video, download, session)
        session.commit()
        
        # Refresh and check if it worked
        session.refresh(video)
        if video.local_path:
            logger.info(f"✅ Successfully linked video {video.id} to {video.local_path}")
            return True
        else:
            logger.warning(f"❌ Failed to link video {video.id} - no local_path set")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error fixing video {video.id}: {e}")
        session.rollback()
        return False

def main():
    parser = argparse.ArgumentParser(description='Fix videos that were downloaded but not linked to local files')
    parser.add_argument('--video-ids', type=str, help='Comma-separated list of video IDs to fix (e.g., 331,332,333)')
    parser.add_argument('--hours-back', type=int, default=24, help='Only fix videos created in the last N hours (default: 24)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    parser.add_argument('--all', action='store_true', help='Fix all unlinked videos regardless of age')
    
    args = parser.parse_args()
    
    if args.all:
        args.hours_back = None
    
    video_ids = None
    if args.video_ids:
        try:
            video_ids = [int(x.strip()) for x in args.video_ids.split(',')]
            logger.info(f"Targeting specific video IDs: {video_ids}")
        except ValueError:
            logger.error("Invalid video IDs format. Use comma-separated integers like: 331,332,333")
            return 1
    
    with get_db() as session:
        # Find unlinked videos
        unlinked_videos = find_unlinked_videos(session, video_ids, args.hours_back)
        
        if not unlinked_videos:
            logger.info("No unlinked videos found")
            return 0
        
        logger.info(f"Found {len(unlinked_videos)} unlinked videos:")
        for video in unlinked_videos:
            artist_name = "Unknown Artist"
            if video.artist_id:
                artist = session.query(Artist).filter(Artist.id == video.artist_id).first()
                if artist:
                    artist_name = artist.name
            logger.info(f"  Video {video.id}: {video.title} by {artist_name}")
        
        if args.dry_run:
            logger.info("\n[DRY RUN MODE] - No changes will be made")
        
        # Fix each video
        fixed_count = 0
        failed_count = 0
        
        for video in unlinked_videos:
            success = fix_video_linking(video, session, args.dry_run)
            if success:
                fixed_count += 1
            else:
                failed_count += 1
        
        if not args.dry_run:
            logger.info(f"\n✅ Fixed {fixed_count} videos")
            if failed_count > 0:
                logger.warning(f"❌ Failed to fix {failed_count} videos")
        else:
            logger.info(f"\n[DRY RUN] Would attempt to fix {len(unlinked_videos)} videos")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())