"""
Collection Optimization Background Jobs - Phase 3 Week 28
Consumer-focused background tasks for music video collection management
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.jobs.base_task import BaseTask
from src.services.collection_organizer import (
    OrganizationRule,
    OrganizationStrategy,
    get_collection_organizer,
)
from src.services.duplicate_manager import DuplicateConfidence, get_duplicate_manager
from src.services.music_video_detector import get_music_video_detector
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.collection_optimization")

# Celery app instance (would be configured in main app)
# celery_app = Celery('mvidarr')


class CollectionOptimizationTask(BaseTask):
    """Base class for collection optimization tasks"""

    def __init__(self):
        super().__init__()
        self.task_type = "collection_optimization"


# Background Music Video Detection Tasks


class BatchMusicVideoDetectionTask(CollectionOptimizationTask):
    """Background task for batch music video detection"""

    async def execute(
        self, directory_path: str, options: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Execute batch music video detection"""
        try:
            options = options or {}
            scan_subdirs = options.get("scan_subdirs", True)
            min_confidence = options.get("min_confidence", "medium")
            update_database = options.get("update_database", True)

            logger.info(f"Starting batch music video detection for {directory_path}")

            # Update progress
            await self.update_progress(5, "Initializing music video detector")
            detector = await get_music_video_detector()

            # Find video files
            await self.update_progress(10, "Scanning for video files")
            video_files = await self._find_video_files(directory_path, scan_subdirs)

            if not video_files:
                return {
                    "success": True,
                    "message": "No video files found",
                    "directory": directory_path,
                    "files_processed": 0,
                    "music_videos_detected": 0,
                }

            # Process videos in batches
            batch_size = options.get("batch_size", 20)
            total_files = len(video_files)
            music_videos_detected = 0
            detection_results = []

            for i in range(0, total_files, batch_size):
                batch = video_files[i : i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_files + batch_size - 1) // batch_size

                await self.update_progress(
                    10 + (80 * i // total_files),
                    f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)",
                )

                # Detect music videos in batch
                batch_results = await detector.batch_detect_music_videos(batch)
                detection_results.extend(batch_results)

                # Count music videos found
                batch_music_videos = sum(1 for r in batch_results if r.is_music_video)
                music_videos_detected += batch_music_videos

                logger.info(
                    f"Batch {batch_num}/{total_batches}: {batch_music_videos} music videos found"
                )

                # Update database if requested
                if update_database:
                    await self._update_database_with_detections(batch_results)

                # Small delay between batches to prevent overwhelming system
                if i + batch_size < total_files:
                    await asyncio.sleep(1)

            await self.update_progress(95, "Finalizing results")

            # Cache results for potential organization use
            cache_key = f"detection_results:{directory_path.replace('/', '_')}"
            redis_client = await get_redis_client()
            await redis_client.setex(
                cache_key,
                3600,  # 1 hour
                json.dumps([r.to_dict() for r in detection_results]),
            )

            result = {
                "success": True,
                "message": f"Detection completed: {music_videos_detected} music videos found",
                "directory": directory_path,
                "files_processed": total_files,
                "music_videos_detected": music_videos_detected,
                "detection_summary": {
                    "very_high_confidence": sum(
                        1
                        for r in detection_results
                        if r.is_music_video and r.confidence.value == "very_high"
                    ),
                    "high_confidence": sum(
                        1
                        for r in detection_results
                        if r.is_music_video and r.confidence.value == "high"
                    ),
                    "medium_confidence": sum(
                        1
                        for r in detection_results
                        if r.is_music_video and r.confidence.value == "medium"
                    ),
                    "low_confidence": sum(
                        1
                        for r in detection_results
                        if r.is_music_video and r.confidence.value == "low"
                    ),
                },
                "cache_key": cache_key,
            }

            await self.update_progress(100, "Detection task completed")
            logger.info(
                f"Batch detection completed: {music_videos_detected} music videos detected from {total_files} files"
            )

            return result

        except Exception as e:
            error_msg = f"Batch detection failed: {e}"
            logger.error(error_msg)
            await self.update_progress(-1, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "files_processed": 0,
                "music_videos_detected": 0,
            }

    async def _find_video_files(self, directory: str, scan_subdirs: bool) -> List[str]:
        """Find all video files in directory"""
        from pathlib import Path

        video_extensions = {
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }
        video_files = []

        try:
            directory_path = Path(directory)
            pattern = "**/*" if scan_subdirs else "*"

            for file_path in directory_path.glob(pattern):
                if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                    video_files.append(str(file_path))

        except Exception as e:
            logger.error(f"Failed to find video files: {e}")

        return sorted(video_files)

    async def _update_database_with_detections(self, detection_results):
        """Update database with detection results"""
        try:
            # This would update the video database with detection results
            # For now, just log the action
            music_videos = [r for r in detection_results if r.is_music_video]
            logger.info(
                f"Would update database with {len(music_videos)} music video detections"
            )

        except Exception as e:
            logger.warning(f"Failed to update database with detections: {e}")


