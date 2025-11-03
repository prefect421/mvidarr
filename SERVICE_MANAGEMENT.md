# MVidarr Service Management Guide

## Overview

MVidarr runs as a systemd service with three main components:
1. **mvidarr.service** - Main FastAPI application (port 5000)
2. **mvidarr-celery-worker.service** - Background job processor
3. **mvidarr-celery-beat.service** - Task scheduler

## Quick Start

### Using the Management Script (Recommended)

```bash
# Show service status
./scripts/manage-services.sh status

# Start all services
./scripts/manage-services.sh start

# Stop all services
./scripts/manage-services.sh stop

# Restart all services
./scripts/manage-services.sh restart

# View logs
./scripts/manage-services.sh logs                    # Main app logs
./scripts/manage-services.sh logs mvidarr-celery-worker  # Worker logs
```

### Manual Service Management

```bash
# Start services in order
sudo systemctl start mvidarr
sudo systemctl start mvidarr-celery-worker
sudo systemctl start mvidarr-celery-beat

# Stop services (reverse order)
sudo systemctl stop mvidarr-celery-beat
sudo systemctl stop mvidarr-celery-worker
sudo systemctl stop mvidarr

# Check status
sudo systemctl status mvidarr
sudo systemctl status mvidarr-celery-worker
sudo systemctl status mvidarr-celery-beat
```

## Service Dependencies

### Dependency Chain
```
mvidarr.service (Main App)
  ├── Requires: redis.service
  ├── After: mysql.service, mariadb.service
  │
  ├─> mvidarr-celery-worker.service (Background Jobs)
  │     ├── Requires: mvidarr.service, redis.service
  │     └── BindsTo: mvidarr.service
  │
  └─> mvidarr-celery-beat.service (Scheduler)
        ├── Requires: mvidarr.service, redis.service
        ├── After: mvidarr-celery-worker.service
        └── BindsTo: mvidarr.service
```

### What This Means
- **BindsTo**: If main app stops, dependent services stop automatically
- **PartOf**: Dependent services are part of the main service lifecycle
- **PropagatesStopTo**: Stopping main app stops all dependent services
- **After**: Service waits for dependencies before starting

## Service Configuration

### Main Application (mvidarr.service)

**Location**: `/etc/systemd/system/mvidarr.service`

**Key Features**:
- FastAPI application on port 5000
- Modular architecture with 64+ specialized modules
- Full async/await support
- Automatic directory creation
- Enhanced resource limits

**Environment Variables**:
```bash
FASTAPI_ENV=production
MODULAR_ARCHITECTURE=enabled
ENTERPRISE_MODULES=enabled
E2E_TESTING_READY=true
MVIDARR_VERSION=0.9.9-dev
MVIDARR_PHASE=3-complete
```

### Celery Worker (mvidarr-celery-worker.service)

**Location**: `/etc/systemd/system/mvidarr-celery-worker.service`

**Key Features**:
- 4 concurrent workers (prefork pool)
- Max 100 tasks per child process
- Automatic worker recycling
- Optimized for modular architecture

**Settings**:
```bash
--concurrency=4
--max-tasks-per-child=100
--pool=prefork
```

### Celery Beat (mvidarr-celery-beat.service)

**Location**: `/etc/systemd/system/mvidarr-celery-beat.service`

**Key Features**:
- Persistent schedule storage
- Automatic schedule synchronization
- Runs after worker is ready

## Enable/Disable Auto-Start

### Enable Auto-Start on Boot
```bash
# Enable all services
./scripts/manage-services.sh enable

# Or manually
sudo systemctl enable mvidarr
sudo systemctl enable mvidarr-celery-worker
sudo systemctl enable mvidarr-celery-beat
```

### Disable Auto-Start
```bash
# Disable all services
./scripts/manage-services.sh disable

# Or manually
sudo systemctl disable mvidarr
sudo systemctl disable mvidarr-celery-worker
sudo systemctl disable mvidarr-celery-beat
```

## Updating Services

### After Code Changes
```bash
# 1. Stop services
./scripts/manage-services.sh stop

# 2. Pull latest code
cd /home/mike/mvidarr
git pull origin dev

# 3. Update dependencies (if needed)
source venv/bin/activate
pip install -r requirements.txt

# 4. Restart services
./scripts/manage-services.sh start
```

### After Service File Changes
```bash
# 1. Copy updated service files
sudo cp /tmp/mvidarr*.service /etc/systemd/system/

# 2. Reload systemd and restart
./scripts/manage-services.sh reload
```

## Troubleshooting

### Service Won't Start

1. **Check service status**:
   ```bash
   sudo systemctl status mvidarr
   ```

2. **View recent logs**:
   ```bash
   journalctl -u mvidarr -n 100 --no-pager
   ```

