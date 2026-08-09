# Changelog

All notable changes to MVidarr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.12.24] - 2026-08-09 - Security Sweep

### Security
- **CVE-2026-69244 / GHSA-cq5v-8q36-5273** (HIGH): aiohttp 3.14.1 → 3.14.3 — out-of-bounds heap read in the C HTTP response parser error path
- **CVE-2026-69243 / GHSA-mfx4-hv73-q22v** (MEDIUM): aiohttp 3.14.1 → 3.14.3 — HTTP request smuggling via WebSocket upgrade
- **CVE-2026-59881 / GHSA-mq44-7p77-q5h7** (MEDIUM): aiohttp 3.14.1 → 3.14.3 — WebSocket client decompressed frames without a negotiated permessage-deflate extension

### Fixed
- **#307**: Removed a premature 3-second false-positive "format not supported" warning on MKV/AVI playback that raced against real-time transcoding and destroyed the live video element; the existing 30-second `loadTimeout` already handles genuine load failures
- **#306** (partial/defensive): `scan_missing_thumbnails()` no longer treats a failed filesystem check (`OSError`) as proof a thumbnail file was deleted — only a clean, confirmed-missing file now clears `thumbnail_path`/`thumbnail_url` from the database, and the checked path is logged for diagnosability. Root cause not fully reproduced; flagged as a candidate fix.

## [0.12.23] - 2026-08-02 - Dependency Sweep

### Changed
- **pytest** 9.0.3 → 9.1.1 (dev), **tqdm** 4.68.3 → 4.70.0
- **sphinx** 7.2.6 → 9.1.0, **sphinx-rtd-theme** 1.3.0 → 3.1.0 (dev-only; rtd-theme bump required to resolve a `sphinx<8` pin conflict)
- **redis** 8.0.1 → 8.1.0
- **psutil** 5.9.6 → 7.2.2 (2 major versions) — deferred in v0.12.22 pending its own verification pass; changelog review found no overlap between the 6.0.0/7.0.0 breaking-change list and any psutil API this codebase calls

## [0.12.22] - 2026-07-25 - Dependency Sweep

### Changed
- **celery** 5.3.4 → 5.6.3, **redis** 5.0.1 → 8.0.1 (3 major versions) — verified live: celery worker/beat ping successfully, job-progress/cache round-trips through `redis_manager` work correctly
- **sentry-sdk** 2.63.0 → 2.66.1, **imagehash** 4.3.1 → 4.3.2 (dev-only)
- **CI**: actions/setup-python v6 → v7, actions/labeler v6 → v7, ruby/setup-ruby 1.319.0 → 1.321.0

## [0.12.21] - 2026-07-19 - Dependabot Sweep

### Security
- **GHSA-4jhm-jv67-739f**: lxml 6.1.0 → 6.1.1 — `xlink:href` URL bypass in embedded SVG/MathML; also bundles libxslt fixes for CVE-2025-7424 / CVE-2025-11731
- **GHSA-r397-ff8c-wv2g**: aiomysql >=0.2.0 → >=0.3.2 — local_infile load bypass

### Changed
- **pymysql** 1.1.1 → 1.2.0 (`requirements.txt` + `requirements-fastapi.txt`) — v1.2.0 makes TLS required-by-default when the server supports it; verified against live MariaDB with no regression
- **marshmallow** 3.26.2 → 4.3.0, **flake8** 6.1.0 → 7.3.0 (dev-only)
- **CI**: ruby/setup-ruby 1.316.0 → 1.319.0

## [0.12.20] - 2026-07-16 - Fix Stuck Download Queue

### Fixed
- **"Stop Download" 400 error**: the queue view is built from `Video.status == DOWNLOADING`, but `stop_download` always looked the id up as a `Download` table row, so stopping a stuck video almost always 400'd. Queue ids from videos are now unambiguously tagged (`video_123`) and routed to the right table.
- **"Force Clear All" reported nothing to clear**: the endpoint only reset videos reachable through a `Download` row still in `queued`/`downloading`/`pending`; a video stuck at `DOWNLOADING` with no such row was invisible to it. It now also resets orphaned stuck videos directly.
- **Misleading "no stuck downloads found" message**: the frontend's success message depended on a `cleared_count` field the backend never sent, so it always claimed nothing was found. Backend now returns the real count.

## [0.12.19] - 2026-07-16 - YouTube Max-Quality Downloads & Dead-URL Recovery

