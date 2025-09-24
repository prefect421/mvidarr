# MVidarr Scripts

## reset_stuck_downloads.py

### Purpose
This script runs automatically at system startup to clean up any downloads that are stuck in intermediate states (`pending`, `queued`, or `downloading`) and resets them to `wanted` status.

### Why This Is Needed
- When the system restarts unexpectedly, downloads can be left in intermediate states
- The ytdlp_service uses in-memory queues that don't persist across restarts
- Stuck downloads prevent proper re-queuing through the web interface

### What It Does
1. **Scans** the database for downloads with status: `pending`, `queued`, or `downloading`
2. **Resets** them to `wanted` status
3. **Clears** progress and adds a reset message explaining when and why the reset occurred
4. **Logs** the operation with detailed statistics

### Integration
- Runs automatically via systemd `ExecStartPre` in `mvidarr.service`
- Executes before the main MVidarr application starts
- Uses the same virtual environment and database as the main application

### Output Example
```
============================================================
MVidarr Download Cleanup - System Startup
============================================================
[2025-09-23 13:12:18] Starting download cleanup...
📊 Found 7 stuck downloads:
   - downloading: 7 downloads
🔄 Reset download 540: 'ATARASHII GAKKO! - 青春を切り裂く波動...' (downloading → wanted)
🔄 Reset download 541: 'ATARASHII GAKKO! - 青春を切り裂く波動...' (downloading → wanted)
✅ Successfully reset 7/7 downloads to 'wanted' status
🎯 Downloads can now be properly re-queued through the web interface
============================================================
✅ Download cleanup completed successfully
```

### Manual Execution
You can also run this script manually:
```bash
cd /home/mike/mvidarr
python3 scripts/reset_stuck_downloads.py
```

### Status Meanings
- **wanted**: Ready to be downloaded via web interface
- **pending**: Queued for processing but not started
- **queued**: In download queue waiting to start
- **downloading**: Currently being downloaded
- **completed**: Successfully downloaded
- **failed**: Download failed with error

After the startup script runs, all problematic downloads will be in `wanted` status and can be properly re-queued through the MVidarr web interface.