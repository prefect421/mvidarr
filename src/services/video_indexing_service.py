"""
Video indexing service for scanning and adding existing videos to database
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from src.database.connection import get_db
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.thumbnail_service import thumbnail_service
from src.services.video_organization_service import video_organizer
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.video_indexing")


class VideoIndexingService:
    """Service for indexing existing video files and fetching metadata"""

    def __init__(self):
        self.cleanup = FilenameCleanup()
        self.video_extensions = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }

    def scan_video_files(self, directory: Path = None) -> List[Path]:
        """
        Scan directory for video files

        Args:
            directory: Directory to scan (defaults to music videos path)

        Returns:
            List of video file paths
        """
        if directory is None:
            directory = video_organizer.get_music_videos_path()

        if not directory.exists():
            logger.warning(f"Directory does not exist: {directory}")
            return []

        video_files = []
        for file_path in directory.rglob("*"):
            if (
                file_path.is_file()
                and file_path.suffix.lower() in self.video_extensions
            ):
                video_files.append(file_path)

        logger.info(f"Found {len(video_files)} video files in {directory}")
        return video_files

    def extract_ffmpeg_metadata(self, file_path: Path) -> Dict:
        """
        Extract technical metadata from video file using FFprobe

        Args:
            file_path: Path to video file

        Returns:
            Dictionary with video metadata (duration, resolution, quality, etc.)
        """
        metadata = {
            "duration": None,
            "quality": None,
            "width": None,
            "height": None,
            "video_codec": None,
            "audio_codec": None,
            "fps": None,
            "bitrate": None,
            "file_size": None,
        }

        try:
            # Use ffprobe to get detailed video information
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(file_path),
            ]

            logger.debug(f"Running ffprobe on: {file_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                logger.warning(f"FFprobe failed for {file_path}: {result.stderr}")
                return metadata

            data = json.loads(result.stdout)

            # Extract format information
            if "format" in data:
                format_info = data["format"]

                # Duration in seconds
                if "duration" in format_info:
                    try:
                        metadata["duration"] = int(float(format_info["duration"]))
                    except (ValueError, TypeError):
                        pass

                # Bitrate
                if "bit_rate" in format_info:
                    try:
                        metadata["bitrate"] = int(format_info["bit_rate"])
                    except (ValueError, TypeError):
                        pass

                # File size
                if "size" in format_info:
                    try:
                        metadata["file_size"] = int(format_info["size"])
                    except (ValueError, TypeError):
                        pass

            # Extract stream information
            if "streams" in data:
                for stream in data["streams"]:
                    if stream.get("codec_type") == "video":
                        # Video stream information
                        metadata["width"] = stream.get("width")
                        metadata["height"] = stream.get("height")
                        metadata["video_codec"] = stream.get("codec_name")

                        # Frame rate
                        if "r_frame_rate" in stream:
                            try:
                                fps_str = stream["r_frame_rate"]
                                if "/" in fps_str:
                                    num, den = fps_str.split("/")
                                    metadata["fps"] = round(float(num) / float(den), 2)
                                else:
                                    metadata["fps"] = float(fps_str)
                            except (ValueError, TypeError, ZeroDivisionError):
                                pass

                    elif stream.get("codec_type") == "audio":
                        # Audio stream information
                        if not metadata["audio_codec"]:  # Take first audio stream
                            metadata["audio_codec"] = stream.get("codec_name")

            # Determine quality based on height
            if metadata["height"]:
                height = metadata["height"]
                if height >= 2160:
                    metadata["quality"] = "4K"
                elif height >= 1440:
                    metadata["quality"] = "1440p"
                elif height >= 1080:
                    metadata["quality"] = "1080p"
                elif height >= 720:
                    metadata["quality"] = "720p"
                elif height >= 480:
                    metadata["quality"] = "480p"
                else:
                    metadata["quality"] = f"{height}p"

            logger.debug(
                f"Extracted metadata for {file_path}: duration={metadata['duration']}s, quality={metadata['quality']}"
            )

        except subprocess.TimeoutExpired:
            logger.error(f"FFprobe timeout for {file_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse FFprobe output for {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error extracting FFmpeg metadata for {file_path}: {e}")

        return metadata

    def extract_file_metadata(self, file_path: Path) -> Dict:
        """
        Extract metadata from video file path and filename

        Args:
            file_path: Path to video file

        Returns:
            Dictionary with extracted metadata
        """
        metadata = {
            "file_path": str(file_path),
            "filename": file_path.name,
            "file_size": None,
            "created_time": None,
            "modified_time": None,
            "artist_folder": None,
            "extracted_artist": None,
            "extracted_title": None,
            "cleaned_filename": None,
        }

        try:
            # Get file stats
            stat = file_path.stat()
            metadata["file_size"] = stat.st_size
            metadata["created_time"] = datetime.fromtimestamp(stat.st_ctime)
            metadata["modified_time"] = datetime.fromtimestamp(stat.st_mtime)

            # Extract artist from folder structure
            music_videos_path = video_organizer.get_music_videos_path()
            try:
                relative_path = file_path.relative_to(music_videos_path)
                if len(relative_path.parts) > 1:
                    metadata["artist_folder"] = relative_path.parts[0]
            except ValueError:
                # File is not under music videos path
                pass

            # Clean filename and extract artist/title
            cleaned_filename = self.cleanup.clean_filename(file_path.name)
            metadata["cleaned_filename"] = cleaned_filename

            artist, title = self.cleanup.extract_artist_and_title(cleaned_filename)
            metadata["extracted_artist"] = artist
            metadata["extracted_title"] = title

            # Use folder name as fallback artist if extraction failed
            if not artist and metadata["artist_folder"]:
                metadata["extracted_artist"] = metadata["artist_folder"]

        except Exception as e:
            logger.error(f"Failed to extract metadata from {file_path}: {e}")

        return metadata

    def find_or_create_artist(self, artist_name: str, session) -> Artist:
        """
        Find existing artist or create new one

        Args:
            artist_name: Name of the artist
            session: Database session

        Returns:
            Artist object
        """
        # Clean up artist name
        clean_name = self.cleanup.sanitize_folder_name(artist_name)

        # Try to find existing artist (case-insensitive)
        artist = (
            session.query(Artist).filter(Artist.name.ilike(f"%{clean_name}%")).first()
        )

        if artist:
            logger.debug(f"Found existing artist: {artist.name}")
            return artist

        # Create new artist
        artist = Artist(
            name=clean_name,
            monitored=True,
            folder_path=str(video_organizer.get_music_videos_path() / clean_name),
        )

        session.add(artist)
        session.flush()  # Get the ID

        logger.info(f"Created new artist: {clean_name}")

        # Run auto-processing for newly created artist
        try:
            from src.services.artist_auto_processing_service import (
                artist_auto_processing_service,
            )

            # Only attempt auto-processing if artist is properly bound to session
            if artist in session:
                auto_processing_results = (
                    artist_auto_processing_service.process_new_artist(artist, session)
                )
                match_count = auto_processing_results.get("auto_match", {}).get(
                    "match_count", 0
                )
                logger.info(
                    f"Auto-processing completed for {clean_name} - {match_count} services matched"
                )
            else:
                logger.warning(
                    f"Skipping auto-processing for {clean_name} - artist not bound to session"
                )
        except Exception as e:
            logger.warning(
                f"Auto-processing failed for newly created artist {clean_name}: {e}"
            )

        return artist

    def fetch_imvdb_metadata(self, artist_name: str, title: str) -> Optional[Dict]:
        """
        Fetch metadata from IMVDb for a video

        Args:
            artist_name: Name of the artist
            title: Video title

        Returns:
            IMVDb metadata dictionary or None
        """
        try:
            video_data = imvdb_service.find_best_video_match(artist_name, title)
            if video_data:
                metadata = imvdb_service.extract_metadata(video_data)
                logger.info(f"Retrieved IMVDb metadata for: {artist_name} - {title}")
                return metadata
            else:
                logger.debug(f"No IMVDb metadata found for: {artist_name} - {title}")
                return None
        except Exception as e:
            logger.error(
                f"Failed to fetch IMVDb metadata for {artist_name} - {title}: {e}"
            )
            return None

    def create_video_record(
        self,
        artist: Artist,
        file_metadata: Dict,
        imvdb_metadata: Dict = None,
        ffmpeg_metadata: Dict = None,
        session=None,
    ) -> Video:
        """
        Create a video record in the database

        Args:
            artist: Artist object
            file_metadata: File metadata dictionary
            imvdb_metadata: Optional IMVDb metadata
            ffmpeg_metadata: Optional FFmpeg technical metadata
            session: Database session

        Returns:
            Video object
        """
        title = file_metadata["extracted_title"] or file_metadata["filename"]

        video = Video(
            artist_id=artist.id,
            title=title,
            status=VideoStatus.DOWNLOADED,  # File exists so it's downloaded
            local_path=file_metadata["file_path"],
            created_at=file_metadata.get("created_time", datetime.utcnow()),
        )

        # Add FFmpeg technical metadata if available
        if ffmpeg_metadata:
            video.duration = ffmpeg_metadata.get("duration")
            video.quality = ffmpeg_metadata.get("quality")

            # Store additional technical metadata in video_metadata field
            tech_metadata = {
                "width": ffmpeg_metadata.get("width"),
                "height": ffmpeg_metadata.get("height"),
                "video_codec": ffmpeg_metadata.get("video_codec"),
                "audio_codec": ffmpeg_metadata.get("audio_codec"),
                "fps": ffmpeg_metadata.get("fps"),
                "bitrate": ffmpeg_metadata.get("bitrate"),
                "ffmpeg_extracted": True,
                "extraction_date": datetime.utcnow().isoformat(),
            }
            video.video_metadata = tech_metadata
            logger.info(
                f"Added FFmpeg metadata: duration={video.duration}s, quality={video.quality}"
            )

        # Add IMVDb metadata if available
        if imvdb_metadata:
            video.imvdb_id = imvdb_metadata.get("imvdb_id")
            video.year = imvdb_metadata.get("year")
            video.directors = imvdb_metadata.get("directors")
            video.producers = imvdb_metadata.get("producers")
            video.thumbnail_url = imvdb_metadata.get("thumbnail_url")
            video.imvdb_metadata = imvdb_metadata.get("raw_metadata")

            # Use IMVDb title if it's more accurate
            if imvdb_metadata.get("title"):
                video.title = imvdb_metadata["title"]

            # Download thumbnail if available
            if imvdb_metadata.get("thumbnail_url"):
                try:
                    thumbnail_path = thumbnail_service.download_video_thumbnail(
                        artist.name, video.title, imvdb_metadata["thumbnail_url"]
                    )
                    if thumbnail_path:
                        video.thumbnail_path = thumbnail_path
                        logger.info(
                            f"Downloaded thumbnail for: {artist.name} - {video.title}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to download thumbnail for {artist.name} - {video.title}: {e}"
                    )

        session.add(video)
        session.flush()  # Get the ID

        return video

    def create_download_record(
        self, artist: Artist, video: Video, file_metadata: Dict, session=None
    ) -> Download:
        """
        Create a download record for the existing file

        Args:
            artist: Artist object
            video: Video object
            file_metadata: File metadata dictionary
            session: Database session

        Returns:
            Download object
        """
        download = Download(
            artist_id=artist.id,
            video_id=video.id,
            title=video.title,
            original_url="local_file",  # Mark as local file
            file_path=file_metadata["file_path"],
            file_size=file_metadata.get("file_size"),
            download_date=file_metadata.get("created_time", datetime.utcnow()),
            status="completed",
            progress=100,
            quality="unknown",
            format=Path(file_metadata["file_path"]).suffix.lstrip("."),
        )

        session.add(download)

        return download

    def index_single_file(self, file_path: Path, fetch_metadata: bool = True) -> Dict:
        """
        Index a single video file

        Args:
            file_path: Path to video file
            fetch_metadata: Whether to fetch IMVDb metadata

        Returns:
            Dictionary with indexing results
        """
        result = {
            "file_path": str(file_path),
            "success": False,
            "error": None,
            "artist_name": None,
            "video_title": None,
            "artist_created": False,
            "video_created": False,
            "download_created": False,
            "imvdb_metadata_found": False,
            "thumbnail_downloaded": False,
            "already_indexed": False,
            "ffmpeg_metadata_extracted": False,
            "ffmpeg_metadata_updated": False,
        }

        try:
            # Extract file metadata
            file_metadata = self.extract_file_metadata(file_path)

            # Extract FFmpeg technical metadata
            ffmpeg_metadata = self.extract_ffmpeg_metadata(file_path)
            result["ffmpeg_metadata_extracted"] = bool(
                ffmpeg_metadata.get("duration") or ffmpeg_metadata.get("quality")
            )

            if not file_metadata["extracted_artist"]:
                result["error"] = "Could not extract artist name from file or folder"
                return result

            result["artist_name"] = file_metadata["extracted_artist"]
            result["video_title"] = (
                file_metadata["extracted_title"] or file_metadata["filename"]
            )

            with get_db() as session:
                # Find or create artist
                artist = self.find_or_create_artist(
                    file_metadata["extracted_artist"], session
                )
                if artist.id is None:  # New artist
                    result["artist_created"] = True

                # Check if video already exists
                existing_video = (
                    session.query(Video)
                    .filter(
                        Video.artist_id == artist.id,
                        Video.title.ilike(f"%{result['video_title']}%"),
                    )
                    .first()
                )

                if existing_video:
                    # Check if this file is already tracked
                    existing_download = (
                        session.query(Download)
                        .filter(
                            Download.video_id == existing_video.id,
                            Download.file_path == str(file_path),
                        )
                        .first()
                    )

                    if existing_download:
                        result["already_indexed"] = True
                        result["success"] = True
                        logger.debug(f"File already indexed: {file_path}")
                        return result

                # Fetch IMVDb metadata if requested
                imvdb_metadata = None
                if fetch_metadata and file_metadata["extracted_title"]:
                    imvdb_metadata = self.fetch_imvdb_metadata(
                        file_metadata["extracted_artist"],
                        file_metadata["extracted_title"],
                    )
                    if imvdb_metadata:
                        result["imvdb_metadata_found"] = True

                # Create or update video record
                if existing_video:
                    video = existing_video

                    # Update with FFmpeg metadata if not already present
                    if ffmpeg_metadata and (not video.duration or not video.quality):
                        video.duration = (
                            ffmpeg_metadata.get("duration") or video.duration
                        )
                        video.quality = ffmpeg_metadata.get("quality") or video.quality

                        # Update video_metadata with technical info
                        existing_metadata = video.video_metadata or {}
                        tech_metadata = {
                            "width": ffmpeg_metadata.get("width"),
                            "height": ffmpeg_metadata.get("height"),
                            "video_codec": ffmpeg_metadata.get("video_codec"),
                            "audio_codec": ffmpeg_metadata.get("audio_codec"),
                            "fps": ffmpeg_metadata.get("fps"),
                            "bitrate": ffmpeg_metadata.get("bitrate"),
                            "ffmpeg_extracted": True,
                            "extraction_date": datetime.utcnow().isoformat(),
                        }
                        existing_metadata.update(tech_metadata)
                        video.video_metadata = existing_metadata
                        video.updated_at = datetime.utcnow()
                        result["ffmpeg_metadata_updated"] = True
                        logger.info(
                            f"Updated existing video with FFmpeg metadata: duration={video.duration}s, quality={video.quality}"
                        )

                    # Update with IMVDb metadata if found
                    if imvdb_metadata and not video.imvdb_id:
                        video.imvdb_id = imvdb_metadata.get("imvdb_id")
                        video.year = imvdb_metadata.get("year")
                        video.directors = imvdb_metadata.get("directors")
                        video.producers = imvdb_metadata.get("producers")
                        video.thumbnail_url = imvdb_metadata.get("thumbnail_url")
                        video.imvdb_metadata = imvdb_metadata.get("raw_metadata")
                        video.updated_at = datetime.utcnow()

                        # Download thumbnail if not already present
                        if (
                            imvdb_metadata.get("thumbnail_url")
                            and not video.thumbnail_path
                        ):
                            try:
                                thumbnail_path = (
                                    thumbnail_service.download_video_thumbnail(
                                        artist.name,
                                        video.title,
                                        imvdb_metadata["thumbnail_url"],
                                    )
                                )
                                if thumbnail_path:
                                    video.thumbnail_path = thumbnail_path
                                    result["thumbnail_downloaded"] = True
                                    logger.info(
                                        f"Downloaded thumbnail for existing video: {artist.name} - {video.title}"
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to download thumbnail for {artist.name} - {video.title}: {e}"
                                )
                else:
                    video = self.create_video_record(
                        artist, file_metadata, imvdb_metadata, ffmpeg_metadata, session
                    )
                    result["video_created"] = True
                    if imvdb_metadata and imvdb_metadata.get("thumbnail_url"):
                        result["thumbnail_downloaded"] = True

                # Create download record
                download = self.create_download_record(
                    artist, video, file_metadata, session
                )
                result["download_created"] = True

                session.commit()
                result["success"] = True

                logger.info(f"Successfully indexed: {file_path.name}")

        except IntegrityError as e:
            logger.warning(f"Integrity error indexing {file_path}: {e}")
            result["error"] = f"Database integrity error: {e}"
        except Exception as e:
            logger.error(f"Failed to index {file_path}: {e}")
            result["error"] = str(e)

        return result

    def index_all_videos(
        self, directory: Path = None, fetch_metadata: bool = True, max_files: int = None
    ) -> Dict:
        """
        Index all video files in a directory

        Args:
            directory: Directory to scan (defaults to music videos path)
            fetch_metadata: Whether to fetch IMVDb metadata
            max_files: Maximum number of files to process (for testing)

        Returns:
            Summary of indexing results
        """
        logger.info("Starting video indexing process")

        video_files = self.scan_video_files(directory)

        if max_files:
            video_files = video_files[:max_files]
            logger.info(f"Limited processing to {max_files} files for testing")

        if not video_files:
            return {
                "total_files": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "already_indexed": 0,
                "artists_created": 0,
                "videos_created": 0,
                "downloads_created": 0,
                "imvdb_metadata_found": 0,
                "results": [],
            }

        results = []
        successful = 0
        failed = 0
        already_indexed = 0
        artists_created = 0
        videos_created = 0
        downloads_created = 0
        imvdb_metadata_found = 0
        thumbnails_downloaded = 0

        for i, file_path in enumerate(video_files, 1):
            logger.info(f"Processing file {i}/{len(video_files)}: {file_path.name}")

            result = self.index_single_file(file_path, fetch_metadata)
            results.append(result)

            if result["success"]:
                if result["already_indexed"]:
                    already_indexed += 1
                else:
                    successful += 1

                if result["artist_created"]:
                    artists_created += 1
                if result["video_created"]:
                    videos_created += 1
                if result["download_created"]:
                    downloads_created += 1
                if result["imvdb_metadata_found"]:
                    imvdb_metadata_found += 1
                if result["thumbnail_downloaded"]:
                    thumbnails_downloaded += 1
            else:
                failed += 1

            # Log progress every 100 files
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(video_files)} files processed")

        summary = {
            "total_files": len(video_files),
            "processed": len(results),
            "successful": successful,
            "failed": failed,
            "already_indexed": already_indexed,
            "artists_created": artists_created,
            "videos_created": videos_created,
            "downloads_created": downloads_created,
            "imvdb_metadata_found": imvdb_metadata_found,
            "thumbnails_downloaded": thumbnails_downloaded,
            "results": results,
        }

        logger.info(
            f"Indexing complete: {successful} successful, {failed} failed, {already_indexed} already indexed"
        )
        logger.info(
            f"Created: {artists_created} artists, {videos_created} videos, {downloads_created} downloads"
        )
        logger.info(f"IMVDb metadata found for {imvdb_metadata_found} videos")
        logger.info(f"Downloaded {thumbnails_downloaded} thumbnails")

        return summary

    def get_indexing_stats(self) -> Dict:
        """
        Get current indexing statistics - OPTIMIZED

        Returns:
            Dictionary with indexing statistics
        """
        try:
            with get_db() as session:
                # Use optimized query if available
                try:
                    from src.database.performance_optimizations import (
                        DatabasePerformanceOptimizer,
                    )

                    optimizer = DatabasePerformanceOptimizer()
                    return optimizer.optimize_video_indexing_stats(session)
                except ImportError:
                    logger.warning(
                        "Performance optimizer not available, using fallback queries"
                    )

                    # Fallback to original individual queries
                    total_artists = session.query(Artist).count()
                    total_videos = session.query(Video).count()
                    total_downloads = session.query(Download).count()

                    # Count videos with IMVDb metadata
                    videos_with_imvdb = (
                        session.query(Video).filter(Video.imvdb_id.isnot(None)).count()
                    )

                    # Count downloaded videos
                    downloaded_videos = (
                        session.query(Video)
                        .filter(Video.status == VideoStatus.DOWNLOADED)
                        .count()
                    )

                    # Count videos with local files
                    videos_with_files = (
                        session.query(Download)
                        .filter(
                            Download.file_path.isnot(None),
                            Download.status == "completed",
                        )
                        .count()
                    )

                    return {
                        "total_artists": total_artists,
                        "total_videos": total_videos,
                        "total_downloads": total_downloads,
                        "videos_with_imvdb": videos_with_imvdb,
                        "downloaded_videos": downloaded_videos,
                        "videos_with_files": videos_with_files,
                        "imvdb_coverage": (
                            round((videos_with_imvdb / total_videos * 100), 2)
                            if total_videos > 0
                            else 0
                        ),
                    }

        except Exception as e:
            logger.error(f"Failed to get indexing stats: {e}")
            return {"error": str(e)}


# Convenience instance
video_indexing_service = VideoIndexingService()
