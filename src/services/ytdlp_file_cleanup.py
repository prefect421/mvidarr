"""
File Cleanup Operations for yt-dlp Service
Handles post-download file management and quality version cleanup

Extracted from ytdlp_service.py as part of code cleanup.
"""

import os
import re

from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ytdlp_file_cleanup")


def cleanup_old_quality_versions(new_file_path: str, new_file_size: int):
    """
    Clean up old lower-quality versions after successful quality upgrade
    Keeps only the newest/largest version to save disk space

    Args:
        new_file_path: Path to the new higher-quality video file
        new_file_size: Size of the new file in bytes
    """
    try:
        if not new_file_path or not os.path.exists(new_file_path):
            logger.warning(f"Cannot cleanup: new file doesn't exist: {new_file_path}")
            return

        # Get directory and base filename
        directory = os.path.dirname(new_file_path)
        new_filename = os.path.basename(new_file_path)
        new_basename = os.path.splitext(new_filename)[0]

        # Remove "(Quality Upgrade)" suffix if present for matching
        base_pattern = re.sub(r"\s*\(Quality Upgrade\)", "", new_basename)

        logger.info(f"Cleaning up old quality versions for: {base_pattern}")

        # Find all related files (same base name, different quality)
        related_files = []
        for file in os.listdir(directory):
            if file == new_filename:
                continue  # Skip the new file itself

            # Match files with same base pattern
            file_basename = os.path.splitext(file)[0]
            file_pattern = re.sub(r"\s*\(Quality Upgrade\)", "", file_basename)

            if file_pattern == base_pattern or base_pattern in file_pattern:
                full_path = os.path.join(directory, file)
                if os.path.isfile(full_path):
                    file_size = os.path.getsize(full_path)
                    # Only consider video files smaller than the new file
                    if (
                        file.endswith((".mp4", ".webm", ".mkv", ".avi", ".mov"))
                        and file_size < new_file_size
                    ):
                        related_files.append((full_path, file, file_size))

        if not related_files:
            logger.info("No old quality versions found to clean up")
            return

        # Delete old quality versions
        deleted_count = 0
        space_freed = 0
        for file_path, filename, file_size in related_files:
            try:
                os.remove(file_path)
                deleted_count += 1
                space_freed += file_size
                logger.info(
                    f"Deleted old quality version: {filename} ({file_size/(1024*1024):.1f}MB)"
                )

                # Also delete associated files (.info.json, .vtt, etc.)
                base_path = os.path.splitext(file_path)[0]
                for ext in [".info.json", ".vtt", ".srt", ".webp", ".jpg", ".meta"]:
                    assoc_file = base_path + ext
                    if os.path.exists(assoc_file):
                        try:
                            os.remove(assoc_file)
                            logger.debug(
                                f"Deleted associated file: {os.path.basename(assoc_file)}"
                            )
                        except Exception:
                            pass

            except Exception as e:
                logger.warning(f"Failed to delete old version {filename}: {e}")

        if deleted_count > 0:
            logger.info(
                f"Cleanup complete: Deleted {deleted_count} old versions, freed {space_freed/(1024*1024):.1f}MB"
            )

    except Exception as e:
        logger.error(f"Error during old quality cleanup: {e}")
