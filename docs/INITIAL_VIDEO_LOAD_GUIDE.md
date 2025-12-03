# Initial Video Load Guide

## Problem
The web UI indexing has multiple issues:
- Slow API responses (70+ seconds)
- Creating duplicate videos
- Missing success feedback
- Background job reliability issues

## Solution: Use CLI Script Instead

The CLI script (`scripts/index_videos.py`) is **more reliable** for initial video loading:
- ✅ Direct database access (no API/job queue overhead)
- ✅ Clear progress output
- ✅ Duplicate detection
- ✅ Better error handling
- ✅ Can run in production container

---

## Method 1: Run in Production Container (Recommended)

### Step 1: Access Portainer
1. Open: http://192.168.1.132:9000
2. Navigate to **Containers**
3. Click on **mvidarr** container
4. Click **Console** button
5. Select **Command: /bin/bash**
6. Click **Connect**

### Step 2: Run Indexing Script

```bash
# First, check current stats
python3 scripts/index_videos.py --stats

# Scan to see what files will be indexed
python3 scripts/index_videos.py --scan

# Test with first 10 files (recommended first time)
python3 scripts/index_videos.py --index-all --max-files 10

# If test looks good, index all videos WITH metadata
python3 scripts/index_videos.py --index-all

# Or index WITHOUT metadata (faster, for initial load)
python3 scripts/index_videos.py --index-all --no-metadata
```

### Step 3: Verify Results
```bash
# Check stats after indexing
python3 scripts/index_videos.py --stats
```

---

## Method 2: Run from Dev Server (if SSH works)

```bash
# SSH to production
ssh mike@192.168.1.132

# Run inside container
docker exec -it mvidarr python3 scripts/index_videos.py --index-all
```

---

## Method 3: Copy Script to Production Host

If you prefer to run outside the container:

```bash
# On production host (192.168.1.132)
# Copy the script
docker cp mvidarr:/app/scripts/index_videos.py /tmp/

# Run with docker exec
docker exec -it mvidarr python3 /app/scripts/index_videos.py --index-all
```

---

## What the Script Does

### Duplicate Detection
The script checks for existing videos by:
- Artist name
- Video title
- File path

If a video already exists, it shows:
```
⏭️  File already indexed: Artist Name - Video Title
```

### Progress Output
Shows real-time progress:
```
🎬 Video Indexing Process 🎬
Fetch IMVDb metadata: Yes
------------------------------------------------------------
Processing: [1/100] Artist Name - Video Title
✅ Successfully indexed: Artist Name - Video Title
   📋 IMVDb metadata found
   🖼️  Thumbnail downloaded
```

### Final Summary
```
🎬 Video Indexing Complete 🎬
Total files found: 217
Successfully indexed: 2
Already indexed: 215
Failed to index: 0
Artists created: 0
Videos created: 2
IMVDb metadata found: 2
Thumbnails downloaded: 2
```

---

## Useful Commands

### Preview a Single File
```bash
python3 scripts/index_videos.py --preview "/app/data/musicvideos/Artist/Video.mp4"
```

### Index a Single File
```bash
python3 scripts/index_videos.py --index "/app/data/musicvideos/Artist/Video.mp4"
```

### Test IMVDb Connection
```bash
python3 scripts/index_videos.py --test-imvdb
```

### Show Current Stats
```bash
python3 scripts/index_videos.py --stats
```

---

## Advantages Over Web UI

| Feature | Web UI | CLI Script |
|---------|--------|------------|
| Speed | 70+ seconds | < 5 seconds |
| Duplicates | Creates duplicates | Detects and skips |
| Progress | Stuck message | Real-time output |
| Reliability | Background job issues | Direct execution |
| Error Details | Hidden | Clear error messages |
| Testability | All or nothing | Can test with --max-files |

---

## Recommended Initial Load Process

1. **First Time Setup:**
   ```bash
   # Check what videos exist
   python3 scripts/index_videos.py --scan

   # Test with 10 files
   python3 scripts/index_videos.py --index-all --max-files 10

   # If good, do full index WITHOUT metadata (faster)
   python3 scripts/index_videos.py --index-all --no-metadata

   # Later, can add metadata via web UI's "Enrich All Artists"
   ```

2. **Already Have Videos in DB:**
   ```bash
   # Check current stats
   python3 scripts/index_videos.py --stats

   # Just index new videos (skips existing)
   python3 scripts/index_videos.py --index-all
   ```

---

## Troubleshooting

### "Failed to initialize environment"
- Make sure you're inside the container
- Check database connection in container logs

### "No video files found"
- Check the path: `/app/data/musicvideos/`
- Verify videos are mounted correctly in Docker

### "IMVDb connection failed"
- Set IMVDb API key in Settings first
- Or use `--no-metadata` flag

---

## After Initial Load

Once videos are loaded via CLI, you can use the web UI for:
- ✅ Adding metadata (Enrich All Artists button)
- ✅ Managing individual videos
- ✅ Downloading new videos
- ✅ Organizing videos

The CLI script is **only needed for bulk initial loading**.
