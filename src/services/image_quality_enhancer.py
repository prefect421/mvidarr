"""
MVidarr Image Quality Enhancement Service - Phase 2 Week 21
Automated image quality improvement workflows with concurrent processing
"""

import asyncio
import json
import logging
import math
import os
import time
from concurrent.futures import as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps
    from PIL.ImageFilter import (
        DETAIL,
        EDGE_ENHANCE,
        SHARPEN,
        SMOOTH,
        GaussianBlur,
        UnsharpMask,
    )

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
from src.utils.logger import get_logger

logger = get_logger("mvidarr.image_quality")


class EnhancementType(Enum):
    """Types of image enhancements"""

    AUTO_LEVELS = "auto_levels"
    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    SATURATION = "saturation"
    SHARPNESS = "sharpness"
    COLOR_BALANCE = "color_balance"
    NOISE_REDUCTION = "noise_reduction"
    HISTOGRAM_EQUALIZATION = "histogram_equalization"
    GAMMA_CORRECTION = "gamma_correction"
    WHITE_BALANCE = "white_balance"


class QualityIssue(Enum):
    """Detected quality issues"""

    DARK_IMAGE = "dark_image"
    OVEREXPOSED = "overexposed"
    LOW_CONTRAST = "low_contrast"
    BLURRY = "blurry"
    OVERSATURATED = "oversaturated"
    UNDERSATURATED = "undersaturated"
    COLOR_CAST = "color_cast"
    NOISY = "noisy"
    UNDEREXPOSED = "underexposed"


@dataclass
class EnhancementSettings:
    """Settings for image enhancement operations"""

    brightness_factor: float = 1.0  # 0.0 = black, 1.0 = original, 2.0 = twice as bright
    contrast_factor: float = 1.0  # 0.0 = gray, 1.0 = original, 2.0 = twice contrast
    saturation_factor: float = (
        1.0  # 0.0 = grayscale, 1.0 = original, 2.0 = twice saturation
    )
    sharpness_factor: float = 1.0  # 0.0 = blurred, 1.0 = original, 2.0 = sharpened
    gamma: float = 1.0  # Gamma correction factor
    auto_enhance: bool = True  # Enable automatic enhancements
    preserve_original: bool = True  # Keep original file
    suffix: str = "_enhanced"  # Suffix for enhanced files


@dataclass
class QualityAnalysis:
    """Analysis results for image quality"""

    brightness_level: float  # 0-255 average brightness
    contrast_level: float  # Standard deviation of brightness
    saturation_level: float  # Average saturation (HSV)
    sharpness_score: float  # Laplacian variance for sharpness
    noise_level: float  # Estimated noise level
    histogram_data: Dict[str, List[int]]  # RGB histograms
    detected_issues: List[QualityIssue]
    recommended_enhancements: List[EnhancementType]
    confidence_score: float  # 0-1 confidence in analysis

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brightness_level": self.brightness_level,
            "contrast_level": self.contrast_level,
            "saturation_level": self.saturation_level,
            "sharpness_score": self.sharpness_score,
            "noise_level": self.noise_level,
            "histogram_data": self.histogram_data,
            "detected_issues": [issue.value for issue in self.detected_issues],
            "recommended_enhancements": [
                enh.value for enh in self.recommended_enhancements
            ],
            "confidence_score": self.confidence_score,
        }


@dataclass
class EnhancementResult:
    """Result of image enhancement operation"""

    success: bool
    source_path: str
    enhanced_path: Optional[str] = None
    enhancements_applied: List[EnhancementType] = None
    quality_analysis: Optional[QualityAnalysis] = None
    before_metrics: Optional[Dict[str, float]] = None
    after_metrics: Optional[Dict[str, float]] = None
    processing_time: float = 0.0
    file_size_change: Optional[int] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.enhancements_applied is None:
            self.enhancements_applied = []


