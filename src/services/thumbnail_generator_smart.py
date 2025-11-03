"""
Thumbnail Generator - Smart Module
Enhanced thumbnail generator with AI-powered selection
"""

import time
from pathlib import Path
from typing import Dict, List

try:
    from PIL import Image, ImageEnhance

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

from src.services.image_thread_pool import ThreadPoolConfig
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.services.thumbnail_ai_selector import AIThumbnailSelector
from src.services.thumbnail_generator_base import ConcurrentThumbnailGenerator
from src.services.thumbnail_models import (
    SmartThumbnailConfig,
    ThumbnailConfig,
    ThumbnailResult,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.thumbnail_generator_smart")


class SmartThumbnailGenerator(ConcurrentThumbnailGenerator):
    """Enhanced thumbnail generator with AI-powered selection"""

    def __init__(
        self,
        output_dir: Path,
        cache_dir: Path = None,
        thread_pool_config: ThreadPoolConfig = None,
    ):
        """Initialize smart thumbnail generator"""
        super().__init__(output_dir, cache_dir, thread_pool_config)
        self.ai_selector = AIThumbnailSelector()
        logger.info("🧠 Smart Thumbnail Generator initialized")

    async def generate_smart_thumbnail(
        self, source_path: Path, config: SmartThumbnailConfig
    ) -> ThumbnailResult:
        """Generate optimized thumbnail using AI selection"""
        start_time = time.time()

        try:
            if not source_path.exists():
                raise FileNotFoundError(f"Source image not found: {source_path}")

            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"smart_thumb_{source_path}_{config.width}x{config.height}"
            cached_result = await cache_manager.get(CacheType.THUMBNAIL, cache_key)

            if cached_result and Path(cached_result["path"]).exists():
                return ThumbnailResult(
                    success=True,
                    source_path=str(source_path),
                    thumbnail_path=cached_result["path"],
                    config=ThumbnailConfig(config.width, config.height, config.quality),
                    file_size=cached_result["file_size"],
                    processing_time=time.time() - start_time,
                    cached=True,
                )

            # Use AI to select best crop
            best_candidate = await self.ai_selector.select_best_thumbnail_crop(
                source_path, config
            )

            # Load and crop image
            image = Image.open(source_path)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Apply AI-selected crop
            cropped_image = image.crop(best_candidate.crop_box)

            # Resize to target dimensions
            thumbnail = cropped_image.resize(
                (config.width, config.height), Image.Resampling.LANCZOS
            )

            # Apply quality enhancements based on AI analysis
            if best_candidate.quality_score < 0.7:
                # Enhance sharpness for low-quality regions
                enhancer = ImageEnhance.Sharpness(thumbnail)
                thumbnail = enhancer.enhance(1.3)

                # Enhance contrast if needed
                enhancer = ImageEnhance.Contrast(thumbnail)
                thumbnail = enhancer.enhance(1.2)

            # Generate output filename
            output_name = f"{source_path.stem}_smart_{config.width}x{config.height}.{config.format.lower()}"
            output_path = self.output_dir / output_name

            # Save thumbnail
            save_kwargs = {"format": config.format, "optimize": True}
            if config.format.upper() == "JPEG":
                save_kwargs["quality"] = config.quality
                save_kwargs["progressive"] = True
            elif config.format.upper() == "PNG":
                save_kwargs["compress_level"] = 6

            thumbnail.save(output_path, **save_kwargs)

            # Cache result
            await cache_manager.set(
                CacheType.THUMBNAIL,
                cache_key,
                {
                    "path": str(output_path),
                    "file_size": output_path.stat().st_size,
                    "ai_score": best_candidate.score,
                    "reasons": best_candidate.reasons,
                },
                ttl=86400,  # 24 hours
            )

            processing_time = time.time() - start_time

            result = ThumbnailResult(
                success=True,
                source_path=str(source_path),
                thumbnail_path=str(output_path),
                config=ThumbnailConfig(config.width, config.height, config.quality),
                file_size=output_path.stat().st_size,
                processing_time=processing_time,
                cached=False,
            )

            # Add AI-specific metadata
            result.ai_score = best_candidate.score
            result.ai_reasons = best_candidate.reasons
            result.has_faces = best_candidate.has_faces

            await track_media_processing_time(
                "smart_thumbnail_generation", processing_time, str(source_path)
            )

            logger.info(
                f"🧠 Smart thumbnail generated: {output_path.name} (score: {best_candidate.score:.2f})"
            )

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Smart thumbnail generation failed: {e}")

            return ThumbnailResult(
                success=False,
                source_path=str(source_path),
                config=ThumbnailConfig(config.width, config.height, config.quality),
                processing_time=processing_time,
                error=str(e),
            )


# Enhanced convenience functions with AI capabilities
async def generate_smart_thumbnails(
    image_paths: List[Path], output_dir: Path, config: SmartThumbnailConfig = None
) -> List[ThumbnailResult]:
    """Generate AI-optimized thumbnails for multiple images"""
    if config is None:
        config = SmartThumbnailConfig(width=512, height=384)

    generator = SmartThumbnailGenerator(output_dir)
    results = []

    for image_path in image_paths:
        result = await generator.generate_smart_thumbnail(image_path, config)
        results.append(result)

    logger.info(
        f"🧠 Generated {len([r for r in results if r.success])} smart thumbnails"
    )
    return results


async def compare_ai_vs_standard_thumbnails(
    image_path: Path, output_dir: Path, config: SmartThumbnailConfig
) -> Dict[str, ThumbnailResult]:
    """Compare AI-generated vs standard thumbnails for quality assessment"""

    # Generate smart thumbnail
    smart_generator = SmartThumbnailGenerator(output_dir)
    smart_result = await smart_generator.generate_smart_thumbnail(image_path, config)

    # Generate standard thumbnail
    standard_config = ThumbnailConfig(config.width, config.height, config.quality)
    standard_generator = ConcurrentThumbnailGenerator(output_dir)
    standard_result = await standard_generator._generate_single_thumbnail(
        image_path, standard_config
    )

    return {"smart": smart_result, "standard": standard_result}
