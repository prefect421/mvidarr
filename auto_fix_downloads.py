#!/usr/bin/env python3
"""
Auto-Fix Downloads Service
Real-time monitoring and fixing of download linking issues
Can run as a daemon to automatically fix problems as they occur
"""

import os
import sys
import time
import signal
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.insert(0, '/home/mike/mvidarr')

from src.database.connection import get_db
from src.database.models import Video, VideoStatus, Artist, Download
from src.jobs.simple_download_task import _update_video_after_download

class DownloadAutoFixer:
    def __init__(self, check_interval=30):
        self.check_interval = check_interval  # seconds
        self.running = False
        self.last_check_time = datetime.utcnow()
        
    def start(self):
        """Start the auto-fix service"""
        self.running = True
        print(f"🚀 Download Auto-Fixer started at {datetime.now()}")
        print(f"📊 Checking every {self.check_interval} seconds for unlinked downloads")
        
        try:
            while self.running:
                self.check_and_fix()
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            print(f"\n🛑 Stopping Download Auto-Fixer...")
        finally:
            self.running = False
    
    def stop(self):
        """Stop the auto-fix service"""
        self.running = False
    
    def check_and_fix(self):
        """Check for recent unlinked downloads and fix them"""
        current_time = datetime.utcnow()
        
        # Look for downloads completed since last check
        with get_db() as session:
            recent_downloads = session.query(Download)\
                .filter(Download.status == 'completed')\
                .filter(Download.download_date >= self.last_check_time)\
                .all()
            
            problems_found = 0
            problems_fixed = 0
            
            for download in recent_downloads:
                if download.video_id:
                    video = session.query(Video).filter(Video.id == download.video_id).first()
                    
                    if video and video.status == VideoStatus.DOWNLOADED and not video.local_path:
                        problems_found += 1
                        print(f"🚨 [{datetime.now().strftime('%H:%M:%S')}] UNLINKED: Video {video.id} ({video.title})")
                        
                        try:
                            # Attempt immediate fix
                            _update_video_after_download(video, download, session)
                            session.commit()
                            session.refresh(video)
                            
                            if video.local_path:
                                problems_fixed += 1
                                print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] AUTO-FIXED: Video {video.id} -> {video.local_path}")
                            else:
                                print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] FAILED TO FIX: Video {video.id}")
                                
                        except Exception as e:
                            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] ERROR fixing video {video.id}: {e}")
                            session.rollback()
            
            # Only print summary if there was activity
            if problems_found > 0:
                print(f"📊 [{datetime.now().strftime('%H:%M:%S')}] Check complete: {problems_found} issues found, {problems_fixed} fixed")
            elif recent_downloads:
                print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] {len(recent_downloads)} recent downloads all properly linked")
        
        self.last_check_time = current_time

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\n🛑 Received signal {signum}, shutting down...")
    sys.exit(0)

def main():
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description='Auto-fix download linking issues in real-time')
    parser.add_argument('--interval', type=int, default=30, help='Check interval in seconds (default: 30)')
    parser.add_argument('--daemon', action='store_true', help='Run as background daemon')
    
    args = parser.parse_args()
    
    if args.daemon:
        print("🔧 Starting as background daemon...")
        # In a real implementation, you'd use proper daemon libs here
        # For now, just run normally
    
    fixer = DownloadAutoFixer(check_interval=args.interval)
    fixer.start()

if __name__ == '__main__':
    main()