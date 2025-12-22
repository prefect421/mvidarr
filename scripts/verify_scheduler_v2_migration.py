#!/usr/bin/env python3
"""
Verify Scheduler V2 Migration Script
Version: v0.10.1
Phase 6: Migration & Cleanup

This script verifies that Scheduler V2 migration was successful by:
1. Checking all artists have valid scheduling settings
2. Checking for missing data
3. Validating foreign key relationships
4. Generating verification report

Usage:
    python scripts/verify_scheduler_v2_migration.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect

from src.database.connection import get_db
from src.database.models import Artist, Download, ScheduledJob
from src.utils.logger import get_logger

logger = get_logger("mvidarr.verification")


class SchedulerV2Verification:
    """Verifies Scheduler V2 migration"""

    def __init__(self):
        self.results = {
            "schema_ok": False,
            "artists_valid": 0,
            "artists_invalid": 0,
            "downloads_valid": 0,
            "scheduled_jobs_count": 0,
            "issues": [],
        }

    def run(self):
        """Execute verification"""
        logger.info("=" * 60)
        logger.info("Scheduler V2 Migration Verification")
        logger.info("Version: v0.10.1")
        logger.info("=" * 60)
        logger.info("")

        try:
            # Check database schema
            logger.info("Step 1: Verifying database schema...")
            if not self.verify_schema():
                logger.error("❌ Schema verification failed")
                self.print_report()
                return False

            # Verify artist data
            logger.info("\nStep 2: Verifying artist data...")
            self.verify_artists()

            # Verify download data
            logger.info("\nStep 3: Verifying download data...")
            self.verify_downloads()

            # Check scheduled jobs
            logger.info("\nStep 4: Checking scheduled jobs...")
            self.check_scheduled_jobs()

            # Generate report
            logger.info("\n" + "=" * 60)
            self.print_report()
            logger.info("=" * 60)

            if self.results["issues"]:
                logger.warning(
                    f"\n⚠️  Verification completed with {len(self.results['issues'])} issues"
                )
                return False
            else:
                logger.info("\n✅ Verification passed - Migration successful!")
                return True

        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            return False

    def verify_schema(self):
        """Verify database schema has all required tables and columns"""
        try:
            with get_db() as db:
                inspector = inspect(db.get_bind())
                tables = inspector.get_table_names()

                # Check for required tables
                required_tables = ["artists", "downloads", "scheduled_jobs"]

                for table in required_tables:
                    if table not in tables:
                        self.results["issues"].append(
                            f"Missing required table: {table}"
                        )
                        logger.error(f"  ✗ Missing table: {table}")
                        return False

                # Check artist table columns
                artist_columns = [
                    col["name"] for col in inspector.get_columns("artists")
                ]

                required_artist_fields = [
                    "discovery_interval_hours",
                    "last_discovery",
                    "last_download",
                    "discovery_enabled",
                    "download_enabled",
                    "max_videos_per_discovery",
                    "schedule_priority",
                ]

                missing_fields = [
                    field
                    for field in required_artist_fields
                    if field not in artist_columns
                ]

                if missing_fields:
                    for field in missing_fields:
                        self.results["issues"].append(f"Missing artist field: {field}")
                        logger.error(f"  ✗ Missing artist field: {field}")
                    return False

                # Check scheduled_jobs table columns
                job_columns = [
                    col["name"] for col in inspector.get_columns("scheduled_jobs")
                ]

                required_job_fields = [
                    "id",
                    "job_type",
                    "artist_id",
                    "status",
                    "celery_task_id",
                    "retry_count",
                    "max_retries",
                ]

                missing_job_fields = [
                    field for field in required_job_fields if field not in job_columns
                ]

                if missing_job_fields:
                    for field in missing_job_fields:
                        self.results["issues"].append(
                            f"Missing scheduled_jobs field: {field}"
                        )
                        logger.error(f"  ✗ Missing scheduled_jobs field: {field}")
                    return False

                logger.info("  ✓ Database schema valid")
                self.results["schema_ok"] = True
                return True

        except Exception as e:
            self.results["issues"].append(f"Schema verification error: {e}")
            logger.error(f"  ✗ Schema verification error: {e}")
            return False

    def verify_artists(self):
        """Verify all artists have valid scheduling settings"""
        try:
            with get_db() as db:
                artists = db.query(Artist).all()
                logger.info(f"  Checking {len(artists)} artists...")

                for artist in artists:
                    issues = []

                    # Check discovery_enabled
                    if not hasattr(artist, "discovery_enabled"):
                        issues.append("missing discovery_enabled")
                    elif artist.discovery_enabled is None:
                        issues.append("discovery_enabled is None")

                    # Check download_enabled
                    if not hasattr(artist, "download_enabled"):
                        issues.append("missing download_enabled")
                    elif artist.download_enabled is None:
                        issues.append("download_enabled is None")

                    # Check schedule_priority
                    if not hasattr(artist, "schedule_priority"):
                        issues.append("missing schedule_priority")
                    elif not artist.schedule_priority:
                        issues.append("schedule_priority is empty")
                    elif artist.schedule_priority not in ["high", "medium", "low"]:
                        issues.append(
                            f"invalid schedule_priority: {artist.schedule_priority}"
                        )

                    # Check discovery_interval_hours (optional, but must be valid if set)
                    if (
                        hasattr(artist, "discovery_interval_hours")
                        and artist.discovery_interval_hours is not None
                    ):
                        if (
                            not isinstance(artist.discovery_interval_hours, int)
                            or artist.discovery_interval_hours < 1
                        ):
                            issues.append(
                                f"invalid discovery_interval_hours: {artist.discovery_interval_hours}"
                            )

                    if issues:
                        self.results["artists_invalid"] += 1
                        issue_msg = (
                            f"Artist {artist.id} ({artist.name}): {', '.join(issues)}"
                        )
                        self.results["issues"].append(issue_msg)
                        logger.warning(f"  ⚠️  {issue_msg}")
                    else:
                        self.results["artists_valid"] += 1

                logger.info(
                    f"  ✓ Valid artists: {self.results['artists_valid']}/{len(artists)}"
                )

                if self.results["artists_invalid"] > 0:
                    logger.warning(
                        f"  ⚠️  Invalid artists: {self.results['artists_invalid']}"
                    )

        except Exception as e:
            self.results["issues"].append(f"Artist verification error: {e}")
            logger.error(f"  ✗ Artist verification error: {e}")

    def verify_downloads(self):
        """Verify download records have valid retry fields"""
        try:
            with get_db() as db:
                # Check if downloads table has retry fields
                inspector = inspect(db.get_bind())
                download_columns = [
                    col["name"] for col in inspector.get_columns("downloads")
                ]

                has_retry_fields = "retry_count" in download_columns

                if not has_retry_fields:
                    logger.warning(
                        "  ⚠️  Download retry fields not found (optional feature)"
                    )
                    return

                downloads = db.query(Download).all()
                logger.info(f"  Checking {len(downloads)} downloads...")

                valid_count = 0
                for download in downloads:
                    if hasattr(download, "retry_count"):
                        if download.retry_count is None:
                            self.results["issues"].append(
                                f"Download {download.id} has None retry_count"
                            )
                        else:
                            valid_count += 1

                self.results["downloads_valid"] = valid_count
                logger.info(f"  ✓ Valid downloads: {valid_count}/{len(downloads)}")

        except Exception as e:
            # Non-critical error
            logger.warning(f"  ⚠️  Download verification error: {e}")

    def check_scheduled_jobs(self):
        """Check scheduled jobs table"""
        try:
            with get_db() as db:
                job_count = db.query(ScheduledJob).count()
                self.results["scheduled_jobs_count"] = job_count
                logger.info(f"  Found {job_count} scheduled job records")

                if job_count > 0:
                    # Check for any orphaned jobs (artist_id set but artist doesn't exist)
                    orphaned = (
                        db.query(ScheduledJob)
                        .filter(ScheduledJob.artist_id.isnot(None))
                        .outerjoin(Artist, ScheduledJob.artist_id == Artist.id)
                        .filter(Artist.id == None)
                        .count()
                    )

                    if orphaned > 0:
                        self.results["issues"].append(
                            f"{orphaned} orphaned scheduled jobs (artist_id references non-existent artists)"
                        )
                        logger.warning(f"  ⚠️  Found {orphaned} orphaned scheduled jobs")
                    else:
                        logger.info("  ✓ No orphaned scheduled jobs")

        except Exception as e:
            self.results["issues"].append(f"Scheduled jobs check error: {e}")
            logger.error(f"  ✗ Scheduled jobs check error: {e}")

    def print_report(self):
        """Print verification report"""
        logger.info("Verification Report")
        logger.info("-" * 60)
        logger.info(
            f"Schema valid:          {'Yes' if self.results['schema_ok'] else 'No'}"
        )
        logger.info(f"Artists valid:         {self.results['artists_valid']}")
        logger.info(f"Artists invalid:       {self.results['artists_invalid']}")
        logger.info(f"Downloads valid:       {self.results['downloads_valid']}")
        logger.info(f"Scheduled jobs:        {self.results['scheduled_jobs_count']}")
        logger.info(f"Issues found:          {len(self.results['issues'])}")

        if self.results["issues"]:
            logger.info("\nIssues:")
            for issue in self.results["issues"]:
                logger.info(f"  - {issue}")
            logger.info("\nRecommendation:")
            logger.info("  Run migration script to fix issues:")
            logger.info("  python scripts/migrate_to_scheduler_v2.py")


def main():
    """Main entry point"""
    verification = SchedulerV2Verification()
    success = verification.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
