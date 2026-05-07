"""
FastAPI Videos API - Router Aggregator
Refactored from monolithic 4,029-line file into modular architecture

This file serves as the main entry point that aggregates all video-related routers:
- videos_models: Pydantic schemas and models
- videos_crud: Core CRUD operations (list, get, update, delete, status)
- videos_search: Search operations (search, universal-search, lyrics)
- videos_thumbnails: Thumbnail management operations
- videos_streaming: Video streaming and subtitle operations
- videos_downloads: Download management operations
- videos_bulk: Bulk edit/delete/organize/status operations
- videos_metadata: Metadata refresh and enrichment operations
- videos_import: YouTube and IMVDb import operations
- videos_blacklist: Blacklist management operations

Original file: 4,029 lines with 36 endpoints
Refactored into: 10 specialized modules for better maintainability
"""

from fastapi import APIRouter

from src.api.fastapi.videos_blacklist import router as blacklist_router
from src.api.fastapi.videos_bulk import router as bulk_router
from src.api.fastapi.videos_crud import router as crud_router
from src.api.fastapi.videos_downloads import router as downloads_router
from src.api.fastapi.videos_import import router as import_router
from src.api.fastapi.videos_metadata import router as metadata_router
from src.api.fastapi.videos_search import router as search_router
from src.api.fastapi.videos_streaming import router as streaming_router
from src.api.fastapi.videos_thumbnails import router as thumbnails_router
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.videos")

# ========================================================================================
# MAIN ROUTER AGGREGATOR
# ========================================================================================

router = APIRouter(
    prefix="/api/videos",
    tags=["videos"],
    responses={
        404: {"description": "Video not found"},
        422: {"description": "Validation error"},
    },
)

# Include all sub-routers
# IMPORTANT: Order matters! More specific routes must come before generic routes
# (e.g., /search must come before /{video_id}, /bulk/* before /{video_id})

# 1. Blacklist operations (has /blacklist/*, very specific)
router.include_router(blacklist_router, prefix="", tags=["videos-blacklist"])

# 2. Import operations (has /import-from-*, specific)
router.include_router(import_router, prefix="", tags=["videos-import"])

# 3. Search operations (has /search*, /universal-search, specific)
router.include_router(search_router, prefix="", tags=["videos-search"])

# 4. Bulk operations (has /bulk/*, specific)
router.include_router(bulk_router, prefix="", tags=["videos-bulk"])

# 5. Metadata operations (has /bulk/refresh-metadata, /enhanced-refresh-all-metadata)
router.include_router(metadata_router, prefix="", tags=["videos-metadata"])

# 6. Download operations (has /bulk/download, /bulk/download-wanted)
router.include_router(downloads_router, prefix="", tags=["videos-downloads"])

# 7. Thumbnail operations (has /{video_id}/thumbnail/*, specific)
router.include_router(thumbnails_router, prefix="", tags=["videos-thumbnails"])

# 8. Streaming operations (has /{video_id}/stream, /{video_id}/subtitles/*)
router.include_router(streaming_router, prefix="", tags=["videos-streaming"])

# 9. CRUD operations (list, get, update, delete, status) - has generic /{video_id}
# MUST COME LAST because /{video_id} will match any path
router.include_router(crud_router, prefix="", tags=["videos-crud"])

logger.info(
    "Videos API router initialized with modular architecture "
    "(CRUD, Search, Thumbnails, Streaming, Downloads, Bulk, Metadata, Import, Blacklist)"
)

# ========================================================================================
# REFACTORING NOTES
# ========================================================================================
#
# Original Structure: Single 4,029-line file with 36 endpoints
#
# New Modular Structure:
# - videos_models.py (~200 lines) - Pydantic schemas
# - videos_crud.py (~450 lines) - Core CRUD operations (5 endpoints)
# - videos_search.py (~520 lines) - Search functionality (4 endpoints)
# - videos_thumbnails.py (~650 lines) - Thumbnail management (5 endpoints)
# - videos_streaming.py (~380 lines) - Video streaming & subtitles (4 endpoints)
# - videos_downloads.py (~680 lines) - Download operations (5 endpoints)
# - videos_bulk.py (~560 lines) - Bulk management (5 endpoints)
# - videos_metadata.py (~490 lines) - Metadata refresh (4 endpoints)
# - videos_import.py (~220 lines) - YouTube/IMVDb import (2 endpoints)
# - videos_blacklist.py (~280 lines) - Blacklist management (4 endpoints)
# - videos.py (~120 lines) - Main router aggregator
#
# Total: ~4,550 lines across 11 files (includes documentation)
#
# Benefits:
# - Easier to navigate and maintain
# - Clear separation of concerns by functionality
# - Better testability and modularity
# - Reduced cognitive load per file
# - Faster file loading in editors
# - Logical grouping of related operations
#
# Migration completed: 2025-10-13
# For 0.9.9 Code Cleanup & Optimization milestone
# Following the pattern established by artists.py refactoring
# ========================================================================================
