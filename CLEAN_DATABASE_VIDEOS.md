# Clean Database - Remove All Indexed Videos

## ⚠️ BACKUP FIRST! ⚠️

Before running any delete commands, **create a backup**:

```bash
# On production server
docker exec mvidarr mysqldump -u mvidarr -p mvidarr > /tmp/mvidarr_backup_$(date +%Y%m%d_%H%M%S).sql

# Or via docker
docker exec mvidarr mysqldump -u mvidarr -p"your_password" mvidarr > /tmp/mvidarr_backup.sql
```

---

## Option 1: Remove ONLY Videos & Downloads (Keep Artists)

This removes all videos and their associated downloads, but **keeps artist records** for future imports.

```sql
-- Connect to database
USE mvidarr;

-- Check what you have before deleting
SELECT
    (SELECT COUNT(*) FROM videos) as total_videos,
    (SELECT COUNT(*) FROM downloads) as total_downloads,
    (SELECT COUNT(*) FROM artists) as total_artists;

-- Delete all downloads first (foreign key constraint)
DELETE FROM downloads;

-- Delete all videos
DELETE FROM videos;

-- Verify deletion
SELECT
    (SELECT COUNT(*) FROM videos) as remaining_videos,
    (SELECT COUNT(*) FROM downloads) as remaining_downloads,
    (SELECT COUNT(*) FROM artists) as remaining_artists;
```

**Result:** Artists remain, ready for re-import. Videos and downloads removed.

---

## Option 2: Remove EVERYTHING (Videos, Downloads, AND Artists)

This is a **complete wipe** - removes all indexed content including artist records.

```sql
-- Connect to database
USE mvidarr;

-- Check counts before deletion
SELECT
    (SELECT COUNT(*) FROM videos) as total_videos,
    (SELECT COUNT(*) FROM downloads) as total_downloads,
    (SELECT COUNT(*) FROM artists) as total_artists;

-- Delete in order due to foreign key constraints
-- 1. Delete downloads first (references videos)
DELETE FROM downloads;

-- 2. Delete videos (references artists)
DELETE FROM videos;

-- 3. Delete artists (no dependencies)
DELETE FROM artists;

-- Verify complete deletion
SELECT
    (SELECT COUNT(*) FROM videos) as remaining_videos,
    (SELECT COUNT(*) FROM downloads) as remaining_downloads,
    (SELECT COUNT(*) FROM artists) as remaining_artists;
```

**Result:** Complete clean slate. All video data removed.

---

## Option 3: Remove Only Duplicate Videos

If you want to keep originals and remove only duplicates:

```sql
-- Find duplicates (same artist and title)
SELECT
    artist_id,
    title,
    COUNT(*) as duplicate_count
FROM videos
GROUP BY artist_id, title
HAVING COUNT(*) > 1;

-- Keep oldest, delete newer duplicates
DELETE v1 FROM videos v1
INNER JOIN videos v2
WHERE v1.artist_id = v2.artist_id
  AND v1.title = v2.title
  AND v1.id > v2.id;

-- Also clean up orphaned downloads
DELETE FROM downloads
WHERE video_id NOT IN (SELECT id FROM videos);
```

---

## How to Execute

### Method 1: Via Portainer Console (Easiest)

1. **Open Portainer:** http://192.168.1.132:9000
2. **Go to Containers** → Click **mvidarr**
3. **Click "Console"** button
4. **Select "/bin/bash"** and click **Connect**
5. **Run MySQL client:**
   ```bash
   mysql -u mvidarr -p mvidarr
   # Enter password when prompted
   ```
6. **Paste SQL commands** from Option 1 or 2 above

### Method 2: Via Docker Exec

```bash
# Interactive mode
docker exec -it mvidarr mysql -u mvidarr -p mvidarr

# Or single command
docker exec -it mvidarr mysql -u mvidarr -p -e "
USE mvidarr;
DELETE FROM downloads;
DELETE FROM videos;
SELECT COUNT(*) as remaining_videos FROM videos;
"
```

### Method 3: Via SQL File

```bash
# Create SQL file
cat > /tmp/clean_videos.sql << 'EOF'
USE mvidarr;
DELETE FROM downloads;
DELETE FROM videos;
SELECT 'Videos deleted' as status;
EOF

# Execute it
docker exec -i mvidarr mysql -u mvidarr -p < /tmp/clean_videos.sql
```

---

## Verification After Deletion

```sql
-- Check all counts
SELECT
    'videos' as table_name, COUNT(*) as count FROM videos
UNION ALL
SELECT 'downloads', COUNT(*) FROM downloads
UNION ALL
SELECT 'artists', COUNT(*) FROM artists;

-- Check for orphaned records
SELECT
    'Orphaned downloads' as check_type,
    COUNT(*) as count
FROM downloads d
LEFT JOIN videos v ON d.video_id = v.id
WHERE v.id IS NULL

UNION ALL

SELECT
    'Orphaned videos',
    COUNT(*)
FROM videos v
LEFT JOIN artists a ON v.artist_id = a.id
WHERE a.id IS NULL;
```

---

## Reset Auto-Increment IDs (Optional)

If you want to start ID sequences from 1 again:

```sql
ALTER TABLE downloads AUTO_INCREMENT = 1;
ALTER TABLE videos AUTO_INCREMENT = 1;
-- Only if you deleted artists:
ALTER TABLE artists AUTO_INCREMENT = 1;
```

---

## Quick Reference Commands

### Get Database Password
```bash
# Check environment or config
docker exec mvidarr env | grep -i mysql
# or
docker exec mvidarr cat /app/.env | grep DB_PASSWORD
```

### One-Line Complete Wipe
```bash
docker exec mvidarr mysql -u mvidarr -p"$(docker exec mvidarr cat /app/.env | grep DB_PASSWORD | cut -d= -f2)" -e "USE mvidarr; DELETE FROM downloads; DELETE FROM videos; DELETE FROM artists;"
```

### Check Current State
```bash
docker exec mvidarr mysql -u mvidarr -p -e "USE mvidarr; SELECT COUNT(*) as videos FROM videos; SELECT COUNT(*) as downloads FROM downloads; SELECT COUNT(*) as artists FROM artists;"
```

---

## After Cleaning

Once videos are removed, you can:

1. **Re-import using CLI script** (recommended):
   ```bash
   docker exec -it mvidarr python3 scripts/index_videos.py --index-all
   ```

2. **Use web UI** (after wizard is implemented in v1.0.0)

3. **Manually add videos** through the UI

---

## Troubleshooting

### "Access denied for user"
- Check password in `/app/.env` file
- Ensure user has DELETE permissions

### "Cannot delete or update a parent row: a foreign key constraint fails"
- Delete in correct order: downloads → videos → artists
- Check for additional tables with foreign keys

### "Commands out of sync"
- Exit and reconnect to MySQL
- Run commands one at a time

---

## Safety Checklist

Before running deletion:
- [ ] Database backup created
- [ ] Confirmed production/dev environment
- [ ] Verified which option to use (Option 1 or 2)
- [ ] Understood that this is **permanent**
- [ ] Ready to re-import videos after deletion

---

## Related Files
- `INSTALLATION_WIZARD_SPEC.md` - Future proper import method
- `INITIAL_VIDEO_LOAD_GUIDE.md` - CLI script for reliable import
- GitHub Issue #163 - Installation wizard for v1.0.0
