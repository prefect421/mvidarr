# MVidarr Scripts

This directory contains utility scripts for MVidarr installation, maintenance, and administration.

**Last Updated**: 2025-10-29 (Phase 5 Cleanup)

---

## Table of Contents

- [Production Scripts](#production-scripts)
- [Installation & Setup](#installation--setup)
- [Utilities & Maintenance](#utilities--maintenance)
- [Development Tools](#development-tools)
- [Archived Scripts](#archived-scripts)

---

## Production Scripts

### `reset_stuck_downloads.py`

**Purpose**: Automatically cleans up downloads stuck in intermediate states during system startup

**Integration**: Runs via systemd `ExecStartPre` in `mvidarr.service`

**Why This Is Needed**:
- When the system restarts unexpectedly, downloads can be left in intermediate states
- The ytdlp_service uses in-memory queues that don't persist across restarts
- Stuck downloads prevent proper re-queuing through the web interface

**What It Does**:
1. **Scans** the database for downloads with status: `pending`, `queued`, or `downloading`
2. **Resets** them to `wanted` status
3. **Clears** progress and adds a reset message explaining when and why the reset occurred
4. **Logs** the operation with detailed statistics

**Manual Execution**:
```bash
cd /home/mike/mvidarr
python3 scripts/reset_stuck_downloads.py
```

**Output Example**:
```
============================================================
MVidarr Download Cleanup - System Startup
============================================================
[2025-09-23 13:12:18] Starting download cleanup...
📊 Found 7 stuck downloads:
   - downloading: 7 downloads
🔄 Reset download 540: 'ATARASHII GAKKO! - 青春を切り裂く波動...' (downloading → wanted)
✅ Successfully reset 7/7 downloads to 'wanted' status
🎯 Downloads can now be properly re-queued through the web interface
============================================================
✅ Download cleanup completed successfully
```

**Status Meanings**:
- **wanted**: Ready to be downloaded via web interface
- **pending**: Queued for processing but not started
- **queued**: In download queue waiting to start
- **downloading**: Currently being downloaded
- **completed**: Successfully downloaded
- **failed**: Download failed with error

---

### `manage-services.sh`

**Purpose**: Comprehensive service management utility for MVidarr systemd services

**Usage**:
```bash
./scripts/manage-services.sh [command]

Commands:
  start       Start all MVidarr services
  stop        Stop all MVidarr services
  restart     Restart all MVidarr services
  status      Show status of all services
  logs        Show recent logs from all services
  enable      Enable services to start on boot
  disable     Disable services from starting on boot
```

**Services Managed**:
- `mvidarr.service` - Main application
- `mvidarr-celery-worker.service` - Background job worker
- `mvidarr-celery-beat.service` - Scheduled tasks
- `mvidarr-redis.service` - Redis cache/queue

**Examples**:
```bash
# Restart all services
./scripts/manage-services.sh restart

# Check status
./scripts/manage-services.sh status

# View recent logs
./scripts/manage-services.sh logs
```

---

### `health_check.sh`

**Purpose**: System health monitoring and validation script

**Usage**:
```bash
./scripts/health_check.sh
```

**Checks**:
- MVidarr service status
- Redis connectivity
- MySQL/MariaDB connectivity
- Disk space usage
- API endpoint responsiveness
- Log file health

**Output**: Returns exit code 0 if healthy, non-zero if issues detected

---

## Installation & Setup

### `install.sh`

**Purpose**: Main installation script for MVidarr on Linux systems

**Usage**:
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

**What It Does**:
1. Checks system requirements (Python 3.11+, MySQL/MariaDB, Redis)
2. Creates Python virtual environment
3. Installs dependencies from requirements.txt
4. Sets up database schema
5. Creates initial configuration
6. Sets up systemd services
7. Configures file permissions

**Requirements**:
- Ubuntu/Debian-based Linux
- Python 3.11 or higher
- MySQL 8.0+ or MariaDB 10.5+
- Redis 6.0+
- FFmpeg (for video processing)

---

### `install_service.sh`

**Purpose**: Install MVidarr as a systemd service

**Usage**:
```bash
sudo ./scripts/install_service.sh
```

**What It Does**:
1. Copies service files to `/etc/systemd/system/`
2. Sets proper permissions
3. Reloads systemd daemon
4. Enables services for auto-start on boot

**Service Files Installed**:
- `mvidarr.service` - Main application
- `mvidarr-celery-worker.service` - Background workers
- `mvidarr-celery-beat.service` - Scheduled tasks

---

### `setup_database.sh`

**Purpose**: Initialize or reset MVidarr database schema

**Usage**:
```bash
./scripts/setup_database.sh [--reset]

Options:
  --reset    Drop existing database and recreate (WARNING: Data loss!)
```

**What It Does**:
1. Creates database if it doesn't exist
2. Runs all migrations in order
3. Creates default admin user
4. Sets up initial settings

**Default Admin Credentials**:
- Username: `admin`
- Password: `mvidarr` (change after first login!)

---

### `setup_production.py`

**Purpose**: Configure MVidarr for production deployment

**Usage**:
```bash
python3 scripts/setup_production.py
```

**What It Does**:
1. Generates secure secret keys
2. Sets production environment variables
3. Configures logging
4. Sets up SSL/TLS if certificates available
5. Optimizes database settings
6. Configures Gunicorn workers

---

## Utilities & Maintenance

### `update_version.sh`

**Purpose**: Update version metadata with current git commit information

**Usage**:
```bash
./scripts/update_version.sh
```

**What It Does**:
1. Gets current git commit hash
2. Gets current timestamp
3. Updates `version.json` with commit and build date
4. Preserves version number and features list

**When to Use**:
- Before pushing to dev branch
- Before creating releases
- After significant commits

**Example**:
```bash
# Update version metadata
./scripts/update_version.sh

# Commit the updated version file
git add version.json
git commit -m "Update version metadata"
git push origin dev
```

---

### `generate_secret_key.py`

**Purpose**: Generate cryptographically secure secret keys for Flask/FastAPI

**Usage**:
```bash
python3 scripts/generate_secret_key.py
```

**Output**: Prints a secure random key suitable for `SECRET_KEY` environment variable

**Example**:
```bash
# Generate new secret key
SECRET_KEY=$(python3 scripts/generate_secret_key.py)
echo "SECRET_KEY=$SECRET_KEY" >> .env
```

---

### Backfill Scripts

#### `backfill_video_years.py`

**Purpose**: Intelligent year extraction for video metadata using multiple methods

**Usage**:
```bash
python3 scripts/backfill_video_years.py [options]

Options:
  --dry-run       Show what would be updated without making changes
  --limit N       Process only N videos
  --video-id ID   Process specific video by ID
```

**Methods Used** (in order of preference):
1. Year from video description
2. Year from YouTube info.json metadata
3. Year from upload date

**Example**:
```bash
# Dry run to see what would change
python3 scripts/backfill_video_years.py --dry-run

# Process first 100 videos
python3 scripts/backfill_video_years.py --limit 100

# Process specific video
python3 scripts/backfill_video_years.py --video-id 123
```

#### Other Backfill Scripts:
- `backfill_year_from_descriptions.py` - Extract from descriptions only
- `backfill_year_from_info_json.py` - Extract from YouTube metadata only
- `backfill_year_from_upload_date.py` - Use upload date as fallback

---

### Database Management

#### `reset_database.py`

**Purpose**: Reset database to clean state (⚠️ DESTRUCTIVE)

**Usage**:
```bash
python3 scripts/reset_database.py --confirm

Options:
  --confirm       Required confirmation flag
  --keep-users    Preserve user accounts
```

**WARNING**: This will delete ALL data! Use only for testing/development.

---

#### `troubleshoot_database.py`

**Purpose**: Diagnose and fix common database issues

**Usage**:
```bash
python3 scripts/troubleshoot_database.py
```

**Checks**:
- Database connectivity
- Table integrity
- Index health
- Foreign key constraints
- Orphaned records
- Disk space

---

### User Management

#### `create_admin_user.py`

**Purpose**: Create a new admin user account

**Usage**:
```bash
python3 scripts/create_admin_user.py
```

**Interactive**: Prompts for username, password, and email

---

#### `reset_admin_credentials.py`

**Purpose**: Reset admin password if locked out

**Usage**:
```bash
python3 scripts/reset_admin_credentials.py

Options:
  --username USER    Username to reset (default: admin)
  --password PASS    New password (prompted if not provided)
```

---

## Development Tools

### `testing/run_comprehensive_tests.py`

**Purpose**: Run comprehensive test suite (pre-Playwright)

**Note**: May be superseded by Playwright E2E tests in `tests/playwright/`

---

### `testing/manual_test_checklist.py`

**Purpose**: Interactive manual testing checklist

**Usage**:
```bash
python3 scripts/testing/manual_test_checklist.py
```

---

## Archived Scripts

See `scripts/archive/README.md` for information about archived/obsolete scripts.

**Archived Categories**:
- AI development helpers
- Screenshot/documentation generators
- Manual restart scripts (superseded by systemd)
- Phase-specific development tools
- One-time data fix scripts

---

## Contributing New Scripts

When adding new scripts to this directory:

1. **Add header comments**:
   ```python
   #!/usr/bin/env python3
   """
   Script Name: script_name.py
   Purpose: Brief description
   Usage: python3 scripts/script_name.py [options]
   Author: Your Name
   Date: YYYY-MM-DD
   """
   ```

2. **Update this README** with:
   - Script name and purpose
   - Usage instructions
   - Examples
   - Dependencies (if any)

3. **Set executable permissions** (for shell scripts):
   ```bash
   chmod +x scripts/script_name.sh
   ```

4. **Test before committing**:
   - Test with sample data
   - Test error handling
   - Document any environment variables needed

---

## Directory Structure

```
scripts/
├── README.md                    # This file
├── archive/                     # Obsolete scripts (preserved for history)
├── migrations/                  # Database migrations (⚠️ DO NOT DELETE)
├── deployment/                  # Deployment scripts
├── monitoring/                  # Monitoring utilities
├── release/                     # Release management
├── setup/                       # Setup utilities
└── testing/                     # Test utilities
```

---

## Support

For issues with scripts:
1. Check script header comments for requirements
2. Verify environment variables are set correctly
3. Check systemd logs: `journalctl -u mvidarr -n 50`
4. Create an issue on GitHub with error details

---

**Maintenance**: This documentation is updated as part of milestone releases. Last reviewed during Phase 5 (Cleanup) of milestone 0.9.9.