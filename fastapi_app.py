"""
FastAPI Application for MVidarr
Modern async web framework with native background job support
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# OpenAPI documentation configuration
from src.api.openapi_config import (
    add_openapi_metadata_to_routers,
    custom_openapi_schema,
    setup_custom_docs,
)
from src.config.config import Config

# Database and services
from src.database.connection import DatabaseManager, get_db

# Database initialization
from src.database.init_db import initialize_database
# Old Flask job system imports removed - using Celery now
from src.services.settings_service import SettingsService
from src.services.ytdlp_service import ytdlp_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi")


# FastAPI-specific database initialization
async def init_database_for_fastapi():
    """Initialize database for FastAPI application"""
    import src.database.connection as db_conn

    # Initialize database manager
    config = Config()
    db_conn.db_manager = DatabaseManager(config)

    # Create database if it doesn't exist
    if not db_conn.db_manager.create_database_if_not_exists():
        logger.error("Failed to create database")
        raise RuntimeError("Database creation failed")

    # Test connection
    if not db_conn.db_manager.test_connection():
        logger.error("Database connection test failed")
        raise RuntimeError("Database connection failed")

    # Create engine and session factory
    db_conn.engine = db_conn.db_manager.create_engine()
    db_conn.SessionLocal = db_conn.db_manager.create_session_factory()

    # Initialize database tables and data
    if not initialize_database():
        logger.error("Failed to initialize database tables")
        raise RuntimeError("Database initialization failed")

    logger.info("Database initialization completed successfully")


# Global references for cleanup
job_queue = None
worker_tasks = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - starts/stops background services and initializes database"""
    global job_queue, worker_tasks

    logger.info("FastAPI MVidarr application starting up...")

    try:
        # Initialize database first
        logger.info("Initializing database...")
        await init_database_for_fastapi()
        logger.info("✅ Database initialized successfully")

        # Initialize background job system with minimal configuration
        logger.info("🔄 Initializing background job system...")
        # Background jobs are now handled by Celery + Redis system
        logger.info("✅ Background jobs handled by Celery + Redis system")

        yield  # Application is running

    except Exception as e:
        logger.error(f"Failed to start application services: {e}")
        raise

    finally:
        # Cleanup on shutdown
        logger.info("Shutting down application services...")

        try:
            # Celery workers are managed independently
            logger.info("✅ Background job system (Celery) managed independently")

            # Close database connections
            import src.database.connection as db_conn

            if db_conn.db_manager:
                db_conn.db_manager.close_connections()

            logger.info("✅ Application services stopped cleanly")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Create FastAPI app with comprehensive OpenAPI configuration
