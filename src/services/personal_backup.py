"""
Personal Cloud Backup Service - Phase 3 Week 29
Consumer-focused cloud backup for Google Drive, Dropbox, and OneDrive
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import aiofiles
import aiohttp

from src.auth.jwt_handler import get_jwt_handler
from src.jobs.base_task import BaseTask
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.personal_backup")


class CloudProvider(Enum):
    """Supported cloud storage providers"""

    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    ONEDRIVE = "onedrive"


class BackupType(Enum):
    """Types of backup content"""

    MUSIC_VIDEOS = "music_videos"
    THUMBNAILS = "thumbnails"
    DATABASE = "database"
    CONFIGURATION = "configuration"
    FULL_BACKUP = "full_backup"


class BackupStatus(Enum):
    """Backup operation status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CloudCredentials:
    """Cloud provider credentials and authentication"""

    def __init__(self, provider: CloudProvider):
        self.provider = provider
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[datetime] = None
        self.client_id: Optional[str] = None
        self.client_secret: Optional[str] = None
        self.api_key: Optional[str] = None

    def is_valid(self) -> bool:
        """Check if credentials are valid and not expired"""
        if not self.access_token:
            return False

        if self.expires_at and datetime.now() >= self.expires_at:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider.value,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "client_id": self.client_id,
            "has_credentials": self.is_valid(),
        }


class BackupJob:
    """Individual backup job definition"""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.provider = CloudProvider.GOOGLE_DRIVE
        self.backup_type = BackupType.MUSIC_VIDEOS
        self.source_paths: List[str] = []
        self.destination_path = ""
        self.status = BackupStatus.PENDING
        self.progress_percent = 0.0
        self.files_processed = 0
        self.total_files = 0
        self.bytes_uploaded = 0
        self.total_bytes = 0
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.cloud_file_ids: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "provider": self.provider.value,
            "backup_type": self.backup_type.value,
            "source_paths": self.source_paths,
            "destination_path": self.destination_path,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "files_processed": self.files_processed,
            "total_files": self.total_files,
            "bytes_uploaded": self.bytes_uploaded,
            "total_bytes": self.total_bytes,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
            "cloud_file_ids": self.cloud_file_ids,
            "duration_seconds": self._get_duration_seconds(),
        }

    def _get_duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None


