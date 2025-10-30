"""
Thumbnail service for downloading and managing video thumbnails
"""

import hashlib
import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps

from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.thumbnail_service")


class ThumbnailService:
    """Service for downloading and managing video thumbnails"""

    def __init__(self):
        self.thumbnails_dir = self._get_thumbnails_directory()
        self.ensure_thumbnails_directory()

    def _get_thumbnails_directory(self) -> Path:
        """Get the thumbnails directory path"""
        thumbnails_path = settings.get("thumbnails_path", "data/thumbnails")
        # Ensure absolute path
        if not Path(thumbnails_path).is_absolute():
            # Make it relative to the project root
            from pathlib import Path as PathlibPath

            project_root = PathlibPath(__file__).parent.parent.parent
            return project_root / thumbnails_path
        return Path(thumbnails_path)

    def ensure_thumbnails_directory(self):
        """Ensure the thumbnails directory exists"""
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

        # Create subdirectories for organization
        (self.thumbnails_dir / "artists").mkdir(exist_ok=True, mode=0o755)
        (self.thumbnails_dir / "videos").mkdir(exist_ok=True, mode=0o755)
        (self.thumbnails_dir / "uploads").mkdir(exist_ok=True, mode=0o755)
        (self.thumbnails_dir / "playlists").mkdir(exist_ok=True, mode=0o755)

        # Create size-specific directories for multi-size thumbnails
        for entity in ["artists", "videos"]:
            for size in ["small", "medium", "large", "original"]:
                (self.thumbnails_dir / entity / size).mkdir(exist_ok=True, mode=0o755)

        logger.debug(f"Thumbnails directory ensured: {self.thumbnails_dir}")

    def _is_placeholder_url(self, url: str) -> bool:
        """Check if URL is a known placeholder image"""
        if not url:
            return True

        url_lower = url.lower()

        # Known placeholder patterns (same as metadata service)
        placeholder_patterns = [
            # Last.fm placeholder images
            "2a96cbd8b46e442fc41c2b86b821562f.png",
            "lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f",
            "lastfm.freetls.fastly.net/i/u/300x300/4128a6eb29f94943c9d206c08e625904",
            "lastfm.freetls.fastly.net/i/u/300x300/c6f59c1e5e7240a4c0d427abd71f3dbb",
            # Generic placeholders
            "placeholder",
            "default",
            "generic",
            "no-image",
            "blank",
            "missing",
            "unavailable",
            "coming-soon",
            "avatar-default",
            "profile-default",
            "default_artist",
            "artist_placeholder",
            "music_placeholder",
            "album_default",
            "cover_default",
            # Common placeholder files
            "grey.gif",
            "transparent.png",
            "1x1.png",
            "spacer.gif",
            "default.jpg",
            "default.png",
            "placeholder.jpg",
            "placeholder.png",
        ]

        return any(pattern in url_lower for pattern in placeholder_patterns)

    def generate_filename(self, url: str, prefix: str = "") -> str:
        """
        Generate a filename for a thumbnail based on its URL

        Args:
            url: URL of the thumbnail
            prefix: Optional prefix for the filename

        Returns:
            Generated filename
        """
        # Create hash of URL for unique filename
        url_hash = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:12]

        # Try to get extension from URL
        parsed_url = urlparse(url)
        path = parsed_url.path
        extension = Path(path).suffix.lower()

        # Default to .jpg if no extension found
        if not extension or extension not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            extension = ".jpg"

        filename = (
            f"{prefix}{url_hash}{extension}" if prefix else f"{url_hash}{extension}"
        )
        return filename

    def download_thumbnail(
        self, url: str, filename: str = None, subdirectory: str = "videos"
    ) -> Optional[str]:
        """
        Download a thumbnail from a URL

        Args:
            url: URL of the thumbnail to download
            filename: Optional filename (will be generated if not provided)
            subdirectory: Subdirectory to save in (artists/videos)

        Returns:
            Path to downloaded thumbnail or None if failed
        """
        if not url:
            return None

        try:
            # Generate filename if not provided
            if not filename:
                filename = self.generate_filename(url)

            # Determine target directory - ensure absolute path
            target_dir = Path(self.thumbnails_dir).resolve() / subdirectory
            target_dir.mkdir(exist_ok=True, mode=0o755)
            target_path = target_dir / filename

            # Skip if file already exists
            if target_path.exists():
                logger.debug(f"Thumbnail already exists: {target_path}")
                return str(target_path)

            # Download the image
            headers = {"User-Agent": "MVidarr/1.0", "Accept": "image/*"}

            response = requests.get(url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()

            # Check if it's actually an image
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                logger.warning(f"URL does not point to an image: {url}")
                return None

            # Download and save the image
            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify the image is valid and optionally resize
            if self._validate_and_process_image(target_path):
                logger.info(f"Downloaded thumbnail: {target_path}")
                return str(target_path)
            else:
                # Remove invalid image
                target_path.unlink(missing_ok=True)
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download thumbnail from {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading thumbnail: {e}")
            return None

    def _validate_and_process_image(
        self, image_path: Path, max_size: tuple = (800, 600)
    ) -> bool:
        """
        Validate and optionally resize an image

        Args:
            image_path: Path to image file
            max_size: Maximum size (width, height) for resizing

        Returns:
            True if image is valid, False otherwise
        """
        try:
            with Image.open(image_path) as img:
                # Validate image
                img.verify()

                # Reopen for processing (verify closes the file)
                with Image.open(image_path) as img:
                    # Convert to RGB if needed (for JPEG saving)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")

                    # Resize if too large
                    if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)

                        # Save the resized image
                        temp_path = image_path.with_suffix(".tmp")
                        img.save(temp_path, "JPEG", quality=85, optimize=True)

                        # Replace original with resized version
                        temp_path.replace(image_path)

                        logger.debug(f"Resized thumbnail: {image_path}")

                return True

        except Exception as e:
            logger.error(f"Invalid image file {image_path}: {e}")
            return False

    def download_artist_thumbnail(self, artist_name: str, url: str) -> Optional[str]:
        """
        Download thumbnail for an artist

        Args:
            artist_name: Name of the artist
            url: URL of the thumbnail

        Returns:
            Path to downloaded thumbnail or None
        """
        # Additional safety check - don't download known placeholders
        if self._is_placeholder_url(url):
            logger.info(
                f"Refusing to download placeholder thumbnail for {artist_name}: {url}"
            )
            return None
        # Sanitize artist name for filename
        safe_name = "".join(
            c for c in artist_name if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        safe_name = safe_name.replace(" ", "_").lower()

        filename = self.generate_filename(url, f"{safe_name}_")
        return self.download_thumbnail(url, filename, "artists")

    def download_video_thumbnail(
        self, artist_name: str, video_title: str, url: str
    ) -> Optional[str]:
        """
        Download thumbnail for a video

        Args:
            artist_name: Name of the artist
            video_title: Title of the video
            url: URL of the thumbnail

        Returns:
            Path to downloaded thumbnail or None
        """
        # Sanitize names for filename
        safe_artist = "".join(
            c for c in artist_name if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        safe_artist = safe_artist.replace(" ", "_").lower()

        safe_title = "".join(
            c for c in video_title if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        safe_title = safe_title.replace(" ", "_").lower()

        filename = self.generate_filename(url, f"{safe_artist}_{safe_title}_")
        return self.download_thumbnail(url, filename, "videos")

    def download_playlist_thumbnail(
        self, playlist_name: str, url: str
    ) -> Optional[str]:
        """
        Download thumbnail for a playlist

        Args:
            playlist_name: Name of the playlist
            url: URL of the thumbnail

        Returns:
            Path to downloaded thumbnail or None
        """
        # Sanitize playlist name for filename
        safe_name = "".join(
            c for c in playlist_name if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        safe_name = safe_name.replace(" ", "_").lower()

        filename = self.generate_filename(url, f"playlist_{safe_name}_")
        return self.download_thumbnail(url, filename, "playlists")

    def get_thumbnail_path(self, relative_path: str) -> Optional[Path]:
        """
        Get full path to a thumbnail from relative path

        Args:
            relative_path: Relative path to thumbnail

        Returns:
            Full path to thumbnail or None if not found
        """
        if not relative_path:
            return None

        full_path = self.thumbnails_dir / relative_path

        if full_path.exists():
            return full_path

        return None

    def cleanup_orphaned_thumbnails(self) -> int:
        """
        Remove thumbnail files that are no longer referenced in the database

        Returns:
            Number of files removed
        """
        # This would require database access to check for orphaned files
        # For now, just return 0 as a placeholder
        logger.info("Orphaned thumbnail cleanup not implemented yet")
        return 0

    def upload_manual_thumbnail(
        self,
        file_data: bytes,
        filename: str,
        entity_type: str,
        entity_id: int,
        entity_name: str,
    ) -> Optional[Dict]:
        """
        Upload and process a manual thumbnail

        Args:
            file_data: Raw image file data
            filename: Original filename
            entity_type: 'artist' or 'video'
            entity_id: ID of the entity
            entity_name: Name of the entity (for filename generation)

        Returns:
            Dictionary with upload results and file paths
        """
        try:
            # Generate unique identifier for this upload
            upload_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Sanitize entity name for filename
            safe_name = "".join(
                c for c in entity_name if c.isalnum() or c in (" ", "-", "_")
            ).strip()
            safe_name = safe_name.replace(" ", "_").lower()[:50]  # Limit length

            # Determine file extension
            original_ext = Path(filename).suffix.lower()
            if original_ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                original_ext = ".jpg"  # Default to JPEG

            # Create base filename
            base_filename = f"{safe_name}_{timestamp}_{upload_id}"

            # Validate image data
            try:
                image = Image.open(io.BytesIO(file_data))
                image.verify()  # Verify it's a valid image
                image = Image.open(io.BytesIO(file_data))  # Reopen for processing
            except Exception as e:
                logger.error(f"Invalid image data: {e}")
                return None

            # Convert to RGB if needed
            if image.mode in ("RGBA", "P", "LA"):
                # Create white background for transparency
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                if image.mode in ("RGBA", "LA"):
                    background.paste(
                        image, mask=image.split()[-1] if image.mode == "RGBA" else None
                    )
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            # Auto-orient based on EXIF data
            image = ImageOps.exif_transpose(image)

            # Generate multiple sizes
            sizes_config = {
                "small": (150, 150),
                "medium": (300, 300),
                "large": (600, 600),
                "original": None,  # Keep original size
            }

            generated_files = {}
            metadata = {
                "upload_id": upload_id,
                "original_filename": filename,
                "upload_timestamp": datetime.now().isoformat(),
                "original_size": image.size,
                "file_size": len(file_data),
                "format": image.format or "JPEG",
                "sizes": {},
            }

            # Create directory structure
            entity_dir = self.thumbnails_dir / f"{entity_type}s"
            entity_dir.mkdir(exist_ok=True, mode=0o755)

            for size_name, dimensions in sizes_config.items():
                size_dir = entity_dir / size_name
                size_dir.mkdir(exist_ok=True, mode=0o755)

                filename_with_size = f"{base_filename}_{size_name}.jpg"
                file_path = size_dir / filename_with_size

                # Process image for this size
                if dimensions is None:
                    # Original size
                    processed_image = image.copy()
                else:
                    # Resize maintaining aspect ratio
                    processed_image = image.copy()
                    processed_image.thumbnail(dimensions, Image.Resampling.LANCZOS)

                # Save with optimization
                processed_image.save(
                    file_path,
                    "JPEG",
                    quality=90 if size_name == "original" else 85,
                    optimize=True,
                    progressive=True,
                )

                # Store file info
                file_stat = file_path.stat()
                generated_files[size_name] = str(file_path)
                metadata["sizes"][size_name] = {
                    "path": str(file_path),
                    "size": processed_image.size,
                    "file_size": file_stat.st_size,
                    "filename": filename_with_size,
                }

                logger.debug(
                    f"Generated {size_name} thumbnail: {file_path} ({processed_image.size})"
                )

            # Use medium size as the primary thumbnail path
            primary_path = generated_files["medium"]

            result = {
                "success": True,
                "primary_path": primary_path,
                "all_paths": generated_files,
                "metadata": metadata,
                "source": "manual",
                "upload_id": upload_id,
            }

            logger.info(
                f"Successfully uploaded and processed manual thumbnail for {entity_type} {entity_id}: {base_filename}"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to upload manual thumbnail: {e}")
            return None

    def crop_thumbnail(
        self,
        image_path: str,
        crop_box: Tuple[int, int, int, int],
        entity_type: str,
        entity_id: int,
        entity_name: str,
    ) -> Optional[Dict]:
        """
        Crop an existing thumbnail and regenerate sizes

        Args:
            image_path: Path to existing image
            crop_box: (left, top, right, bottom) crop coordinates
            entity_type: 'artist' or 'video'
            entity_id: ID of the entity
            entity_name: Name of the entity

        Returns:
            Dictionary with crop results and new file paths
        """
        try:
            # Load and crop the image
            with Image.open(image_path) as image:
                # Auto-orient based on EXIF data
                image = ImageOps.exif_transpose(image)

                # Validate crop box
                img_width, img_height = image.size
                left, top, right, bottom = crop_box

                if (
                    left < 0
                    or top < 0
                    or right > img_width
                    or bottom > img_height
                    or left >= right
                    or top >= bottom
                ):
                    logger.error(
                        f"Invalid crop box: {crop_box} for image size {image.size}"
                    )
                    return None

                # Perform crop
                cropped_image = image.crop(crop_box)

                # Convert to RGB if needed
                if cropped_image.mode != "RGB":
                    if cropped_image.mode in ("RGBA", "LA"):
                        background = Image.new(
                            "RGB", cropped_image.size, (255, 255, 255)
                        )
                        if cropped_image.mode == "RGBA":
                            background.paste(
                                cropped_image, mask=cropped_image.split()[-1]
                            )
                        cropped_image = background
                    else:
                        cropped_image = cropped_image.convert("RGB")

                # Convert to bytes for reprocessing
                img_buffer = io.BytesIO()
                cropped_image.save(img_buffer, "JPEG", quality=95)
                img_buffer.seek(0)

                # Use upload function to generate new sizes
                upload_result = self.upload_manual_thumbnail(
                    img_buffer.getvalue(),
                    f"cropped_{Path(image_path).name}",
                    entity_type,
                    entity_id,
                    entity_name,
                )

                if upload_result:
                    upload_result["source"] = "manual_crop"
                    upload_result["original_image"] = image_path
                    upload_result["crop_box"] = crop_box
                    logger.info(
                        f"Successfully cropped thumbnail for {entity_type} {entity_id}"
                    )

                return upload_result

        except Exception as e:
            logger.error(f"Failed to crop thumbnail: {e}")
            return None

    def delete_thumbnail_files(
        self, thumbnail_path: str, metadata: Dict = None
    ) -> bool:
        """
        Delete thumbnail files including all generated sizes

        Args:
            thumbnail_path: Primary thumbnail path
            metadata: Thumbnail metadata containing size information

        Returns:
            True if successfully deleted
        """
        try:
            deleted_count = 0

            # If we have metadata with size information, delete all sizes
            if metadata and "sizes" in metadata:
                for size_name, size_info in metadata["sizes"].items():
                    size_path = Path(size_info["path"])
                    if size_path.exists():
                        size_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted thumbnail size {size_name}: {size_path}")
            else:
                # Fallback: try to delete just the primary path
                primary_path = Path(thumbnail_path)
                if primary_path.exists():
                    primary_path.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted primary thumbnail: {primary_path}")

            logger.info(f"Deleted {deleted_count} thumbnail files")
            return deleted_count > 0

        except Exception as e:
            logger.error(f"Failed to delete thumbnail files: {e}")
            return False

    def get_thumbnail_info(self, thumbnail_path: str) -> Optional[Dict]:
        """
        Get information about a thumbnail file

        Args:
            thumbnail_path: Path to thumbnail file

        Returns:
            Dictionary with thumbnail information
        """
        try:
            path = Path(thumbnail_path)
            if not path.exists():
                return None

            with Image.open(path) as image:
                stat = path.stat()

                return {
                    "path": str(path),
                    "size": image.size,
                    "format": image.format,
                    "mode": image.mode,
                    "file_size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }

        except Exception as e:
            logger.error(f"Failed to get thumbnail info: {e}")
            return None

    def get_storage_stats(self) -> dict:
        """
        Get thumbnail storage statistics

        Returns:
            Dictionary with storage statistics
        """
        try:
            stats = {
                "total_files": 0,
                "total_size": 0,
                "artist_thumbnails": 0,
                "video_thumbnails": 0,
                "manual_uploads": 0,
                "auto_generated": 0,
                "by_size": {"small": 0, "medium": 0, "large": 0, "original": 0},
                "thumbnails_directory": str(self.thumbnails_dir),
            }

            for category in ["artists", "videos", "uploads"]:
                category_dir = self.thumbnails_dir / category
                if category_dir.exists():
                    for file_path in category_dir.rglob("*"):
                        if file_path.is_file():
                            stats["total_files"] += 1
                            stats["total_size"] += file_path.stat().st_size

                            # Category counting
                            if category == "artists":
                                stats["artist_thumbnails"] += 1
                            elif category == "videos":
                                stats["video_thumbnails"] += 1
                            elif category == "uploads":
                                stats["manual_uploads"] += 1

                            # Size counting
                            for size in ["small", "medium", "large", "original"]:
                                if (
                                    size in file_path.name
                                    or file_path.parent.name == size
                                ):
                                    stats["by_size"][size] += 1
                                    break

            # Convert size to MB
            stats["total_size_mb"] = round(stats["total_size"] / (1024 * 1024), 2)

            return stats

        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {"error": str(e)}


# Convenience instance
thumbnail_service = ThumbnailService()