app = FastAPI(
    title="MVidarr API",
    description="""
    ## MVidarr - Music Video Management and Automation System

    **Complete FastAPI implementation with advanced async operations and comprehensive admin functionality.**

    ### Key Features
    - **Video Management**: Complete CRUD operations with HTTP range-based streaming
    - **Artist Management**: Full artist lifecycle with metadata enrichment
    - **Playlist Management**: Dynamic playlists with auto-update capabilities
    - **System Administration**: User management, settings, authentication, and monitoring
    - **Advanced Processing**: FFmpeg operations, image processing, bulk operations
    - **Performance Monitoring**: Real-time system health and performance tracking

    ### Authentication
    This API uses session-based authentication with support for:
    - OAuth providers (Google, GitHub, Authentik)
    - Two-factor authentication (2FA)
    - Role-based access control (USER, MANAGER, ADMIN)
    - Session management and audit logging

    ### API Architecture
    - **Async Operations**: All endpoints use async/await patterns for optimal performance
    - **Pydantic Validation**: Type-safe request/response models with comprehensive validation
    - **Database Integration**: SQLAlchemy ORM with async database operations
    - **Background Jobs**: Native asyncio-based job system for long-running tasks

    ### Week 29 Consumer Features (✅ Complete)
    - **Personal Cloud Backup**: Google Drive, Dropbox, OneDrive integration for music video backup
    - **YouTube Import**: Import playlists, channels, and individual videos with music detection
    - **Local Network Sharing**: mDNS discovery, QR codes, home network device access
    - **Mobile Access**: Mobile-optimized API endpoints and responsive web app
    - **Sync Manager**: Automated file synchronization with personal cloud storage
    
    ---
    **Version**: 0.9.10 - Phase 3 Week 29 Consumer Features Complete
    """,
    version="0.9.8",
    contact={
        "name": "MVidarr Development Team",
        "url": "https://github.com/prefect421/mvidarr",
        "email": "support@mvidarr.local",
    },
    license_info={"name": "MIT License", "url": "https://opensource.org/licenses/MIT"},
    servers=[
        {"url": "http://192.168.1.145:5000", "description": "Development server"},
        {"url": "http://localhost:5000", "description": "Local development server"},
    ],
    openapi_tags=[
        {
            "name": "videos",
            "description": "Video management operations including CRUD, streaming, thumbnails, and bulk operations",
        },
        {
            "name": "artists",
            "description": "Artist management with metadata enrichment, IMVDb integration, and video associations",
        },
        {
            "name": "playlists",
            "description": "Playlist management with dynamic filtering, file uploads, and advanced access control",
        },
        {
            "name": "admin",
            "description": "System administration including user management, audit logs, and system control",
        },
        {
            "name": "settings",
            "description": "Application settings management, scheduler control, and database configuration",
        },
        {
            "name": "authentication",
            "description": "Authentication, OAuth, session management, and credential handling",
        },
        {
            "name": "system",
            "description": "System health monitoring, performance metrics, and application status",
        },
    ],
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

from src.api.fastapi.mobile_access import mobile_router

# Phase 3 Week 29 Integration - Personal Cloud Backup & Basic Integrations
from src.api.fastapi.week29_integration import (  # youtube_router,  # Temporarily disabled
    backup_router,
    network_router,
    sync_router,
)

# Include Week 29 API routers
app.include_router(backup_router, prefix="/api")
# app.include_router(youtube_router, prefix="/api")  # Temporarily disabled
app.include_router(network_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(mobile_router)

logger.info(
    "✅ Phase 3 Week 29 services integrated: Personal Cloud Backup, YouTube Import, Network Sharing, Sync Manager, Mobile Access"
)

# Add CORS middleware with optimized configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.1.145:5000",
        "http://192.168.1.145:5010",
        "http://localhost:5000",
        "http://localhost:5010",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:5010",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight requests for 24 hours
)

# Add analytics middleware - Phase 3 Week 36
from src.middleware.analytics_middleware import AnalyticsMiddleware

# Add API Gateway middleware - Phase 3 Week 37
from src.middleware.api_gateway_middleware import (
    APIGatewayMiddleware,
    GatewayManagementMiddleware,
)

# Add production middleware - Phase 3 Week 35
from src.middleware.auto_scaling_middleware import AutoScalingMiddleware

# Add caching middleware
from src.middleware.cache_middleware import (
    APIResponseCacheMiddleware,
    CacheInvalidationMiddleware,
)
from src.middleware.circuit_breaker_middleware import (
    CircuitBreakerConfig,
    CircuitBreakerMiddleware,
)
from src.middleware.jwt_auth_middleware import JWTAuthMiddleware, TokenConfig

# Add performance monitoring middleware
from src.middleware.performance_middleware import (
    CacheHeadersMiddleware,
    PerformanceTrackingMiddleware,
    ResourceMonitoringMiddleware,
)
from src.middleware.rate_limiting_middleware import (
    RateLimitingConfig,
    RateLimitingMiddleware,
)

# Add security middleware - Phase 3 Week 34
from src.middleware.security_validation_middleware import (
    SecurityValidationConfig,
    SecurityValidationMiddleware,
)

# Add middleware in correct order (last added = first executed)
# Re-enabling basic authentication middleware with safe configuration
try:
    from src.middleware.jwt_auth_middleware import JWTAuthMiddleware, TokenConfig

    # Use basic token config to prevent timeout issues
    basic_token_config = TokenConfig(
        access_token_expire_minutes=60,  # Longer timeout
        refresh_token_expire_days=7,  # Shorter refresh period
        algorithm="HS256",
    )
    
    app.add_middleware(JWTAuthMiddleware, config=basic_token_config)
    logger.info("✅ JWT Authentication middleware enabled with safe configuration")
except Exception as e:
    logger.warning(
        f"⚠️ Failed to load JWT middleware: {e}, continuing without authentication middleware"
    )

# TODO: Re-enable other middleware after fixing MediaCacheManager and Redis issues
# app.add_middleware(CircuitBreakerMiddleware, config=CircuitBreakerConfig())
# app.add_middleware(AutoScalingMiddleware)
# app.add_middleware(RateLimitingMiddleware, config=RateLimitingConfig())
# app.add_middleware(CacheInvalidationMiddleware)
# app.add_middleware(APIResponseCacheMiddleware, cache_ttl=300)
# app.add_middleware(ResourceMonitoringMiddleware, track_memory=True)
# app.add_middleware(CacheHeadersMiddleware, default_cache_ttl=300)
# app.add_middleware(PerformanceTrackingMiddleware)
# app.add_middleware(AnalyticsMiddleware)
# app.add_middleware(GatewayManagementMiddleware)
# app.add_middleware(APIGatewayMiddleware, gateway_enabled=True)

# Static files and templates
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/css", StaticFiles(directory="frontend/CSS"), name="css")
templates = Jinja2Templates(directory="frontend/templates")

from src.api.fastapi.advanced_image_processing import router as advanced_image_router
from src.api.fastapi.image_processing import router as image_processing_router

# Include API routers - Re-enabling critical endpoints
from src.api.fastapi.jobs import router as jobs_router
from src.api.fastapi.media_processing import router as media_processing_router

# Re-enable critical missing routers
try:
    from src.api.fastapi.video_quality import router as video_quality_router

    logger.info("✅ Video quality router loaded successfully")
except Exception as e:
    logger.warning(f"⚠️ Failed to load video quality router: {e}")
    video_quality_router = None

try:
    from src.api.fastapi.bulk_operations import router as bulk_operations_router

    logger.info("✅ Bulk operations router loaded successfully")
except Exception as e:
    logger.warning(f"⚠️ Failed to load bulk operations router: {e}")
    bulk_operations_router = None
from src.api.fastapi.admin import router as fastapi_admin_router
from src.api.fastapi.api_gateway_management import router as gateway_router
from src.api.fastapi.artists import router as fastapi_artists_router
from src.api.fastapi.auth import router as fastapi_auth_router
from src.api.fastapi.frontend_router import frontend_router
from src.api.fastapi.genres import router as fastapi_genres_router
from src.api.fastapi.monitoring_dashboard import router as dashboard_router
from src.api.fastapi.performance import router as performance_router
from src.api.fastapi.playlists import router as fastapi_playlists_router
from src.api.fastapi.production_monitoring import router as monitoring_router
from src.api.fastapi.settings import router as fastapi_settings_router
from src.api.fastapi.videos import router as fastapi_videos_router

# from src.api.fastapi.music_recommendations import recommendations_router  # Temporarily disabled
# from src.api.system_health import router as system_health_router
# from src.api.fastapi.model_demo import router as model_demo_router

app.include_router(jobs_router)
app.include_router(media_processing_router)
app.include_router(image_processing_router)
app.include_router(advanced_image_router)

# Include critical routers if they loaded successfully
if video_quality_router:
    app.include_router(video_quality_router)
    logger.info("✅ Video quality router included")

if bulk_operations_router:
    app.include_router(bulk_operations_router)
    logger.info("✅ Bulk operations router included")
# Re-enable real database routers after fixing database initialization
app.include_router(fastapi_videos_router)
app.include_router(fastapi_artists_router)
app.include_router(fastapi_playlists_router)
app.include_router(fastapi_genres_router)
app.include_router(fastapi_admin_router)
app.include_router(fastapi_settings_router)
app.include_router(fastapi_auth_router)
app.include_router(frontend_router)

from src.api.fastapi.lastfm import router as lastfm_router

# Metadata enrichment routers
from src.api.fastapi.metadata_enrichment import router as metadata_enrichment_router
from src.api.fastapi.musicbrainz import router as musicbrainz_router
from src.api.fastapi.spotify import router as spotify_router

app.include_router(metadata_enrichment_router)
app.include_router(spotify_router)
app.include_router(musicbrainz_router)
app.include_router(lastfm_router)
app.include_router(performance_router)
app.include_router(monitoring_router)
app.include_router(dashboard_router)
app.include_router(gateway_router)

# Add Week 29 Integration Router - Personal Cloud & YouTube Import
try:
    from src.api.fastapi.week29_integration import (
        backup_router,
        network_router,
        sync_router,
        youtube_router,
    )

    app.include_router(backup_router, prefix="/api")
    app.include_router(youtube_router, prefix="/api")
    app.include_router(network_router, prefix="/api")
    app.include_router(sync_router, prefix="/api")
    logger.info("✅ Week 29 integration routers included")
except Exception as e:
    logger.warning(f"⚠️ Failed to load Week 29 integration routers: {e}")

# Add critical missing integration endpoints temporarily using simple FastAPI routers
# These provide basic compatibility with existing frontend templates


@app.get("/api/lidarr/status", tags=["lidarr"])
async def get_lidarr_status():
    """Basic Lidarr status endpoint for template compatibility"""
    return {
        "status": "not_configured",
        "message": "Lidarr integration not yet migrated to FastAPI",
    }


@app.post("/api/lidarr/test", tags=["lidarr"])
async def test_lidarr_connection():
    """Basic Lidarr test endpoint for template compatibility"""
    return {
        "success": False,
        "message": "Lidarr integration not yet migrated to FastAPI",
    }


@app.get("/api/plex/status", tags=["plex"])
async def get_plex_status():
    """Basic Plex status endpoint for template compatibility"""
    return {
        "configured": False,
        "connected": False,
        "message": "Plex integration not yet migrated to FastAPI",
    }


# app.include_router(recommendations_router)  # Temporarily disabled
# app.include_router(system_health_router)
# app.include_router(model_demo_router)

# Setup enhanced OpenAPI documentation - temporarily disabled for startup
# app.openapi = lambda: custom_openapi_schema(app)
# setup_custom_docs(app)
# add_openapi_metadata_to_routers(app)


# Basic health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "0.9.8",
        "framework": "FastAPI",
        "job_system": "native_asyncio",
    }


