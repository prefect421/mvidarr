"""
Utility module for detecting downloaded video files with yt-dlp filename variations.

This module handles the complexity of finding downloaded files when yt-dlp
may have modified the filename in various ways (HTML entities, quote handling,
parentheses removal, etc.).
"""

import glob
import os
import re
import time
from html import unescape
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("mvidarr.ytdlp_file_detection")


class YtDlpFileDetection:
    """Utility class for robust file detection with yt-dlp filename variations."""

    @staticmethod
    def find_downloaded_file(
        output_template: str, download_entry: dict
    ) -> Optional[str]:
        """
        Robust file detection that handles yt-dlp filename variations.

        Args:
            output_template: Expected output filename template (with %(ext)s placeholder)
            download_entry: Download metadata dictionary (for logging context)

        Returns:
            Path to the downloaded file if found, None otherwise

        Strategy:
            1. Exact template match (try common extensions)
            2. Pattern-based search with HTML entity decoding and transformations
            3. Fallback to recent files with title similarity
        """
        # Extract directory and base filename from template
        output_dir = os.path.dirname(output_template)
        template_basename = os.path.basename(output_template).replace("%(ext)s", "")

        logger.debug(
            f"Looking for files in {output_dir} matching pattern based on: {template_basename}"
        )

        # Strategy 1: Exact template match (original logic)
        exact_match = YtDlpFileDetection._try_exact_match(output_template)
        if exact_match:
            return exact_match

        # Strategy 2: Pattern-based search with HTML entity decoding
        pattern_match = YtDlpFileDetection._try_pattern_match(
            output_dir, template_basename
        )
        if pattern_match:
            return pattern_match

        # Strategy 3: Fallback - look for any recent video files in the directory
        fallback_match = YtDlpFileDetection._try_fallback_match(
            output_dir, template_basename
        )
        if fallback_match:
            return fallback_match

        logger.warning(f"No downloaded file found for template: {output_template}")
        return None

    @staticmethod
    def _try_exact_match(output_template: str) -> Optional[str]:
        """
        Try to find file using exact template match with common video extensions.

        Args:
            output_template: Filename template with %(ext)s placeholder

        Returns:
            Path to file if found, None otherwise
        """
        for ext in ["mp4", "mkv", "webm", "avi", "mov", "flv"]:
            exact_file = output_template.replace("%(ext)s", ext)
            if os.path.exists(exact_file):
                logger.debug(f"Found exact template match: {exact_file}")
                return exact_file
        return None

    @staticmethod
    def _try_pattern_match(output_dir: str, template_basename: str) -> Optional[str]:
        """
        Try to find file using flexible pattern matching with filename transformations.

        Handles various yt-dlp filename transformations:
        - HTML entity decoding
        - Quote/apostrophe variations
        - Parentheses removal
        - Period removal from abbreviations
        - Partial matches with scoring

        Args:
            output_dir: Directory to search in
            template_basename: Base filename (without extension)

        Returns:
            Path to best matching file if found, None otherwise
        """
        # Clean the template basename by handling common yt-dlp transformations
        search_patterns = []

        # Create search pattern by:
        # 1. HTML decode common entities
        decoded_basename = unescape(template_basename)
        # 2. Handle yt-dlp's common filename transformations
        alt_basename1 = template_basename.replace("'", "39").replace("&#39;", "39")
        alt_basename2 = template_basename.replace(" - '", " - 39").replace(
            " - &#39;", " - 39"
        )
        alt_basename3 = (
            template_basename.replace("'", "39")
            .replace("&#39;", "39")
            .replace(" - ", " - 39")
        )
        # Handle parentheses removal (common yt-dlp transformation)
        no_parens = re.sub(r"[()]", "", template_basename)
        no_parens_spaces = re.sub(r"[()]", " ", template_basename).replace("  ", " ")
        # Handle period removal after abbreviations
        no_periods = template_basename.replace("ft.", "ft").replace("feat.", "feat")
        # Combined transformations
        combined = (
            re.sub(r"[()]", "", template_basename)
            .replace("ft.", "ft")
            .replace("feat.", "feat")
        )

        # 3. Create flexible pattern that allows for minor variations
        flexible_pattern = re.escape(template_basename[:15])  # First 15 chars

        # More comprehensive search patterns
        search_patterns.extend(
            [
                f"{template_basename}.*",  # Original template
                f"{decoded_basename}.*",  # HTML decoded
                f"{alt_basename1}.*",  # Quote variations
                f"{alt_basename2}.*",  # Quote variations with context
                f"{alt_basename3}.*",  # Quote variations with separator
                f"{no_parens}.*",  # Parentheses removed
                f"{no_parens_spaces}.*",  # Parentheses replaced with spaces
                f"{no_periods}.*",  # Periods removed from abbreviations
                f"{combined}.*",  # Combined transformations
                f"*{template_basename[:10]}*",  # Partial start match
                f"*{flexible_pattern[:10]}*",  # Flexible partial match
                f"*{template_basename.split(' - ')[0]}*{template_basename.split(' - ')[-1][:10]}*",  # Artist + partial title
            ]
        )

        # Search for files using glob patterns
        for pattern in search_patterns:
            glob_pattern = os.path.join(output_dir, pattern)
            matches = glob.glob(glob_pattern)

            # Filter for video files
            video_matches = [
                m
                for m in matches
                if any(
                    m.lower().endswith(f".{ext}")
                    for ext in ["mp4", "mkv", "webm", "avi", "mov", "flv"]
                )
            ]

            if video_matches:
                best_file = YtDlpFileDetection._score_and_select_best_match(
                    video_matches, template_basename
                )
                logger.debug(
                    f"Found pattern match: {best_file} using pattern: {pattern}"
                )
                return best_file

        return None

    @staticmethod
    def _score_and_select_best_match(
        video_matches: list, template_basename: str
    ) -> str:
        """
        Score multiple file matches and select the best one.

        Scoring algorithm:
        1. Count how many significant keywords from template appear in filename
        2. Select files with highest keyword match score
        3. Among those, pick the largest file (best quality)

        Args:
            video_matches: List of potential matching file paths
            template_basename: Original template basename for keyword extraction

        Returns:
            Path to the best matching file
        """
        # Filter matches by title similarity to avoid wrong files
        title_keywords = [
            word.lower() for word in template_basename.split() if len(word) > 3
        ]

        if len(video_matches) > 1 and title_keywords:
            # Score each match by how many title keywords it contains
            def score_match(file_path):
                filename = os.path.basename(file_path).lower()
                score = sum(1 for keyword in title_keywords if keyword in filename)
                return score

            # Get matches with the highest keyword score
            scored_matches = [(score_match(f), f) for f in video_matches]
            max_score = max(scored_matches, key=lambda x: x[0])[0]

            if max_score > 0:  # At least one keyword match
                best_matches = [f for score, f in scored_matches if score == max_score]
                # Among the best keyword matches, pick the largest file
                best_file = max(
                    best_matches,
                    key=lambda f: (os.path.getsize(f) if os.path.exists(f) else 0),
                )
            else:
                # No keyword matches, fall back to largest file
                best_file = max(
                    video_matches,
                    key=lambda f: (os.path.getsize(f) if os.path.exists(f) else 0),
                )
        else:
            # Single match or no keywords, take first/largest
            best_file = (
                video_matches[0]
                if len(video_matches) == 1
                else max(
                    video_matches,
                    key=lambda f: (os.path.getsize(f) if os.path.exists(f) else 0),
                )
            )

        return best_file

    @staticmethod
    def _try_fallback_match(output_dir: str, template_basename: str) -> Optional[str]:
        """
        Fallback strategy: Look for recent video files with title similarity.

        Searches for .mp4 files modified within the last 5 minutes that
        contain significant words from the expected title.

        Args:
            output_dir: Directory to search in
            template_basename: Expected basename for similarity matching

        Returns:
            Path to recent similar file if found, None otherwise
        """
        try:
            current_time = time.time()
            recent_threshold = 300  # 5 minutes

            for file_path in glob.glob(os.path.join(output_dir, "*.mp4")):
                if os.path.exists(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age < recent_threshold:
                        # Check if filename has any similarity to expected title
                        if any(
                            word.lower() in os.path.basename(file_path).lower()
                            for word in template_basename.split()
                            if len(word) > 3
                        ):
                            logger.debug(f"Found recent similar file: {file_path}")
                            return file_path
        except Exception as e:
            logger.debug(f"Fallback search failed: {e}")

        return None
