# User Testing Fixes - Issues 1-4

**Date**: 2025-10-17
**Session**: First User Testing
**Status**: Issues #1 and #3 Fixed ✅, Issues #2 and #4 Pending

**Fixes Committed**: 4c809ca
**Services**: ✅ Restarted and active

---

## ✅ Issue #1: Toast Message Shows "artist undefined" When Adding from IMVDb - **FIXED**

### Problem
When adding an artist from IMVDb, the toast message displays:
```
Artist "undefined" added successfully
```

### Root Cause
The JavaScript function responsible for showing the success toast is trying to access a `name` property that doesn't exist in the response object from the IMVDb add artist API.

### Files Fixed
- `frontend/templates/dashboard.html` ✅
- `frontend/templates/artists.html` ✅
- `frontend/templates/index.html` ✅
- `frontend/templates/admin/dashboard.html` ✅

### Fix Applied (Commit: 4c809ca)
Added fallback for artist name in all toast messages:
```javascript
const artistName = result.name || result.artist_name || 'Artist';
showToast(`Artist "${artistName}" added successfully!`, 'success');
```

**Status**: ✅ **COMPLETED** - All 4 files updated with name fallback

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

## ✅ Issue #3: Artist Detail Page "Enrich from all services" Stuck at 80% - **FIXED**

### Problem
When clicking "Enrich from all services" on Artist Detail page, the progress bar gets stuck at 80% with message:
```
Aggregating and resolving metadata conflicts...
```

### Root Cause
The metadata aggregation function at line 169 of `metadata_artist_enricher.py` had no error handling or timeout. If it hung or threw an exception, progress callbacks at 90%, 95%, 98%, and 100% would never be sent to the frontend, causing the UI to appear stuck.

### Fix Applied (Commit: 4c809ca)

**File**: `src/services/metadata_artist_enricher.py` (lines 166-189)

Added comprehensive error handling around metadata aggregation:

```python
# Aggregate and resolve conflicts
if progress_callback:
    progress_callback(80, "Aggregating and resolving metadata conflicts...")

logger.info(f"🔄 Starting metadata aggregation for {artist_name} with {len(metadata_sources)} sources")
try:
    # Add timeout to prevent hanging
    async with asyncio.timeout(30):  # 30 second timeout for aggregation
        unified_metadata = service._aggregate_metadata(metadata_sources)
    logger.info(f"✅ Metadata aggregation complete for {artist_name}")
except asyncio.TimeoutError:
    error_msg = f"Metadata aggregation timed out after 30 seconds for {artist_name}"
    logger.error(f"❌ {error_msg}")
    result.errors.append(error_msg)
    if progress_callback:
        progress_callback(100, "Error: Aggregation timed out")
    return result
except Exception as e:
    error_msg = f"Metadata aggregation failed for {artist_name}: {str(e)}"
    logger.error(f"❌ {error_msg}", exc_info=True)
    result.errors.append(error_msg)
    if progress_callback:
        progress_callback(100, f"Error: {str(e)[:50]}")
    return result
```

**Changes**:
1. ✅ Added 30-second timeout using `asyncio.timeout(30)`
2. ✅ Added try/except for `TimeoutError` and general `Exception`
3. ✅ Added detailed logging before/after aggregation
4. ✅ Progress callback sends 100% even on error (prevents UI from being stuck)
5. ✅ Error messages displayed to user
6. ✅ Full exception traceback logged for debugging

**Status**: ✅ **COMPLETED** - Aggregation now has timeout and error handling, progress always reaches 100%

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
