"""
FastAPI Installation Wizard Router
v1.0.0 Feature: First-run setup wizard for guided configuration
Issue #163: https://github.com/prefect421/mvidarr/issues/163
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.database.models import WizardState, WizardStatus, WizardStep
from src.services.imvdb_service import imvdb_service

# Note: Wizard now uses Celery for video indexing instead of custom JobQueue
# No need to import job_queue here anymore

logger = logging.getLogger("mvidarr.fastapi.wizard")

router = APIRouter(
    prefix="/api/wizard",
    tags=["wizard"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class WizardStateResponse(BaseModel):
    """Wizard state response"""

    id: int
    status: str
    current_step: str
    completion_percentage: int
    steps: Dict[str, bool]
    config_data: Dict[str, Any]
    import_job_id: Optional[str] = None
    videos_imported: int
    import_errors: list
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    last_step_at: Optional[str] = None

    class Config:
        from_attributes = True


class StartWizardRequest(BaseModel):
    """Start wizard request"""

    pass  # No parameters needed for starting wizard


class CreateAdminRequest(BaseModel):
    """Create first admin user request"""

    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        """Basic email validation"""
        if "@" not in v or "." not in v:
            raise ValueError("Invalid email address")
        return v


class CreateAdminResponse(BaseModel):
    """Create admin user response"""

    success: bool
    message: str
    user_id: Optional[int] = None
    username: Optional[str] = None


class CompleteStepRequest(BaseModel):
    """Complete wizard step request"""

    config_data: Optional[Dict[str, Any]] = Field(
        None, description="Configuration data collected in this step"
    )


class DirectoryValidationRequest(BaseModel):
    """Directory validation request"""

    path: str = Field(..., min_length=1, description="Directory path to validate")


class DirectoryValidationResponse(BaseModel):
    """Directory validation response"""

    valid: bool
    exists: bool
    readable: bool
    writable: bool
    is_directory: bool
    video_count: Optional[int] = None
    error: Optional[str] = None


class APITestRequest(BaseModel):
    """API test request"""

    api_type: str = Field(..., description="API type to test (imvdb, youtube)")
    api_key: Optional[str] = Field(None, description="API key to test")
    cookies_content: Optional[str] = Field(None, description="YouTube cookies content")

    @field_validator("api_type")
    @classmethod
    def validate_api_type(cls, v):
        """Validate API type"""
        valid_types = ["imvdb", "youtube"]
        if v not in valid_types:
            raise ValueError(f"Invalid API type: {v}")
        return v


class APITestResponse(BaseModel):
    """API test response"""

    success: bool
    api_type: str
    message: str
    error: Optional[str] = None


class ImportStartRequest(BaseModel):
    """Start video import request"""

    directory: str = Field(..., description="Directory to import from")
    fetch_metadata: bool = Field(
        default=True, description="Whether to fetch metadata for videos"
    )
    process_artists: bool = Field(
        default=True,
        description="Whether to process artists after import (auto-matching, metadata enrichment)",
    )
    max_files: Optional[int] = Field(
        None, ge=1, description="Maximum files to import (None = all)"
    )


class ImportStartResponse(BaseModel):
    """Start video import response"""

    success: bool
    job_id: str
    artist_processing_job_id: Optional[str] = None
    message: str


# Note: JobStatusResponse removed - wizard now uses standard Celery job status
# via /api/jobs/{job_id} endpoint


# ========================================================================================
# WIZARD ENDPOINTS
# ========================================================================================


@router.get("/status", response_model=WizardStateResponse)
async def get_wizard_status(
    session: Session = Depends(get_db_session),
):
    """
    Get current wizard state.

    Returns the current state of the installation wizard, including:
    - Overall status (not_started, in_progress, completed, skipped)
    - Current step
    - Completion status of each step
    - Configuration data collected so far
    - Import progress if applicable

    Note: This endpoint does NOT require authentication since it's used
    during first-run setup before any users exist.
    """
    try:
        # Get or create wizard state (there should only be one)
        wizard_state = session.query(WizardState).first()

        if not wizard_state:
            # Create initial wizard state
            wizard_state = WizardState(
                status=WizardStatus.NOT_STARTED, current_step=WizardStep.WELCOME
            )
            session.add(wizard_state)
            session.commit()
            session.refresh(wizard_state)

        # Pre-populate config_data with environment variables (if not already set)
        config_data = wizard_state.config_data or {}

        # Pre-populate API keys from environment if not already configured
        if not config_data.get("apis"):
            config_data["apis"] = {}

        # IMVDB API key from environment (only if not already set by user)
        if not config_data["apis"].get("imvdb"):
            env_imvdb_key = os.getenv("IMVDB_API_KEY", "").strip()
            if env_imvdb_key:
                config_data["apis"]["imvdb"] = env_imvdb_key
                logger.info("Pre-populated IMVDB_API_KEY from environment")

        # YouTube API key from environment (only if not already set by user)
        if not config_data["apis"].get("youtube_api_key"):
            env_youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip()
            if env_youtube_key:
                config_data["apis"]["youtube_api_key"] = env_youtube_key
                logger.info("Pre-populated YOUTUBE_API_KEY from environment")

        # Return wizard state with pre-populated config_data
        wizard_dict = wizard_state.to_dict()
        wizard_dict["config_data"] = config_data
        return WizardStateResponse(**wizard_dict)

    except Exception as e:
        logger.error(f"Error getting wizard status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start", response_model=WizardStateResponse)
async def start_wizard(
    request: StartWizardRequest,
    session: Session = Depends(get_db_session),
):
    """
    Start the installation wizard.

    Initializes the wizard state and sets status to IN_PROGRESS.

    Note: This endpoint does NOT require authentication since it's used
    during first-run setup before any users exist.
    """
    try:
        # Get or create wizard state
        wizard_state = session.query(WizardState).first()

        if not wizard_state:
            wizard_state = WizardState()
            session.add(wizard_state)

        # Start wizard
        wizard_state.advance_to_step(WizardStep.WELCOME)
        wizard_state.mark_step_complete(WizardStep.WELCOME)

        session.commit()
        session.refresh(wizard_state)

        return WizardStateResponse(**wizard_state.to_dict())

    except Exception as e:
        logger.error(f"Error starting wizard: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-admin", response_model=CreateAdminResponse)
async def create_admin_user(
    request: CreateAdminRequest,
    session: Session = Depends(get_db_session),
):
    """
    Create the first admin user during wizard setup.

    This endpoint does NOT require authentication since it's used during
    first-run setup before any users exist. It should only be accessible
    when the wizard is in progress.
    """
    try:
        # Import here to avoid circular dependencies
        from src.database.models import User, UserRole
        from src.services.auth_service import AuthService

        # Check if wizard is in progress
        wizard_state = session.query(WizardState).first()
        if not wizard_state or wizard_state.status == WizardStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail="Cannot create admin user: wizard already completed",
            )

        # Check if admin user already exists
        existing_admin = session.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing_admin:
            raise HTTPException(status_code=400, detail="Admin user already exists")

        # Create admin user using AuthService
        success, message, user = AuthService.create_user(
            username=request.username,
            email=request.email,
            password=request.password,
            role=UserRole.ADMIN,
        )

        if success:
            # Create a fresh session to verify the user was created
            from src.database.connection import SessionLocal

            verification_session = SessionLocal()
            try:
                # Query the created user in a fresh session
                created_user = (
                    verification_session.query(User)
                    .filter(User.username == request.username)
                    .first()
                )

                if created_user:
                    user_id = created_user.id
                    username = created_user.username

                    logger.info(
                        f"✅ First admin user created during wizard: {username}"
                    )
                    return CreateAdminResponse(
                        success=True,
                        message=message,
                        user_id=user_id,
                        username=username,
                    )
                else:
                    logger.error(
                        f"User created but not found in database: {request.username}"
                    )
                    return CreateAdminResponse(
                        success=False,
                        message="User created but verification failed",
                    )
            finally:
                verification_session.close()
        else:
            logger.error(f"Failed to create admin user: {message}")
            return CreateAdminResponse(success=False, message=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Failed to create admin user: {str(e)}"
        )


@router.post("/steps/{step_id}/complete", response_model=WizardStateResponse)
async def complete_wizard_step(
    step_id: str,
    request: CompleteStepRequest,
    session: Session = Depends(get_db_session),
):
    """
    Mark a wizard step as complete and advance to next step.

    Updates the wizard state with:
    - Mark current step as completed
    - Store any configuration data collected
    - Advance to next step (or mark wizard complete if last step)

    Note: This endpoint does NOT require authentication since it's used
    during first-run setup before any users exist.
    """
    try:
        # Get wizard state
        wizard_state = session.query(WizardState).first()

        if not wizard_state:
            raise HTTPException(status_code=404, detail="Wizard state not found")

        # Validate step matches current step
        if wizard_state.current_step.value != step_id:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot complete step {step_id}. Current step is {wizard_state.current_step.value}",
            )

        # Update config data if provided
        if request.config_data:
            current_config = wizard_state.config_data or {}
            current_config.update(request.config_data)
            wizard_state.config_data = current_config

        # Mark step as complete
        wizard_state.mark_step_complete(WizardStep(step_id))

        # Advance to next step
        step_order = [
            WizardStep.WELCOME,
            WizardStep.ADMIN_ACCOUNT,
            WizardStep.DIRECTORIES,
            WizardStep.API_CONFIG,
            WizardStep.VIDEO_IMPORT,
            WizardStep.COMPLETE,
        ]
        current_index = step_order.index(WizardStep(step_id))
        if current_index < len(step_order) - 1:
            next_step = step_order[current_index + 1]
            wizard_state.advance_to_step(next_step)

        session.commit()
        session.refresh(wizard_state)

        return WizardStateResponse(**wizard_state.to_dict())

    except HTTPException:
        # Re-raise HTTP exceptions unchanged (validation errors, 404s, etc.)
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error completing wizard step: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skip", response_model=WizardStateResponse)
async def skip_wizard(
    session: Session = Depends(get_db_session),
):
    """
    Skip the installation wizard.

    Marks the wizard as skipped so it won't be shown again.

    Note: This endpoint does NOT require authentication since it's used
    during first-run setup before any users exist.
    """
    try:
        # Get or create wizard state
        wizard_state = session.query(WizardState).first()

        if not wizard_state:
            wizard_state = WizardState()
            session.add(wizard_state)

        # Mark as skipped
        wizard_state.status = WizardStatus.SKIPPED
        wizard_state.current_step = WizardStep.COMPLETE

        session.commit()
        session.refresh(wizard_state)

        return WizardStateResponse(**wizard_state.to_dict())

    except Exception as e:
        logger.error(f"Error skipping wizard: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-directory", response_model=DirectoryValidationResponse)
async def validate_directory(
    request: DirectoryValidationRequest,
    session: Session = Depends(get_db_session),
):
    """
    Validate a directory path for use as music videos directory.

    Checks:
    - Path exists
    - Is a directory (not a file)
    - Is readable
    - Is writable
    - Contains video files (optional count)

    Note: This endpoint does NOT require authentication since it's used
    during first-run setup before any users exist.
    """
    try:
        path = Path(request.path)

        # Check if path exists
        exists = path.exists()
        is_directory = path.is_dir() if exists else False
        readable = os.access(path, os.R_OK) if exists else False
        writable = os.access(path, os.W_OK) if exists else False

        # Count video files if directory is valid
        video_count = None
        if is_directory and readable:
            video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
            try:
                video_files = [
                    f
                    for f in path.rglob("*")
                    if f.is_file() and f.suffix.lower() in video_extensions
                ]
                video_count = len(video_files)
            except Exception as e:
                logger.warning(f"Error counting video files: {str(e)}")

        # Determine overall validity
        valid = exists and is_directory and readable and writable

        error = None
        if not exists:
            error = "Directory does not exist"
        elif not is_directory:
            error = "Path is not a directory"
        elif not readable:
            error = "Directory is not readable"
        elif not writable:
            error = "Directory is not writable"

        return DirectoryValidationResponse(
            valid=valid,
            exists=exists,
            readable=readable,
            writable=writable,
            is_directory=is_directory,
            video_count=video_count,
            error=error,
        )

    except Exception as e:
        logger.error(f"Error validating directory: {str(e)}")
        return DirectoryValidationResponse(
            valid=False,
            exists=False,
            readable=False,
            writable=False,
            is_directory=False,
            error=str(e),
        )


@router.post("/test-api", response_model=APITestResponse)
async def test_api(
    request: APITestRequest,
    session: Session = Depends(get_db_session),
):
    """
    Test API keys/credentials before saving.

    Tests connectivity and validity of:
    - IMVDb API key
    - YouTube cookies

    Note: This endpoint does NOT require authentication since it's used
    during first-run setup before any users exist.
    """
    try:
        if request.api_type == "imvdb":
            # Test IMVDb API key
            if not request.api_key:
                return APITestResponse(
                    success=False,
                    api_type="imvdb",
                    message="API key is required",
                    error="Missing API key",
                )

            # Test API key using the new test_api_key method
            # This tests the key directly without saving to settings first
            test_result = imvdb_service.test_api_key(request.api_key)
            return APITestResponse(
                success=test_result.get("success", False),
                api_type="imvdb",
                message=test_result.get("message", "API test completed"),
                error=test_result.get("error"),
            )

        elif request.api_type == "youtube":
            # Test YouTube cookies
            if not request.cookies_content:
                return APITestResponse(
                    success=False,
                    api_type="youtube",
                    message="YouTube cookies content is required",
                    error="Missing cookies",
                )

            # Basic validation of cookies format
            # TODO: Implement actual YouTube API test when needed
            if "youtube.com" in request.cookies_content.lower():
                return APITestResponse(
                    success=True,
                    api_type="youtube",
                    message="YouTube cookies format appears valid",
                )
            else:
                return APITestResponse(
                    success=False,
                    api_type="youtube",
                    message="Invalid YouTube cookies format",
                    error="Cookies do not appear to be for YouTube",
                )

        else:
            return APITestResponse(
                success=False,
                api_type=request.api_type,
                message=f"Unknown API type: {request.api_type}",
                error="Invalid API type",
            )

    except Exception as e:
        logger.error(f"Error testing API: {str(e)}")
        return APITestResponse(
            success=False,
            api_type=request.api_type,
            message="API test failed",
            error=str(e),
        )


@router.post("/import/start", response_model=ImportStartResponse)
async def start_video_import(
    request: ImportStartRequest,
    session: Session = Depends(get_db_session),
):
    """
    Start video import as part of wizard using Celery.

    Creates a Celery task chain to:
    1. Import videos from the specified directory (with skip_auto_processing=True)
    2. Run batch artist auto-processing after import completes (if enabled)

    Progress can be tracked via the standard /api/jobs/{job_id} endpoint.

    Note: This endpoint does NOT require authentication since it's used
    during first-run setup before any users exist.
    """
    try:
        # Validate directory exists
        directory = Path(request.directory)
        if not directory.exists() or not directory.is_dir():
            raise HTTPException(status_code=400, detail="Invalid directory path")

        # Import Celery tasks
        from src.jobs.wizard_tasks import index_videos_task, process_artists_batch_task

        artist_processing_job_id = None

        # If artist processing is enabled, use Celery's link to chain tasks
        if request.process_artists:
            logger.info("Chaining batch artist processing after video import")

            # Use Celery's link mechanism to run artist processing AFTER import succeeds
            # .si() creates an immutable signature (ignores parent result)
            import_task = index_videos_task.apply_async(
                kwargs={
                    "directory": str(directory),
                    "fetch_metadata": request.fetch_metadata,
                    "max_files": request.max_files,
                },
                priority=9,
                link=process_artists_batch_task.si(
                    artist_ids=None, force_refresh=False
                ),
            )

            job_id = import_task.id
            logger.info(
                f"Created chained tasks: video import ({job_id}) -> artist processing (will be created after import)"
            )
        else:
            # Just run video import without artist processing
            import_task = index_videos_task.apply_async(
                kwargs={
                    "directory": str(directory),
                    "fetch_metadata": request.fetch_metadata,
                    "max_files": request.max_files,
                },
                priority=9,
            )

            job_id = import_task.id
            logger.info(f"Created Celery task for wizard video import: {job_id}")

        # Update wizard state with job ID
        wizard_state = session.query(WizardState).first()
        if wizard_state:
            wizard_state.import_job_id = job_id
            session.commit()

        message = f"Video import job queued with ID: {job_id}"
        if request.process_artists:
            message += " (artist processing will run after import completes)"

        return ImportStartResponse(
            success=True,
            job_id=job_id,
            artist_processing_job_id=artist_processing_job_id,
            message=message,
        )

    except Exception as e:
        logger.error(f"Error starting video import: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Note: Job status for wizard imports is now handled by the standard
# /api/jobs/{job_id} endpoint which queries Celery backend.
# This eliminates the dual job system issue.


@router.post("/import/custom-directory/start", response_model=ImportStartResponse)
async def start_custom_directory_import(
    request: ImportStartRequest,
    session: Session = Depends(get_db_session),
):
    """
    Start custom directory import (Settings > System feature).

    This endpoint imports videos from any custom directory by:
    1. Copying video files to the music_videos_path (organized by artist/title)
    2. Indexing the copied files
    3. Optionally running batch artist auto-processing after import completes

    Progress can be tracked via the standard /api/jobs/{job_id} endpoint.

    Note: Unlike wizard import, this copies files from a custom source directory
    to the configured music videos directory.
    """
    try:
        # Validate directory exists
        directory = Path(request.directory)
        if not directory.exists() or not directory.is_dir():
            raise HTTPException(status_code=400, detail="Invalid directory path")

        # Import Celery tasks
        from src.jobs.wizard_tasks import (
            import_from_custom_directory_task,
            process_artists_batch_task,
        )

        artist_processing_job_id = None

        # If artist processing is enabled, use Celery's link to chain tasks
        if request.process_artists:
            logger.info(
                "Chaining batch artist processing after custom directory import"
            )

            # Use Celery's link mechanism to run artist processing AFTER import succeeds
            import_task = import_from_custom_directory_task.apply_async(
                kwargs={
                    "source_directory": str(directory),
                    "fetch_metadata": request.fetch_metadata,
                    "max_files": request.max_files,
                },
                priority=9,
                link=process_artists_batch_task.si(
                    artist_ids=None, force_refresh=False
                ),
            )

            job_id = import_task.id
            logger.info(
                f"Created chained tasks: custom directory import ({job_id}) -> artist processing"
            )
        else:
            # Just run import without artist processing
            import_task = import_from_custom_directory_task.apply_async(
                kwargs={
                    "source_directory": str(directory),
                    "fetch_metadata": request.fetch_metadata,
                    "max_files": request.max_files,
                },
                priority=9,
            )

            job_id = import_task.id
            logger.info(f"Created Celery task for custom directory import: {job_id}")

        message = f"Custom directory import job queued with ID: {job_id}"
        if request.process_artists:
            message += " (artist processing will run after import completes)"

        return ImportStartResponse(
            success=True,
            job_id=job_id,
            artist_processing_job_id=artist_processing_job_id,
            message=message,
        )

    except Exception as e:
        logger.error(f"Error starting custom directory import: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class UploadResponse(BaseModel):
    """Upload response"""

    success: bool
    upload_directory: str
    files_uploaded: int
    total_size_mb: float
    message: str


@router.post("/upload-videos", response_model=UploadResponse)
async def upload_videos(
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
):
    """
    Upload video files from user's PC to a temporary directory on the server.

    This endpoint:
    1. Creates a temporary directory
    2. Saves uploaded files to the temp directory
    3. Returns the temp directory path for import

    After import is complete, the temp directory should be cleaned up.
    """
    try:
        logger.info(f"Upload request received with {len(files) if files else 0} files")

        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        # Filter for video files only
        video_extensions = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }

        # Log all filenames
        for f in files:
            logger.info(f"Received file: {f.filename}, type: {f.content_type}")

        video_files = [
            f for f in files if Path(f.filename).suffix.lower() in video_extensions
        ]

        if not video_files:
            logger.warning(
                f"No video files found. Received {len(files)} files but none matched video extensions"
            )
            raise HTTPException(
                status_code=400, detail="No video files found in upload"
            )

        logger.info(f"Filtered to {len(video_files)} video files for upload")

        # Create temporary directory for uploads
        temp_dir = Path(tempfile.mkdtemp(prefix="mvidarr_upload_"))
        logger.info(f"Created temporary upload directory: {temp_dir}")

        total_size = 0
        files_uploaded = 0

        # Save each file to temp directory
        for upload_file in video_files:
            try:
                logger.info(f"Processing file: {upload_file.filename}")
                file_path = temp_dir / upload_file.filename
                logger.info(f"Target path: {file_path}")

                # Create parent directories if filename contains subdirectories
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Read and save file
                contents = await upload_file.read()
                logger.info(f"Read {len(contents)} bytes from {upload_file.filename}")

                file_path.write_bytes(contents)
                logger.info(f"Wrote bytes to {file_path}")

                total_size += len(contents)
                files_uploaded += 1

                logger.info(
                    f"✅ Saved {upload_file.filename} ({len(contents) / (1024*1024):.2f} MB)"
                )

            except Exception as e:
                logger.error(
                    f"❌ Error saving file {upload_file.filename}: {e}", exc_info=True
                )
                # Continue with other files even if one fails
                continue

        logger.info(f"Upload loop complete. files_uploaded={files_uploaded}")

        if files_uploaded == 0:
            # Clean up temp directory if no files were saved
            logger.error(
                "No files were uploaded successfully. Cleaning up temp directory."
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Failed to save any files")

        total_size_mb = total_size / (1024 * 1024)

        logger.info(
            f"Upload complete: {files_uploaded} files, {total_size_mb:.2f} MB total"
        )

        return UploadResponse(
            success=True,
            upload_directory=str(temp_dir),
            files_uploaded=files_uploaded,
            total_size_mb=round(total_size_mb, 2),
            message=f"Successfully uploaded {files_uploaded} video file(s)",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during video upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
