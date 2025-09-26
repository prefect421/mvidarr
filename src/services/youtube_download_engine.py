"""
Complete YouTube Download Engine - Production Solution
Comprehensive approach to YouTube downloads with OAuth2, multi-client strategies, and advanced anti-detection
"""

import json
import os
import subprocess
import time
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass

from src.services.youtube_oauth_service import youtube_oauth_service
from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.youtube_engine")


class DownloadStrategy(Enum):
    """Available download strategies in order of preference"""
    OAUTH2_AUTHENTICATED = "oauth2"          # Best: Official API authentication
    TV_CLIENT = "tv_client"                  # Good: TV client bypasses most detection
    ANDROID_CLIENT = "android_client"        # Good: Android client works well
    WEB_CLIENT_COOKIES = "web_cookies"       # OK: Web client with browser cookies  
    WEB_CLIENT_FALLBACK = "web_fallback"     # Last resort: Basic web client


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
        self.oauth_service = youtube_oauth_service
        self.strategies = [
            DownloadStrategy.OAUTH2_AUTHENTICATED,
            DownloadStrategy.TV_CLIENT, 
            DownloadStrategy.ANDROID_CLIENT,
            DownloadStrategy.WEB_CLIENT_COOKIES,
            DownloadStrategy.WEB_CLIENT_FALLBACK
        ]
        
        # Ensure latest yt-dlp version
        self._ensure_latest_ytdlp()
        
        logger.info("YouTube Download Engine initialized with complete strategy suite")
    
    def _find_best_ytdlp(self) -> str:
        """Find the best yt-dlp executable, preferring nightly builds"""
        candidates = [
            "/root/.local/bin/yt-dlp",  # pipx nightly
            "/usr/local/bin/yt-dlp",   # system install
            "yt-dlp"                   # PATH fallback
        ]
        
        for path in candidates:
            if path.startswith('/') and os.path.exists(path):
                return path
            elif not path.startswith('/') and shutil.which(path):
                return shutil.which(path)
        
        raise RuntimeError("yt-dlp not found - please install yt-dlp")
    
    def _ensure_latest_ytdlp(self):
        """Ensure we have the absolute latest yt-dlp version"""
        try:
            # Check current version
            result = subprocess.run([self.yt_dlp_path, "--version"], 
                                 capture_output=True, text=True, timeout=10)
            
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
            result = subprocess.run(["pipx", "upgrade", "yt-dlp"], 
                                  capture_output=True, timeout=300)
            
            if result.returncode == 0:
                logger.info("yt-dlp updated via pipx")
                return
            
            # Try direct GitHub install
            subprocess.run([
                "pipx", "install", "--force", 
                "git+https://github.com/yt-dlp/yt-dlp.git"
            ], capture_output=True, timeout=300)
            
            logger.info("yt-dlp updated from GitHub")
            
        except Exception as e:
            logger.error(f"yt-dlp update failed: {e}")
    
    def download_video(self, url: str, output_path: str, title: str = "video", 
                      quality: str = "best") -> DownloadResult:
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
                    logger.info(f"Waiting {delay:.1f}s before next strategy to avoid rate limiting")
                    time.sleep(delay)
                
                logger.info(f"Attempting strategy: {strategy.value}")
                
                result = self._attempt_download_with_strategy(
                    strategy, url, output_path, title, quality
                )
                
                if result.success:
                    result.duration = time.time() - start_time
                    result.strategy_used = strategy
                    
                    logger.info(f"Download successful with strategy: {strategy.value}")
                    logger.info(f"File: {result.file_path}")
                    logger.info(f"Duration: {result.duration:.1f}s")
                    
                    return result
                else:
                    logger.warning(f"Strategy {strategy.value} failed: {result.error_message}")
                    
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
            duration=duration
        )
    
    def _attempt_download_with_strategy(self, strategy: DownloadStrategy, 
                                      url: str, output_path: str, 
                                      title: str, quality: str) -> DownloadResult:
        """Attempt download with specific strategy"""
        
        # Build base command
        cmd = [self.yt_dlp_path]
        
        # Output settings
        safe_title = self._sanitize_filename(title)
        output_template = os.path.join(output_path, f"{safe_title}.%(ext)s")
        cmd.extend(["-o", output_template])
        
        # Quality format
        cmd.extend(["-f", self._get_quality_format(quality)])
        
        # Metadata
        cmd.extend(["--write-info-json", "--embed-metadata", "--add-metadata"])
        
        # Subtitle options - download subtitles when available
        cmd.extend([
            "--write-subs",           # Download subtitle files
            "--write-auto-subs",      # Download auto-generated subtitles  
            "--sub-langs", "en,en-US" # Prefer English subtitles
        ])
        
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
                universal_newlines=True
            )
            
            output_lines = []
            for line in iter(process.stdout.readline, ""):
                output_lines.append(line.strip())
                
                # Log important events
                if any(keyword in line for keyword in ["ERROR:", "WARNING:", "Selected format:"]):
                    logger.debug(f"yt-dlp: {line.strip()}")
            
            process.wait(timeout=300)  # 5 minute timeout
            
            if process.returncode == 0:
                # Success - find downloaded file
                downloaded_file = self._find_downloaded_file(output_template, output_lines)
                if downloaded_file and os.path.exists(downloaded_file):
                    file_size = os.path.getsize(downloaded_file)
                    
                    return DownloadResult(
                        success=True,
                        file_path=downloaded_file,
                        file_size=file_size,
                        metadata=self._extract_metadata(downloaded_file)
                    )
            
            # Failed - extract error
            error_output = "\n".join(output_lines)
            error_message = self._extract_error_message(error_output)
            
            return DownloadResult(
                success=False,
                error_message=error_message
            )
            
        except subprocess.TimeoutExpired:
            process.kill()
            return DownloadResult(
                success=False,
                error_message="Download timed out after 5 minutes"
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=f"Process error: {str(e)}"
            )
    
    def _get_strategy_args(self, strategy: DownloadStrategy) -> List[str]:
        """Get yt-dlp arguments for specific strategy"""
        
        if strategy == DownloadStrategy.OAUTH2_AUTHENTICATED:
            # Use OAuth2 authentication
            if self.oauth_service.is_authenticated():
                return self.oauth_service.get_authenticated_yt_dlp_args()
            else:
                # OAuth not available, fall back to TV client
                return self._get_tv_client_args()
        
        elif strategy == DownloadStrategy.TV_CLIENT:
            return self._get_tv_client_args()
        
        elif strategy == DownloadStrategy.ANDROID_CLIENT:
            return self._get_android_client_args()
        
        elif strategy == DownloadStrategy.WEB_CLIENT_COOKIES:
            return self._get_web_cookies_args()
        
        elif strategy == DownloadStrategy.WEB_CLIENT_FALLBACK:
            return self._get_web_fallback_args()
        
        else:
            return []
    
    def _get_tv_client_args(self) -> List[str]:
        """TV client strategy - bypasses most signature extraction"""
        return [
            "--extractor-args", "youtube:player_client=tv",
            "--socket-timeout", "30", 
            "--retries", "3",
            "--fragment-retries", "3"
        ]
    
    def _get_android_client_args(self) -> List[str]:
        """Android client strategy"""
        return [
            "--extractor-args", "youtube:player_client=android",
            "--add-header", "User-Agent:com.google.android.youtube/19.09.36 (Linux; U; Android 11)",
            "--socket-timeout", "30",
            "--retries", "3"
        ]
    
    def _get_web_cookies_args(self) -> List[str]:
        """Web client with browser cookies"""
        args = [
            "--extractor-args", "youtube:player_client=web",
            "--socket-timeout", "30",
            "--retries", "3"
        ]
        
        # Add cookies if available
        cookie_path = "data/cookies/youtube_cookies.txt"
        if os.path.exists(cookie_path):
            args.extend(["--cookies", cookie_path])
        else:
            # Try to extract from browser
            args.extend(["--cookies-from-browser", "firefox,chrome,chromium,edge"])
        
        return args
    
    def _get_web_fallback_args(self) -> List[str]:
        """Last resort web client strategy"""
        return [
            "--extractor-args", "youtube:player_client=web,tv,android",
            "--socket-timeout", "45",
            "--retries", "5",
            "--fragment-retries", "5",
            "--retry-sleep", "2",
            "--no-check-certificate"
        ]
    
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
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename[:200]  # Limit length
        return filename
    
    def _find_downloaded_file(self, template: str, output_lines: List[str]) -> Optional[str]:
        """Find actual downloaded file"""
        # Look for destination in output, prioritizing video files
        video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov']
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
            video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov']
            found_files = []
            
            for file in os.listdir(base_dir):
                if file.startswith(base_name) and not file.endswith('.info.json'):
                    found_files.append(file)
            
            # First, look for video files
            for file in found_files:
                for ext in video_extensions:
                    if file.endswith(ext):
                        return os.path.join(base_dir, file)
            
            # If no video file found, return first non-video file (subtitle, etc.)
            if found_files:
                return os.path.join(base_dir, found_files[0])
        
        return None
    
    def _extract_metadata(self, file_path: str) -> Optional[Dict]:
        """Extract metadata from info.json"""
        info_file = os.path.splitext(file_path)[0] + ".info.json"
        if os.path.exists(info_file):
            try:
                with open(info_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return None
    
    def _extract_error_message(self, output: str) -> str:
        """Extract meaningful error from output"""
        lines = output.split('\n')
        for line in reversed(lines):
            if line.startswith('ERROR:'):
                return line.replace('ERROR:', '').strip()
        return "Unknown error occurred"
    
    def get_oauth_setup_url(self) -> Optional[str]:
        """Get URL to set up OAuth2 authentication"""
        try:
            return self.oauth_service.start_oauth_flow()
        except Exception as e:
            logger.error(f"Failed to start OAuth flow: {e}")
            return None
    
    def complete_oauth_setup(self, timeout: int = 300) -> bool:
        """Complete OAuth2 setup process"""
        return self.oauth_service.complete_oauth_flow(timeout)
    
    def is_oauth_configured(self) -> bool:
        """Check if OAuth2 is properly configured"""
        return self.oauth_service.is_authenticated()
    
    def test_download_capability(self, test_url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ") -> Dict[str, Any]:
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
                
                success = result.returncode == 0 and "Signature extraction failed" not in result.stderr
                
                results[strategy.value] = {
                    "success": success,
                    "error": result.stderr if not success else None
                }
                
                if success:
                    logger.info(f"Strategy {strategy.value}: ✅ Working")
                else:
                    logger.warning(f"Strategy {strategy.value}: ❌ Failed")
                    
            except Exception as e:
                results[strategy.value] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"Strategy {strategy.value}: ❌ Exception - {e}")
        
        return results


# Global engine instance
youtube_download_engine = YouTubeDownloadEngine()