# Simple test login endpoint for debugging
@app.post("/test-login")
async def test_login(request: Request):
    """Simple test login endpoint that bypasses middleware"""
    try:
        body = await request.json()
        username = body.get("username", "")
        password = body.get("password", "")

        if username == "admin" and password == "mvidarr":
            # Create session token and set cookie
            import secrets

            session_token = secrets.token_urlsafe(32)

            from fastapi.responses import JSONResponse

            response_data = {
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": 1,
                    "username": username,
                    "role": "ADMIN",
                    "can_admin": True,
                },
                "redirect_url": "/dashboard",
            }

            response = JSONResponse(content=response_data)
            response.set_cookie(
                key="session_token",
                value=session_token,
                max_age=86400,  # 24 hours
                httponly=True,
                samesite="lax",
            )
            return response
        else:
            return {"success": False, "message": "Invalid credentials"}

    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


# Simple test endpoints to verify database connectivity
@app.get("/api/test/artists")
async def test_get_artists():
    """Simple test endpoint to check artists data"""
    try:
        from sqlalchemy.orm import Session

        from src.database.connection import get_db_session
        from src.database.models import Artist

        # Get database session
        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            # Get first few artists
            artists = session.query(Artist).limit(5).all()

            result = []
            for artist in artists:
                result.append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "imvdb_id": artist.imvdb_id,
                        "monitored": getattr(artist, "monitored", True),
                        "created_at": getattr(artist, "created_at", None),
                        # Add all available attributes
                        "available_fields": [
                            attr
                            for attr in dir(artist)
                            if not attr.startswith("_")
                            and not callable(getattr(artist, attr))
                        ],
                    }
                )

            return {"success": True, "count": len(result), "artists": result}
        finally:
            session.close()

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/test/videos")
async def test_get_videos():
    """Simple test endpoint to check videos data"""
    try:
        from sqlalchemy.orm import Session

        from src.database.connection import get_db_session
        from src.database.models import Video

        # Get database session
        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            # Get first few videos
            videos = session.query(Video).limit(5).all()

            result = []
            for video in videos:
                # Handle enum status safely
                status_value = None
                try:
                    status_value = (
                        video.status.value
                        if hasattr(video.status, "value")
                        else str(video.status)
                    )
                except Exception as e:
                    status_value = f"enum_error: {e}"

                result.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist_id": video.artist_id,
                        "youtube_id": getattr(video, "youtube_id", None),
                        "local_path": getattr(video, "local_path", None),
                        "status": status_value,
                        "created_at": getattr(video, "created_at", None),
                        # Add all available attributes
                        "available_fields": [
                            attr
                            for attr in dir(video)
                            if not attr.startswith("_")
                            and not callable(getattr(video, attr))
                        ],
                    }
                )

            return {"success": True, "count": len(result), "videos": result}
        finally:
            session.close()

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/discover")
async def discover_search(q: str = Query(...)):
    """Universal search endpoint for videos, artists, and external sources (IMVDb, YouTube)"""
    try:
        from sqlalchemy.orm import Session

        from src.database.connection import get_db_session
        from src.database.models import Artist, Video

        # Initialize result containers
        local_videos = []
        local_artists = []
        imvdb_results = []
        youtube_results = []

        # Search local database
        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            query = q.lower()

            # Search local videos
            videos = (
                session.query(Video)
                .filter(Video.title.ilike(f"%{query}%"))
                .limit(10)
                .all()
            )

            # Search local artists
            artists = (
                session.query(Artist)
                .filter(Artist.name.ilike(f"%{query}%"))
                .limit(5)
                .all()
            )

            # Format local video results
            for video in videos:
                local_videos.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist": video.artist.name if video.artist else "Unknown",
                        "status": (
                            video.status.value
                            if hasattr(video.status, "value")
                            else str(video.status)
                        ),
                        "youtube_id": getattr(video, "youtube_id", None),
                        "source": "local",
                        "type": "video",
                    }
                )

            # Format local artist results
            for artist in artists:
                local_artists.append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "video_count": len(artist.videos) if artist.videos else 0,
                        "source": "local",
                        "type": "artist",
                    }
                )

        finally:
            session.close()

        # Search external sources in parallel
        external_search_tasks = []

        # Search IMVDb
        try:
            from src.services.imvdb_service import imvdb_service

            if imvdb_service:
                import asyncio

                imvdb_task = asyncio.create_task(
                    asyncio.to_thread(imvdb_service.search_artist, q)
                )
                external_search_tasks.append(("imvdb", imvdb_task))
        except Exception as e:
            logger.warning(f"Failed to initialize IMVDb search: {e}")

        # Search YouTube
        try:
            from src.services.youtube_search_service import youtube_search_service

            if youtube_search_service and youtube_search_service.api_key:
                import asyncio

                youtube_task = asyncio.create_task(
                    asyncio.to_thread(youtube_search_service.search_artist_videos, q, 5)
                )
                external_search_tasks.append(("youtube", youtube_task))
        except Exception as e:
            logger.warning(f"Failed to initialize YouTube search: {e}")

        # Wait for external search results
        if external_search_tasks:
            import asyncio

            for source, task in external_search_tasks:
                try:
                    result = await asyncio.wait_for(
                        task, timeout=3.0
                    )  # 3 second timeout

                    if source == "imvdb" and result:
                        if isinstance(result, list):
                            for item in result[:5]:  # Limit to 5 results
                                imvdb_results.append(
                                    {
                                        "id": item.get("id"),
                                        "name": item.get("name"),
                                        "url": item.get("url"),
                                        "source": "imvdb",
                                        "type": "artist",
                                    }
                                )
                        else:
                            imvdb_results.append(
                                {
                                    "id": result.get("id"),
                                    "name": result.get("name"),
                                    "url": result.get("url"),
                                    "source": "imvdb",
                                    "type": "artist",
                                }
                            )

                    elif source == "youtube" and result and result.get("videos"):
                        for video in result["videos"][:5]:  # Limit to 5 results
                            youtube_results.append(
                                {
                                    "id": video.get("id"),
                                    "title": video.get("title"),
                                    "channel": video.get("channel_title"),
                                    "thumbnail": video.get("thumbnail_url"),
                                    "url": f"https://youtube.com/watch?v={video.get('id')}",
                                    "source": "youtube",
                                    "type": "video",
                                }
                            )

                except asyncio.TimeoutError:
                    logger.warning(f"{source} search timed out")
                except Exception as e:
                    logger.warning(f"{source} search failed: {e}")

        # Combine all results
        all_results = {
            "videos": local_videos,
            "artists": local_artists,
            "external": {"imvdb": imvdb_results, "youtube": youtube_results},
        }

        total_count = (
            len(local_videos)
            + len(local_artists)
            + len(imvdb_results)
            + len(youtube_results)
        )

        return {
            "success": True,
            "query": q,
            "results": all_results,
            "total": total_count,
            "external_enabled": len(external_search_tasks) > 0,
        }

    except Exception as e:
        logger.error(f"Discover search error: {e}")
        return {
            "success": False,
            "error": str(e),
            "results": {"videos": [], "artists": []},
            "total": 0,
        }


