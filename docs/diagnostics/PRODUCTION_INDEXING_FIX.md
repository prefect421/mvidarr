# Production Video Indexing Issue - Diagnosis and Fix

## Problem
Only 20 videos indexed out of 2400 remaining after rebuilding production container.

## Root Cause
The recent path fix (commit d3f1fdd) changed the music videos directory from `/music_videos/` to `/musicvideos/` to match Docker mounts. This means:

1. **Old database records** have paths like `/app/data/music_videos/Artist/video.mp4`
2. **New scanned files** have paths like `/app/data/musicvideos/Artist/video.mp4`
3. **Duplicate detection fails** to match them because paths are different
4. **Old records block indexing** of the same videos at the new correct paths

## Step 1: Copy Scripts to Production

### Method A: If you have SSH access

```bash
# From your local dev machine (this machine)
scp /home/mike/mvidarr/diagnose_indexing.py mike@192.168.1.132:/tmp/
scp /home/mike/mvidarr/fix_path_mismatch.py mike@192.168.1.132:/tmp/

# SSH to production and copy to container
ssh mike@192.168.1.132
docker cp /tmp/diagnose_indexing.py mvidarr:/app/
docker cp /tmp/fix_path_mismatch.py mvidarr:/app/
```

### Method B: Direct access to production server

If you're working directly on the production server:

```bash
# Copy files from dev to production (use USB drive, network share, or git)
# Then on production server:
docker cp diagnose_indexing.py mvidarr:/app/
docker cp fix_path_mismatch.py mvidarr:/app/
```

### Method C: Create scripts directly in container

```bash
# On production server, create the scripts directly:
# (The scripts are also available in this repo at the root)
# Just pull the latest code and copy them in:
cd /path/to/mvidarr
git pull origin dev
docker cp diagnose_indexing.py mvidarr:/app/
docker cp fix_path_mismatch.py mvidarr:/app/
```

## Step 2: Diagnose the Issue

Run the diagnostic script in the production container:

```bash
# Enter the mvidarr container
docker exec -it mvidarr bash

# Run diagnostic
cd /app
python3 diagnose_indexing.py
```

The diagnostic will show:
- How many records have OLD path pattern (/music_videos/)
- How many records have NEW path pattern (/musicvideos/)
- How many files exist on disk but not in database
- Sample paths from both database and disk

## Step 3: Fix - Clean Up Stale Records

### Option A: Dry Run (See what will be deleted)

```bash
# In production container
cd /app
python3 fix_path_mismatch.py
```

This shows what records would be deleted WITHOUT actually deleting them.

### Option B: Execute the Fix

```bash
# In production container
cd /app
python3 fix_path_mismatch.py --execute
```

When prompted, type `YES` to confirm deletion of stale records.

This will:
1. Delete all Download records with old path pattern (/music_videos/)
2. Delete any orphaned Video records that no longer have downloads
3. Clear the way for re-indexing from the correct path

## Step 4: Re-Index Videos

After cleaning up stale records:

1. Go to http://192.168.1.132:5050
2. Navigate to Settings > Video Indexing (or wherever the indexing UI is)
3. Click "Index All Videos"
4. Monitor the job to see the progress

All 2400 videos should now be indexed with the correct paths.

## Alternative: Database Query Method

If you prefer SQL, you can also check/fix directly:

```bash
# Check old path records
docker exec -it mvidarr mysql -u mvidarr -p -D mvidarr -e \
  "SELECT COUNT(*) as old_path_count FROM downloads WHERE file_path LIKE '%/music_videos/%';"

# Check new path records
docker exec -it mvidarr mysql -u mvidarr -p -D mvidarr -e \
  "SELECT COUNT(*) as new_path_count FROM downloads WHERE file_path LIKE '%/musicvideos/%';"

# Delete old path records (BE CAREFUL!)
docker exec -it mvidarr mysql -u mvidarr -p -D mvidarr -e \
  "DELETE FROM downloads WHERE file_path LIKE '%/music_videos/%';"
```

## Verification

After the fix and re-indexing:

```bash
# Check counts again
python3 diagnose_indexing.py
```

You should see:
- 0 records with old path pattern
- ~2400 records with new path pattern
- 0 files on disk missing from database

## Notes

- **Backup first**: If you're concerned, back up the database before running the fix
- **Safe operation**: The scripts only delete Download records with provably wrong paths
- **Orphan cleanup**: Videos with no remaining downloads are also removed (they'll be recreated during re-indexing)
- **Metadata preserved**: Re-indexing will fetch fresh metadata from IMVDb

## Questions?

If you see unexpected results, share the diagnostic output for further analysis.
