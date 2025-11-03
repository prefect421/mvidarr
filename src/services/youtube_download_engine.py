"""
Complete YouTube Download Engine - Production Solution
Comprehensive approach to YouTube downloads with multi-client strategies and advanced anti-detection
"""

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("mvidarr.youtube_engine")


class DownloadStrategy(Enum):
    """Available download strategies in order of preference"""

    TV_CLIENT = "tv_client"  # Best: TV client bypasses most detection
    WEB_CLIENT_COOKIES = "web_cookies"  # Good: Web client with browser cookies
    WEB_CLIENT_FALLBACK = "web_fallback"  # Last resort: Basic web client


@dataclass
class DownloadResult:
    """Result of a download attempt"""

    success: bool
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    strategy_used: Optional[DownloadStrategy] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None
    metadata: Optional[Dict] = None


class YouTubeDownloadEngine:
    """
    Complete YouTube download solution that handles all 2025 YouTube restrictions
    Uses multiple fallback strategies to ensure reliable downloads
    """

    def __init__(self):
        self.yt_dlp_path = self._find_best_ytdlp()
        # Strategy order prioritizes TV client then web with cookies
        self.strategies = [
            DownloadStrategy.TV_CLIENT,  # Primary: Works reliably for most videos
            DownloadStrategy.WEB_CLIENT_COOKIES,  # Secondary: Web with cookies
            DownloadStrategy.WEB_CLIENT_FALLBACK,  # Last resort
        ]

        # Ensure latest yt-dlp version
        self._ensure_latest_ytdlp()

        logger.info("YouTube Download Engine initialized with complete strategy suite")

    def _find_best_ytdlp(self) -> str:
        """Find the best yt-dlp executable, preferring nightly builds"""
        candidates = [
            "/root/.local/bin/yt-dlp",  # pipx nightly
            "/usr/local/bin/yt-dlp",  # system install
            "yt-dlp",  # PATH fallback
        ]

        for path in candidates:
            if path.startswith("/") and os.path.exists(path):
                return path
            elif not path.startswith("/") and shutil.which(path):
                return shutil.which(path)

        raise RuntimeError("yt-dlp not found - please install yt-dlp")

    def _ensure_latest_ytdlp(self):
        """Ensure we have the absolute latest yt-dlp version"""
        try:
            # Check current version
            result = subprocess.run(
                [self.yt_dlp_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                current_version = result.stdout.strip()
                logger.info(f"Current yt-dlp version: {current_version}")

                # If not from 2025, force update
                if "2025" not in current_version:
                    logger.warning("yt-dlp version is outdated, updating...")
                    self._update_ytdlp()
            else:
                logger.error("Could not check yt-dlp version")

        except Exception as e:
            logger.warning(f"Version check failed: {e}")

    def _update_ytdlp(self):
        """Update yt-dlp to latest nightly build"""
        try:
            # Try pipx upgrade first
            result = subprocess.run(
                ["pipx", "upgrade", "yt-dlp"], capture_output=True, timeout=300
            )

            if result.returncode == 0:
                logger.info("yt-dlp updated via pipx")
                return

            # Try direct GitHub install
            subprocess.run(
                [
                    "pipx",
                    "install",
                    "--force",
                    "git+https://github.com/yt-dlp/yt-dlp.git",
                ],
                capture_output=True,
                timeout=300,
            )

            logger.info("yt-dlp updated from GitHub")

        except Exception as e:
            logger.error(f"yt-dlp update failed: {e}")

    def download_video(
        self,
        url: str,
        output_path: str,
        title: str = "video",
        quality: str = "best",
        download_subtitles: bool = False,
        subtitle_languages: str = "en,en-US",
    ) -> DownloadResult:
        """
        Download video using the complete strategy suite
        Tries each strategy until one succeeds
        """
        start_time = time.time()

        logger.info(f"Starting download: {title}")
        logger.info(f"URL: {url}")
        logger.info(f"Quality: {quality}")

        # Try each strategy in order with delays to avoid rate limiting
        for i, strategy in enumerate(self.strategies):
            try:
                # Add delay between strategy attempts (except first)
                if i > 0:
                    import random

                    delay = random.uniform(2, 5)  # Random delay 2-5 seconds
                    logger.info(
                        f"Waiting {delay:.1f}s before next strategy to avoid rate limiting"
                    )
                    time.sleep(delay)

                logger.info(f"Attempting strategy: {strategy.value}")

                result = self._attempt_download_with_strategy(
                    strategy,
                    url,
                    output_path,
                    title,
                    quality,
                    download_subtitles,
                    subtitle_languages,
                )

                if result.success:
                    result.duration = time.time() - start_time
                    result.strategy_used = strategy

                    logger.info(f"Download successful with strategy: {strategy.value}")
                    logger.info(f"File: {result.file_path}")
                    logger.info(f"Duration: {result.duration:.1f}s")

                    return result
                else:
                    logger.warning(
                        f"Strategy {strategy.value} failed: {result.error_message}"
                    )

                    # Wait before trying next strategy
                    time.sleep(2)

            except Exception as e:
                logger.error(f"Strategy {strategy.value} exception: {e}")
                continue

        # All strategies failed
        duration = time.time() - start_time
        return DownloadResult(
            success=False,
            error_message="All download strategies failed",
            duration=duration,
        )

    def _attempt_download_with_strategy(
        self,
        strategy: DownloadStrategy,
        url: str,
        output_path: str,
        title: str,
        quality: str,
        download_subtitles: bool = False,
        subtitle_languages: str = "en,en-US",
    ) -> DownloadResult:
        """Attempt download with specific strategy"""

        # Build base command
        cmd = [self.yt_dlp_path]

        # Output settings
        safe_title = self._sanitize_filename(title)
        output_template = os.path.join(output_path, f"{safe_title}.%(ext)s")
        cmd.extend(["-o", output_template])

        # Pre-download cleanup: Remove corrupted target files that would block rename
        # Check for existing files with 0 hard links (corrupted inodes)
        import subprocess

        for ext in [".mp4", ".webm", ".mkv"]:
            potential_target = os.path.join(output_path, f"{safe_title}{ext}")
            if os.path.exists(potential_target):
                try:
                    # Check hard link count using stat
                    stat_result = subprocess.run(
                        ["stat", "-c", "%h", potential_target],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if stat_result.returncode == 0:
                        hard_links = int(stat_result.stdout.strip())
                        if hard_links == 0:
                            # Corrupted file with 0 hard links - remove it
                            logger.warning(
                                f"Removing corrupted file with 0 hard links: {potential_target}"
                            )
                            subprocess.run(["rm", "-f", potential_target], timeout=5)
                except Exception as e:
                    logger.debug(
                        f"Could not check/remove existing file {potential_target}: {e}"
                    )

        # Quality format - use directly if it's a complex format string, otherwise convert
        if "/" in quality or "[" in quality or "+" in quality:
            # Complex format string from video quality service - use as-is
            logger.info(f"Using complex format string: {quality[:100]}...")
            cmd.extend(["-f", quality])
        else:
            # Simple quality like "720p" or "best" - convert to format string
            simple_format = self._get_quality_format(quality)
            logger.info(
                f"Converting simple quality '{quality}' to format: {simple_format}"
            )
            cmd.extend(["-f", simple_format])

        # Metadata
        cmd.extend(["--write-info-json", "--embed-metadata", "--add-metadata"])

        # Subtitle options - only if requested
        if download_subtitles:
            # Handle smart subtitle language matching
            if "*" in subtitle_languages:
                # For patterns like "en.*", we need to query available subs first
                logger.info(
                    f"Smart subtitle matching for pattern: {subtitle_languages}"
                )
                subtitle_langs = self._resolve_subtitle_languages(
                    url, subtitle_languages
                )
                logger.info(f"Resolved subtitle languages: {subtitle_langs}")
            else:
                # Direct language codes
                subtitle_langs = subtitle_languages

            cmd.extend(
                [
                    "--write-subs",  # Download subtitle files
                    "--write-auto-subs",  # Download auto-generated subtitles
                    "--sub-langs",
                    subtitle_langs,  # Use resolved subtitle languages
                ]
            )

        # Strategy-specific arguments
        cmd.extend(self._get_strategy_args(strategy))

        # URL
        cmd.append(url)

        logger.debug(f"Command: {' '.join(cmd[:5])}... (truncated)")

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

                # Log important events
                if any(
                    keyword in line
                    for keyword in ["ERROR:", "WARNING:", "Selected format:"]
                ):
                    logger.debug(f"yt-dlp: {line.strip()}")

            process.wait(timeout=300)  # 5 minute timeout

            if process.returncode == 0:
                # Success - find downloaded file
                downloaded_file = self._find_downloaded_file(
                    output_template, output_lines
                )

                if not downloaded_file:
                    logger.error(f"Download succeeded but file not found!")
                    logger.error(f"Output template: {output_template}")
                    logger.error(f"Output lines: {output_lines[-20:]}")  # Last 20 lines
                    # Try to list directory to see what's there
                    output_dir = os.path.dirname(output_template)
                    if os.path.exists(output_dir):
                        files = os.listdir(output_dir)
                        logger.error(f"Directory contents: {files}")

                # Handle .temp files that couldn't be renamed (filesystem issues)
                if downloaded_file and downloaded_file.endswith(".temp.mp4"):
                    final_file = downloaded_file.replace(".temp.mp4", ".mp4")
                    try:
                        # Try force rename with multiple strategies
                        if self._force_rename_temp_file(downloaded_file, final_file):
                            downloaded_file = final_file
                            logger.info(f"Successfully renamed temp file: {final_file}")
                        else:
                            logger.warning(
                                f"Could not rename temp file, but file is valid. Using temp file: {downloaded_file}"
                            )
                            # Keep using the .temp.mp4 file - it's valid even if rename failed
                    except Exception as rename_error:
                        logger.warning(
                            f"Temp file rename exception, but file is valid. Using temp file: {rename_error}"
                        )

                if downloaded_file and os.path.exists(downloaded_file):
                    file_size = os.path.getsize(downloaded_file)

                    return DownloadResult(
                        success=True,
                        file_path=downloaded_file,
                        file_size=file_size,
                        metadata=self._extract_metadata(downloaded_file),
                    )
                elif downloaded_file:
                    logger.error(
                        f"Downloaded file path exists but file not found: {downloaded_file}"
                    )
                    return DownloadResult(
                        success=False,
                        error_message=f"File not found after download: {downloaded_file}",
                    )

            # Failed - extract error
            error_output = "\n".join(output_lines)
            error_message = self._extract_error_message(error_output)

            return DownloadResult(success=False, error_message=error_message)

        except subprocess.TimeoutExpired:
            process.kill()
            return DownloadResult(
                success=False, error_message="Download timed out after 5 minutes"
            )
        except Exception as e:
            return DownloadResult(
                success=False, error_message=f"Process error: {str(e)}"
            )

    def _get_strategy_args(self, strategy: DownloadStrategy) -> List[str]:
        """Get yt-dlp arguments for specific strategy"""

        if strategy == DownloadStrategy.TV_CLIENT:
            return self._get_tv_client_args()

        elif strategy == DownloadStrategy.WEB_CLIENT_COOKIES:
            return self._get_web_cookies_args()

        elif strategy == DownloadStrategy.WEB_CLIENT_FALLBACK:
            return self._get_web_fallback_args()

        else:
            return []

    def _get_tv_client_args(self) -> List[str]:
        """TV client strategy - with cookies for age-restricted content"""
        args = [
            "--extractor-args",
            "youtube:player_client=tv",
            "--socket-timeout",
            "30",
            "--retries",
            "3",
            "--fragment-retries",
            "3",
        ]

        # Add cookies for age-restricted videos - TV client still needs them!
        args.extend(self._get_cookie_args(DownloadStrategy.TV_CLIENT))

        return args

    def _get_android_client_args(self) -> List[str]:
        """Android client strategy"""
        return [
            "--extractor-args",
            "youtube:player_client=android",
            "--add-header",
            "User-Agent:com.google.android.youtube/19.09.36 (Linux; U; Android 11)",
            "--socket-timeout",
            "30",
            "--retries",
            "3",
        ]

    def _get_web_cookies_args(self) -> List[str]:
        """Web client with cookie file or firefox browser cookies"""
        args = [
            "--extractor-args",
            "youtube:player_client=web",
            "--socket-timeout",
            "30",
            "--retries",
            "3",
        ]

        # Add cookies using helper method - tries file first, then firefox
        args.extend(self._get_cookie_args(DownloadStrategy.WEB_CLIENT_COOKIES))

        return args

    def _get_web_fallback_args(self) -> List[str]:
        """Last resort web client strategy with edge/firefox cookies"""
        args = [
            "--extractor-args",
            "youtube:player_client=web,tv,android",
            "--socket-timeout",
            "45",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--retry-sleep",
            "2",
            "--no-check-certificate",
        ]

        # Add cookies for age-restricted videos - tries edge/firefox
        args.extend(self._get_cookie_args(DownloadStrategy.WEB_CLIENT_FALLBACK))

        return args

    def _get_cookie_args(
        self, strategy: Optional[DownloadStrategy] = None
    ) -> List[str]:
        """
        Get cookie arguments for yt-dlp
        Uses cookie file exclusively for server environment

        Server environment: browsers not available, must use cookie file
        """
        cookie_path = "data/cookies/youtube_cookies.txt"

        # All strategies use the cookie file since this is a server environment
        # Browsers with GUI aren't available for --cookies-from-browser
        if os.path.exists(cookie_path):
            logger.debug(f"Using cookie file: {cookie_path}")
            return ["--cookies", cookie_path]
        else:
            logger.warning(
                f"Cookie file not found at {cookie_path}. Age-restricted videos will fail. "
                "Please export cookies from your browser using a cookie extension."
            )
            return []

    def _get_quality_format(self, quality: str) -> str:
        """Get optimized format string - TV client compatible"""
        if quality == "best":
            # Use separate video+audio for better quality with TV client
            return "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        elif quality.endswith("p"):
            height = quality.replace("p", "")
            return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
        else:
            return "bestvideo+bestaudio/best"

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem"""
        import re

        # Remove or replace problematic characters
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        filename = filename[:200]  # Limit length
        return filename

    def _find_downloaded_file(
        self, template: str, output_lines: List[str]
    ) -> Optional[str]:
        """Find actual downloaded file"""
        # Look for destination in output, prioritizing video files
        video_extensions = [".mp4", ".webm", ".mkv", ".avi", ".mov"]
        destinations = []

        for line in output_lines:
            if "Destination:" in line:
                dest = line.split("Destination:")[1].strip()
                destinations.append(dest)

        # If we have multiple destinations, prioritize video files that actually exist
        if destinations:
            # First, look for video files that actually exist
            for dest in destinations:
                for ext in video_extensions:
                    if dest.endswith(ext) and os.path.exists(dest):
                        return dest
            # Don't return subtitle files - let it fall through to directory search

        # Fallback: search directory
        base_dir = os.path.dirname(template)
        base_name = os.path.splitext(os.path.basename(template))[0]

        if os.path.exists(base_dir):
            # Priority order: video files first, then other files
            video_extensions = [".mp4", ".webm", ".mkv", ".avi", ".mov"]
            found_files = []

            # Strategy 1: Exact match with base_name
            for file in os.listdir(base_dir):
                if file.startswith(base_name) and not file.endswith(".info.json"):
                    found_files.append(file)

            # Strategy 2: If no exact match, try fuzzy matching (handle yt-dlp adding prefixes)
            # Sometimes yt-dlp adds "Artist - " prefix even when template already has it
            if not found_files:
                # Extract the core title (remove common prefixes)
                title_parts = base_name.split(" - ")
                if len(title_parts) >= 2:
                    # Try matching on the last part (actual title)
                    core_title = title_parts[-1].strip()
                    for file in os.listdir(base_dir):
                        if core_title in file and not file.endswith(".info.json"):
                            found_files.append(file)

            # Strategy 3: Last resort - get most recent video file (including .temp files)
            # Prioritize by: 1) Most recent, 2) Largest file size (higher quality)
            if not found_files:

                video_files = []
                for file in os.listdir(base_dir):
                    full_path = os.path.join(base_dir, file)
                    # Include .temp.mp4 files so rename handling can fix them
                    if any(
                        file.endswith(ext) for ext in video_extensions
                    ) or file.endswith(".temp.mp4"):
                        # Only exclude info.json
                        if not file.endswith(".info.json"):
                            file_size = os.path.getsize(full_path)
                            file_mtime = os.path.getmtime(full_path)
                            video_files.append((file, file_mtime, file_size, full_path))

                if video_files:
                    # Get files modified in the last 5 minutes (recent downloads)
                    import time

                    current_time = time.time()
                    recent_files = [
                        f for f in video_files if (current_time - f[1]) < 300
                    ]  # 5 minutes

                    if recent_files:
                        # Sort recent files by size (largest first) - higher quality
                        recent_files.sort(key=lambda x: x[2], reverse=True)
                        most_recent = recent_files[0][0]
                        logger.info(
                            f"Using most recent large video file: {most_recent} ({recent_files[0][2]/(1024*1024):.1f}MB)"
                        )
                        found_files.append(most_recent)
                    else:
                        # No recent files, sort all by modification time
                        video_files.sort(key=lambda x: x[1], reverse=True)
                        most_recent = video_files[0][0]
                        found_files.append(most_recent)
                        logger.info(
                            f"Using most recent video file as fallback: {most_recent}"
                        )

            # First, look for video files (excluding temp files)
            for file in found_files:
                for ext in video_extensions:
                    if file.endswith(ext) and not file.endswith(".temp.mp4"):
                        return os.path.join(base_dir, file)

            # If no video file found, return first non-video file (subtitle, etc.)
            if found_files:
                return os.path.join(base_dir, found_files[0])

        return None

    def _force_rename_temp_file(self, temp_file: str, final_file: str) -> bool:
        """
        Force rename a .temp file to final file using multiple strategies
        Handles filesystem issues like unlinked inodes or locked files
        """
        import time

        try:
            # Strategy 1: Simple rename (works most of the time)
            if not os.path.exists(final_file):
                os.rename(temp_file, final_file)
                return True

            # Strategy 2: Final file exists - remove it first then rename
            logger.warning(f"Final file exists, attempting to remove: {final_file}")
            try:
                os.remove(final_file)
                time.sleep(0.1)  # Brief pause for filesystem
                os.rename(temp_file, final_file)
                return True
            except (OSError, PermissionError) as e:
                logger.warning(f"Could not remove existing file (attempt 1): {e}")

            # Strategy 3: Force unlink with subprocess (handles corrupted inodes)
            try:
                import subprocess

                logger.info("Attempting force unlink with subprocess")
                result = subprocess.run(
                    ["rm", "-f", final_file], capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    time.sleep(0.2)
                    os.rename(temp_file, final_file)
                    logger.info("Force unlink succeeded")
                    return True
            except Exception as e:
                logger.warning(f"Force unlink failed: {e}")

            # Strategy 4: Use shutil.move (handles cross-device links)
            try:
                if os.path.exists(final_file):
                    os.remove(final_file)
                shutil.move(temp_file, final_file)
                return True
            except Exception as e:
                logger.warning(f"shutil.move failed: {e}")

            # Strategy 5: Copy then delete (preserves temp if fails)
            try:
                if os.path.exists(final_file):
                    try:
                        os.remove(final_file)
                    except:
                        pass  # Ignore errors, try copy anyway

                shutil.copy2(temp_file, final_file)
                # Verify copy succeeded before deleting temp
                if os.path.exists(final_file) and os.path.getsize(
                    final_file
                ) == os.path.getsize(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        logger.warning(
                            "Temp file could not be removed after copy, but copy succeeded"
                        )
                    logger.info("Used copy+delete strategy for temp file")
                    return True
            except Exception as e:
                logger.warning(f"copy+delete failed: {e}")

            # Strategy 6: Just use the temp file as-is (return True to signal success)
            logger.warning(
                f"Cannot rename temp file, but temp file exists and is valid: {temp_file}"
            )
            logger.warning("System will use .temp.mp4 file directly")
            return False  # Return False so caller uses temp file path

        except Exception as e:
            logger.error(f"Unexpected error in _force_rename_temp_file: {e}")
            return False

    def _extract_metadata(self, file_path: str) -> Optional[Dict]:
        """Extract metadata from info.json"""
        info_file = os.path.splitext(file_path)[0] + ".info.json"
        if os.path.exists(info_file):
            try:
                with open(info_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _extract_error_message(self, output: str) -> str:
        """Extract meaningful error from output"""
        lines = output.split("\n")

        # First try to find ERROR: lines
        for line in reversed(lines):
            if line.startswith("ERROR:"):
                return line.replace("ERROR:", "").strip()

        # If no ERROR line, look for WARNING lines that might explain the issue
        warnings = [line for line in lines if line.startswith("WARNING:")]
        if warnings:
            return f"No explicit error, warnings: {warnings[-1].replace('WARNING:', '').strip()}"

        # Last resort: return last few non-empty lines as context
        non_empty = [line.strip() for line in lines if line.strip()]
        if non_empty:
            return f"Unknown error - last output: {' | '.join(non_empty[-3:])}"

        return "Unknown error occurred - no output captured"

    def _resolve_subtitle_languages(self, url: str, pattern: str) -> str:
        """Resolve subtitle language patterns like 'en.*' to actual available languages"""
        try:
            # Query available subtitles for this video
            cmd = [self.yt_dlp_path, "--list-subs", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                logger.warning(
                    f"Could not query subtitles for {url}, using pattern as-is"
                )
                return pattern

            # Parse available languages from output
            available_langs = []
            lines = result.stdout.split("\n")

            for line in lines:
                # Look for language lines (they contain language codes)
                if " - " in line and any(fmt in line for fmt in ["vtt", "srt", "ttml"]):
                    # Extract language code (first part before space)
                    lang_code = line.split()[0]
                    if lang_code:
                        available_langs.append(lang_code)

            if not available_langs:
                logger.warning(f"No subtitle languages found for {url}")
                return pattern

            # Match patterns like "en.*" to available languages
            matched_langs = []
            for pattern_part in pattern.split(","):
                pattern_part = pattern_part.strip()

                if pattern_part.endswith(".*"):
                    # Wildcard matching (e.g., "en.*" matches "en", "en-US", "en-nP7-2PuUl7o")
                    prefix = pattern_part[:-2]  # Remove ".*"
                    for lang in available_langs:
                        if lang.startswith(prefix):
                            matched_langs.append(lang)
                elif pattern_part in available_langs:
                    # Exact match
                    matched_langs.append(pattern_part)

            if matched_langs:
                result_langs = ",".join(matched_langs[:5])  # Limit to 5 languages
                logger.info(f"Pattern '{pattern}' resolved to: {result_langs}")
                return result_langs
            else:
                logger.warning(f"Pattern '{pattern}' matched no available languages")
                return pattern

        except Exception as e:
            logger.error(f"Error resolving subtitle languages: {e}")
            return pattern

    def test_download_capability(
        self, test_url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ) -> Dict[str, Any]:
        """Test download capabilities with all strategies"""
        results = {}

        for strategy in self.strategies:
            try:
                logger.info(f"Testing strategy: {strategy.value}")

                # Use simulate mode for testing
                cmd = [self.yt_dlp_path, "--simulate"]
                cmd.extend(self._get_strategy_args(strategy))
                cmd.append(test_url)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                success = (
                    result.returncode == 0
                    and "Signature extraction failed" not in result.stderr
                )

                results[strategy.value] = {
                    "success": success,
                    "error": result.stderr if not success else None,
                }

                if success:
                    logger.info(f"Strategy {strategy.value}: ✅ Working")
                else:
                    logger.warning(f"Strategy {strategy.value}: ❌ Failed")

            except Exception as e:
                results[strategy.value] = {"success": False, "error": str(e)}
                logger.error(f"Strategy {strategy.value}: ❌ Exception - {e}")

        return results


# Global engine instance
youtube_download_engine = YouTubeDownloadEngine()
