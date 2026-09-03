# Migration Guide: v0.10.1 Scheduler V2

**Version:** v0.10.1
**Release Date:** December 2025
**Migration Difficulty:** Medium
**Estimated Time:** 15-30 minutes

## Table of Contents

1. [Overview](#overview)
2. [Breaking Changes](#breaking-changes)
3. [Pre-Migration Checklist](#pre-migration-checklist)
4. [Migration Steps](#migration-steps)
5. [Post-Migration Verification](#post-migration-verification)
6. [Rollback Procedure](#rollback-procedure)
7. [Common Issues](#common-issues)

---

## Overview

Version 0.10.1 introduces **Scheduler V2**, a complete rewrite of MVidarr's scheduling system. This migration guide will help you upgrade from the legacy scheduler to Scheduler V2.

### What's Changing

**Removed:**
- `SchedulerService` (legacy thread-based scheduler)
- `EnhancedSchedulerService` (interim scheduler)
- Old scheduler API endpoints

**Added:**
- Celery Beat-based Scheduler V2
- Per-artist scheduling configuration
- Job history and tracking
- Enhanced retry mechanisms
- New REST API (23 endpoints)
- Web dashboard for monitoring

### Impact

- ⚠️ **Breaking Change**: Old scheduler code removed - cannot rollback to old scheduler
- ✅ **Data Safe**: Your videos, artists, and downloads are not affected
- ✅ **Settings Migrated**: Most settings automatically converted
- ⚠️ **New Dependencies**: Requires Celery Beat and Redis

---

## Breaking Changes

### 1. Removed Services

**Removed Files:**
- `src/services/scheduler_service.py`
- `src/services/enhanced_scheduler_service.py`
- `src/api/fastapi/enhanced_scheduler.py`

**Replacement:**
- `src/services/scheduler_service_v2.py`
- `src/api/fastapi/scheduler_v2.py`
- `src/api/fastapi/scheduled_jobs.py`

### 2. API Endpoint Changes

**Deprecated Endpoints:**
```
POST /api/scheduler/start        → Use /api/v2/scheduler/start
POST /api/scheduler/stop         → Use /api/v2/scheduler/stop
GET  /api/scheduler/status       → Use /api/v2/scheduler/status
POST /api/scheduler/trigger      → Use /api/v2/scheduler/trigger/discovery
```

**New Endpoints:**
- All scheduler endpoints now under `/api/v2/scheduler`
- Job management endpoints under `/api/v2/jobs`
- Artist scheduling under `/api/artists/{id}/scheduling`

### 3. Configuration Changes

**Settings Renamed/Changed:**
- `scheduler_enabled` → `scheduler_v2_enabled`
- `scheduler_interval` → Replaced by per-schedule configuration
- Artist-level scheduling now available

### 4. Database Schema Changes

**New Tables:**
- `scheduled_jobs` - Job tracking and history

**New Artist Columns:**
- `discovery_interval_hours`
- `last_discovery`
- `last_download`
- `discovery_enabled`
- `download_enabled`
- `max_videos_per_discovery`
- `schedule_priority`

**New Download Columns:**
- `retry_count`
- `last_attempt`
- `last_error`
- `next_retry_at`

---

## Pre-Migration Checklist

### 1. Backup Your Data

```bash
# Backup database
mysqldump -u mvidarr -p mvidarr > mvidarr_backup_$(date +%Y%m%d).sql

# Backup configuration
cp -r /path/to/mvidarr /path/to/mvidarr_backup_$(date +%Y%m%d)
```

### 2. Verify Prerequisites

**Required:**
- Python 3.8+
- MariaDB/MySQL
- Redis server
- Celery

**Check Redis:**
```bash
redis-cli ping
# Should return: PONG
```

**Check Celery:**
```bash
pip list | grep celery
# Should show: celery==5.x.x
```

### 3. Stop Old Scheduler

```bash
# Stop MVidarr application
systemctl stop mvidarr

# Or if running manually
pkill -f "mvidarr"
```

### 4. Update Codebase

```bash
cd /path/to/mvidarr
git fetch origin
git checkout feature-schedule  # Or main when merged
git pull
```

### 5. Install Dependencies

```bash
# Activate virtualenv
source venv/bin/activate

# Install/update requirements
pip install -r requirements.txt
```

---

## Migration Steps

### Step 1: Run Database Migration

The database migration creates new tables and columns for Scheduler V2.

```bash
cd /path/to/mvidarr

# Run migration
python migrations/019_add_scheduler_v2_tables.py

# Expected output:
# ✅ Created scheduled_jobs table
# ✅ Added artist scheduling columns
# ✅ Added download retry columns
# ✅ Created indexes
```

**Verify Migration:**
```bash
# Check tables exist
mysql -u mvidarr -p mvidarr -e "SHOW TABLES LIKE 'scheduled_jobs';"

# Check artist columns
mysql -u mvidarr -p mvidarr -e "DESCRIBE artists;" | grep discovery_enabled
```

### Step 2: Run Data Migration

The data migration script sets default values for new fields.

```bash
# Dry run first (preview changes)
python scripts/migrate_to_scheduler_v2.py --dry-run

# Review output, then run for real
python scripts/migrate_to_scheduler_v2.py

# Expected output:
# ✅ Migration completed successfully!
#    Artists updated: 50
#    Artists skipped: 0
#    Downloads updated: 120
#    Errors: 0
```

### Step 3: Verify Migration

Run the verification script to ensure migration was successful.

```bash
python scripts/verify_scheduler_v2_migration.py

# Expected output:
# ✅ Verification passed - Migration successful!
#    Schema valid: Yes
#    Artists valid: 50
#    Artists invalid: 0
#    Downloads valid: 120
#    Issues found: 0
```

**If verification fails:**
- Review issues in output
- Fix issues manually or re-run migration
- Re-run verification

### Step 4: Update Configuration

#### A. Update Global Settings

**Via Database:**
```sql
-- Enable Scheduler V2
UPDATE settings SET value='true' WHERE key='scheduler_v2_enabled';

-- Set worker count (optional)
INSERT INTO settings (key, value) VALUES ('scheduler_v2_worker_count', '3')
ON DUPLICATE KEY UPDATE value='3';

-- Set discovery schedule (optional)
UPDATE settings SET value='daily' WHERE key='auto_discovery_schedule_days';
UPDATE settings SET value='06:00' WHERE key='auto_discovery_schedule_time';
```

**Via Settings UI:**
1. Navigate to **Settings** → **Scheduler**
2. Enable **Scheduler V2**
3. Configure schedules as needed
4. Click **Save**

#### B. Configure Per-Artist Settings (Optional)

For artists that need custom scheduling:

**Via API:**
```bash
curl -X PUT http://localhost:5000/api/artists/123/scheduling \
  -H "Content-Type: application/json" \
  -d '{
    "discovery_enabled": true,
    "download_enabled": true,
    "discovery_interval_hours": 12,
    "schedule_priority": "high"
  }'
```

**Via Web UI:**
1. Navigate to **Artists** → Select artist
2. Click **Scheduling** tab
3. Configure settings
4. Click **Save**

### Step 5: Start Celery Workers

Scheduler V2 requires Celery workers to be running.

**Option A: systemd Service**

Create `/etc/systemd/system/mvidarr-celery-worker.service`:
```ini
[Unit]
Description=MVidarr Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=mvidarr
Group=mvidarr
WorkingDirectory=/path/to/mvidarr
Environment="PATH=/path/to/mvidarr/venv/bin"
ExecStart=/path/to/mvidarr/venv/bin/celery -A src.jobs.celery_app worker \
          --loglevel=info \
          --concurrency=3 \
          --queues=scheduler,default
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
systemctl daemon-reload
systemctl enable mvidarr-celery-worker
systemctl start mvidarr-celery-worker
```

**Option B: Docker Compose**

Add to `docker-compose.yml`:
```yaml
services:
  celery-worker:
    image: mvidarr:latest
    command: celery -A src.jobs.celery_app worker --loglevel=info --concurrency=3 --queues=scheduler,default
    depends_on:
      - redis
      - db
    environment:
      - REDIS_HOST=redis
      - DB_HOST=db
```

**Option C: Manual Start**
```bash
cd /path/to/mvidarr
source venv/bin/activate
celery -A src.jobs.celery_app worker --loglevel=info --concurrency=3 --queues=scheduler,default &
```

### Step 6: Start Celery Beat

Celery Beat manages the schedule.

**Option A: systemd Service**

Create `/etc/systemd/system/mvidarr-celery-beat.service`:
```ini
[Unit]
Description=MVidarr Celery Beat
After=network.target redis.service

[Service]
Type=simple
User=mvidarr
Group=mvidarr
WorkingDirectory=/path/to/mvidarr
Environment="PATH=/path/to/mvidarr/venv/bin"
ExecStart=/path/to/mvidarr/venv/bin/celery -A src.jobs.celery_app beat --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
systemctl enable mvidarr-celery-beat
systemctl start mvidarr-celery-beat
```

**Option B: Docker Compose**
```yaml
services:
  celery-beat:
    image: mvidarr:latest
    command: celery -A src.jobs.celery_app beat --loglevel=info
    depends_on:
      - redis
      - celery-worker
```

**Option C: Manual Start**
```bash
celery -A src.jobs.celery_app beat --loglevel=info &
```

### Step 7: Start MVidarr Application

```bash
# systemd
systemctl start mvidarr

# Docker
docker-compose up -d

# Manual
cd /path/to/mvidarr
source venv/bin/activate
python app.py
```

---

## Post-Migration Verification

### 1. Check Scheduler Status

**Via Web UI:**
1. Navigate to `/scheduler/dashboard`
2. Verify status shows "Running"
3. Check statistics display correctly

**Via API:**
```bash
curl http://localhost:5000/api/v2/scheduler/status
```

Expected response:
```json
{
  "status": "running",
  "enabled": true,
  "celery_connected": true,
  "schedules": {...},
  "statistics": {...}
}
```

### 2. Verify Celery Workers

```bash
celery -A src.jobs.celery_app status

# Expected output:
# celery@hostname: OK
#
# 3 nodes online.
```

### 3. Test Manual Trigger

**Via Web UI:**
1. Go to `/scheduler/dashboard`
2. Click **Trigger Discovery**
3. Confirm action
4. Check "Recent Jobs" for new entry

**Via API:**
```bash
curl -X POST http://localhost:5000/api/v2/scheduler/trigger/discovery
```

### 4. Monitor First Scheduled Run

Wait for the next scheduled discovery/download time and verify:
1. Job appears in scheduled_jobs table
2. Job completes successfully
3. Artists/videos updated as expected

### 5. Check Logs

```bash
# Application logs
tail -f /var/log/mvidarr/mvidarr.log | grep scheduler

# Celery worker logs
tail -f /var/log/mvidarr/celery-worker.log

# Celery beat logs
tail -f /var/log/mvidarr/celery-beat.log
```

---

## Rollback Procedure

### ⚠️ Important: Limited Rollback

Scheduler V2 removes legacy scheduler code. You cannot rollback to the old scheduler without restoring from backup.

### Full Rollback (Last Resort)

**Step 1: Stop Services**
```bash
systemctl stop mvidarr mvidarr-celery-worker mvidarr-celery-beat
```

**Step 2: Restore Database**
```bash
mysql -u mvidarr -p mvidarr < mvidarr_backup_YYYYMMDD.sql
```

**Step 3: Restore Codebase**
```bash
cd /path/to/mvidarr_backup_YYYYMMDD
cp -r * /path/to/mvidarr/
```

**Step 4: Restart Services**
```bash
systemctl start mvidarr
```

### Partial Rollback (Disable Scheduler Only)

If you want to disable scheduling but keep v0.10.1:

```sql
UPDATE settings SET value='false' WHERE key='scheduler_v2_enabled';
```

Then restart MVidarr. Scheduled discovery/downloads will not run, but manual operations work normally.

---

## Common Issues

### Issue: "scheduled_jobs table doesn't exist"

**Cause:** Database migration not run

**Solution:**
```bash
python migrations/019_add_scheduler_v2_tables.py
```

### Issue: "Celery not connected"

**Cause:** Celery workers not running or Redis down

**Solution:**
```bash
# Check Redis
redis-cli ping

# Start Celery workers
systemctl start mvidarr-celery-worker mvidarr-celery-beat

# Or manually
celery -A src.jobs.celery_app worker --loglevel=info --concurrency=3 &
celery -A src.jobs.celery_app beat --loglevel=info &
```

### Issue: "Jobs not running"

**Cause:** Schedule not configured or disabled

**Solution:**
1. Check `scheduler_v2_enabled=true`
2. Verify schedules in database: `SELECT * FROM settings WHERE key LIKE '%schedule%';`
3. Check Celery Beat logs for errors

### Issue: "Artists not updating"

**Cause:** Migration didn't set default values

**Solution:**
```bash
python scripts/migrate_to_scheduler_v2.py
```

### Issue: "Permission denied on Celery"

**Cause:** User permissions

**Solution:**
```bash
# Fix ownership
chown -R mvidarr:mvidarr /path/to/mvidarr

# Fix permissions
chmod +x /path/to/mvidarr/venv/bin/celery
```

---

## Support

If you encounter issues not covered in this guide:

1. **Check Logs**: Review application, Celery worker, and Beat logs
2. **Run Verification**: `python scripts/verify_scheduler_v2_migration.py`
3. **GitHub Issues**: https://github.com/prefect421/mvidarr/issues
4. **Documentation**: See `docs/SCHEDULER_V2.md` for detailed documentation

---

**Version:** v0.10.1
**Last Updated:** December 2024
**Migration Support:** GitHub Issues
