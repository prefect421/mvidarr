# MVidarr Deployment Guide

**Version: 0.9.9 (Production-Ready)**

This guide covers deployment of MVidarr with Celery + Redis background job system, complete security hardening, and optimized production configuration.

## Overview

MVidarr now includes a robust background job processing system using Celery + Redis for:
- Metadata enrichment (artist/video data from external sources)
- Video download processing
- Image processing tasks
- FFmpeg operations
- Bulk operations

## Deployment Options

### Option 1: Docker Compose (Recommended)

#### Full Setup with Background Jobs
The default `docker-compose.yml` now includes Redis, Celery worker, beat scheduler, and Flower monitoring:

```bash
# Clone repository
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr

# Start all services
docker-compose up -d

# Services started:
# - MVidarr web application (port 5000)
# - MariaDB database (port 3306, localhost only)
# - Redis cache/job queue (port 6379, localhost only)
# - Celery worker (background job processing)
# - Celery beat (task scheduler)
# - Flower dashboard (port 5555, localhost only)
```

**Monitoring:**
- **Web Interface:** http://localhost:5000
- **Flower Dashboard:** http://localhost:5555 (admin/mvidarr123)

#### Minimal Setup (No Background Jobs)
If you don't need background job processing:

```bash
# Use minimal configuration
docker-compose -f docker-compose.minimal.yml up -d

# Only starts:
# - MVidarr web application
# - MariaDB database
```

#### Environment Variables
Create `.env` file in the project root:

```env
# Basic Configuration
MVIDARR_PORT=5000
DB_USER=mvidarr
DB_PASSWORD=secure_password_change_this
MYSQL_ROOT_PASSWORD=root_password_change_this
SECRET_KEY=your-secret-key-here-change-this

# Optional API Keys (for enhanced metadata)
IMVDB_API_KEY=your_imvdb_key
YOUTUBE_API_KEY=your_youtube_key

# System Configuration  
TZ=America/New_York
PUID=1000
PGID=1000

# Storage Paths (optional, uses ./volumes by default)
DOWNLOADS_PATH=./downloads
MUSIC_VIDEOS_PATH=./music_videos
DATABASE_FOLDER=./database
THUMBNAILS_PATH=./thumbnails
LOGS_PATH=./logs
CACHE_PATH=./cache

# Redis/Celery Ports (optional)
REDIS_PORT=6379
FLOWER_PORT=5555
```

### Option 2: Systemd Services (Linux Server)

For direct installation on Linux servers with systemd.

#### Prerequisites
```bash
# Install Redis
sudo apt update
sudo apt install redis-server

# Create Python virtual environment
cd /home/mike/mvidarr
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Service Installation
```bash
# Copy service files
sudo cp mvidarr.service /etc/systemd/system/
sudo cp mvidarr-redis.service /etc/systemd/system/
sudo cp mvidarr-celery-worker.service /etc/systemd/system/
sudo cp mvidarr-celery-beat.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable redis
sudo systemctl enable mvidarr-redis.service
sudo systemctl enable mvidarr.service
sudo systemctl enable mvidarr-celery-worker.service  
sudo systemctl enable mvidarr-celery-beat.service

# Start services
sudo systemctl start redis
sudo systemctl start mvidarr-redis.service
sudo systemctl start mvidarr.service
sudo systemctl start mvidarr-celery-worker.service
sudo systemctl start mvidarr-celery-beat.service

# Check status
sudo systemctl status mvidarr.service
sudo systemctl status mvidarr-celery-worker.service
```

#### Service Management Commands
```bash
# View logs
sudo journalctl -f -u mvidarr.service
sudo journalctl -f -u mvidarr-celery-worker.service

# Restart services
sudo systemctl restart mvidarr.service
sudo systemctl restart mvidarr-celery-worker.service

# Stop all MVidarr services
sudo systemctl stop mvidarr-celery-beat.service
sudo systemctl stop mvidarr-celery-worker.service
sudo systemctl stop mvidarr.service
sudo systemctl stop mvidarr-redis.service
```

## Configuration

### Redis Configuration
Redis is configured with:
- **Memory Limit:** 256MB (adjustable)
- **Persistence:** AOF (append-only file)
- **Eviction Policy:** allkeys-lru
- **Port:** 6379 (localhost only in Docker)

### Celery Configuration  
Celery workers are configured with:
- **Concurrency:** 3 workers (adjustable)
- **Queues:** metadata, video_downloads, image_processing, default
- **Time Limits:** 60min hard / 30min soft
- **Max Tasks per Child:** 100 (prevents memory leaks)

### Environment Variables for Background Jobs

#### Required
```bash
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
BACKGROUND_JOBS_ENABLED=true
JOB_SYSTEM_ENABLED=true
```

#### Optional
```bash
JOB_WORKER_COUNT=3              # Number of worker processes
JOB_WEBSOCKET_ENABLED=true      # Real-time progress updates
PYTHONPATH=/path/to/mvidarr     # Python path for imports
```

## Testing Deployment

### 1. Basic Health Check
```bash
# Test web interface
curl http://localhost:5000/api/health

