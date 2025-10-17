# User Testing Fixes - Issues 1-4

**Date**: 2025-10-17
**Session**: First User Testing
**Status**: In Progress

---

## 🐛 Issue #1: Toast Message Shows "artist undefined" When Adding from IMVDb

### Problem
When adding an artist from IMVDb, the toast message displays:
```
Artist "undefined" added successfully
```

### Root Cause
The JavaScript function responsible for showing the success toast is trying to access a `name` property that doesn't exist in the response object from the IMVDb add artist API.

### Files Affected
- `frontend/templates/dashboard.html` (lines ~556, 591)
- `frontend/templates/artists.html` (lines ~1434, 1436)
- `frontend/templates/index.html` (lines ~662, 700)
- `frontend/templates/admin/dashboard.html` (lines ~826, 856)

### Fix Required
Update the toast message to handle cases where `result.name` is undefined. Need to check the actual response structure from the IMVDb artist add API.

**Possible fixes**:
1. Ensure API returns `name` field in response
2. Add fallback: `result.name || result.artist_name || 'Artist'`
3. Check if response includes artist data and extract name properly

### API to Check
- Find where IMVDb artist is added (likely in `artists_discovery.py` or `artists_crud.py`)
- Ensure response includes: `{"id": <id>, "name": <name>, "success": true}`

---

## 🤖 Issue #2: Auto-Match and Enrich Not Triggered on New Artist Creation

### Problem
When a new artist is added from any source (IMVDb, Spotify, manual, etc.), the system should automatically:
1. Run Auto-Match Service to link to external services
2. Run Enrich From All Services to fetch metadata

Currently, these steps must be run manually.

### Root Cause
No post-creation hook exists to trigger automatic enrichment workflow.

### Files to Modify

#### 1. Artist Creation API (`src/api/fastapi/artists_crud.py`)
Add auto-enrichment after artist creation:

