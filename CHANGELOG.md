# Changelog

All notable changes to MVidarr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.11.8] - 2026-02-04

### Fixed - Thumbnail System Overhaul
- **Manual Thumbnail Setting**: Fixed artist thumbnail setting failing silently - frontend now displays actual API error messages
- **Bulk Scan Validation**: Scan now validates thumbnail files actually exist on disk before skipping artists
- **Stale Path Cleanup**: Automatic cleanup of `thumbnail_path` database values pointing to non-existent files
- **Wikimedia 403/429 Errors**: Browser-like headers for Wikipedia/Wikimedia downloads to avoid blocking
- **Error Display**: Frontend properly shows `data.detail` from FastAPI error responses

### Changed
- **Search Priority**: Google Images now searched first for artist thumbnails, then Wikipedia, then YouTube
- **Rate Limiting**: Added 1-second delay between artists in bulk scan to avoid API throttling
- **Wikimedia Headers**: Uses full browser-like headers including Referer and Sec-Fetch headers

### Added
- **REDIS_HOST**: New environment variable for external Redis server hostname (PR #189)
- **REDIS_PORT**: New environment variable for external Redis server port (PR #189)

### Metrics
- Bulk scan success improved from 0% to 87% (231/264 artists)

## [0.11.7] - 2026-02-02

### Added
- Per-artist video type filtering for autodownload (Issue #191)
- Extended YouTube discovery for live performances, concerts, acoustic versions
- Increased max_videos_per_discovery from 5 to 50

### Fixed
- Blacklist not saving info when deleting videos (Issue #190)
- Download completion callback not updating records
- Download History not showing completed downloads

### Changed
- API optimization for improved performance and response times

## [0.10.1] - 2024-12-22

### Added - Scheduler V2 Complete Implementation

#### Phase 1: Core Infrastructure
- **Celery Integration**: Production-grade distributed task scheduling with Celery Beat
- **Redis Backend**: Message broker and result backend for reliable task execution
- **Database Models**: New `ScheduledJob` model for comprehensive job tracking
- **Service Layer**: `SchedulerServiceV2` managing all scheduling operations
- **Task Definitions**:
  - `scheduled_discovery_task` - Automated artist video discovery
  - `artist_specific_discovery_task` - Per-artist discovery with custom intervals
  - `scheduled_downloads_task` - Priority-based batch downloads
  - `retry_failed_downloads_task` - Exponential backoff retry mechanism
  - `scheduler_health_check_task` - System health monitoring
- **Configuration System**: 20+ settings for fine-tuned scheduler control

#### Phase 2: Per-Artist Scheduling
- **Artist Scheduling Fields**: 7 new database columns for per-artist configuration
  - `discovery_interval_hours` - Custom discovery intervals
  - `discovery_enabled` / `download_enabled` - Individual control
  - `last_discovery` / `last_download` - Activity tracking
  - `max_videos_per_discovery` - Rate limiting
  - `schedule_priority` - High/medium/low priority levels
- **Download Retry System**: Enhanced retry tracking with exponential backoff
  - `retry_count`, `last_attempt`, `last_error`, `next_retry_at` fields
  - Automatic retry scheduling for failed downloads

#### Phase 3: REST API (23 Endpoints)
- **Scheduler Control API** (`/api/v2/scheduler`):
  - `GET /status` - Comprehensive scheduler status and statistics
  - `POST /start` - Start scheduler service
  - `POST /stop` - Stop scheduler service
  - `POST /trigger/discovery` - Manual discovery trigger (global or per-artist)
  - `POST /trigger/downloads` - Manual download trigger
  - `GET /schedules` - View all configured schedules
  - `PUT /schedules/{name}` - Update schedule configuration
  - `GET /health` - Health check endpoint

- **Job Management API** (`/api/v2/jobs`):
  - `GET /scheduled` - List jobs with filtering and pagination
  - `GET /scheduled/{id}` - Get detailed job information
  - `POST /scheduled/{id}/retry` - Retry failed job
  - `POST /scheduled/{id}/cancel` - Cancel running job
  - `GET /statistics` - Job statistics with time range filtering
  - `GET /history` - Historical job data export
  - `DELETE /cleanup` - Cleanup old completed jobs

- **Artist Scheduling API** (`/api/artists/{id}/scheduling`):
  - `GET /api/artists/{id}/scheduling` - Get artist scheduling config
  - `PUT /api/artists/{id}/scheduling` - Update artist scheduling config
  - `DELETE /api/artists/{id}/scheduling` - Reset to defaults
  - `GET /api/artists/{id}/jobs` - Get artist-specific job history

#### Phase 4: Job Tracking & Monitoring
- **Comprehensive Job Tracking**:
  - Job lifecycle management (pending → running → completed/failed)
  - Celery task ID correlation for distributed debugging
  - Execution time tracking and performance metrics
  - Error message capture with full traceback
  - Retry attempt tracking with exponential backoff
  - Result summaries in JSON format (videos found, downloads queued, etc.)
- **Database Schema Enhancements**:
  - 15+ indexed columns for fast queries
  - Composite indexes for common filter patterns
  - Automatic timestamp management
  - Orphan job detection and cleanup
- **Statistics & Analytics**:
  - 24-hour rolling statistics
  - Success/failure rates by job type
  - Average execution times
  - Artist-specific performance metrics
  - System health indicators

#### Phase 5: Frontend Integration
- **Scheduler Dashboard** (`/scheduler/dashboard`):
  - Real-time scheduler status monitoring
  - Start/stop controls with confirmation
  - Manual trigger buttons for discovery and downloads
  - 24-hour statistics dashboard
  - Active schedules display with next run times
  - System health indicators (Celery, Redis, database)
  - Recent jobs preview with status
  - Auto-refresh every 30 seconds
- **Scheduled Jobs Monitor** (`/scheduler/jobs`):
  - Advanced filtering (status, type, artist, date range)
  - Server-side pagination (50 jobs per page)
  - Job details modal with full information
  - Retry failed jobs with one click
  - Cancel running jobs
  - Bulk cleanup for old completed jobs
  - Export capabilities for job history
  - Responsive design for mobile devices
- **Frontend Assets**:
  - `scheduler-dashboard.js` - Dashboard interactions and API calls
  - `scheduled-jobs.js` - Job list management and filtering
  - `scheduler.css` - Shared responsive styling with dark mode support

#### Phase 6: Migration & Cleanup
- **Legacy Code Removal**:
  - Removed `src/services/scheduler_service.py` (thread-based scheduler)
  - Removed `src/services/enhanced_scheduler_service.py` (interim solution)
  - Removed `src/api/fastapi/enhanced_scheduler.py` (old API endpoints)
- **Migration Tools**:
  - `scripts/migrate_to_scheduler_v2.py` - Data migration script
    - Dry-run mode for safe preview
    - Sets default values for new fields
    - Validates data integrity
    - Detailed migration reporting
  - `scripts/verify_scheduler_v2_migration.py` - Verification script
    - Schema validation
    - Artist data validation
    - Download field validation
    - Orphaned job detection
    - Comprehensive verification report
- **Documentation**:
  - `docs/SCHEDULER_V2.md` - Complete technical documentation (600+ lines)
    - System architecture with diagrams
    - Database schema details
    - All 23 API endpoints with examples
    - Configuration guide (global and per-artist)
    - Troubleshooting section
    - FAQ with 10+ common questions
  - `docs/MIGRATION_0.10.1.md` - Step-by-step migration guide (500+ lines)
    - Breaking changes documentation
    - Pre-migration checklist
    - Detailed migration procedure
    - Post-migration verification steps
    - Rollback procedure
    - Common issues and solutions
- **Application Updates**:
  - Updated `fastapi_app.py` to use Scheduler V2 on startup
  - Removed all legacy scheduler references
  - Updated frontend routes for new scheduler pages

### Changed
- **Scheduler Architecture**: Complete replacement of thread-based scheduling with Celery Beat
- **API Endpoints**: Legacy `/api/scheduler/*` endpoints deprecated in favor of `/api/v2/scheduler/*`
- **Configuration**: Settings renamed and reorganized for Scheduler V2
  - `scheduler_enabled` → `scheduler_v2_enabled`
  - `scheduler_interval` → Per-schedule configuration
  - Added 20+ new configuration options

### Deprecated
- `/api/scheduler/start` - Use `/api/v2/scheduler/start`
- `/api/scheduler/stop` - Use `/api/v2/scheduler/stop`
- `/api/scheduler/status` - Use `/api/v2/scheduler/status`
- `/api/scheduler/trigger` - Use `/api/v2/scheduler/trigger/discovery`

### Removed
- `SchedulerService` (legacy thread-based scheduler)
- `EnhancedSchedulerService` (interim scheduler)
- Legacy scheduler API endpoints (`/api/scheduler/*`)
- Thread-based scheduling implementation

### Fixed
- **Reliability**: Eliminated race conditions in thread-based scheduler
- **Scalability**: Distributed task execution replaces single-threaded processing
- **Monitoring**: Complete visibility into job execution and failures
- **Recovery**: Automatic retry mechanism for failed operations

### Security
- **Authentication**: All Scheduler V2 API endpoints require authentication
- **Authorization**: Job actions restricted to authenticated users
- **Input Validation**: Pydantic models validate all API requests

### Migration Notes
- **Breaking Change**: Cannot rollback to legacy scheduler after upgrade
- **Database Migration**: Run `python migrations/019_add_scheduler_v2_tables.py`
- **Data Migration**: Run `python scripts/migrate_to_scheduler_v2.py`
- **Verification**: Run `python scripts/verify_scheduler_v2_migration.py`
- **Dependencies**: Requires Celery, Redis, and updated requirements.txt
- **Services**: Must start Celery workers and Beat scheduler
- See `docs/MIGRATION_0.10.1.md` for complete migration guide

## [0.10.0-beta.1] - 2024-12-01

### Added
- 🔒 **Security**: Fixed 10 critical vulnerabilities (issue #165)
- 🔧 **Installation Wizard**: Guided first-run setup (issue #163)
- 🎬 **Video Import System**: Reliable import with duplicate detection
- ✅ **API Validation**: Pre-configuration testing
- 📚 **Documentation**: Complete user guides (issue #91)
- 📊 **Performance Dashboard**: System monitoring (issue #95)
- 🔄 **Migration Tools**: Database upgrade utilities (issue #92)
- 🐳 **Unraid Support**: Official Unraid template (issue #97)

### Changed
- **Versioning**: Adopted SemVer 0.x conventions for pre-production

## [0.9.9] - 2024-11-04

### Changed
- Code cleanup and optimization
- Performance improvements

## Earlier Versions

Previous version history not documented. See GitHub releases for more information.

---

## Version Links

[Unreleased]: https://github.com/prefect421/mvidarr/compare/v0.10.1...HEAD
[0.10.1]: https://github.com/prefect421/mvidarr/releases/tag/v0.10.1
[0.10.0-beta.1]: https://github.com/prefect421/mvidarr/releases/tag/v0.10.0-beta.1
[0.9.9]: https://github.com/prefect421/mvidarr/releases/tag/v0.9.9
