#!/usr/bin/env python3
"""
Video indexing script for MVidarr
Scans existing videos and adds them to database with metadata
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

from src.config.config import Config
from src.database.connection import init_db
from src.services.video_indexing_service import video_indexing_service
from src.services.thumbnail_service import thumbnail_service
from src.utils.logger import get_logger

logger = get_logger('mvidarr.video_indexing_script')

class DummyApp:
    """Dummy app for database initialization"""
    def __init__(self):
        self.config = {}
        self.db_manager = None
        config = Config()
        for attr in dir(config):
            if not attr.startswith('_'):
                self.config[attr] = getattr(config, attr)
    
    def teardown_appcontext(self, func):
        """Dummy teardown function for Flask compatibility"""
        pass

def initialize_environment():
    """Initialize the application environment"""
    try:
        # Initialize database
        app = DummyApp() 
        init_db(app)
        logger.info("Environment initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize environment: {e}")
        return False

def index_all_videos(fetch_metadata=True, max_files=None):
    """Index all videos in the music videos directory"""
    logger.info("Starting video indexing process")
    
    try:
        print(f"\n🎬 Video Indexing Process 🎬")
        print(f"Fetch metadata: {'Yes' if fetch_metadata else 'No'}")
        if max_files:
            print(f"Max files to process: {max_files}")
        print("-" * 60)
        
        result = video_indexing_service.index_all_videos(
            fetch_metadata=fetch_metadata,
            max_files=max_files
        )
        
        print(f"\n🎬 Video Indexing Complete 🎬")
        print(f"Total files found: {result['total_files']}")
        print(f"Successfully indexed: {result['successful']}")
        print(f"Already indexed: {result['already_indexed']}")
        print(f"Failed to index: {result['failed']}")
        print(f"Artists created: {result['artists_created']}")
        print(f"Videos created: {result['videos_created']}")
        print(f"Downloads created: {result['downloads_created']}")
        print(f"Metadata found: {result['imvdb_metadata_found']}")
        print(f"Thumbnails downloaded: {result['thumbnails_downloaded']}")
        
        if result['successful'] > 0:
            print(f"\n✅ Successfully indexed videos:")
            for item in result['results'][:10]:  # Show first 10
                if item['success'] and not item['already_indexed']:
                    metadata_status = "✓" if item['imvdb_metadata_found'] else "✗"
                    thumbnail_status = "✓" if item['thumbnail_downloaded'] else "✗"
                    print(f"  • {item['artist_name']} - {item['video_title']} [Meta: {metadata_status}, Thumb: {thumbnail_status}]")
            
            if result['successful'] > 10:
                print(f"  ... and {result['successful'] - 10} more videos")
        
        if result['failed'] > 0:
            print(f"\n❌ Failed to index:")
            for item in result['results']:
                if not item['success']:
                    file_name = Path(item['file_path']).name
                    print(f"  • {file_name}: {item['error']}")
        
        return result['successful'] > 0
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        print(f"❌ Indexing failed: {e}")
        return False

def index_single_file(file_path, fetch_metadata=True):
    """Index a specific video file"""
    logger.info(f"Indexing single file: {file_path}")
    
    try:
        print(f"\n🎬 Single Video Indexing 🎬")
        print(f"File: {file_path}")
        print(f"Fetch metadata: {'Yes' if fetch_metadata else 'No'}")
        print("-" * 60)
        
        result = video_indexing_service.index_single_file(
            Path(file_path),
            fetch_metadata=fetch_metadata
        )
        
        if result['success']:
            if result['already_indexed']:
                print(f"⏭️  File already indexed: {result['artist_name']} - {result['video_title']}")
            else:
                print(f"✅ Successfully indexed: {result['artist_name']} - {result['video_title']}")
                if result['imvdb_metadata_found']:
                    print(f"   📋 Metadata found")
                if result['thumbnail_downloaded']:
                    print(f"   🖼️  Thumbnail downloaded")
            return True
        else:
            print(f"❌ Failed to index {file_path}: {result['error']}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to index {file_path}: {e}")
        print(f"❌ Failed to index {file_path}: {e}")
        return False

def show_indexing_stats():
    """Show current indexing statistics"""
    try:
        stats = video_indexing_service.get_indexing_stats()
        thumbnail_stats = thumbnail_service.get_storage_stats()
        
        print(f"\n📊 Video Indexing Statistics 📊")
        print("-" * 50)
        print(f"Total artists:           {stats['total_artists']}")
        print(f"Total videos:            {stats['total_videos']}")
        print(f"Total downloads:         {stats['total_downloads']}")
        print(f"Downloaded videos:       {stats['downloaded_videos']}")
        print(f"Videos with files:       {stats['videos_with_files']}")
        print(f"Videos with metadata:    {stats['videos_with_imvdb']}")
        print(f"Metadata coverage:       {stats['imvdb_coverage']}%")
        print("-" * 50)
        print(f"Thumbnail files:         {thumbnail_stats['total_files']}")
        print(f"Thumbnail storage:       {thumbnail_stats['total_size_mb']} MB")
        print(f"Artist thumbnails:       {thumbnail_stats['artist_thumbnails']}")
        print(f"Video thumbnails:        {thumbnail_stats['video_thumbnails']}")
        
    except Exception as e:
        logger.error(f"Failed to show stats: {e}")
        print(f"❌ Failed to show stats: {e}")

def scan_video_files(directory=None):
    """Scan directory for video files without indexing"""
    try:
        scan_dir = Path(directory) if directory else None
        video_files = video_indexing_service.scan_video_files(scan_dir)
        
        if scan_dir:
            print(f"\n📁 Video Files Scan: {scan_dir} 📁")
        else:
            print(f"\n📁 Video Files Scan: Default Directory 📁")
        
        print(f"Total video files found: {len(video_files)}")
        print("-" * 60)
        
        if video_files:
            print("Video files found:")
            for i, file_path in enumerate(video_files[:20], 1):  # Show first 20 files
                try:
                    if scan_dir:
                        relative_path = file_path.relative_to(scan_dir)
                    else:
                        relative_path = file_path.name
                    print(f"  {i:3d}. {relative_path}")
                except ValueError:
                    print(f"  {i:3d}. {file_path}")
            
            if len(video_files) > 20:
                print(f"  ... and {len(video_files) - 20} more files")
        else:
            print("No video files found")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to scan video files: {e}")
        print(f"❌ Failed to scan video files: {e}")
        return False

def preview_file_indexing(file_path):
    """Preview what would be indexed for a file"""
    try:
        print(f"\n🔍 Indexing Preview: {Path(file_path).name} 🔍")
        print("-" * 60)
        
        file_metadata = video_indexing_service.extract_file_metadata(Path(file_path))
        
        print(f"File path: {file_metadata['file_path']}")
        print(f"File size: {file_metadata['file_size']} bytes" if file_metadata['file_size'] else "File size: Unknown")
        print(f"Artist folder: {file_metadata['artist_folder'] or 'None detected'}")
        print(f"Cleaned filename: {file_metadata['cleaned_filename']}")
        print(f"Extracted artist: {file_metadata['extracted_artist'] or 'Could not extract'}")
        print(f"Extracted title: {file_metadata['extracted_title'] or 'Could not extract'}")
        
        if file_metadata['extracted_artist'] and file_metadata['extracted_title']:
            print(f"✅ Can be indexed")
            
            # Try to get a metadata preview
            print("\nSearching for metadata...")
            try:
                imvdb_metadata = video_indexing_service.fetch_imvdb_metadata(
                    file_metadata['extracted_artist'],
                    file_metadata['extracted_title']
                )
                if imvdb_metadata:
                    print(f"✅ Metadata found:")
                    print(f"   Title: {imvdb_metadata['title']}")
                    print(f"   Artist: {imvdb_metadata['artist_name']}")
                    print(f"   Year: {imvdb_metadata['year'] or 'Unknown'}")
                    print(f"   Thumbnail: {'Available' if imvdb_metadata['thumbnail_url'] else 'None'}")
                else:
                    print(f"❌ No metadata found")
            except Exception as e:
                print(f"⚠️  Metadata search failed: {e}")
        else:
            print(f"❌ Cannot be indexed - missing artist or title")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to preview file: {e}")
        print(f"❌ Failed to preview file: {e}")
        return False

def main():
    """Main script entry point"""
    parser = argparse.ArgumentParser(
        description='Index existing music videos to database with metadata',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --index-all                    # Index all videos with metadata
  %(prog)s --index-all --no-metadata     # Index without fetching metadata
  %(prog)s --index-all --max-files 100   # Index up to 100 files (testing)
  %(prog)s --index "video.mp4"           # Index specific video
  %(prog)s --scan                        # Scan for video files
  %(prog)s --scan --directory /path      # Scan specific directory
  %(prog)s --stats                       # Show indexing statistics
  %(prog)s --preview "video.mp4"         # Preview file indexing
        """
    )
    
    parser.add_argument('--index-all', action='store_true',
                       help='Index all videos in music videos directory')
    parser.add_argument('--index', metavar='FILE_PATH',
                       help='Index specific video file')
    parser.add_argument('--scan', action='store_true',
                       help='Scan for video files without indexing')
    parser.add_argument('--directory', metavar='PATH',
                       help='Directory to scan (for --scan)')
    parser.add_argument('--stats', action='store_true',
                       help='Show current indexing statistics')
    parser.add_argument('--preview', metavar='FILE_PATH',
                       help='Preview what would be indexed for a file')
    parser.add_argument('--no-metadata', action='store_true',
                       help='Skip fetching metadata')
    parser.add_argument('--max-files', type=int, metavar='N',
                       help='Maximum number of files to process (for testing)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Show help if no arguments
    if not any(vars(args).values()):
        parser.print_help()
        return 0
    
    # Stats mode doesn't require database
    if args.stats:
        if not initialize_environment():
            print("❌ Failed to initialize environment")
            return 1
        show_indexing_stats()
        return 0
    
    if args.scan:
        if not initialize_environment():
            print("❌ Failed to initialize environment")
            return 1
        return 0 if scan_video_files(args.directory) else 1
    
    if args.preview:
        if not initialize_environment():
            print("❌ Failed to initialize environment")
            return 1
        return 0 if preview_file_indexing(args.preview) else 1
    
    # Initialize environment for database operations
    if not initialize_environment():
        print("❌ Failed to initialize environment")
        return 1
    
    success = True
    fetch_metadata = not args.no_metadata
    
    if args.index_all:
        success = index_all_videos(fetch_metadata, args.max_files) and success
    
    if args.index:
        success = index_single_file(args.index, fetch_metadata) and success
    
    return 0 if success else 1

if __name__ == '__main__':
    exit(main())