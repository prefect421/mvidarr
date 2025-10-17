"""
MVidarr AI-Powered Thumbnail Generator - Main Module
High-performance thumbnail generation with AI-powered smart selection and optimization
Enhanced with intelligent thumbnail selection using computer vision and quality assessment

This module serves as the main aggregator, importing and exposing all thumbnail
generation components from their modular files.
"""

# Import availability flags
try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    np = None

try:
    import cv2

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None

# Import AI selector
from src.services.thumbnail_ai_selector import AIThumbnailSelector

# Import cache system
from src.services.thumbnail_cache import ThumbnailCache

# Import base generator and convenience functions
from src.services.thumbnail_generator_base import (
    ConcurrentThumbnailGenerator,
    generate_bulk_thumbnails,
    generate_video_thumbnails,
)

# Import smart generator and convenience functions
from src.services.thumbnail_generator_smart import (
    SmartThumbnailGenerator,
    compare_ai_vs_standard_thumbnails,
    generate_smart_thumbnails,
)

# Import models
from src.services.thumbnail_models import (
    SmartThumbnailConfig,
    ThumbnailCandidate,
    ThumbnailConfig,
    ThumbnailResult,
)

# Define public API
__all__ = [
    # Availability flags
    "PIL_AVAILABLE",
    "OPENCV_AVAILABLE",
    # Models
    "ThumbnailConfig",
    "ThumbnailResult",
    "SmartThumbnailConfig",
    "ThumbnailCandidate",
    # Cache
    "ThumbnailCache",
    # Base generator
    "ConcurrentThumbnailGenerator",
    "generate_video_thumbnails",
    "generate_bulk_thumbnails",
    # AI components
    "AIThumbnailSelector",
    "SmartThumbnailGenerator",
    "generate_smart_thumbnails",
    "compare_ai_vs_standard_thumbnails",
]
