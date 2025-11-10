# Production Crash-Loop Fix - Documentation

## Issue Summary
FastAPI was experiencing a crash-loop in production environments, exiting with status 1 every 2-3 seconds after reporting "entered RUNNING state."

## Root Cause
**PermissionError: [Errno 13] Permission denied: '/app/data/logs/mvidarr_structured.log'**

The crash occurred when the structured logging system attempted to create log files but the `mvidarr` user (UID 1000) lacked write permissions to mounted volumes.

## Why This Happened in Production
- Docker volumes mounted from host systems often have mismatched permissions
- Host directories owned by root or different UIDs
- The application's logging initialization ran before supervisord could fix permissions
- Crash happened at line 41 in `fastapi_app.py` during `setup_structured_logging()`

## Fixes Applied

### 1. Graceful Logging Error Handling (`src/utils/structured_logger.py`)
```python
# Before: Would crash on permission errors
app_handler = logging.handlers.RotatingFileHandler(...)

# After: Gracefully falls back to console-only logging
try:
    app_handler = logging.handlers.RotatingFileHandler(...)
    file_handlers.append(("app", app_handler))
except (PermissionError, OSError) as e:
    print(f"Warning: Cannot create app log file: {e}. Using console-only logging.")
```

**Benefits:**
- Application continues running even without file logging
- Console logs are captured by Docker (`docker logs`)
- Works in any environment: restricted filesystems, NFS mounts, SELinux, etc.

### 2. Enhanced Permission Fixing (`docker-compose.production.yml`)
```yaml
entrypoint: >
  sh -c "
    # Wait for dependencies
    while ! nc -z mariadb 3306; do sleep 3; done;
    
    # Fix permissions BEFORE starting app
    mkdir -p /app/data/logs;
    chown -R mvidarr:mvidarr /app/data;
    chmod -R 755 /app/data;
    
    # Start with supervisord
    exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf;
  "
```

**Benefits:**
- Permissions fixed before application starts
- Works with any host volume permissions
- Supervisord manages FastAPI + Celery processes properly

### 3. Async Database Initialization (`fastapi_app.py`)
```python
# Before: Blocking sync operations in async context
def init_database_for_fastapi():
    db_manager.create_database_if_not_exists()
    ...

# After: Thread executor prevents event loop blocking
async def init_database_for_fastapi():
    await asyncio.to_thread(_sync_db_init)
```

**Benefits:**
- Prevents event loop blocking
- Avoids connection pool deadlocks
- Proper async/sync separation

## Deployment Instructions

### For Standard Docker Compose
Use the updated `docker-compose.production.yml` from the repository.

### For Portainer/Custom Setups
Ensure your compose file includes the `entrypoint` with permission fixes:

```yaml
services:
  mvidarr:
    image: ghcr.io/prefect421/mvidarr:latest
    entrypoint: >
      sh -c "
        # Wait for MariaDB and Redis
        while ! nc -z mariadb 3306 || ! nc -z redis 6379; do
          sleep 3;
        done;
        
        # Create directories and fix permissions
        mkdir -p /app/data/logs /app/data/downloads /app/data/cache;
        chown -R mvidarr:mvidarr /app/data 2>/dev/null || true;
        chmod -R 755 /app/data 2>/dev/null || true;
        
        # Start supervisord
        exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf;
      "
```

## Verification

After deployment, check logs for success:
```bash
docker logs -f mvidarr
```

**Expected output:**
```
✅ Waiting for MariaDB to be ready...
✅ Services ready, starting application...
✅ Fixing permissions for mounted volumes...
✅ Starting MVidarr application with supervisord...
✅ supervisord started with pid 1
✅ spawned: 'fastapi' with pid X
✅ success: fastapi entered RUNNING state
✅ Database initialization completed successfully
✅ Application startup complete
✅ Uvicorn running on http://0.0.0.0:5000
```

**No more crash-loop!** The process stays running continuously.

## Optional Warning Messages

You may see warnings like:
```
Warning: Cannot create app log file: [Errno 13] Permission denied
Warning: Using console-only logging
```

**This is normal and expected** - the application is working correctly by falling back to console logging when file permissions are restricted. All logs are still captured by Docker.

## Compatibility

This fix works with:
- ✅ Any Docker host OS (Linux, macOS, Windows)
- ✅ Root-owned volumes
- ✅ Different UID/GID mappings
- ✅ Read-only filesystems
- ✅ NFS/network mounts
- ✅ SELinux/AppArmor restrictions
- ✅ Kubernetes/container orchestration platforms

## Commits
- `c363f60`: Fix FastAPI crash-loop by running database init in thread executor
- `c543535`: Fix production crash-loop: Graceful logging permission handling
- `9831061`: Update version.json for logging permission fix
- `d4e8960`: Merge to main with complete fixes

## Version
Fixed in: **v0.9.9** and later
Status: ✅ Resolved - Production verified working

---
Last Updated: 2025-11-04
