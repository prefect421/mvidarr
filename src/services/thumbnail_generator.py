"""
MVidarr AI-Powered Thumbnail Generator - Phase 3 Week 25
High-performance thumbnail generation with AI-powered smart selection and optimization
Enhanced with intelligent thumbnail selection using computer vision and quality assessment
"""

import asyncio
import logging
import os
import time
import math
from concurrent.futures import as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any, Callable
from dataclasses import dataclass
import hashlib
import json

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw
    import numpy as np
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    np = None

# AI/ML imports
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None

from src.services.image_thread_pool import get_image_processing_pool, ThreadPoolConfig
from src.services.media_cache_manager import get_media_cache_manager, CacheType
from src.services.performance_monitor import track_media_processing_time
from src.services.ai_content_analyzer import get_ai_content_analyzer, AnalysisType
from src.utils.logger import get_logger

logger = get_logger("mvidarr.thumbnail_generator")


@dataclass
class ThumbnailConfig:
    """Configuration for thumbnail generation"""
    width: int
    height: int
    quality: int = 85
    format: str = "JPEG"
    suffix: str = ""
    maintain_aspect: bool = True
    enhance_sharpness: bool = False
    enhance_contrast: bool = False
    
    @property
    def size(self) -> Tuple[int, int]:
        return (self.width, self.height)
    
    @property
    def filename_suffix(self) -> str:
        return self.suffix or f"_{self.width}x{self.height}"
    
    def __str__(self) -> str:
        return f"{self.width}x{self.height}_{self.format.lower()}_q{self.quality}"


@dataclass
class ThumbnailResult:
    """Result of thumbnail generation"""
    success: bool
    source_path: str
    thumbnail_path: Optional[str] = None
    config: Optional[ThumbnailConfig] = None
    file_size: Optional[int] = None
    processing_time: float = 0.0
    error: Optional[str] = None
    cached: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "source_path": self.source_path,
            "thumbnail_path": self.thumbnail_path,
            "config": f"{self.config}" if self.config else None,
            "file_size": self.file_size,
            "processing_time": self.processing_time,
            "error": self.error,
            "cached": self.cached
        }