# Expected response:
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

### 2. Background Jobs Test
```bash  
# Access artist page and test "Enrich from all sources"
# Navigate to: http://localhost:5000/artist/[ID]
# Click "Enrich from all sources" button
# Should show real-time progress, not stuck in "queued"
```

### 3. Flower Monitoring
```bash
# Access Flower dashboard
open http://localhost:5555

# Login: admin / mvidarr123
# Verify:
# - Workers tab shows active worker
# - Tasks tab shows completed jobs  
# - Monitor shows real-time statistics
```

### 4. Command Line Testing
```bash
# Test Celery worker directly (if using systemd)
cd /home/mike/mvidarr
source venv/bin/activate

# Check worker status
celery -A src.jobs.celery_app inspect stats

# Test task execution
python -c "
from src.jobs.metadata_tasks import enrich_artist_metadata_task
result = enrich_artist_metadata_task.delay(192, force_refresh=True)
print(f'Task ID: {result.id}')
print(f'Result: {result.get(timeout=60)}')
"
```

## Troubleshooting

### Common Issues

#### 1. Jobs Stuck in "Queued" Status
```bash
# Check Celery worker logs
docker logs mvidarr-celery-worker
# OR
sudo journalctl -f -u mvidarr-celery-worker.service

# Common fixes:
docker-compose restart celery-worker  # Docker
sudo systemctl restart mvidarr-celery-worker.service  # Systemd
```

#### 2. Redis Connection Failed
```bash
# Check Redis status  
docker logs mvidarr-redis
redis-cli ping  # Should return PONG

# Restart Redis
docker-compose restart redis
sudo systemctl restart redis
```

#### 3. Import/Path Errors
```bash
# Verify Python path
docker exec -it mvidarr-celery-worker python -c "import sys; print(sys.path)"

# Should include /app (Docker) or project path
# Set PYTHONPATH if needed
```

#### 4. Database Connection Issues
```bash
# Test database connection from worker
docker exec -it mvidarr-celery-worker python -c "
from src.database.connection import get_db
with get_db() as session:
    print('Database connection OK')
"
```

### Performance Tuning

#### Scaling Workers
```bash
# Docker: Scale to 5 workers  
docker-compose up -d --scale celery-worker=5

# Systemd: Create additional worker services
sudo cp mvidarr-celery-worker.service mvidarr-celery-worker-2.service
# Edit and change hostname: --hostname=worker2@%h
sudo systemctl enable mvidarr-celery-worker-2.service
sudo systemctl start mvidarr-celery-worker-2.service
```

#### Memory Management
```bash
# Increase Redis memory limit
# In docker-compose.yml, change Redis command:
command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru

# Monitor memory usage
docker stats mvidarr-redis mvidarr-celery-worker
```

## Migration from Old System

If you're upgrading from the old Flask job system:

### 1. Backup Database
```bash
# Docker
docker exec mvidarr-mariadb mysqldump -u root -p[password] mvidarr > backup.sql

# Direct
mysqldump -u root -p mvidarr > backup.sql
```

### 2. Stop Old Services
```bash
# Docker
docker-compose down

# Systemd  
sudo systemctl stop mvidarr.service
```

### 3. Update and Restart
```bash
# Pull latest changes
git pull origin dev

# Docker: Update and restart
docker-compose pull
docker-compose up -d

# Systemd: Restart services
sudo systemctl daemon-reload
sudo systemctl restart mvidarr.service
sudo systemctl start mvidarr-celery-worker.service
```

### 4. Verify Migration
```bash
# Test enrichment functionality
# Old system: Jobs would get stuck in "queued"
# New system: Jobs complete with real-time progress

# Check Flower for task history
open http://localhost:5555
```

## Production Deployment

### Security Considerations
- Change default passwords in `.env` file
- Use reverse proxy (nginx/Apache) for HTTPS
- Restrict Redis/Flower ports to localhost only
- Enable firewall rules
- Use strong SECRET_KEY values

### Performance Recommendations  
- Use SSD storage for Redis persistence
- Monitor worker memory usage
- Scale workers based on job load
- Set up log rotation for Docker containers
- Monitor disk space for video downloads

### Monitoring
- Use Flower dashboard for job monitoring
- Set up alerts for worker failures
- Monitor Redis memory usage
- Track job completion rates
- Log analysis for error patterns

## Support

### Log Locations
- **Docker:** `docker logs [container_name]`
- **Systemd:** `journalctl -f -u [service_name]`
- **Application:** `logs/` directory

### Useful Commands
```bash
# View all container statuses
docker-compose ps

# Follow all logs  
docker-compose logs -f

# Restart background job system
docker-compose restart redis celery-worker celery-beat flower

# Purge all job queues (if needed)
docker exec -it mvidarr-celery-worker celery -A src.jobs.celery_app purge

# Check Redis queue lengths
docker exec -it mvidarr-redis redis-cli llen metadata
```

---

**Note:** This deployment replaces the previous Flask-based job system that had reliability issues. The new Celery + Redis system provides enterprise-grade background job processing with proper monitoring and error handling.