class ImageQualityAnalyzer:
    """Analyze image quality and detect common issues"""

    def __init__(self):
        """Initialize quality analyzer"""
        if not PIL_AVAILABLE:
            raise RuntimeError(
                "PIL/Pillow not available - required for quality analysis"
            )

    def analyze_image_quality(
        self, img: Image.Image, cv_img: Optional[np.ndarray] = None
    ) -> QualityAnalysis:
        """Comprehensive quality analysis of an image"""
        try:
            # Convert to RGB if necessary
            if img.mode != "RGB":
                rgb_img = img.convert("RGB")
            else:
                rgb_img = img

            # Basic metrics
            brightness = self._calculate_brightness(rgb_img)
            contrast = self._calculate_contrast(rgb_img)
            saturation = self._calculate_saturation(rgb_img)

            # Advanced metrics with OpenCV if available
            sharpness_score = 0.0
            noise_level = 0.0

            if OPENCV_AVAILABLE and cv_img is not None:
                sharpness_score = self._calculate_sharpness_cv(cv_img)
                noise_level = self._estimate_noise_level(cv_img)
            else:
                sharpness_score = self._calculate_sharpness_pil(rgb_img)

            # Histogram analysis
            histogram_data = self._calculate_histograms(rgb_img)

            # Detect issues
            detected_issues = self._detect_quality_issues(
                brightness,
                contrast,
                saturation,
                sharpness_score,
                noise_level,
                histogram_data,
            )

            # Recommend enhancements
            recommended_enhancements = self._recommend_enhancements(
                detected_issues, brightness, contrast, saturation
            )

            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                img.size, sharpness_score, contrast
            )

            return QualityAnalysis(
                brightness_level=brightness,
                contrast_level=contrast,
                saturation_level=saturation,
                sharpness_score=sharpness_score,
                noise_level=noise_level,
                histogram_data=histogram_data,
                detected_issues=detected_issues,
                recommended_enhancements=recommended_enhancements,
                confidence_score=confidence_score,
            )

        except Exception as e:
            logger.error(f"❌ Quality analysis failed: {e}")
            # Return default analysis
            return QualityAnalysis(
                brightness_level=128.0,
                contrast_level=64.0,
                saturation_level=128.0,
                sharpness_score=50.0,
                noise_level=10.0,
                histogram_data={
                    "red": [0] * 256,
                    "green": [0] * 256,
                    "blue": [0] * 256,
                },
                detected_issues=[],
                recommended_enhancements=[],
                confidence_score=0.0,
            )

    def _calculate_brightness(self, img: Image.Image) -> float:
        """Calculate average brightness (0-255)"""
        grayscale = img.convert("L")
        histogram = grayscale.histogram()
        pixels = sum(histogram)
        brightness = sum(i * histogram[i] for i in range(256)) / pixels
        return brightness

    def _calculate_contrast(self, img: Image.Image) -> float:
        """Calculate contrast as standard deviation of brightness"""
        grayscale = img.convert("L")
        histogram = grayscale.histogram()
        pixels = sum(histogram)

        # Calculate mean
        mean = sum(i * histogram[i] for i in range(256)) / pixels

        # Calculate standard deviation
        variance = sum(((i - mean) ** 2) * histogram[i] for i in range(256)) / pixels
        contrast = math.sqrt(variance)

        return contrast

    def _calculate_saturation(self, img: Image.Image) -> float:
        """Calculate average saturation in HSV color space"""
        hsv_img = img.convert("HSV")
        # Get saturation channel (middle channel in HSV)
        sat_data = list(hsv_img.split()[1].getdata())
        avg_saturation = sum(sat_data) / len(sat_data)
        return avg_saturation

    def _calculate_sharpness_pil(self, img: Image.Image) -> float:
        """Calculate sharpness using PIL edge detection"""
        grayscale = img.convert("L")
        edges = grayscale.filter(ImageFilter.FIND_EDGES)
        # Sum of edge pixels as sharpness measure
        edge_data = list(edges.getdata())
        sharpness = sum(edge_data) / len(edge_data)
        return sharpness

    def _calculate_sharpness_cv(self, cv_img: np.ndarray) -> float:
        """Calculate sharpness using OpenCV Laplacian variance"""
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def _estimate_noise_level(self, cv_img: np.ndarray) -> float:
        """Estimate noise level using OpenCV"""
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        # Use local standard deviation as noise estimate
        kernel = np.ones((3, 3), np.float32) / 9
        mean = cv2.filter2D(gray.astype(np.float32), -1, kernel)
        sqr_diff = (gray.astype(np.float32) - mean) ** 2
        noise_level = np.sqrt(cv2.filter2D(sqr_diff, -1, kernel)).mean()
        return float(noise_level)

    def _calculate_histograms(self, img: Image.Image) -> Dict[str, List[int]]:
        """Calculate RGB histograms"""
        r_hist = img.split()[0].histogram()
        g_hist = img.split()[1].histogram()
        b_hist = img.split()[2].histogram()

        return {"red": r_hist, "green": g_hist, "blue": b_hist}

    def _detect_quality_issues(
        self,
        brightness: float,
        contrast: float,
        saturation: float,
        sharpness: float,
        noise: float,
        histograms: Dict,
    ) -> List[QualityIssue]:
        """Detect common quality issues"""
        issues = []

        # Brightness issues
        if brightness < 85:
            issues.append(QualityIssue.DARK_IMAGE)
        elif brightness > 200:
            issues.append(QualityIssue.OVEREXPOSED)

        # Contrast issues
        if contrast < 30:
            issues.append(QualityIssue.LOW_CONTRAST)

        # Saturation issues
        if saturation < 50:
            issues.append(QualityIssue.UNDERSATURATED)
        elif saturation > 200:
            issues.append(QualityIssue.OVERSATURATED)

        # Sharpness issues
        if sharpness < 50:  # Adjust threshold based on method used
            issues.append(QualityIssue.BLURRY)

        # Noise issues
        if noise > 15:
            issues.append(QualityIssue.NOISY)

        # Color cast detection (simplified)
        r_hist, g_hist, b_hist = (
            histograms["red"],
            histograms["green"],
            histograms["blue"],
        )
        r_mean = sum(i * r_hist[i] for i in range(256)) / sum(r_hist)
        g_mean = sum(i * g_hist[i] for i in range(256)) / sum(g_hist)
        b_mean = sum(i * b_hist[i] for i in range(256)) / sum(b_hist)

        color_diff_threshold = 20
        if (
            abs(r_mean - g_mean) > color_diff_threshold
            or abs(g_mean - b_mean) > color_diff_threshold
            or abs(b_mean - r_mean) > color_diff_threshold
        ):
            issues.append(QualityIssue.COLOR_CAST)

        return issues

    def _recommend_enhancements(
        self,
        issues: List[QualityIssue],
        brightness: float,
        contrast: float,
        saturation: float,
    ) -> List[EnhancementType]:
        """Recommend specific enhancements based on detected issues"""
        recommendations = []

        # Always consider auto levels for overall improvement
        recommendations.append(EnhancementType.AUTO_LEVELS)

        for issue in issues:
            if issue == QualityIssue.DARK_IMAGE:
                recommendations.append(EnhancementType.BRIGHTNESS)
                recommendations.append(EnhancementType.GAMMA_CORRECTION)
            elif issue == QualityIssue.OVEREXPOSED:
                recommendations.append(EnhancementType.BRIGHTNESS)
            elif issue == QualityIssue.LOW_CONTRAST:
                recommendations.append(EnhancementType.CONTRAST)
                recommendations.append(EnhancementType.HISTOGRAM_EQUALIZATION)
            elif issue == QualityIssue.BLURRY:
                recommendations.append(EnhancementType.SHARPNESS)
            elif issue == QualityIssue.UNDERSATURATED:
                recommendations.append(EnhancementType.SATURATION)
            elif issue == QualityIssue.OVERSATURATED:
                recommendations.append(EnhancementType.SATURATION)
            elif issue == QualityIssue.COLOR_CAST:
                recommendations.append(EnhancementType.WHITE_BALANCE)
                recommendations.append(EnhancementType.COLOR_BALANCE)
            elif issue == QualityIssue.NOISY:
                recommendations.append(EnhancementType.NOISE_REDUCTION)

        # Remove duplicates while preserving order
        unique_recommendations = []
        for rec in recommendations:
            if rec not in unique_recommendations:
                unique_recommendations.append(rec)

        return unique_recommendations

    def _calculate_confidence_score(
        self, image_size: Tuple[int, int], sharpness: float, contrast: float
    ) -> float:
        """Calculate confidence score for the analysis (0-1)"""
        width, height = image_size
        pixels = width * height

        # Base confidence on image size (larger images = more reliable analysis)
        size_factor = min(1.0, pixels / (1920 * 1080))  # Normalized to Full HD

        # Factor in sharpness and contrast for reliability
        sharpness_factor = min(1.0, sharpness / 100)
        contrast_factor = min(1.0, contrast / 100)

        # Weighted average
        confidence = size_factor * 0.4 + sharpness_factor * 0.3 + contrast_factor * 0.3
        return max(0.0, min(1.0, confidence))