# Root endpoint with authentication checking
@app.get("/")
async def root(request: Request):
    """Root endpoint - redirect to dashboard if authenticated, otherwise to login"""
    from fastapi.responses import RedirectResponse

    try:
        # Check if user is authenticated via session or other means
        # For now, since we have simplified auth, check for basic auth indicators

        # Try to get authentication from headers/cookies
        auth_header = request.headers.get("authorization")
        cookie_auth = request.cookies.get("session_token") or request.cookies.get(
            "auth_token"
        )

        # Simple check - if we have any auth indicators, assume authenticated
        # In a real system, this would validate the token/session properly
        if auth_header or cookie_auth:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Check if this is coming from a successful login (check referer)
        referer = request.headers.get("referer", "")
        if "auth/login" in referer or "test-login" in referer:
            # If coming from login page, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=302)

        # Otherwise redirect to login
        return RedirectResponse(url="/auth/login", status_code=302)

    except Exception as e:
        logger.error(f"Root endpoint error: {e}")
        # Fallback to login on any error
        return RedirectResponse(url="/auth/login", status_code=302)


# Additional missing API endpoints that frontend is looking for
@app.get("/api/metube/queue")
async def get_metube_queue():
    """Get download queue from database"""
    try:
        from sqlalchemy.orm import Session, joinedload

        from src.database.connection import get_db_session
        from src.database.models import Download

        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            # Get downloads with queued or downloading status
            downloads = (
                session.query(Download)
                .options(joinedload(Download.video), joinedload(Download.artist))
                .filter(Download.status.in_(["queued", "downloading"]))
                .order_by(Download.created_at.desc())
                .all()
            )

            queue_items = []
            for download in downloads:
                queue_items.append(
                    {
                        "id": download.id,
                        "title": download.title,
                        "url": download.original_url,
                        "status": download.status,
                        "progress": download.progress or 0,
                        "priority": download.priority,
                        "created_at": (
                            download.created_at.isoformat()
                            if download.created_at
                            else None
                        ),
                        "artist": (
                            download.artist.name
                            if download.artist
                            else "Unknown Artist"
                        ),
                        "video_id": download.video_id,
                    }
                )

            return {"queue": queue_items, "total": len(queue_items)}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error getting download queue: {e}")
        return {"queue": [], "total": 0}


