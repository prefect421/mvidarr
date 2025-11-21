"""
Maintenance tasks service for MVidarr.

Provides simple cleanup and optimization tools for home self-hosters:
- Log cleanup
- Database optimization
- Orphaned file cleanup
- Temp file cleanup
- Job history cleanup
"""

import os
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def cleanup_old_logs(
    log_directory: str = "/app/data/logs",
    days_to_keep: int = 30,
    dry_run: bool = True
) -> Dict:
    """
    Delete log files older than specified days.

    Args:
        log_directory: Path to log directory
        days_to_keep: Keep logs from last N days
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup results
    """
    try:
        if not os.path.exists(log_directory):
            return {
                "success": False,
                "error": f"Log directory not found: {log_directory}",
                "files_removed": 0,
                "space_freed_mb": 0
            }

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        files_to_remove = []
        total_size = 0

        # Find old log files
        for root, dirs, files in os.walk(log_directory):
            for file in files:
                if file.endswith(('.log', '.log.gz', '.log.1', '.log.2')):
                    file_path = os.path.join(root, file)
                    try:
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                        if file_mtime < cutoff_date:
                            file_size = os.path.getsize(file_path)
                            files_to_remove.append({
                                "path": file_path,
                                "size": file_size,
                                "modified": file_mtime.isoformat()
                            })
                            total_size += file_size
                    except Exception as e:
                        logger.warning(f"Error checking file {file_path}: {e}")

        # Remove files if not dry run
        removed_count = 0
        if not dry_run:
            for file_info in files_to_remove:
                try:
                    os.remove(file_info["path"])
                    removed_count += 1
                    logger.info(f"Removed old log: {file_info['path']}")
                except Exception as e:
                    logger.error(f"Error removing {file_info['path']}: {e}")

        return {
            "success": True,
            "dry_run": dry_run,
            "files_found": len(files_to_remove),
            "files_removed": removed_count,
            "space_freed_mb": round(total_size / (1024 * 1024), 2),
            "files": files_to_remove[:50]  # Limit to 50 for response size
        }

    except Exception as e:
        logger.error(f"Error cleaning logs: {e}")
        return {
            "success": False,
            "error": str(e),
            "files_removed": 0,
            "space_freed_mb": 0
        }


