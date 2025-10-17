"""
Thumbnail Generator - Models Module
Data classes and configuration models for thumbnail generation
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


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

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "success": self.success,
            "source_path": self.source_path,
            "thumbnail_path": self.thumbnail_path,
            "config": f"{self.config}" if self.config else None,
            "file_size": self.file_size,
            "processing_time": self.processing_time,
            "error": self.error,
            "cached": self.cached,
        }


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
        return (
            (self.crop_box[0] + self.crop_box[2]) // 2,
            (self.crop_box[1] + self.crop_box[3]) // 2,
        )