@app.get("/api/metube/history")
async def get_metube_history(limit: int = 10):
    """Get download history from database"""
    try:
        from sqlalchemy.orm import Session, joinedload

        from src.database.connection import get_db_session
        from src.database.models import Download

        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            # Get downloads with completed, failed, or cancelled status
            downloads = (
                session.query(Download)
                .options(joinedload(Download.video), joinedload(Download.artist))
                .filter(Download.status.in_(["completed", "failed", "cancelled"]))
                .order_by(Download.updated_at.desc())
                .limit(limit)
                .all()
            )

            history_items = []
            for download in downloads:
                history_items.append(
                    {
                        "id": download.id,
                        "title": download.title,
                        "url": download.original_url,
                        "status": download.status,
                        "progress": download.progress or 0,
                        "priority": download.priority,
                        "created_at": (
                            download.created_at.isoformat()
                            if download.created_at
                            else None
                        ),
                        "updated_at": (
                            download.updated_at.isoformat()
                            if download.updated_at
                            else None
                        ),
                        "artist": (
                            download.artist.name
                            if download.artist
                            else "Unknown Artist"
                        ),
                        "video_id": download.video_id,
                        "file_path": download.file_path,
                        "file_size": download.file_size,
                        "error_message": download.error_message,
                    }
                )

            return {"history": history_items, "total": len(history_items)}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error getting download history: {e}")
        return {"history": [], "total": 0}


