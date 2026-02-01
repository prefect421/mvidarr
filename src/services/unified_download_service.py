"""
Unified Download Service - Enterprise Architecture
Replaces the fragmented download system with a single, robust solution
"""

import json
import os
import shutil
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("mvidarr.unified_download")


class DownloadStatus(Enum):
    """Standardized download status enum"""

    PENDING = "pending"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AntiDetectionLevel(Enum):
    """Anti-detection strategy levels"""

    MINIMAL = "minimal"  # Basic headers and rate limiting
    MODERATE = "moderate"  # User agent rotation, cookies
    AGGRESSIVE = "aggressive"  # Proxies, session rotation, delays
    STEALTH = "stealth"  # Maximum evasion techniques


@dataclass
class DownloadContext:
    """Immutable download context configuration"""

    video_id: int
    url: str
    title: str
    artist: str
    quality: str
    output_path: str
    cookies_path: Optional[str] = None
    user_agent: Optional[str] = None
    proxy: Optional[str] = None
    rate_limit: Optional[str] = None
    anti_detection: AntiDetectionLevel = AntiDetectionLevel.MODERATE


@dataclass
class DownloadResult:
    """Immutable download result"""

    success: bool
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None
    metadata: Optional[Dict] = None


class YtDlpManager:
    """Centralized yt-dlp version and configuration management"""

    def __init__(self):
        self.executable_paths = [
            "/root/.local/bin/yt-dlp",  # pipx installed (latest)
            "/usr/local/bin/yt-dlp",  # system installed
            "yt-dlp",  # PATH fallback
        ]
        self.current_executable = self._find_best_executable()
        self.last_version_check = None
        self.version_check_interval = timedelta(hours=6)

    def _find_best_executable(self) -> str:
        """Find the best available yt-dlp executable"""
        for path in self.executable_paths:
            if path.startswith("/") and os.path.exists(path):
                return path
            elif not path.startswith("/") and shutil.which(path):
                return shutil.which(path)

        raise RuntimeError("yt-dlp executable not found")

    def get_version(self) -> str:
        """Get current yt-dlp version"""
        try:
            result = subprocess.run(
                [self.current_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    def needs_update(self) -> bool:
        """Check if yt-dlp needs updating"""
        if not self.last_version_check:
            return True

        return datetime.now() - self.last_version_check > self.version_check_interval

    def update_if_needed(self) -> bool:
        """Update yt-dlp if necessary"""
        if not self.needs_update():
            return True

        try:
            # Try to update via pipx first (preferred)
            if "/root/.local/bin/yt-dlp" in self.executable_paths:
                result = subprocess.run(
                    ["pipx", "upgrade", "yt-dlp"], capture_output=True, timeout=300
                )
                if result.returncode == 0:
                    self.last_version_check = datetime.now()
                    logger.info("yt-dlp updated successfully via pipx")
                    return True

            # Fallback to self-update
            result = subprocess.run(
                [self.current_executable, "-U"], capture_output=True, timeout=300
            )
            success = result.returncode == 0
            if success:
                self.last_version_check = datetime.now()
                logger.info("yt-dlp updated successfully")

            return success

        except Exception as e:
            logger.error(f"Failed to update yt-dlp: {e}")
            return False


class AntiDetectionManager:
    """Advanced anti-bot detection countermeasures"""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(self):
        self.current_ua_index = 0
        self.detection_count = 0
        self.last_detection = None

    def get_anti_detection_args(
        self, level: AntiDetectionLevel, context: DownloadContext
    ) -> List[str]:
        """Get yt-dlp arguments for anti-detection"""
        args = []

        # Basic anti-detection (always applied)
        args.extend(
            [
                "--no-check-certificate",
                "--prefer-insecure",
                "--socket-timeout",
                "30",
                "--retries",
                "3",
                "--fragment-retries",
                "3",
            ]
        )

        if level in [
            AntiDetectionLevel.MODERATE,
            AntiDetectionLevel.AGGRESSIVE,
            AntiDetectionLevel.STEALTH,
        ]:
            # User agent rotation
            ua = context.user_agent or self._get_rotating_user_agent()
            args.extend(["--add-header", f"User-Agent:{ua}"])

            # Cookie handling
            if context.cookies_path and os.path.exists(context.cookies_path):
                args.extend(["--cookies", context.cookies_path])

            # Rate limiting
            args.extend(
                [
                    "--sleep-requests",
                    "1",
                    "--sleep-interval",
                    "2",
                    "--max-sleep-interval",
                    "5",
                ]
            )

        if level in [AntiDetectionLevel.AGGRESSIVE, AntiDetectionLevel.STEALTH]:
            # More aggressive evasion
            args.extend(["--throttled-rate", "100K", "--sleep-subtitles", "1"])

            # Use different extraction strategies
            args.extend(["--extractor-args", "youtube:player_client=android,web"])

        if level == AntiDetectionLevel.STEALTH:
            # Maximum evasion
            args.extend(
                [
                    "--extractor-args",
                    "youtube:player_client=tv_embedded,android_creator,android_vr,web",
                    "--sleep-requests",
                    "3",
                    "--sleep-interval",
                    "5",
                    "--max-sleep-interval",
                    "15",
                ]
            )

        return args

    def _get_rotating_user_agent(self) -> str:
        """Get a rotating user agent"""
        ua = self.USER_AGENTS[self.current_ua_index]
        self.current_ua_index = (self.current_ua_index + 1) % len(self.USER_AGENTS)
        return ua

    def handle_detection_error(self, error: str) -> AntiDetectionLevel:
        """Determine escalated anti-detection level based on error"""
        self.detection_count += 1
        self.last_detection = datetime.now()

        if "Signature extraction failed" in error:
            return AntiDetectionLevel.AGGRESSIVE
        elif "bot" in error.lower():
            return AntiDetectionLevel.STEALTH
        elif "429" in error or "rate" in error.lower():
            return AntiDetectionLevel.AGGRESSIVE
        else:
            return AntiDetectionLevel.MODERATE


class DownloadStrategy(ABC):
    """Abstract base class for download strategies"""

    @abstractmethod
    def download(self, context: DownloadContext) -> DownloadResult:
        """Execute download with given context"""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this strategy can handle the URL"""
        pass


class YouTubeDownloadStrategy(DownloadStrategy):
    """Specialized YouTube download strategy with advanced anti-detection"""

    def __init__(
        self, ytdlp_manager: YtDlpManager, anti_detection: AntiDetectionManager
    ):
        self.ytdlp_manager = ytdlp_manager
        self.anti_detection = anti_detection

    def can_handle(self, url: str) -> bool:
        """Check if this is a YouTube URL"""
        return any(domain in url.lower() for domain in ["youtube.com", "youtu.be"])

    def download(self, context: DownloadContext) -> DownloadResult:
        """Execute YouTube download with full anti-detection"""
        start_time = time.time()

        # Ensure yt-dlp is up to date
        if not self.ytdlp_manager.update_if_needed():
            logger.warning("Failed to update yt-dlp, proceeding with current version")

        # Start with moderate anti-detection
        current_level = context.anti_detection
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                result = self._attempt_download(context, current_level)
                if result.success:
                    result.duration = time.time() - start_time
                    return result

                # Escalate anti-detection on failure
                if attempt < max_attempts - 1:
                    current_level = self.anti_detection.handle_detection_error(
                        result.error_message
                    )
                    logger.info(
                        f"Download attempt {attempt + 1} failed, escalating to {current_level}"
                    )
                    time.sleep(2**attempt)  # Exponential backoff

            except Exception as e:
                logger.error(f"Download attempt {attempt + 1} exception: {e}")
                if attempt < max_attempts - 1:
                    current_level = AntiDetectionLevel.AGGRESSIVE
                    time.sleep(2**attempt)

        return DownloadResult(
            success=False,
            error_message=f"All {max_attempts} download attempts failed",
            duration=time.time() - start_time,
        )

    def _attempt_download(
        self, context: DownloadContext, level: AntiDetectionLevel
    ) -> DownloadResult:
        """Attempt single download with specified anti-detection level"""

        # Build command with anti-detection arguments
        cmd = [self.ytdlp_manager.current_executable]

        # Output template
        output_template = os.path.join(context.output_path, f"{context.title}.%(ext)s")
        cmd.extend(["-o", output_template])

        # Quality format
        cmd.extend(["-f", self._get_quality_format(context.quality)])

        # Metadata options
        cmd.extend(["--write-info-json", "--embed-metadata", "--add-metadata"])

        # Anti-detection arguments
        cmd.extend(self.anti_detection.get_anti_detection_args(level, context))

        # URL
        cmd.append(context.url)

        logger.info(f"Executing download: {context.title} with {level} anti-detection")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True,
            )

            output_lines = []
            for line in iter(process.stdout.readline, ""):
                output_lines.append(line.strip())

                # Log important information
                if any(
                    keyword in line
                    for keyword in ["Selected format:", "ERROR:", "WARNING:"]
                ):
                    logger.info(f"yt-dlp: {line.strip()}")

            process.wait()

            if process.returncode == 0:
                # Find downloaded file
                downloaded_file = self._find_downloaded_file(
                    output_template, output_lines
                )
                if downloaded_file and os.path.exists(downloaded_file):
                    file_size = os.path.getsize(downloaded_file)
                    return DownloadResult(
                        success=True,
                        file_path=downloaded_file,
                        file_size=file_size,
                        metadata=self._extract_metadata(downloaded_file),
                    )

            # Extract error message
            error_output = "\n".join(output_lines)
            error_message = self._extract_error_message(error_output)

            return DownloadResult(success=False, error_message=error_message)

        except subprocess.TimeoutExpired:
            return DownloadResult(success=False, error_message="Download timed out")
        except Exception as e:
            return DownloadResult(
                success=False, error_message=f"Process error: {str(e)}"
            )

    def _get_quality_format(self, quality: str) -> str:
        """Get optimized format string for YouTube downloads"""
        # If quality contains yt-dlp format selectors, use it directly (for custom format strings)
        if any(
            selector in quality
            for selector in ["bestvideo", "bestaudio", "bv", "ba", "bv*", "ba*", "+"]
        ):
            return quality

        # Simple quality presets
        if quality == "best":
            # Prioritize combined formats to avoid audio/video sync issues
            return "bv*[height<=2160]+ba/best[height<=2160]/bv+ba/best"
        elif quality.endswith("p"):
            height = quality.replace("p", "")
            return f"bv*[height<={height}]+ba/best[height<={height}]/bv+ba/best"
        else:
            return "bv*+ba/best"

    def _find_downloaded_file(
        self, template: str, output_lines: List[str]
    ) -> Optional[str]:
        """Find the actual downloaded file from template and output"""
        # Look for "Destination:" lines in output
        for line in output_lines:
            if "Destination:" in line:
                return line.split("Destination:")[1].strip()

        # Fallback: look for files matching the pattern
        base_path = os.path.dirname(template)
        if os.path.exists(base_path):
            for file in os.listdir(base_path):
                if file.startswith(os.path.splitext(os.path.basename(template))[0]):
                    return os.path.join(base_path, file)

        return None

    def _extract_error_message(self, output: str) -> str:
        """Extract meaningful error message from yt-dlp output"""
        lines = output.split("\n")
        for line in reversed(lines):
            if line.startswith("ERROR:"):
                return line.replace("ERROR:", "").strip()
        return "Unknown error occurred"

    def _extract_metadata(self, file_path: str) -> Optional[Dict]:
        """Extract metadata from downloaded file"""
        info_file = os.path.splitext(file_path)[0] + ".info.json"
        if os.path.exists(info_file):
            try:
                with open(info_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None


class UnifiedDownloadService:
    """Single, unified download service replacing all fragmented implementations"""

    def __init__(self):
        self.ytdlp_manager = YtDlpManager()
        self.anti_detection = AntiDetectionManager()

        # Register strategies
        self.strategies = [
            YouTubeDownloadStrategy(self.ytdlp_manager, self.anti_detection)
        ]

        # Thread management
        self.active_downloads: Dict[int, threading.Thread] = {}
        self.download_callbacks: Dict[int, List[Callable]] = {}

        logger.info("Unified Download Service initialized")

    def download_video(
        self,
        context: DownloadContext,
        progress_callback: Optional[Callable] = None,
        completion_callback: Optional[Callable] = None,
    ) -> int:
        """
        Initiate video download

        Returns:
            download_id: Unique identifier for tracking this download
        """
        download_id = self._generate_download_id()

        # Store callbacks
        callbacks = []
        if progress_callback:
            callbacks.append(progress_callback)
        if completion_callback:
            callbacks.append(completion_callback)
        self.download_callbacks[download_id] = callbacks

        # Start download in background thread
        thread = threading.Thread(
            target=self._execute_download, args=(download_id, context), daemon=True
        )

        self.active_downloads[download_id] = thread
        thread.start()

        logger.info(f"Started download {download_id}: {context.title}")
        return download_id

    def _execute_download(self, download_id: int, context: DownloadContext):
        """Execute download in background thread"""
        try:
            # Update database status
            self._update_database_status(context.video_id, DownloadStatus.DOWNLOADING)

            # Find appropriate strategy
            strategy = self._get_strategy(context.url)
            if not strategy:
                raise ValueError(f"No strategy available for URL: {context.url}")

            # Execute download
            result = strategy.download(context)

            # Update database with result
            if result.success:
                self._update_database_success(context.video_id, result)
                logger.info(
                    f"Download {download_id} completed successfully: {result.file_path}"
                )
            else:
                self._update_database_failure(context.video_id, result.error_message)
                logger.error(f"Download {download_id} failed: {result.error_message}")

            # Execute callbacks
            for callback in self.download_callbacks.get(download_id, []):
                try:
                    callback(download_id, result)
                except Exception as e:
                    logger.error(f"Callback error for download {download_id}: {e}")

        except Exception as e:
            logger.error(f"Download {download_id} exception: {e}")
            self._update_database_failure(context.video_id, str(e))

        finally:
            # Cleanup
            if download_id in self.active_downloads:
                del self.active_downloads[download_id]
            if download_id in self.download_callbacks:
                del self.download_callbacks[download_id]

    def _get_strategy(self, url: str) -> Optional[DownloadStrategy]:
        """Get appropriate download strategy for URL"""
        for strategy in self.strategies:
            if strategy.can_handle(url):
                return strategy
        return None

    def _generate_download_id(self) -> int:
        """Generate unique download ID"""
        import random

        return random.randint(100000, 999999)

    def _update_database_status(self, video_id: int, status: DownloadStatus):
        """Update video status in database"""
        try:
            from src.database.connection import get_db
            from src.database.models import Video

            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                if video:
                    video.status = status.value.upper()
                    session.commit()
        except Exception as e:
            logger.error(f"Database status update failed: {e}")

    def _update_database_success(self, video_id: int, result: DownloadResult):
        """Update database on successful download"""
        try:
            from datetime import datetime

            from src.database.connection import get_db
            from src.database.models import Download, Video, VideoStatus

            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                if video:
                    video.status = VideoStatus.DOWNLOADED.value
                    video.local_path = result.file_path
                    if result.file_size:
                        video.file_size = result.file_size
                    if result.metadata:
                        video.video_metadata = result.metadata

                    # Find existing Download record (created by endpoint) and update it
                    existing_download = (
                        session.query(Download)
                        .filter(
                            Download.video_id == video_id,
                            Download.status.in_(["queued", "downloading", "pending"]),
                        )
                        .order_by(Download.created_at.desc())
                        .first()
                    )

                    if existing_download:
                        # Update existing record
                        existing_download.status = "completed"
                        existing_download.file_path = result.file_path
                        existing_download.file_size = result.file_size
                        existing_download.progress = 100
                        existing_download.updated_at = datetime.utcnow()
                        logger.info(
                            f"Updated download record {existing_download.id} to completed for video {video_id}"
                        )
                    else:
                        # Create new Download record if none exists (fallback)
                        download = Download(
                            artist_id=video.artist_id,
                            video_id=video_id,
                            title=video.title,
                            original_url=video.url or video.youtube_url,
                            status="completed",
                            file_path=result.file_path,
                            file_size=result.file_size,
                            download_date=datetime.utcnow(),
                            progress=100,
                        )
                        session.add(download)
                        logger.info(
                            f"Created download history record for video {video_id}"
                        )

                    session.commit()
        except Exception as e:
            logger.error(f"Database success update failed: {e}", exc_info=True)

    def _update_database_failure(self, video_id: int, error_message: str):
        """Update database on failed download"""
        try:
            from src.database.connection import get_db
            from src.database.models import Download, Video, VideoStatus

            with get_db() as session:
                # Update video status
                video = session.query(Video).filter(Video.id == video_id).first()
                if video:
                    video.status = VideoStatus.FAILED.value

                    # Create or update Download record with error message
                    # This ensures error is persisted even if download history is cleared
                    download = (
                        session.query(Download)
                        .filter(Download.video_id == video_id)
                        .order_by(Download.download_date.desc())
                        .first()
                    )

                    if download:
                        # Update existing download record
                        download.status = "failed"
                        download.error_message = error_message
                        download.last_error = error_message
                        download.updated_at = datetime.utcnow()
                        logger.info(
                            f"Updated download {download.id} with error: {error_message}"
                        )
                    else:
                        # Create new download record to preserve error
                        download = Download(
                            artist_id=video.artist_id,
                            video_id=video_id,
                            title=video.title,
                            original_url=video.url,
                            status="failed",
                            error_message=error_message,
                            last_error=error_message,
                            download_date=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                        session.add(download)
                        logger.info(
                            f"Created download record for video {video_id} with error: {error_message}"
                        )

                    session.commit()
        except Exception as e:
            logger.error(f"Database failure update failed: {e}", exc_info=True)

    def get_active_downloads(self) -> Dict[int, str]:
        """Get currently active downloads"""
        return {
            download_id: "downloading" for download_id in self.active_downloads.keys()
        }

    def get_download_queue(self, limit: int = 50) -> Dict:
        """
        Get current download queue from database

        Returns only videos with DOWNLOADING status (active downloads)
        Completed videos appear in history, not queue
        """
        try:
            from datetime import datetime, timedelta

            from src.database.connection import get_db
            from src.database.models import Artist, Video, VideoStatus

            queue_items = []

            with get_db() as session:
                recent_cutoff = datetime.utcnow() - timedelta(hours=2)

                # Get DOWNLOADING videos only
                downloading_videos = (
                    session.query(Video, Artist.name)
                    .join(Artist, Video.artist_id == Artist.id)
                    .filter(
                        Video.status == VideoStatus.DOWNLOADING,
                        Video.updated_at >= recent_cutoff,
                    )
                    .order_by(Video.updated_at.desc())
                    .limit(50)
                    .all()
                )

                for video, artist_name in downloading_videos:
                    queue_items.append(
                        {
                            "id": video.id,
                            "artist": artist_name,
                            "title": video.title,
                            "url": video.url or video.youtube_url,
                            "status": "downloading",
                            "created_at": (
                                video.created_at.isoformat()
                                if video.created_at
                                else None
                            ),
                            "video_id": video.id,
                        }
                    )

            return {
                "queue": queue_items,
                "total": len(queue_items),
                "active_downloads": len(self.active_downloads),
            }

        except Exception as e:
            logger.error(f"Error getting download queue: {e}", exc_info=True)
            return {"queue": [], "total": 0, "active_downloads": 0}

    def get_download_history(self, limit: int = 50) -> Dict:
        """
        Get download history from database

        Returns completed/failed download records from the Download table
        This matches what clear_history() clears
        """
        try:
            from datetime import datetime, timedelta

            from src.database.connection import get_db
            from src.database.models import Artist, Download

            history_items = []

            with get_db() as session:
                recent_cutoff = datetime.utcnow() - timedelta(days=30)

                logger.info(
                    f"Unified service querying download history since {recent_cutoff}"
                )

                # Query Download table for completed/failed downloads
                completed_downloads = (
                    session.query(Download, Artist.name)
                    .join(Artist, Download.artist_id == Artist.id)
                    .filter(
                        Download.status.in_(["completed", "failed", "cancelled"]),
                        Download.created_at >= recent_cutoff,
                    )
                    .order_by(Download.created_at.desc())
                    .limit(limit)
                    .all()
                )

                logger.info(
                    f"Unified service found {len(completed_downloads)} downloads in history"
                )

                for download, artist_name in completed_downloads:
                    history_items.append(
                        {
                            "id": download.id,
                            "artist": artist_name,
                            "title": download.title,
                            "url": download.original_url,
                            "status": download.status,
                            "file_path": download.file_path,
                            "file_size": download.file_size,
                            "completed_at": (
                                download.updated_at.isoformat()
                                if download.updated_at
                                else None
                            ),
                            "created_at": (
                                download.created_at.isoformat()
                                if download.created_at
                                else None
                            ),
                            "video_id": download.video_id,
                            "error_message": download.error_message,
                        }
                    )

            logger.info(f"Unified service returning {len(history_items)} history items")
            return {"history": history_items, "total": len(history_items)}

        except Exception as e:
            logger.error(f"Error getting download history: {e}", exc_info=True)
            return {"history": [], "total": 0}

    def cancel_download(self, download_id: int) -> bool:
        """Cancel active download or mark database download as stopped"""
        # Check in-memory active downloads first
        if download_id in self.active_downloads:
            logger.info(f"Download {download_id} cancellation requested (in-memory)")
            return True

        # Check database for download record
        try:
            from src.database.connection import get_db
            from src.database.models import Download

            with get_db() as session:
                download = (
                    session.query(Download).filter(Download.id == download_id).first()
                )
                if download and download.status in ["queued", "downloading", "pending"]:
                    download.status = "stopped"
                    download.error_message = "Download stopped by user"
                    download.updated_at = datetime.utcnow()
                    session.commit()
                    logger.info(f"Download {download_id} marked as stopped in database")
                    return True
                elif download:
                    logger.info(
                        f"Download {download_id} already in final state: {download.status}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Error cancelling download {download_id}: {e}")
            return False

        logger.warning(f"Download {download_id} not found")
        return False


# Global service instance
unified_download_service = UnifiedDownloadService()
