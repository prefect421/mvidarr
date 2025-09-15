"""
MVidarr Advanced Image Operations - Phase 2 Week 21
Complete image processing optimization with advanced features
"""

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    from PIL import ExifTags, Image, ImageEnhance, ImageFilter, ImageOps
    from PIL.ExifTags import GPSTAGS, TAGS

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

try:
    import cv2
    import numpy as np

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None
    np = None

from src.services.image_thread_pool import get_image_processing_pool
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.advanced_image")


class ImageFormat(Enum):
    """Supported image formats"""

    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"
    TIFF = "TIFF"
    BMP = "BMP"
    GIF = "GIF"


class ImageQuality(Enum):
    """Image quality levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    ULTRA = "ultra"


@dataclass
class ImageMetadata:
    """Comprehensive image metadata structure"""

    # Basic information
    file_path: str
    filename: str
    file_size: int
    format: str
    mode: str
    width: int
    height: int
    aspect_ratio: float
    megapixels: float

    # Quality metrics
    estimated_quality: ImageQuality = ImageQuality.MEDIUM
    sharpness_score: Optional[float] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    saturation: Optional[float] = None

    # Color information
    dominant_colors: List[Tuple[int, int, int]] = field(default_factory=list)
    color_palette: List[Tuple[int, int, int]] = field(default_factory=list)
    has_transparency: bool = False

    # EXIF data
    exif_data: Dict[str, Any] = field(default_factory=dict)
    gps_data: Optional[Dict[str, Any]] = None
    camera_info: Optional[Dict[str, str]] = None
    datetime_taken: Optional[str] = None

    # Technical details
    compression_ratio: Optional[float] = None
    color_depth: Optional[int] = None
    dpi: Optional[Tuple[int, int]] = None

    # Analysis timestamps
    processed_at: float = field(default_factory=time.time)
    processing_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "file_path": self.file_path,
            "filename": self.filename,
            "file_size": self.file_size,
            "format": self.format,
            "mode": self.mode,
            "dimensions": {"width": self.width, "height": self.height},
            "aspect_ratio": self.aspect_ratio,
            "megapixels": self.megapixels,
            "quality": {
                "estimated_quality": self.estimated_quality.value,
                "sharpness_score": self.sharpness_score,
                "brightness": self.brightness,
                "contrast": self.contrast,
                "saturation": self.saturation,
            },
            "colors": {
                "dominant_colors": self.dominant_colors,
                "color_palette": self.color_palette,
                "has_transparency": self.has_transparency,
            },
            "exif": self.exif_data,
            "gps": self.gps_data,
            "camera": self.camera_info,
            "datetime_taken": self.datetime_taken,
            "technical": {
                "compression_ratio": self.compression_ratio,
                "color_depth": self.color_depth,
                "dpi": self.dpi,
            },
            "processing": {
                "processed_at": self.processed_at,
                "processing_time": self.processing_time,
            },
        }


@dataclass
class ConversionSpec:
    """Image format conversion specification"""

    target_format: ImageFormat
    quality: int = 85
    optimize: bool = True
    progressive: bool = False  # For JPEG
    lossless: bool = False  # For WEBP
    method: int = 6  # PNG compression level
    suffix: str = ""

    @property
    def file_extension(self) -> str:
        return f".{self.target_format.value.lower()}"


class AdvancedImageAnalyzer:
    """Advanced image analysis with comprehensive metadata extraction"""

    def __init__(self, max_workers: Optional[int] = None):
        """Initialize advanced image analyzer"""
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL/Pillow not available - required for image analysis")

        self.max_workers = max_workers or min(os.cpu_count() * 2, 12)
        logger.info(
            f"🔍 Advanced image analyzer initialized with {self.max_workers} workers"
        )

    def _extract_exif_data(
        self, img: Image.Image
    ) -> Tuple[Dict, Optional[Dict], Optional[Dict]]:
        """Extract EXIF, GPS, and camera information"""
        exif_data = {}
        gps_data = None
        camera_info = None

        try:
            if hasattr(img, "_getexif") and img._getexif():
                exif = img._getexif()

                # Standard EXIF data
                for tag_id, value in exif.items():
                    tag_name = TAGS.get(tag_id, tag_id)

                    # Handle GPS data specially
                    if tag_name == "GPSInfo" and isinstance(value, dict):
                        gps_data = {}
                        for gps_tag_id, gps_value in value.items():
                            gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                            gps_data[gps_tag_name] = str(gps_value)
                    else:
                        exif_data[tag_name] = str(value)

                # Extract camera information
                camera_info = {}
                camera_fields = ["Make", "Model", "LensModel", "Software"]
                for field in camera_fields:
                    if field in exif_data:
                        camera_info[field.lower()] = exif_data[field]

        except Exception as e:
            logger.warning(f"⚠️ Failed to extract EXIF data: {e}")

        return exif_data, gps_data, camera_info

    def _analyze_image_quality(
        self, img: Image.Image, cv_img: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """Analyze image quality metrics"""
        quality_metrics = {}

        try:
            if OPENCV_AVAILABLE and cv_img is not None:
                # Convert to grayscale for analysis
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

                # Sharpness (Laplacian variance)
                quality_metrics["sharpness_score"] = cv2.Laplacian(
                    gray, cv2.CV_64F
                ).var()

                # Brightness and contrast
                quality_metrics["brightness"] = np.mean(gray)
                quality_metrics["contrast"] = np.std(gray)

                # Color analysis if original image available
                hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
                quality_metrics["saturation"] = np.mean(hsv[:, :, 1])

            # PIL-based quality estimation
            if img.mode == "RGB":
                # Simple quality estimation based on file size vs dimensions
                expected_size = img.width * img.height * 3 * 0.5  # Rough estimate
                # This would require file size, which we'll get from caller
                quality_metrics["pil_quality_estimate"] = 1.0

        except Exception as e:
            logger.warning(f"⚠️ Failed to analyze image quality: {e}")

        return quality_metrics

    def _extract_color_info(self, img: Image.Image) -> Dict[str, Any]:
        """Extract color information including dominant colors and palette"""
        color_info = {
            "dominant_colors": [],
            "color_palette": [],
            "has_transparency": False,
        }

        try:
            # Check for transparency
            color_info["has_transparency"] = (
                img.mode in ("RGBA", "LA") or "transparency" in img.info
            )

            # Convert to RGB for color analysis
            if img.mode != "RGB":
                rgb_img = img.convert("RGB")
            else:
                rgb_img = img

            # Get dominant colors by quantizing to a small palette
            quantized = rgb_img.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
            palette = quantized.getpalette()

            # Extract the color palette
            if palette:
                for i in range(0, min(len(palette), 24), 3):  # Max 8 colors
                    color = (palette[i], palette[i + 1], palette[i + 2])
                    color_info["color_palette"].append(color)

            # Get the most dominant colors (top 5)
            histogram = quantized.histogram()
            dominant_indices = sorted(
                range(len(histogram)), key=lambda i: histogram[i], reverse=True
            )[:5]

            for idx in dominant_indices:
                if idx * 3 + 2 < len(palette):
                    color = (
                        palette[idx * 3],
                        palette[idx * 3 + 1],
                        palette[idx * 3 + 2],
                    )
                    color_info["dominant_colors"].append(color)

        except Exception as e:
            logger.warning(f"⚠️ Failed to extract color information: {e}")

        return color_info

    def _analyze_single_image(self, image_path: Path) -> ImageMetadata:
        """Analyze a single image comprehensively"""
        start_time = time.time()

        try:
            # Open image
            with Image.open(image_path) as img:
                # Basic information
                file_stats = image_path.stat()
                basic_info = {
                    "file_path": str(image_path),
                    "filename": image_path.name,
                    "file_size": file_stats.st_size,
                    "format": img.format or "unknown",
                    "mode": img.mode,
                    "width": img.width,
                    "height": img.height,
                    "aspect_ratio": img.width / img.height,
                    "megapixels": (img.width * img.height) / 1_000_000,
                }

                # Extract EXIF data
                exif_data, gps_data, camera_info = self._extract_exif_data(img)

                # Get datetime from EXIF
                datetime_taken = exif_data.get("DateTime") or exif_data.get(
                    "DateTimeOriginal"
                )

                # DPI information
                dpi = img.info.get("dpi", None)

                # Color information
                color_info = self._extract_color_info(img)

                # Prepare for OpenCV analysis if available
                cv_img = None
                if OPENCV_AVAILABLE:
                    try:
                        # Convert PIL to OpenCV format
                        img_array = np.array(img)
                        if img.mode == "RGB":
                            cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                        elif img.mode == "RGBA":
                            cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
                    except Exception as e:
                        logger.debug(f"Could not convert to OpenCV format: {e}")

                # Quality analysis
                quality_metrics = self._analyze_image_quality(img, cv_img)

                # Estimate quality level
                estimated_quality = ImageQuality.MEDIUM
                if quality_metrics.get("sharpness_score", 0) > 100:
                    estimated_quality = ImageQuality.HIGH
                    if quality_metrics.get("sharpness_score", 0) > 300:
                        estimated_quality = ImageQuality.ULTRA
                elif quality_metrics.get("sharpness_score", 0) < 30:
                    estimated_quality = ImageQuality.LOW

                # Compression ratio estimation
                compression_ratio = None
                if basic_info["format"] == "JPEG":
                    # Rough estimate based on file size vs uncompressed size
                    uncompressed_size = img.width * img.height * 3
                    compression_ratio = file_stats.st_size / uncompressed_size

                processing_time = time.time() - start_time

                return ImageMetadata(
                    **basic_info,
                    estimated_quality=estimated_quality,
                    sharpness_score=quality_metrics.get("sharpness_score"),
                    brightness=quality_metrics.get("brightness"),
                    contrast=quality_metrics.get("contrast"),
                    saturation=quality_metrics.get("saturation"),
                    dominant_colors=color_info["dominant_colors"],
                    color_palette=color_info["color_palette"],
                    has_transparency=color_info["has_transparency"],
                    exif_data=exif_data,
                    gps_data=gps_data,
                    camera_info=camera_info,
                    datetime_taken=datetime_taken,
                    compression_ratio=compression_ratio,
                    color_depth=(
                        len(img.getbands()) * 8 if hasattr(img, "getbands") else None
                    ),
                    dpi=dpi,
                    processing_time=processing_time,
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Failed to analyze image {image_path}: {e}")

            # Return minimal metadata for failed analysis
            try:
                file_stats = image_path.stat()
                return ImageMetadata(
                    file_path=str(image_path),
                    filename=image_path.name,
                    file_size=file_stats.st_size,
                    format="unknown",
                    mode="unknown",
                    width=0,
                    height=0,
                    aspect_ratio=0.0,
                    megapixels=0.0,
                    processing_time=processing_time,
                )
            except:
                return ImageMetadata(
                    file_path=str(image_path),
                    filename=image_path.name,
                    file_size=0,
                    format="unknown",
                    mode="unknown",
                    width=0,
                    height=0,
                    aspect_ratio=0.0,
                    megapixels=0.0,
                    processing_time=processing_time,
                )

    async def analyze_image_collection(
        self, image_paths: List[Path], progress_callback: Optional[callable] = None
    ) -> List[ImageMetadata]:
        """Analyze a large collection of images concurrently with caching integration"""
        start_time = time.time()
        pool = get_image_processing_pool()
        cache_manager = await get_media_cache_manager()

        if not pool.pool.is_running():
            await pool.start()

        logger.info(
            f"🔍 Analyzing {len(image_paths)} images using {pool.pool.config.max_workers} workers"
        )

        # Filter existing files
        valid_paths = [p for p in image_paths if p.exists()]
        if len(valid_paths) != len(image_paths):
            logger.warning(
                f"⚠️ {len(image_paths) - len(valid_paths)} image files not found"
            )

        # Check cache for existing analysis results
        cached_results = []
        uncached_paths = []
        cache_hits = 0

        for path in valid_paths:
            cached_analysis = await cache_manager.get(
                CacheType.IMAGE_ANALYSIS, str(path)
            )
            if cached_analysis:
                # Convert cached dict back to ImageMetadata
                metadata = ImageMetadata(**cached_analysis)
                cached_results.append((metadata, str(path)))
                cache_hits += 1
            else:
                uncached_paths.append(path)

        logger.info(
            f"📊 Cache performance: {cache_hits}/{len(valid_paths)} hits ({cache_hits/len(valid_paths)*100:.1f}%)"
        )

        # Process uncached images
        jobs = [(self._analyze_single_image, (path,), {}) for path in uncached_paths]
        results = []
        completed = 0

        # Add cached results first
        for metadata, path in cached_results:
            results.append(metadata)
            completed += 1
            if progress_callback:
                progress_callback(
                    completed, len(valid_paths), f"Cached: {Path(path).name}"
                )

        if uncached_paths:
            with pool.pool.batch_execution(jobs) as batch_futures:
                for future, path in zip(batch_futures, uncached_paths):
                    try:
                        metadata = future.result()
                        results.append(metadata)

                        # Cache the analysis result
                        await cache_manager.set(
                            CacheType.IMAGE_ANALYSIS,
                            str(path),
                            metadata.to_dict(),
                            ttl=3600,  # Cache for 1 hour
                        )

                    except Exception as e:
                        logger.error(f"❌ Image analysis job failed for {path}: {e}")
                        # Create placeholder metadata for failed job
                        failed_metadata = ImageMetadata(
                            file_path=str(path),
                            filename=path.name,
                            file_size=0,
                            format="unknown",
                            mode="unknown",
                            width=0,
                            height=0,
                            aspect_ratio=0.0,
                            megapixels=0.0,
                        )
                        results.append(failed_metadata)

                    completed += 1
                    if progress_callback:
                        progress_callback(
                            completed, len(valid_paths), f"Processed: {path.name}"
                        )

        # Track overall performance
        total_time = time.time() - start_time
        await track_media_processing_time(
            "image_collection_analysis", total_time, f"{len(valid_paths)}_images"
        )

        logger.info(
            f"✅ Image collection analysis completed: {len(results)} images processed in {total_time:.2f}s"
        )
        logger.info(
            f"📊 Performance: {len(valid_paths)/total_time:.1f} images/sec, {cache_hits} cache hits"
        )
        return results


class BulkImageFormatConverter:
    """High-performance bulk image format conversion with concurrent processing"""

    def __init__(self, max_workers: Optional[int] = None):
        """Initialize bulk format converter"""
        if not PIL_AVAILABLE:
            raise RuntimeError(
                "PIL/Pillow not available - required for format conversion"
            )

        self.max_workers = max_workers or min(os.cpu_count() * 2, 10)
        logger.info(
            f"🔄 Bulk format converter initialized with {self.max_workers} workers"
        )

    def _convert_single_image(
        self, source_path: Path, output_path: Path, spec: ConversionSpec
    ) -> Dict[str, Any]:
        """Convert a single image format"""
        start_time = time.time()

        try:
            original_size = source_path.stat().st_size

            with Image.open(source_path) as img:
                # Handle format-specific conversions
                converted_img = img.copy()

                # Convert color mode if necessary
                if spec.target_format == ImageFormat.JPEG and converted_img.mode in (
                    "RGBA",
                    "P",
                    "LA",
                ):
                    # JPEG doesn't support transparency, convert to RGB
                    if converted_img.mode == "P":
                        converted_img = converted_img.convert("RGBA")

                    # Create white background for transparent images
                    background = Image.new("RGB", converted_img.size, (255, 255, 255))
                    if converted_img.mode == "RGBA":
                        background.paste(converted_img, mask=converted_img.split()[3])
                    converted_img = background

                elif (
                    spec.target_format == ImageFormat.PNG
                    and converted_img.mode == "CMYK"
                ):
                    # Convert CMYK to RGB for PNG
                    converted_img = converted_img.convert("RGB")

                # Prepare save arguments
                save_kwargs = {"format": spec.target_format.value}

                if spec.target_format == ImageFormat.JPEG:
                    save_kwargs.update(
                        {
                            "quality": spec.quality,
                            "optimize": spec.optimize,
                            "progressive": spec.progressive,
                        }
                    )
                elif spec.target_format == ImageFormat.PNG:
                    save_kwargs.update(
                        {"optimize": spec.optimize, "compress_level": spec.method}
                    )
                elif spec.target_format == ImageFormat.WEBP:
                    save_kwargs.update(
                        {
                            "quality": spec.quality,
                            "lossless": spec.lossless,
                            "optimize": spec.optimize,
                        }
                    )

                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Save converted image
                converted_img.save(output_path, **save_kwargs)

                converted_size = output_path.stat().st_size
                processing_time = time.time() - start_time

                return {
                    "success": True,
                    "source_path": str(source_path),
                    "output_path": str(output_path),
                    "source_format": img.format,
                    "target_format": spec.target_format.value,
                    "original_size": original_size,
                    "converted_size": converted_size,
                    "size_change": converted_size - original_size,
                    "compression_ratio": (
                        (1 - converted_size / original_size) * 100
                        if original_size > 0
                        else 0
                    ),
                    "processing_time": processing_time,
                    "dimensions": f"{img.width}x{img.height}",
                }

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Format conversion failed for {source_path}: {e}")

            return {
                "success": False,
                "source_path": str(source_path),
                "output_path": str(output_path),
                "error": str(e),
                "processing_time": processing_time,
            }

    async def convert_image_formats(
        self,
        source_paths: List[Path],
        output_dir: Path,
        conversion_specs: List[ConversionSpec],
        progress_callback: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        """Convert multiple images to different formats concurrently"""
        pool = get_image_processing_pool()

        if not pool.pool.is_running():
            await pool.start()

        # Create all conversion jobs (source + spec combinations)
        jobs = []
        for source_path in source_paths:
            if not source_path.exists():
                logger.warning(f"⚠️ Source image not found: {source_path}")
                continue

            for spec in conversion_specs:
                # Generate output filename
                output_name = f"{source_path.stem}{spec.suffix}{spec.file_extension}"
                output_path = output_dir / output_name

                jobs.append(
                    (self._convert_single_image, (source_path, output_path, spec), {})
                )

        logger.info(
            f"🔄 Converting {len(jobs)} images using {pool.pool.config.max_workers} workers"
        )

        results = []
        completed = 0

        with pool.pool.batch_execution(jobs) as batch_futures:
            for future in batch_futures:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"❌ Format conversion job failed: {e}")
                    results.append(
                        {"success": False, "error": str(e), "processing_time": 0.0}
                    )

                completed += 1
                if progress_callback:
                    progress_callback(completed, len(jobs))

        successful = sum(1 for r in results if r.get("success", False))
        logger.info(
            f"✅ Format conversion completed: {successful}/{len(jobs)} successful"
        )

        return results


# Collection analysis and summary functions
def generate_collection_summary(metadata_list: List[ImageMetadata]) -> Dict[str, Any]:
    """Generate comprehensive summary of image collection analysis"""
    if not metadata_list:
        return {"error": "No images to analyze"}

    # Filter successful analyses
    valid_metadata = [m for m in metadata_list if m.width > 0 and m.height > 0]

    if not valid_metadata:
        return {"error": "No valid image metadata found"}

    # Basic statistics
    total_images = len(valid_metadata)
    total_size = sum(m.file_size for m in valid_metadata)
    total_megapixels = sum(m.megapixels for m in valid_metadata)

    # Format distribution
    format_counter = Counter(m.format for m in valid_metadata)

    # Resolution categories
    resolution_categories = {"low": 0, "medium": 0, "high": 0, "ultra": 0}
    for metadata in valid_metadata:
        if metadata.megapixels < 2:
            resolution_categories["low"] += 1
        elif metadata.megapixels < 8:
            resolution_categories["medium"] += 1
        elif metadata.megapixels < 20:
            resolution_categories["high"] += 1
        else:
            resolution_categories["ultra"] += 1

    # Quality distribution
    quality_counter = Counter(m.estimated_quality.value for m in valid_metadata)

    # Average metrics
    avg_dimensions = {
        "width": sum(m.width for m in valid_metadata) / total_images,
        "height": sum(m.height for m in valid_metadata) / total_images,
    }

    # Processing performance
    total_processing_time = sum(m.processing_time for m in valid_metadata)
    avg_processing_time = total_processing_time / total_images

    # Camera information (if available)
    cameras = {}
    for metadata in valid_metadata:
        if metadata.camera_info:
            camera_key = f"{metadata.camera_info.get('make', 'Unknown')} {metadata.camera_info.get('model', 'Unknown')}"
            cameras[camera_key] = cameras.get(camera_key, 0) + 1

    # Date range (if available)
    dates = [m.datetime_taken for m in valid_metadata if m.datetime_taken]
    date_range = None
    if dates:
        dates.sort()
        date_range = {"earliest": dates[0], "latest": dates[-1]}

    return {
        "summary": {
            "total_images": total_images,
            "total_size_mb": total_size / (1024 * 1024),
            "total_megapixels": total_megapixels,
            "average_size_mb": (total_size / total_images) / (1024 * 1024),
            "average_megapixels": total_megapixels / total_images,
        },
        "formats": dict(format_counter),
        "resolutions": resolution_categories,
        "quality_distribution": dict(quality_counter),
        "dimensions": {
            "average_width": int(avg_dimensions["width"]),
            "average_height": int(avg_dimensions["height"]),
            "largest_image": max(
                (m.width * m.height, f"{m.width}x{m.height}") for m in valid_metadata
            )[1],
            "smallest_image": min(
                (m.width * m.height, f"{m.width}x{m.height}") for m in valid_metadata
            )[1],
        },
        "performance": {
            "total_processing_time": total_processing_time,
            "average_processing_time": avg_processing_time,
            "images_per_second": (
                total_images / total_processing_time if total_processing_time > 0 else 0
            ),
        },
        "cameras": cameras,
        "date_range": date_range,
        "metadata_coverage": {
            "exif_data": sum(1 for m in valid_metadata if m.exif_data),
            "gps_data": sum(1 for m in valid_metadata if m.gps_data),
            "camera_info": sum(1 for m in valid_metadata if m.camera_info),
            "datetime_info": sum(1 for m in valid_metadata if m.datetime_taken),
        },
    }


# Convenience functions for task submission
async def analyze_large_image_collection(
    image_paths: List[str], progress_callback: Optional[callable] = None
) -> Tuple[List[ImageMetadata], Dict[str, Any]]:
    """Analyze a large collection of images and generate summary"""
    analyzer = AdvancedImageAnalyzer()
    paths = [Path(p) for p in image_paths]

    # Perform analysis
    metadata_list = await analyzer.analyze_image_collection(paths, progress_callback)

    # Generate summary
    summary = generate_collection_summary(metadata_list)

    return metadata_list, summary


async def bulk_convert_image_formats(
    source_paths: List[str],
    output_dir: str,
    target_formats: List[str],
    quality: int = 85,
    progress_callback: Optional[callable] = None,
) -> List[Dict[str, Any]]:
    """Convert multiple images to different formats"""
    converter = BulkImageFormatConverter()
    paths = [Path(p) for p in source_paths]
    output_path = Path(output_dir)

    # Create conversion specs
    conversion_specs = []
    for fmt in target_formats:
        try:
            image_format = ImageFormat(fmt.upper())
            spec = ConversionSpec(
                target_format=image_format,
                quality=quality,
                optimize=True,
                suffix=f"_converted_{fmt.lower()}",
            )
            conversion_specs.append(spec)
        except ValueError:
            logger.warning(f"⚠️ Unsupported image format: {fmt}")

    if not conversion_specs:
        raise ValueError("No valid image formats specified")

    return await converter.convert_image_formats(
        paths, output_path, conversion_specs, progress_callback
    )
