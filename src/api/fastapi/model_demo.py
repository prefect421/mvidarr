"""
Model Demo FastAPI Router - Phase 3 Week 32
Demonstrates the new centralized Pydantic model system
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

# Import centralized models - temporarily disabled for startup
# from src.api.models import (
#     VideoCreateRequest,
#     VideoResponse,
#     ArtistCreateRequest,
#     ArtistResponse,
#     PlaylistCreateRequest,
#     PlaylistResponse,
#     LoginRequest,
#     LoginResponse,
#     SettingUpdateRequest,
#     SettingResponse,
#     JobRequest,
#     JobResponse,
#     HealthResponse,
#     ContentAnalysisRequest,
#     ContentAnalysisResponse
# )
# from src.api.models.validation import ModelValidator, ModelTester

router = APIRouter(
    prefix="/api/demo/models",
    tags=["model-demo"],
    responses={
        404: {"description": "Demo endpoint not found"},
        422: {"description": "Validation error in demo"}
    }
)

@router.get("/", response_model=Dict[str, Any])
async def model_system_overview():
    """Overview of the centralized Pydantic model system"""
    return {
        "message": "MVidarr Centralized Pydantic Model System",
        "phase": "Phase 3 Week 32 Complete",
        "total_models": "100+",
        "categories": [
            "Video Management",
            "Artist Management", 
            "Playlist Management",
            "Authentication & Authorization",
            "System Administration",
            "Settings Management",
            "Background Jobs",
            "Media Processing",
            "AI Services",
            "Health Monitoring"
        ],
        "features": [
            "Type-safe request/response validation",
            "Advanced business logic validators",
            "Model inheritance and composition",
            "Comprehensive field documentation",
            "Built-in testing utilities",
            "Consistent validation patterns",
            "Enterprise-grade data validation"
        ],
        "examples": {
            "video_creation": "/api/demo/models/video/create",
            "artist_management": "/api/demo/models/artist/create", 
            "validation_testing": "/api/demo/models/validate",
            "model_documentation": "/api/demo/models/docs"
        }
    }

@router.post("/video/create", response_model=VideoResponse)
async def demo_video_creation(video_data: VideoCreateRequest):
    """Demo endpoint showing centralized video model validation"""
    # This demonstrates the centralized VideoCreateRequest model
    # with all its validation rules and business logic
    return VideoResponse(
        id=123,
        title=video_data.title,
        artist_id=video_data.artist_id,
        artist_name="Demo Artist",
        url=video_data.url,
        youtube_url=video_data.youtube_url,
        status=video_data.status,
        genres=video_data.genres or [],
        thumbnail_url="/api/videos/123/thumbnail"
    )

@router.post("/artist/create", response_model=ArtistResponse)
async def demo_artist_creation(artist_data: ArtistCreateRequest):
    """Demo endpoint showing centralized artist model validation"""
    return ArtistResponse(
        id=456,
        name=artist_data.name,
        bio=artist_data.bio,
        website=artist_data.website,
        imvdb_url=artist_data.imvdb_url,
        spotify_url=artist_data.spotify_url,
        youtube_channel=artist_data.youtube_channel,
        twitter_handle=artist_data.twitter_handle,
        instagram_handle=artist_data.instagram_handle,
        video_count=0,
        thumbnail_url="/api/artists/456/thumbnail"
    )

@router.post("/playlist/create", response_model=PlaylistResponse)
async def demo_playlist_creation(playlist_data: PlaylistCreateRequest):
    """Demo endpoint showing centralized playlist model validation"""
    return PlaylistResponse(
        id=789,
        name=playlist_data.name,
        description=playlist_data.description,
        playlist_type=playlist_data.playlist_type,
        privacy=playlist_data.privacy,
        sort_order=playlist_data.sort_order,
        created_by_user_id=1,
        created_by_username="demo_user",
        video_count=0,
        filters=playlist_data.filters,
        auto_update=playlist_data.auto_update,
        max_videos=playlist_data.max_videos
    )

@router.post("/auth/login", response_model=LoginResponse)
async def demo_login(login_data: LoginRequest):
    """Demo endpoint showing centralized auth model validation"""
    # This would normally authenticate against a real system
    return LoginResponse(
        user_id=1,
        username=login_data.username,
        role="USER",
        session_id="demo_session_123",
        expires_at="2024-12-31T23:59:59Z",
        permissions=["videos:read", "videos:download"]
    )

@router.post("/job/submit", response_model=JobResponse)
async def demo_job_submission(job_data: JobRequest):
    """Demo endpoint showing centralized job model validation"""
    return JobResponse(
        id="job_demo_123",
        job_type=job_data.job_type,
        status="PENDING",
        priority=job_data.priority,
        submitted_by=1,
        submitted_by_username="demo_user",
        scheduled_for=job_data.scheduled_for,
        parameters=job_data.parameters,
        retry_count=0,
        max_retries=job_data.retry_count
    )

@router.post("/validate")
async def demo_model_validation(request: Dict[str, Any]):
    """Demo endpoint for testing model validation"""
    model_name = request.get("model")
    test_data = request.get("data", {})
    
    # Map of available models for testing
    model_classes = {
        "video_create": VideoCreateRequest,
        "artist_create": ArtistCreateRequest,
        "playlist_create": PlaylistCreateRequest,
        "login": LoginRequest,
        "setting_update": SettingUpdateRequest,
        "job": JobRequest,
        "content_analysis": ContentAnalysisRequest
    }
    
    if model_name not in model_classes:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{model_name}'. Available models: {list(model_classes.keys())}"
        )
    
    model_class = model_classes[model_name]
    validation_result = ModelValidator.validate_model(model_class, test_data)
    
    return {
        "model_tested": model_name,
        "validation_result": validation_result,
        "example_data": ModelValidator.generate_example_data(model_class)
    }

@router.get("/docs")
async def model_documentation():
    """Generate documentation for all centralized models"""
    from src.api.models.validation import ModelDocumenter
    
    model_classes = [
        VideoCreateRequest, VideoResponse,
        ArtistCreateRequest, ArtistResponse,
        PlaylistCreateRequest, PlaylistResponse,
        LoginRequest, LoginResponse,
        SettingUpdateRequest, SettingResponse,
        JobRequest, JobResponse,
        HealthResponse
    ]
    
    docs = {}
    for model_class in model_classes:
        docs[model_class.__name__] = ModelDocumenter.generate_model_docs(model_class)
    
    return {
        "message": "Centralized Model Documentation",
        "total_models_documented": len(docs),
        "model_documentation": docs
    }

@router.get("/test/comprehensive")
async def run_comprehensive_tests():
    """Run comprehensive validation tests on centralized models"""
    tester = ModelTester()
    results = tester.run_comprehensive_tests()
    
    return {
        "message": "Comprehensive Model Validation Tests",
        "test_results": results
    }

@router.get("/health", response_model=HealthResponse)
async def demo_health_check():
    """Demo health check using centralized health model"""
    return HealthResponse(
        status="healthy",
        version="0.9.8",
        uptime=86400.0,
        database_connected=True,
        redis_connected=True,
        jobs_running=True,
        active_connections=5,
        pending_jobs=3,
        memory_usage_mb=256.7
    )

@router.get("/examples")
async def model_examples():
    """Show examples of all major model types"""
    return {
        "video_create_example": ModelValidator.generate_example_data(VideoCreateRequest),
        "artist_create_example": ModelValidator.generate_example_data(ArtistCreateRequest),
        "playlist_create_example": ModelValidator.generate_example_data(PlaylistCreateRequest),
        "login_example": ModelValidator.generate_example_data(LoginRequest),
        "job_example": ModelValidator.generate_example_data(JobRequest),
        "content_analysis_example": ModelValidator.generate_example_data(ContentAnalysisRequest)
    }