```python
@router.post("/")
async def create_artist(
    artist_data: ArtistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # Existing artist creation logic
        new_artist = await artist_service.create_artist(db, artist_data)

        # NEW: Trigger automatic enrichment workflow
        if new_artist:
            # Run Auto-Match in background
            from src.jobs.metadata_tasks import auto_match_artist_task
            auto_match_artist_task.delay(new_artist.id)

            # Wait a moment for auto-match, then enrich
            from src.jobs.metadata_tasks import enrich_artist_all_services_task
            enrich_artist_all_services_task.apply_async(
                args=[new_artist.id],
                countdown=5  # Wait 5 seconds for auto-match to complete
            )

        return {"success": True, "artist": new_artist, "id": new_artist.id, "name": new_artist.name}
    except Exception as e:
        logger.error(f"Error creating artist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 2. Artist Discovery API (`src/api/fastapi/artists_discovery.py`)
Add same auto-enrichment to artist import functions:
- `import_artist_from_spotify`
- `import_artist_from_imvdb`
- `import_artist_from_lastfm`

#### 3. Settings Check
Add setting to enable/disable auto-enrichment:
- Setting key: `auto_enrich_new_artists` (default: `true`)
- Check this setting before triggering enrichment

### Implementation Steps
1. Create helper function in `artists_crud.py`:
   ```python
   async def trigger_auto_enrichment(artist_id: int, delay_seconds: int = 5):
       """Trigger automatic enrichment workflow for new artist"""
       from src.services.settings_service import get_setting

       # Check if auto-enrichment is enabled
       auto_enrich = get_setting('auto_enrich_new_artists', True)
       if not auto_enrich:
           return

       # Trigger auto-match
       from src.jobs.metadata_tasks import auto_match_artist_task
       auto_match_artist_task.delay(artist_id)

       # Trigger enrich after delay
       from src.jobs.metadata_tasks import enrich_artist_all_services_task
       enrich_artist_all_services_task.apply_async(
           args=[artist_id],
           countdown=delay_seconds
       )
   ```

2. Call this helper after every artist creation

3. Add to settings page:
   - Checkbox: "Auto-enrich newly added artists"
   - Description: "Automatically run Auto-Match and Enrich From All Services when adding new artists"

---

## 🔄 Issue #3: Artist Detail Page "Enrich from all services" Stuck at 80%

### Problem
When clicking "Enrich from all services" on Artist Detail page, the progress bar gets stuck at 80% with message:
```
Aggregating and resolving metadata conflicts...
```

### Root Cause
The enrichment API endpoint likely has an error or hangs during the metadata aggregation phase. This is the final step that:
1. Collects metadata from all sources (Spotify, Last.fm, Wikipedia, IMVDb, MusicBrainz)
2. Resolves conflicts between different sources
3. Updates the artist record

### Files to Check

#### 1. Frontend Progress Tracking (`frontend/templates/artist_detail.html`)
Look for enrichment progress tracking around line 3726:
- Check if progress updates are correctly parsed
- Verify WebSocket or polling mechanism

#### 2. Backend Enrichment API
Files to examine:
- `src/api/fastapi/metadata_enrichment_operations.py`
- `src/services/metadata_enrichment_service.py` (aggregator)
- `src/services/metadata_aggregators.py` (aggregation logic)

Look for:
- The "Aggregating and resolving metadata conflicts" message
- Any try/except blocks that might be swallowing errors
- Timeout issues in metadata aggregation

### Debugging Steps

1. **Check Backend Logs**:
   ```bash
   journalctl -u mvidarr -f | grep -i "aggregat\|conflict\|enrich"
   ```

2. **Add More Logging**:
   In `metadata_aggregators.py`, add detailed logging:
   ```python
   logger.info(f"Starting metadata aggregation for artist {artist_id}")
   logger.info(f"Collected data from {len(sources)} sources")
   logger.info(f"Resolving conflicts...")
   logger.info(f"Aggregation complete")
   ```

3. **Check for Deadlocks**:
   - Verify no circular waits in async functions
   - Check if aggregation is waiting for a response that never comes

4. **Add Timeout**:
   ```python
   async with asyncio.timeout(30):  # 30 second timeout
       aggregated_data = await aggregate_metadata(sources_data)
   ```

### Likely Fix Locations

1. **metadata_aggregators.py** - `aggregate_metadata()` function:
   - Add try/except with detailed error logging
   - Add timeout handling
   - Verify all async calls are properly awaited

2. **Progress Reporting**:
   - Ensure progress is updated BEFORE aggregation starts
   - Add progress update AFTER aggregation completes
   - Current: `update_progress(80, "Aggregating...")`
   - Add: `update_progress(90, "Finalizing...")`
   - Add: `update_progress(100, "Complete!")`

---

## 📥 Issue #4: Discover Videos Auto-Download Not Working with Multiple Selections

### Problem
When multiple videos are selected on Discover Videos page and "Auto-download imported videos" setting is enabled, videos are marked as "wanted" but do not automatically download.

Expected: Videos should immediately trigger download
Actual: Videos only get "wanted" status

### Root Cause
The bulk import/add function is not checking the auto-download setting or not properly triggering downloads for multiple videos.

### Files to Check

#### 1. Frontend - Multiple Video Selection
`frontend/templates/discover.html`:
- Find the bulk add/import function
- Check how selected videos are sent to backend

#### 2. Backend - Bulk Video Import
`src/api/fastapi/videos_import.py`:
- Check bulk import endpoints
- Verify auto-download setting is checked

#### 3. Videos Downloads API
`src/api/fastapi/videos_downloads.py`:
- Line 510: `bulk_download_wanted_videos` endpoint
- Check if this is called after bulk import

### Fix Required

#### Option 1: Check Setting in Bulk Import
In `videos_import.py`, after adding videos as "wanted":

```python
@router.post("/bulk/import")
async def bulk_import_videos(
    videos: List[VideoImportData],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from src.services.settings_service import get_setting

    imported_video_ids = []

    # Import all videos
    for video_data in videos:
        video = await import_video(db, video_data)
        if video:
            imported_video_ids.append(video.id)

    # Check auto-download setting
    auto_download = get_setting('auto_download_imported_videos', False)

    if auto_download and imported_video_ids:
        # Trigger bulk download for all imported videos
        from src.services.ytdlp_service import ytdlp_service

        for video_id in imported_video_ids:
            try:
                await ytdlp_service.download_video(video_id, priority=1)
            except Exception as e:
                logger.error(f"Failed to auto-download video {video_id}: {e}")

    return {
        "success": True,
        "imported_count": len(imported_video_ids),
        "auto_downloaded": auto_download
    }
```

#### Option 2: Use Bulk Download Endpoint
After bulk import completes, call the bulk download endpoint:

```javascript
// In discover.html - after bulk import
async function importSelectedVideos(videoIds) {
    // 1. Import videos
    const importResponse = await fetch('/api/videos/import/bulk', {
        method: 'POST',
        body: JSON.stringify({videos: videoIds})
    });

    const importData = await importResponse.json();

    // 2. Check if auto-download is enabled
    const settingsResponse = await fetch('/api/settings/auto_download_imported_videos');
    const settingsData = await settingsResponse.json();

    if (settingsData.value === true || settingsData.value === 'true') {
        // 3. Trigger bulk download
        await fetch('/api/videos/bulk/download-wanted', {
            method: 'POST',
            body: JSON.stringify({
                video_ids: importData.imported_video_ids,
                priority: 1
            })
        });

        showToast(`Imported ${importData.imported_count} videos and triggered downloads`, 'success');
    } else {
        showToast(`Imported ${importData.imported_count} videos as wanted`, 'success');
    }
}
```

#### Option 3: Celery Task Chain
Use Celery task chaining to automatically download after import:

```python
from src.jobs.video_tasks import import_video_task, download_video_task

# Chain tasks
task_chain = (
    import_video_task.s(video_data) |
    download_video_task.s()
)
task_chain.apply_async()
```

### Settings to Verify
Ensure these settings exist in database:
- `auto_download_imported_videos` - Enable/disable auto-download
- `auto_download_priority` - Priority level (1-10)

---

## 📋 Implementation Priority

### Phase 1: Quick Fixes (30 minutes)
1. **Issue #1**: Fix toast message undefined
   - Add fallback for artist name
   - Test IMVDb artist add response

### Phase 2: Auto-Enrichment (1 hour)
2. **Issue #2**: Add auto-enrichment on artist creation
   - Create helper function
   - Add to all artist creation endpoints
   - Add setting to enable/disable

### Phase 3: Debug Enrichment Stuck (1-2 hours)
3. **Issue #3**: Fix enrichment stuck at 80%
   - Add extensive logging
   - Add timeout handling
   - Test aggregation function
   - Fix any deadlocks or errors

### Phase 4: Bulk Download (1 hour)
4. **Issue #4**: Fix bulk auto-download
   - Check auto-download setting in bulk import
   - Trigger downloads after import
   - Test with multiple videos

---

## 🧪 Testing Checklist

### Issue #1 Testing
- [ ] Add artist from IMVDb
- [ ] Verify toast shows correct artist name
- [ ] Test with different artist names (special characters, etc.)

### Issue #2 Testing
- [ ] Add new artist manually
- [ ] Verify Auto-Match runs automatically (check jobs)
- [ ] Verify Enrich runs after Auto-Match
- [ ] Check artist detail page shows enriched data
- [ ] Test with setting disabled

### Issue #3 Testing
- [ ] Go to artist detail page
- [ ] Click "Enrich from all services"
- [ ] Verify progress completes to 100%
- [ ] Check artist data is updated
- [ ] Test with artist having conflicts
- [ ] Check logs for any errors

### Issue #4 Testing
- [ ] Go to Discover Videos
- [ ] Search for videos
- [ ] Select multiple videos (5+)
- [ ] Verify auto-download setting is enabled
- [ ] Add videos to library
- [ ] Verify downloads start automatically
- [ ] Check download status in Jobs page
- [ ] Test with setting disabled (should be wanted only)

---

## 📝 Notes for Implementation

### Logging
Add comprehensive logging for debugging:
```python
logger.info(f"🎨 Creating new artist: {artist_name}")
logger.info(f"🤖 Auto-enrichment enabled: {auto_enrich}")
logger.info(f"🔄 Triggering auto-match for artist {artist_id}")
logger.info(f"📊 Aggregating metadata from {len(sources)} sources")
logger.info(f"📥 Auto-downloading {len(video_ids)} videos")
```

### Error Handling
Wrap auto-enrichment in try/except to prevent failures from blocking artist creation:
```python
try:
    await trigger_auto_enrichment(artist_id)
except Exception as e:
    logger.warning(f"Auto-enrichment failed for artist {artist_id}: {e}")
    # Artist creation still succeeds
```

### Settings
Add to settings page under "Automation":
- ✅ Auto-enrich newly added artists
- ✅ Auto-download imported videos
- ⚙️ Auto-enrichment delay (default: 5 seconds)
- ⚙️ Auto-download priority (default: 1)

---

**Status**: Ready for implementation
**Estimated Time**: 3-4 hours total
**Complexity**: Medium
**Impact**: High (affects core user workflows)
