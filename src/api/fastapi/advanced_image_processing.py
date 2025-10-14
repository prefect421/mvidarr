"""
MVidarr Advanced Image Processing FastAPI Endpoints - Phase 2 Week 21
REST API endpoints for advanced image operations and quality enhancement
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException
from pydantic import BaseModel, Field

from src.jobs.advanced_image_tasks import (
    ImageFormat,
    analyze_large_image_collection,
    bulk_convert_image_formats,
)
from src.services.image_quality_enhancer import analyze_and_enhance_images
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.advanced_image")

router = APIRouter(
    prefix="/api/advanced-image-processing",
    tags=["advanced-image-processing"],
    responses={404: {"description": "Not found"}},
)


# Request/Response Models
class BulkAnalysisRequest(BaseModel):
    """Request model for bulk image analysis"""

    image_paths: List[str] = Field(
        ..., min_items=1, max_items=5000, description="List of image paths to analyze"
    )
    include_metadata: bool = Field(
        True, description="Include detailed metadata extraction"
    )
    include_quality_analysis: bool = Field(True, description="Include quality analysis")
    generate_summary: bool = Field(True, description="Generate collection summary")


class FormatConversionRequest(BaseModel):
    """Request model for format conversion"""

    source_paths: List[str] = Field(
        ..., min_items=1, max_items=1000, description="List of source image paths"
    )
    output_dir: str = Field(..., description="Output directory for converted images")
    target_formats: List[str] = Field(
        ..., min_items=1, description="Target formats (JPEG, PNG, WEBP, etc.)"
    )
    quality: int = Field(85, ge=1, le=100, description="Compression quality (1-100)")
    optimize: bool = Field(True, description="Apply format-specific optimizations")


class QualityEnhancementRequest(BaseModel):
    """Request model for image quality enhancement"""

    source_paths: List[str] = Field(
        ..., min_items=1, max_items=1000, description="List of source image paths"
    )
    output_dir: str = Field(..., description="Output directory for enhanced images")
    auto_enhance: bool = Field(True, description="Apply automatic quality enhancements")
    brightness_factor: float = Field(
        1.0, ge=0.1, le=3.0, description="Brightness adjustment (1.0 = no change)"
    )
    contrast_factor: float = Field(
        1.0, ge=0.1, le=3.0, description="Contrast adjustment (1.0 = no change)"
    )
    saturation_factor: float = Field(
        1.0, ge=0.1, le=3.0, description="Saturation adjustment (1.0 = no change)"
    )
    sharpness_factor: float = Field(
        1.0, ge=0.1, le=3.0, description="Sharpness adjustment (1.0 = no change)"
    )
    preserve_original: bool = Field(True, description="Keep original files")


class AdvancedAnalysisResponse(BaseModel):
    """Response model for advanced image analysis"""

    total_analyzed: int
    successful_analyses: int
    failed_analyses: int
    processing_time: float
    collection_summary: Optional[Dict[str, Any]] = None
    detailed_results: Optional[List[Dict[str, Any]]] = None


class FormatConversionResponse(BaseModel):
    """Response model for format conversion"""

    total_conversions: int
    successful_conversions: int
    failed_conversions: int
    processing_time: float
    total_size_change: int
    average_compression_ratio: float
    results: List[Dict[str, Any]]


class QualityEnhancementResponse(BaseModel):
    """Response model for quality enhancement"""

    total_enhanced: int
    successful_enhancements: int
    failed_enhancements: int
    processing_time: float
    enhancements_applied: Dict[str, int]  # Count of each enhancement type
    results: List[Dict[str, Any]]


# Endpoints
@router.post("/analyze/bulk", response_model=AdvancedAnalysisResponse)
async def bulk_image_analysis(
    request: BulkAnalysisRequest, background_tasks: BackgroundTasks
):
    """
    Perform bulk analysis of large image collections

    This endpoint analyzes thousands of images concurrently, extracting comprehensive
    metadata, quality metrics, and generating collection summaries.
    """
    try:
        # Validate paths exist
        source_paths = [Path(p) for p in request.image_paths]
        missing_paths = [p for p in source_paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Image paths not found: {[str(p) for p in missing_paths[:10]]}",  # Limit error output
            )

        logger.info(f"🔍 Starting bulk analysis of {len(source_paths)} images")

        # Perform analysis
        metadata_list, summary = await analyze_large_image_collection(
            [str(p) for p in source_paths]
        )

        # Calculate metrics
        successful = sum(1 for m in metadata_list if m.width > 0 and m.height > 0)
        failed = len(metadata_list) - successful
        total_processing_time = sum(m.processing_time for m in metadata_list)

        # Prepare response
        response = AdvancedAnalysisResponse(
            total_analyzed=len(metadata_list),
            successful_analyses=successful,
            failed_analyses=failed,
            processing_time=total_processing_time,
        )

        if request.generate_summary:
            response.collection_summary = summary

        if request.include_metadata:
            response.detailed_results = [m.to_dict() for m in metadata_list]

        logger.info(
            f"✅ Bulk analysis completed: {successful}/{len(metadata_list)} successful"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Bulk analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/convert/formats", response_model=FormatConversionResponse)
async def convert_image_formats(
    request: FormatConversionRequest, background_tasks: BackgroundTasks
):
    """
    Convert images to different formats concurrently

    This endpoint converts multiple images to various formats (JPEG, PNG, WEBP, etc.)
    with optimized quality settings and concurrent processing.
    """
    try:
        # Validate paths exist
        source_paths = [Path(p) for p in request.source_paths]
        missing_paths = [p for p in source_paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Source paths not found: {[str(p) for p in missing_paths]}",
            )

        # Validate formats
        valid_formats = [fmt.value for fmt in ImageFormat]
        invalid_formats = [
            fmt for fmt in request.target_formats if fmt.upper() not in valid_formats
        ]
        if invalid_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid formats: {invalid_formats}. Supported: {valid_formats}",
            )

        logger.info(
            f"🔄 Converting {len(source_paths)} images to {len(request.target_formats)} formats"
        )

        # Perform conversions
        results = await bulk_convert_image_formats(
            source_paths=[str(p) for p in source_paths],
            output_dir=request.output_dir,
            target_formats=request.target_formats,
            quality=request.quality,
        )

        # Calculate metrics
        successful = sum(1 for r in results if r.get("success", False))
        failed = len(results) - successful
        total_processing_time = sum(r.get("processing_time", 0) for r in results)

        # Size change metrics
        total_size_change = sum(
            r.get("size_change", 0) for r in results if r.get("success", False)
        )
        compression_ratios = [
            r.get("compression_ratio", 0)
            for r in results
            if r.get("success", False) and r.get("compression_ratio")
        ]
        avg_compression_ratio = (
            sum(compression_ratios) / len(compression_ratios)
            if compression_ratios
            else 0
        )

        response = FormatConversionResponse(
            total_conversions=len(results),
            successful_conversions=successful,
            failed_conversions=failed,
            processing_time=total_processing_time,
            total_size_change=total_size_change,
            average_compression_ratio=avg_compression_ratio,
            results=results,
        )

        logger.info(
            f"✅ Format conversion completed: {successful}/{len(results)} successful"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Format conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enhance/quality", response_model=QualityEnhancementResponse)
async def enhance_image_quality(
    request: QualityEnhancementRequest, background_tasks: BackgroundTasks
):
    """
    Enhance image quality with automated improvements

    This endpoint analyzes image quality issues and applies appropriate enhancements
    such as brightness/contrast adjustment, sharpening, noise reduction, etc.
    """
    try:
        # Validate paths exist
        source_paths = [Path(p) for p in request.source_paths]
        missing_paths = [p for p in source_paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Source paths not found: {[str(p) for p in missing_paths]}",
            )

        logger.info(f"✨ Enhancing quality of {len(source_paths)} images")

        # Perform enhancements
        results = await analyze_and_enhance_images(
            image_paths=[str(p) for p in source_paths],
            output_dir=request.output_dir,
            auto_enhance=request.auto_enhance,
            brightness=request.brightness_factor,
            contrast=request.contrast_factor,
            saturation=request.saturation_factor,
            sharpness=request.sharpness_factor,
        )

        # Calculate metrics
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_processing_time = sum(r.processing_time for r in results)

        # Count enhancement types applied
        enhancement_counts = {}
        for result in results:
            if result.success and result.enhancements_applied:
                for enhancement in result.enhancements_applied:
                    enh_name = (
                        enhancement.value
                        if hasattr(enhancement, "value")
                        else str(enhancement)
                    )
                    enhancement_counts[enh_name] = (
                        enhancement_counts.get(enh_name, 0) + 1
                    )

        response = QualityEnhancementResponse(
            total_enhanced=len(results),
            successful_enhancements=successful,
            failed_enhancements=failed,
            processing_time=total_processing_time,
            enhancements_applied=enhancement_counts,
            results=[
                {
                    "source_path": r.source_path,
                    "enhanced_path": r.enhanced_path,
                    "success": r.success,
                    "enhancements_applied": [
                        e.value if hasattr(e, "value") else str(e)
                        for e in (r.enhancements_applied or [])
                    ],
                    "processing_time": r.processing_time,
                    "file_size_change": r.file_size_change,
                    "quality_analysis": (
                        r.quality_analysis.to_dict() if r.quality_analysis else None
                    ),
                    "error": r.error,
                }
                for r in results
            ],
        )

        logger.info(
            f"✅ Quality enhancement completed: {successful}/{len(results)} successful"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Quality enhancement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/formats/supported")
async def get_supported_formats():
    """
    Get list of supported image formats for conversion

    Returns information about supported input and output formats with their capabilities.
    """
    try:
        formats_info = {}

        for fmt in ImageFormat:
            formats_info[fmt.value] = {
                "name": fmt.value,
                "extension": f".{fmt.value.lower()}",
                "supports_quality": fmt in [ImageFormat.JPEG, ImageFormat.WEBP],
                "supports_transparency": fmt in [ImageFormat.PNG, ImageFormat.WEBP],
                "supports_animation": fmt == ImageFormat.GIF,
                "recommended_use": {
                    ImageFormat.JPEG: "Photos and complex images with many colors",
                    ImageFormat.PNG: "Images with transparency or text/graphics",
                    ImageFormat.WEBP: "Modern web images with excellent compression",
                    ImageFormat.TIFF: "High-quality archival and professional use",
                    ImageFormat.BMP: "Uncompressed images for editing",
                    ImageFormat.GIF: "Simple animations and images with few colors",
                }.get(fmt, "General purpose"),
            }

        return {
            "supported_formats": formats_info,
            "total_formats": len(formats_info),
            "conversion_capabilities": {
                "max_concurrent_conversions": 50,
                "quality_range": "1-100 (for JPEG/WEBP)",
                "optimization_available": True,
                "batch_processing": True,
            },
        }

    except Exception as e:
        logger.error(f"❌ Failed to get supported formats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhancement/options")
async def get_enhancement_options():
    """
    Get available image enhancement options and their descriptions

    Returns information about automatic and manual enhancement capabilities.
    """
    try:
        enhancement_info = {
            "automatic_enhancements": {
                "auto_levels": "Automatic contrast and brightness adjustment",
                "histogram_equalization": "Improve contrast by redistributing pixel intensities",
                "gamma_correction": "Correct image brightness using gamma curves",
                "noise_reduction": "Reduce image noise while preserving details",
                "white_balance": "Correct color temperature and color casts",
                "sharpness": "Enhance image sharpness and edge definition",
            },
            "manual_adjustments": {
                "brightness": "Adjust overall image brightness (0.1-3.0)",
                "contrast": "Adjust image contrast (0.1-3.0)",
                "saturation": "Adjust color saturation (0.1-3.0)",
                "sharpness": "Adjust image sharpness (0.1-3.0)",
            },
            "quality_detection": {
                "brightness_issues": "Detects dark, bright, or overexposed images",
                "contrast_issues": "Identifies low contrast images",
                "sharpness_analysis": "Measures image blur and sharpness",
                "color_analysis": "Detects color casts and saturation issues",
                "noise_detection": "Estimates image noise levels",
            },
            "processing_capabilities": {
                "concurrent_processing": True,
                "batch_size": "Up to 1000 images",
                "quality_analysis": True,
                "before_after_metrics": True,
                "preserve_originals": True,
            },
        }

        return enhancement_info

    except Exception as e:
        logger.error(f"❌ Failed to get enhancement options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/quality-only")
async def analyze_image_quality_only(
    image_paths: List[str] = Body(..., description="List of image paths to analyze"),
    include_histograms: bool = Body(
        False, description="Include histogram data in response"
    ),
):
    """
    Analyze image quality without enhancement

    This endpoint performs quality analysis only, returning detailed metrics
    and recommendations without modifying the images.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        from src.services.image_quality_enhancer import ImageQualityAnalyzer

        # Validate paths
        source_paths = [Path(p) for p in image_paths]
        missing_paths = [p for p in source_paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Image paths not found: {[str(p) for p in missing_paths]}",
            )

        analyzer = ImageQualityAnalyzer()
        results = []

        logger.info(f"🔍 Analyzing quality of {len(source_paths)} images")

        for path in source_paths:
            try:
                with Image.open(path) as img:
                    # Convert to RGB if necessary
                    if img.mode != "RGB":
                        rgb_img = img.convert("RGB")
                    else:
                        rgb_img = img

                    # Convert to OpenCV format if available
                    cv_img = None
                    try:
                        img_array = np.array(rgb_img)
                        cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    except:
                        pass

                    # Analyze quality
                    analysis = analyzer.analyze_image_quality(rgb_img, cv_img)

                    result = {"image_path": str(path), "analysis": analysis.to_dict()}

                    # Optionally exclude histogram data to reduce response size
                    if not include_histograms:
                        result["analysis"].pop("histogram_data", None)

                    results.append(result)

            except Exception as e:
                logger.error(f"❌ Quality analysis failed for {path}: {e}")
                results.append({"image_path": str(path), "error": str(e)})

        successful = sum(1 for r in results if "error" not in r)

        return {
            "total_analyzed": len(results),
            "successful_analyses": successful,
            "failed_analyses": len(results) - successful,
            "results": results,
        }

    except Exception as e:
        logger.error(f"❌ Quality analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