3. **Check dependencies**:
   ```bash
   # Redis must be running
   sudo systemctl status redis

   # Database must be accessible
   sudo systemctl status mariadb
   ```

4. **Test manually**:
   ```bash
   cd /home/mike/mvidarr
   source venv/bin/activate
   python fastapi_app.py
   ```

### Service Keeps Failing

1. **Check for port conflicts**:
   ```bash
   sudo netstat -tulpn | grep :5000
   sudo ss -tulpn | grep :5000
   ```

2. **Check permissions**:
   ```bash
   ls -la /home/mike/mvidarr/data/
   sudo chown -R mike:mike /home/mike/mvidarr/data/
   ```

3. **Check resource limits**:
   ```bash
   # View current limits
   systemctl show mvidarr | grep Limit
   ```

### Celery Worker Issues

1. **Check Redis connection**:
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

2. **View worker logs**:
   ```bash
   journalctl -u mvidarr-celery-worker -f
   ```

3. **Check worker status**:
   ```bash
   cd /home/mike/mvidarr
   source venv/bin/activate
   celery -A src.jobs.celery_app inspect active
   celery -A src.jobs.celery_app inspect stats
   ```

### Celery Beat Issues

1. **Check schedule file**:
   ```bash
   ls -la /home/mike/mvidarr/celerybeat-schedule
   ```

2. **Reset schedule** (if corrupted):
   ```bash
   sudo systemctl stop mvidarr-celery-beat
   rm /home/mike/mvidarr/celerybeat-schedule
   sudo systemctl start mvidarr-celery-beat
   ```

## Viewing Logs

### Real-time Log Monitoring
```bash
# Main application
journalctl -u mvidarr -f

# Celery worker
journalctl -u mvidarr-celery-worker -f

# Celery beat
journalctl -u mvidarr-celery-beat -f

# All MVidarr services
journalctl -u "mvidarr*" -f
```

### Historical Logs
```bash
# Last 100 lines
journalctl -u mvidarr -n 100

# Since specific time
journalctl -u mvidarr --since "2 hours ago"

# Specific date range
journalctl -u mvidarr --since "2025-10-17 00:00:00" --until "2025-10-17 23:59:59"

# Export to file
journalctl -u mvidarr > mvidarr.log
```

## Performance Monitoring

### Resource Usage
```bash
# CPU and Memory
systemctl status mvidarr
top -p $(pgrep -f fastapi_app.py)

# Open files
lsof -p $(pgrep -f fastapi_app.py) | wc -l

# Network connections
netstat -an | grep :5000
```

### Service Statistics
```bash
# Service uptime
systemctl show mvidarr | grep ActiveEnterTimestamp

# Restart count
systemctl show mvidarr | grep NRestarts

# Memory usage
systemctl show mvidarr | grep MemoryCurrent
```

## Best Practices

### Routine Maintenance
1. **Monitor logs regularly** for errors or warnings
2. **Check disk space** in `/home/mike/mvidarr/data/`
3. **Review Celery queue** for stuck tasks
4. **Update services** after major code changes

### Performance Optimization
1. **Adjust worker concurrency** based on CPU cores
2. **Monitor memory usage** and adjust if needed
3. **Review slow queries** in database logs
4. **Check Redis memory** usage

### Security
1. **Keep services updated** with latest security patches
2. **Monitor failed login attempts** in logs
3. **Review access logs** regularly
4. **Limit file permissions** on data directories

## Service Management Script Reference

### Commands
```bash
./scripts/manage-services.sh status     # Show all service status
./scripts/manage-services.sh start      # Start all services
./scripts/manage-services.sh stop       # Stop all services
./scripts/manage-services.sh restart    # Restart all services
./scripts/manage-services.sh enable     # Enable auto-start
./scripts/manage-services.sh disable    # Disable auto-start
./scripts/manage-services.sh reload     # Reload config and restart
./scripts/manage-services.sh logs [svc] # Show logs for service
./scripts/manage-services.sh help       # Show help
```

### Output Colors
- 🟢 **Green** - Service running normally
- 🔴 **Red** - Service failed
- 🟡 **Yellow** - Service inactive or warning

## Phase 3 Achievements

### Modular Architecture
- 64 specialized modules
- 71.4% average file size reduction
- Enterprise-grade code organization
- Clear separation of concerns

### E2E Testing Ready
- 122+ Playwright tests (100% passing)
- Multi-browser support
- CI/CD integration
- Comprehensive test documentation

### Production Ready
- Backward compatibility maintained
- All services properly orchestrated
- Enhanced resource limits
- Optimized for concurrent processing

---

**Version**: 0.9.9-dev (Phase 3 Complete)
**Last Updated**: 2025-10-17
**Services**: mvidarr, mvidarr-celery-worker, mvidarr-celery-beat
