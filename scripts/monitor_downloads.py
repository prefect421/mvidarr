#!/usr/bin/env python3
"""
Download Monitor - Automated monitoring and fixing of download issues
Can be run as a cron job to automatically detect and fix unlinked videos
"""

import os
import sys
import time
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.insert(0, '/home/mike/mvidarr')

from src.database.connection import get_db
from src.database.models import Video, VideoStatus, Artist, Download
from src.jobs.simple_download_task import _update_video_after_download

def check_and_fix_unlinked_videos(hours_back=2):
    """Check for and fix videos that were downloaded but not linked in the last N hours"""
    
    results = {
        'checked': 0,
        'unlinked_found': 0,
        'fixed': 0,
        'failed': 0,
        'details': []
    }
    
    # Look for videos downloaded in the last few hours that aren't linked
    cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
    
    with get_db() as session:
        # Find recent downloads that completed successfully but video has no local_path
        unlinked_videos = session.query(Video.id, Video.title, Video.artist_id, Download.id, Download.download_date)\
            .join(Download, Video.id == Download.video_id)\
            .filter(Video.status == VideoStatus.DOWNLOADED)\
            .filter(Video.local_path.is_(None))\
            .filter(Download.status == 'completed')\
            .filter(Download.download_date >= cutoff_time)\
            .order_by(Download.download_date.desc())\
            .all()
        
        results['checked'] = len(unlinked_videos)
        results['unlinked_found'] = len(unlinked_videos)
        
        for row in unlinked_videos:
            video_id, title, artist_id, download_id, download_date = row
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Found unlinked video {video_id}: {title}")
            
            try:
                # Get the full video and download objects
                video = session.query(Video).filter(Video.id == video_id).first()
                download = session.query(Download).filter(Download.id == download_id).first()
                
                if video and download:
                    # Try to fix the linking
                    _update_video_after_download(video, download, session)
                    session.commit()
                    
                    # Check if it worked
                    session.refresh(video)
                    if video.local_path:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Fixed video {video_id}: {video.local_path}")
                        results['fixed'] += 1
                        results['details'].append({
                            'video_id': video_id,
                            'title': title,
                            'status': 'fixed',
                            'local_path': video.local_path
                        })
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Failed to fix video {video_id}")
                        results['failed'] += 1
                        results['details'].append({
                            'video_id': video_id,
                            'title': title,
                            'status': 'failed',
                            'reason': 'linking_failed'
                        })
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Could not find video or download record for {video_id}")
                    results['failed'] += 1
                    results['details'].append({
                        'video_id': video_id,
                        'title': title,
                        'status': 'failed',
                        'reason': 'record_not_found'
                    })
                    
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error fixing video {video_id}: {e}")
                results['failed'] += 1
                results['details'].append({
                    'video_id': video_id,
                    'title': title,
                    'status': 'failed',
                    'reason': str(e)
                })
    
    return results

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting download monitor check...")
    
    # Check for unlinked videos from the last 6 hours
    results = check_and_fix_unlinked_videos(hours_back=6)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitor check complete:")
    print(f"  - Videos checked: {results['checked']}")
    print(f"  - Unlinked found: {results['unlinked_found']}")
    print(f"  - Successfully fixed: {results['fixed']}")
    print(f"  - Failed to fix: {results['failed']}")
    
    if results['unlinked_found'] == 0:
        print(f"  ✅ All recent downloads are properly linked")
    elif results['fixed'] == results['unlinked_found']:
        print(f"  ✅ All unlinked videos were successfully fixed")
    elif results['failed'] > 0:
        print(f"  ⚠️  {results['failed']} videos could not be automatically fixed")
        print(f"      Manual intervention may be required")
        
        # Show details for failed videos
        for detail in results['details']:
            if detail['status'] == 'failed':
                print(f"      - Video {detail['video_id']}: {detail['title']} ({detail['reason']})")
    
    print()

if __name__ == '__main__':
    main()