class ThumbnailCache:
    """Cache system for generated thumbnails"""
    
    def __init__(self, cache_dir: Path):
        """Initialize thumbnail cache"""
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_index_file = cache_dir / "thumbnail_cache.json"
        self.cache_index = self._load_cache_index()
    
    def _load_cache_index(self) -> Dict:
        """Load cache index from disk"""
        try:
            if self.cache_index_file.exists():
                with open(self.cache_index_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Could not load thumbnail cache index: {e}")
        return {}
    
    def _save_cache_index(self):
        """Save cache index to disk"""
        try:
            with open(self.cache_index_file, 'w') as f:
                json.dump(self.cache_index, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Could not save thumbnail cache index: {e}")
    
    def _get_cache_key(self, source_path: Path, config: ThumbnailConfig) -> str:
        """Generate cache key for source file and config"""
        # Include file modification time and size for cache invalidation
        try:
            stat = source_path.stat()
            key_data = f"{source_path}:{stat.st_mtime}:{stat.st_size}:{config}"
            return hashlib.md5(key_data.encode()).hexdigest()
        except OSError:
            # File doesn't exist, use path + config only
            key_data = f"{source_path}:{config}"
            return hashlib.md5(key_data.encode()).hexdigest()
    
    def get_cached_thumbnail(self, source_path: Path, config: ThumbnailConfig) -> Optional[Path]:
        """Get cached thumbnail if available and valid"""
        cache_key = self._get_cache_key(source_path, config)
        
        if cache_key in self.cache_index:
            cached_path = Path(self.cache_index[cache_key]["path"])
            if cached_path.exists():
                logger.debug(f"📦 Using cached thumbnail: {cached_path}")
                return cached_path
            else:
                # Remove invalid cache entry
                del self.cache_index[cache_key]
                self._save_cache_index()
        
        return None
    
    def cache_thumbnail(self, source_path: Path, thumbnail_path: Path, config: ThumbnailConfig):
        """Add thumbnail to cache"""
        cache_key = self._get_cache_key(source_path, config)
        
        self.cache_index[cache_key] = {
            "path": str(thumbnail_path),
            "source": str(source_path),
            "config": str(config),
            "created": time.time(),
            "size": thumbnail_path.stat().st_size if thumbnail_path.exists() else 0
        }
        
        self._save_cache_index()
    
    def clear_cache(self) -> int:
        """Clear all cached thumbnails"""
        cleared = 0
        for entry in self.cache_index.values():
            cached_path = Path(entry["path"])
            if cached_path.exists():
                try:
                    cached_path.unlink()
                    cleared += 1
                except OSError as e:
                    logger.warning(f"⚠️ Could not delete cached thumbnail {cached_path}: {e}")
        
        self.cache_index.clear()
        self._save_cache_index()
        
        logger.info(f"🗑️ Cleared {cleared} cached thumbnails")
        return cleared


class ConcurrentThumbnailGenerator:
    """High-performance thumbnail generator with concurrent processing"""
    
    # Predefined thumbnail configurations
    THUMBNAIL_PRESETS = {
        "small": ThumbnailConfig(150, 150, suffix="_thumb_small"),
        "medium": ThumbnailConfig(300, 300, suffix="_thumb_medium"),
        "large": ThumbnailConfig(600, 600, suffix="_thumb_large"),
        "preview": ThumbnailConfig(1200, 800, suffix="_preview"),  # 3:2 aspect ratio
        "square": ThumbnailConfig(400, 400, suffix="_square", maintain_aspect=False),
        "banner": ThumbnailConfig(1200, 300, suffix="_banner", maintain_aspect=False)
    }
    
    def __init__(self, output_dir: Path, cache_dir: Optional[Path] = None,
                 thread_pool_config: Optional[ThreadPoolConfig] = None):
        """
        Initialize concurrent thumbnail generator
        
        Args:
            output_dir: Directory for generated thumbnails
            cache_dir: Directory for thumbnail cache (optional)
            thread_pool_config: Thread pool configuration (optional)
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL/Pillow not available - required for thumbnail generation")
        
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup caching
        if cache_dir:
            self.cache = ThumbnailCache(cache_dir)
        else:
            self.cache = ThumbnailCache(output_dir / ".thumbnail_cache")
        
        # Setup thread pool
        self.thread_pool_config = thread_pool_config
        self._processing_pool = None
        
        logger.info(f"🖼️ Thumbnail generator initialized: output={output_dir}")
    
    async def _generate_single_thumbnail(self, source_path: Path, config: ThumbnailConfig) -> ThumbnailResult:
        """Generate a single thumbnail (thread worker function) with Redis caching integration"""
        start_time = time.time()
        
        try:
            # Check Redis cache first for thumbnail metadata
            cache_manager = await get_media_cache_manager()
            cache_key = f"{source_path}_{config.width}x{config.height}_{config.format}"
            cached_thumbnail = await cache_manager.get(CacheType.THUMBNAIL, cache_key)
            
            if cached_thumbnail and Path(cached_thumbnail["path"]).exists():
                await track_media_processing_time("thumbnail_generation_cached", time.time() - start_time, str(source_path))
                return ThumbnailResult(
                    success=True,
                    source_path=str(source_path),
                    thumbnail_path=cached_thumbnail["path"],
                    config=config,
                    file_size=cached_thumbnail["file_size"],
                    processing_time=time.time() - start_time,
                    cached=True
                )
            
            # Check local cache (fallback)
            cached_path = self.cache.get_cached_thumbnail(source_path, config)
            if cached_path:
                # Update Redis cache with local cache info
                thumbnail_info = {
                    "path": str(cached_path),
                    "file_size": cached_path.stat().st_size,
                    "width": config.width,
                    "height": config.height,
                    "format": config.format
                }
                await cache_manager.set(CacheType.THUMBNAIL, cache_key, thumbnail_info, ttl=86400)  # 24 hours
                
                await track_media_processing_time("thumbnail_generation_local_cached", time.time() - start_time, str(source_path))
                return ThumbnailResult(
                    success=True,
                    source_path=str(source_path),
                    thumbnail_path=str(cached_path),
                    config=config,
                    file_size=cached_path.stat().st_size,
                    processing_time=time.time() - start_time,
                    cached=True
                )
            
            # Generate thumbnail
            with Image.open(source_path) as img:
                # Convert to RGB if needed
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                original_size = img.size
                
                # Calculate target size
                if config.maintain_aspect:
                    # Maintain aspect ratio
                    img_ratio = img.width / img.height
                    config_ratio = config.width / config.height
                    
                    if img_ratio > config_ratio:
                        # Image is wider - fit to width
                        new_width = config.width
                        new_height = int(config.width / img_ratio)
                    else:
                        # Image is taller - fit to height
                        new_height = config.height
                        new_width = int(config.height * img_ratio)
                    
                    target_size = (new_width, new_height)
                else:
                    # Force exact dimensions
                    target_size = config.size
                
                # Resize image with high-quality resampling
                thumbnail = img.resize(target_size, Image.Resampling.LANCZOS)
                
                # Apply enhancements if requested
                if config.enhance_sharpness:
                    enhancer = ImageEnhance.Sharpness(thumbnail)
                    thumbnail = enhancer.enhance(1.2)  # 20% sharpness increase
                
                if config.enhance_contrast:
                    enhancer = ImageEnhance.Contrast(thumbnail)
                    thumbnail = enhancer.enhance(1.1)  # 10% contrast increase
                
                # Generate output filename
                output_name = f"{source_path.stem}{config.filename_suffix}.{config.format.lower()}"
                output_path = self.output_dir / output_name
                
                # Save thumbnail
                save_kwargs = {"format": config.format, "optimize": True}
                if config.format.upper() == "JPEG":
                    save_kwargs["quality"] = config.quality
                    save_kwargs["progressive"] = True
                elif config.format.upper() == "PNG":
                    save_kwargs["compress_level"] = 6
                
                thumbnail.save(output_path, **save_kwargs)
                
                # Cache the result
                self.cache.cache_thumbnail(source_path, output_path, config)
                
                processing_time = time.time() - start_time
                
                return ThumbnailResult(
                    success=True,
                    source_path=str(source_path),
                    thumbnail_path=str(output_path),
                    config=config,
                    file_size=output_path.stat().st_size,
                    processing_time=processing_time,
                    cached=False
                )
                
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Thumbnail generation failed for {source_path}: {e}")
            
            return ThumbnailResult(
                success=False,
                source_path=str(source_path),
                config=config,
                processing_time=processing_time,
                error=str(e)
            )
    
    async def generate_thumbnails_async(self, source_paths: List[Path],
                                      configs: List[ThumbnailConfig],
                                      progress_callback: Optional[Callable] = None) -> List[ThumbnailResult]:
        """
        Generate thumbnails asynchronously using thread pool
        
        Args:
            source_paths: List of source image paths
            configs: List of thumbnail configurations
            progress_callback: Optional progress callback function
            
        Returns:
            List of thumbnail results
        """
        pool = get_image_processing_pool()
        
        if not pool.pool.is_running():
            await pool.start()
        
        # Create all jobs (source + config combinations)
        jobs = []
        for source_path in source_paths:
            if not source_path.exists():
                logger.warning(f"⚠️ Source image not found: {source_path}")
                continue
            
            for config in configs:
                jobs.append((self._generate_single_thumbnail, (source_path, config), {}))
        
        total_jobs = len(jobs)
        results = []
        
        logger.info(f"🖼️ Generating {total_jobs} thumbnails using concurrent processing")
        
        # Execute jobs concurrently
        completed = 0
        with pool.pool.batch_execution(jobs) as batch_futures:
            for future in batch_futures:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"❌ Thumbnail job failed: {e}")
                    results.append(ThumbnailResult(
                        success=False,
                        source_path="unknown",
                        error=str(e)
                    ))
                
                completed += 1
                
                # Update progress
                if progress_callback:
                    progress_callback(completed, total_jobs)
        
        # Generate summary
        successful = sum(1 for r in results if r.success)
        cached = sum(1 for r in results if r.success and r.cached)
        
        logger.info(f"✅ Thumbnail generation completed: {successful}/{total_jobs} successful, {cached} from cache")
        
        return results
    
    async def generate_preset_thumbnails(self, source_paths: List[Path],
                                       presets: List[str] = None,
                                       progress_callback: Optional[Callable] = None) -> List[ThumbnailResult]:
        """
        Generate thumbnails using predefined presets
        
        Args:
            source_paths: List of source image paths
            presets: List of preset names (default: all presets)
            progress_callback: Optional progress callback function
            
        Returns:
            List of thumbnail results
        """
        if presets is None:
            presets = list(self.THUMBNAIL_PRESETS.keys())
        
        configs = []
        for preset in presets:
            if preset in self.THUMBNAIL_PRESETS:
                configs.append(self.THUMBNAIL_PRESETS[preset])
            else:
                logger.warning(f"⚠️ Unknown thumbnail preset: {preset}")
        
        if not configs:
            logger.error("❌ No valid thumbnail presets specified")
            return []
        
        return await self.generate_thumbnails_async(source_paths, configs, progress_callback)
    
    def generate_thumbnails_sync(self, source_paths: List[Path],
                               configs: List[ThumbnailConfig]) -> List[ThumbnailResult]:
        """
        Generate thumbnails synchronously (blocking)
        
        Args:
            source_paths: List of source image paths
            configs: List of thumbnail configurations
            
        Returns:
            List of thumbnail results
        """
        results = []
        
        for source_path in source_paths:
            if not source_path.exists():
                logger.warning(f"⚠️ Source image not found: {source_path}")
                continue
            
            for config in configs:
                result = self._generate_single_thumbnail(source_path, config)
                results.append(result)
        
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get thumbnail cache statistics"""
        total_entries = len(self.cache.cache_index)
        total_size = 0
        valid_entries = 0
        
        for entry in self.cache.cache_index.values():
            cached_path = Path(entry["path"])
            if cached_path.exists():
                valid_entries += 1
                total_size += entry.get("size", 0)
        
        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "invalid_entries": total_entries - valid_entries,
            "total_size_mb": total_size / (1024 * 1024),
            "cache_directory": str(self.cache.cache_dir)
        }
    
    def clear_cache(self) -> int:
        """Clear thumbnail cache"""
        return self.cache.clear_cache()


# Convenience functions for common operations
async def generate_video_thumbnails(video_paths: List[Path], 
                                  output_dir: Path,
                                  presets: List[str] = None) -> List[ThumbnailResult]:
    """Generate thumbnails for video files (poster frames)"""
    generator = ConcurrentThumbnailGenerator(output_dir)
    
    # For now, just generate standard thumbnails
    # In a real implementation, you'd extract video frames first
    return await generator.generate_preset_thumbnails(video_paths, presets)


async def generate_bulk_thumbnails(image_paths: List[Path],
                                 output_dir: Path,
                                 config: ThumbnailConfig = None) -> List[ThumbnailResult]:
    """Generate bulk thumbnails with single configuration"""
    if config is None:
        config = ConcurrentThumbnailGenerator.THUMBNAIL_PRESETS["medium"]
    
    generator = ConcurrentThumbnailGenerator(output_dir)
    return await generator.generate_thumbnails_async(image_paths, [config])


# AI-Powered Thumbnail Selection - Phase 3 Week 25 Enhancement

@dataclass
class SmartThumbnailConfig:
    """Configuration for AI-powered thumbnail selection"""
    width: int
    height: int
    quality: int = 90
    format: str = "JPEG"
    face_detection: bool = True
    content_analysis: bool = True
    composition_analysis: bool = True
    quality_threshold: float = 0.7
    face_priority: float = 0.8
    rule_of_thirds: bool = True
    avoid_edges: bool = True
    min_quality_score: float = 0.5


@dataclass
class ThumbnailCandidate:
    """Candidate thumbnail with scoring"""
    crop_box: Tuple[int, int, int, int]  # (left, top, right, bottom)
    score: float
    has_faces: bool
    face_count: int
    quality_score: float
    composition_score: float
    content_score: float
    reasons: List[str]
    
    @property
    def width(self) -> int:
        return self.crop_box[2] - self.crop_box[0]
    
    @property
    def height(self) -> int:
        return self.crop_box[3] - self.crop_box[1]
    
    @property
    def center(self) -> Tuple[int, int]:
        return ((self.crop_box[0] + self.crop_box[2]) // 2, 
                (self.crop_box[1] + self.crop_box[3]) // 2)


class AIThumbnailSelector:
    """AI-powered intelligent thumbnail selection using computer vision and content analysis"""
    
    def __init__(self):
        """Initialize AI thumbnail selector"""
        self.face_cascade = None
        self._load_face_detection()
        logger.info("🤖 AI Thumbnail Selector initialized")
    
    def _load_face_detection(self):
        """Load OpenCV face detection cascade"""
        if OPENCV_AVAILABLE:
            try:
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                if os.path.exists(cascade_path):
                    self.face_cascade = cv2.CascadeClassifier(cascade_path)
                    logger.info("👤 Face detection loaded successfully")
                else:
                    logger.warning("⚠️ Face detection cascade not found")
            except Exception as e:
                logger.error(f"❌ Face detection loading failed: {e}")
    
    async def select_best_thumbnail_crop(self, 
                                       image_path: Path, 
                                       config: SmartThumbnailConfig) -> ThumbnailCandidate:
        """
        Select the best crop region for thumbnail using AI analysis
        
        Args:
            image_path: Path to source image
            config: Smart thumbnail configuration
            
        Returns:
            Best thumbnail candidate with crop coordinates
        """
        try:
            if not PIL_AVAILABLE or not image_path.exists():
                raise ValueError(f"Invalid image path or PIL not available: {image_path}")
            
            # Load image
            image = Image.open(image_path)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Get AI content analysis
            ai_analysis = None
            if config.content_analysis:
                try:
                    analyzer = await get_ai_content_analyzer()
                    analysis_results = await analyzer.analyze_content(
                        str(image_path), 
                        content_type=analyzer.ContentType.IMAGE,
                        analysis_types=[AnalysisType.QUALITY_ASSESSMENT, AnalysisType.COLOR_ANALYSIS]
                    )
                    if analysis_results:
                        ai_analysis = analysis_results[0]  # Use first result
                except Exception as e:
                    logger.warning(f"⚠️ AI analysis failed, using basic selection: {e}")
            
            # Generate candidate crops
            candidates = await self._generate_thumbnail_candidates(
                image, config, ai_analysis
            )
            
            # Score candidates
            scored_candidates = []
            for candidate in candidates:
                score = await self._score_thumbnail_candidate(
                    image, candidate, config, ai_analysis
                )
                scored_candidates.append(score)
            
            # Select best candidate
            if scored_candidates:
                best_candidate = max(scored_candidates, key=lambda c: c.score)
                logger.info(f"🎯 Selected best thumbnail crop with score: {best_candidate.score:.2f}")
                return best_candidate
            else:
                # Fallback to center crop
                return self._create_fallback_candidate(image, config)
                
        except Exception as e:
            logger.error(f"❌ AI thumbnail selection failed: {e}")
            # Return center crop as fallback
            image = Image.open(image_path)
            return self._create_fallback_candidate(image, config)
    
    async def _generate_thumbnail_candidates(self, 
                                           image: Image.Image, 
                                           config: SmartThumbnailConfig,
                                           ai_analysis = None) -> List[ThumbnailCandidate]:
        """Generate potential thumbnail crop candidates"""
        candidates = []
        img_width, img_height = image.size
        target_ratio = config.width / config.height
        
        # Face detection candidates
        if config.face_detection and self.face_cascade and OPENCV_AVAILABLE:
            face_candidates = await self._generate_face_centered_candidates(
                image, config, target_ratio
            )
            candidates.extend(face_candidates)
        
        # Rule of thirds candidates
        if config.rule_of_thirds:
            thirds_candidates = self._generate_rule_of_thirds_candidates(
                img_width, img_height, config, target_ratio
            )
            candidates.extend(thirds_candidates)
        
        # Center and corner candidates
        center_candidates = self._generate_center_candidates(
            img_width, img_height, config, target_ratio
        )
        candidates.extend(center_candidates)
        
        # Content-aware candidates (if AI analysis available)
        if ai_analysis and config.content_analysis:
            content_candidates = await self._generate_content_aware_candidates(
                image, ai_analysis, config, target_ratio
            )
            candidates.extend(content_candidates)
        
        return candidates
    
    async def _generate_face_centered_candidates(self, 
                                               image: Image.Image, 
                                               config: SmartThumbnailConfig,
                                               target_ratio: float) -> List[ThumbnailCandidate]:
        """Generate candidates centered on detected faces"""
        candidates = []
        
        try:
            # Convert to OpenCV format for face detection
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
            
            if len(faces) > 0:
                # Create candidates for each face
                for (x, y, w, h) in faces:
                    face_center_x = x + w // 2
                    face_center_y = y + h // 2
                    
                    # Calculate crop box centered on face
                    crop_box = self._calculate_crop_box(
                        face_center_x, face_center_y, 
                        image.size, config, target_ratio
                    )
                    
                    if crop_box:
                        candidates.append(ThumbnailCandidate(
                            crop_box=crop_box,
                            score=0.0,  # Will be scored later
                            has_faces=True,
                            face_count=len(faces),
                            quality_score=0.0,
                            composition_score=0.8,  # High composition score for face-centered
                            content_score=0.0,
                            reasons=["Face-centered crop"]
                        ))
                
                logger.debug(f"👤 Generated {len(candidates)} face-centered candidates")
        
        except Exception as e:
            logger.error(f"❌ Face detection failed: {e}")
        
        return candidates
    
    def _generate_rule_of_thirds_candidates(self, 
                                          img_width: int, 
                                          img_height: int,
                                          config: SmartThumbnailConfig,
                                          target_ratio: float) -> List[ThumbnailCandidate]:
        """Generate candidates using rule of thirds composition"""
        candidates = []
        
        # Rule of thirds intersection points
        third_x1, third_x2 = img_width // 3, 2 * img_width // 3
        third_y1, third_y2 = img_height // 3, 2 * img_height // 3
        
        intersection_points = [
            (third_x1, third_y1), (third_x2, third_y1),
            (third_x1, third_y2), (third_x2, third_y2)
        ]
        
        for center_x, center_y in intersection_points:
            crop_box = self._calculate_crop_box(
                center_x, center_y, (img_width, img_height), config, target_ratio
            )
            
            if crop_box:
                candidates.append(ThumbnailCandidate(
                    crop_box=crop_box,
                    score=0.0,
                    has_faces=False,
                    face_count=0,
                    quality_score=0.0,
                    composition_score=0.7,  # Good composition score for rule of thirds
                    content_score=0.0,
                    reasons=["Rule of thirds composition"]
                ))
        
        return candidates
    
    def _generate_center_candidates(self, 
                                  img_width: int, 
                                  img_height: int,
                                  config: SmartThumbnailConfig,
                                  target_ratio: float) -> List[ThumbnailCandidate]:
        """Generate center-based candidates"""
        candidates = []
        
        # Perfect center
        center_x, center_y = img_width // 2, img_height // 2
        crop_box = self._calculate_crop_box(
            center_x, center_y, (img_width, img_height), config, target_ratio
        )
        
        if crop_box:
            candidates.append(ThumbnailCandidate(
                crop_box=crop_box,
                score=0.0,
                has_faces=False,
                face_count=0,
                quality_score=0.0,
                composition_score=0.5,  # Neutral composition score for center
                content_score=0.0,
                reasons=["Center crop"]
            ))
        
        # Slightly offset centers (to avoid perfect symmetry)
        offsets = [(0.1, 0.1), (-0.1, 0.1), (0.1, -0.1), (-0.1, -0.1)]
        for offset_x, offset_y in offsets:
            offset_center_x = int(center_x + offset_x * img_width * 0.1)
            offset_center_y = int(center_y + offset_y * img_height * 0.1)
            
            crop_box = self._calculate_crop_box(
                offset_center_x, offset_center_y, 
                (img_width, img_height), config, target_ratio
            )
            
            if crop_box:
                candidates.append(ThumbnailCandidate(
                    crop_box=crop_box,
                    score=0.0,
                    has_faces=False,
                    face_count=0,
                    quality_score=0.0,
                    composition_score=0.4,
                    content_score=0.0,
                    reasons=["Offset center crop"]
                ))
        
        return candidates
    
    async def _generate_content_aware_candidates(self, 
                                               image: Image.Image,
                                               ai_analysis,
                                               config: SmartThumbnailConfig,
                                               target_ratio: float) -> List[ThumbnailCandidate]:
        """Generate candidates based on AI content analysis"""
        candidates = []
        
        try:
            # Use AI analysis to identify interesting regions
            results = ai_analysis.results
            
            # If we have color analysis, focus on areas with dominant colors
            if 'dominant_colors' in results:
                # This is a simplified approach - in reality, you'd analyze
                # color distribution and focus on regions with interesting colors
                img_width, img_height = image.size
                
                # Generate candidates in regions that might have interesting content
                # Based on the golden ratio
                golden_ratio = 1.618
                golden_x = int(img_width / golden_ratio)
                golden_y = int(img_height / golden_ratio)
                
                for center_x, center_y in [(golden_x, golden_y), 
                                         (img_width - golden_x, golden_y),
                                         (golden_x, img_height - golden_y)]:
                    crop_box = self._calculate_crop_box(
                        center_x, center_y, (img_width, img_height), 
                        config, target_ratio
                    )
                    
                    if crop_box:
                        candidates.append(ThumbnailCandidate(
                            crop_box=crop_box,
                            score=0.0,
                            has_faces=False,
                            face_count=0,
                            quality_score=0.0,
                            composition_score=0.6,
                            content_score=0.7,  # Higher content score for AI-guided
                            reasons=["AI content analysis guided"]
                        ))
        
        except Exception as e:
            logger.error(f"❌ Content-aware candidate generation failed: {e}")
        
        return candidates
    
    def _calculate_crop_box(self, 
                          center_x: int, 
                          center_y: int, 
                          image_size: Tuple[int, int],
                          config: SmartThumbnailConfig,
                          target_ratio: float) -> Optional[Tuple[int, int, int, int]]:
        """Calculate crop box given center point and target ratio"""
        img_width, img_height = image_size
        
        # Calculate crop dimensions maintaining aspect ratio
        if target_ratio > (img_width / img_height):
            # Width-constrained
            crop_width = min(img_width, int(img_height * target_ratio))
            crop_height = int(crop_width / target_ratio)
        else:
            # Height-constrained
            crop_height = min(img_height, int(img_width / target_ratio))
            crop_width = int(crop_height * target_ratio)
        
        # Calculate crop box coordinates
        half_width = crop_width // 2
        half_height = crop_height // 2
        
        left = max(0, min(center_x - half_width, img_width - crop_width))
        top = max(0, min(center_y - half_height, img_height - crop_height))
        right = left + crop_width
        bottom = top + crop_height
        
        # Validate crop box
        if right <= img_width and bottom <= img_height and left >= 0 and top >= 0:
            return (left, top, right, bottom)
        
        return None
    
    async def _score_thumbnail_candidate(self, 
                                       image: Image.Image,
                                       candidate: ThumbnailCandidate,
                                       config: SmartThumbnailConfig,
                                       ai_analysis = None) -> ThumbnailCandidate:
        """Score a thumbnail candidate based on multiple criteria"""
        
        try:
            # Extract crop region
            crop = image.crop(candidate.crop_box)
            
            # Quality scoring
            quality_score = await self._assess_crop_quality(crop)
            candidate.quality_score = quality_score
            
            # Face scoring
            face_score = 0.0
            if candidate.has_faces:
                face_score = config.face_priority * (1.0 + candidate.face_count * 0.1)
            
            # Edge avoidance scoring
            edge_score = 0.0
            if config.avoid_edges:
                edge_score = self._calculate_edge_avoidance_score(
                    candidate.crop_box, image.size
                )
            
            # Content scoring (if AI analysis available)
            content_score = candidate.content_score
            if ai_analysis and config.content_analysis:
                content_score *= ai_analysis.confidence
            
            # Calculate final score
            final_score = (
                quality_score * 0.3 +
                face_score * 0.3 +
                candidate.composition_score * 0.2 +
                content_score * 0.1 +
                edge_score * 0.1
            )
            
            candidate.score = final_score
            
            # Update reasons
            if quality_score > 0.8:
                candidate.reasons.append("High image quality")
            if face_score > 0.5:
                candidate.reasons.append("Contains faces")
            if edge_score > 0.7:
                candidate.reasons.append("Good positioning")
            
            return candidate
            
        except Exception as e:
            logger.error(f"❌ Candidate scoring failed: {e}")
            candidate.score = 0.0
            return candidate
    
    async def _assess_crop_quality(self, crop_image: Image.Image) -> float:
        """Assess the quality of a crop region"""
        try:
            if not OPENCV_AVAILABLE or not np:
                return 0.5  # Default neutral score
            
            # Convert to OpenCV format
            cv_crop = cv2.cvtColor(np.array(crop_image), cv2.COLOR_RGB2BGR)
            gray_crop = cv2.cvtColor(cv_crop, cv2.COLOR_BGR2GRAY)
            
            # Calculate sharpness (Laplacian variance)
            sharpness = cv2.Laplacian(gray_crop, cv2.CV_64F).var()
            normalized_sharpness = min(1.0, sharpness / 1000.0)
            
            # Calculate contrast (standard deviation)
            contrast = np.std(gray_crop) / 255.0
            
            # Calculate brightness balance
            brightness = np.mean(gray_crop) / 255.0
            brightness_balance = 1.0 - abs(brightness - 0.5) * 2
            
            # Combine quality metrics
            quality_score = (
                normalized_sharpness * 0.4 +
                contrast * 0.3 +
                brightness_balance * 0.3
            )
            
            return min(1.0, quality_score)
            
        except Exception as e:
            logger.error(f"❌ Quality assessment failed: {e}")
            return 0.5
    
    def _calculate_edge_avoidance_score(self, 
                                      crop_box: Tuple[int, int, int, int],
                                      image_size: Tuple[int, int]) -> float:
        """Calculate score based on distance from image edges"""
        left, top, right, bottom = crop_box
        img_width, img_height = image_size
        
        # Calculate distance from each edge (normalized)
        left_dist = left / img_width
        top_dist = top / img_height
        right_dist = (img_width - right) / img_width
        bottom_dist = (img_height - bottom) / img_height
        
        # Score based on minimum distance to any edge
        min_edge_dist = min(left_dist, top_dist, right_dist, bottom_dist)
        
        # Give higher scores to crops that are more centered
        return min_edge_dist * 2  # Scale to 0-1 range
    
    def _create_fallback_candidate(self, 
                                 image: Image.Image, 
                                 config: SmartThumbnailConfig) -> ThumbnailCandidate:
        """Create fallback center crop candidate"""
        img_width, img_height = image.size
        center_x, center_y = img_width // 2, img_height // 2
        target_ratio = config.width / config.height
        
        crop_box = self._calculate_crop_box(
            center_x, center_y, (img_width, img_height), config, target_ratio
        )
        
        if crop_box is None:
            # Ultimate fallback - entire image
            crop_box = (0, 0, img_width, img_height)
        
        return ThumbnailCandidate(
            crop_box=crop_box,
            score=0.5,
            has_faces=False,
            face_count=0,
            quality_score=0.5,
            composition_score=0.5,
            content_score=0.5,
            reasons=["Fallback center crop"]
        )


class SmartThumbnailGenerator(ConcurrentThumbnailGenerator):
    """Enhanced thumbnail generator with AI-powered selection"""
    
    def __init__(self, output_dir: Path, cache_dir: Path = None, 
                 thread_pool_config: ThreadPoolConfig = None):
        """Initialize smart thumbnail generator"""
        super().__init__(output_dir, cache_dir, thread_pool_config)
        self.ai_selector = AIThumbnailSelector()
        logger.info("🧠 Smart Thumbnail Generator initialized")
    
    async def generate_smart_thumbnail(self, 
                                     source_path: Path, 
                                     config: SmartThumbnailConfig) -> ThumbnailResult:
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
                    cached=True
                )
            
            # Use AI to select best crop
            best_candidate = await self.ai_selector.select_best_thumbnail_crop(
                source_path, config
            )
            
            # Load and crop image
            image = Image.open(source_path)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Apply AI-selected crop
            cropped_image = image.crop(best_candidate.crop_box)
            
            # Resize to target dimensions
            thumbnail = cropped_image.resize(
                (config.width, config.height), 
                Image.Resampling.LANCZOS
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
                    "reasons": best_candidate.reasons
                },
                ttl=86400  # 24 hours
            )
            
            processing_time = time.time() - start_time
            
            result = ThumbnailResult(
                success=True,
                source_path=str(source_path),
                thumbnail_path=str(output_path),
                config=ThumbnailConfig(config.width, config.height, config.quality),
                file_size=output_path.stat().st_size,
                processing_time=processing_time,
                cached=False
            )
            
            # Add AI-specific metadata
            result.ai_score = best_candidate.score
            result.ai_reasons = best_candidate.reasons
            result.has_faces = best_candidate.has_faces
            
            await track_media_processing_time("smart_thumbnail_generation", processing_time, str(source_path))
            
            logger.info(f"🧠 Smart thumbnail generated: {output_path.name} (score: {best_candidate.score:.2f})")
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Smart thumbnail generation failed: {e}")
            
            return ThumbnailResult(
                success=False,
                source_path=str(source_path),
                config=ThumbnailConfig(config.width, config.height, config.quality),
                processing_time=processing_time,
                error=str(e)
            )


