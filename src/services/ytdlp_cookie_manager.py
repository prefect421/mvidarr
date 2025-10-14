"""
Cookie Management for yt-dlp Service
Handles cookie file management for age-restricted and authenticated video downloads

Extracted from ytdlp_service.py as part of code cleanup.
"""

import os
from typing import Dict, Optional

from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ytdlp_cookie_manager")


class YtDlpCookieManager:
    """Manages cookie files for yt-dlp authentication"""

    def __init__(self):
        """Initialize cookie manager"""
        self.custom_cookie_file: Optional[str] = None

    def set_cookie_file(self, cookie_file_path: str):
        """Set custom cookie file for age-restricted videos

        Args:
            cookie_file_path: Path to the cookie file
        """
        self.custom_cookie_file = cookie_file_path
        logger.info(f"Custom cookie file set: {cookie_file_path}")

    def clear_cookie_file(self):
        """Clear custom cookie file"""
        self.custom_cookie_file = None
        logger.info("Custom cookie file cleared")

    def get_cookie_status(self) -> Dict:
        """Get status of custom cookie file

        Returns:
            Dictionary containing cookie availability status and file info
        """
        if self.custom_cookie_file and os.path.exists(self.custom_cookie_file):
            try:
                stat = os.stat(self.custom_cookie_file)
                return {
                    "cookies_available": True,
                    "file_path": self.custom_cookie_file,
                    "file_size": stat.st_size,
                    "modified_time": stat.st_mtime,
                }
            except Exception as e:
                return {"cookies_available": False, "error": str(e)}
        else:
            return {"cookies_available": False}

    def load_existing_cookie_file(self):
        """Auto-load existing cookie file at startup if available

        Checks standard cookie locations and loads the first available file.
        """
        # Check standard cookie locations
        cookie_paths = [
            "data/cookies/youtube_cookies.txt",
            "cookies.txt",
            "youtube_cookies.txt",
        ]

        for path in cookie_paths:
            full_path = os.path.join(os.getcwd(), path)
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                logger.info(f"Auto-loading existing cookie file: {full_path}")
                self.custom_cookie_file = full_path
                return

        logger.debug("No existing cookie file found to auto-load")

    def get_cookie_file_path(self) -> Optional[str]:
        """Get the current cookie file path

        Returns:
            Cookie file path or None if not set
        """
        return self.custom_cookie_file