class ImageQualityEnhancer:
    """Automated image quality enhancement with concurrent processing"""

    def __init__(self, max_workers: Optional[int] = None):
        """Initialize quality enhancer"""
        if not PIL_AVAILABLE:
            raise RuntimeError(
                "PIL/Pillow not available - required for image enhancement"
            )

        self.max_workers = max_workers or min(os.cpu_count() * 2, 8)
        self.analyzer = ImageQualityAnalyzer()
        logger.info(
            f"✨ Image quality enhancer initialized with {self.max_workers} workers"
        )

    def _apply_auto_levels(self, img: Image.Image) -> Image.Image:
        """Apply automatic level adjustment"""
        return ImageOps.autocontrast(img, cutoff=2)

    def _apply_histogram_equalization(self, img: Image.Image) -> Image.Image:
        """Apply histogram equalization"""
        return ImageOps.equalize(img)

    def _apply_gamma_correction(
        self, img: Image.Image, gamma: float = 1.2
    ) -> Image.Image:
        """Apply gamma correction"""
        # Create gamma correction lookup table
        gamma_table = [pow(i / 255.0, 1.0 / gamma) * 255 for i in range(256)]
        gamma_table = [int(x) for x in gamma_table]

        # Apply gamma correction to each channel
        if img.mode == "RGB":
            r, g, b = img.split()
            r = r.point(gamma_table)
            g = g.point(gamma_table)
            b = b.point(gamma_table)
            return Image.merge("RGB", (r, g, b))
        else:
            return img.point(gamma_table)

    def _apply_noise_reduction(self, img: Image.Image) -> Image.Image:
        """Apply noise reduction using blur and edge preservation"""
        # Light Gaussian blur to reduce noise
        blurred = img.filter(GaussianBlur(radius=0.8))

        # Preserve edges by blending with original
        alpha = 0.7  # Blend factor
        return Image.blend(img, blurred, alpha)

    def _apply_white_balance(self, img: Image.Image) -> Image.Image:
        """Simple white balance correction"""
        # Convert to LAB color space equivalent using RGB adjustments
        r, g, b = img.split()

        # Calculate channel averages
        r_avg = sum(r.histogram()[i] * i for i in range(256)) / sum(r.histogram())
        g_avg = sum(g.histogram()[i] * i for i in range(256)) / sum(g.histogram())
        b_avg = sum(b.histogram()[i] * i for i in range(256)) / sum(b.histogram())

        # Calculate correction factors
        gray_target = (r_avg + g_avg + b_avg) / 3
        r_factor = gray_target / r_avg if r_avg > 0 else 1.0
        g_factor = gray_target / g_avg if g_avg > 0 else 1.0
        b_factor = gray_target / b_avg if b_avg > 0 else 1.0

        # Apply corrections (with limits to prevent overcompensation)
        r_factor = max(0.5, min(2.0, r_factor))
        g_factor = max(0.5, min(2.0, g_factor))
        b_factor = max(0.5, min(2.0, b_factor))

        # Apply factor-based enhancement
        if r_factor != 1.0:
            r = ImageEnhance.Brightness(r).enhance(r_factor)
        if g_factor != 1.0:
            g = ImageEnhance.Brightness(g).enhance(g_factor)
        if b_factor != 1.0:
            b = ImageEnhance.Brightness(b).enhance(b_factor)

        return Image.merge("RGB", (r, g, b))

    def _enhance_single_image(
        self, source_path: Path, output_path: Path, settings: EnhancementSettings
    ) -> EnhancementResult:
        """Enhance a single image with quality improvements"""
        start_time = time.time()

        try:
            original_size = source_path.stat().st_size

            with Image.open(source_path) as img:
                # Convert to RGB for consistent processing
                if img.mode != "RGB":
                    enhanced_img = img.convert("RGB")
                else:
                    enhanced_img = img.copy()

                # Analyze quality if auto-enhance is enabled
                quality_analysis = None
                enhancements_applied = []

                if settings.auto_enhance:
                    # Convert to OpenCV format if available
                    cv_img = None
                    if OPENCV_AVAILABLE:
                        try:
                            img_array = np.array(enhanced_img)
                            cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                        except:
                            pass

                    # Analyze quality
                    quality_analysis = self.analyzer.analyze_image_quality(
                        enhanced_img, cv_img
                    )

                    # Apply recommended enhancements
                    for enhancement in quality_analysis.recommended_enhancements:
                        if enhancement == EnhancementType.AUTO_LEVELS:
                            enhanced_img = self._apply_auto_levels(enhanced_img)
                            enhancements_applied.append(EnhancementType.AUTO_LEVELS)

                        elif enhancement == EnhancementType.HISTOGRAM_EQUALIZATION:
                            enhanced_img = self._apply_histogram_equalization(
                                enhanced_img
                            )
                            enhancements_applied.append(
                                EnhancementType.HISTOGRAM_EQUALIZATION
                            )

                        elif enhancement == EnhancementType.GAMMA_CORRECTION:
                            gamma_value = (
                                1.2 if quality_analysis.brightness_level < 100 else 0.9
                            )
                            enhanced_img = self._apply_gamma_correction(
                                enhanced_img, gamma_value
                            )
                            enhancements_applied.append(
                                EnhancementType.GAMMA_CORRECTION
                            )

                        elif enhancement == EnhancementType.NOISE_REDUCTION:
                            enhanced_img = self._apply_noise_reduction(enhanced_img)
                            enhancements_applied.append(EnhancementType.NOISE_REDUCTION)

                        elif enhancement == EnhancementType.WHITE_BALANCE:
                            enhanced_img = self._apply_white_balance(enhanced_img)
                            enhancements_applied.append(EnhancementType.WHITE_BALANCE)

                # Apply manual settings
                if settings.brightness_factor != 1.0:
                    enhancer = ImageEnhance.Brightness(enhanced_img)
                    enhanced_img = enhancer.enhance(settings.brightness_factor)
                    enhancements_applied.append(EnhancementType.BRIGHTNESS)

                if settings.contrast_factor != 1.0:
                    enhancer = ImageEnhance.Contrast(enhanced_img)
                    enhanced_img = enhancer.enhance(settings.contrast_factor)
                    enhancements_applied.append(EnhancementType.CONTRAST)

                if settings.saturation_factor != 1.0:
                    enhancer = ImageEnhance.Color(enhanced_img)
                    enhanced_img = enhancer.enhance(settings.saturation_factor)
                    enhancements_applied.append(EnhancementType.SATURATION)

                if settings.sharpness_factor != 1.0:
                    enhancer = ImageEnhance.Sharpness(enhanced_img)
                    enhanced_img = enhancer.enhance(settings.sharpness_factor)
                    enhancements_applied.append(EnhancementType.SHARPNESS)

                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Save enhanced image
                save_kwargs = {"format": "JPEG", "quality": 90, "optimize": True}

                enhanced_img.save(output_path, **save_kwargs)

                enhanced_size = output_path.stat().st_size
                processing_time = time.time() - start_time

                return EnhancementResult(
                    success=True,
                    source_path=str(source_path),
                    enhanced_path=str(output_path),
                    enhancements_applied=enhancements_applied,
                    quality_analysis=quality_analysis,
                    processing_time=processing_time,
                    file_size_change=enhanced_size - original_size,
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Image enhancement failed for {source_path}: {e}")

            return EnhancementResult(
                success=False,
                source_path=str(source_path),
                processing_time=processing_time,
                error=str(e),
            )

    async def enhance_image_collection(
        self,
        source_paths: List[Path],
        output_dir: Path,
        settings: EnhancementSettings,
        progress_callback: Optional[Callable] = None,
    ) -> List[EnhancementResult]:
        """Enhance a collection of images concurrently"""
        pool = get_image_processing_pool()

        if not pool.pool.is_running():
            await pool.start()

        # Prepare jobs
        jobs = []
        for source_path in source_paths:
            if not source_path.exists():
                logger.warning(f"⚠️ Source image not found: {source_path}")
                continue

            # Generate output path
            output_name = f"{source_path.stem}{settings.suffix}.jpg"
            output_path = output_dir / output_name

            jobs.append(
                (self._enhance_single_image, (source_path, output_path, settings), {})
            )

        logger.info(
            f"✨ Enhancing {len(jobs)} images using {pool.pool.config.max_workers} workers"
        )

        results = []
        completed = 0

        with pool.pool.batch_execution(jobs) as batch_futures:
            for future in batch_futures:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"❌ Enhancement job failed: {e}")
                    results.append(
                        EnhancementResult(
                            success=False, source_path="unknown", error=str(e)
                        )
                    )

                completed += 1
                if progress_callback:
                    progress_callback(completed, len(jobs))

        successful = sum(1 for r in results if r.success)
        logger.info(
            f"✅ Image enhancement completed: {successful}/{len(jobs)} successful"
        )

        return results


# Convenience functions
async def analyze_and_enhance_images(
    image_paths: List[str],
    output_dir: str,
    auto_enhance: bool = True,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 1.0,
    progress_callback: Optional[Callable] = None,
) -> List[EnhancementResult]:
    """Analyze and enhance images with quality improvements"""
    enhancer = ImageQualityEnhancer()
    paths = [Path(p) for p in image_paths]
    output_path = Path(output_dir)

    settings = EnhancementSettings(
        brightness_factor=brightness,
        contrast_factor=contrast,
        saturation_factor=saturation,
        sharpness_factor=sharpness,
        auto_enhance=auto_enhance,
    )

    return await enhancer.enhance_image_collection(
        paths, output_path, settings, progress_callback
    )