# Enhanced convenience functions with AI capabilities
async def generate_smart_thumbnails(image_paths: List[Path],
                                  output_dir: Path,
                                  config: SmartThumbnailConfig = None) -> List[ThumbnailResult]:
    """Generate AI-optimized thumbnails for multiple images"""
    if config is None:
        config = SmartThumbnailConfig(width=512, height=384)
    
    generator = SmartThumbnailGenerator(output_dir)
    results = []
    
    for image_path in image_paths:
        result = await generator.generate_smart_thumbnail(image_path, config)
        results.append(result)
    
    logger.info(f"🧠 Generated {len([r for r in results if r.success])} smart thumbnails")
    return results


async def compare_ai_vs_standard_thumbnails(image_path: Path,
                                          output_dir: Path,
                                          config: SmartThumbnailConfig) -> Dict[str, ThumbnailResult]:
    """Compare AI-generated vs standard thumbnails for quality assessment"""
    
    # Generate smart thumbnail
    smart_generator = SmartThumbnailGenerator(output_dir)
    smart_result = await smart_generator.generate_smart_thumbnail(image_path, config)
    
    # Generate standard thumbnail
    standard_config = ThumbnailConfig(config.width, config.height, config.quality)
    standard_generator = ConcurrentThumbnailGenerator(output_dir)
    standard_result = await standard_generator._generate_single_thumbnail(image_path, standard_config)
    
    return {
        "smart": smart_result,
        "standard": standard_result
    }