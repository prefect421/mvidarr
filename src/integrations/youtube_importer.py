"""
YouTube Music Video Importer - Phase 3 Week 29
Consumer-focused YouTube playlist and music video import functionality
"""

import asyncio
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import aiofiles
import yt_dlp

from src.database.async_connection import get_async_session
from src.database.models import Artist, Video
from src.jobs.base_task import BaseTask
from src.services.enhanced_artist_discovery_service import get_enhanced_artist_discovery
from src.services.music_video_detector import get_music_video_detector
from src.services.redis_service import get_redis_client
from src.services.youtube_service import get_youtube_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.youtube_importer")


class ImportType(Enum):
    """Types of YouTube imports"""

    PLAYLIST = "playlist"
    CHANNEL = "channel"
    SINGLE_VIDEO = "single_video"
    SEARCH_RESULTS = "search_results"


class ImportStatus(Enum):
    """Import job status"""

    PENDING = "pending"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoQuality(Enum):
    """Preferred video quality for downloads"""

    BEST = "best"
    HIGH = "720p"
    MEDIUM = "480p"
    LOW = "360p"
    AUDIO_ONLY = "audio_only"


class ImportedVideo:
    """Represents an imported YouTube video"""

    def __init__(self):
        self.youtube_id: str = ""
        self.title: str = ""
        self.artist: str = ""
        self.duration: int = 0
        self.view_count: int = 0
        self.upload_date: Optional[datetime] = None
        self.description: str = ""
        self.thumbnail_url: str = ""
        self.channel_name: str = ""
        self.local_path: Optional[str] = None
        self.file_size: int = 0
        self.quality: str = ""
        self.is_music_video: bool = False
        self.music_video_confidence: str = ""
        self.import_timestamp: datetime = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "youtube_id": self.youtube_id,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "view_count": self.view_count,
            "upload_date": self.upload_date.isoformat() if self.upload_date else None,
            "description": self.description,
            "thumbnail_url": self.thumbnail_url,
            "channel_name": self.channel_name,
            "local_path": self.local_path,
            "file_size": self.file_size,
            "quality": self.quality,
            "is_music_video": self.is_music_video,
            "music_video_confidence": self.music_video_confidence,
            "import_timestamp": self.import_timestamp.isoformat(),
        }


class ImportJob:
    """YouTube import job tracking"""

    def __init__(self, job_id: str):
        self.job_id: str = job_id
        self.import_type: ImportType = ImportType.SINGLE_VIDEO
        self.source_url: str = ""
        self.destination_directory: str = ""
        self.status: ImportStatus = ImportStatus.PENDING
        self.progress_percent: float = 0.0
        self.videos_found: int = 0
        self.videos_processed: int = 0
        self.videos_downloaded: int = 0
        self.music_videos_detected: int = 0
        self.total_size_bytes: int = 0
        self.quality_preference: VideoQuality = VideoQuality.HIGH
        self.filter_music_only: bool = True
        self.created_at: datetime = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.imported_videos: List[ImportedVideo] = []
        self.current_video: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "import_type": self.import_type.value,
            "source_url": self.source_url,
            "destination_directory": self.destination_directory,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "videos_found": self.videos_found,
            "videos_processed": self.videos_processed,
            "videos_downloaded": self.videos_downloaded,
            "music_videos_detected": self.music_videos_detected,
            "total_size_bytes": self.total_size_bytes,
            "quality_preference": self.quality_preference.value,
            "filter_music_only": self.filter_music_only,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
            "current_video": self.current_video,
            "imported_videos": [v.to_dict() for v in self.imported_videos],
            "duration_seconds": self._get_duration_seconds(),
        }

    def _get_duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None


