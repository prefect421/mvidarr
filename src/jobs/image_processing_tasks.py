"""
MVidarr Image Processing Tasks - Phase 2 Week 20
Advanced concurrent image processing with thread pool optimization
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class TaskStatus(Enum):
    """Task status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


try:
    from PIL import ExifTags, Image, ImageEnhance, ImageFilter

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
from src.utils.logger import get_logger

logger = get_logger("mvidarr.image_processing")


@dataclass
class ImageProcessingStats:
    """Statistics for image processing operations"""

    total_images: int = 0
    processed_images: int = 0
    failed_images: int = 0
    processing_time: float = 0.0
    average_time_per_image: float = 0.0
    thread_pool_size: int = 0
    memory_usage_mb: float = 0.0


@dataclass
class ThumbnailSpec:
    """Specification for thumbnail generation"""

    width: int
    height: int
    quality: int = 85
    format: str = "JPEG"
    suffix: str = ""

    @property
    def size(self) -> Tuple[int, int]:
        return (self.width, self.height)


class ImageThreadPoolManager:
    """Thread pool manager for concurrent image processing operations"""

    def __init__(self, max_workers: Optional[int] = None):
        """
        Initialize thread pool manager

        Args:
            max_workers: Maximum number of worker threads (default: CPU count * 2)
        """
        if max_workers is None:
            import multiprocessing

            max_workers = min(multiprocessing.cpu_count() * 2, 16)  # Cap at 16 threads

        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(f"🧵 Image thread pool initialized with {max_workers} workers")

    def shutdown(self):
        """Shutdown the thread pool"""
        if self.executor:
            self.executor.shutdown(wait=True)
            logger.info("🧵 Image thread pool shut down")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


class ImageProcessingTask:
    """Base class for image processing tasks with thread pool support"""

    def __init__(self, task_id: str, user_id: int = None):
        self.task_id = task_id
        self.user_id = user_id
        self.status = TaskStatus.PENDING
        self.progress = 0.0
        self.status_message = ""
        self.stats = ImageProcessingStats()
        self.thread_pool_manager: Optional[ImageThreadPoolManager] = None

    def update_status(self, status: TaskStatus, message: str = ""):
        """Update task status"""
        self.status = status
        self.status_message = message
        logger.info(f"📊 Task {self.task_id} status: {status.value} - {message}")

    def update_progress(self, progress: float, status_message: str = ""):
        """Update task progress"""
        self.progress = min(100.0, max(0.0, progress))
        if status_message:
            self.status_message = status_message
        logger.debug(
            f"⏳ Task {self.task_id} progress: {self.progress:.1f}% - {status_message}"
        )

    async def setup(self):
        """Setup image processing environment"""
        if not PIL_AVAILABLE:
            raise RuntimeError(
                "PIL/Pillow not available - required for image processing"
            )

        # Initialize thread pool
        thread_count = min(os.cpu_count() * 2, 12)  # Conservative thread count
        self.thread_pool_manager = ImageThreadPoolManager(max_workers=thread_count)
        self.stats.thread_pool_size = thread_count

        logger.info(
            f"🖼️ Image processing task {self.task_id} initialized with {thread_count} threads"
        )

    async def cleanup(self):
        """Cleanup resources"""
        if self.thread_pool_manager:
            self.thread_pool_manager.shutdown()
            self.thread_pool_manager = None


