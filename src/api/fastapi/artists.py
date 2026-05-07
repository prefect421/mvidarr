"""
FastAPI Artists API - Router Aggregator
Refactored from monolithic 2,874-line file into modular architecture

This file serves as the main entry point that aggregates all artist-related routers:
- artists_models: Pydantic schemas and models
- artists_crud: Core CRUD operations (list, get, create, update, delete, search)
- artists_thumbnails: Thumbnail management operations
- artists_discovery: Artist discovery and IMVDb import operations
- artists_bulk: Bulk operations and navigation

Original file: 2,874 lines with 26 endpoints
Refactored into: 5 specialized modules for better maintainability
"""

from fastapi import APIRouter
from src.api.fastapi.artists_bulk import router as bulk_router
from src.api.fastapi.artists_crud import router as crud_router
from src.api.fastapi.artists_discovery import router as discovery_router
from src.api.fastapi.artists_scheduling import router as scheduling_router
from src.api.fastapi.artists_thumbnails import router as thumbnails_router
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.artists")

# ========================================================================================
# MAIN ROUTER AGGREGATOR
# ========================================================================================

router = APIRouter(
    prefix="/api/artists",
    tags=["artists"],
    responses={
        404: {"description": "Artist not found"},
        422: {"description": "Validation error"},
    },
)

# Include all sub-routers
# IMPORTANT: Order matters! More specific routes must come before generic routes
# (e.g., /discover must come before /{artist_id})

# Discovery and import operations (has /discover, must come before /{artist_id})
router.include_router(discovery_router, prefix="", tags=["artists-discovery"])

# Bulk operations and navigation (has /cleanup-zero-videos, must come before /{artist_id})
router.include_router(bulk_router, prefix="", tags=["artists-bulk"])

# Thumbnail management operations (has /{artist_id}/thumbnail/*, specific)
router.include_router(thumbnails_router, prefix="", tags=["artists-thumbnails"])

# Scheduling operations (has /{artist_id}/scheduling/*, specific) - Scheduler V2 (v0.10.1)
router.include_router(scheduling_router, prefix="", tags=["artists-scheduling"])

# CRUD operations (list, get, create, update, delete, search) - has generic /{artist_id}
# MUST COME LAST because /{artist_id} will match any path
router.include_router(crud_router, prefix="", tags=["artists-crud"])

logger.info(
    "Artists API router initialized with modular architecture (CRUD, Thumbnails, Discovery, Bulk, Scheduling)"
)

# ========================================================================================
# REFACTORING NOTES
# ========================================================================================
#
# Original Structure: Single 2,874-line file with 26 endpoints
#
# New Modular Structure:
# - artists_models.py (~150 lines) - Pydantic schemas
# - artists_crud.py (~700 lines) - Core CRUD + search operations (7 endpoints)
# - artists_thumbnails.py (~750 lines) - Thumbnail management (7 endpoints)
# - artists_discovery.py (~800 lines) - Discovery and import (6 endpoints)
# - artists_bulk.py (~500 lines) - Bulk operations (5 endpoints)
# - artists.py (~100 lines) - Main router aggregator
#
# Benefits:
# - Easier to navigate and maintain
# - Clear separation of concerns
# - Better testability
# - Reduced cognitive load
# - Faster file loading in editors
#
# Fixed Issues:
# - Removed duplicate endpoint: PUT /{artist_id}/thumbnail (line 1616)
#   Kept the version at line 1221 which uses ThumbnailService properly
#
# Migration completed: 2025-10-13
# For 0.9.9 Code Cleanup & Optimization milestone
# ========================================================================================
