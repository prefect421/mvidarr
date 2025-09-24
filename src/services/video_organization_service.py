"""
Video organization service for moving and organizing downloaded videos
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.settings_service import settings
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.video_organization")


class VideoOrganizationService:
    """Service for organizing downloaded videos into artist folders"""

    def __init__(self):
        self.cleanup = FilenameCleanup()

    def get_downloads_path(self) -> Path:
        """Get the downloads directory path"""
        downloads_path = settings.get("downloads_path", "data/downloads")
        return Path(downloads_path)

    def get_music_videos_path(self) -> Path:
        """Get the music videos directory path"""
        music_videos_path = settings.get("music_videos_path", "data/musicvideos")

        # If setting exists but is empty, use default
        if not music_videos_path or music_videos_path.strip() == "":
            music_videos_path = "data/musicvideos"

        return Path(music_videos_path)

    def ensure_directories_exist(self):
        """Ensure required directories exist"""
        downloads_dir = self.get_downloads_path()
        music_videos_dir = self.get_music_videos_path()

        downloads_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
        music_videos_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

        logger.debug(f"Ensured directories exist: {downloads_dir}, {music_videos_dir}")

    def scan_downloads_directory(self) -> List[Path]:
        """
        Scan downloads directory for video files

        Returns:
            List of video file paths
        """
        downloads_dir = self.get_downloads_path()

        if not downloads_dir.exists():
            logger.warning(f"Downloads directory does not exist: {downloads_dir}")
            return []

        # Common video file extensions
        video_extensions = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }

        video_files = []
        for file_path in downloads_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                video_files.append(file_path)

        logger.info(f"Found {len(video_files)} video files in downloads directory")
        return video_files

    def process_video_file(self, file_path: Path) -> Dict:
        """
        Process a single video file - clean filename and organize

        Args:
            file_path: Path to video file

        Returns:
            Dict with processing results
        """
        result = {
            "original_path": str(file_path),
            "success": False,
            "error": None,
            "artist": None,
            "title": None,
            "new_path": None,
            "cleaned_filename": None,
        }

        try:
            # Clean the filename
            cleaned_filename = self.cleanup.clean_filename(file_path.name)
            result["cleaned_filename"] = cleaned_filename

            # Extract artist and title
            artist, title = self.cleanup.extract_artist_and_title(cleaned_filename)
            result["artist"] = artist
            result["title"] = title

            if not artist or not title:
                logger.warning(f"Could not extract artist/title from: {file_path.name}")
                result["error"] = "Could not parse artist and title from filename"
                return result

            # Create destination path
            music_videos_dir = self.get_music_videos_path()
            artist_folder = self.cleanup.sanitize_folder_name(artist)
            artist_dir = music_videos_dir / artist_folder

            # Generate clean filename
            final_filename = self.cleanup.generate_clean_filename(
                artist, title, file_path.suffix
            )

            destination_path = artist_dir / final_filename
            result["new_path"] = str(destination_path)

            # Create artist directory if it doesn't exist
            artist_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

            # Handle filename conflicts
            if destination_path.exists():
                counter = 1
                stem = destination_path.stem
                suffix = destination_path.suffix
                while destination_path.exists():
                    new_name = f"{stem} ({counter}){suffix}"
                    destination_path = artist_dir / new_name
                    counter += 1
                result["new_path"] = str(destination_path)

            # Move the file
            shutil.move(str(file_path), str(destination_path))

            # Update database if artist/video records exist
            self._update_database_records(artist, title, str(destination_path))

            result["success"] = True
            logger.info(
                f"Successfully organized: {file_path.name} -> {destination_path}"
            )

        except Exception as e:
            error_msg = f"Failed to process {file_path.name}: {e}"
            logger.error(error_msg)
            result["error"] = error_msg

        return result

    def _update_database_records(self, artist_name: str, title: str, file_path: str):
        """Update database records with the new file location"""
        try:
            with get_db() as session:
                # Find matching artist
                artist = (
                    session.query(Artist)
                    .filter(Artist.name.ilike(f"%{artist_name}%"))
                    .first()
                )

                if artist:
                    # Find matching video
                    video = (
                        session.query(Video)
                        .filter(
                            Video.artist_id == artist.id,
                            Video.title.ilike(f"%{title}%"),
                        )
                        .first()
                    )

                    if video:
                        # Update video with local file path and extract technical details
                        video.local_path = file_path
                        video.status = VideoStatus.DOWNLOADED
                        video.updated_at = datetime.utcnow()
                        
                        # Extract technical metadata from the video file
                        try:
                            import subprocess
                            import json
                            import os
                            
                            # Use ffprobe to get video information
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
                                if video_stream:
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
                                    
                                    # Update video record with technical details
                                    video.duration = duration
                                    video.quality = quality
                                    
                                    # Update or create video_metadata
                                    existing_metadata = video.video_metadata or {}
                                    existing_metadata.update({
                                        'width': width,
                                        'height': height,
                                        'video_codec': codec,
                                        'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else None,
                                        'organized_file_path': file_path,
                                        'extraction_date': datetime.utcnow().isoformat()
                                    })
                                    video.video_metadata = existing_metadata
                                    
                                    logger.info(f"✅ Extracted technical metadata for organized video {video.id}:")
                                    logger.info(f"   Duration: {duration:.1f}s")
                                    logger.info(f"   Quality: {quality} ({width}x{height})")
                                    logger.info(f"   Codec: {codec}")
                                    
                                else:
                                    logger.warning(f"No video stream found in organized file: {file_path}")
                            else:
                                logger.warning(f"ffprobe failed for organized file {file_path}: {result.stderr}")
                                
                        except Exception as metadata_error:
                            logger.warning(f"Failed to extract metadata from organized file {file_path}: {metadata_error}")
                        
                        session.commit()

                        logger.info(
                            f"Updated database record for: {artist_name} - {title}"
                        )
                        
                        # Trigger automatic metadata enrichment for organized video
                        try:
                            from src.services.metadata_enrichment_service import MetadataEnrichmentService
                            enrichment_service = MetadataEnrichmentService()
                            
                            # Enrich metadata asynchronously
                            import asyncio
                            async def enrich_metadata():
                                result = await enrichment_service.enrich_video_metadata(
                                    video.id, force_refresh=True
                                )
                                if result.success:
                                    logger.info(f"Metadata enrichment completed for organized video {video.id}: "
                                               f"enriched {len(result.enriched_fields or [])} fields")
                                else:
                                    logger.warning(f"Metadata enrichment failed for organized video {video.id}: "
                                                  f"{result.errors}")
                            
                            # Run enrichment in background
                            try:
                                loop = asyncio.get_event_loop()
                                loop.create_task(enrich_metadata())
                            except RuntimeError:
                                asyncio.run(enrich_metadata())
                                
                            logger.info(f"Triggered metadata enrichment for organized video {video.id}")
                            
                        except Exception as enrichment_error:
                            logger.error(f"Failed to trigger metadata enrichment for video {video.id}: {enrichment_error}")
                    else:
                        logger.debug(
                            f"No video record found for: {artist_name} - {title}"
                        )
                        # Consider auto-indexing the video here if enabled
                        self._auto_index_video_if_enabled(artist_name, title, file_path)
                else:
                    logger.debug(f"No artist record found for: {artist_name}")
                    # Consider auto-indexing the video here if enabled
                    self._auto_index_video_if_enabled(artist_name, title, file_path)

        except Exception as e:
            logger.error(f"Failed to update database records: {e}")

    def _auto_index_video_if_enabled(
        self, artist_name: str, title: str, file_path: str
    ):
        """Auto-index video if auto-indexing is enabled"""
        try:
            # Check if auto-indexing is enabled in settings
            auto_index = settings.get("auto_index_organized_videos", True)

            if auto_index:
                from pathlib import Path

                from src.services.video_indexing_service import video_indexing_service

                logger.info(f"Auto-indexing organized video: {artist_name} - {title}")

                result = video_indexing_service.index_single_file(
                    Path(file_path), fetch_metadata=True
                )

                if result["success"]:
                    logger.info(f"Successfully auto-indexed: {artist_name} - {title}")
                else:
                    logger.warning(
                        f"Failed to auto-index: {artist_name} - {title}: {result.get('error')}"
                    )

        except Exception as e:
            logger.warning(f"Failed to auto-index video: {e}")

    def organize_all_downloads(self) -> Dict:
        """
        Organize all video files in the downloads directory

        Returns:
            Summary of organization results
        """
        logger.info("Starting video organization process")

        # Ensure directories exist
        self.ensure_directories_exist()

        # Scan for video files
        video_files = self.scan_downloads_directory()

        if not video_files:
            logger.info("No video files found to organize")
            return {
                "total_files": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "results": [],
            }

        # Process each file
        results = []
        successful = 0
        failed = 0

        for file_path in video_files:
            result = self.process_video_file(file_path)
            results.append(result)

            if result["success"]:
                successful += 1
            else:
                failed += 1

        summary = {
            "total_files": len(video_files),
            "processed": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

        logger.info(f"Organization complete: {successful} successful, {failed} failed")
        return summary

    def organize_single_file(self, filename: str) -> Dict:
        """
        Organize a specific file by name

        Args:
            filename: Name of file in downloads directory

        Returns:
            Processing result
        """
        downloads_dir = self.get_downloads_path()
        file_path = downloads_dir / filename

        if not file_path.exists():
            return {
                "success": False,
                "error": f"File not found: {filename}",
                "original_path": str(file_path),
            }

        return self.process_video_file(file_path)

    def get_artist_directories(self) -> List[Dict]:
        """
        Get list of artist directories in music videos folder

        Returns:
            List of artist directory info
        """
        music_videos_dir = self.get_music_videos_path()

        if not music_videos_dir.exists():
            return []

        artists = []
        for item in music_videos_dir.iterdir():
            if item.is_dir():
                # Count video files in artist directory
                video_count = (
                    len(list(item.glob("*.mp4")))
                    + len(list(item.glob("*.mkv")))
                    + len(list(item.glob("*.avi")))
                    + len(list(item.glob("*.mov")))
                    + len(list(item.glob("*.wmv")))
                    + len(list(item.glob("*.flv")))
                    + len(list(item.glob("*.webm")))
                    + len(list(item.glob("*.m4v")))
                )

                artists.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "video_count": video_count,
                        "last_modified": datetime.fromtimestamp(
                            item.stat().st_mtime
                        ).isoformat(),
                    }
                )

        # Sort by name
        artists.sort(key=lambda x: x["name"].lower())
        return artists

    def cleanup_empty_directories(self) -> int:
        """
        Remove empty directories from music videos folder

        Returns:
            Number of directories removed
        """
        music_videos_dir = self.get_music_videos_path()

        if not music_videos_dir.exists():
            return 0

        removed_count = 0
        for item in music_videos_dir.iterdir():
            if item.is_dir():
                try:
                    # Check if directory is empty
                    if not any(item.iterdir()):
                        item.rmdir()
                        removed_count += 1
                        logger.info(f"Removed empty directory: {item.name}")
                except OSError:
                    # Directory not empty or permission error
                    pass

        return removed_count

    def scan_existing_music_videos(self) -> List[Path]:
        """
        Scan existing music videos directory for video files that might need reorganization

        Returns:
            List of video file paths in music videos directory
        """
        music_videos_dir = self.get_music_videos_path()

        if not music_videos_dir.exists():
            logger.warning(f"Music videos directory does not exist: {music_videos_dir}")
            return []

        # Common video file extensions
        video_extensions = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }

        video_files = []
        for file_path in music_videos_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                video_files.append(file_path)

        logger.info(f"Found {len(video_files)} video files in music videos directory")
        return video_files

    def reorganize_existing_videos(self) -> Dict:
        """
        Reorganize existing videos in the music videos directory

        Returns:
            Summary of reorganization results
        """
        logger.info("Starting reorganization of existing music videos")

        # Ensure directories exist
        self.ensure_directories_exist()

        # Scan for video files in music videos directory
        video_files = self.scan_existing_music_videos()

        if not video_files:
            logger.info("No video files found to reorganize")
            return {
                "total_files": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
            }

        # Process each file
        results = []
        successful = 0
        failed = 0
        skipped = 0

        for file_path in video_files:
            result = self.reorganize_single_existing_video(file_path)
            results.append(result)

            if result["success"]:
                successful += 1
            elif result["skipped"]:
                skipped += 1
            else:
                failed += 1

        summary = {
            "total_files": len(video_files),
            "processed": len(results),
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "results": results,
        }

        logger.info(
            f"Reorganization complete: {successful} successful, {failed} failed, {skipped} skipped"
        )
        return summary

    def reorganize_single_existing_video(self, file_path: Path) -> Dict:
        """
        Reorganize a single existing video file

        Args:
            file_path: Path to existing video file

        Returns:
            Dict with reorganization results
        """
        result = {
            "original_path": str(file_path),
            "success": False,
            "skipped": False,
            "error": None,
            "artist": None,
            "title": None,
            "new_path": None,
            "cleaned_filename": None,
            "action": None,
        }

        try:
            # Clean the filename
            cleaned_filename = self.cleanup.clean_filename(file_path.name)
            result["cleaned_filename"] = cleaned_filename

            # Extract artist and title
            artist, title = self.cleanup.extract_artist_and_title(cleaned_filename)
            result["artist"] = artist
            result["title"] = title

            if not artist or not title:
                logger.debug(f"Could not extract artist/title from: {file_path.name}")
                result["error"] = "Could not parse artist and title from filename"
                result["skipped"] = True
                return result

            # Generate the proper target path
            music_videos_dir = self.get_music_videos_path()
            artist_folder = self.cleanup.sanitize_folder_name(artist)
            artist_dir = music_videos_dir / artist_folder

            # Generate clean filename
            final_filename = self.cleanup.generate_clean_filename(
                artist, title, file_path.suffix
            )

            destination_path = artist_dir / final_filename
            result["new_path"] = str(destination_path)

            # Check if the file is already in the correct location with correct name
            if file_path == destination_path:
                result["success"] = True
                result["skipped"] = True
                result["action"] = "already_organized"
                logger.debug(f"File already properly organized: {file_path}")
                return result

            # Check if the file is in the correct artist folder but wrong name
            if file_path.parent == artist_dir and file_path.name != final_filename:
                # Just rename the file
                result["action"] = "rename"
            elif file_path.parent.name != artist_folder:
                # Need to move to different artist folder
                result["action"] = "move_and_rename"
            else:
                result["action"] = "organize"

            # Create artist directory if it doesn't exist
            artist_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

            # Handle filename conflicts
            if destination_path.exists() and destination_path != file_path:
                counter = 1
                stem = destination_path.stem
                suffix = destination_path.suffix
                while destination_path.exists():
                    new_name = f"{stem} ({counter}){suffix}"
                    destination_path = artist_dir / new_name
                    counter += 1
                result["new_path"] = str(destination_path)

            # Move/rename the file
            shutil.move(str(file_path), str(destination_path))

            # Update database if artist/video records exist
            self._update_database_records(artist, title, str(destination_path))

            result["success"] = True
            logger.info(
                f"Successfully reorganized: {file_path.name} -> {destination_path}"
            )

        except Exception as e:
            error_msg = f"Failed to reorganize {file_path.name}: {e}"
            logger.error(error_msg)
            result["error"] = error_msg

        return result


# Convenience instance
video_organizer = VideoOrganizationService()
