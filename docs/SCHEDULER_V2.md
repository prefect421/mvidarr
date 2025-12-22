# Scheduler V2 Documentation

**Version:** v0.10.1
**Status:** Production Ready
**Release Date:** December 2024

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Configuration](#configuration)
4. [API Endpoints](#api-endpoints)
5. [Frontend Interface](#frontend-interface)
6. [Troubleshooting](#troubleshooting)
7. [FAQ](#faq)

---

## Overview

Scheduler V2 is a complete rewrite of MVidarr's scheduling system, replacing the legacy thread-based scheduler with a production-grade Celery Beat implementation.

### Key Features

- **Celery Beat Integration** - Distributed task scheduling with Redis backend
- **Per-Artist Configuration** - Custom intervals, priorities, and limits
- **Robust Retry Mechanism** - Exponential backoff with configurable retries
- **Job Tracking** - Comprehensive database-tracked job history
- **Real-Time Monitoring** - Web dashboard with live status updates
- **RESTful API** - 23 endpoints for complete programmatic control
- **Health Monitoring** - System health checks and diagnostics

### What's New in V2

✅ **Replaced:**
- `SchedulerService` (legacy thread-based)
- `EnhancedSchedulerService` (interim solution)

✅ **Added:**
- Production-grade Celery Beat integration
- Per-artist scheduling configuration
- Job retry mechanism with exponential backoff
- Comprehensive REST API (23 endpoints)
- Real-time web dashboard
- Job history and statistics

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    MVidarr Application                   │
│  ┌────────────────────────────────────────────────────┐ │
│  │              SchedulerServiceV2                     │ │
│  │  - Schedule management                              │ │
│  │  - Manual triggers                                  │ │
│  │  - Health monitoring                                │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│  ┌─────────────────▼──────────────────────────────────┐ │
│  │              Celery Beat Scheduler                  │ │
│  │  - scheduled-discovery (configurable)               │ │
│  │  - scheduled-downloads (configurable)               │ │
│  │  - retry-failed-downloads (hourly)                  │ │
│  │  - scheduler-health-check (5 minutes)               │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│  ┌─────────────────▼──────────────────────────────────┐ │
│  │              Celery Workers (Queue: scheduler)      │ │
│  │  - scheduled_discovery_task()                       │ │
│  │  - artist_specific_discovery_task()                 │ │
│  │  - scheduled_downloads_task()                       │ │
│  │  - retry_failed_downloads_task()                    │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│  ┌─────────────────▼──────────────────────────────────┐ │
│  │              Service Layer                          │ │
│  │  - VideoDiscoveryService (artist discovery)         │ │
│  │  - VideoBatchService (priority downloads)           │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│  ┌─────────────────▼──────────────────────────────────┐ │
│  │              Database (MariaDB/MySQL)               │ │
│  │  - ScheduledJob (job tracking)                      │ │
│  │  - Artist (scheduling config)                       │ │
│  │  - Download (retry tracking)                        │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

         ┌────────────┐
         │   Redis    │ (Celery Broker/Results)
         └────────────┘
```

### Database Schema

#### ScheduledJob Table
Tracks all scheduled jobs with comprehensive lifecycle information.

```sql
CREATE TABLE scheduled_jobs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    job_type VARCHAR(50) NOT NULL,          -- 'discovery' or 'download'
    artist_id INT,                           -- NULL for global jobs
    status VARCHAR(50) DEFAULT 'pending',    -- pending/running/completed/failed/cancelled
    started_at DATETIME,
    completed_at DATETIME,
    celery_task_id VARCHAR(255) UNIQUE,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    error_message TEXT,
    result_summary JSON,
    execution_time_seconds INT,
    triggered_by VARCHAR(50) DEFAULT 'scheduled',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_artist_id (artist_id),
    INDEX idx_status (status),
    INDEX idx_job_type (job_type),
    INDEX idx_celery_task_id (celery_task_id),
    -- ... additional indexes
);
```

#### Artist Scheduling Fields
Per-artist configuration for custom scheduling behavior.

```sql
ALTER TABLE artists ADD COLUMN (
    discovery_interval_hours INT,            -- Custom interval (NULL = use global)
    last_discovery DATETIME,                 -- Last discovery timestamp
    last_download DATETIME,                  -- Last download timestamp
    discovery_enabled BOOLEAN DEFAULT TRUE,  -- Enable/disable discovery
    download_enabled BOOLEAN DEFAULT TRUE,   -- Enable/disable downloads
    max_videos_per_discovery INT,            -- Limit videos per run
    schedule_priority VARCHAR(20) DEFAULT 'medium'  -- high/medium/low
);
```

### Task Hierarchy

1. **Celery Beat** → Triggers scheduled tasks at configured intervals
2. **scheduled_discovery_task()** → Discovers videos for all enabled artists
3. **artist_specific_discovery_task()** → Discovers videos for specific artist
4. **scheduled_downloads_task()** → Downloads all wanted videos (priority-based)
5. **retry_failed_downloads_task()** → Retries downloads with exponential backoff

---

## Configuration

### Global Settings

Configure Scheduler V2 through the MVidarr settings UI or database.

#### Scheduler Control
- `scheduler_v2_enabled` (boolean, default: `true`) - Enable/disable Scheduler V2
- `scheduler_v2_worker_count` (integer, default: `3`) - Number of Celery workers
- `scheduler_v2_health_check_enabled` (boolean, default: `true`) - Enable health checks

#### Discovery Configuration
- `auto_discovery_schedule_enabled` (boolean, default: `true`) - Enable scheduled discovery
- `auto_discovery_schedule_time` (string, default: `"06:00"`) - Time to run (HH:MM format)
- `auto_discovery_schedule_days` (string, default: `"daily"`) - Frequency
  - Options: `hourly`, `daily`, `weekly`, `twice_daily`, `every_N_hours`, or comma-separated days
- `scheduler_v2_discovery_parallel_workers` (integer, default: `3`) - Concurrent artist discoveries
- `scheduler_v2_discovery_timeout_seconds` (integer, default: `300`) - Discovery timeout per artist
- `scheduler_v2_discovery_batch_size` (integer, default: `50`) - Videos to discover per batch

#### Download Configuration
- `auto_download_schedule_enabled` (boolean, default: `true`) - Enable scheduled downloads
- `auto_download_schedule_time` (string, default: `"02:00"`) - Time to run
- `auto_download_schedule_days` (string, default: `"hourly"`) - Frequency
- `scheduler_v2_max_concurrent_downloads` (integer, default: `3`) - Max simultaneous downloads
- `scheduler_v2_download_retry_enabled` (boolean, default: `true`) - Enable auto-retry
- `scheduler_v2_download_max_retries` (integer, default: `3`) - Max retry attempts
- `scheduler_v2_download_retry_delay_seconds` (integer, default: `300`) - Initial retry delay

#### Monitoring
- `scheduler_v2_job_retention_days` (integer, default: `30`) - Days to keep job history
- `scheduler_v2_enable_job_alerts` (boolean, default: `false`) - Enable job failure alerts

### Per-Artist Configuration

Configure individual artists through:
- **Web UI**: Artist edit page → Scheduling tab
- **API**: `PUT /api/artists/{id}/scheduling`

#### Artist Settings
- `discovery_enabled` (boolean) - Enable discovery for this artist
- `download_enabled` (boolean) - Enable auto-downloads for this artist
- `discovery_interval_hours` (integer, nullable) - Custom discovery interval (NULL = use global)
- `max_videos_per_discovery` (integer, nullable) - Limit videos per discovery run
- `schedule_priority` (string) - Priority level: `high`, `medium`, `low`
  - High priority artists discovered/downloaded first
  - Low priority artists processed last

### Schedule Formats

#### Time Format
All times use **24-hour HH:MM format**: `"06:00"`, `"14:30"`, `"23:00"`

#### Frequency Options
- `"hourly"` - Every hour
- `"daily"` - Once per day at specified time
- `"weekly"` - Once per week (Monday) at specified time
- `"twice_daily"` - Twice per day (at time and +12 hours)
- `"every_N_hours"` - Every N hours (e.g., `"every_6_hours"`)
- `"monday,wednesday,friday"` - Specific days of week

---

## API Endpoints

### Scheduler Control API (`/api/v2/scheduler`)

#### Get Scheduler Status
```http
GET /api/v2/scheduler/status
```

**Response:**
```json
{
  "status": "running",
  "enabled": true,
  "celery_connected": true,
  "schedules": {
    "scheduled-discovery": {
      "task": "src.tasks.scheduled_tasks.scheduled_discovery_task",
      "schedule": "crontab(hour=6, minute=0)",
      "enabled": true
    }
  },
  "statistics": {
    "total_jobs_24h": 48,
    "completed": 45,
    "failed": 3,
    "running": 0,
    "success_rate": 93.75
  },
  "worker_count": 3,
  "health_check_enabled": true
}
```

#### Start/Stop Scheduler
```http
POST /api/v2/scheduler/start
POST /api/v2/scheduler/stop
```

#### Manual Triggers
```http
POST /api/v2/scheduler/trigger/discovery
POST /api/v2/scheduler/trigger/downloads

# Artist-specific discovery
POST /api/v2/scheduler/trigger/discovery
Content-Type: application/json

{
  "artist_id": 123
}
```

**Response:**
```json
{
  "status": "triggered",
  "task_id": "abcd-1234-efgh-5678",
  "message": "Discovery triggered for Artist Name"
}
```

### Job Management API (`/api/v2/jobs`)

#### List Scheduled Jobs
```http
GET /api/v2/jobs/scheduled?limit=50&offset=0&status=failed&job_type=discovery
```

#### Get Job Details
```http
GET /api/v2/jobs/scheduled/{job_id}
```

#### Retry/Cancel Job
```http
POST /api/v2/jobs/scheduled/{job_id}/retry
POST /api/v2/jobs/scheduled/{job_id}/cancel
```

#### Job Statistics
```http
GET /api/v2/jobs/statistics?hours=24
```

**Response:**
```json
{
  "total_jobs": 48,
  "completed_jobs": 45,
  "failed_jobs": 3,
  "running_jobs": 0,
  "pending_jobs": 0,
  "success_rate": 93.75,
  "avg_execution_time": 12.5,
  "by_job_type": {
    "discovery": 24,
    "download": 24
  },
  "by_status": {
    "completed": 45,
    "failed": 3
  }
}
```

### Artist Scheduling API (`/api/artists/{id}/scheduling`)

#### Get Artist Scheduling Config
```http
GET /api/artists/123/scheduling
```

**Response:**
```json
{
  "discovery_enabled": true,
  "download_enabled": true,
  "discovery_interval_hours": 24,
  "max_videos_per_discovery": 50,
  "schedule_priority": "high"
}
```

#### Update Artist Scheduling
```http
PUT /api/artists/123/scheduling
Content-Type: application/json

{
  "discovery_enabled": true,
  "download_enabled": true,
  "discovery_interval_hours": 12,
  "schedule_priority": "high"
}
```

---

## Frontend Interface

### Scheduler Dashboard (`/scheduler/dashboard`)

**Features:**
- Real-time scheduler status
- Start/stop controls
- Manual trigger buttons
- 24-hour statistics
- Active schedules display
- Health status indicators
- Recent jobs preview
- Auto-refresh every 30 seconds

### Scheduled Jobs Monitor (`/scheduler/jobs`)

**Features:**
- Advanced filtering (status, type, artist, limit)
- Paginated jobs table
- Job details modal
- Retry failed jobs
- Cancel running jobs
- Bulk cleanup old jobs
- Export capabilities

---

## Troubleshooting

### Scheduler Not Starting

**Symptoms:** Status shows "stopped" or "disabled"

**Solutions:**
1. Check `scheduler_v2_enabled` setting is `true`
2. Verify Celery workers are running: `celery -A src.jobs.celery_app status`
3. Check Redis connection: `redis-cli ping`
4. Review logs: Check for errors in Celery worker logs

### Jobs Not Running

**Symptoms:** No jobs appearing in scheduled_jobs table

**Solutions:**
1. Verify scheduler is running: `GET /api/v2/scheduler/status`
2. Check schedule configuration in database
3. Verify artists have `discovery_enabled=true`
4. Check Celery Beat is running and connected
5. Review Celery Beat schedule: Check `celery_app.py` beat_schedule

### Jobs Failing Immediately

**Symptoms:** Jobs status=failed with no useful error

**Solutions:**
1. Check job details modal for error message
2. Review Celery worker logs
3. Verify database connectivity
4. Check artist/video data integrity
5. Ensure external APIs (IMVDb, YouTube) are accessible

### High Job Failure Rate

**Symptoms:** Many jobs failing in statistics

**Solutions:**
1. Review common error messages in failed jobs
2. Check external API rate limits
3. Verify network connectivity
4. Increase retry delays: `scheduler_v2_download_retry_delay_seconds`
5. Reduce concurrent operations: Lower parallel workers

### Performance Issues

**Symptoms:** Slow job execution, system lag

**Solutions:**
1. Reduce concurrent workers: Lower `scheduler_v2_discovery_parallel_workers`
2. Increase timeouts: Raise `scheduler_v2_discovery_timeout_seconds`
3. Reduce batch sizes: Lower `scheduler_v2_discovery_batch_size`
4. Check system resources (CPU, memory, disk I/O)
5. Optimize database indexes (see migration script)

---

## FAQ

### Q: Can I disable Scheduler V2 and use the old scheduler?

**A:** No, the legacy schedulers have been removed in v0.10.1. Scheduler V2 is the only scheduling system. If you need to disable scheduling entirely, set `scheduler_v2_enabled=false`.

### Q: How do I migrate from the old scheduler?

**A:** Run the migration script:
```bash
python scripts/migrate_to_scheduler_v2.py --dry-run  # Preview changes
python scripts/migrate_to_scheduler_v2.py             # Apply migration
python scripts/verify_scheduler_v2_migration.py       # Verify success
```

### Q: Can I schedule discoveries at different times for different artists?

**A:** Not directly through scheduled times. Use `discovery_interval_hours` to control per-artist frequency, or trigger manually via API/UI.

### Q: How does priority affect scheduling?

**A:** Priority determines processing order:
1. **High priority** artists discovered/downloaded first
2. **Medium priority** processed second
3. **Low priority** processed last

Within same priority, oldest videos/artists processed first (fairness).

### Q: What happens if a job exceeds the timeout?

**A:** The job is marked as failed and can be retried. Increase `scheduler_v2_discovery_timeout_seconds` if timeouts are frequent.

### Q: Can I run multiple scheduler instances?

**A:** Yes, Celery Beat supports distributed scheduling, but only ONE Beat instance should be running at a time. Multiple workers are fine and recommended.

### Q: How long is job history kept?

**A:** Job history is kept for `scheduler_v2_job_retention_days` (default: 30 days). Use the cleanup endpoint to manually remove old jobs.

### Q: Can I export job history?

**A:** Yes, through the API:
```bash
curl -X GET "http://localhost:5000/api/v2/jobs/history?hours=168" > jobs.json
```

### Q: How do I troubleshoot a specific failed job?

**A:** 1. View job details in web UI or via API
2. Check `error_message` field for error details
3. Review Celery worker logs for full traceback
4. Retry the job after fixing the underlying issue

### Q: What's the recommended configuration for a large library (1000+ artists)?

**A:**
```
scheduler_v2_discovery_parallel_workers = 5
scheduler_v2_discovery_timeout_seconds = 600
scheduler_v2_discovery_batch_size = 100
scheduler_v2_max_concurrent_downloads = 5
auto_discovery_schedule_days = "twice_daily"
```

---

## Support

- **GitHub Issues**: https://github.com/prefect421/mvidarr/issues
- **Documentation**: https://prefect421.github.io/mvidarr
- **Project Board**: https://github.com/users/prefect421/projects/1

---

**Version:** v0.10.1
**Last Updated:** December 2024
**Maintainer:** MVidarr Development Team
