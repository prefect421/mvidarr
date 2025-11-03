# MVidarr Deployment Guide

**Version: 0.9.9 (Production-Ready)**

This guide covers deployment of MVidarr with Celery + Redis background job system, complete security hardening, and optimized consumer-grade configuration.

## Overview

MVidarr includes a robust background job processing system using Celery + Redis for:
- Metadata enrichment (artist/video data from external sources)
- Video download processing
- Image processing tasks
- FFmpeg operations
- Bulk operations

**Simplified Architecture**: MVidarr uses a streamlined 3-container architecture optimized for home users:
- **mvidarr**: FastAPI application + Celery worker (managed by supervisord)
- **mariadb**: Database
- **redis**: Cache and job queue

## Deployment Options

### Option 1: Docker Compose (Recommended)

#### Simplified 3-Container Setup
The default `docker-compose.yml` provides a streamlined deployment perfect for home users:

```bash
# Clone repository
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr

# Start all services
docker-compose up -d

# Services started:
# - MVidarr container (FastAPI + Celery worker via supervisord) - port 5000
# - MariaDB database - port 3306 (localhost only)
# - Redis cache/job queue - port 6379 (localhost only)
```

**Key Features:**
- **Single Application Container**: FastAPI and Celery worker run together using supervisord
- **Automatic Job Processing**: Background jobs start automatically with the application
- **Simple Management**: Only 3 containers to monitor and maintain
- **Lower Resource Usage**: Optimized for single-user home deployments

**Access:**
- **Web Interface:** http://localhost:5000

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

# Redis Port (optional)
REDIS_PORT=6379
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
Celery worker runs inside the main mvidarr container and is configured with:
- **Concurrency:** 3 workers (adjustable via JOB_WORKER_COUNT)
- **Queues:** metadata, video_downloads, image_processing, default
- **Beat Scheduler:** Embedded in worker for scheduled tasks
- **Process Management:** Supervisord manages both FastAPI and Celery
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

### 3. View Application Logs
```bash
# View combined logs (FastAPI + Celery)
docker logs -f mvidarr

# Or view specific supervisor logs
docker exec -it mvidarr tail -f /app/data/logs/supervisord.log
docker exec -it mvidarr tail -f /app/data/logs/fastapi.log
docker exec -it mvidarr tail -f /app/data/logs/celery-worker.log
```

### 4. Command Line Testing
```bash
# Check Celery worker status inside container
docker exec -it mvidarr celery -A src.jobs.celery_app inspect stats

# Check active tasks
docker exec -it mvidarr celery -A src.jobs.celery_app inspect active

# Verify supervisord process status
docker exec -it mvidarr supervisorctl status
```

## Troubleshooting

### Common Issues

#### 1. Jobs Stuck in "Queued" Status
```bash
# Check Celery worker logs inside mvidarr container
docker exec -it mvidarr tail -f /app/data/logs/celery-worker.log
# OR check all logs
docker logs -f mvidarr

# Verify Celery worker is running
docker exec -it mvidarr supervisorctl status celery-worker

# Restart Celery worker only (keeps FastAPI running)
docker exec -it mvidarr supervisorctl restart celery-worker

# Or restart entire container
docker-compose restart mvidarr
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
# Verify Python path inside mvidarr container
docker exec -it mvidarr python -c "import sys; print(sys.path)"

# Should include /app
# PYTHONPATH is set in Dockerfile and docker-compose.yml
```

#### 4. Database Connection Issues
```bash
# Test database connection from mvidarr container
docker exec -it mvidarr python -c "
from src.database.connection import get_db
with get_db() as session:
    print('Database connection OK')
"
```

#### 5. Supervisord Process Issues
```bash
# Check all supervised processes
docker exec -it mvidarr supervisorctl status

# Restart a specific process
docker exec -it mvidarr supervisorctl restart fastapi
docker exec -it mvidarr supervisorctl restart celery-worker

# Check supervisord logs
docker exec -it mvidarr tail -f /app/data/logs/supervisord.log
```

### Performance Tuning

#### Adjusting Worker Concurrency
```bash
# Set worker concurrency in .env file
JOB_WORKER_COUNT=5

# Or set in docker-compose.yml environment section
# Then restart:
docker-compose down && docker-compose up -d

# The Celery worker will start with the specified concurrency level
```

#### Memory Management
```bash
# Increase Redis memory limit
# In docker-compose.yml, change Redis command:
command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru

# Monitor memory usage
docker stats mvidarr mvidarr-redis mvidarr-mariadb
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

# Follow specific container logs
docker logs -f mvidarr
docker logs -f mvidarr-redis
docker logs -f mvidarr-mariadb

# Restart application (FastAPI + Celery)
docker-compose restart mvidarr

# Restart individual services inside mvidarr container
docker exec -it mvidarr supervisorctl restart fastapi
docker exec -it mvidarr supervisorctl restart celery-worker

# Check service status inside container
docker exec -it mvidarr supervisorctl status

# Purge all job queues (if needed)
docker exec -it mvidarr celery -A src.jobs.celery_app purge

# Check Redis queue lengths
docker exec -it mvidarr-redis redis-cli llen metadata
```

---

**Note:** This simplified 3-container architecture provides all the functionality of enterprise-grade background job processing while being optimized for consumer-grade home deployments. The single application container approach reduces complexity and resource usage while maintaining full Celery + Redis capabilities.