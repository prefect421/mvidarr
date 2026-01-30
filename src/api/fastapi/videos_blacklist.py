"""
FastAPI Videos Blacklist API Module

This module contains blacklist management operations for videos.
These endpoints handle managing the video blacklist:
- GET /blacklist - List blacklisted videos with pagination and search
- POST /blacklist - Add a video to blacklist
- DELETE /blacklist/{id} - Remove a video from blacklist
- POST /blacklist/check - Check if a URL is blacklisted

Extracted from videos.py as part of the API modularization effort.

Authentication: All endpoints require session-based authentication via require_authentication dependency.
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import (
    get_current_user_legacy,
    require_authentication_legacy,
)
from src.database.connection import get_db_session
from src.database.models import VideoBlacklist
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_blacklist")


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


async def require_authentication(current_user: dict = Depends(get_current_user)):
    """Dependency to require authentication for protected endpoints"""
    return await require_authentication_legacy(current_user)


# ========================================================================================
# BLACKLIST OPERATIONS
# ========================================================================================


@router.get("/blacklist")
async def get_blacklist(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: str = Query("", description="Search blacklisted videos"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get all blacklisted YouTube URLs"""
    try:
        # Build query
        query = session.query(VideoBlacklist)

        if search.strip():
            search_filter = f"%{search}%"
            query = query.filter(
                or_(
                    VideoBlacklist.title.ilike(search_filter),
                    VideoBlacklist.artist_name.ilike(search_filter),
                    VideoBlacklist.youtube_url.ilike(search_filter),
                )
            )

        # Get total count for pagination
        total_count = query.count()

        # Apply pagination and ordering
        blacklist_entries = (
            query.order_by(VideoBlacklist.blacklisted_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        # Format response
        entries = []
        for entry in blacklist_entries:
            entries.append(
                {
                    "youtube_url": entry.youtube_url,
                    "title": entry.title,
                    "artist_name": entry.artist_name,
                    "blacklisted_at": (
                        entry.blacklisted_at.isoformat()
                        if entry.blacklisted_at
                        else None
                    ),
                    "blacklisted_by": entry.blacklisted_by,
                    "blacklisted_by_username": (
                        entry.user.username if entry.user else None
                    ),
                }
            )

        return {
            "blacklist_entries": entries,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_count,
                "total_pages": (total_count + per_page - 1) // per_page,
            },
        }

    except Exception as e:
        logger.error(f"Error getting blacklist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/blacklist")
async def add_to_blacklist(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Add a YouTube URL to blacklist"""
    try:
        youtube_url = request.get("youtube_url", "").strip()
        title = request.get("title", "").strip()
        artist_name = request.get("artist_name", "").strip()

        if not youtube_url:
            raise HTTPException(status_code=422, detail="YouTube URL is required")

        # Check if already blacklisted
        existing = (
            session.query(VideoBlacklist)
            .filter(VideoBlacklist.youtube_url == youtube_url)
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=409, detail=f"URL already blacklisted: {youtube_url}"
            )

        # Add to blacklist
        blacklist_entry = VideoBlacklist(
            youtube_url=youtube_url,
            title=title or None,
            artist_name=artist_name or None,
            blacklisted_by=current_user.get("id"),
        )

        session.add(blacklist_entry)
        session.commit()

        logger.info(
            f"Added {youtube_url} to blacklist by user {current_user.get('username')}"
        )

        return {
            "success": True,
            "message": f"Added to blacklist: {youtube_url}",
            "blacklist_entry": {
                "youtube_url": blacklist_entry.youtube_url,
                "title": blacklist_entry.title,
                "artist_name": blacklist_entry.artist_name,
                "blacklisted_at": (
                    blacklist_entry.blacklisted_at.isoformat()
                    if blacklist_entry.blacklisted_at
                    else None
                ),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding to blacklist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/blacklist")
async def remove_from_blacklist(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Remove a YouTube URL from blacklist"""
    try:
        youtube_url = request.get("youtube_url", "").strip()

        if not youtube_url:
            raise HTTPException(status_code=400, detail="youtube_url is required")

        blacklist_entry = (
            session.query(VideoBlacklist)
            .filter(VideoBlacklist.youtube_url == youtube_url)
            .first()
        )

        if not blacklist_entry:
            raise HTTPException(status_code=404, detail="Blacklist entry not found")

        session.delete(blacklist_entry)
        session.commit()

        logger.info(f"Removed {youtube_url} from blacklist")

        return {"success": True, "message": f"Removed from blacklist: {youtube_url}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from blacklist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/blacklist/check")
async def check_blacklist(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Check if a YouTube URL is blacklisted"""
    try:
        youtube_url = request.get("youtube_url", "").strip()

        if not youtube_url:
            raise HTTPException(status_code=422, detail="YouTube URL is required")

        blacklist_entry = (
            session.query(VideoBlacklist)
            .filter(VideoBlacklist.youtube_url == youtube_url)
            .first()
        )

        is_blacklisted = blacklist_entry is not None

        response = {
            "youtube_url": youtube_url,
            "is_blacklisted": is_blacklisted,
        }

        if is_blacklisted:
            response["blacklist_info"] = {
                "title": blacklist_entry.title,
                "artist_name": blacklist_entry.artist_name,
                "blacklisted_at": (
                    blacklist_entry.blacklisted_at.isoformat()
                    if blacklist_entry.blacklisted_at
                    else None
                ),
                "blacklisted_by": blacklist_entry.blacklisted_by,
            }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking blacklist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
