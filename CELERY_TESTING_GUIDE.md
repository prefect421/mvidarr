# Celery + Redis Background Jobs Testing Guide
## Quick Setup and Testing Instructions

### Prerequisites
- Docker and Docker Compose installed
- MVidarr dev environment running
- Git repository updated with latest Celery implementation

## Quick Start Testing

### Step 1: Start Redis + Celery Infrastructure

```bash
# Navigate to MVidarr directory
cd /home/mike/mvidarr

# Start Redis and Celery workers
docker-compose -f docker-compose.redis.yml up -d

# Check if services are running
docker ps | grep -E "(redis|celery)"
```

**Expected Output:**
```
mvidarr_redis          - Redis server (port 6379)
mvidarr_celery_worker  - Background task worker  
mvidarr_celery_beat    - Scheduled task scheduler
mvidarr_celery_flower  - Monitoring dashboard (port 5555)
```

### Step 2: Verify Celery Worker Status

```bash
# Check worker logs
docker logs mvidarr_celery_worker

# Should show:
# - "celery@hostname ready" 
# - Connected to redis://redis:6379/0
# - Registered tasks: metadata.enrich_artist, metadata.enrich_video, etc.
```

### Step 3: Access Flower Monitoring Dashboard

Open in browser: **http://localhost:5555**
- **Username:** admin
- **Password:** mvidarr123

**What to verify:**
- Workers tab shows 1 active worker
- Tasks tab shows registered metadata tasks
- Monitor tab shows real-time statistics

### Step 4: Test Metadata Enrichment

1. **Start Flask App (if not running)**
```bash
cd /home/mike/mvidarr
python app.py
```

2. **Access Artist Detail Page**
   - Go to: http://localhost:5000/artist/192
   - Click "Enrich from all sources" button

3. **Monitor Progress**
   - Job should show real-time progress updates
   - Check Flower dashboard for task execution
   - Verify no "stuck in queued" status

### Step 5: Manual API Testing

```bash
# Test artist enrichment endpoint
curl -X POST "http://localhost:5000/api/metadata-enrichment/enrich/artist/192" \
  -H "Content-Type: application/json" \
  -d '{"force_refresh": true, "enrich_videos": true}' \
  --cookie-jar cookies.txt \
  --cookie cookies.txt

# Expected response:
{
  "success": true,
  "job_id": "abc123-def456-...",
  "artist_id": 192,
  "status": "queued",
  "message": "Metadata enrichment job started for artist 192"
}

# Check job status (replace JOB_ID with actual ID)
curl "http://localhost:5000/api/metadata-enrichment/job/JOB_ID/status" \
  --cookie cookies.txt
```

## Troubleshooting

### Common Issues

#### 1. Redis Connection Failed
```bash
# Check Redis status
docker logs mvidarr_redis

# Restart Redis
docker-compose -f docker-compose.redis.yml restart redis
```

#### 2. Celery Worker Not Starting
```bash
# Check worker logs
docker logs mvidarr_celery_worker

# Common fix: Restart worker
docker-compose -f docker-compose.redis.yml restart celery_worker
```

#### 3. Import Errors
```bash
# Check Python path in worker
docker exec -it mvidarr_celery_worker python -c "import sys; print(sys.path)"

# Should include /app path
```

#### 4. Database Connection Issues
```bash
# Check if worker can connect to database
docker exec -it mvidarr_celery_worker python -c "
from src.database.connection import get_db
with get_db() as session:
    print('Database connection OK')
"
```

### Performance Testing

#### Load Test with Multiple Jobs
```bash
# Queue multiple enrichment jobs
for i in {190..200}; do
  curl -X POST "http://localhost:5000/api/metadata-enrichment/enrich/artist/$i" \
    -H "Content-Type: application/json" \
    -d '{"force_refresh": true}' \
    --cookie cookies.txt &
done

# Monitor in Flower dashboard
# Check worker handles concurrent jobs properly
```

## Verification Checklist

### ✅ Infrastructure
- [ ] Redis server running on port 6379
- [ ] Celery worker connected and ready
- [ ] Flower dashboard accessible on port 5555
- [ ] No error messages in worker logs

### ✅ API Integration  
- [ ] Artist enrichment endpoint returns Celery task ID
- [ ] Job status endpoint returns task progress
- [ ] WebSocket updates show real-time progress
- [ ] Jobs complete successfully (not stuck in queued)

### ✅ Functionality
- [ ] Metadata enrichment actually processes (not mock data)
- [ ] Artist data gets updated in database
- [ ] Progress bar shows real-time updates
- [ ] Error handling works for failed jobs

### ✅ Performance
- [ ] Jobs start processing immediately
- [ ] Multiple concurrent jobs handled properly
- [ ] No memory leaks or worker crashes
- [ ] Flower shows accurate statistics

## Architecture Validation

### Before (Problematic Flask System)
```
Flask App → Complex Async Integration → ❌ Jobs Stuck
  ↓              ↓                          ↓
API            Event Loop Issues        Unreliable
WebSocket      Startup Failures         No Processing
```

### After (Celery + Redis System)
```
Flask App → Redis Queue → Celery Worker → ✅ Jobs Complete
  ↓            ↓             ↓              ↓  
API         Job Storage   Task Processing  Reliable
WebSocket   Progress      Real Enrichment  Scalable
```

## Next Steps After Testing

1. **If all tests pass:**
   - Remove old Flask job system
   - Update documentation
   - Deploy to production environment

2. **If issues found:**
   - Check logs for specific errors
   - Verify Docker network connectivity
   - Check Python imports and dependencies
   - Test individual components separately

## Support Commands

```bash
# View all container logs
docker-compose -f docker-compose.redis.yml logs

# Restart entire Celery infrastructure
docker-compose -f docker-compose.redis.yml restart

# Scale workers (add more workers)
docker-compose -f docker-compose.redis.yml up -d --scale celery_worker=3

# Stop Celery infrastructure
docker-compose -f docker-compose.redis.yml down

# Check Redis queue status
docker exec -it mvidarr_redis redis-cli llen metadata

# Purge all queues (if needed)
docker exec -it mvidarr_celery_worker celery -A src.jobs.celery_app purge
```

---

**Testing Priority:** HIGH - This replaces critical broken functionality
**Expected Time:** 30-60 minutes for complete testing
**Success Criteria:** Metadata enrichment works reliably without stuck jobs