class CollectionOrganizationTask(CollectionOptimizationTask):
    """Background task for collection organization"""

    async def execute(
        self,
        source_directory: str,
        target_directory: str,
        options: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Execute collection organization"""
        try:
            options = options or {}

            logger.info(
                f"Starting collection organization: {source_directory} -> {target_directory}"
            )

            await self.update_progress(5, "Initializing collection organizer")
            organizer = await get_collection_organizer()

            # Create organization rules from options
            rules = OrganizationRule()

            strategy_map = {
                "artist_title": OrganizationStrategy.ARTIST_TITLE,
                "artist_album_title": OrganizationStrategy.ARTIST_ALBUM_TITLE,
                "genre_artist": OrganizationStrategy.GENRE_ARTIST,
                "year_artist": OrganizationStrategy.YEAR_ARTIST,
                "flat_artist_title": OrganizationStrategy.FLAT_ARTIST_TITLE,
                "custom": OrganizationStrategy.CUSTOM,
            }

            rules.strategy = strategy_map.get(
                options.get("strategy", "artist_title"),
                OrganizationStrategy.ARTIST_TITLE,
            )
            rules.clean_filenames = options.get("clean_filenames", True)
            rules.preserve_quality_info = options.get("preserve_quality_info", True)
            rules.group_versions = options.get("group_versions", True)
            rules.handle_duplicates = options.get("handle_duplicates", True)
            rules.create_artist_folders = options.get("create_artist_folders", True)

            # Create organization plan
            await self.update_progress(15, "Creating organization plan")
            plan = await organizer.create_organization_plan(
                source_directory, target_directory, rules
            )

            if not plan.organization_actions:
                return {
                    "success": True,
                    "message": "No music videos found to organize",
                    "source_directory": source_directory,
                    "target_directory": target_directory,
                    "files_processed": 0,
                    "files_organized": 0,
                }

            # Execute organization plan
            await self.update_progress(
                20, f"Organizing {len(plan.organization_actions)} music videos"
            )

            async def progress_callback(current, total, action):
                progress = 20 + (70 * current // total)
                file_name = os.path.basename(action.get("source_path", "unknown"))
                await self.update_progress(progress, f"Organizing: {file_name}")

            result = await organizer.execute_organization_plan(
                plan,
                dry_run=options.get("dry_run", False),
                progress_callback=progress_callback,
            )

            await self.update_progress(95, "Finalizing organization")

            response = {
                "success": result.success,
                "message": f"Organization completed: {result.files_processed} files processed",
                "source_directory": source_directory,
                "target_directory": target_directory,
                "files_processed": result.files_processed,
                "files_moved": result.files_moved,
                "files_renamed": result.files_renamed,
                "folders_created": result.folders_created,
                "errors": result.errors,
                "warnings": result.warnings,
                "dry_run": options.get("dry_run", False),
                "organization_summary": result.organization_summary,
            }

            await self.update_progress(100, "Organization task completed")
            logger.info(
                f"Collection organization completed: {result.files_processed} files processed"
            )

            return response

        except Exception as e:
            error_msg = f"Collection organization failed: {e}"
            logger.error(error_msg)
            await self.update_progress(-1, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "files_processed": 0,
                "files_organized": 0,
            }


class DuplicateDetectionTask(CollectionOptimizationTask):
    """Background task for duplicate detection"""

    async def execute(
        self, directory_path: str, options: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Execute duplicate detection"""
        try:
            options = options or {}
            scan_subdirs = options.get("scan_subdirs", True)
            min_confidence = options.get("min_confidence", "medium")

            logger.info(f"Starting duplicate detection for {directory_path}")

            await self.update_progress(5, "Initializing duplicate manager")
            duplicate_manager = await get_duplicate_manager()

            # Map confidence string to enum
            confidence_map = {
                "very_low": DuplicateConfidence.VERY_LOW,
                "low": DuplicateConfidence.LOW,
                "medium": DuplicateConfidence.MEDIUM,
                "high": DuplicateConfidence.HIGH,
                "very_high": DuplicateConfidence.VERY_HIGH,
            }

            confidence_level = confidence_map.get(
                min_confidence, DuplicateConfidence.MEDIUM
            )

            # Progress callback for duplicate scanning
            async def progress_callback(current, total, message):
                progress = 10 + (80 * current // total) if total > 0 else 50
                await self.update_progress(progress, message)

            # Perform duplicate scan
            await self.update_progress(10, "Scanning for duplicates")
            scan_result = await duplicate_manager.scan_for_duplicates(
                directory_path, scan_subdirs, confidence_level, progress_callback
            )

            await self.update_progress(95, "Finalizing duplicate detection")

            # Cache results for potential removal
            cache_key = f"duplicate_results:{directory_path.replace('/', '_')}"
            redis_client = await get_redis_client()
            await redis_client.setex(
                cache_key, 3600, json.dumps(scan_result.to_dict())  # 1 hour
            )

            result = {
                "success": True,
                "message": f"Duplicate detection completed: {scan_result.duplicate_groups_found} groups found",
                "directory": directory_path,
                "files_scanned": scan_result.total_files_scanned,
                "duplicate_groups_found": scan_result.duplicate_groups_found,
                "total_duplicates": scan_result.total_duplicates,
                "potential_space_savings": scan_result.potential_space_savings,
                "potential_space_savings_mb": scan_result.potential_space_savings
                / (1024 * 1024),
                "scan_time_seconds": scan_result.scan_time_seconds,
                "confidence_summary": {
                    "very_high": len(
                        scan_result.get_groups_by_confidence(
                            DuplicateConfidence.VERY_HIGH
                        )
                    ),
                    "high": len(
                        scan_result.get_groups_by_confidence(DuplicateConfidence.HIGH)
                    ),
                    "medium": len(
                        scan_result.get_groups_by_confidence(DuplicateConfidence.MEDIUM)
                    ),
                    "low": len(
                        scan_result.get_groups_by_confidence(DuplicateConfidence.LOW)
                    ),
                },
                "cache_key": cache_key,
            }

            await self.update_progress(100, "Duplicate detection completed")
            logger.info(
                f"Duplicate detection completed: {scan_result.duplicate_groups_found} groups, "
                f"{scan_result.potential_space_savings / (1024*1024):.1f} MB potential savings"
            )

            return result

        except Exception as e:
            error_msg = f"Duplicate detection failed: {e}"
            logger.error(error_msg)
            await self.update_progress(-1, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "files_scanned": 0,
                "duplicates_found": 0,
            }


class CollectionHealthCheckTask(CollectionOptimizationTask):
    """Background task for collection health assessment"""

    async def execute(
        self, directory_path: str, options: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Execute collection health check"""
        try:
            options = options or {}

            logger.info(f"Starting collection health check for {directory_path}")

            await self.update_progress(5, "Initializing health check")

            health_report = {
                "directory": directory_path,
                "timestamp": datetime.now().isoformat(),
                "overall_score": 0.0,
                "issues_found": [],
                "recommendations": [],
                "statistics": {},
            }

            # Analyze directory structure
            await self.update_progress(20, "Analyzing directory structure")
            structure_analysis = await self._analyze_directory_structure(directory_path)
            health_report["statistics"]["structure"] = structure_analysis

            # Check for organization issues
            await self.update_progress(40, "Checking organization quality")
            organization_issues = await self._check_organization_issues(
                directory_path, structure_analysis
            )
            health_report["issues_found"].extend(organization_issues)

            # Check for metadata issues
            await self.update_progress(60, "Checking metadata quality")
            metadata_issues = await self._check_metadata_issues(directory_path)
            health_report["issues_found"].extend(metadata_issues)

            # Check for quality issues
            await self.update_progress(80, "Checking file quality")
            quality_issues = await self._check_quality_issues(directory_path)
            health_report["issues_found"].extend(quality_issues)

            # Generate recommendations
            await self.update_progress(90, "Generating recommendations")
            recommendations = await self._generate_health_recommendations(health_report)
            health_report["recommendations"] = recommendations

            # Calculate overall health score
            health_report["overall_score"] = await self._calculate_health_score(
                health_report
            )

            await self.update_progress(100, "Health check completed")

            result = {
                "success": True,
                "message": f'Health check completed: {health_report["overall_score"]:.1f}/100 score',
                "health_report": health_report,
                "summary": {
                    "overall_score": health_report["overall_score"],
                    "issues_count": len(health_report["issues_found"]),
                    "recommendations_count": len(health_report["recommendations"]),
                },
            }

            logger.info(
                f"Collection health check completed: {health_report['overall_score']:.1f}/100 score"
            )

            return result

        except Exception as e:
            error_msg = f"Collection health check failed: {e}"
            logger.error(error_msg)
            await self.update_progress(-1, error_msg)
            return {"success": False, "error": error_msg, "health_score": 0.0}

    async def _analyze_directory_structure(self, directory: str) -> Dict[str, Any]:
        """Analyze directory structure for organization patterns"""
        import collections
        from pathlib import Path

        structure = {
            "total_files": 0,
            "video_files": 0,
            "folder_count": 0,
            "max_depth": 0,
            "file_extensions": collections.defaultdict(int),
            "folder_patterns": [],
            "organization_type": "unknown",
        }

        try:
            directory_path = Path(directory)
            video_extensions = {
                ".mp4",
                ".avi",
                ".mkv",
                ".mov",
                ".wmv",
                ".flv",
                ".webm",
                ".m4v",
            }

            # Analyze directory structure
            for item in directory_path.rglob("*"):
                depth = len(item.relative_to(directory_path).parts)
                structure["max_depth"] = max(structure["max_depth"], depth)

                if item.is_file():
                    structure["total_files"] += 1
                    ext = item.suffix.lower()
                    structure["file_extensions"][ext] += 1

                    if ext in video_extensions:
                        structure["video_files"] += 1

                elif item.is_dir() and item != directory_path:
                    structure["folder_count"] += 1

            # Detect organization patterns
            if structure["folder_count"] > 0:
                # Check for artist-based organization
                artist_folders = 0
                for item in directory_path.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        # Simple heuristic: folders with reasonable names
                        if len(item.name) > 2 and not any(
                            char.isdigit() for char in item.name[:4]
                        ):
                            artist_folders += 1

                if artist_folders > structure["folder_count"] * 0.7:
                    structure["organization_type"] = "artist_based"
                elif structure["max_depth"] <= 1:
                    structure["organization_type"] = "flat"
                else:
                    structure["organization_type"] = "hierarchical"

        except Exception as e:
            logger.error(f"Failed to analyze directory structure: {e}")

        return structure

    async def _check_organization_issues(
        self, directory: str, structure: Dict
    ) -> List[Dict]:
        """Check for organization issues"""
        issues = []

        # Check for poor organization
        if (
            structure["organization_type"] == "unknown"
            and structure["video_files"] > 20
        ):
            issues.append(
                {
                    "type": "poor_organization",
                    "severity": "medium",
                    "message": f"Collection with {structure['video_files']} videos lacks clear organization",
                    "suggestion": "Consider organizing videos by artist or genre",
                }
            )

        # Check for excessive depth
        if structure["max_depth"] > 4:
            issues.append(
                {
                    "type": "excessive_depth",
                    "severity": "low",
                    "message": f"Directory structure is {structure['max_depth']} levels deep",
                    "suggestion": "Consider flattening directory structure for easier navigation",
                }
            )

        # Check for mixed content
        video_ratio = structure["video_files"] / max(structure["total_files"], 1)
        if video_ratio < 0.8 and structure["total_files"] > 50:
            issues.append(
                {
                    "type": "mixed_content",
                    "severity": "low",
                    "message": f"Only {video_ratio*100:.1f}% of files are videos",
                    "suggestion": "Consider separating video files from other content",
                }
            )

        return issues

    async def _check_metadata_issues(self, directory: str) -> List[Dict]:
        """Check for metadata-related issues"""
        issues = []

        # This would check for missing metadata, inconsistent naming, etc.
        # For now, return placeholder issues

        return issues

    async def _check_quality_issues(self, directory: str) -> List[Dict]:
        """Check for quality-related issues"""
        issues = []

        # This would check for low-quality videos, corruption, etc.
        # For now, return placeholder issues

        return issues

    async def _generate_health_recommendations(self, health_report: Dict) -> List[Dict]:
        """Generate recommendations based on health analysis"""
        recommendations = []

        issues_by_type = {}
        for issue in health_report["issues_found"]:
            issue_type = issue["type"]
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)

        # Generate recommendations based on issues
        if "poor_organization" in issues_by_type:
            recommendations.append(
                {
                    "action": "organize_collection",
                    "priority": "high",
                    "description": "Organize collection by artist and title",
                    "estimated_time": "moderate",
                    "benefits": [
                        "Easier navigation",
                        "Better file management",
                        "Improved search",
                    ],
                }
            )

        if "mixed_content" in issues_by_type:
            recommendations.append(
                {
                    "action": "separate_content",
                    "priority": "medium",
                    "description": "Separate video files from other content types",
                    "estimated_time": "low",
                    "benefits": ["Cleaner organization", "Faster processing"],
                }
            )

        # Always recommend duplicate detection for large collections
        video_count = health_report["statistics"]["structure"]["video_files"]
        if video_count > 50:
            recommendations.append(
                {
                    "action": "scan_duplicates",
                    "priority": "medium",
                    "description": "Scan for duplicate videos to save space",
                    "estimated_time": "moderate",
                    "benefits": ["Free up disk space", "Remove clutter"],
                }
            )

        return recommendations

    async def _calculate_health_score(self, health_report: Dict) -> float:
        """Calculate overall health score (0-100)"""
        base_score = 100.0

        # Deduct points for issues
        for issue in health_report["issues_found"]:
            severity = issue.get("severity", "low")
            if severity == "critical":
                base_score -= 15
            elif severity == "high":
                base_score -= 10
            elif severity == "medium":
                base_score -= 5
            elif severity == "low":
                base_score -= 2

        # Bonus for good organization
        structure = health_report["statistics"]["structure"]
        if structure["organization_type"] == "artist_based":
            base_score += 10
        elif structure["organization_type"] != "unknown":
            base_score += 5

        return max(0.0, min(100.0, base_score))


# Collection Optimization Scheduler


class CollectionOptimizationScheduler:
    """Scheduler for periodic collection optimization tasks"""

    def __init__(self):
        self.redis_client = None
        self.scheduled_tasks = {}

    async def initialize(self):
        """Initialize scheduler"""
        self.redis_client = await get_redis_client()

    async def schedule_periodic_optimization(
        self, directory: str, schedule_options: Dict
    ):
        """Schedule periodic collection optimization"""
        try:
            schedule_id = f"schedule_{directory.replace('/', '_')}"

            # Store schedule in Redis
            schedule_data = {
                "directory": directory,
                "options": schedule_options,
                "created_at": datetime.now().isoformat(),
                "last_run": None,
                "next_run": None,
            }

            await self.redis_client.setex(
                f"collection_schedule:{schedule_id}",
                86400 * 7,  # 1 week
                json.dumps(schedule_data),
            )

            logger.info(f"Scheduled periodic optimization for {directory}")

            return {
                "schedule_id": schedule_id,
                "status": "scheduled",
                "directory": directory,
            }

        except Exception as e:
            logger.error(f"Failed to schedule periodic optimization: {e}")
            raise

    async def run_scheduled_optimizations(self):
        """Run scheduled optimization tasks"""
        try:
            # This would be called by a periodic scheduler (cron job, celery beat, etc.)
            logger.info("Running scheduled collection optimizations")

            # Get all scheduled tasks from Redis
            pattern = "collection_schedule:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys:
                try:
                    schedule_data = json.loads(await self.redis_client.get(key))

                    # Check if task should run based on schedule
                    if await self._should_run_optimization(schedule_data):
                        await self._execute_scheduled_optimization(schedule_data)

                        # Update last run time
                        schedule_data["last_run"] = datetime.now().isoformat()
                        await self.redis_client.setex(
                            key, 86400 * 7, json.dumps(schedule_data)
                        )

                except Exception as e:
                    logger.error(f"Failed to process scheduled task {key}: {e}")

        except Exception as e:
            logger.error(f"Failed to run scheduled optimizations: {e}")

    async def _should_run_optimization(self, schedule_data: Dict) -> bool:
        """Check if optimization should run based on schedule"""
        # Simple implementation - run daily if no last_run or last run was >24h ago
        if not schedule_data.get("last_run"):
            return True

        try:
            last_run = datetime.fromisoformat(schedule_data["last_run"])
            return datetime.now() - last_run > timedelta(hours=24)
        except:
            return True

    async def _execute_scheduled_optimization(self, schedule_data: Dict):
        """Execute a scheduled optimization task"""
        try:
            directory = schedule_data["directory"]
            options = schedule_data.get("options", {})

            logger.info(f"Executing scheduled optimization for {directory}")

            # Run health check
            if options.get("health_check", True):
                health_task = CollectionHealthCheckTask()
                await health_task.execute(directory)

            # Run duplicate detection if requested
            if options.get("duplicate_detection", False):
                duplicate_task = DuplicateDetectionTask()
                await duplicate_task.execute(
                    directory,
                    {"min_confidence": options.get("duplicate_confidence", "medium")},
                )

            logger.info(f"Completed scheduled optimization for {directory}")

        except Exception as e:
            logger.error(f"Failed to execute scheduled optimization: {e}")


# Global scheduler instance
_collection_scheduler = None


async def get_collection_scheduler():
    """Get global collection optimization scheduler"""
    global _collection_scheduler

    if _collection_scheduler is None:
        _collection_scheduler = CollectionOptimizationScheduler()
        await _collection_scheduler.initialize()

    return _collection_scheduler
