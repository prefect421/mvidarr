"""
Local Backup & Recovery Service for MVidarr
v1.0.0 Feature: Automated local backups for database, config, and media
Issue #93: https://github.com/prefect421/mvidarr/issues/93
"""

import gzip
import json
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from src.config.config import Config
from src.utils.logger import get_logger

logger = get_logger("mvidarr.backup_service")


def _safe_tar_extract(tar: tarfile.TarFile, path: str) -> None:
    """Safely extract tar archive, filtering out dangerous members."""
    import sys

    if sys.version_info >= (3, 12):
        tar.extractall(path=path, filter="data")
    else:
        safe_members = []
        for member in tar.getmembers():
            # Block absolute paths
            if member.name.startswith("/") or member.name.startswith("\\"):
                logger.warning(f"Skipping absolute path in tar: {member.name}")
                continue
            # Block path traversal
            if ".." in member.name.split("/"):
                logger.warning(f"Skipping path traversal in tar: {member.name}")
                continue
            # Block symlinks and hardlinks
            if member.issym() or member.islnk():
                logger.warning(f"Skipping symlink/hardlink in tar: {member.name}")
                continue
            safe_members.append(member)
        tar.extractall(path=path, members=safe_members)


class BackupType(Enum):
    """Types of backups supported"""

    DATABASE = "database"
    CONFIGURATION = "configuration"
    THUMBNAILS = "thumbnails"
    FULL = "full"  # All of the above


class BackupStatus(Enum):
    """Backup operation status"""

    SUCCESS = "success"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"


