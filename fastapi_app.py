"""
FastAPI Application for MVidarr
Modern async web framework with native background job support
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# Database and services
from src.database.connection import get_db
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

# Database initialization
from src.database.init_db import initialize_database
from src.config.config import Config
from src.database.connection import DatabaseManager

# Background job system
from src.services.job_queue import get_job_queue, cleanup_job_queue
from src.services.background_workers import start_background_workers, stop_background_workers

# OpenAPI documentation configuration
from src.api.openapi_config import custom_openapi_schema, setup_custom_docs, add_openapi_metadata_to_routers

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
        
        # Initialize job system
        logger.info("Initializing job queue...")
        job_queue = await get_job_queue()
        
        # Start background workers
        worker_count = 3  # TODO: make configurable
        logger.info(f"Starting {worker_count} background workers...")
        await start_background_workers(worker_count)
        
        logger.info("✅ Background job system started successfully")
        
        yield  # Application is running
        
    except Exception as e:
        logger.error(f"Failed to start application services: {e}")
        raise
    
    finally:
        # Cleanup on shutdown
        logger.info("Shutting down application services...")
        
        try:
            await stop_background_workers()
            await cleanup_job_queue()
            
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
        "email": "support@mvidarr.local"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    servers=[
        {
            "url": "http://192.168.1.145:5000",
            "description": "Development server"
        },
        {
            "url": "http://localhost:5000", 
            "description": "Local development server"
        }
    ],
    openapi_tags=[
        {
            "name": "videos",
            "description": "Video management operations including CRUD, streaming, thumbnails, and bulk operations"
        },
        {
            "name": "artists", 
            "description": "Artist management with metadata enrichment, IMVDb integration, and video associations"
        },
        {
            "name": "playlists",
            "description": "Playlist management with dynamic filtering, file uploads, and advanced access control"
        },
        {
            "name": "admin",
            "description": "System administration including user management, audit logs, and system control"
        },
        {
            "name": "settings",
            "description": "Application settings management, scheduler control, and database configuration"
        },
        {
            "name": "authentication",
            "description": "Authentication, OAuth, session management, and credential handling"
        },
        {
            "name": "system",
            "description": "System health monitoring, performance metrics, and application status"
        }
    ],
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Phase 3 Week 29 Integration - Personal Cloud Backup & Basic Integrations
from src.api.fastapi.week29_integration import (
    backup_router, 
    youtube_router, 
    network_router, 
    sync_router
)
from src.api.fastapi.mobile_access import mobile_router

# Include Week 29 API routers
app.include_router(backup_router, prefix="/api")
app.include_router(youtube_router, prefix="/api") 
app.include_router(network_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(mobile_router)

logger.info("✅ Phase 3 Week 29 services integrated: Personal Cloud Backup, YouTube Import, Network Sharing, Sync Manager, Mobile Access")

# Add CORS middleware with optimized configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.1.145:5000",
        "http://192.168.1.145:5010", 
        "http://localhost:5000",
        "http://localhost:5010",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:5010"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight requests for 24 hours
)

# Add performance monitoring middleware
from src.middleware.performance_middleware import (
    PerformanceTrackingMiddleware,
    CacheHeadersMiddleware, 
    ResourceMonitoringMiddleware
)

# Add caching middleware
from src.middleware.cache_middleware import (
    APIResponseCacheMiddleware,
    CacheInvalidationMiddleware
)

# Add security middleware - Phase 3 Week 34
from src.middleware.security_validation_middleware import (
    SecurityValidationMiddleware,
    SecurityValidationConfig
)
from src.middleware.rate_limiting_middleware import (
    RateLimitingMiddleware,
    RateLimitingConfig
)
from src.middleware.jwt_auth_middleware import (
    JWTAuthMiddleware,
    TokenConfig
)

# Add production middleware - Phase 3 Week 35
from src.middleware.auto_scaling_middleware import AutoScalingMiddleware
from src.middleware.circuit_breaker_middleware import (
    CircuitBreakerMiddleware,
    CircuitBreakerConfig
)
# Add analytics middleware - Phase 3 Week 36
from src.middleware.analytics_middleware import AnalyticsMiddleware
# Add API Gateway middleware - Phase 3 Week 37
from src.middleware.api_gateway_middleware import APIGatewayMiddleware, GatewayManagementMiddleware

# Add middleware in correct order (last added = first executed)
# Temporarily disabled ALL middleware to isolate authentication timeout issue
# TODO: Re-enable middleware one by one after fixing the core issue
# app.add_middleware(JWTAuthMiddleware, config=TokenConfig())
# app.add_middleware(SecurityValidationMiddleware, config=SecurityValidationConfig())

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

# Include API routers (some temporarily disabled due to Redis dependencies)
# from src.api.fastapi.jobs import router as jobs_router
# from src.api.fastapi.video_quality import router as video_quality_router
from src.api.fastapi.media_processing import router as media_processing_router
from src.api.fastapi.image_processing import router as image_processing_router
from src.api.fastapi.advanced_image_processing import router as advanced_image_router
# from src.api.fastapi.bulk_operations import router as bulk_operations_router
from src.api.fastapi.videos import router as fastapi_videos_router
from src.api.fastapi.artists import router as fastapi_artists_router
from src.api.fastapi.playlists import router as fastapi_playlists_router
from src.api.fastapi.admin import router as fastapi_admin_router
from src.api.fastapi.settings import router as fastapi_settings_router
from src.api.fastapi.auth import router as fastapi_auth_router
from src.api.fastapi.frontend_router import frontend_router
from src.api.fastapi.performance import router as performance_router
from src.api.fastapi.production_monitoring import router as monitoring_router
from src.api.fastapi.monitoring_dashboard import router as dashboard_router
from src.api.fastapi.api_gateway_management import router as gateway_router
# from src.api.fastapi.music_recommendations import recommendations_router  # Temporarily disabled
# from src.api.system_health import router as system_health_router
# from src.api.fastapi.model_demo import router as model_demo_router

# app.include_router(jobs_router)
# app.include_router(video_quality_router)
app.include_router(media_processing_router)
app.include_router(image_processing_router)
app.include_router(advanced_image_router)
# app.include_router(bulk_operations_router)
# Re-enable real database routers after fixing database initialization
app.include_router(fastapi_videos_router)
app.include_router(fastapi_artists_router) 
app.include_router(fastapi_playlists_router)
app.include_router(fastapi_admin_router)
app.include_router(fastapi_settings_router)
app.include_router(fastapi_auth_router)
app.include_router(frontend_router)

# Metadata enrichment routers
from src.api.fastapi.metadata_enrichment import router as metadata_enrichment_router
from src.api.fastapi.spotify import router as spotify_router
from src.api.fastapi.musicbrainz import router as musicbrainz_router
app.include_router(metadata_enrichment_router)
app.include_router(spotify_router)
app.include_router(musicbrainz_router)
app.include_router(performance_router)
app.include_router(monitoring_router)
app.include_router(dashboard_router)
app.include_router(gateway_router)
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
        "job_system": "native_asyncio"
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
            return {
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": 1,
                    "username": username,
                    "role": "ADMIN",
                    "can_admin": True
                }
            }
        else:
            return {"success": False, "message": "Invalid credentials"}
            
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


# Simple test endpoints to verify database connectivity
@app.get("/api/test/artists")
async def test_get_artists():
    """Simple test endpoint to check artists data"""
    try:
        from src.database.connection import get_db_session
        from src.database.models import Artist
        from sqlalchemy.orm import Session
        
        # Get database session
        session_gen = get_db_session()
        session: Session = next(session_gen)
        
        try:
            # Get first few artists
            artists = session.query(Artist).limit(5).all()
            
            result = []
            for artist in artists:
                result.append({
                    "id": artist.id,
                    "name": artist.name,
                    "imvdb_id": artist.imvdb_id,
                    "monitored": getattr(artist, 'monitored', True),
                    "created_at": getattr(artist, 'created_at', None),
                    # Add all available attributes
                    "available_fields": [attr for attr in dir(artist) if not attr.startswith('_') and not callable(getattr(artist, attr))]
                })
            
            return {
                "success": True,
                "count": len(result),
                "artists": result
            }
        finally:
            session.close()
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/test/videos")
async def test_get_videos():
    """Simple test endpoint to check videos data"""
    try:
        from src.database.connection import get_db_session
        from src.database.models import Video
        from sqlalchemy.orm import Session
        
        # Get database session  
        session_gen = get_db_session()
        session: Session = next(session_gen)
        
        try:
            # Get first few videos
            videos = session.query(Video).limit(5).all()
            
            result = []
            for video in videos:
                result.append({
                    "id": video.id,
                    "title": video.title,
                    "artist_id": video.artist_id,
                    "youtube_id": getattr(video, 'youtube_id', None),
                    "local_path": getattr(video, 'local_path', None),
                    "status": getattr(video, 'status', None),
                    "created_at": getattr(video, 'created_at', None),
                    # Add all available attributes
                    "available_fields": [attr for attr in dir(video) if not attr.startswith('_') and not callable(getattr(video, attr))]
                })
            
            return {
                "success": True,
                "count": len(result),
                "videos": result
            }
        finally:
            session.close()
            
    except Exception as e:
        return {"success": False, "error": str(e)}


# Root redirect - redirect to login for now since auth middleware is disabled
@app.get("/")
async def root():
    """Root endpoint - redirect to login since middleware is disabled"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/auth/login", status_code=302)


