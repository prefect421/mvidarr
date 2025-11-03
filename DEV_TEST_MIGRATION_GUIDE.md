# Migration Guide: Dev Test Environment to 3-Container Architecture

**Environment**: Dev Test (http://localhost:5001)
**Location**: /home/mike/Docker_Drives/mvidarr-Test/

## Overview

This guide will help you migrate your dev test environment from the old 6-container setup to the new simplified 3-container architecture.

### What's Changing

**Before (6 containers):**
- mvidarr
- mvidarr-mariadb
- mvidarr-redis
- mvidarr-celery-worker ❌ **REMOVED**
- mvidarr-celery-beat ❌ **REMOVED**
- (possibly flower) ❌ **REMOVED**

**After (3 containers):**
- mvidarr (now includes FastAPI + Celery worker + Beat via supervisord)
- mvidarr-mariadb
- mvidarr-redis

## Migration Steps

### Step 1: Backup Your Data

```bash
# Stop all running containers
cd /path/to/your/docker-compose/directory
docker-compose down

# Your data is safe in /home/mike/Docker_Drives/mvidarr-Test/
# Database: /home/mike/Docker_Drives/mvidarr-Test/database/mariadb/
# Videos: /home/mike/Docker_Drives/mvidarr-Test/data/music_videos/
# Downloads: /home/mike/Docker_Drives/mvidarr-Test/data/downloads/
# All other data preserved in their respective directories
```

### Step 2: Replace docker-compose.yml

```bash
# Copy the new docker-compose file from the mvidarr repo
cp /home/mike/mvidarr/docker-compose.dev-test.yml /path/to/your/compose/directory/docker-compose.yml

# Or if you want to keep both:
cp /home/mike/mvidarr/docker-compose.dev-test.yml /path/to/your/compose/directory/
mv docker-compose.yml docker-compose.yml.old
mv docker-compose.dev-test.yml docker-compose.yml
```

### Step 3: Pull Latest Dev Image

```bash
# Pull the latest dev image with supervisord support
docker pull ghcr.io/prefect421/mvidarr:dev
```

### Step 4: Start New 3-Container Setup

```bash
# Start with the new configuration
docker-compose up -d

# Monitor the startup
docker-compose logs -f mvidarr
```

### Step 5: Verify Everything is Running

```bash
# Check that only 3 containers are running
docker-compose ps

# Expected output:
# NAME                  STATUS
# mvidarr               Up (healthy)
# mvidarr-mariadb       Up (healthy)
# mvidarr-redis         Up (healthy)

# Verify processes inside mvidarr container
docker exec mvidarr ps aux | grep -E "(fastapi|celery|supervisord)"

# Expected to see:
# - supervisord (PID 1)
# - python3 fastapi_app.py
# - celery worker processes
```

### Step 6: Check Supervisord Status

```bash
# View supervisord log
docker exec mvidarr tail -f /app/data/logs/supervisord.log

# Check FastAPI logs
docker exec mvidarr tail -f /app/data/logs/fastapi.log

# Check Celery logs
docker exec mvidarr tail -f /app/data/logs/celery-worker.log
```

### Step 7: Test the Application

```bash
# Test health endpoint
curl http://localhost:5001/api/health

# Test web interface
# Open browser to: http://localhost:5001

# Test background jobs
# Navigate to an artist page and click "Enrich from all sources"
# Should show real-time progress
```

## Troubleshooting

### Issue: Containers won't start

```bash
# Check logs
docker-compose logs

# Common fix: Clean restart
docker-compose down -v
docker-compose up -d
```

### Issue: FastAPI not starting

```bash
# Check FastAPI error logs
docker exec mvidarr tail -100 /app/data/logs/fastapi_error.log

# Check if database is accessible
docker exec mvidarr python -c "from src.database.connection import get_db; print('DB OK')"
```

### Issue: Celery worker not running

```bash
# Check Celery error logs
docker exec mvidarr tail -100 /app/data/logs/celery-worker_error.log

# Check Redis connection
docker exec mvidarr redis-cli -h mvidarr-redis -p 6379 -a mvidarr_redis_password ping
```

### Issue: Jobs stuck in "Queued"

```bash
# Verify Celery worker is running
docker exec mvidarr ps aux | grep celery

# Restart just the Celery worker (keeps FastAPI running)
docker exec mvidarr supervisorctl restart celery-worker

# Check worker status
docker exec mvidarr tail -f /app/data/logs/celery-worker.log
```

## Key Differences

### Managing Services

**Old way (separate containers):**
```bash
docker-compose restart celery-worker
docker-compose restart celery-beat
```

**New way (supervisord inside mvidarr):**
```bash
# Restart specific service
docker exec mvidarr supervisorctl restart celery-worker
docker exec mvidarr supervisorctl restart fastapi

# Or restart entire container
docker-compose restart mvidarr
```

### Viewing Logs

**Old way:**
```bash
docker logs mvidarr-celery-worker
docker logs mvidarr-celery-beat
```

**New way:**
```bash
# All logs in one container
docker logs mvidarr

# Or specific service logs
docker exec mvidarr tail -f /app/data/logs/celery-worker.log
docker exec mvidarr tail -f /app/data/logs/fastapi.log
```

### Scaling Workers

**Old way:**
```bash
docker-compose up -d --scale celery-worker=5
```

**New way:**
```bash
# Edit docker-compose.yml and change:
- JOB_WORKER_COUNT=5

# Then restart
docker-compose restart mvidarr
```

## Benefits of New Architecture

✅ **Simpler Management**: Only 3 containers instead of 6
✅ **Lower Resource Usage**: Reduced container overhead
✅ **Easier Troubleshooting**: All app logs in one place
✅ **Same Functionality**: All background jobs work exactly the same
✅ **Better for Home Use**: Optimized for consumer-grade deployments

## Rollback (If Needed)

If you need to rollback to the old setup:

```bash
# Stop new setup
docker-compose down

# Restore old compose file
mv docker-compose.yml.old docker-compose.yml

# Start old setup
docker-compose up -d
```

## Support

If you encounter issues:

1. Check logs in `/home/mike/Docker_Drives/mvidarr-Test/data/logs/`
2. Verify all 3 containers are healthy: `docker-compose ps`
3. Check supervisord status: `docker exec mvidarr supervisorctl status`
4. Review error logs for specific services

---

**Questions?** Check the main DEPLOYMENT_GUIDE.md for detailed troubleshooting steps.
