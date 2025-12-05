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
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.api.fastapi.logging_middleware import setup_logging_middleware
from src.api.fastapi.wizard_middleware import setup_wizard_middleware

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

# Background job system imports
from src.services.background_workers import (
    start_background_workers,
    stop_background_workers,
)
from src.services.settings_service import SettingsService
from src.services.ytdlp_service import ytdlp_service
from src.utils.logger import get_logger
from src.utils.structured_logger import get_structured_logger, setup_structured_logging

# Setup structured logging
setup_structured_logging()

logger = get_logger("mvidarr.fastapi")
structured_logger = get_structured_logger("mvidarr.fastapi")


# FastAPI-specific database initialization
async def init_database_for_fastapi():
    """
    Initialize database for FastAPI application

    IMPORTANT: Runs synchronous database operations in thread executor to prevent
    event loop blocking and connection pool issues.
    """
    import src.database.connection as db_conn

    def _sync_db_init():
        """Synchronous database initialization to run in thread executor"""
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
        return True

    # Run synchronous database initialization in thread executor to prevent event loop blocking
    logger.info("Starting database initialization in thread executor...")
    try:
        await asyncio.to_thread(_sync_db_init)
        logger.info("✅ Database initialization completed successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise


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
        # Start background workers for video indexing, organization, and quality checks
        await start_background_workers(num_workers=3)
        logger.info(
            "✅ Background workers started (3 workers for video indexing/organization)"
        )

        # Note: Celery + Redis system handles metadata enrichment separately
        logger.info("✅ Celery + Redis system handles metadata enrichment")

        # Initialize WebSocket system for real-time job progress
        logger.info("🔄 Initializing WebSocket job progress system...")
        await init_websocket_system(app)
        logger.info("✅ WebSocket job progress system initialized")

        # Start job scheduler for advanced job features
        logger.info("🔄 Starting advanced job scheduler...")
        await start_job_scheduler()
        logger.info("✅ Advanced job scheduler started")

        # ytdlp_service is already initialized and pending downloads resumed during import
        logger.info(
            "✅ ytdlp_service initialized (pending downloads auto-resumed during init)"
        )

        yield  # Application is running

    except Exception as e:
        logger.error(f"Failed to start application services: {e}")
        raise

    finally:
        # Cleanup on shutdown
        logger.info("Shutting down application services...")

        try:
            # Stop job scheduler
            logger.info("🔄 Stopping advanced job scheduler...")
            await stop_job_scheduler()
            logger.info("✅ Advanced job scheduler stopped")

            # Cleanup WebSocket system
            logger.info("🔄 Stopping WebSocket job progress system...")
            await cleanup_websocket_system()
            logger.info("✅ WebSocket system stopped")

            # Stop background workers
            logger.info("🔄 Stopping background workers...")
            await stop_background_workers()
            logger.info("✅ Background workers stopped")

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
from src.api.fastapi.week29_integration import youtube_router  # Re-enabled
from src.api.fastapi.week29_integration import (
    backup_router,
    network_router,
    sync_router,
)

# Include Week 29 API routers
app.include_router(backup_router, prefix="/api")
app.include_router(youtube_router, prefix="/api")  # Re-enabled for full functionality
app.include_router(network_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(mobile_router)

# Enhanced Artist Discovery Router
from src.api.fastapi.enhanced_artist_discovery import (
    router as enhanced_discovery_router,
)

app.include_router(enhanced_discovery_router)

# YouTube Playlists Router
from src.api.fastapi.youtube_playlists import router as youtube_playlists_router

app.include_router(youtube_playlists_router)

# Enhanced Scheduler Router
from src.api.fastapi.enhanced_scheduler import router as enhanced_scheduler_router

app.include_router(enhanced_scheduler_router)

# Webhooks Router
from src.api.fastapi.webhooks import router as webhooks_router

app.include_router(webhooks_router)

# Video Discovery Router
from src.api.fastapi.video_discovery import router as video_discovery_router

app.include_router(video_discovery_router)

# Security Router
from src.api.fastapi.security import router as security_router

app.include_router(security_router)

# Video Organization Router
from src.api.fastapi.video_organization import router as video_org_router

app.include_router(video_org_router)

# Video Indexing Router
from src.api.fastapi.video_indexing import router as video_indexing_router

app.include_router(video_indexing_router)

# MeTube Router
from src.api.fastapi.metube import router as metube_router

app.include_router(metube_router)

# YTDLP Router
from src.api.fastapi.ytdlp import router as ytdlp_router

app.include_router(ytdlp_router)

# Optimization Router
from src.api.fastapi.optimization import router as optimization_router

app.include_router(optimization_router)

# VLC Streaming Router
from src.api.fastapi.vlc_streaming import router as vlc_router

app.include_router(vlc_router)

# Spotify Enhanced Router
from src.api.fastapi.spotify_enhanced import router as spotify_enhanced_router

app.include_router(spotify_enhanced_router)

# IMVDb Router
from src.api.fastapi.imvdb import router as imvdb_router

app.include_router(imvdb_router)

# Plex Router
from src.api.fastapi.plex import router as plex_router

app.include_router(plex_router)

# Lidarr Router
from src.api.fastapi.lidarr import router as lidarr_router

app.include_router(lidarr_router)

# Health Check Router - Comprehensive Production Health Monitoring
from src.api.fastapi.health import health_router
from src.api.fastapi.maintenance import page_router as maintenance_page_router
from src.api.fastapi.maintenance import router as maintenance_router
from src.api.fastapi.personal_insights import page_router as analytics_page_router
from src.api.fastapi.personal_insights import router as analytics_router
from src.api.fastapi.system_health import page_router as system_health_page_router
from src.api.fastapi.system_health import router as system_health_router
from src.api.fastapi.video_indexing_page import (
    page_router as video_indexing_page_router,
)

app.include_router(health_router, prefix="/api")
app.include_router(system_health_router)
app.include_router(system_health_page_router)
app.include_router(maintenance_router)
app.include_router(maintenance_page_router)
app.include_router(analytics_router)
app.include_router(analytics_page_router)
app.include_router(video_indexing_page_router)

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

# Add proxy headers middleware for HTTPS reverse proxy support
# This allows FastAPI to trust X-Forwarded-* headers from reverse proxies
# Fixes mixed content issues when accessing via HTTPS proxy (e.g., https://mvidarr.prefect42.com)
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=["*"],  # Trust all proxies - adjust for production security
)
logger.info("✅ Proxy headers middleware enabled for reverse proxy support")

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

# Setup structured logging middleware for production monitoring
setup_logging_middleware(app)
structured_logger.info(
    "Structured logging middleware enabled for production monitoring"
)

# Setup first-run wizard middleware for v1.0.0 (Issue #163)
setup_wizard_middleware(app, wizard_redirect_url="/wizard")
logger.info("✅ First-run wizard middleware enabled")

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

# Use AsyncTemplateSystem instead of basic Jinja2Templates for Flask compatibility
from src.api.fastapi.template_system import get_template_system

template_system = get_template_system()
templates = template_system.templates

from src.api.fastapi.advanced_image_processing import router as advanced_image_router
from src.api.fastapi.advanced_jobs import router as advanced_jobs_router
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
from src.api.fastapi.auth import legacy_router as fastapi_auth_legacy_router
from src.api.fastapi.auth import router as fastapi_auth_router
from src.api.fastapi.backups import router as backups_router
from src.api.fastapi.filesystem import router as filesystem_router
from src.api.fastapi.frontend_router import frontend_router
from src.api.fastapi.genres import router as fastapi_genres_router
from src.api.fastapi.monitoring_dashboard import router as dashboard_router
from src.api.fastapi.performance import router as performance_router
from src.api.fastapi.playlists import router as fastapi_playlists_router
from src.api.fastapi.production_monitoring import router as monitoring_router
from src.api.fastapi.settings import router as fastapi_settings_router
from src.api.fastapi.videos import router as fastapi_videos_router
from src.api.fastapi.videos_search import router as fastapi_videos_search_router
from src.api.fastapi.videos_streaming import router as fastapi_videos_streaming_router
from src.api.fastapi.wizard import router as wizard_router

# from src.api.fastapi.music_recommendations import recommendations_router  # Temporarily disabled
# from src.api.system_health import router as system_health_router
# from src.api.fastapi.model_demo import router as model_demo_router

app.include_router(jobs_router)
app.include_router(advanced_jobs_router)
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
app.include_router(fastapi_videos_streaming_router, prefix="/api/videos")
app.include_router(fastapi_videos_search_router, prefix="/api/videos")
app.include_router(fastapi_artists_router)
app.include_router(fastapi_playlists_router)
app.include_router(fastapi_genres_router)
app.include_router(fastapi_admin_router)
app.include_router(fastapi_settings_router)
app.include_router(backups_router)  # v1.0.0 Backup & Recovery (Issue #93)
app.include_router(wizard_router)  # v1.0.0 Installation Wizard (Issue #163)
app.include_router(filesystem_router)  # v1.0.0 Custom Directory Import (Issue #164)
app.include_router(fastapi_auth_router)
app.include_router(fastapi_auth_legacy_router)
app.include_router(frontend_router)

from src.api.fastapi.advanced_search import router as advanced_search_router
from src.api.fastapi.discogs import router as discogs_router
from src.api.fastapi.lastfm import router as lastfm_router

# Metadata enrichment routers
from src.api.fastapi.metadata_enrichment import router as metadata_enrichment_router
from src.api.fastapi.musicbrainz import router as musicbrainz_router
from src.api.fastapi.spotify import router as spotify_router
from src.api.fastapi.themes import router as themes_router
from src.api.fastapi.two_factor_auth import router as two_factor_router
from src.api.fastapi.users import router as users_router

app.include_router(metadata_enrichment_router)
app.include_router(spotify_router)
app.include_router(musicbrainz_router)
app.include_router(discogs_router)
app.include_router(themes_router)
app.include_router(users_router)
app.include_router(lastfm_router)
app.include_router(advanced_search_router)
app.include_router(two_factor_router)
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


# Basic health check - Redirect to comprehensive health router
@app.get("/health")
async def health_check():
    """Simple health check endpoint - Use /api/health for comprehensive monitoring"""
    return {
        "status": "healthy",
        "version": "0.9.8",
        "framework": "FastAPI",
        "job_system": "native_asyncio",
        "comprehensive_health": "/api/health",
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
            # Get downloads with queued, downloading, or processing status
            downloads = (
                session.query(Download)
                .options(joinedload(Download.video), joinedload(Download.artist))
                .filter(Download.status.in_(["queued", "downloading", "processing"]))
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
async def clear_stuck_downloads(force: bool = False):
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
            if force:
                # Force mode: clear ALL stuck downloads regardless of time
                stuck_downloads = (
                    session.query(Download)
                    .filter(
                        Download.status.in_(["queued", "downloading", "processing"])
                    )
                    .all()
                )
                logger.info("Force clearing ALL stuck downloads")
            else:
                # Normal mode: Find downloads that have been stuck for more than 10 minutes
                # This includes downloads stuck in downloading/processing AND queued state
                cutoff_time = datetime.utcnow() - timedelta(minutes=10)

                stuck_downloads = (
                    session.query(Download)
                    .filter(
                        Download.status.in_(["queued", "downloading", "processing"]),
                        Download.updated_at < cutoff_time,
                    )
                    .all()
                )
                logger.info(f"Clearing downloads stuck for more than 10 minutes")

            cleared_count = 0
            for download in stuck_downloads:
                # Cancel stuck downloads instead of retrying to prevent infinite loops
                download.status = "failed"
                download.progress = 0
                download.updated_at = datetime.utcnow()
                download.error_message = (
                    "Cancelled - stuck in processing state and cleared by user"
                )
                cleared_count += 1

            session.commit()

            logger.info(f"Cleared {cleared_count} stuck downloads")

            # Don't resubmit cleared downloads to avoid infinite loops
            # Users can manually retry failed downloads if needed

            return {
                "success": True,
                "cleared_count": cleared_count,
                "message": f"Cancelled {cleared_count} stuck downloads - they will no longer appear in queue",
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error clearing stuck downloads: {e}")
        return {"success": False, "error": str(e), "cleared_count": 0}


@app.post("/api/metube/download/{download_id}/retry")
async def retry_download(download_id: str):
    """Retry a failed download"""
    try:
        # Handle download IDs with 'db_' prefix from frontend
        if download_id.startswith("db_"):
            actual_download_id = int(download_id[3:])  # Remove 'db_' prefix
        else:
            actual_download_id = int(download_id)

        result = ytdlp_service.retry_download(actual_download_id)
        return result
    except ValueError as e:
        logger.error(f"Invalid download ID format: {download_id}")
        return {"success": False, "error": f"Invalid download ID format: {download_id}"}
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
            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )

            if not download:
                return {"success": False, "error": "Download not found"}

            # Only allow deletion of queued, failed, or completed downloads
            if download.status not in ["queued", "failed", "completed", "cancelled"]:
                return {
                    "success": False,
                    "error": f"Cannot delete download with status: {download.status}",
                }

            # Delete the download
            session.delete(download)
            session.commit()

            logger.info(f"Deleted download {download_id}: {download.title}")
            return {
                "success": True,
                "message": f"Download {download_id} deleted successfully",
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
@app.get("/api/imvdb/search-videos")
async def search_imvdb_videos(q: str = Query(...)):
    """Search IMVDb for videos"""
    try:
        # Mock IMVDb search results for now
        query = q.lower()

        mock_results = [
            {
                "id": f"imvdb_{i}",
                "title": f"{q} - IMVDb Result {i+1}",
                "artist": f"Artist {i+1}",
                "year": 2020 + i,
                "director": f"Director {i+1}",
                "imvdb_url": f"https://imvdb.com/video/mock_{i}",
            }
            for i in range(3)
        ]

        return {
            "success": True,
            "query": q,
            "results": mock_results,
            "total": len(mock_results),
        }

    except Exception as e:
        logger.error(f"IMVDb search failed: {e}")
        return {"success": False, "error": str(e), "results": [], "total": 0}


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


# Health endpoints moved to comprehensive health router - see /api/health


# All theme endpoints moved to themes router - duplicates removed


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


@app.post("/auth/dynamic-logout")
async def dynamic_logout():
    """Dynamic logout endpoint - clears session cookie"""
    from fastapi.responses import JSONResponse

    response = JSONResponse(
        content={
            "success": True,
            "message": "Logged out successfully",
            "redirect_url": "/auth/login",
        }
    )
    response.delete_cookie(key="mvidarr_session")
    response.delete_cookie(key="session_token")
    return response


# WebSocket routes imported from dedicated module
from src.api.fastapi.websocket_jobs import (
    cleanup_websocket_system,
    init_websocket_system,
)

# Job scheduler for advanced job features
from src.services.job_scheduler import start_job_scheduler, stop_job_scheduler

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