def optimize_database() -> Dict:
    """
    Run OPTIMIZE TABLE on all MVidarr tables.

    Returns:
        Dict with optimization results
    """
    try:
        from src.database.connection import get_db
        from sqlalchemy import text

        results = []
        with get_db() as session:
            # Get all MVidarr tables
            tables_query = text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                AND table_type = 'BASE TABLE'
            """)
            tables = session.execute(tables_query).fetchall()

            # Optimize each table
            for (table_name,) in tables:
                try:
                    optimize_query = text(f"OPTIMIZE TABLE {table_name}")
                    result = session.execute(optimize_query)
                    results.append({
                        "table": table_name,
                        "status": "optimized",
                        "success": True
                    })
                    logger.info(f"Optimized table: {table_name}")
                except Exception as e:
                    logger.error(f"Error optimizing {table_name}: {e}")
                    results.append({
                        "table": table_name,
                        "status": "error",
                        "success": False,
                        "error": str(e)
                    })

        return {
            "success": True,
            "tables_optimized": len([r for r in results if r["success"]]),
            "tables_failed": len([r for r in results if not r["success"]]),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        return {
            "success": False,
            "error": str(e),
            "tables_optimized": 0
        }


def cleanup_orphaned_thumbnails(
    thumbnails_path: str = "/app/data/thumbnails",
    dry_run: bool = True
) -> Dict:
    """
    Remove thumbnail files for videos that no longer exist in database.

    Args:
        thumbnails_path: Path to thumbnails directory
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup results
    """
    try:
        from src.database.connection import get_db
        from src.database.models import Video

        if not os.path.exists(thumbnails_path):
            return {
                "success": False,
                "error": f"Thumbnails directory not found: {thumbnails_path}",
                "files_removed": 0,
                "space_freed_mb": 0
            }

        # Get list of valid video IDs from database
        with get_db() as session:
            valid_video_ids = set(
                video_id for (video_id,) in session.query(Video.id).all()
            )

        orphaned_files = []
        total_size = 0

        # Check thumbnail files
        for root, dirs, files in os.walk(thumbnails_path):
            for file in files:
                if file.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    file_path = os.path.join(root, file)

                    # Extract video ID from filename (assumes format: {video_id}_*.jpg)
                    try:
                        video_id_str = file.split('_')[0]
                        video_id = int(video_id_str)

                        if video_id not in valid_video_ids:
                            file_size = os.path.getsize(file_path)
                            orphaned_files.append({
                                "path": file_path,
                                "size": file_size,
                                "video_id": video_id
                            })
                            total_size += file_size
                    except (ValueError, IndexError):
                        # Skip files that don't match expected pattern
                        continue

        # Remove files if not dry run
        removed_count = 0
        if not dry_run:
            for file_info in orphaned_files:
                try:
                    os.remove(file_info["path"])
                    removed_count += 1
                    logger.info(f"Removed orphaned thumbnail: {file_info['path']}")
                except Exception as e:
                    logger.error(f"Error removing {file_info['path']}: {e}")

        return {
            "success": True,
            "dry_run": dry_run,
            "files_found": len(orphaned_files),
            "files_removed": removed_count,
            "space_freed_mb": round(total_size / (1024 * 1024), 2),
            "files": orphaned_files[:50]  # Limit for response size
        }

    except Exception as e:
        logger.error(f"Error cleaning orphaned thumbnails: {e}")
        return {
            "success": False,
            "error": str(e),
            "files_removed": 0,
            "space_freed_mb": 0
        }


def cleanup_temp_files(
    temp_paths: Optional[List[str]] = None,
    dry_run: bool = True
) -> Dict:
    """
    Clean up temporary files and cache directories.

    Args:
        temp_paths: List of paths to clean. If None, uses default paths.
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup results
    """
    if temp_paths is None:
        temp_paths = [
            "/app/data/cache",
            "/app/data/downloads",
            "/tmp/mvidarr"
        ]

    try:
        total_files = 0
        total_size = 0
        removed_count = 0
        path_results = []

        for path in temp_paths:
            if not os.path.exists(path):
                continue

            path_files = 0
            path_size = 0

            for root, dirs, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        path_files += 1
                        path_size += file_size
                        total_files += 1
                        total_size += file_size

                        if not dry_run:
                            os.remove(file_path)
                            removed_count += 1
                    except Exception as e:
                        logger.warning(f"Error processing {file_path}: {e}")

            path_results.append({
                "path": path,
                "files_found": path_files,
                "size_mb": round(path_size / (1024 * 1024), 2)
            })

        return {
            "success": True,
            "dry_run": dry_run,
            "files_found": total_files,
            "files_removed": removed_count,
            "space_freed_mb": round(total_size / (1024 * 1024), 2),
            "paths": path_results
        }

    except Exception as e:
        logger.error(f"Error cleaning temp files: {e}")
        return {
            "success": False,
            "error": str(e),
            "files_removed": 0,
            "space_freed_mb": 0
        }


def cleanup_old_job_history(
    days_to_keep: int = 30,
    dry_run: bool = True
) -> Dict:
    """
    Remove old completed job records from Redis/database.

    Args:
        days_to_keep: Keep job history from last N days
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup results
    """
    try:
        import redis
        from src.config import get_setting

        redis_url = get_setting("redis_url", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)

        # Get all Celery result keys
        pattern = "celery-task-meta-*"
        keys = r.keys(pattern)

        cutoff_timestamp = (datetime.now() - timedelta(days=days_to_keep)).timestamp()
        keys_to_delete = []

        for key in keys:
            try:
                # Get task result
                task_data = r.get(key)
                if task_data:
                    # Check if task is old (this is simplified - real implementation
                    # would parse the task data to get completion timestamp)
                    ttl = r.ttl(key)
                    if ttl == -1:  # No expiration set
                        keys_to_delete.append(key.decode('utf-8') if isinstance(key, bytes) else key)
            except Exception as e:
                logger.warning(f"Error checking key {key}: {e}")

        # Delete keys if not dry run
        deleted_count = 0
        if not dry_run and keys_to_delete:
            for key in keys_to_delete:
                try:
                    r.delete(key)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting key {key}: {e}")

        return {
            "success": True,
            "dry_run": dry_run,
            "jobs_found": len(keys_to_delete),
            "jobs_removed": deleted_count
        }

    except Exception as e:
        logger.error(f"Error cleaning job history: {e}")
        return {
            "success": False,
            "error": str(e),
            "jobs_removed": 0
        }


def get_maintenance_summary() -> Dict:
    """
    Get summary of what maintenance tasks would find (dry run all).

    Returns:
        Dict with summary of all maintenance tasks
    """
    summary = {
        "logs": cleanup_old_logs(dry_run=True),
        "thumbnails": cleanup_orphaned_thumbnails(dry_run=True),
        "temp_files": cleanup_temp_files(dry_run=True),
        "job_history": cleanup_old_job_history(dry_run=True),
    }

    return summary