Core fix contributed by **@Ktell123** in [#282](https://github.com/prefect421/mvidarr/pull/282).

### Fixed
- **Anti-detection setting ignored**: `enable_aggressive_anti_detection` was read with `settings.get()`, which returns the string `'False'` — truthy in Python — forcing AGGRESSIVE anti-detection (and the Android YouTube client) on every download and capping quality at ~360p. Now uses `settings.get_bool()`.
- **Retry file-preservation bug** (found in code review): the low-res retry logic deleted the original download's file before confirming the retry actually succeeded or was better, so a failed or worse retry could report success while pointing at a deleted file. Fixed, with 16 new unit tests covering the retry paths.

### Changed
- **Player client priority**: prefer `web,mweb,tv` YouTube clients over android-first clients that hide adaptive HD/4K formats
- **Format selection**: yt-dlp Node JS runtime + resolution-first format sort (`-S res,br`), improved `best` format string, automatic MODERATE retry when an escalated (AGGRESSIVE/STEALTH) download still lands at ≤360p

### Added
- **Dead YouTube URL recovery**: when a stored YouTube URL is private, unavailable, or terminated, MVidarr now searches for an official alternate upload, persists the new URL, and retries the download once

## [0.12.18] - 2026-07-05 - Dependency Sweep

### Changed
- **fastapi** 0.138.1 → 0.139.0, **Pillow** 12.2.0 → 12.3.0, **opencv-python-headless** >=4.13.0.92 → >=5.0.0.93
- **click** 8.1.7 → 8.4.2, **tqdm** 4.66.3 → 4.68.3
- **CI**: ruby/setup-ruby 1.314.0 → 1.315.0

### Fixed
- `release.yml` now tolerates pre-existing release tags (skips create if already exists)

## [0.12.17] - 2026-06-27 - Security Sweep

### Security
- **GHSA-4xgf-cpjx-pc3j** (MEDIUM): pydantic-settings 2.14.1 → 2.14.2 — `NestedSecretsSettingsSource` symlink traversal; also fixed in `requirements-fastapi.txt` (a stale pin was silently downgrading httpx in Docker)

### Changed
- **fastapi** 0.136.3 → 0.138.1, **alembic** 1.18.4 → 1.18.5, **httpx** 0.25.2 → 0.28.1, **python-slugify** 8.0.1 → 8.0.4
- **mypy** 1.7.1 → 2.1.0 (dev-only, not run in CI), **CI**: actions/cache v5 → v6, ruby/setup-ruby 1.313.0 → 1.314.0

## [0.12.16] - 2026-06-19 - Security Sweep

### Security
- **CVE-2026-53539** (HIGH, CVSS 7.5): python-multipart 0.0.27 → 0.0.32 — quadratic CPU DoS via semicolon separators
- **Dependabot #20** (MEDIUM, CVSS 6.1): bleach 6.1.0 → 6.4.0 — `formaction` URI scheme bypass
- **CVE-2026-53538** (LOW): python-multipart — semicolon field separator parameter smuggling
- **CVE-2026-53537** (LOW): python-multipart — Content-Disposition RFC 2231 smuggling
- **CVE-2026-45152** (LOW): python-multipart — negative Content-Length buffers body
- **Dependabot #19** (LOW): bleach — Unicode >U+00A0 URI sanitization bypass

### Changed
- **sentry-sdk** 2.8.0 → 2.63.0 (FastAPI 0.137 compat fix), **starlette** floor >=1.2.1 → >=1.3.1
- **CI**: actions/checkout v6 → v7

## [0.12.15] - 2026-06-06 - Security Sweep

### Security
- **CVE-2026-34993** (MEDIUM): aiohttp 3.13.4 → 3.14.0 — `CookieJar.load()` deserialization RCE
- **CVE-2026-47265** (MEDIUM): aiohttp 3.13.4 → 3.14.0 — cross-origin redirect leaks per-request cookies

### Changed
- **bcrypt** 4.1.2 → 5.0.0 — breaking: passwords >72 bytes now raise `ValueError`; guard added in auth service
- **requests** 2.33.0 → 2.34.2, **alembic** 1.13.1 → 1.18.4, **zeroconf** 0.149.7 → 0.149.16
- **CI**: GitHub Actions Node 24 — docker/metadata-action@v6, upload-pages-artifact@v5, labeler@v6, label-actions@v5, lock-threads@v6

## [0.12.14] - 2026-06-02 - Security Sweep

### Security
- **PYSEC-2026-179/178/177/176/175**: PyJWT 2.12.0 → 2.13.0 — HMAC algorithm confusion, detached JWS DoS, unbounded JWKS unauthenticated DoS, algorithm allow-list bypass via PyJWK, PyJWKClient SSRF via file://, ftp://, data://

### Fixed
- 3 stale Trivy code scanning alerts (zeroconf CVE-2026-47180/83/84) cleared via fresh scan

## [0.12.13] - 2026-06-01 - Video Streaming Fix

### Fixed
- Streaming 404 errors — `find_relocated_video()` used `getattr(file_path)` returning `None`, silently ignoring `local_path`
- Streaming 404 errors — added `Config.BASE_DIR`-anchored path fallback for relative `local_path` values in Docker
- Both `stream` and `stream-transcode` endpoints patched

## [0.12.12] - 2026-06-01 - Dependabot Sweep + Python 3.14

### Changed
- Python base image 3.12-slim → 3.14-slim (verified: netifaces, mysqlclient, moviepy compile cleanly)
- **aiofiles** 23.2.1 → 25.1.0, **starlette** ≥1.2.1, **python-dateutil** 2.9.0.post0, **werkzeug** 3.1.8, **PyYAML** 6.0.3
- **CI**: Actions Node.js 24 — checkout@v6, login-action@v4, build-push-action@v7, github-script@v9, deploy-pages@v5

## [0.12.11] - 2026-06-01 - Security Sweep + CI Modernization

### Security
- **CVE-2026-47180, CVE-2026-47183, CVE-2026-47184**: zeroconf 0.132.2 → 0.149.7 — LAN-local DoS/OOM via mDNS flood
- **PYSEC-2026-161**: starlette ≥1.0.1 — Host header injection / authentication bypass

### Changed
- **fastapi** 0.123.0 → 0.136.3, **pydantic** 2.5.0 → 2.13.4, **pydantic-settings** 2.1.0 → 2.14.1, **typing-inspection** ≥0.4.2
- **CI**: GitHub Actions v4 → Node.js 24 (checkout@v5, cache@v5, setup-python@v6, upload-artifact@v7, codecov@v6)

### Fixed
- codecov `file:` → `files:` input rename (Unexpected input warnings)

## [0.12.10] - 2026-05-16 - Security Sweep

### Security
- **CVE-2026-44432** (HIGH, CVSS 7.5): urllib3 2.6.3 → 2.7.0 — decompression-bomb bypass
- **CVE-2026-44431** (HIGH, CVSS 5.3): urllib3 2.6.3 → 2.7.0 — sensitive header forwarding

### Fixed
- pytest-asyncio 0.23.8 → 1.3.0 (0.x incompatible with pytest 9.x, broke pip-audit + test suite)
- pytest-playwright 0.4.3 → 0.7.2 (required for pytest 9.x compatibility)

### Changed
- Dockerfile: added `--timeout 120` to pip install for reliable builds on slow connections

## [0.12.9] - 2026-05-11 - YouTube Quota & Discovery Improvements

### Changed
- Reduced YouTube searches from 4 to 2 per artist for quota efficiency
- Quota enforcement with file locking in `YouTubeQuotaTracker`
- Per-artist `last_discovery` committed after each artist to survive interrupted runs

## [0.12.8] - 2026-05-07 - Security Patches

### Security
- **CVE-2026-41066** (HIGH): lxml 4.9.3 → 6.1.0 — XXE local file read
- **CVE-2026-42561** (MEDIUM): python-multipart 0.0.26 → 0.0.27 — DoS via header parsing
- **CVE-2026-28684** (MEDIUM): python-dotenv 1.0.0 → 1.2.2 — symlink arbitrary file overwrite

### Fixed
- broken `-r requirements-prod.txt` include in `requirements-dev.txt` → `-r requirements.txt`
- isort import ordering corrected across `src/`

## [0.12.7] - 2026-04-16 - Dependency Cleanup & Test Infrastructure

### Security
- 5 CVEs resolved (python-multipart, Pillow, pytest)

### Changed
- Removed sphinx from production runtime (dev-only)
- pytest-cov 4.1.0 → 7.1.0 for pytest 9.x compatibility

## [0.12.6] - 2026-04-09 - Security Dependency Updates

### Security
- **CVE-2026-25645** (MEDIUM): requests 2.32.4 → 2.33.0 — predictable temporary file creation
- **CVE-2026-22815/34513-34520**: aiohttp 3.13.3 → 3.13.4 — multiple DoS and injection fixes
- 12 CVEs total resolved

## [0.12.5] - 2026-03-19 - Security & Bug Fixes

### Security
- **CVE-2026-32597**: PyJWT 2.8.0 → 2.12.0 — missing `crit` header validation
- **CVE-2026-32274**: black 24.3.0 → 26.3.1 — arbitrary cache file write
- Removed black from runtime requirements (dev tool only)

### Fixed
- Docker `git_branch` always unknown — `version.json` now read first in health endpoint
- Docker ERROR log spam from missing git binary on every health check
- Installation wizard credentials now applied to login (#199)
- Thumbnail download on video completion (#200)

## [0.12.4] - 2026-02-26 - Scheduler & Auto-Download Fixes

### Security
- **CVE-2026-27205**: Flask 3.1.1 → 3.1.3 in docker/monitor (Vary: Cookie)
- **CVE-2026-27199**: werkzeug → 3.1.6 (Windows device names in `safe_join`)
- **CVE-2026-25990**: Pillow → 12.1.1 (out-of-bounds write on PSD images)
- Replaced python-jose/ecdsa (CVE-2024-23342) with PyJWT

### Fixed
- Celery connection check no longer hangs — 2s timeout + ps fallback
- `trigger/discovery` and `trigger/downloads` no longer 500 after 19s timeout
- Metadata enrichment endpoints no longer block the async event loop
- Job progress bar stuck at 0% — nested progress object now parsed correctly
- Job completion not detected — status normalized to lowercase
- Auto-download scheduling priority was computed but then discarded
- `auto_download_max_videos` raised from 10 → 50
- Pre-v0.10.1 artists with NULL `download_enabled` excluded from download queue
- MONITORED videos never promoted to WANTED when artist enables `auto_download`
- Plain "Artist - Song" titles classified as None type, blocked by `allowed_video_types`
- Videos no longer set to WANTED for monitor-only artists
- `allowed_video_types` and 20+ other artist fields now save correctly

### Changed
- Default: Official Music Video pre-selected for all artists

### Migration
- Migration 004: backfill NULL Scheduler V2 fields for all existing artists

## [0.12.3] - 2026-02-16

### Fixed
- **Playlist Sync - VEVO Names**: Channel names like "KornVEVO" and "tenaciousDVEVO" are now cleaned to "Korn" and "tenaciousD" before artist lookup and creation, preventing duplicate artists with ugly YouTube suffixes
- **Celery Task Logging**: All scheduled task logs (playlist sync, discovery, downloads) were silently dropped because `setup_logging()` only runs in the FastAPI process. Added `after_setup_logger` signal handler in Celery worker to configure `mvidarr.*` loggers with proper handlers
- **Logger Namespace**: Added "src" to configured logger namespaces so Celery task loggers using `get_task_logger(__name__)` get file and console handlers in the FastAPI process

### Changed
- **Artist Name Cleanup**: New `_clean_channel_name()` method strips common YouTube channel suffixes (VEVO, Official, Music, Records, Channel, TV) case-insensitively before searching for or creating artists during playlist sync

## [0.12.2] - 2026-02-14

### Security
- **Authentication**: Added authentication to 36 unprotected API endpoints across 6 files
- **Global 401 Interceptor**: Unauthenticated users now redirected to login page instead of seeing error counts

### Fixed
- **Video Discovery**: Discovery no longer sets videos to WANTED when artist `auto_download` is disabled
- **Artist Deletion**: Fixed 500 error from orphaned playlist/download foreign key references
- **Playlist Sync**: YouTube monitored playlists now auto-sync every 6 hours via scheduled task
- **Playlist Sync**: Fixed session detachment when creating new artists during sync
- **Playlist Video Count**: Fixed video count not reflecting all videos in monitored playlists

### Removed
- Obsolete po-token-provider supervisord process causing FATAL crashes on startup

### Infrastructure
- bgutil-ytdlp-pot-provider updated to v1.2.2 (Rust-based yt-dlp plugin)

## [0.12.1] - 2026-02-12

### Fixed
- **Login Page**: Fixed POSTing to removed `/test-login` endpoint
- **WAF False Positives**: Fixed blocking of URLs, cookies, Range headers
- **Video Streaming**: Range header no longer blocked by security middleware
- **Playlist Sync**: Fixed not detecting new videos in YouTube playlists
- **Auth Bridge**: Fixed Flask-to-FastAPI session bridge for consistent authentication
- **Rate Limiting**: Set to 300/min with static files exempt

### Changed
- CI/CD: 28 files reformatted with black 24.3.0

## [0.12.0] - 2026-02-11

### Security
- Consolidated auth system (SimpleAuth + SessionStore)
- Removed backdoor endpoints (`/test-login`, credential reset)
- Upgraded passwords from SHA-256 to bcrypt with lazy migration
- SSRF protection, safe tar extraction, upload sanitization
- Redis authentication, secure cookies, restricted proxy hosts
- 49 vulnerabilities fixed (8 critical, 12 high, 16 medium, 13 low)

## [0.11.9] - 2026-02-05

### Security
- **CVE-2026-24486**: Updated python-multipart 0.0.20 → 0.0.22 (path traversal vulnerability)
- **CVE-2026-21441**: Updated urllib3 2.6.0 → 2.6.3 (decompression-bomb bypass on redirects)
- **CVE-2025-69223/24/25/26/27/28/29/30**: Updated aiohttp 3.12.14 → 3.13.3 (zip bomb + multiple DoS vulnerabilities)
- **CVE-2026-21860**: Updated werkzeug 3.1.4 → 3.1.5 (Windows device names bypass)

### Fixed
- **Video Quality**: Downloads now respect user's `max_video_quality` database setting instead of defaulting to 360p
- **YouTube Discovery**: Fixed API key caching bug that caused discovery to return 0 results despite valid API key
- **Format Selection**: Added `-S` format sorting to prioritize resolution over bitrate

### Changed
- **Video Downloads**: TV client now falls back to web client for more format options
- **YouTube Cache**: Bumped cache version to invalidate stale empty results from API key bug

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

[Unreleased]: https://github.com/prefect421/mvidarr/compare/v0.12.24...HEAD
[0.12.24]: https://github.com/prefect421/mvidarr/compare/v0.12.23...v0.12.24
[0.12.23]: https://github.com/prefect421/mvidarr/compare/v0.12.22...v0.12.23
[0.12.22]: https://github.com/prefect421/mvidarr/compare/v0.12.21...v0.12.22
[0.12.21]: https://github.com/prefect421/mvidarr/compare/v0.12.20...v0.12.21
[0.12.20]: https://github.com/prefect421/mvidarr/compare/v0.12.19...v0.12.20
[0.12.19]: https://github.com/prefect421/mvidarr/compare/v0.12.18...v0.12.19
[0.12.18]: https://github.com/prefect421/mvidarr/compare/v0.12.17...v0.12.18
[0.12.17]: https://github.com/prefect421/mvidarr/compare/v0.12.16...v0.12.17
[0.12.16]: https://github.com/prefect421/mvidarr/compare/v0.12.15...v0.12.16
[0.12.15]: https://github.com/prefect421/mvidarr/compare/v0.12.14...v0.12.15
[0.12.14]: https://github.com/prefect421/mvidarr/compare/v0.12.13...v0.12.14
[0.12.13]: https://github.com/prefect421/mvidarr/compare/v0.12.12...v0.12.13
[0.12.12]: https://github.com/prefect421/mvidarr/compare/v0.12.11...v0.12.12
[0.12.11]: https://github.com/prefect421/mvidarr/compare/v0.12.10...v0.12.11
[0.12.10]: https://github.com/prefect421/mvidarr/compare/v0.12.9...v0.12.10
[0.12.9]: https://github.com/prefect421/mvidarr/compare/v0.12.8...v0.12.9
[0.12.8]: https://github.com/prefect421/mvidarr/compare/v0.12.7...v0.12.8
[0.12.7]: https://github.com/prefect421/mvidarr/compare/v0.12.6...v0.12.7
[0.12.6]: https://github.com/prefect421/mvidarr/compare/v0.12.5...v0.12.6
[0.12.5]: https://github.com/prefect421/mvidarr/compare/v0.12.4...v0.12.5
[0.12.4]: https://github.com/prefect421/mvidarr/compare/v0.12.3...v0.12.4
[0.12.3]: https://github.com/prefect421/mvidarr/compare/v0.12.2...v0.12.3
[0.12.2]: https://github.com/prefect421/mvidarr/compare/v0.12.1...v0.12.2
[0.12.1]: https://github.com/prefect421/mvidarr/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/prefect421/mvidarr/compare/v0.11.9...v0.12.0
[0.11.9]: https://github.com/prefect421/mvidarr/compare/v0.11.8...v0.11.9
[0.11.8]: https://github.com/prefect421/mvidarr/compare/v0.11.7...v0.11.8
[0.11.7]: https://github.com/prefect421/mvidarr/compare/v0.10.1...v0.11.7
[0.10.1]: https://github.com/prefect421/mvidarr/releases/tag/v0.10.1
[0.10.0-beta.1]: https://github.com/prefect421/mvidarr/releases/tag/v0.10.0-beta.1
[0.9.9]: https://github.com/prefect421/mvidarr/releases/tag/v0.9.9