class BulkThumbnailGenerationTask(ImageProcessingTask):
    """Generate thumbnails for multiple images using thread pools"""

    THUMBNAIL_SPECS = [
        ThumbnailSpec(150, 150, suffix="_thumb_small"),
        ThumbnailSpec(300, 300, suffix="_thumb_medium"),
        ThumbnailSpec(600, 600, suffix="_thumb_large"),
        ThumbnailSpec(1200, 800, suffix="_preview"),  # 16:10 preview ratio
    ]

    def __init__(
        self,
        task_id: str,
        source_paths: List[str],
        output_dir: str,
        specs: Optional[List[ThumbnailSpec]] = None,
        user_id: int = None,
    ):
        super().__init__(task_id, user_id)
        self.source_paths = [Path(p) for p in source_paths]
        self.output_dir = Path(output_dir)
        self.thumbnail_specs = specs or self.THUMBNAIL_SPECS
        self.results: Dict[str, Dict] = {}

    def _generate_single_thumbnail(
        self, source_path: Path, spec: ThumbnailSpec
    ) -> Dict:
        """Generate a single thumbnail (thread worker function)"""
        try:
            start_time = time.time()

            # Open and process image
            with Image.open(source_path) as img:
                # Convert to RGB if needed
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Calculate aspect-preserving size
                img_ratio = img.width / img.height
                spec_ratio = spec.width / spec.height

                if img_ratio > spec_ratio:
                    # Image is wider - fit to width
                    new_width = spec.width
                    new_height = int(spec.width / img_ratio)
                else:
                    # Image is taller - fit to height
                    new_height = spec.height
                    new_width = int(spec.height * img_ratio)

                # Resize with high-quality resampling
                thumbnail = img.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )

                # Create output path
                output_name = f"{source_path.stem}{spec.suffix}.{spec.format.lower()}"
                output_path = self.output_dir / output_name

                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Save thumbnail
                save_kwargs = {"format": spec.format, "optimize": True}
                if spec.format.upper() == "JPEG":
                    save_kwargs["quality"] = spec.quality

                thumbnail.save(output_path, **save_kwargs)

                processing_time = time.time() - start_time

                return {
                    "success": True,
                    "source": str(source_path),
                    "output": str(output_path),
                    "spec": f"{spec.width}x{spec.height}",
                    "size_bytes": output_path.stat().st_size,
                    "processing_time": processing_time,
                }

        except Exception as e:
            logger.error(f"❌ Thumbnail generation failed for {source_path}: {e}")
            return {
                "success": False,
                "source": str(source_path),
                "error": str(e),
                "processing_time": time.time() - start_time,
            }

    async def run(self) -> Dict[str, Any]:
        """Execute bulk thumbnail generation"""
        await self.setup()

        try:
            start_time = time.time()
            self.update_status(TaskStatus.RUNNING)

            # Prepare all thumbnail generation jobs
            jobs = []
            for source_path in self.source_paths:
                if not source_path.exists():
                    logger.warning(f"⚠️ Source image not found: {source_path}")
                    continue

                for spec in self.thumbnail_specs:
                    jobs.append((source_path, spec))

            self.stats.total_images = len(jobs)
            logger.info(
                f"🖼️ Generating {len(jobs)} thumbnails using {self.stats.thread_pool_size} threads"
            )

            # Submit jobs to thread pool
            future_to_job = {}
            for source_path, spec in jobs:
                future = self.thread_pool_manager.executor.submit(
                    self._generate_single_thumbnail, source_path, spec
                )
                future_to_job[future] = (source_path, spec)

            # Process completed jobs
            completed = 0
            for future in as_completed(future_to_job):
                result = future.result()
                source_path, spec = future_to_job[future]

                # Store result
                source_key = str(source_path)
                if source_key not in self.results:
                    self.results[source_key] = {"thumbnails": []}
                self.results[source_key]["thumbnails"].append(result)

                if result["success"]:
                    self.stats.processed_images += 1
                else:
                    self.stats.failed_images += 1

                completed += 1

                # Update progress
                progress = (completed / len(jobs)) * 100
                self.update_progress(
                    progress=progress,
                    status_message=f"Generated {completed}/{len(jobs)} thumbnails",
                )

            # Calculate final stats
            self.stats.processing_time = time.time() - start_time
            if self.stats.processed_images > 0:
                self.stats.average_time_per_image = (
                    self.stats.processing_time / self.stats.processed_images
                )

            success_rate = (
                (self.stats.processed_images / len(jobs)) * 100 if jobs else 0
            )

            self.update_status(TaskStatus.COMPLETED)

            result = {
                "task_id": self.task_id,
                "status": "completed",
                "stats": {
                    "total_jobs": len(jobs),
                    "successful": self.stats.processed_images,
                    "failed": self.stats.failed_images,
                    "success_rate": f"{success_rate:.1f}%",
                    "processing_time": f"{self.stats.processing_time:.2f}s",
                    "average_time_per_thumbnail": f"{self.stats.average_time_per_image:.3f}s",
                    "threads_used": self.stats.thread_pool_size,
                    "thumbnails_per_second": (
                        self.stats.processed_images / self.stats.processing_time
                        if self.stats.processing_time > 0
                        else 0
                    ),
                },
                "results": self.results,
            }

            logger.info(
                f"✅ Bulk thumbnail generation completed: {self.stats.processed_images}/{len(jobs)} successful"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Bulk thumbnail generation failed: {e}")
            self.update_status(TaskStatus.FAILED)
            raise
        finally:
            await self.cleanup()


class ConcurrentImageOptimizationTask(ImageProcessingTask):
    """Optimize multiple images concurrently using thread pools"""

    def __init__(
        self,
        task_id: str,
        source_paths: List[str],
        output_dir: str,
        quality: int = 85,
        max_dimension: Optional[int] = None,
        user_id: int = None,
    ):
        super().__init__(task_id, user_id)
        self.source_paths = [Path(p) for p in source_paths]
        self.output_dir = Path(output_dir)
        self.quality = quality
        self.max_dimension = max_dimension
        self.results: List[Dict] = []

    def _optimize_single_image(self, source_path: Path) -> Dict:
        """Optimize a single image (thread worker function)"""
        try:
            start_time = time.time()
            original_size = source_path.stat().st_size

            with Image.open(source_path) as img:
                # Convert to RGB if needed
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                optimized = img.copy()

                # Resize if max dimension specified
                if (
                    self.max_dimension
                    and max(optimized.width, optimized.height) > self.max_dimension
                ):
                    ratio = self.max_dimension / max(optimized.width, optimized.height)
                    new_size = (
                        int(optimized.width * ratio),
                        int(optimized.height * ratio),
                    )
                    optimized = optimized.resize(new_size, Image.Resampling.LANCZOS)

                # Create output path
                output_path = self.output_dir / f"optimized_{source_path.name}"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Save optimized image
                optimized.save(output_path, "JPEG", quality=self.quality, optimize=True)

                optimized_size = output_path.stat().st_size
                compression_ratio = (1 - optimized_size / original_size) * 100
                processing_time = time.time() - start_time

                return {
                    "success": True,
                    "source": str(source_path),
                    "output": str(output_path),
                    "original_size": original_size,
                    "optimized_size": optimized_size,
                    "compression_ratio": f"{compression_ratio:.1f}%",
                    "processing_time": processing_time,
                    "dimensions": f"{optimized.width}x{optimized.height}",
                }

        except Exception as e:
            logger.error(f"❌ Image optimization failed for {source_path}: {e}")
            return {
                "success": False,
                "source": str(source_path),
                "error": str(e),
                "processing_time": time.time() - start_time,
            }

    async def run(self) -> Dict[str, Any]:
        """Execute concurrent image optimization"""
        await self.setup()

        try:
            start_time = time.time()
            self.update_status(TaskStatus.RUNNING)

            # Filter existing source files
            valid_sources = [p for p in self.source_paths if p.exists()]
            self.stats.total_images = len(valid_sources)

            logger.info(
                f"🖼️ Optimizing {len(valid_sources)} images using {self.stats.thread_pool_size} threads"
            )

            # Submit optimization jobs to thread pool
            future_to_path = {
                self.thread_pool_manager.executor.submit(
                    self._optimize_single_image, path
                ): path
                for path in valid_sources
            }

            # Process completed jobs
            completed = 0
            total_original_size = 0
            total_optimized_size = 0

            for future in as_completed(future_to_path):
                result = future.result()
                self.results.append(result)

                if result["success"]:
                    self.stats.processed_images += 1
                    total_original_size += result["original_size"]
                    total_optimized_size += result["optimized_size"]
                else:
                    self.stats.failed_images += 1

                completed += 1
                progress = (completed / len(valid_sources)) * 100
                self.update_progress(
                    progress=progress,
                    status_message=f"Optimized {completed}/{len(valid_sources)} images",
                )

            # Calculate final stats
            self.stats.processing_time = time.time() - start_time
            if self.stats.processed_images > 0:
                self.stats.average_time_per_image = (
                    self.stats.processing_time / self.stats.processed_images
                )

            overall_compression = (
                (
                    (total_original_size - total_optimized_size)
                    / total_original_size
                    * 100
                )
                if total_original_size > 0
                else 0
            )

            self.update_status(TaskStatus.COMPLETED)

            result = {
                "task_id": self.task_id,
                "status": "completed",
                "stats": {
                    "total_images": len(valid_sources),
                    "successful": self.stats.processed_images,
                    "failed": self.stats.failed_images,
                    "success_rate": (
                        f"{(self.stats.processed_images / len(valid_sources) * 100):.1f}%"
                        if valid_sources
                        else "0%"
                    ),
                    "processing_time": f"{self.stats.processing_time:.2f}s",
                    "average_time_per_image": f"{self.stats.average_time_per_image:.3f}s",
                    "threads_used": self.stats.thread_pool_size,
                    "images_per_second": (
                        self.stats.processed_images / self.stats.processing_time
                        if self.stats.processing_time > 0
                        else 0
                    ),
                    "total_original_size_mb": total_original_size / (1024 * 1024),
                    "total_optimized_size_mb": total_optimized_size / (1024 * 1024),
                    "overall_compression": f"{overall_compression:.1f}%",
                },
                "results": self.results,
            }

            logger.info(
                f"✅ Image optimization completed: {self.stats.processed_images}/{len(valid_sources)} successful"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Image optimization failed: {e}")
            self.update_status(TaskStatus.FAILED)
            raise
        finally:
            await self.cleanup()


class ImageAnalysisTask(ImageProcessingTask):
    """Analyze multiple images concurrently for metadata and quality metrics"""

    def __init__(self, task_id: str, source_paths: List[str], user_id: int = None):
        super().__init__(task_id, user_id)
        self.source_paths = [Path(p) for p in source_paths]
        self.results: List[Dict] = []

    def _analyze_single_image(self, source_path: Path) -> Dict:
        """Analyze a single image (thread worker function)"""
        try:
            start_time = time.time()

            with Image.open(source_path) as img:
                # Basic image information
                analysis = {
                    "success": True,
                    "path": str(source_path),
                    "filename": source_path.name,
                    "format": img.format,
                    "mode": img.mode,
                    "width": img.width,
                    "height": img.height,
                    "aspect_ratio": img.width / img.height,
                    "megapixels": (img.width * img.height) / 1_000_000,
                    "file_size_bytes": source_path.stat().st_size,
                    "file_size_mb": source_path.stat().st_size / (1024 * 1024),
                }

                # Extract EXIF data if available
                if hasattr(img, "_getexif") and img._getexif():
                    exif_data = {}
                    for tag_id, value in img._getexif().items():
                        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                        exif_data[tag_name] = str(value)
                    analysis["exif"] = exif_data

                # Quality assessment using OpenCV if available
                if OPENCV_AVAILABLE:
                    # Convert PIL image to OpenCV format
                    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

                    # Calculate blur metric (Laplacian variance)
                    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                    blur_metric = cv2.Laplacian(gray, cv2.CV_64F).var()
                    analysis["blur_metric"] = blur_metric
                    analysis["sharpness_quality"] = (
                        "high"
                        if blur_metric > 100
                        else "medium"
                        if blur_metric > 30
                        else "low"
                    )

                    # Calculate brightness and contrast
                    analysis["brightness"] = np.mean(gray)
                    analysis["contrast"] = np.std(gray)

                analysis["processing_time"] = time.time() - start_time
                return analysis

        except Exception as e:
            logger.error(f"❌ Image analysis failed for {source_path}: {e}")
            return {
                "success": False,
                "path": str(source_path),
                "filename": source_path.name,
                "error": str(e),
                "processing_time": time.time() - start_time,
            }

    async def run(self) -> Dict[str, Any]:
        """Execute concurrent image analysis"""
        await self.setup()

        try:
            start_time = time.time()
            self.update_status(TaskStatus.RUNNING)

            # Filter existing source files
            valid_sources = [p for p in self.source_paths if p.exists()]
            self.stats.total_images = len(valid_sources)

            logger.info(
                f"🔍 Analyzing {len(valid_sources)} images using {self.stats.thread_pool_size} threads"
            )

            # Submit analysis jobs to thread pool
            future_to_path = {
                self.thread_pool_manager.executor.submit(
                    self._analyze_single_image, path
                ): path
                for path in valid_sources
            }

            # Process completed jobs
            completed = 0
            for future in as_completed(future_to_path):
                result = future.result()
                self.results.append(result)

                if result["success"]:
                    self.stats.processed_images += 1
                else:
                    self.stats.failed_images += 1

                completed += 1
                progress = (completed / len(valid_sources)) * 100
                self.update_progress(
                    progress=progress,
                    status_message=f"Analyzed {completed}/{len(valid_sources)} images",
                )

            # Calculate final stats
            self.stats.processing_time = time.time() - start_time
            if self.stats.processed_images > 0:
                self.stats.average_time_per_image = (
                    self.stats.processing_time / self.stats.processed_images
                )

            # Generate summary statistics
            successful_results = [r for r in self.results if r["success"]]
            summary_stats = {}

            if successful_results:
                total_megapixels = sum(
                    r.get("megapixels", 0) for r in successful_results
                )
                total_file_size_mb = sum(
                    r.get("file_size_mb", 0) for r in successful_results
                )

                summary_stats = {
                    "average_megapixels": total_megapixels / len(successful_results),
                    "total_file_size_mb": total_file_size_mb,
                    "average_file_size_mb": total_file_size_mb
                    / len(successful_results),
                    "format_distribution": {},
                    "resolution_categories": {
                        "low": 0,
                        "medium": 0,
                        "high": 0,
                        "ultra": 0,
                    },
                }

                # Format distribution
                formats = [r.get("format", "unknown") for r in successful_results]
                for fmt in set(formats):
                    summary_stats["format_distribution"][fmt] = formats.count(fmt)

                # Resolution categories
                for result in successful_results:
                    mp = result.get("megapixels", 0)
                    if mp < 2:
                        summary_stats["resolution_categories"]["low"] += 1
                    elif mp < 8:
                        summary_stats["resolution_categories"]["medium"] += 1
                    elif mp < 20:
                        summary_stats["resolution_categories"]["high"] += 1
                    else:
                        summary_stats["resolution_categories"]["ultra"] += 1

            self.update_status(TaskStatus.COMPLETED)

            result = {
                "task_id": self.task_id,
                "status": "completed",
                "stats": {
                    "total_images": len(valid_sources),
                    "successful": self.stats.processed_images,
                    "failed": self.stats.failed_images,
                    "success_rate": (
                        f"{(self.stats.processed_images / len(valid_sources) * 100):.1f}%"
                        if valid_sources
                        else "0%"
                    ),
                    "processing_time": f"{self.stats.processing_time:.2f}s",
                    "average_time_per_image": f"{self.stats.average_time_per_image:.3f}s",
                    "threads_used": self.stats.thread_pool_size,
                    "images_per_second": (
                        self.stats.processed_images / self.stats.processing_time
                        if self.stats.processing_time > 0
                        else 0
                    ),
                },
                "summary": summary_stats,
                "results": self.results,
            }

            logger.info(
                f"✅ Image analysis completed: {self.stats.processed_images}/{len(valid_sources)} successful"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Image analysis failed: {e}")
            self.update_status(TaskStatus.FAILED)
            raise
        finally:
            await self.cleanup()


# Task registry for easy access
IMAGE_PROCESSING_TASKS = {
    "bulk_thumbnail_generation": BulkThumbnailGenerationTask,
    "concurrent_image_optimization": ConcurrentImageOptimizationTask,
    "image_analysis": ImageAnalysisTask,
}


# Convenience functions for task submission
async def submit_bulk_thumbnail_generation(
    source_paths: List[str],
    output_dir: str,
    specs: Optional[List[ThumbnailSpec]] = None,
    user_id: int = None,
) -> str:
    """Submit bulk thumbnail generation task"""
    import uuid

    task_id = f"thumbnail_gen_{uuid.uuid4().hex[:8]}"

    task = BulkThumbnailGenerationTask(
        task_id=task_id,
        source_paths=source_paths,
        output_dir=output_dir,
        specs=specs,
        user_id=user_id,
    )

    # Submit to background job queue
    result = await task.run()
    return task_id


async def submit_concurrent_image_optimization(
    source_paths: List[str],
    output_dir: str,
    quality: int = 85,
    max_dimension: Optional[int] = None,
    user_id: int = None,
) -> str:
    """Submit concurrent image optimization task"""
    import uuid

    task_id = f"image_opt_{uuid.uuid4().hex[:8]}"

    task = ConcurrentImageOptimizationTask(
        task_id=task_id,
        source_paths=source_paths,
        output_dir=output_dir,
        quality=quality,
        max_dimension=max_dimension,
        user_id=user_id,
    )

    # Submit to background job queue
    result = await task.run()
    return task_id


async def submit_image_analysis(source_paths: List[str], user_id: int = None) -> str:
    """Submit image analysis task"""
    import uuid

    task_id = f"image_analysis_{uuid.uuid4().hex[:8]}"

    task = ImageAnalysisTask(
        task_id=task_id, source_paths=source_paths, user_id=user_id
    )

    # Submit to background job queue
    result = await task.run()
    return task_id