class PersonalBackupService:
    """Consumer-focused personal cloud backup service"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.active_jobs: Dict[str, BackupJob] = {}
        self.credentials: Dict[CloudProvider, CloudCredentials] = {}

        # Consumer-friendly settings
        self.max_concurrent_uploads = 3
        self.chunk_size_mb = 10  # 10MB chunks for consumer internet
        self.retry_attempts = 3
        self.timeout_seconds = 300  # 5 minutes per file

        # Rate limiting for consumer accounts
        self.rate_limits = {
            CloudProvider.GOOGLE_DRIVE: {
                "requests_per_minute": 100,
                "bytes_per_second": 10 * 1024 * 1024,
            },  # 10MB/s
            CloudProvider.DROPBOX: {
                "requests_per_minute": 60,
                "bytes_per_second": 8 * 1024 * 1024,
            },  # 8MB/s
            CloudProvider.ONEDRIVE: {
                "requests_per_minute": 80,
                "bytes_per_second": 12 * 1024 * 1024,
            },  # 12MB/s
        }

    async def initialize(self):
        """Initialize backup service"""
        try:
            self.redis_client = await get_redis_client()

            # Load saved credentials
            await self._load_saved_credentials()

            logger.info("Personal backup service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize personal backup service: {e}")
            raise

    async def configure_cloud_provider(
        self, provider: CloudProvider, credentials: Dict[str, str]
    ) -> Dict[str, Any]:
        """Configure cloud provider credentials"""
        try:
            logger.info(f"Configuring {provider.value} credentials")

            cloud_creds = CloudCredentials(provider)

            if provider == CloudProvider.GOOGLE_DRIVE:
                # Google Drive OAuth setup
                cloud_creds.client_id = credentials.get("client_id")
                cloud_creds.client_secret = credentials.get("client_secret")
                cloud_creds.access_token = credentials.get("access_token")
                cloud_creds.refresh_token = credentials.get("refresh_token")

                # Validate Google Drive credentials
                if cloud_creds.access_token:
                    is_valid = await self._validate_google_drive_credentials(
                        cloud_creds
                    )
                    if not is_valid:
                        raise ValueError("Invalid Google Drive credentials")

            elif provider == CloudProvider.DROPBOX:
                # Dropbox API token
                cloud_creds.access_token = credentials.get("access_token")

                # Validate Dropbox credentials
                if cloud_creds.access_token:
                    is_valid = await self._validate_dropbox_credentials(cloud_creds)
                    if not is_valid:
                        raise ValueError("Invalid Dropbox credentials")

            elif provider == CloudProvider.ONEDRIVE:
                # OneDrive OAuth setup
                cloud_creds.client_id = credentials.get("client_id")
                cloud_creds.client_secret = credentials.get("client_secret")
                cloud_creds.access_token = credentials.get("access_token")
                cloud_creds.refresh_token = credentials.get("refresh_token")

                # Validate OneDrive credentials
                if cloud_creds.access_token:
                    is_valid = await self._validate_onedrive_credentials(cloud_creds)
                    if not is_valid:
                        raise ValueError("Invalid OneDrive credentials")

            # Store credentials
            self.credentials[provider] = cloud_creds
            await self._save_credentials(provider, cloud_creds)

            return {
                "success": True,
                "provider": provider.value,
                "status": "configured",
                "valid": cloud_creds.is_valid(),
            }

        except Exception as e:
            logger.error(f"Failed to configure {provider.value}: {e}")
            return {"success": False, "provider": provider.value, "error": str(e)}

    async def create_backup_job(
        self,
        provider: CloudProvider,
        backup_type: BackupType,
        source_paths: List[str],
        destination_path: str = "",
        options: Optional[Dict] = None,
    ) -> BackupJob:
        """Create a new backup job"""
        try:
            # Generate job ID
            job_id = f"backup_{int(time.time())}_{hashlib.md5(str(source_paths).encode()).hexdigest()[:8]}"

            # Validate provider credentials
            if (
                provider not in self.credentials
                or not self.credentials[provider].is_valid()
            ):
                raise ValueError(f"Invalid or missing credentials for {provider.value}")

            # Create backup job
            job = BackupJob(job_id)
            job.provider = provider
            job.backup_type = backup_type
            job.source_paths = source_paths
            job.destination_path = (
                destination_path or f"MVidarr Backup/{backup_type.value}"
            )

            # Calculate total size and file count
            total_size, total_files = await self._calculate_backup_size(source_paths)
            job.total_bytes = total_size
            job.total_files = total_files

            # Store job
            self.active_jobs[job_id] = job
            await self._save_job_status(job)

            logger.info(
                f"Created backup job {job_id}: {total_files} files, {total_size / (1024*1024):.1f} MB"
            )

            return job

        except Exception as e:
            logger.error(f"Failed to create backup job: {e}")
            raise

    async def start_backup_job(
        self, job_id: str, progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Start executing a backup job"""
        try:
            if job_id not in self.active_jobs:
                raise ValueError(f"Backup job {job_id} not found")

            job = self.active_jobs[job_id]

            if job.status != BackupStatus.PENDING:
                raise ValueError(f"Job {job_id} is not in pending status")

            logger.info(f"Starting backup job {job_id} to {job.provider.value}")

            # Update job status
            job.status = BackupStatus.IN_PROGRESS
            job.started_at = datetime.now()
            await self._save_job_status(job)

            # Execute backup based on provider
            if job.provider == CloudProvider.GOOGLE_DRIVE:
                result = await self._execute_google_drive_backup(job, progress_callback)
            elif job.provider == CloudProvider.DROPBOX:
                result = await self._execute_dropbox_backup(job, progress_callback)
            elif job.provider == CloudProvider.ONEDRIVE:
                result = await self._execute_onedrive_backup(job, progress_callback)
            else:
                raise ValueError(f"Unsupported provider: {job.provider}")

            # Update final status
            if result["success"]:
                job.status = BackupStatus.COMPLETED
                job.completed_at = datetime.now()
                job.progress_percent = 100.0
            else:
                job.status = BackupStatus.FAILED
                job.error_message = result.get("error", "Unknown error")

            await self._save_job_status(job)

            logger.info(
                f"Backup job {job_id} {'completed' if result['success'] else 'failed'}"
            )

            return {
                "job_id": job_id,
                "success": result["success"],
                "status": job.status.value,
                "files_uploaded": job.files_processed,
                "bytes_uploaded": job.bytes_uploaded,
                "error": job.error_message,
            }

        except Exception as e:
            # Update job with error
            if job_id in self.active_jobs:
                job = self.active_jobs[job_id]
                job.status = BackupStatus.FAILED
                job.error_message = str(e)
                await self._save_job_status(job)

            logger.error(f"Failed to start backup job {job_id}: {e}")
            return {"job_id": job_id, "success": False, "error": str(e)}

    async def get_backup_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a backup job"""
        try:
            if job_id in self.active_jobs:
                return self.active_jobs[job_id].to_dict()

            # Try to load from Redis
            cached_job = await self.redis_client.get(f"backup_job:{job_id}")
            if cached_job:
                return json.loads(cached_job)

            return None

        except Exception as e:
            logger.error(f"Failed to get backup status for {job_id}: {e}")
            return None

    async def list_backup_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent backup jobs"""
        try:
            jobs = []

            # Get active jobs
            for job in self.active_jobs.values():
                jobs.append(job.to_dict())

            # Get cached jobs from Redis
            pattern = "backup_job:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys[:limit]:
                try:
                    job_data = await self.redis_client.get(key)
                    if job_data:
                        job_dict = json.loads(job_data)
                        # Avoid duplicates with active jobs
                        if not any(j["job_id"] == job_dict["job_id"] for j in jobs):
                            jobs.append(job_dict)
                except:
                    continue

            # Sort by creation time, most recent first
            jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            return jobs[:limit]

        except Exception as e:
            logger.error(f"Failed to list backup jobs: {e}")
            return []

    async def cancel_backup_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a running backup job"""
        try:
            if job_id not in self.active_jobs:
                return {"success": False, "error": "Job not found"}

            job = self.active_jobs[job_id]

            if job.status not in [BackupStatus.PENDING, BackupStatus.IN_PROGRESS]:
                return {"success": False, "error": "Job cannot be cancelled"}

            job.status = BackupStatus.CANCELLED
            job.completed_at = datetime.now()
            await self._save_job_status(job)

            logger.info(f"Cancelled backup job {job_id}")

            return {"success": True, "job_id": job_id, "status": "cancelled"}

        except Exception as e:
            logger.error(f"Failed to cancel backup job {job_id}: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_google_drive_backup(
        self, job: BackupJob, progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Execute backup to Google Drive"""
        try:
            credentials = self.credentials[CloudProvider.GOOGLE_DRIVE]

            # Ensure credentials are still valid
            if not credentials.is_valid():
                return {
                    "success": False,
                    "error": "Invalid or expired Google Drive credentials",
                }

            uploaded_files = []

            # Create folder in Google Drive
            folder_id = await self._create_google_drive_folder(
                credentials, job.destination_path
            )

            # Upload files
            for i, file_path in enumerate(job.source_paths):
                if job.status == BackupStatus.CANCELLED:
                    break

                try:
                    if os.path.exists(file_path):
                        # Upload file
                        file_id = await self._upload_file_to_google_drive(
                            credentials, file_path, folder_id
                        )

                        if file_id:
                            uploaded_files.append(file_id)
                            job.cloud_file_ids.append(file_id)
                            job.files_processed += 1

                            # Update progress
                            file_size = os.path.getsize(file_path)
                            job.bytes_uploaded += file_size
                            job.progress_percent = (
                                job.files_processed / job.total_files
                            ) * 100

                            if progress_callback:
                                await progress_callback(
                                    job.job_id,
                                    job.progress_percent,
                                    os.path.basename(file_path),
                                )

                            await self._save_job_status(job)

                            # Rate limiting
                            await asyncio.sleep(0.5)  # Consumer-friendly rate limiting

                except Exception as e:
                    logger.warning(f"Failed to upload {file_path} to Google Drive: {e}")
                    continue

            success = len(uploaded_files) > 0
            return {
                "success": success,
                "uploaded_files": len(uploaded_files),
                "folder_id": folder_id,
            }

        except Exception as e:
            logger.error(f"Google Drive backup failed: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_dropbox_backup(
        self, job: BackupJob, progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Execute backup to Dropbox"""
        try:
            credentials = self.credentials[CloudProvider.DROPBOX]

            if not credentials.is_valid():
                return {"success": False, "error": "Invalid Dropbox credentials"}

            uploaded_files = []

            # Upload files to Dropbox
            for i, file_path in enumerate(job.source_paths):
                if job.status == BackupStatus.CANCELLED:
                    break

                try:
                    if os.path.exists(file_path):
                        # Upload file
                        success = await self._upload_file_to_dropbox(
                            credentials, file_path, job.destination_path
                        )

                        if success:
                            uploaded_files.append(file_path)
                            job.files_processed += 1

                            # Update progress
                            file_size = os.path.getsize(file_path)
                            job.bytes_uploaded += file_size
                            job.progress_percent = (
                                job.files_processed / job.total_files
                            ) * 100

                            if progress_callback:
                                await progress_callback(
                                    job.job_id,
                                    job.progress_percent,
                                    os.path.basename(file_path),
                                )

                            await self._save_job_status(job)

                            # Rate limiting
                            await asyncio.sleep(
                                1.0
                            )  # Conservative rate limiting for Dropbox

                except Exception as e:
                    logger.warning(f"Failed to upload {file_path} to Dropbox: {e}")
                    continue

            success = len(uploaded_files) > 0
            return {"success": success, "uploaded_files": len(uploaded_files)}

        except Exception as e:
            logger.error(f"Dropbox backup failed: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_onedrive_backup(
        self, job: BackupJob, progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Execute backup to OneDrive"""
        try:
            credentials = self.credentials[CloudProvider.ONEDRIVE]

            if not credentials.is_valid():
                return {"success": False, "error": "Invalid OneDrive credentials"}

            uploaded_files = []

            # Upload files to OneDrive
            for i, file_path in enumerate(job.source_paths):
                if job.status == BackupStatus.CANCELLED:
                    break

                try:
                    if os.path.exists(file_path):
                        # Upload file
                        file_id = await self._upload_file_to_onedrive(
                            credentials, file_path, job.destination_path
                        )

                        if file_id:
                            uploaded_files.append(file_id)
                            job.cloud_file_ids.append(file_id)
                            job.files_processed += 1

                            # Update progress
                            file_size = os.path.getsize(file_path)
                            job.bytes_uploaded += file_size
                            job.progress_percent = (
                                job.files_processed / job.total_files
                            ) * 100

                            if progress_callback:
                                await progress_callback(
                                    job.job_id,
                                    job.progress_percent,
                                    os.path.basename(file_path),
                                )

                            await self._save_job_status(job)

                            # Rate limiting
                            await asyncio.sleep(0.75)  # OneDrive rate limiting

                except Exception as e:
                    logger.warning(f"Failed to upload {file_path} to OneDrive: {e}")
                    continue

            success = len(uploaded_files) > 0
            return {"success": success, "uploaded_files": len(uploaded_files)}

        except Exception as e:
            logger.error(f"OneDrive backup failed: {e}")
            return {"success": False, "error": str(e)}

    async def _calculate_backup_size(self, file_paths: List[str]) -> tuple[int, int]:
        """Calculate total size and file count for backup"""
        total_size = 0
        total_files = 0

        for path in file_paths:
            try:
                if os.path.isfile(path):
                    total_size += os.path.getsize(path)
                    total_files += 1
                elif os.path.isdir(path):
                    for root, dirs, files in os.walk(path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                total_size += os.path.getsize(file_path)
                                total_files += 1
                            except:
                                continue
            except:
                continue

        return total_size, total_files

    # Placeholder methods for cloud provider API calls
    # These would contain the actual API integration code

    async def _validate_google_drive_credentials(
        self, credentials: CloudCredentials
    ) -> bool:
        """Validate Google Drive credentials"""
        # This would make a test API call to Google Drive
        # For now, return True if access_token exists
        return bool(credentials.access_token)

    async def _validate_dropbox_credentials(
        self, credentials: CloudCredentials
    ) -> bool:
        """Validate Dropbox credentials"""
        # This would make a test API call to Dropbox
        return bool(credentials.access_token)

    async def _validate_onedrive_credentials(
        self, credentials: CloudCredentials
    ) -> bool:
        """Validate OneDrive credentials"""
        # This would make a test API call to OneDrive
        return bool(credentials.access_token)

    async def _create_google_drive_folder(
        self, credentials: CloudCredentials, folder_name: str
    ) -> str:
        """Create folder in Google Drive and return folder ID"""
        # This would use Google Drive API to create folder
        # For now, return a placeholder folder ID
        return f"folder_{hashlib.md5(folder_name.encode()).hexdigest()[:12]}"

    async def _upload_file_to_google_drive(
        self, credentials: CloudCredentials, file_path: str, folder_id: str
    ) -> Optional[str]:
        """Upload file to Google Drive"""
        # This would implement the actual Google Drive file upload
        # Return file ID on success, None on failure
        await asyncio.sleep(0.1)  # Simulate upload time
        return f"file_{hashlib.md5(file_path.encode()).hexdigest()[:12]}"

    async def _upload_file_to_dropbox(
        self, credentials: CloudCredentials, file_path: str, destination_path: str
    ) -> bool:
        """Upload file to Dropbox"""
        # This would implement the actual Dropbox file upload
        await asyncio.sleep(0.1)  # Simulate upload time
        return True

    async def _upload_file_to_onedrive(
        self, credentials: CloudCredentials, file_path: str, destination_path: str
    ) -> Optional[str]:
        """Upload file to OneDrive"""
        # This would implement the actual OneDrive file upload
        await asyncio.sleep(0.1)  # Simulate upload time
        return f"file_{hashlib.md5(file_path.encode()).hexdigest()[:12]}"

    async def _save_credentials(
        self, provider: CloudProvider, credentials: CloudCredentials
    ):
        """Save credentials to secure storage"""
        try:
            # Store in Redis with encryption (in production, use proper encryption)
            cache_key = f"cloud_credentials:{provider.value}"
            await self.redis_client.setex(
                cache_key, 86400 * 30, json.dumps(credentials.to_dict())
            )

        except Exception as e:
            logger.error(f"Failed to save credentials for {provider.value}: {e}")

    async def _load_saved_credentials(self):
        """Load saved credentials from storage"""
        try:
            for provider in CloudProvider:
                cache_key = f"cloud_credentials:{provider.value}"
                cached_creds = await self.redis_client.get(cache_key)

                if cached_creds:
                    creds_data = json.loads(cached_creds)
                    credentials = CloudCredentials(provider)
                    credentials.access_token = creds_data.get("access_token")
                    credentials.refresh_token = creds_data.get("refresh_token")
                    credentials.client_id = creds_data.get("client_id")

                    if creds_data.get("expires_at"):
                        credentials.expires_at = datetime.fromisoformat(
                            creds_data["expires_at"]
                        )

                    self.credentials[provider] = credentials

        except Exception as e:
            logger.warning(f"Failed to load saved credentials: {e}")

    async def _save_job_status(self, job: BackupJob):
        """Save job status to Redis"""
        try:
            cache_key = f"backup_job:{job.job_id}"
            await self.redis_client.setex(
                cache_key, 86400 * 7, json.dumps(job.to_dict())
            )

        except Exception as e:
            logger.error(f"Failed to save job status for {job.job_id}: {e}")


# Global service instance
_personal_backup_service = None


async def get_personal_backup_service(
    config: Optional[Dict] = None,
) -> PersonalBackupService:
    """Get global personal backup service instance"""
    global _personal_backup_service

    if _personal_backup_service is None:
        _personal_backup_service = PersonalBackupService(config)
        await _personal_backup_service.initialize()

    return _personal_backup_service