class BackupMetadata:
    """Metadata for a backup file"""

    def __init__(
        self,
        backup_id: str,
        backup_type: BackupType,
        timestamp: datetime,
        file_path: str,
        file_size: int,
        status: BackupStatus,
        error: Optional[str] = None,
    ):
        self.backup_id = backup_id
        self.backup_type = backup_type
        self.timestamp = timestamp
        self.file_path = file_path
        self.file_size = file_size
        self.status = status
        self.error = error

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "backup_id": self.backup_id,
            "backup_type": self.backup_type.value,
            "timestamp": self.timestamp.isoformat(),
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_size_mb": round(self.file_size / (1024 * 1024), 2),
            "status": self.status.value,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "BackupMetadata":
        """Create from dictionary"""
        return cls(
            backup_id=data["backup_id"],
            backup_type=BackupType(data["backup_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            file_path=data["file_path"],
            file_size=data["file_size"],
            status=BackupStatus(data["status"]),
            error=data.get("error"),
        )


class BackupService:
    """
    Local backup and recovery service for MVidarr.

    Handles automated backups of:
    - Database (MariaDB/MySQL dumps)
    - Configuration files (.env, config files)
    - Thumbnails and media metadata

    Features:
    - Compressed archives (tar.gz)
    - Backup rotation with retention policy
    - Restore functionality
    - Backup verification
    """

    def __init__(self, config: Optional[Config] = None):
        """Initialize backup service"""
        self.config = config or Config()

        # Backup directory - where all backups are stored
        self.backup_dir = Path(
            getattr(self.config, "BACKUPS_DIR", None) or "data/backups"
        )
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Metadata file - tracks all backups
        self.metadata_file = self.backup_dir / "backup_metadata.json"

        # Retention settings (configurable via environment variables)
        self.retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
        self.max_backups = int(os.environ.get("MAX_BACKUPS", "10"))

    def create_backup(
        self, backup_type: BackupType = BackupType.FULL
    ) -> Optional[BackupMetadata]:
        """
        Create a backup of the specified type.

        Args:
            backup_type: Type of backup to create

        Returns:
            BackupMetadata if successful, None otherwise
        """
        backup_id = self._generate_backup_id(backup_type)
        logger.info(f"Starting {backup_type.value} backup: {backup_id}")

        try:
            if backup_type == BackupType.DATABASE:
                metadata = self._backup_database(backup_id)
            elif backup_type == BackupType.CONFIGURATION:
                metadata = self._backup_configuration(backup_id)
            elif backup_type == BackupType.THUMBNAILS:
                metadata = self._backup_thumbnails(backup_id)
            elif backup_type == BackupType.FULL:
                metadata = self._backup_full(backup_id)
            else:
                logger.error(f"Unknown backup type: {backup_type}")
                return None

            if metadata:
                self._save_metadata(metadata)
                self._cleanup_old_backups(backup_type)
                logger.info(
                    f"Backup completed: {metadata.file_path} ({metadata.file_size_mb}MB)"
                )

            return metadata

        except Exception as e:
            logger.error(f"Backup failed: {str(e)}", exc_info=True)
            return BackupMetadata(
                backup_id=backup_id,
                backup_type=backup_type,
                timestamp=datetime.utcnow(),
                file_path="",
                file_size=0,
                status=BackupStatus.FAILED,
                error=str(e),
            )

    def _backup_database(self, backup_id: str) -> Optional[BackupMetadata]:
        """Backup MariaDB/MySQL database"""
        timestamp = datetime.utcnow()
        filename = f"database_{backup_id}.sql.gz"
        file_path = self.backup_dir / filename

        try:
            # Build mysqldump command (password via env var to avoid process list exposure)
            dump_cmd = [
                "mysqldump",
                f"--host={self.config.DB_HOST}",
                f"--port={self.config.DB_PORT}",
                f"--user={self.config.DB_USER}",
                "--single-transaction",
                "--routines",
                "--triggers",
                "--events",
                self.config.DB_NAME,
            ]
            dump_env = {**os.environ, "MYSQL_PWD": self.config.DB_PASSWORD}

            logger.info(f"Creating database dump: {filename}")

            # Execute mysqldump and compress with gzip
            with gzip.open(file_path, "wb") as gz_file:
                process = subprocess.Popen(
                    dump_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=dump_env,
                )
                stdout, stderr = process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode("utf-8")
                    logger.error(f"mysqldump failed: {error_msg}")
                    raise Exception(f"Database dump failed: {error_msg}")

                gz_file.write(stdout)

            file_size = file_path.stat().st_size

            return BackupMetadata(
                backup_id=backup_id,
                backup_type=BackupType.DATABASE,
                timestamp=timestamp,
                file_path=str(file_path),
                file_size=file_size,
                status=BackupStatus.SUCCESS,
            )

        except Exception as e:
            logger.error(f"Database backup failed: {str(e)}")
            if file_path.exists():
                file_path.unlink()
            raise

    def _backup_configuration(self, backup_id: str) -> Optional[BackupMetadata]:
        """Backup configuration files"""
        timestamp = datetime.utcnow()
        filename = f"config_{backup_id}.tar.gz"
        file_path = self.backup_dir / filename

        try:
            logger.info(f"Creating configuration backup: {filename}")

            # Files to backup
            config_files = [
                ".env",
                "config.yml",
                "docker-config.yml",
                ".env.example",
            ]

            with tarfile.open(file_path, "w:gz") as tar:
                for config_file in config_files:
                    file_to_backup = Path(config_file)
                    if file_to_backup.exists():
                        tar.add(file_to_backup, arcname=config_file)
                        logger.debug(f"Added {config_file} to backup")

            file_size = file_path.stat().st_size

            return BackupMetadata(
                backup_id=backup_id,
                backup_type=BackupType.CONFIGURATION,
                timestamp=timestamp,
                file_path=str(file_path),
                file_size=file_size,
                status=BackupStatus.SUCCESS,
            )

        except Exception as e:
            logger.error(f"Configuration backup failed: {str(e)}")
            if file_path.exists():
                file_path.unlink()
            raise

    def _backup_thumbnails(self, backup_id: str) -> Optional[BackupMetadata]:
        """Backup thumbnails directory"""
        timestamp = datetime.utcnow()
        filename = f"thumbnails_{backup_id}.tar.gz"
        file_path = self.backup_dir / filename

        try:
            thumbnails_path = Path(self.config.THUMBNAILS_PATH or "data/thumbnails")

            if not thumbnails_path.exists():
                logger.warning(f"Thumbnails directory not found: {thumbnails_path}")
                return None

            logger.info(f"Creating thumbnails backup: {filename}")

            with tarfile.open(file_path, "w:gz") as tar:
                tar.add(thumbnails_path, arcname="thumbnails")

            file_size = file_path.stat().st_size

            return BackupMetadata(
                backup_id=backup_id,
                backup_type=BackupType.THUMBNAILS,
                timestamp=timestamp,
                file_path=str(file_path),
                file_size=file_size,
                status=BackupStatus.SUCCESS,
            )

        except Exception as e:
            logger.error(f"Thumbnails backup failed: {str(e)}")
            if file_path.exists():
                file_path.unlink()
            raise

    def _backup_full(self, backup_id: str) -> Optional[BackupMetadata]:
        """Create full backup (database + config + thumbnails)"""
        timestamp = datetime.utcnow()
        filename = f"full_{backup_id}.tar.gz"
        file_path = self.backup_dir / filename

        try:
            logger.info(f"Creating full backup: {filename}")

            # Create individual backups first
            db_metadata = self._backup_database(f"{backup_id}_db")
            config_metadata = self._backup_configuration(f"{backup_id}_config")
            thumb_metadata = self._backup_thumbnails(f"{backup_id}_thumb")

            # Combine into single archive
            with tarfile.open(file_path, "w:gz") as tar:
                if db_metadata:
                    tar.add(db_metadata.file_path, arcname="database.sql.gz")
                if config_metadata:
                    tar.add(config_metadata.file_path, arcname="config.tar.gz")
                if thumb_metadata:
                    tar.add(thumb_metadata.file_path, arcname="thumbnails.tar.gz")

            # Clean up individual backup files
            for metadata in [db_metadata, config_metadata, thumb_metadata]:
                if metadata and Path(metadata.file_path).exists():
                    Path(metadata.file_path).unlink()

            file_size = file_path.stat().st_size

            return BackupMetadata(
                backup_id=backup_id,
                backup_type=BackupType.FULL,
                timestamp=timestamp,
                file_path=str(file_path),
                file_size=file_size,
                status=BackupStatus.SUCCESS,
            )

        except Exception as e:
            logger.error(f"Full backup failed: {str(e)}")
            if file_path.exists():
                file_path.unlink()
            raise

    def restore_backup(
        self, backup_id: str, backup_type: Optional[BackupType] = None
    ) -> bool:
        """
        Restore from a backup.

        Args:
            backup_id: ID of backup to restore
            backup_type: Type of backup (if None, determined from metadata)

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Starting restore from backup: {backup_id}")

        try:
            # Find backup metadata
            metadata = self._find_backup(backup_id)
            if not metadata:
                logger.error(f"Backup not found: {backup_id}")
                return False

            backup_file = Path(metadata.file_path)
            if not backup_file.exists():
                logger.error(f"Backup file not found: {backup_file}")
                return False

            # Restore based on type
            if metadata.backup_type == BackupType.DATABASE:
                return self._restore_database(backup_file)
            elif metadata.backup_type == BackupType.CONFIGURATION:
                return self._restore_configuration(backup_file)
            elif metadata.backup_type == BackupType.THUMBNAILS:
                return self._restore_thumbnails(backup_file)
            elif metadata.backup_type == BackupType.FULL:
                return self._restore_full(backup_file)

            return False

        except Exception as e:
            logger.error(f"Restore failed: {str(e)}", exc_info=True)
            return False

    def _restore_database(self, backup_file: Path) -> bool:
        """Restore database from backup"""
        try:
            logger.info(f"Restoring database from: {backup_file}")

            # Decompress and restore (password via env var)
            restore_cmd = [
                "mysql",
                f"--host={self.config.DB_HOST}",
                f"--port={self.config.DB_PORT}",
                f"--user={self.config.DB_USER}",
                self.config.DB_NAME,
            ]
            restore_env = {**os.environ, "MYSQL_PWD": self.config.DB_PASSWORD}

            with gzip.open(backup_file, "rb") as gz_file:
                process = subprocess.Popen(
                    restore_cmd,
                    stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=restore_env,
                )
                stdout, stderr = process.communicate(input=gz_file.read())

                if process.returncode != 0:
                    error_msg = stderr.decode("utf-8")
                    logger.error(f"Database restore failed: {error_msg}")
                    return False

            logger.info("Database restored successfully")
            return True

        except Exception as e:
            logger.error(f"Database restore failed: {str(e)}")
            return False

    def _restore_configuration(self, backup_file: Path) -> bool:
        """Restore configuration files from backup"""
        try:
            logger.info(f"Restoring configuration from: {backup_file}")

            with tarfile.open(backup_file, "r:gz") as tar:
                _safe_tar_extract(tar, ".")

            logger.info("Configuration restored successfully")
            return True

        except Exception as e:
            logger.error(f"Configuration restore failed: {str(e)}")
            return False

    def _restore_thumbnails(self, backup_file: Path) -> bool:
        """Restore thumbnails from backup"""
        try:
            logger.info(f"Restoring thumbnails from: {backup_file}")

            thumbnails_path = Path(self.config.THUMBNAILS_PATH or "data/thumbnails")

            with tarfile.open(backup_file, "r:gz") as tar:
                _safe_tar_extract(tar, str(thumbnails_path.parent))

            logger.info("Thumbnails restored successfully")
            return True

        except Exception as e:
            logger.error(f"Thumbnails restore failed: {str(e)}")
            return False

    def _restore_full(self, backup_file: Path) -> bool:
        """Restore full backup"""
        try:
            logger.info(f"Restoring full backup from: {backup_file}")

            # Extract full backup to temp directory
            temp_dir = self.backup_dir / "temp_restore"
            temp_dir.mkdir(exist_ok=True)

            with tarfile.open(backup_file, "r:gz") as tar:
                _safe_tar_extract(tar, str(temp_dir))

            # Restore each component
            success = True
            if (temp_dir / "database.sql.gz").exists():
                success = success and self._restore_database(
                    temp_dir / "database.sql.gz"
                )
            if (temp_dir / "config.tar.gz").exists():
                success = success and self._restore_configuration(
                    temp_dir / "config.tar.gz"
                )
            if (temp_dir / "thumbnails.tar.gz").exists():
                success = success and self._restore_thumbnails(
                    temp_dir / "thumbnails.tar.gz"
                )

            # Cleanup temp directory
            shutil.rmtree(temp_dir)

            logger.info("Full backup restored successfully")
            return success

        except Exception as e:
            logger.error(f"Full backup restore failed: {str(e)}")
            return False

    def list_backups(
        self, backup_type: Optional[BackupType] = None
    ) -> List[BackupMetadata]:
        """List all available backups"""
        metadata_list = self._load_metadata()

        if backup_type:
            return [m for m in metadata_list if m.backup_type == backup_type]

        return metadata_list

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a specific backup"""
        try:
            metadata = self._find_backup(backup_id)
            if not metadata:
                logger.error(f"Backup not found: {backup_id}")
                return False

            # Delete backup file
            backup_file = Path(metadata.file_path)
            if backup_file.exists():
                backup_file.unlink()
                logger.info(f"Deleted backup file: {backup_file}")

            # Remove from metadata
            metadata_list = self._load_metadata()
            metadata_list = [m for m in metadata_list if m.backup_id != backup_id]
            self._save_metadata_list(metadata_list)

            return True

        except Exception as e:
            logger.error(f"Failed to delete backup: {str(e)}")
            return False

    def _generate_backup_id(self, backup_type: BackupType) -> str:
        """Generate unique backup ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{backup_type.value}_{timestamp}"

    def _save_metadata(self, metadata: BackupMetadata):
        """Save backup metadata"""
        metadata_list = self._load_metadata()
        metadata_list.append(metadata)
        self._save_metadata_list(metadata_list)

    def _save_metadata_list(self, metadata_list: List[BackupMetadata]):
        """Save list of backup metadata"""
        data = [m.to_dict() for m in metadata_list]
        with open(self.metadata_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_metadata(self) -> List[BackupMetadata]:
        """Load all backup metadata"""
        if not self.metadata_file.exists():
            return []

        try:
            with open(self.metadata_file, "r") as f:
                data = json.load(f)
            return [BackupMetadata.from_dict(item) for item in data]
        except Exception as e:
            logger.error(f"Failed to load metadata: {str(e)}")
            return []

    def _find_backup(self, backup_id: str) -> Optional[BackupMetadata]:
        """Find backup by ID"""
        metadata_list = self._load_metadata()
        for metadata in metadata_list:
            if metadata.backup_id == backup_id:
                return metadata
        return None

    def _cleanup_old_backups(self, backup_type: BackupType):
        """Remove old backups based on retention policy"""
        metadata_list = self._load_metadata()

        # Filter by type
        type_backups = [m for m in metadata_list if m.backup_type == backup_type]

        # Sort by timestamp (newest first)
        type_backups.sort(key=lambda m: m.timestamp, reverse=True)

        # Remove backups exceeding max count
        if len(type_backups) > self.max_backups:
            for metadata in type_backups[self.max_backups :]:
                logger.info(f"Removing old backup (max count): {metadata.backup_id}")
                self.delete_backup(metadata.backup_id)

        # Remove backups older than retention period
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        for metadata in type_backups:
            if metadata.timestamp < cutoff_date:
                logger.info(f"Removing old backup (expired): {metadata.backup_id}")
                self.delete_backup(metadata.backup_id)


# Global backup service instance
_backup_service: Optional[BackupService] = None


def get_backup_service() -> BackupService:
    """Get global backup service instance"""
    global _backup_service
    if _backup_service is None:
        _backup_service = BackupService()
    return _backup_service
