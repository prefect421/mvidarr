"""
Basic File Synchronization Service - Phase 3 Week 29
Simple synchronization between local storage and personal cloud providers
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import aiofiles
from src.services.personal_backup import CloudProvider, get_personal_backup_service
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.sync_manager")


class SyncDirection(Enum):
    """Synchronization directions"""

    UPLOAD_ONLY = "upload_only"
    DOWNLOAD_ONLY = "download_only"
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(Enum):
    """Sync operation status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class FileChange:
    """Represents a file change for synchronization"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.local_modified: Optional[datetime] = None
        self.cloud_modified: Optional[datetime] = None
        self.local_size: int = 0
        self.cloud_size: int = 0
        self.local_hash: Optional[str] = None
        self.cloud_hash: Optional[str] = None
        self.change_type: str = "unknown"  # modified, added, deleted
        self.needs_upload: bool = False
        self.needs_download: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "local_modified": (
                self.local_modified.isoformat() if self.local_modified else None
            ),
            "cloud_modified": (
                self.cloud_modified.isoformat() if self.cloud_modified else None
            ),
            "local_size": self.local_size,
            "cloud_size": self.cloud_size,
            "local_hash": self.local_hash,
            "cloud_hash": self.cloud_hash,
            "change_type": self.change_type,
            "needs_upload": self.needs_upload,
            "needs_download": self.needs_download,
        }


class SyncProfile:
    """Synchronization profile configuration"""

    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        self.name: str = ""
        self.local_path: str = ""
        self.cloud_provider: CloudProvider = CloudProvider.GOOGLE_DRIVE
        self.cloud_path: str = ""
        self.sync_direction: SyncDirection = SyncDirection.UPLOAD_ONLY
        self.enabled: bool = True
        self.sync_interval_minutes: int = 60
        self.include_patterns: List[str] = ["*.mp4", "*.mkv", "*.avi", "*.mov"]
        self.exclude_patterns: List[str] = ["*.tmp", "*.part", ".*"]
        self.max_file_size_mb: int = 500
        self.created_at: datetime = datetime.now()
        self.last_sync: Optional[datetime] = None
        self.last_successful_sync: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "local_path": self.local_path,
            "cloud_provider": self.cloud_provider.value,
            "cloud_path": self.cloud_path,
            "sync_direction": self.sync_direction.value,
            "enabled": self.enabled,
            "sync_interval_minutes": self.sync_interval_minutes,
            "include_patterns": self.include_patterns,
            "exclude_patterns": self.exclude_patterns,
            "max_file_size_mb": self.max_file_size_mb,
            "created_at": self.created_at.isoformat(),
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_successful_sync": (
                self.last_successful_sync.isoformat()
                if self.last_successful_sync
                else None
            ),
        }


class SyncJob:
    """Individual synchronization job"""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.profile_id: str = ""
        self.status: SyncStatus = SyncStatus.PENDING
        self.progress_percent: float = 0.0
        self.files_checked: int = 0
        self.files_uploaded: int = 0
        self.files_downloaded: int = 0
        self.files_skipped: int = 0
        self.bytes_transferred: int = 0
        self.created_at: datetime = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.changes_detected: List[FileChange] = []
        self.current_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "profile_id": self.profile_id,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "files_checked": self.files_checked,
            "files_uploaded": self.files_uploaded,
            "files_downloaded": self.files_downloaded,
            "files_skipped": self.files_skipped,
            "bytes_transferred": self.bytes_transferred,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
            "current_file": self.current_file,
            "changes_count": len(self.changes_detected),
            "duration_seconds": self._get_duration_seconds(),
        }

    def _get_duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None


class SyncManager:
    """Basic file synchronization manager for personal cloud storage"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.backup_service = None
        self.active_profiles: Dict[str, SyncProfile] = {}
        self.active_jobs: Dict[str, SyncJob] = {}
        self.sync_tasks: Dict[str, asyncio.Task] = {}

        # Consumer-friendly sync settings
        self.max_concurrent_syncs = 2
        self.sync_check_interval = 300  # 5 minutes
        self.file_chunk_size = 1024 * 1024  # 1MB chunks

    async def initialize(self):
        """Initialize sync manager"""
        try:
            self.redis_client = await get_redis_client()
            self.backup_service = await get_personal_backup_service()

            # Load saved profiles
            await self._load_saved_profiles()

            # Start sync scheduler
            await self._start_sync_scheduler()

            logger.info("File sync manager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize sync manager: {e}")
            raise

    async def create_sync_profile(
        self,
        name: str,
        local_path: str,
        cloud_provider: CloudProvider,
        cloud_path: str,
        sync_direction: SyncDirection = SyncDirection.UPLOAD_ONLY,
        options: Optional[Dict] = None,
    ) -> SyncProfile:
        """Create a new synchronization profile"""
        try:
            # Validate local path exists
            if not os.path.exists(local_path):
                raise ValueError(f"Local path does not exist: {local_path}")

            # Generate profile ID
            profile_id = f"sync_{hashlib.md5(f'{name}_{local_path}'.encode(), usedforsecurity=False).hexdigest()[:12]}"

            # Create profile
            profile = SyncProfile(profile_id)
            profile.name = name
            profile.local_path = local_path
            profile.cloud_provider = cloud_provider
            profile.cloud_path = cloud_path
            profile.sync_direction = sync_direction

            # Apply options
            if options:
                profile.sync_interval_minutes = options.get("sync_interval_minutes", 60)
                profile.include_patterns = options.get(
                    "include_patterns", profile.include_patterns
                )
                profile.exclude_patterns = options.get(
                    "exclude_patterns", profile.exclude_patterns
                )
                profile.max_file_size_mb = options.get("max_file_size_mb", 500)

            # Store profile
            self.active_profiles[profile_id] = profile
            await self._save_profile(profile)

            logger.info(
                f"Created sync profile '{name}' ({profile_id}) for {local_path}"
            )

            return profile

        except Exception as e:
            logger.error(f"Failed to create sync profile: {e}")
            raise

    async def start_sync_job(
        self, profile_id: str, progress_callback: Optional[Callable] = None
    ) -> SyncJob:
        """Start a synchronization job for a profile"""
        try:
            if profile_id not in self.active_profiles:
                raise ValueError(f"Sync profile {profile_id} not found")

            profile = self.active_profiles[profile_id]

            if not profile.enabled:
                raise ValueError(f"Sync profile {profile_id} is disabled")

            # Generate job ID
            job_id = f"sync_job_{int(time.time())}_{profile_id}"

            # Create sync job
            job = SyncJob(job_id)
            job.profile_id = profile_id
            job.status = SyncStatus.IN_PROGRESS
            job.started_at = datetime.now()

            # Store job
            self.active_jobs[job_id] = job
            await self._save_job_status(job)

            logger.info(f"Starting sync job {job_id} for profile {profile_id}")

            # Execute sync
            await self._execute_sync_job(job, profile, progress_callback)

            return job

        except Exception as e:
            logger.error(f"Failed to start sync job: {e}")
            raise

    async def _execute_sync_job(
        self, job: SyncJob, profile: SyncProfile, progress_callback: Optional[Callable]
    ):
        """Execute synchronization job"""
        try:
            # Phase 1: Scan local files
            job.current_file = "Scanning local files..."
            await self._save_job_status(job)

            local_files = await self._scan_local_files(profile)
            job.files_checked = len(local_files)

            # Phase 2: Compare with cloud (simplified for consumer use)
            job.current_file = "Comparing with cloud..."
            changes = await self._detect_changes(profile, local_files)
            job.changes_detected = changes

            # Phase 3: Apply changes
            total_operations = len(
                [c for c in changes if c.needs_upload or c.needs_download]
            )
            completed_operations = 0

            for change in changes:
                if job.status != SyncStatus.IN_PROGRESS:
                    break

                job.current_file = os.path.basename(change.file_path)

                if change.needs_upload and profile.sync_direction in [
                    SyncDirection.UPLOAD_ONLY,
                    SyncDirection.BIDIRECTIONAL,
                ]:
                    # Upload file using backup service
                    success = await self._upload_file(profile, change)
                    if success:
                        job.files_uploaded += 1
                        job.bytes_transferred += change.local_size
                    else:
                        job.files_skipped += 1

                elif change.needs_download and profile.sync_direction in [
                    SyncDirection.DOWNLOAD_ONLY,
                    SyncDirection.BIDIRECTIONAL,
                ]:
                    # Download file (simplified implementation)
                    success = await self._download_file(profile, change)
                    if success:
                        job.files_downloaded += 1
                        job.bytes_transferred += change.cloud_size
                    else:
                        job.files_skipped += 1

                completed_operations += 1
                job.progress_percent = (
                    (completed_operations / total_operations) * 100
                    if total_operations > 0
                    else 100
                )

                if progress_callback:
                    await progress_callback(
                        job.job_id, job.progress_percent, job.current_file
                    )

                await self._save_job_status(job)

                # Consumer-friendly rate limiting
                await asyncio.sleep(0.5)

            # Complete job
            job.status = SyncStatus.COMPLETED
            job.completed_at = datetime.now()
            job.progress_percent = 100.0

            # Update profile
            profile.last_sync = datetime.now()
            if job.error_message is None:
                profile.last_successful_sync = datetime.now()

            await self._save_profile(profile)
            await self._save_job_status(job)

            logger.info(
                f"Sync job {job.job_id} completed: {job.files_uploaded} uploaded, {job.files_downloaded} downloaded"
            )

        except Exception as e:
            job.status = SyncStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now()
            await self._save_job_status(job)

            logger.error(f"Sync job {job.job_id} failed: {e}")

    async def _scan_local_files(self, profile: SyncProfile) -> List[str]:
        """Scan local directory for files matching patterns"""
        try:
            files = []
            local_path = Path(profile.local_path)

            if not local_path.exists():
                return files

            # Walk directory
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    # Check file patterns
                    if self._matches_patterns(file_path.name, profile.include_patterns):
                        if not self._matches_patterns(
                            file_path.name, profile.exclude_patterns
                        ):
                            # Check file size
                            file_size = file_path.stat().st_size / (1024 * 1024)  # MB
                            if file_size <= profile.max_file_size_mb:
                                files.append(str(file_path))

            return files

        except Exception as e:
            logger.error(f"Failed to scan local files: {e}")
            return []

    async def _detect_changes(
        self, profile: SyncProfile, local_files: List[str]
    ) -> List[FileChange]:
        """Detect changes between local and cloud files (simplified)"""
        try:
            changes = []

            for file_path in local_files:
                change = FileChange(file_path)

                # Get local file info
                if os.path.exists(file_path):
                    stat = os.stat(file_path)
                    change.local_modified = datetime.fromtimestamp(stat.st_mtime)
                    change.local_size = stat.st_size

                    # Calculate hash for small files
                    if change.local_size < 10 * 1024 * 1024:  # 10MB
                        change.local_hash = await self._calculate_file_hash(file_path)

                # For consumer use, assume files need upload if they exist locally
                # In production, this would query cloud storage for comparison
                change.needs_upload = True
                change.change_type = "added"

                changes.append(change)

            return changes

        except Exception as e:
            logger.error(f"Failed to detect changes: {e}")
            return []

    async def _upload_file(self, profile: SyncProfile, change: FileChange) -> bool:
        """Upload file using backup service"""
        try:
            # Use backup service to upload file
            job = await self.backup_service.create_backup_job(
                provider=profile.cloud_provider,
                backup_type="custom_folder",
                source_paths=[change.file_path],
                destination_path=profile.cloud_path,
            )

            result = await self.backup_service.start_backup_job(job.job_id)
            return result["success"]

        except Exception as e:
            logger.error(f"Failed to upload file {change.file_path}: {e}")
            return False

    async def _download_file(self, profile: SyncProfile, change: FileChange) -> bool:
        """Download file from cloud (placeholder implementation)"""
        try:
            # This would implement cloud file download
            # For consumer use, this is simplified
            await asyncio.sleep(0.1)  # Simulate download
            return True

        except Exception as e:
            logger.error(f"Failed to download file {change.file_path}: {e}")
            return False

    def _matches_patterns(self, filename: str, patterns: List[str]) -> bool:
        """Check if filename matches any of the patterns"""
        import fnmatch

        return any(
            fnmatch.fnmatch(filename.lower(), pattern.lower()) for pattern in patterns
        )

    async def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of file (for checksums, not security)"""
        try:
            hash_md5 = hashlib.md5(usedforsecurity=False)
            async with aiofiles.open(file_path, "rb") as f:
                async for chunk in self._read_chunks(f):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()

        except Exception as e:
            logger.warning(f"Failed to calculate hash for {file_path}: {e}")
            return ""

    async def _read_chunks(self, file, chunk_size: int = 8192):
        """Read file in chunks"""
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            yield chunk

    async def get_sync_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get sync job status"""
        try:
            if job_id in self.active_jobs:
                return self.active_jobs[job_id].to_dict()

            # Try to load from Redis
            cached_job = await self.redis_client.get(f"sync_job:{job_id}")
            if cached_job:
                return json.loads(cached_job)

            return None

        except Exception as e:
            logger.error(f"Failed to get sync status for {job_id}: {e}")
            return None

    async def list_sync_profiles(self) -> List[Dict[str, Any]]:
        """List all sync profiles"""
        try:
            profiles = []
            for profile in self.active_profiles.values():
                profile_dict = profile.to_dict()

                # Add runtime information
                profile_dict["is_syncing"] = any(
                    job.profile_id == profile.profile_id
                    and job.status == SyncStatus.IN_PROGRESS
                    for job in self.active_jobs.values()
                )

                profiles.append(profile_dict)

            return profiles

        except Exception as e:
            logger.error(f"Failed to list sync profiles: {e}")
            return []

    async def _start_sync_scheduler(self):
        """Start automatic sync scheduler"""
        try:

            async def sync_scheduler():
                while True:
                    try:
                        await asyncio.sleep(self.sync_check_interval)

                        # Check each profile for scheduled sync
                        for profile in self.active_profiles.values():
                            if not profile.enabled:
                                continue

                            # Check if sync is due
                            if profile.last_sync is None:
                                # Never synced, sync now
                                should_sync = True
                            else:
                                next_sync = profile.last_sync + timedelta(
                                    minutes=profile.sync_interval_minutes
                                )
                                should_sync = datetime.now() >= next_sync

                            if (
                                should_sync
                                and len(
                                    [
                                        j
                                        for j in self.active_jobs.values()
                                        if j.status == SyncStatus.IN_PROGRESS
                                    ]
                                )
                                < self.max_concurrent_syncs
                            ):
                                logger.info(
                                    f"Starting scheduled sync for profile {profile.profile_id}"
                                )
                                try:
                                    await self.start_sync_job(profile.profile_id)
                                except Exception as e:
                                    logger.error(
                                        f"Failed to start scheduled sync for {profile.profile_id}: {e}"
                                    )

                    except Exception as e:
                        logger.error(f"Sync scheduler error: {e}")
                        await asyncio.sleep(60)  # Wait before retrying

            # Start scheduler task
            asyncio.create_task(sync_scheduler())
            logger.info("Sync scheduler started")

        except Exception as e:
            logger.error(f"Failed to start sync scheduler: {e}")

    async def _save_profile(self, profile: SyncProfile):
        """Save profile to Redis"""
        try:
            cache_key = f"sync_profile:{profile.profile_id}"
            await self.redis_client.setex(
                cache_key, 86400 * 30, json.dumps(profile.to_dict())
            )

        except Exception as e:
            logger.error(f"Failed to save sync profile {profile.profile_id}: {e}")

    async def _load_saved_profiles(self):
        """Load saved profiles from Redis"""
        try:
            pattern = "sync_profile:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys:
                try:
                    profile_data = await self.redis_client.get(key)
                    if profile_data:
                        profile_dict = json.loads(profile_data)

                        # Reconstruct SyncProfile object
                        profile = SyncProfile(profile_dict["profile_id"])
                        profile.name = profile_dict.get("name", "")
                        profile.local_path = profile_dict.get("local_path", "")
                        profile.cloud_provider = CloudProvider(
                            profile_dict.get("cloud_provider", "google_drive")
                        )
                        profile.cloud_path = profile_dict.get("cloud_path", "")
                        profile.sync_direction = SyncDirection(
                            profile_dict.get("sync_direction", "upload_only")
                        )
                        profile.enabled = profile_dict.get("enabled", True)
                        profile.sync_interval_minutes = profile_dict.get(
                            "sync_interval_minutes", 60
                        )
                        profile.include_patterns = profile_dict.get(
                            "include_patterns", ["*.mp4"]
                        )
                        profile.exclude_patterns = profile_dict.get(
                            "exclude_patterns", ["*.tmp"]
                        )
                        profile.max_file_size_mb = profile_dict.get(
                            "max_file_size_mb", 500
                        )

                        if profile_dict.get("created_at"):
                            profile.created_at = datetime.fromisoformat(
                                profile_dict["created_at"]
                            )
                        if profile_dict.get("last_sync"):
                            profile.last_sync = datetime.fromisoformat(
                                profile_dict["last_sync"]
                            )
                        if profile_dict.get("last_successful_sync"):
                            profile.last_successful_sync = datetime.fromisoformat(
                                profile_dict["last_successful_sync"]
                            )

                        self.active_profiles[profile.profile_id] = profile

                except Exception as e:
                    logger.warning(f"Failed to load sync profile from {key}: {e}")
                    continue

            logger.info(f"Loaded {len(self.active_profiles)} sync profiles")

        except Exception as e:
            logger.error(f"Failed to load saved profiles: {e}")

    async def _save_job_status(self, job: SyncJob):
        """Save job status to Redis"""
        try:
            cache_key = f"sync_job:{job.job_id}"
            await self.redis_client.setex(
                cache_key, 86400 * 7, json.dumps(job.to_dict())
            )

        except Exception as e:
            logger.error(f"Failed to save sync job status for {job.job_id}: {e}")


# Global service instance
_sync_manager = None


async def get_sync_manager(config: Optional[Dict] = None) -> SyncManager:
    """Get global sync manager instance"""
    global _sync_manager

    if _sync_manager is None:
        _sync_manager = SyncManager(config)
        await _sync_manager.initialize()

    return _sync_manager
