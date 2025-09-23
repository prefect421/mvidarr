#!/usr/bin/env python3
"""
Fix Unlinked Videos Utility

This script identifies and fixes videos that were downloaded successfully but not
properly linked to their local files. This addresses the race condition issue
where download metadata wasn't available when _update_video_after_download was called.

Usage: python3 fix_unlinked_videos.py [--dry-run] [--video-id ID]
"""

import sys
import os
import argparse
from pathlib import Path

# Add the project root to sys.path so we can import modules
sys.path.insert(0, str(Path(__file__).parent))

from src.database.connection import get_db
from src.database.models import Video, Download, VideoStatus
from src.jobs.simple_download_task import _update_video_after_download
from src.utils.logger import get_logger

logger = get_logger("fix_unlinked_videos")


def find_unlinked_videos():
    """Find videos that are marked as DOWNLOADED but have no local_path"""
    with get_db() as session:
        unlinked_videos = session.query(Video).filter(
            Video.status == VideoStatus.DOWNLOADED,
            Video.local_path.is_(None)
        ).all()
        
        logger.info(f"Found {len(unlinked_videos)} unlinked videos")
        return [(video.id, video.title, video.artist.name if video.artist else "Unknown") 
                for video in unlinked_videos]


def fix_video(video_id, dry_run=False):
    """Fix a specific video by running the file linking process"""
    with get_db() as session:
        video = session.query(Video).filter(Video.id == video_id).first()
        if not video:
            logger.error(f"Video {video_id} not found")
            return False
            
        download = session.query(Download).filter(Download.video_id == video_id).first()
        if not download:
            logger.error(f"No download record found for video {video_id}")
            return False
            
        if video.local_path:
            logger.info(f"Video {video_id} already has local_path: {video.local_path}")
            return True
            
        logger.info(f"Fixing video {video_id}: {video.title}")
        
        if dry_run:
            logger.info(f"DRY RUN: Would fix video {video_id}")
            
            # Check if we have the necessary data
            if download.download_metadata:
                task_result = download.download_metadata.get('task_result', {})
                output_files = task_result.get('output_files', [])
                if output_files:
                    expected_file = output_files[0]
                    logger.info(f"DRY RUN: Expected file: {expected_file}")
                    logger.info(f"DRY RUN: File exists: {os.path.exists(expected_file)}")
                else:
                    logger.warning(f"DRY RUN: No output files in metadata")
            else:
                logger.warning(f"DRY RUN: No download metadata")
            return True
        
        try:
            _update_video_after_download(video, download, session)
            session.refresh(video)
            
            if video.local_path:
                logger.info(f"✅ Successfully fixed video {video_id}")
                logger.info(f"   Local path: {video.local_path}")
                logger.info(f"   Quality: {video.quality}")
                logger.info(f"   Duration: {video.duration}s")
                return True
            else:
                logger.warning(f"❌ Failed to fix video {video_id} - no local_path set")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error fixing video {video_id}: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Fix unlinked downloaded videos")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be fixed without making changes")
    parser.add_argument("--video-id", type=int, 
                       help="Fix specific video ID")
    
    args = parser.parse_args()
    
    if args.video_id:
        # Fix specific video
        logger.info(f"Fixing specific video ID: {args.video_id}")
        success = fix_video(args.video_id, args.dry_run)
        sys.exit(0 if success else 1)
    
    # Find and fix all unlinked videos
    unlinked_videos = find_unlinked_videos()
    
    if not unlinked_videos:
        logger.info("✅ No unlinked videos found. All downloaded videos are properly linked!")
        return
    
    logger.info(f"Found {len(unlinked_videos)} unlinked videos:")
    for video_id, title, artist in unlinked_videos:
        logger.info(f"  {video_id}: {artist} - {title}")
    
    if args.dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")
    
    fixed_count = 0
    failed_count = 0
    
    for video_id, title, artist in unlinked_videos:
        logger.info(f"\nProcessing video {video_id}: {artist} - {title}")
        
        if fix_video(video_id, args.dry_run):
            fixed_count += 1
        else:
            failed_count += 1
    
    logger.info(f"\nSummary:")
    logger.info(f"  Total unlinked videos: {len(unlinked_videos)}")
    logger.info(f"  Successfully fixed: {fixed_count}")
    logger.info(f"  Failed to fix: {failed_count}")
    
    if not args.dry_run and fixed_count > 0:
        logger.info(f"✅ Fixed {fixed_count} unlinked videos!")
    
    if failed_count > 0:
        logger.warning(f"⚠️  {failed_count} videos could not be fixed. Check logs for details.")


if __name__ == "__main__":
    main()