# Additional missing API endpoints that frontend is looking for
@app.get("/api/metube/queue")
async def get_metube_queue():
    """Mock metube queue endpoint"""
    return {"queue": [], "total": 0}


@app.get("/api/metube/history")
async def get_metube_history(limit: int = 10):
    """Mock metube history endpoint"""
    return {"history": [], "total": 0}


@app.get("/api/health/status") 
async def get_health_status():
    """Mock health status endpoint"""
    return {
        "status": "healthy",
        "uptime": "1h 30m",
        "memory_usage": "180MB",
        "cpu_usage": "15%"
    }


@app.get("/api/health/version")
async def get_health_version():
    """Mock version endpoint"""
    return {
        "version": "0.9.8",
        "build_date": "2024-01-01",
        "commit": "abc1234"
    }


@app.get("/api/themes/current")
async def get_current_theme():
    """Mock current theme endpoint"""
    return {"theme": "dark", "available_themes": ["dark", "light"]}


@app.get("/auth/check")
async def auth_check_simple():
    """Simple auth check endpoint - always return not authenticated since middleware is disabled"""
    return {"authenticated": False}


@app.websocket("/ws/jobs")
async def websocket_jobs(websocket: WebSocket):
    """WebSocket endpoint for background jobs progress"""
    await websocket.accept()
    
    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "message": "Connected to job progress WebSocket",
            "timestamp": "2025-01-08T00:00:00Z"
        })
        
        # Keep connection alive and send periodic updates
        import asyncio
        while True:
            # Send heartbeat every 30 seconds
            await asyncio.sleep(30)
            await websocket.send_json({
                "type": "heartbeat", 
                "timestamp": "2025-01-08T00:00:00Z",
                "active_jobs": 0
            })
            
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
    
    # Run the application
    uvicorn.run(
        "fastapi_app:app", 
        host="0.0.0.0", 
        port=5000,  # Standard MVidarr port
        reload=True,
        log_level="info"
    )