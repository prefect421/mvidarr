"""
Mobile-Optimized Access API - Phase 3 Week 29
Consumer-focused mobile endpoints for music video collections
"""

import asyncio
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)

from src.services.collection_organizer import get_collection_organizer
from src.services.local_network_share import get_local_network_share
from src.services.music_video_detector import get_music_video_detector
from src.services.performance_monitor import get_performance_monitor
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.mobile_access")

# Create router
mobile_router = APIRouter(prefix="/mobile", tags=["mobile", "streaming"])


class MobileDeviceDetector:
    """Simple mobile device detection"""

    @staticmethod
    def is_mobile_device(user_agent: str) -> bool:
        """Check if user agent indicates mobile device"""
        mobile_indicators = [
            "mobile",
            "android",
            "iphone",
            "ipad",
            "ipod",
            "blackberry",
            "windows phone",
            "opera mini",
        ]
        user_agent_lower = user_agent.lower()
        return any(indicator in user_agent_lower for indicator in mobile_indicators)

    @staticmethod
    def get_device_type(user_agent: str) -> str:
        """Get device type from user agent"""
        ua = user_agent.lower()
        if "ipad" in ua:
            return "tablet"
        elif "iphone" in ua or "ipod" in ua:
            return "mobile"
        elif "android" in ua:
            if "mobile" in ua:
                return "mobile"
            else:
                return "tablet"
        elif any(tv in ua for tv in ["smart-tv", "smarttv", "tv"]):
            return "tv"
        else:
            return "desktop"


async def get_mobile_optimized_config(request: Request) -> Dict[str, Any]:
    """Get mobile-optimized configuration based on device"""
    user_agent = request.headers.get("user-agent", "")
    device_type = MobileDeviceDetector.get_device_type(user_agent)
    is_mobile = MobileDeviceDetector.is_mobile_device(user_agent)

    # Mobile-optimized settings
    config = {
        "device_type": device_type,
        "is_mobile": is_mobile,
        "streaming_quality": "medium" if is_mobile else "high",
        "thumbnail_size": "small" if is_mobile else "medium",
        "page_size": 20 if is_mobile else 50,
        "enable_lazy_loading": True,
        "enable_offline_mode": is_mobile,
        "max_concurrent_streams": 2 if is_mobile else 4,
    }

    return config


# Mobile Discovery and Status


