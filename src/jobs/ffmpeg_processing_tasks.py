"""
FFmpeg processing background tasks aggregator module

This module serves as a backward-compatible aggregator for all FFmpeg processing tasks.
All task classes and helper functions are imported from their specialized modules
and re-exported here to maintain existing import paths.

For new code, consider importing directly from the specialized modules:
- ffmpeg_metadata_tasks: Metadata extraction tasks
- ffmpeg_conversion_tasks: Video format conversion tasks
- ffmpeg_quality_tasks: Quality analysis and validation tasks
- ffmpeg_thumbnail_tasks: Thumbnail generation tasks
"""

# Import all task classes from specialized modules
from src.jobs.ffmpeg_conversion_tasks import (
    FFmpegAdvancedFormatConversionTask,
    FFmpegVideoConversionTask,
    submit_advanced_format_conversion_task,
    submit_video_conversion_task,
)
from src.jobs.ffmpeg_metadata_tasks import (
    FFmpegBulkMetadataTask,
    FFmpegMetadataExtractionTask,
    submit_bulk_metadata_task,
    submit_metadata_extraction_task,
)
from src.jobs.ffmpeg_quality_tasks import (
    FFmpegConcurrentQualityAnalysisTask,
    FFmpegVideoValidationTask,
    submit_concurrent_quality_analysis_task,
    submit_video_validation_task,
)
from src.jobs.ffmpeg_thumbnail_tasks import (
    FFmpegBulkThumbnailCreationTask,
    bulk_thumbnail_creation,
    submit_bulk_thumbnail_creation_task,
)

# Task registration for backward compatibility
FFMPEG_TASKS = [
    FFmpegMetadataExtractionTask,
    FFmpegVideoConversionTask,
    FFmpegBulkMetadataTask,
    FFmpegAdvancedFormatConversionTask,
    FFmpegConcurrentQualityAnalysisTask,
    FFmpegBulkThumbnailCreationTask,
    FFmpegVideoValidationTask,
]

# Export all public symbols for backward compatibility
__all__ = [
    # Task classes
    "FFmpegMetadataExtractionTask",
    "FFmpegVideoConversionTask",
    "FFmpegBulkMetadataTask",
    "FFmpegAdvancedFormatConversionTask",
    "FFmpegConcurrentQualityAnalysisTask",
    "FFmpegBulkThumbnailCreationTask",
    "FFmpegVideoValidationTask",
    # Helper functions
    "submit_metadata_extraction_task",
    "submit_video_conversion_task",
    "submit_bulk_metadata_task",
    "submit_video_validation_task",
    "submit_advanced_format_conversion_task",
    "submit_concurrent_quality_analysis_task",
    "submit_bulk_thumbnail_creation_task",
    "bulk_thumbnail_creation",
    # Task registry
    "FFMPEG_TASKS",
]
