"""
Video Indexing page route for MVidarr.

Provides the video indexing management interface.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from src.api.fastapi.template_system import template_system

logger = logging.getLogger(__name__)

page_router = APIRouter(tags=["Video Indexing Pages"])


@page_router.get("/video-indexing", response_class=HTMLResponse)
async def video_indexing_page(request: Request):
    """Render the video indexing management page."""
    context = {"page_title": "Video Indexing"}
    return await template_system.render_response(
        "video_indexing.html", request, context
    )
