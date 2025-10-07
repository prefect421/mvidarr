#!/usr/bin/env python3
"""
Script to clean up videos missing URLs from the database
"""

import sys
from datetime import datetime

from src.database.connection import get_db_session
from src.database.models import Video, Artist
from src.database.init_db import initialize_database
from src.utils.logger import get_logger

logger = get_logger(__name__)


def find_videos_without_urls():
    """Find videos that have no URL information"""
    try:
        # Initialize database
        if not initialize_database():
            raise Exception("Failed to initialize database")
        
        session_gen = get_db_session()
        session = next(session_gen)
        
        try:
            # Find videos with no URL, youtube_url, or youtube_id
            videos_without_urls = (
                session.query(Video, Artist.name)
                .join(Artist, Video.artist_id == Artist.id)
                .filter(
                    (Video.url.is_(None) | (Video.url == "")) &
                    (Video.youtube_url.is_(None) | (Video.youtube_url == "")) &
                    (Video.youtube_id.is_(None) | (Video.youtube_id == ""))
                )
                .all()
            )
            
            print(f"Found {len(videos_without_urls)} videos without any URL information:")
            print("=" * 80)
            
            for video, artist_name in videos_without_urls:
                print(f"ID: {video.id}")
                print(f"Artist: {artist_name}")
                print(f"Title: {video.title}")
                print(f"Status: {video.status}")
                print(f"URL: {video.url}")
                print(f"YouTube URL: {video.youtube_url}")
                print(f"YouTube ID: {video.youtube_id}")
                print(f"Created: {video.created_at}")
                print("-" * 40)
            
            return videos_without_urls
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error finding videos without URLs: {e}")
        print(f"❌ Error: {e}")
        return []


def delete_videos_without_urls(confirm=False):
    """Delete videos that have no URL information"""
    try:
        # Initialize database
        if not initialize_database():
            raise Exception("Failed to initialize database")
        
        session_gen = get_db_session()
        session = next(session_gen)
        
        try:
            # Find videos with no URL, youtube_url, or youtube_id
            videos_to_delete = (
                session.query(Video)
                .filter(
                    (Video.url.is_(None) | (Video.url == "")) &
                    (Video.youtube_url.is_(None) | (Video.youtube_url == "")) &
                    (Video.youtube_id.is_(None) | (Video.youtube_id == ""))
                )
                .all()
            )
            
            if not videos_to_delete:
                print("✅ No videos without URLs found")
                return {"success": True, "deleted_count": 0}
            
            if not confirm:
                print(f"Found {len(videos_to_delete)} videos to delete. Use --confirm to proceed.")
                return {"success": False, "deleted_count": 0, "message": "Confirmation required"}
            
            deleted_count = 0
            for video in videos_to_delete:
                print(f"Deleting video {video.id}: {video.title}")
                session.delete(video)
                deleted_count += 1
            
            session.commit()
            print(f"✅ Deleted {deleted_count} videos without URLs")
            return {"success": True, "deleted_count": deleted_count}
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error deleting videos without URLs: {e}")
        print(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}


def check_imvdb_for_missing_urls():
    """Check IMVDB for videos that have no URL but could be found"""
    try:
        # Initialize database
        if not initialize_database():
            raise Exception("Failed to initialize database")
        
        session_gen = get_db_session()
        session = next(session_gen)
        
        try:
            # Import IMVDB service
            from src.services.imvdb_service import IMVDbService
            imvdb_service = IMVDbService()
            
            # Find videos with no URL information
            videos_without_urls = (
                session.query(Video, Artist.name)
                .join(Artist, Video.artist_id == Artist.id)
                .filter(
                    (Video.url.is_(None) | (Video.url == "")) &
                    (Video.youtube_url.is_(None) | (Video.youtube_url == "")) &
                    (Video.youtube_id.is_(None) | (Video.youtube_id == ""))
                )
                .limit(10)  # Limit to 10 for testing
                .all()
            )
            
            print(f"Checking IMVDB for {len(videos_without_urls)} videos...")
            print("=" * 80)
            
            updated_count = 0
            for video, artist_name in videos_without_urls:
                video_id = video.id
                video_title = video.title
                print(f"Searching IMVDB for: {artist_name} - {video_title}")
                
                try:
                    # Search IMVDB for this video
                    search_results = imvdb_service.search_videos(artist_name, video_title)
                    
                    if search_results and len(search_results) > 0:
                        # Get the first result
                        imvdb_video = search_results[0]
                        
                        # Extract YouTube URL if available
                        youtube_url = None
                        if 'sources' in imvdb_video:
                            for source in imvdb_video['sources']:
                                if source.get('source') == 'youtube' and source.get('source_data'):
                                    youtube_url = source['source_data']
                                    break
                        
                        if youtube_url:
                            print(f"  ✅ Found YouTube URL: {youtube_url}")
                            
                            # Update the video with the found URL using fresh query
                            session_video = session.query(Video).filter(Video.id == video_id).first()
                            if session_video:
                                session_video.youtube_url = youtube_url
                                # Extract YouTube ID from URL
                                if 'watch?v=' in youtube_url:
                                    session_video.youtube_id = youtube_url.split('watch?v=')[1].split('&')[0]
                                elif 'youtu.be/' in youtube_url:
                                    session_video.youtube_id = youtube_url.split('youtu.be/')[1].split('?')[0]
                                
                                updated_count += 1
                        else:
                            print(f"  ❌ Found IMVDB entry but no YouTube URL")
                    else:
                        print(f"  ❌ No IMVDB results found")
                        
                except Exception as search_error:
                    print(f"  ❌ IMVDB search error: {search_error}")
                
                print("-" * 40)
            
            if updated_count > 0:
                session.commit()
                print(f"✅ Updated {updated_count} videos with URLs from IMVDB")
            else:
                print("No videos were updated")
            
            return {"success": True, "updated_count": updated_count}
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error checking IMVDB: {e}")
        print(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "find":
            find_videos_without_urls()
        elif command == "delete":
            confirm = "--confirm" in sys.argv
            result = delete_videos_without_urls(confirm)
            print("\nResult:", result)
        elif command == "imvdb":
            result = check_imvdb_for_missing_urls()
            print("\nResult:", result)
        else:
            print("Usage:")
            print("  python cleanup_videos_without_urls.py find        # Find videos without URLs")
            print("  python cleanup_videos_without_urls.py delete     # Delete videos without URLs (dry run)")
            print("  python cleanup_videos_without_urls.py delete --confirm  # Actually delete")
            print("  python cleanup_videos_without_urls.py imvdb      # Check IMVDB for missing URLs")
    else:
        print("Usage:")
        print("  python cleanup_videos_without_urls.py find        # Find videos without URLs")
        print("  python cleanup_videos_without_urls.py delete     # Delete videos without URLs (dry run)")
        print("  python cleanup_videos_without_urls.py delete --confirm  # Actually delete")
        print("  python cleanup_videos_without_urls.py imvdb      # Check IMVDB for missing URLs")