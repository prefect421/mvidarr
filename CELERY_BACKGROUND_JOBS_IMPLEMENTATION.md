# Celery + Redis Background Jobs Implementation Plan
## MVidarr Background Processing Migration

### Overview
This document outlines the migration from the problematic Flask async job system to a proper **Celery + Redis** background job architecture. This replaces the complex and unreliable Flask job integration with an industry-standard solution.

### Problem Statement
The current Flask application uses a complex async job system that has several issues:
1. **Flask async integration problems** - Flask trying to run async workers with event loop management
2. **Unreliable job processing** - Jobs get stuck in "queued" status
3. **Complex architecture** - Two separate apps (Flask + FastAPI) with duplicate job systems
4. **Resource waste** - Multiple web servers and complex integrations
5. **Maintenance complexity** - Managing two different frameworks and custom async integration

### Solution: Celery + Redis
Implement a proper **Celery + Redis** background job system that provides:
- **Reliable job processing** with industry-tested architecture
- **Real-time progress updates** via WebSocket integration
- **Scalable worker management** with multiple queues
- **Job monitoring** with Flower dashboard
- **Clean separation** between web layer and background processing

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Flask Web     │    │   Redis Queue   │    │  Celery Worker  │
│   (Port 5000)   │───▶│   (Port 6379)   │◀───│   (Background)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
    API Endpoints          Job Storage           Task Processing
    WebSocket Updates      Progress Tracking     Metadata Enrichment
                                                 Video Downloads
                                                 Image Processing
                                                 FFmpeg Operations
```

## Implementation Status

### ✅ Phase 1: Foundation (COMPLETE)
- [x] **Celery App Configuration** - `src/jobs/celery_app.py`
- [x] **Docker Infrastructure** - `docker-compose.redis.yml`
- [x] **Queue Architecture** - Multiple specialized queues
- [x] **Requirements** - Celery 5.3.4, Redis 5.0.1 already in requirements.txt

### 🔄 Phase 2: Metadata Tasks (IN PROGRESS)
- [x] **Metadata Tasks Module** - `src/jobs/metadata_tasks.py`
  - [x] `enrich_artist_metadata_task()` - Artist enrichment with progress
  - [x] `enrich_video_metadata_task()` - Video enrichment 
  - [x] `batch_enrich_artists_task()` - Batch processing
  - [x] **Progress Callbacks** - Real-time WebSocket updates
  - [x] **Error Handling** - Comprehensive error handling and logging

### 📝 Phase 3: API Integration (PENDING)
- [ ] **Update API endpoints** to use Celery tasks instead of Flask workers
- [ ] **WebSocket integration** for real-time progress updates
- [ ] **Job status endpoints** for monitoring active tasks
- [ ] **Job cancellation** functionality

### 🧪 Phase 4: Testing & Deployment (PENDING)
- [ ] **Local testing** with Redis + Celery workers
- [ ] **Docker deployment** testing
- [ ] **Performance validation**
- [ ] **Migration from old system**

## File Structure

```
src/jobs/
├── celery_app.py           # Celery configuration and job management
├── metadata_tasks.py       # Metadata enrichment Celery tasks (NEW)
├── video_download_tasks.py # Video download tasks
├── image_processing_tasks.py # Image processing tasks
└── ffmpeg_processing_tasks.py # FFmpeg tasks

docker-compose.redis.yml    # Redis + Celery infrastructure
```

## Key Features

### 1. Specialized Task Queues
- **`metadata`** - Artist/video metadata enrichment
- **`video_downloads`** - YouTube video downloads  
- **`image_processing`** - Thumbnail generation, image optimization
- **`ffmpeg_processing`** - Video conversion, streaming preparation
- **`default`** - General background tasks

### 2. Progress Tracking
```python
@celery_app.task(bind=True, base=CallbackTask)
def enrich_artist_metadata_task(self, artist_id: int):
    self.update_progress(task_id, 25, "Gathering metadata...")
    # Real-time WebSocket updates to frontend
```

### 3. Job Management
```python
from src.jobs.celery_app import job_manager

# Get active jobs
active = job_manager.get_active_jobs()

# Cancel a job
job_manager.cancel_job(task_id)

# Check queue status
length = job_manager.get_queue_length("metadata")
```

### 4. WebSocket Integration
- Real-time progress updates sent to frontend
- Job status changes broadcast immediately
- Progress bars and status messages update live

## Deployment

### Development
```bash
# Start Redis + Celery workers
docker-compose -f docker-compose.redis.yml up -d

# Access Flower monitoring
http://localhost:5555
# Credentials: admin / mvidarr123
```

### Production
```bash
# Full stack with Redis
docker-compose -f docker-compose.production.yml -f docker-compose.redis.yml up -d
```

## API Usage

### Before (Problematic Flask System)
```python
# Complex async integration that often failed
async def start_job_system():
    loop.run_until_complete(self._start_job_system())
    # Jobs would get stuck in "queued" status
```

### After (Celery System)
```python
# Simple, reliable task dispatch
from src.jobs.metadata_tasks import enrich_artist_metadata_task

# Queue the task
task = enrich_artist_metadata_task.delay(
    artist_id=192, 
    force_refresh=True, 
    enrich_videos=True
)

# Get task status
result = task.get()  # Blocks until complete
status = task.status  # 'PENDING', 'PROGRESS', 'SUCCESS', 'FAILURE'
```

## Migration Steps

### Step 1: Test New System
1. Start Redis and Celery workers
2. Test metadata enrichment via new Celery tasks
3. Verify WebSocket progress updates work

### Step 2: Update API Endpoints
1. Modify `/api/metadata-enrichment/enrich/artist/<id>` to use Celery
2. Update job status endpoints to query Celery instead of custom system
3. Test all metadata enrichment flows

### Step 3: Remove Old System
1. Remove Flask job integration (`src/services/flask_job_integration.py`)
2. Remove custom job queue system (`src/services/job_queue.py`)
3. Remove worker managers (`src/services/background_workers.py`)
4. Clean up imports and references

### Step 4: Deploy and Validate
1. Deploy to dev environment
2. Test all background job functionality
3. Monitor performance and reliability
4. Deploy to production

## Benefits

### Immediate Benefits
- **Reliable job processing** - No more stuck jobs
- **Industry standard** - Battle-tested architecture
- **Better monitoring** - Flower dashboard for job visibility
- **Cleaner code** - Remove complex async integration

### Long-term Benefits  
- **Scalability** - Easy to add more workers
- **Maintainability** - Standard patterns and tools
- **Performance** - Optimized for background processing
- **Flexibility** - Easy to add new task types

## Monitoring

### Flower Dashboard (Port 5555)
- Real-time worker status
- Active/completed/failed task counts
- Task execution times and statistics
- Queue lengths and worker load

### Logs
```bash
# Celery worker logs
docker logs mvidarr_celery_worker

# Redis logs  
docker logs mvidarr_redis

# Task-specific logs
tail -f logs/mvidarr.log | grep "metadata_tasks"
```

## Next Steps

1. **Complete Phase 3** - Update API endpoints to use Celery tasks
2. **Implement WebSocket integration** for real-time progress updates  
3. **Test thoroughly** with Redis + Celery system
4. **Migrate gradually** - Keep old system running until new system is proven
5. **Document performance improvements** and reliability gains

---

**Status**: Phase 2 Complete - Metadata tasks implemented
**Next**: Update API endpoints to use Celery tasks
**Timeline**: 2-3 days for complete migration and testing