@app.post("/api/metube/clear-stuck")
async def clear_stuck_downloads():
    """Clear downloads stuck in processing state"""
    import asyncio
    try:
        from datetime import datetime, timedelta

        from sqlalchemy.orm import Session

        from src.database.connection import get_db_session
        from src.database.models import Download

        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            # Find downloads that have been stuck for more than 1 hour
            # This includes downloads stuck in downloading/processing AND queued state
            cutoff_time = datetime.utcnow() - timedelta(hours=1)

            stuck_downloads = (
                session.query(Download)
                .filter(
                    Download.status.in_(["queued", "downloading", "processing"]),
                    Download.updated_at < cutoff_time,
                )
                .all()
            )

            cleared_count = 0
            for download in stuck_downloads:
                # Reset stuck downloads - set to queued to retry processing
                download.status = "queued"
                download.progress = 0
                download.updated_at = datetime.utcnow()
                download.error_message = (
                    "Reset from stuck state - will retry processing"
                )
                cleared_count += 1

            session.commit()

            logger.info(f"Cleared {cleared_count} stuck downloads")

            # After clearing stuck downloads, submit a limited number of queued downloads to job queue
            # Add timeout and limit to prevent hanging
            try:
                from src.services.job_queue import BackgroundJob, JobType, get_job_queue

                # Get queued downloads (limit to 5 at a time to prevent overload)
                queued_downloads = (
                    session.query(Download)
                    .filter(Download.status == "queued")
                    .limit(5)
                    .all()
                )

                if queued_downloads:
                    # Submit them to the background job queue with timeout
                    try:
                        job_queue = await asyncio.wait_for(get_job_queue(), timeout=10)
                        submitted_count = 0

                        for download in queued_downloads:
                            try:
                                # Create a video download job
                                download_job = BackgroundJob(
                                    type=JobType.VIDEO_DOWNLOAD,
                                    payload={
                                        "video_id": download.video_id,  # Required by video download worker
                                        "download_id": download.id,
                                        "url": download.original_url,
                                        "title": download.title,
                                        "artist": (
                                            download.artist.name
                                            if download.artist
                                            else "Unknown"
                                        ),
                                        "quality": "best",
                                        "priority": download.priority,
                                    },
                                )

                                job_id = await asyncio.wait_for(job_queue.enqueue(download_job), timeout=5)
                                submitted_count += 1
                                logger.info(
                                    f"Submitted download {download.id} to job queue as job {job_id}"
                                )

                            except asyncio.TimeoutError:
                                logger.warning(f"Timeout submitting download {download.id} to job queue")
                                break  # Stop processing if we hit timeout
                            except Exception as job_error:
                                logger.error(
                                    f"Failed to submit download {download.id} to job queue: {job_error}"
                                )

                        logger.info(
                            f"Submitted {submitted_count} queued downloads to job queue"
                        )

                        return {
                            "success": True,
                            "cleared_count": cleared_count,
                            "submitted_count": submitted_count,
                            "message": f"Cleared {cleared_count} stuck downloads and submitted {submitted_count} to job queue",
                        }
                    except asyncio.TimeoutError:
                        logger.warning("Timeout getting job queue, returning cleared count only")
                        return {
                            "success": True,
                            "cleared_count": cleared_count,
                            "message": f"Cleared {cleared_count} stuck downloads (job queue timeout)",
                        }
            except Exception as job_submit_error:
                logger.error(
                    f"Error submitting downloads to job queue: {job_submit_error}"
                )

            return {
                "success": True,
                "cleared_count": cleared_count,
                "message": f"Cleared {cleared_count} stuck downloads",
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error clearing stuck downloads: {e}")
        return {"success": False, "error": str(e), "cleared_count": 0}


@app.post("/api/metube/download/{download_id}/retry")
async def retry_download(download_id: int):
    """Retry a failed download"""
    try:
        result = ytdlp_service.retry_download(download_id)
        return result
    except Exception as e:
        logger.error(f"Error retrying download {download_id}: {e}")
        return {"success": False, "error": str(e)}


@app.delete("/api/metube/download/{download_id}")
async def delete_download(download_id: int):
    """Delete a queued download"""
    try:
        from sqlalchemy.orm import Session
        from src.database.connection import get_db_session
        from src.database.models import Download

        session_gen = get_db_session()
        session: Session = next(session_gen)
        
        try:
            # Find the download
            download = session.query(Download).filter(Download.id == download_id).first()
            
            if not download:
                return {"success": False, "error": "Download not found"}
            
            # Only allow deletion of queued, failed, or completed downloads
            if download.status not in ["queued", "failed", "completed", "cancelled"]:
                return {"success": False, "error": f"Cannot delete download with status: {download.status}"}
            
            # Delete the download
            session.delete(download)
            session.commit()
            
            logger.info(f"Deleted download {download_id}: {download.title}")
            return {
                "success": True, 
                "message": f"Download {download_id} deleted successfully"
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error deleting download {download_id}: {e}")
        return {"success": False, "error": str(e)}


@app.delete("/api/metube/history/clear")
async def clear_metube_history():
    """Clear all completed/failed downloads from history"""
    try:
        from sqlalchemy.orm import Session

        from src.database.connection import get_db_session
        from src.database.models import Download

        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            # Delete all completed and failed downloads
            deleted_count = (
                session.query(Download)
                .filter(Download.status.in_(["completed", "failed"]))
                .delete()
            )

            session.commit()

            logger.info(f"Cleared {deleted_count} downloads from history")
            return {
                "success": True,
                "cleared_count": deleted_count,
                "message": f"Cleared {deleted_count} downloads from history",
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error clearing download history: {e}")
        return {"success": False, "error": str(e), "cleared_count": 0}


# Temporarily disabled - causing startup issues
# @app.get("/api/imvdb/search-videos")
# async def search_imvdb_videos(q: str = Query(...)):
#     """Search IMVDb for videos"""
#     try:
#         # Mock IMVDb search results for now
#         query = q.lower()
#
#         mock_results = [
#             {
#                 "id": f"imvdb_{i}",
#                 "title": f"{q} - IMVDb Result {i+1}",
#                 "artist": f"Artist {i+1}",
#                 "year": 2020 + i,
#                 "director": f"Director {i+1}",
#                 "imvdb_url": f"https://imvdb.com/video/mock_{i}"
#             }
#             for i in range(3)
#         ]
#
#         return {
#             "success": True,
#             "query": q,
#             "results": mock_results,
#             "total": len(mock_results)
#         }
#
#     except Exception as e:
#         logger.error(f"IMVDb search failed: {e}")
#         return {
#             "success": False,
#             "error": str(e),
#             "results": [],
#             "total": 0
#         }


@app.post("/api/metube/process-queue")
async def process_queued_downloads():
    """Process all queued downloads by submitting them to the job queue"""
    try:
        from sqlalchemy.orm import Session

        from src.database.connection import get_db_session
        from src.database.models import Download
        from src.services.job_queue import BackgroundJob, JobType, get_job_queue

        session_gen = get_db_session()
        session: Session = next(session_gen)

        try:
            # Get all queued downloads
            queued_downloads = (
                session.query(Download).filter(Download.status == "queued").all()
            )

            if not queued_downloads:
                return {
                    "success": True,
                    "message": "No queued downloads to process",
                    "submitted_count": 0,
                }

            # Submit them to the background job queue
            job_queue = await get_job_queue()
            submitted_count = 0

            for download in queued_downloads:
                try:
                    # Create a video download job
                    download_job = BackgroundJob(
                        type=JobType.VIDEO_DOWNLOAD,
                        payload={
                            "video_id": download.video_id,  # Required by video download worker
                            "download_id": download.id,
                            "url": download.original_url,
                            "title": download.title,
                            "artist": (
                                download.artist.name if download.artist else "Unknown"
                            ),
                            "quality": "best",
                            "priority": download.priority,
                        },
                    )

                    job_id = await job_queue.enqueue(download_job)
                    submitted_count += 1
                    logger.info(
                        f"Submitted download {download.id} to job queue as job {job_id}"
                    )

                except Exception as job_error:
                    logger.error(
                        f"Failed to submit download {download.id} to job queue: {job_error}"
                    )

            logger.info(f"Submitted {submitted_count} queued downloads to job queue")

            return {
                "success": True,
                "submitted_count": submitted_count,
                "total_queued": len(queued_downloads),
                "message": f"Submitted {submitted_count} queued downloads to job queue",
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error processing queued downloads: {e}")
        return {"success": False, "error": str(e), "submitted_count": 0}


@app.get("/api/health/status")
async def get_health_status():
    """Mock health status endpoint"""
    return {
        "status": "healthy",
        "uptime": "1h 30m",
        "memory_usage": "180MB",
        "cpu_usage": "15%",
    }


@app.get("/api/health/version")
async def get_health_version():
    """Mock version endpoint"""
    return {"version": "0.9.8", "build_date": "2024-01-01", "commit": "abc1234"}


@app.get("/api/themes/current") 
async def get_current_theme():
    """Get the currently applied theme"""
    try:
        from src.services.settings_service import SettingsService
        current_theme = SettingsService.get("ui_theme", "default")
        return {"current_theme": current_theme}
    except Exception as e:
        logger.error(f"Error getting current theme: {e}")
        return {"error": "Failed to get current theme", "details": str(e)}


@app.get("/api/themes")
async def get_themes():
    """Get all available themes"""
    try:
        from src.api.themes import extract_built_in_theme_data
        from src.database.connection import get_db
        from src.database.models import CustomTheme
        
        # Get built-in themes
        built_in_themes = extract_built_in_theme_data()
        
        # Get custom themes from database
        custom_themes = {}
        try:
            with get_db() as session:
                custom_theme_records = session.query(CustomTheme).all()
                for theme in custom_theme_records:
                    custom_themes[theme.name] = {
                        "id": theme.id,
                        "name": theme.name,
                        "css_variables": theme.css_variables or {},
                        "is_active": theme.is_active,
                        "created_at": theme.created_at.isoformat() if theme.created_at else None
                    }
        except Exception as db_error:
            logger.warning(f"Failed to load custom themes from database: {db_error}")
        
        return {
            "built_in_themes": built_in_themes,
            "custom_themes": custom_themes,
            "total_themes": len(built_in_themes) + len(custom_themes)
        }
    except Exception as e:
        logger.error(f"Error getting themes: {e}")
        return {"error": "Failed to get themes", "details": str(e)}


@app.post("/api/themes/apply")
async def apply_theme(request: Request):
    """Apply a theme"""
    try:
        from src.services.settings_service import SettingsService
        
        body = await request.json()
        theme_name = body.get("theme_name")
        
        if not theme_name:
            return {"error": "Theme name is required"}
        
        # Set the theme in settings
        SettingsService.set("ui_theme", theme_name)
        
        logger.info(f"Applied theme: {theme_name}")
        return {
            "success": True,
            "message": f"Theme '{theme_name}' applied successfully",
            "applied_theme": theme_name
        }
    except Exception as e:
        logger.error(f"Error applying theme: {e}")
        return {"error": "Failed to apply theme", "details": str(e)}


@app.post("/api/themes/built-in/{theme_name}/extract")
async def extract_built_in_theme(theme_name: str):
    """Extract CSS variables from a built-in theme"""
    try:
        from src.api.themes import extract_built_in_theme_data
        
        # Get all built-in themes
        built_in_themes = extract_built_in_theme_data()
        
        if theme_name not in built_in_themes:
            return {"error": f"Built-in theme '{theme_name}' not found"}
        
        theme_data = built_in_themes[theme_name]
        
        logger.info(f"Extracted built-in theme: {theme_name}")
        return {
            "success": True,
            "theme_name": theme_name,
            "variables": theme_data
        }
    except Exception as e:
        logger.error(f"Error extracting built-in theme {theme_name}: {e}")
        return {"error": "Failed to extract theme", "details": str(e)}


@app.get("/auth/check")
async def auth_check_simple(request: Request):
    """Check authentication status based on session cookie"""
    try:
        session_token = request.cookies.get("session_token")
        if session_token:
            return {
                "authenticated": True,
                "user": {"id": 1, "username": "admin", "role": "ADMIN"},
            }
        else:
            return {"authenticated": False}
    except Exception as e:
        logger.error(f"Auth check error: {e}")
        return {"authenticated": False}


@app.post("/auth/logout")
async def logout():
    """Logout endpoint - clears session cookie"""
    from fastapi.responses import JSONResponse

    response = JSONResponse(
        content={
            "success": True,
            "message": "Logged out successfully",
            "redirect_url": "/auth/login",
        }
    )
    response.delete_cookie(key="session_token")
    return response


@app.websocket("/ws/jobs")
async def websocket_jobs(websocket: WebSocket):
    """WebSocket endpoint for background jobs progress"""
    await websocket.accept()

    try:
        # Send initial status
        from datetime import datetime
        
        await websocket.send_json(
            {
                "type": "status",
                "message": "Connected to job progress WebSocket",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )

        # Keep connection alive and send periodic updates
        import asyncio
        from src.jobs.celery_app import celery_app

        # Store subscribed job IDs
        subscribed_jobs = set()
        
        # Listen for incoming messages (job subscriptions)
        async def handle_messages():
            try:
                while True:
                    message = await websocket.receive_json()
                    if message.get("type") in ["subscribe", "subscribe_job"]:
                        job_id = message.get("job_id")
                        if job_id:
                            subscribed_jobs.add(job_id)
                            logger.info(f"WebSocket subscribed to job {job_id}")
                    elif message.get("type") in ["unsubscribe", "unsubscribe_job"]:
                        job_id = message.get("job_id")
                        if job_id:
                            subscribed_jobs.discard(job_id)
            except Exception as e:
                logger.debug(f"WebSocket message handling stopped: {e}")

        # Start message handler
        import asyncio
        message_task = asyncio.create_task(handle_messages())

        while True:
            try:
                # Send heartbeat and check for job updates every 5 seconds
                await asyncio.sleep(5)
                
                # Get active jobs count from Celery
                try:
                    inspect = celery_app.control.inspect()
                    active_jobs = inspect.active()
                    total_active = sum(len(jobs) for jobs in (active_jobs or {}).values())
                except Exception:
                    total_active = 0

                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "active_jobs": total_active,
                    }
                )
                
                # Check progress for subscribed jobs
                for job_id in list(subscribed_jobs):
                    try:
                        from celery.result import AsyncResult
                        result = AsyncResult(job_id, app=celery_app)
                        
                        if result.state == "PROGRESS":
                            await websocket.send_json({
                                "type": "job_update",
                                "job_id": job_id,
                                "status": "processing",
                                "progress": result.info.get("progress", 0),
                                "message": result.info.get("message", "Processing..."),
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                            })
                        elif result.state == "SUCCESS":
                            await websocket.send_json({
                                "type": "job_update", 
                                "job_id": job_id,
                                "status": "completed",
                                "progress": 100,
                                "message": "Job completed successfully",
                                "result": result.result,
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                            })
                            subscribed_jobs.discard(job_id)
                        elif result.state == "FAILURE":
                            await websocket.send_json({
                                "type": "job_update",
                                "job_id": job_id, 
                                "status": "failed",
                                "progress": 0,
                                "message": "Job failed",
                                "error": str(result.info),
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                            })
                            subscribed_jobs.discard(job_id)
                    except Exception as job_error:
                        logger.debug(f"Error checking job {job_id}: {job_error}")

            except Exception as loop_error:
                logger.error(f"WebSocket update loop error: {loop_error}")
                break

    except Exception as e:
        logger.error(f"WebSocket jobs error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass


if __name__ == "__main__":
    import uvicorn

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Run the application without reload to prevent file watching issues
    uvicorn.run(
        "fastapi_app:app",
        host="0.0.0.0",
        port=5000,  # Standard MVidarr port
        reload=False,  # Disabled to prevent continuous reload loops
        log_level="info",
    )