class YouTubeImporter:
    """Consumer-focused YouTube music video importer"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.youtube_service = None
        self.music_video_detector = None
        self.artist_discovery = None
        self.active_jobs: Dict[str, ImportJob] = {}

        # Consumer-friendly settings
        self.default_download_directory = "/data/musicvideos/YouTube Imports"
        self.max_concurrent_downloads = 2
        self.max_playlist_size = 500  # Reasonable limit for consumer use
        self.download_timeout = 300  # 5 minutes per video

        # yt-dlp configuration for consumer use
        self.ytdl_opts = {
            "format": "best[height<=720]/best",  # Default to 720p or best available
            "writeinfojson": True,
            "writedescription": False,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "ignoreerrors": True,
            "no_warnings": True,
            "extractaudio": False,
            "audioformat": "mp3",
            "audioquality": "192",
            "embed_subs": False,
            "writesubtitles": False,
            "allsubtitles": False,
        }

        # Music video detection patterns
        self.music_keywords = [
            "official music video",
            "official video",
            "music video",
            "mv",
            "official audio",
            "lyrics",
            "lyric video",
            "acoustic",
            "live performance",
            "live",
            "concert",
            "unplugged",
        ]

        # Channel patterns that typically contain music videos
        self.music_channel_patterns = [
            r".*official.*",
            r".*records.*",
            r".*music.*",
            r".*entertainment.*",
            r".*vevo.*",
            r".*sony.*",
            r".*universal.*",
            r".*warner.*",
        ]

    async def initialize(self):
        """Initialize YouTube importer"""
        try:
            self.redis_client = await get_redis_client()
            self.youtube_service = await get_youtube_service()
            self.music_video_detector = await get_music_video_detector()
            self.artist_discovery = await get_enhanced_artist_discovery()

            # Create default download directory
            os.makedirs(self.default_download_directory, exist_ok=True)

            logger.info("YouTube importer initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize YouTube importer: {e}")
            raise

    async def create_import_job(
        self,
        source_url: str,
        destination_directory: Optional[str] = None,
        quality: VideoQuality = VideoQuality.HIGH,
        filter_music_only: bool = True,
        options: Optional[Dict] = None,
    ) -> ImportJob:
        """Create a new YouTube import job"""
        try:
            # Generate job ID
            job_id = f"yt_import_{int(time.time())}_{hashlib.md5(source_url.encode()).hexdigest()[:8]}"

            # Determine import type from URL
            import_type = self._determine_import_type(source_url)

            # Create import job
            job = ImportJob(job_id)
            job.import_type = import_type
            job.source_url = source_url
            job.destination_directory = (
                destination_directory or self.default_download_directory
            )
            job.quality_preference = quality
            job.filter_music_only = filter_music_only

            # Apply options
            if options:
                job.quality_preference = VideoQuality(
                    options.get("quality", quality.value)
                )
                job.filter_music_only = options.get(
                    "filter_music_only", filter_music_only
                )

            # Store job
            self.active_jobs[job_id] = job
            await self._save_job_status(job)

            logger.info(
                f"Created YouTube import job {job_id} for {import_type.value}: {source_url}"
            )

            return job

        except Exception as e:
            logger.error(f"Failed to create import job: {e}")
            raise

    async def start_import_job(
        self, job_id: str, progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Start executing an import job"""
        try:
            if job_id not in self.active_jobs:
                raise ValueError(f"Import job {job_id} not found")

            job = self.active_jobs[job_id]

            if job.status != ImportStatus.PENDING:
                raise ValueError(f"Job {job_id} is not in pending status")

            logger.info(f"Starting YouTube import job {job_id}")

            # Update job status
            job.status = ImportStatus.ANALYZING
            job.started_at = datetime.now()
            await self._save_job_status(job)

            # Execute import based on type
            if job.import_type == ImportType.PLAYLIST:
                result = await self._import_playlist(job, progress_callback)
            elif job.import_type == ImportType.CHANNEL:
                result = await self._import_channel(job, progress_callback)
            elif job.import_type == ImportType.SINGLE_VIDEO:
                result = await self._import_single_video(job, progress_callback)
            elif job.import_type == ImportType.SEARCH_RESULTS:
                result = await self._import_search_results(job, progress_callback)
            else:
                raise ValueError(f"Unsupported import type: {job.import_type}")

            # Update final status
            if result["success"]:
                job.status = ImportStatus.COMPLETED
                job.completed_at = datetime.now()
                job.progress_percent = 100.0
            else:
                job.status = ImportStatus.FAILED
                job.error_message = result.get("error", "Unknown error")

            await self._save_job_status(job)

            logger.info(
                f"YouTube import job {job_id} {'completed' if result['success'] else 'failed'}: "
                f"{job.videos_downloaded} videos downloaded, {job.music_videos_detected} music videos detected"
            )

            return {
                "job_id": job_id,
                "success": result["success"],
                "status": job.status.value,
                "videos_downloaded": job.videos_downloaded,
                "music_videos_detected": job.music_videos_detected,
                "total_size_mb": job.total_size_bytes / (1024 * 1024),
                "error": job.error_message,
            }

        except Exception as e:
            # Update job with error
            if job_id in self.active_jobs:
                job = self.active_jobs[job_id]
                job.status = ImportStatus.FAILED
                job.error_message = str(e)
                await self._save_job_status(job)

            logger.error(f"Failed to start import job {job_id}: {e}")
            return {"job_id": job_id, "success": False, "error": str(e)}

    async def _import_playlist(
        self, job: ImportJob, progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Import videos from a YouTube playlist"""
        try:
            logger.info(f"Importing playlist: {job.source_url}")

            # Get playlist information using existing YouTube service
            playlist_info = await self.youtube_service.get_playlist_info(job.source_url)

            if not playlist_info:
                return {
                    "success": False,
                    "error": "Failed to fetch playlist information",
                }

            # Get video list from playlist
            video_list = await self.youtube_service.get_playlist_videos(job.source_url)

            if not video_list:
                return {"success": False, "error": "No videos found in playlist"}

            # Limit playlist size for consumer use
            if len(video_list) > self.max_playlist_size:
                video_list = video_list[: self.max_playlist_size]
                logger.warning(
                    f"Playlist truncated to {self.max_playlist_size} videos for consumer limits"
                )

            job.videos_found = len(video_list)
            job.status = ImportStatus.DOWNLOADING
            await self._save_job_status(job)

            # Process each video
            downloaded_count = 0

            for i, video_info in enumerate(video_list):
                if job.status == ImportStatus.CANCELLED:
                    break

                try:
                    # Update current video
                    job.current_video = video_info.get("title", "Unknown")

                    # Check if it looks like a music video (if filtering enabled)
                    if job.filter_music_only:
                        is_likely_music = await self._is_likely_music_video(video_info)
                        if not is_likely_music:
                            logger.debug(
                                f"Skipping non-music video: {video_info.get('title', 'Unknown')}"
                            )
                            continue

                    # Download video
                    imported_video = await self._download_video(
                        video_info, job.destination_directory, job.quality_preference
                    )

                    if imported_video:
                        # Detect if it's actually a music video
                        if imported_video.local_path:
                            detection_result = (
                                await self.music_video_detector.detect_music_video(
                                    imported_video.local_path
                                )
                            )
                            imported_video.is_music_video = (
                                detection_result.is_music_video
                            )
                            imported_video.music_video_confidence = (
                                detection_result.confidence.value
                            )

                            if detection_result.is_music_video:
                                job.music_videos_detected += 1

                        job.imported_videos.append(imported_video)
                        job.total_size_bytes += imported_video.file_size
                        downloaded_count += 1

                    job.videos_processed += 1
                    job.videos_downloaded = downloaded_count
                    job.progress_percent = (
                        job.videos_processed / job.videos_found
                    ) * 100

                    if progress_callback:
                        await progress_callback(
                            job.job_id, job.progress_percent, job.current_video
                        )

                    await self._save_job_status(job)

                    # Consumer-friendly rate limiting
                    await asyncio.sleep(2.0)

                except Exception as e:
                    logger.warning(
                        f"Failed to import video {video_info.get('title', 'Unknown')}: {e}"
                    )
                    continue

            return {"success": True, "downloaded_videos": downloaded_count}

        except Exception as e:
            logger.error(f"Playlist import failed: {e}")
            return {"success": False, "error": str(e)}

    async def _import_single_video(
        self, job: ImportJob, progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Import a single YouTube video"""
        try:
            logger.info(f"Importing single video: {job.source_url}")

            job.videos_found = 1
            job.status = ImportStatus.DOWNLOADING
            await self._save_job_status(job)

            # Extract video info
            video_info = await self._extract_video_info(job.source_url)

            if not video_info:
                return {
                    "success": False,
                    "error": "Failed to extract video information",
                }

            job.current_video = video_info.get("title", "Unknown")

            # Download video
            imported_video = await self._download_video(
                video_info, job.destination_directory, job.quality_preference
            )

            if imported_video:
                # Detect if it's a music video
                if imported_video.local_path:
                    detection_result = (
                        await self.music_video_detector.detect_music_video(
                            imported_video.local_path
                        )
                    )
                    imported_video.is_music_video = detection_result.is_music_video
                    imported_video.music_video_confidence = (
                        detection_result.confidence.value
                    )

                    if detection_result.is_music_video:
                        job.music_videos_detected = 1

                job.imported_videos.append(imported_video)
                job.total_size_bytes = imported_video.file_size
                job.videos_processed = 1
                job.videos_downloaded = 1
                job.progress_percent = 100.0

                if progress_callback:
                    await progress_callback(job.job_id, 100.0, job.current_video)

                await self._save_job_status(job)

                return {"success": True, "downloaded_videos": 1}
            else:
                return {"success": False, "error": "Failed to download video"}

        except Exception as e:
            logger.error(f"Single video import failed: {e}")
            return {"success": False, "error": str(e)}

    async def _import_channel(
        self, job: ImportJob, progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Import videos from a YouTube channel"""
        try:
            logger.info(f"Importing channel: {job.source_url}")

            # This would use YouTube API to get channel videos
            # For consumer use, limit to recent uploads (last 50 videos)
            channel_videos = await self._get_channel_videos(job.source_url, limit=50)

            if not channel_videos:
                return {"success": False, "error": "No videos found in channel"}

            job.videos_found = len(channel_videos)
            job.status = ImportStatus.DOWNLOADING
            await self._save_job_status(job)

            # Process videos similar to playlist
            downloaded_count = 0

            for i, video_info in enumerate(channel_videos):
                if job.status == ImportStatus.CANCELLED:
                    break

                try:
                    job.current_video = video_info.get("title", "Unknown")

                    # Apply music filter
                    if job.filter_music_only:
                        is_likely_music = await self._is_likely_music_video(video_info)
                        if not is_likely_music:
                            continue

                    # Download video
                    imported_video = await self._download_video(
                        video_info, job.destination_directory, job.quality_preference
                    )

                    if imported_video:
                        # Music video detection
                        if imported_video.local_path:
                            detection_result = (
                                await self.music_video_detector.detect_music_video(
                                    imported_video.local_path
                                )
                            )
                            imported_video.is_music_video = (
                                detection_result.is_music_video
                            )
                            imported_video.music_video_confidence = (
                                detection_result.confidence.value
                            )

                            if detection_result.is_music_video:
                                job.music_videos_detected += 1

                        job.imported_videos.append(imported_video)
                        job.total_size_bytes += imported_video.file_size
                        downloaded_count += 1

                    job.videos_processed += 1
                    job.videos_downloaded = downloaded_count
                    job.progress_percent = (
                        job.videos_processed / job.videos_found
                    ) * 100

                    if progress_callback:
                        await progress_callback(
                            job.job_id, job.progress_percent, job.current_video
                        )

                    await self._save_job_status(job)
                    await asyncio.sleep(2.0)  # Rate limiting

                except Exception as e:
                    logger.warning(
                        f"Failed to import channel video {video_info.get('title', 'Unknown')}: {e}"
                    )
                    continue

            return {"success": True, "downloaded_videos": downloaded_count}

        except Exception as e:
            logger.error(f"Channel import failed: {e}")
            return {"success": False, "error": str(e)}

    async def _import_search_results(
        self, job: ImportJob, progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Import videos from YouTube search results"""
        try:
            logger.info(f"Importing search results: {job.source_url}")

            # Extract search query from URL or use as direct query
            search_query = self._extract_search_query(job.source_url)

            # Search for videos using existing YouTube service
            search_results = await self.youtube_service.search_videos(
                search_query, max_results=20
            )

            if not search_results:
                return {"success": False, "error": "No search results found"}

            # Filter for likely music videos if enabled
            if job.filter_music_only:
                filtered_results = []
                for result in search_results:
                    if await self._is_likely_music_video(result):
                        filtered_results.append(result)
                search_results = filtered_results

            job.videos_found = len(search_results)
            job.status = ImportStatus.DOWNLOADING
            await self._save_job_status(job)

            # Process search results
            downloaded_count = 0

            for i, video_info in enumerate(search_results):
                if job.status == ImportStatus.CANCELLED:
                    break

                try:
                    job.current_video = video_info.get("title", "Unknown")

                    # Download video
                    imported_video = await self._download_video(
                        video_info, job.destination_directory, job.quality_preference
                    )

                    if imported_video:
                        # Music video detection
                        if imported_video.local_path:
                            detection_result = (
                                await self.music_video_detector.detect_music_video(
                                    imported_video.local_path
                                )
                            )
                            imported_video.is_music_video = (
                                detection_result.is_music_video
                            )
                            imported_video.music_video_confidence = (
                                detection_result.confidence.value
                            )

                            if detection_result.is_music_video:
                                job.music_videos_detected += 1

                        job.imported_videos.append(imported_video)
                        job.total_size_bytes += imported_video.file_size
                        downloaded_count += 1

                    job.videos_processed += 1
                    job.videos_downloaded = downloaded_count
                    job.progress_percent = (
                        job.videos_processed / job.videos_found
                    ) * 100

                    if progress_callback:
                        await progress_callback(
                            job.job_id, job.progress_percent, job.current_video
                        )

                    await self._save_job_status(job)
                    await asyncio.sleep(2.0)  # Rate limiting

                except Exception as e:
                    logger.warning(
                        f"Failed to import search result {video_info.get('title', 'Unknown')}: {e}"
                    )
                    continue

            return {"success": True, "downloaded_videos": downloaded_count}

        except Exception as e:
            logger.error(f"Search results import failed: {e}")
            return {"success": False, "error": str(e)}

    async def _download_video(
        self, video_info: Dict, destination_dir: str, quality: VideoQuality
    ) -> Optional[ImportedVideo]:
        """Download a single video using yt-dlp"""
        try:
            # Create ImportedVideo object
            imported_video = ImportedVideo()
            imported_video.youtube_id = video_info.get("id", "")
            imported_video.title = video_info.get("title", "Unknown")
            imported_video.channel_name = video_info.get("channel", "Unknown Channel")
            imported_video.duration = video_info.get("duration", 0)
            imported_video.view_count = video_info.get("view_count", 0)
            imported_video.description = video_info.get("description", "")
            imported_video.thumbnail_url = video_info.get("thumbnail", "")

            if video_info.get("upload_date"):
                try:
                    imported_video.upload_date = datetime.strptime(
                        video_info["upload_date"], "%Y%m%d"
                    )
                except:
                    pass

            # Configure yt-dlp options based on quality preference
            ytdl_opts = self.ytdl_opts.copy()

            if quality == VideoQuality.BEST:
                ytdl_opts["format"] = "best"
            elif quality == VideoQuality.HIGH:
                ytdl_opts["format"] = "best[height<=720]/best"
            elif quality == VideoQuality.MEDIUM:
                ytdl_opts["format"] = "best[height<=480]/best"
            elif quality == VideoQuality.LOW:
                ytdl_opts["format"] = "best[height<=360]/best"
            elif quality == VideoQuality.AUDIO_ONLY:
                ytdl_opts["format"] = "bestaudio/best"
                ytdl_opts["extractaudio"] = True

            # Set output directory and filename template
            safe_title = re.sub(r'[<>:"/\\|?*]', "", imported_video.title)[:100]
            safe_channel = re.sub(r'[<>:"/\\|?*]', "", imported_video.channel_name)[:50]

            ytdl_opts["outtmpl"] = os.path.join(
                destination_dir, f"{safe_channel} - {safe_title}.%(ext)s"
            )

            # Download video
            video_url = f"https://www.youtube.com/watch?v={imported_video.youtube_id}"

            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                try:
                    # Download the video
                    ydl.download([video_url])

                    # Find the downloaded file
                    downloaded_file = None
                    for file in os.listdir(destination_dir):
                        if imported_video.youtube_id in file or safe_title in file:
                            downloaded_file = os.path.join(destination_dir, file)
                            break

                    if downloaded_file and os.path.exists(downloaded_file):
                        imported_video.local_path = downloaded_file
                        imported_video.file_size = os.path.getsize(downloaded_file)
                        imported_video.quality = quality.value

                        logger.info(
                            f"Downloaded: {imported_video.title} ({imported_video.file_size / (1024*1024):.1f} MB)"
                        )

                        return imported_video

                except Exception as e:
                    logger.error(f"yt-dlp download failed for {video_url}: {e}")
                    return None

            return None

        except Exception as e:
            logger.error(
                f"Failed to download video {video_info.get('title', 'Unknown')}: {e}"
            )
            return None

    async def _is_likely_music_video(self, video_info: Dict) -> bool:
        """Determine if a video is likely a music video based on metadata"""
        try:
            title = video_info.get("title", "").lower()
            description = video_info.get("description", "").lower()
            channel = video_info.get("channel", "").lower()

            # Check for music keywords in title
            for keyword in self.music_keywords:
                if keyword in title:
                    return True

            # Check for music keywords in description
            for keyword in self.music_keywords[:5]:  # Check only strong indicators
                if keyword in description[:200]:  # First 200 chars of description
                    return True

            # Check if channel looks like a music channel
            for pattern in self.music_channel_patterns:
                if re.match(pattern, channel):
                    return True

            # Check duration (music videos typically 2-8 minutes)
            duration = video_info.get("duration", 0)
            if 120 <= duration <= 480:  # 2-8 minutes
                # Additional checks for songs in this duration range
                if any(keyword in title for keyword in ["ft.", "feat.", "vs.", "x "]):
                    return True

            return False

        except Exception as e:
            logger.warning(f"Failed to analyze video for music content: {e}")
            return True  # When in doubt, include it

    def _determine_import_type(self, url: str) -> ImportType:
        """Determine import type from URL"""
        if "playlist" in url or "list=" in url:
            return ImportType.PLAYLIST
        elif "/channel/" in url or "/c/" in url or "/user/" in url:
            return ImportType.CHANNEL
        elif "/watch" in url or "youtu.be/" in url:
            return ImportType.SINGLE_VIDEO
        else:
            return ImportType.SEARCH_RESULTS

    def _extract_search_query(self, url: str) -> str:
        """Extract search query from URL or return as direct query"""
        if "search_query=" in url:
            import urllib.parse

            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            return parsed.get("search_query", [""])[0]
        else:
            return url  # Treat as direct search query

    async def _extract_video_info(self, video_url: str) -> Optional[Dict]:
        """Extract video information without downloading"""
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(video_url, download=False)
                return info
        except Exception as e:
            logger.error(f"Failed to extract video info for {video_url}: {e}")
            return None

    async def _get_channel_videos(
        self, channel_url: str, limit: int = 50
    ) -> List[Dict]:
        """Get recent videos from a YouTube channel"""
        try:
            # This would use the existing YouTube service to get channel videos
            # For now, return empty list (would be implemented with actual API calls)
            return []

        except Exception as e:
            logger.error(f"Failed to get channel videos: {e}")
            return []

    async def get_import_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an import job"""
        try:
            if job_id in self.active_jobs:
                return self.active_jobs[job_id].to_dict()

            # Try to load from Redis
            cached_job = await self.redis_client.get(f"yt_import_job:{job_id}")
            if cached_job:
                return json.loads(cached_job)

            return None

        except Exception as e:
            logger.error(f"Failed to get import status for {job_id}: {e}")
            return None

    async def list_import_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent import jobs"""
        try:
            jobs = []

            # Get active jobs
            for job in self.active_jobs.values():
                jobs.append(job.to_dict())

            # Get cached jobs from Redis
            pattern = "yt_import_job:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys[:limit]:
                try:
                    job_data = await self.redis_client.get(key)
                    if job_data:
                        job_dict = json.loads(job_data)
                        # Avoid duplicates with active jobs
                        if not any(j["job_id"] == job_dict["job_id"] for j in jobs):
                            jobs.append(job_dict)
                except:
                    continue

            # Sort by creation time, most recent first
            jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            return jobs[:limit]

        except Exception as e:
            logger.error(f"Failed to list import jobs: {e}")
            return []

    async def cancel_import_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a running import job"""
        try:
            if job_id not in self.active_jobs:
                return {"success": False, "error": "Job not found"}

            job = self.active_jobs[job_id]

            if job.status not in [
                ImportStatus.PENDING,
                ImportStatus.ANALYZING,
                ImportStatus.DOWNLOADING,
            ]:
                return {"success": False, "error": "Job cannot be cancelled"}

            job.status = ImportStatus.CANCELLED
            job.completed_at = datetime.now()
            await self._save_job_status(job)

            logger.info(f"Cancelled YouTube import job {job_id}")

            return {"success": True, "job_id": job_id, "status": "cancelled"}

        except Exception as e:
            logger.error(f"Failed to cancel import job {job_id}: {e}")
            return {"success": False, "error": str(e)}

    async def _save_job_status(self, job: ImportJob):
        """Save job status to Redis"""
        try:
            cache_key = f"yt_import_job:{job.job_id}"
            await self.redis_client.setex(
                cache_key, 86400 * 7, json.dumps(job.to_dict())
            )

        except Exception as e:
            logger.error(f"Failed to save import job status for {job.job_id}: {e}")


# Global service instance
_youtube_importer = None


async def get_youtube_importer(config: Optional[Dict] = None) -> YouTubeImporter:
    """Get global YouTube importer instance"""
    global _youtube_importer

    if _youtube_importer is None:
        _youtube_importer = YouTubeImporter(config)
        await _youtube_importer.initialize()

    return _youtube_importer
