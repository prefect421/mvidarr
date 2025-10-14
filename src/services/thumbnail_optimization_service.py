"""
Thumbnail optimization service for MVidarr
Provides WebP conversion and storage optimization
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.thumbnail_optimization")


class ThumbnailOptimizationService:
    """Service for optimizing thumbnail storage and format"""

    def __init__(self):
        self.thumbnails_dir = self._get_thumbnails_directory()
        self.webp_quality = int(settings.get("webp_quality", 85))
        self.webp_lossless = settings.get("webp_lossless", "false").lower() == "true"
        self.optimization_stats = {
            "conversions": 0,
            "space_saved": 0,
            "errors": 0,
            "last_run": None,
        }

    def _get_thumbnails_directory(self) -> Path:
        """Get the thumbnails directory path"""
        thumbnails_path = settings.get("thumbnails_path", "data/thumbnails")
        return Path(thumbnails_path)

    def convert_to_webp(
        self, input_path: Path, output_path: Path, quality: int = None
    ) -> bool:
        """
        Convert image to WebP format with optimization

        Args:
            input_path: Path to input image
            output_path: Path for WebP output
            quality: WebP quality (1-100), uses default if None

        Returns:
            True if conversion successful, False otherwise
        """
        try:
            quality = quality or self.webp_quality

            # Open and process image
            with Image.open(input_path) as img:
                # Convert to RGB if necessary (WebP doesn't support all modes)
                if img.mode not in ("RGB", "RGBA"):
                    if img.mode == "P" and "transparency" in img.info:
                        img = img.convert("RGBA")
                    else:
                        img = img.convert("RGB")

                # Save as WebP with optimization
                save_kwargs = {
                    "format": "WebP",
                    "optimize": True,
                    "method": 6,  # Best compression method
                }

                if self.webp_lossless:
                    save_kwargs["lossless"] = True
                else:
                    save_kwargs["quality"] = quality

                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                img.save(output_path, **save_kwargs)

                # Calculate space savings
                original_size = input_path.stat().st_size
                webp_size = output_path.stat().st_size
                space_saved = original_size - webp_size

                self.optimization_stats["conversions"] += 1
                self.optimization_stats["space_saved"] += space_saved

                logger.info(
                    f"Converted {input_path.name} to WebP: {original_size} -> {webp_size} bytes ({space_saved} saved)"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to convert {input_path} to WebP: {e}")
            self.optimization_stats["errors"] += 1
            return False

    def optimize_existing_thumbnails(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Convert existing thumbnails to WebP format

        Args:
            dry_run: If True, only analyze without converting

        Returns:
            Dictionary with optimization results
        """
        results = {
            "analyzed": 0,
            "converted": 0,
            "errors": 0,
            "space_saved": 0,
            "dry_run": dry_run,
            "files_processed": [],
        }

        # Image extensions to convert
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}

        # Process all thumbnail directories
        for subdirectory in ["artists", "videos"]:
            thumbnail_dir = self.thumbnails_dir / subdirectory
            if not thumbnail_dir.exists():
                continue

            # Process files in the main directory first
            directories_to_process = [thumbnail_dir]

            # Process all size directories
            for size_dir in ["small", "medium", "large", "original"]:
                size_path = thumbnail_dir / size_dir
                if size_path.exists():
                    directories_to_process.append(size_path)

            # Process all directories
            for current_dir in directories_to_process:
                # Process all image files
                for img_file in current_dir.iterdir():
                    if not img_file.is_file():
                        continue

                    if img_file.suffix.lower() not in image_extensions:
                        continue

                    # Skip if already WebP
                    if img_file.suffix.lower() == ".webp":
                        continue

                    results["analyzed"] += 1

                    # Create WebP output path
                    webp_name = img_file.stem + ".webp"
                    webp_path = size_path / webp_name

                    # Skip if WebP version already exists
                    if webp_path.exists():
                        logger.debug(f"WebP version already exists: {webp_path}")
                        continue

                    file_info = {
                        "original_path": str(img_file),
                        "webp_path": str(webp_path),
                        "original_size": img_file.stat().st_size,
                        "webp_size": 0,
                        "space_saved": 0,
                        "success": False,
                    }

                    if not dry_run:
                        # Convert to WebP
                        if self.convert_to_webp(img_file, webp_path):
                            file_info["webp_size"] = webp_path.stat().st_size
                            file_info["space_saved"] = (
                                file_info["original_size"] - file_info["webp_size"]
                            )
                            file_info["success"] = True
                            results["converted"] += 1
                            results["space_saved"] += file_info["space_saved"]

                            # Remove original file after successful conversion
                            try:
                                img_file.unlink()
                                logger.info(f"Removed original file: {img_file}")
                            except Exception as e:
                                logger.warning(
                                    f"Could not remove original file {img_file}: {e}"
                                )
                        else:
                            results["errors"] += 1
                    else:
                        # Estimate space savings for dry run
                        estimated_webp_size = int(
                            file_info["original_size"] * 0.7
                        )  # Estimate 30% reduction
                        file_info["webp_size"] = estimated_webp_size
                        file_info["space_saved"] = (
                            file_info["original_size"] - estimated_webp_size
                        )
                        file_info["success"] = True
                        results["space_saved"] += file_info["space_saved"]

                    results["files_processed"].append(file_info)

        self.optimization_stats["last_run"] = datetime.now().isoformat()

        logger.info(
            f"Thumbnail optimization {'analysis' if dry_run else 'completed'}: "
            f"{results['analyzed']} analyzed, {results['converted']} converted, "
            f"{results['space_saved']} bytes saved"
        )

        return results

    def create_optimized_sizes(
        self, source_path: Path, base_name: str, subdirectory: str = "videos"
    ) -> Dict[str, str]:
        """
        Create optimized thumbnail sizes in WebP format

        Args:
            source_path: Path to source image
            base_name: Base name for output files
            subdirectory: Subdirectory (artists/videos)

        Returns:
            Dictionary mapping size names to file paths
        """
        sizes = {
            "small": (150, 150),
            "medium": (300, 300),
            "large": (600, 600),
            "original": None,  # Keep original size
        }

        created_files = {}

        try:
            with Image.open(source_path) as img:
                # Convert to RGB if necessary
                if img.mode not in ("RGB", "RGBA"):
                    if img.mode == "P" and "transparency" in img.info:
                        img = img.convert("RGBA")
                    else:
                        img = img.convert("RGB")

                for size_name, dimensions in sizes.items():
                    # Create output path
                    output_dir = self.thumbnails_dir / subdirectory / size_name
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_path = output_dir / f"{base_name}.webp"

                    # Resize image if dimensions specified
                    if dimensions:
                        # Use thumbnail method to maintain aspect ratio
                        img_resized = img.copy()
                        img_resized.thumbnail(dimensions, Image.Resampling.LANCZOS)

                        # Create new image with exact dimensions and paste resized image
                        new_img = Image.new("RGB", dimensions, (255, 255, 255))

                        # Calculate position to center the image
                        x = (dimensions[0] - img_resized.width) // 2
                        y = (dimensions[1] - img_resized.height) // 2

                        if img_resized.mode == "RGBA":
                            new_img.paste(img_resized, (x, y), img_resized)
                        else:
                            new_img.paste(img_resized, (x, y))

                        save_img = new_img
                    else:
                        save_img = img

                    # Save as WebP
                    save_kwargs = {
                        "format": "WebP",
                        "optimize": True,
                        "method": 6,
                    }

                    if self.webp_lossless:
                        save_kwargs["lossless"] = True
                    else:
                        save_kwargs["quality"] = self.webp_quality

                    save_img.save(output_path, **save_kwargs)
                    created_files[size_name] = str(output_path)

                    logger.debug(f"Created {size_name} thumbnail: {output_path}")

        except Exception as e:
            logger.error(f"Failed to create optimized sizes for {source_path}: {e}")

        return created_files

    def cleanup_duplicate_thumbnails(self) -> Dict[str, Any]:
        """
        Find and remove duplicate thumbnails to save space

        Returns:
            Dictionary with cleanup results
        """
        results = {
            "analyzed": 0,
            "duplicates_found": 0,
            "space_saved": 0,
            "files_removed": [],
        }

        # Dictionary to track file hashes
        file_hashes = {}

        # Process all thumbnail directories
        for subdirectory in ["artists", "videos"]:
            thumbnail_dir = self.thumbnails_dir / subdirectory
            if not thumbnail_dir.exists():
                continue

            # Process all files recursively
            for img_file in thumbnail_dir.rglob("*"):
                if not img_file.is_file():
                    continue

                if img_file.suffix.lower() not in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif",
                }:
                    continue

                results["analyzed"] += 1

                # Calculate file hash
                try:
                    with open(img_file, "rb") as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()

                    if file_hash in file_hashes:
                        # Duplicate found
                        original_file = file_hashes[file_hash]

                        # Keep the WebP version if one exists
                        if (
                            img_file.suffix.lower() == ".webp"
                            and original_file.suffix.lower() != ".webp"
                        ):
                            # Remove original, keep WebP
                            file_size = original_file.stat().st_size
                            original_file.unlink()
                            results["files_removed"].append(str(original_file))
                            file_hashes[file_hash] = img_file
                        elif (
                            img_file.suffix.lower() != ".webp"
                            and original_file.suffix.lower() == ".webp"
                        ):
                            # Remove current, keep existing WebP
                            file_size = img_file.stat().st_size
                            img_file.unlink()
                            results["files_removed"].append(str(img_file))
                        else:
                            # Keep smaller file
                            if img_file.stat().st_size < original_file.stat().st_size:
                                file_size = original_file.stat().st_size
                                original_file.unlink()
                                results["files_removed"].append(str(original_file))
                                file_hashes[file_hash] = img_file
                            else:
                                file_size = img_file.stat().st_size
                                img_file.unlink()
                                results["files_removed"].append(str(img_file))

                        results["duplicates_found"] += 1
                        results["space_saved"] += file_size

                    else:
                        file_hashes[file_hash] = img_file

                except Exception as e:
                    logger.warning(f"Could not process file {img_file}: {e}")

        logger.info(
            f"Duplicate cleanup completed: {results['duplicates_found']} duplicates removed, "
            f"{results['space_saved']} bytes saved"
        )

        return results

    def analyze_storage_usage(self) -> Dict[str, Any]:
        """
        Analyze current thumbnail storage usage

        Returns:
            Dictionary with storage analysis
        """
        analysis = {
            "total_files": 0,
            "total_size": 0,
            "by_format": {},
            "by_size": {},
            "by_category": {},
            "optimization_potential": 0,
        }

        # Process all thumbnail directories
        for subdirectory in ["artists", "videos"]:
            thumbnail_dir = self.thumbnails_dir / subdirectory
            if not thumbnail_dir.exists():
                continue

            category_stats = {"files": 0, "size": 0}

            for img_file in thumbnail_dir.rglob("*"):
                if not img_file.is_file():
                    continue

                if img_file.suffix.lower() not in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif",
                }:
                    continue

                file_size = img_file.stat().st_size
                file_format = img_file.suffix.lower()

                # Update totals
                analysis["total_files"] += 1
                analysis["total_size"] += file_size
                category_stats["files"] += 1
                category_stats["size"] += file_size

                # Update format stats
                if file_format not in analysis["by_format"]:
                    analysis["by_format"][file_format] = {"files": 0, "size": 0}
                analysis["by_format"][file_format]["files"] += 1
                analysis["by_format"][file_format]["size"] += file_size

                # Update size category stats
                size_category = img_file.parent.name
                if size_category not in analysis["by_size"]:
                    analysis["by_size"][size_category] = {"files": 0, "size": 0}
                analysis["by_size"][size_category]["files"] += 1
                analysis["by_size"][size_category]["size"] += file_size

                # Calculate optimization potential (non-WebP files)
                if file_format != ".webp":
                    analysis["optimization_potential"] += int(
                        file_size * 0.3
                    )  # Estimate 30% savings

            analysis["by_category"][subdirectory] = category_stats

        # Add optimization stats
        analysis["optimization_stats"] = self.optimization_stats.copy()

        return analysis

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """
        Get recommendations for thumbnail optimization

        Returns:
            List of optimization recommendations
        """
        recommendations = []
        analysis = self.analyze_storage_usage()

        # Check for non-WebP files
        non_webp_files = sum(
            stats["files"]
            for format_name, stats in analysis["by_format"].items()
            if format_name != ".webp"
        )
        non_webp_size = sum(
            stats["size"]
            for format_name, stats in analysis["by_format"].items()
            if format_name != ".webp"
        )

        if non_webp_files > 0:
            recommendations.append(
                {
                    "type": "format_conversion",
                    "priority": "high",
                    "description": f"Convert {non_webp_files} non-WebP files to WebP format",
                    "potential_savings": int(non_webp_size * 0.3),
                    "action": "optimize_existing_thumbnails",
                }
            )

        # Check for large files
        large_files = analysis["by_size"].get("original", {}).get("files", 0)
        if large_files > 100:
            recommendations.append(
                {
                    "type": "size_optimization",
                    "priority": "medium",
                    "description": f"{large_files} original size thumbnails may be unnecessarily large",
                    "potential_savings": "Variable",
                    "action": "review_original_sizes",
                }
            )

        # Check for duplicate potential
        if analysis["total_files"] > 1000:
            recommendations.append(
                {
                    "type": "duplicate_cleanup",
                    "priority": "medium",
                    "description": "Large collection may have duplicates",
                    "potential_savings": "Variable",
                    "action": "cleanup_duplicate_thumbnails",
                }
            )

        # Check optimization stats
        if self.optimization_stats["errors"] > 0:
            recommendations.append(
                {
                    "type": "error_review",
                    "priority": "low",
                    "description": f'{self.optimization_stats["errors"]} optimization errors need review',
                    "potential_savings": 0,
                    "action": "review_optimization_errors",
                }
            )

        return recommendations


# Global instance
thumbnail_optimization_service = ThumbnailOptimizationService()