@mobile_router.get("/discover")
async def mobile_discover_server(request: Request):
    """Discover MVidarr server capabilities for mobile apps"""
    try:
        config = await get_mobile_optimized_config(request)
        network_share = await get_local_network_share()

        # Get server capabilities
        network_status = await network_share.get_network_status()

        discovery_info = {
            "server_name": network_status.get("service_name", "MVidarr Server"),
            "server_address": network_status.get("server_address", ""),
            "capabilities": {
                "streaming": True,
                "downloads": True,
                "playlists": True,
                "search": True,
                "collections": True,
            },
            "mobile_config": config,
            "api_endpoints": {
                "collections": "/mobile/collections",
                "search": "/mobile/search",
                "stream": "/mobile/stream",
                "download": "/mobile/download",
                "playlists": "/mobile/playlists",
            },
            "supported_formats": ["mp4", "webm", "m4v"],
            "quality_levels": ["low", "medium", "high"],
            "server_version": "0.9.8",
            "last_updated": datetime.now().isoformat(),
        }

        return JSONResponse(discovery_info)

    except Exception as e:
        logger.error(f"Failed to provide mobile discovery info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mobile_router.get("/status")
async def get_mobile_server_status(request: Request):
    """Get server status optimized for mobile display"""
    try:
        config = await get_mobile_optimized_config(request)
        network_share = await get_local_network_share()
        performance_monitor = await get_performance_monitor()

        # Get basic status information
        network_status = await network_share.get_network_status()
        system_health = await performance_monitor.get_system_health_summary()

        mobile_status = {
            "server_online": True,
            "health_score": system_health.get("overall_score", 100),
            "active_streams": network_status.get("active_streams", 0),
            "available_shares": network_status.get("active_shares", 0),
            "device_type": config["device_type"],
            "recommended_quality": config["streaming_quality"],
            "server_load": "low",  # Simplified for mobile
            "last_check": datetime.now().isoformat(),
        }

        return JSONResponse(mobile_status)

    except Exception as e:
        logger.error(f"Failed to get mobile server status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mobile Collection Browsing


@mobile_router.get("/collections")
async def get_mobile_collections(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("name", regex="^(name|date|size|type)$"),
):
    """Get music video collections optimized for mobile"""
    try:
        config = await get_mobile_optimized_config(request)

        # Adjust limit based on device
        if config["is_mobile"] and limit > 20:
            limit = 20

        # This would integrate with existing collection services
        # For now, return sample mobile-optimized data
        collections = []

        # Sample collections with mobile-optimized metadata
        sample_collections = [
            {
                "id": "collection_1",
                "name": "Recent Music Videos",
                "type": "recent",
                "video_count": 45,
                "total_size_mb": 1250,
                "thumbnail_url": "/mobile/thumbnail/collection_1",
                "last_updated": "2025-01-09T10:30:00Z",
                "description": "Recently added music videos",
            },
            {
                "id": "collection_2",
                "name": "Top Artists",
                "type": "artists",
                "video_count": 128,
                "total_size_mb": 3420,
                "thumbnail_url": "/mobile/thumbnail/collection_2",
                "last_updated": "2025-01-08T15:45:00Z",
                "description": "Most popular artists in collection",
            },
        ]

        # Paginate results
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_collections = sample_collections[start_idx:end_idx]

        response = {
            "collections": paginated_collections,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_pages": (len(sample_collections) + limit - 1) // limit,
                "total_items": len(sample_collections),
                "has_next": end_idx < len(sample_collections),
                "has_prev": page > 1,
            },
            "mobile_config": config,
            "last_updated": datetime.now().isoformat(),
        }

        return JSONResponse(response)

    except Exception as e:
        logger.error(f"Failed to get mobile collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mobile_router.get("/collections/{collection_id}")
async def get_mobile_collection_videos(
    collection_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    quality: str = Query("auto", regex="^(auto|low|medium|high)$"),
):
    """Get videos in collection optimized for mobile"""
    try:
        config = await get_mobile_optimized_config(request)

        # Auto-select quality based on device
        if quality == "auto":
            quality = config["streaming_quality"]

        # Sample videos with mobile-optimized metadata
        sample_videos = [
            {
                "id": "video_1",
                "title": "Artist Name - Song Title",
                "artist": "Artist Name",
                "duration": 245,
                "file_size_mb": 28.5,
                "quality": quality,
                "thumbnail_url": f"/mobile/thumbnail/video_1?quality={quality}",
                "stream_url": f"/mobile/stream/video_1?quality={quality}",
                "download_url": f"/mobile/download/video_1",
                "mobile_optimized": True,
                "upload_date": "2025-01-05T12:00:00Z",
            }
        ] * 25  # Sample data

        # Paginate results
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_videos = sample_videos[start_idx:end_idx]

        response = {
            "collection_id": collection_id,
            "videos": paginated_videos,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_pages": (len(sample_videos) + limit - 1) // limit,
                "total_items": len(sample_videos),
                "has_next": end_idx < len(sample_videos),
                "has_prev": page > 1,
            },
            "quality_settings": {
                "current": quality,
                "available": ["low", "medium", "high"],
                "recommended": config["streaming_quality"],
            },
            "mobile_config": config,
        }

        return JSONResponse(response)

    except Exception as e:
        logger.error(f"Failed to get collection videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mobile Search


@mobile_router.get("/search")
async def mobile_search_videos(
    request: Request,
    q: str = Query(..., min_length=1),
    type: str = Query("all", regex="^(all|videos|artists|albums)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
):
    """Search music videos optimized for mobile"""
    try:
        config = await get_mobile_optimized_config(request)

        # Mobile search is limited to smaller result sets
        if config["is_mobile"] and limit > 15:
            limit = 15

        # This would integrate with existing search functionality
        # For now, return sample search results
        search_results = []

        # Sample search results
        for i in range(min(limit, 25)):
            search_results.append(
                {
                    "id": f"result_{i}",
                    "type": "video",
                    "title": f"Search Result {i+1} - {q}",
                    "artist": f"Artist {i+1}",
                    "duration": 180 + i * 15,
                    "match_score": 0.9 - (i * 0.02),
                    "thumbnail_url": f"/mobile/thumbnail/result_{i}",
                    "stream_url": f"/mobile/stream/result_{i}",
                    "mobile_optimized": True,
                }
            )

        response = {
            "query": q,
            "search_type": type,
            "results": search_results,
            "total_results": len(search_results),
            "search_time_ms": 45,  # Simulated search time
            "pagination": {
                "page": page,
                "limit": limit,
                "has_next": len(search_results) >= limit,
                "has_prev": page > 1,
            },
            "mobile_config": config,
            "suggestions": (
                [f"{q} official", f"{q} live", f"{q} acoustic"] if len(q) > 2 else []
            ),
        }

        return JSONResponse(response)

    except Exception as e:
        logger.error(f"Failed to perform mobile search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mobile Streaming


@mobile_router.get("/stream/{video_id}")
async def stream_video_mobile(
    video_id: str,
    request: Request,
    quality: str = Query("auto", regex="^(auto|low|medium|high)$"),
    range_header: Optional[str] = Header(None, alias="range"),
):
    """Stream video optimized for mobile devices"""
    try:
        config = await get_mobile_optimized_config(request)

        # Auto-select quality for mobile
        if quality == "auto":
            quality = config["streaming_quality"]

        # This would integrate with actual video streaming logic
        # For now, return a placeholder response

        # In production, this would:
        # 1. Validate video exists and user has access
        # 2. Select appropriate quality/bitrate for device
        # 3. Handle HTTP range requests for seeking
        # 4. Stream video with mobile-optimized chunks

        return JSONResponse(
            {
                "message": "Video streaming endpoint",
                "video_id": video_id,
                "quality": quality,
                "mobile_optimized": config["is_mobile"],
                "supports_range_requests": True,
                "chunk_size_kb": 64 if config["is_mobile"] else 256,
            }
        )

    except Exception as e:
        logger.error(f"Failed to stream video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mobile_router.get("/thumbnail/{item_id}")
async def get_mobile_thumbnail(
    item_id: str,
    request: Request,
    size: str = Query("auto", regex="^(auto|small|medium|large)$"),
    quality: str = Query("medium", regex="^(low|medium|high)$"),
):
    """Get thumbnail optimized for mobile display"""
    try:
        config = await get_mobile_optimized_config(request)

        # Auto-select thumbnail size for mobile
        if size == "auto":
            size = config["thumbnail_size"]

        # Mobile thumbnail specifications
        thumbnail_specs = {
            "small": {"width": 160, "height": 90, "quality": 75},
            "medium": {"width": 320, "height": 180, "quality": 85},
            "large": {"width": 480, "height": 270, "quality": 95},
        }

        spec = thumbnail_specs.get(size, thumbnail_specs["medium"])

        # This would generate/serve actual thumbnail
        # For now, return thumbnail metadata

        return JSONResponse(
            {
                "item_id": item_id,
                "size": size,
                "dimensions": f"{spec['width']}x{spec['height']}",
                "quality": spec["quality"],
                "mobile_optimized": config["is_mobile"],
                "format": "webp" if config["is_mobile"] else "jpeg",
                "cache_duration": 86400,  # 24 hours
            }
        )

    except Exception as e:
        logger.error(f"Failed to get thumbnail for {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mobile Download


@mobile_router.get("/download/{video_id}")
async def download_video_mobile(
    video_id: str,
    request: Request,
    quality: str = Query("medium", regex="^(low|medium|high)$"),
    format: str = Query("mp4", regex="^(mp4|webm)$"),
):
    """Download video with mobile-optimized settings"""
    try:
        config = await get_mobile_optimized_config(request)

        # Check if downloads are allowed for mobile
        if config["is_mobile"] and not config.get("enable_downloads", True):
            raise HTTPException(
                status_code=403, detail="Downloads not available on this device"
            )

        # This would handle actual file download
        # For now, return download information

        return JSONResponse(
            {
                "video_id": video_id,
                "download_url": f"/api/download/{video_id}?quality={quality}&format={format}",
                "quality": quality,
                "format": format,
                "mobile_optimized": True,
                "estimated_size_mb": (
                    25 if quality == "low" else 45 if quality == "medium" else 85
                ),
                "estimated_download_time_minutes": (
                    2 if quality == "low" else 4 if quality == "medium" else 8
                ),
                "expires_at": (
                    datetime.now()
                ).isoformat(),  # Would be actual expiration
            }
        )

    except Exception as e:
        logger.error(f"Failed to prepare download for {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mobile Playlists


@mobile_router.get("/playlists")
async def get_mobile_playlists(
    request: Request, page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=25)
):
    """Get playlists optimized for mobile"""
    try:
        config = await get_mobile_optimized_config(request)

        # Sample playlists
        playlists = [
            {
                "id": "playlist_1",
                "name": "Favorites",
                "description": "My favorite music videos",
                "video_count": 23,
                "duration_minutes": 92,
                "thumbnail_url": "/mobile/thumbnail/playlist_1",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-09T10:00:00Z",
                "mobile_optimized": True,
            },
            {
                "id": "playlist_2",
                "name": "Recently Added",
                "description": "Latest additions to collection",
                "video_count": 15,
                "duration_minutes": 67,
                "thumbnail_url": "/mobile/thumbnail/playlist_2",
                "created_at": "2025-01-05T00:00:00Z",
                "updated_at": "2025-01-09T09:30:00Z",
                "mobile_optimized": True,
            },
        ]

        # Paginate
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_playlists = playlists[start_idx:end_idx]

        response = {
            "playlists": paginated_playlists,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_pages": (len(playlists) + limit - 1) // limit,
                "total_items": len(playlists),
                "has_next": end_idx < len(playlists),
                "has_prev": page > 1,
            },
            "mobile_config": config,
        }

        return JSONResponse(response)

    except Exception as e:
        logger.error(f"Failed to get mobile playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mobile_router.get("/playlists/{playlist_id}")
async def get_mobile_playlist_videos(
    playlist_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=30),
):
    """Get playlist videos optimized for mobile"""
    try:
        config = await get_mobile_optimized_config(request)

        # Sample playlist videos
        playlist_info = {
            "id": playlist_id,
            "name": "Sample Playlist",
            "description": "Sample playlist description",
            "video_count": 45,
            "total_duration_minutes": 180,
            "created_at": "2025-01-01T00:00:00Z",
        }

        # Sample videos in playlist
        videos = [
            {
                "id": f"playlist_video_{i}",
                "title": f"Playlist Video {i+1}",
                "artist": f"Artist {i+1}",
                "duration": 200 + i * 10,
                "position_in_playlist": i + 1,
                "thumbnail_url": f"/mobile/thumbnail/playlist_video_{i}",
                "stream_url": f"/mobile/stream/playlist_video_{i}",
                "mobile_optimized": True,
            }
            for i in range(min(limit, 25))
        ]

        response = {
            "playlist": playlist_info,
            "videos": videos,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_pages": (playlist_info["video_count"] + limit - 1) // limit,
                "total_items": playlist_info["video_count"],
                "has_next": page * limit < playlist_info["video_count"],
                "has_prev": page > 1,
            },
            "mobile_config": config,
        }

        return JSONResponse(response)

    except Exception as e:
        logger.error(f"Failed to get playlist {playlist_id} videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mobile App Interface


@mobile_router.get("/app", response_class=HTMLResponse)
async def get_mobile_app_interface(request: Request):
    """Get mobile web app interface"""
    try:
        config = await get_mobile_optimized_config(request)

        # Simple mobile web app HTML
        mobile_app_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
            <title>MVidarr Mobile</title>
            <meta name="description" content="MVidarr Music Video Collection - Mobile Access">
            <meta name="theme-color" content="#1a1a1a">
            <link rel="manifest" href="/mobile/manifest.json">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #000; color: #fff; line-height: 1.4;
                }}
                .header {{ 
                    background: #1a1a1a; padding: 15px; text-align: center;
                    border-bottom: 1px solid #333; position: sticky; top: 0; z-index: 100;
                }}
                .nav {{ 
                    display: flex; justify-content: space-around; padding: 10px 0;
                    background: #222; border-top: 1px solid #333;
                }}
                .nav button {{ 
                    background: none; border: none; color: #fff; padding: 10px;
                    font-size: 14px; cursor: pointer; flex: 1;
                }}
                .nav button:hover {{ background: #333; }}
                .content {{ padding: 15px; min-height: calc(100vh - 140px); }}
                .video-grid {{ 
                    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                    gap: 15px; margin-top: 15px;
                }}
                .video-card {{ 
                    background: #1a1a1a; border-radius: 8px; overflow: hidden;
                    border: 1px solid #333; cursor: pointer;
                }}
                .video-thumbnail {{ 
                    width: 100%; height: 85px; background: #333;
                    display: flex; align-items: center; justify-content: center;
                    color: #666; font-size: 12px;
                }}
                .video-info {{ padding: 10px; }}
                .video-title {{ font-size: 13px; font-weight: bold; margin-bottom: 4px; }}
                .video-artist {{ font-size: 11px; color: #999; }}
                .loading {{ text-align: center; padding: 40px; color: #666; }}
                @media (max-width: 480px) {{
                    .video-grid {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }}
                    .content {{ padding: 10px; }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎬 MVidarr Mobile</h1>
                <div>Music Video Collection</div>
            </div>
            
            <div class="content">
                <div id="app-content">
                    <div class="loading">Loading collections...</div>
                </div>
            </div>
            
            <div class="nav">
                <button onclick="loadCollections()">📁 Collections</button>
                <button onclick="loadSearch()">🔍 Search</button>
                <button onclick="loadPlaylists()">📋 Playlists</button>
                <button onclick="loadSettings()">⚙️ Settings</button>
            </div>
            
            <script>
                const deviceConfig = {json.dumps(config)};
                
                async function loadCollections() {{
                    try {{
                        const response = await fetch('/mobile/collections');
                        const data = await response.json();
                        
                        let html = '<h2>Collections</h2><div class="video-grid">';
                        data.collections.forEach(collection => {{
                            html += `
                                <div class="video-card" onclick="loadCollection('${{collection.id}}')">
                                    <div class="video-thumbnail">${{collection.video_count}} videos</div>
                                    <div class="video-info">
                                        <div class="video-title">${{collection.name}}</div>
                                        <div class="video-artist">${{collection.description}}</div>
                                    </div>
                                </div>`;
                        }});
                        html += '</div>';
                        
                        document.getElementById('app-content').innerHTML = html;
                    }} catch (error) {{
                        document.getElementById('app-content').innerHTML = '<div class="loading">Error loading collections</div>';
                    }}
                }}
                
                async function loadCollection(collectionId) {{
                    try {{
                        const response = await fetch(`/mobile/collections/${{collectionId}}`);
                        const data = await response.json();
                        
                        let html = `<h2>${{data.collection_id}}</h2><div class="video-grid">`;
                        data.videos.forEach(video => {{
                            html += `
                                <div class="video-card" onclick="playVideo('${{video.id}}')">
                                    <div class="video-thumbnail">▶️</div>
                                    <div class="video-info">
                                        <div class="video-title">${{video.title}}</div>
                                        <div class="video-artist">${{video.artist}}</div>
                                    </div>
                                </div>`;
                        }});
                        html += '</div>';
                        
                        document.getElementById('app-content').innerHTML = html;
                    }} catch (error) {{
                        document.getElementById('app-content').innerHTML = '<div class="loading">Error loading videos</div>';
                    }}
                }}
                
                function loadSearch() {{
                    const html = `
                        <h2>Search</h2>
                        <input type="text" id="searchInput" placeholder="Search music videos..." 
                               style="width: 100%; padding: 12px; margin: 15px 0; background: #1a1a1a; 
                               border: 1px solid #333; color: #fff; border-radius: 6px;"
                               onkeypress="if(event.key === 'Enter') performSearch()">
                        <div id="searchResults"></div>
                    `;
                    document.getElementById('app-content').innerHTML = html;
                }}
                
                function loadPlaylists() {{
                    document.getElementById('app-content').innerHTML = '<div class="loading">Loading playlists...</div>';
                    fetch('/mobile/playlists')
                        .then(response => response.json())
                        .then(data => {{
                            let html = '<h2>Playlists</h2><div class="video-grid">';
                            data.playlists.forEach(playlist => {{
                                html += `
                                    <div class="video-card" onclick="loadPlaylist('${{playlist.id}}')">
                                        <div class="video-thumbnail">${{playlist.video_count}} videos</div>
                                        <div class="video-info">
                                            <div class="video-title">${{playlist.name}}</div>
                                            <div class="video-artist">${{playlist.description}}</div>
                                        </div>
                                    </div>`;
                            }});
                            html += '</div>';
                            document.getElementById('app-content').innerHTML = html;
                        }})
                        .catch(error => {{
                            document.getElementById('app-content').innerHTML = '<div class="loading">Error loading playlists</div>';
                        }});
                }}
                
                function loadSettings() {{
                    const html = `
                        <h2>Settings</h2>
                        <div style="padding: 15px 0;">
                            <div><strong>Device:</strong> ${{deviceConfig.device_type}}</div>
                            <div><strong>Quality:</strong> ${{deviceConfig.streaming_quality}}</div>
                            <div><strong>Mobile Optimized:</strong> ${{deviceConfig.is_mobile ? 'Yes' : 'No'}}</div>
                        </div>
                    `;
                    document.getElementById('app-content').innerHTML = html;
                }}
                
                function playVideo(videoId) {{
                    alert(`Playing video: ${{videoId}}`);
                    // In production, this would open video player
                }}
                
                // Initialize app
                loadCollections();
            </script>
        </body>
        </html>
        """

        return HTMLResponse(content=mobile_app_html)

    except Exception as e:
        logger.error(f"Failed to generate mobile app interface: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mobile_router.get("/manifest.json")
async def get_mobile_app_manifest():
    """Get Progressive Web App manifest"""
    manifest = {
        "name": "MVidarr Mobile",
        "short_name": "MVidarr",
        "description": "MVidarr Music Video Collection - Mobile Access",
        "start_url": "/mobile/app",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#1a1a1a",
        "orientation": "portrait",
        "icons": [
            {
                "src": "/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "/static/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
        "categories": ["music", "video", "entertainment"],
        "screenshots": [],
    }

    return JSONResponse(manifest)


# Mobile Device Management


@mobile_router.post("/register-device")
async def register_mobile_device(request: Request, device_info: Dict[str, Any]):
    """Register mobile device for optimized experience"""
    try:
        config = await get_mobile_optimized_config(request)
        network_share = await get_local_network_share()

        # Get client IP
        client_ip = request.client.host

        # Register device with network sharing service
        success = await network_share.set_device_access_level(
            client_ip,
            access_level="streaming_only",  # Default mobile access
            trusted=False,
        )

        if success:
            return JSONResponse(
                {
                    "success": True,
                    "device_registered": True,
                    "client_ip": client_ip,
                    "mobile_config": config,
                    "access_level": "streaming_only",
                }
            )
        else:
            return JSONResponse(
                {"success": False, "error": "Failed to register device"}
            )

    except Exception as e:
        logger.error(f"Failed to register mobile device: {e}")
        raise HTTPException(status_code=500, detail=str(e))
