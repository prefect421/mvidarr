# Automatic Video Discovery

## Overview
MVidarr now supports automatic discovery of new music videos for artists marked as "monitored" through the enhanced scheduler service. The scheduler can be configured to search for and discover new videos from MusicBrainz and YouTube at regular intervals.

## How It Works

### Artist Monitoring
- Artists have a `monitored` field that determines if they should be included in automatic discovery
- Artists also have an `auto_download` field that can be used in conjunction with monitoring
- The system tracks `last_discovery` timestamps to prevent excessive API calls

### Discovery Process
1. **Scheduled Check**: At the configured interval, scheduler triggers discovery check
2. **Artist Query**: System queries database for artists with `monitored = true`
3. **Time-based Filtering**: Only processes artists that haven't been checked recently (based on `last_discovery`)
4. **Video Discovery**: Searches MusicBrainz for new videos for each qualifying artist
5. **Duplicate Prevention**: Compares discovered videos against existing video URLs
6. **Video Storage**: New videos are stored with `WANTED` status for potential download
7. **Timestamp Update**: Updates `last_discovery` timestamp for processed artists

## Configuration

### Default Settings (Optimized for Daily Discovery)
- **Enabled**: `true` (automatic discovery enabled by default)
- **Frequency**: `daily` (checks daily)
- **Schedule Time**: `06:00` (6:00 AM)
- **Max Videos per Artist**: `5` (discovers up to 5 new videos per artist per run)

### Available Frequencies

#### Daily Discovery (Recommended)
```
Schedule Frequency: daily
Schedule Time: 06:00 (or custom time)
- Checks for new videos once per day at specified time
- Discovers up to 5 videos per artist (configurable)
- Balanced between API usage and freshness
- Suitable for most users
```

#### Weekly Discovery
```
Schedule Frequency: weekly  
Schedule Time: 06:00 (or custom time)
- Checks once per week on Saturday at specified time
- Discovers up to 5 videos per artist (configurable)
- Minimal API usage for light monitoring
- Good for stable collections
```

#### Twice Daily Discovery
```
Schedule Frequency: twice_daily
Schedule Time: 06:00 (or custom time)
- Checks twice per day (morning and evening, 12 hours apart)
- Discovers up to 5 videos per artist per check
- More frequent discovery for active monitoring
- Higher API usage but more up-to-date
```

#### Custom Day Discovery
```
Schedule Frequency: monday,wednesday,friday
Schedule Time: 06:00 (or custom time)
- Checks on specified days at specified time
- Supports comma-separated day names
- Flexible scheduling for specific needs
```

## Database Settings

All scheduler settings are stored in the database:

| Setting Key | Default Value | Description |
|-------------|---------------|-------------|
| `auto_discovery_schedule_enabled` | `true` | Enable/disable automatic video discovery |
| `auto_discovery_schedule_days` | `daily` | Discovery frequency |
| `auto_discovery_schedule_time` | `06:00` | Time for scheduled discovery |
| `auto_discovery_max_videos_per_artist` | `5` | Max videos to discover per artist per run |

### Environment Variables
Settings can also be configured via environment variables:
```bash
AUTO_DISCOVERY_SCHEDULE_ENABLED=true
AUTO_DISCOVERY_SCHEDULE_DAYS=daily
AUTO_DISCOVERY_SCHEDULE_TIME=06:00
AUTO_DISCOVERY_MAX_VIDEOS_PER_ARTIST=5
```

## API Integration

### Scheduler Status
The scheduler status API now includes discovery information:

```bash
GET /api/settings/scheduler/status
```

**Response includes:**
```json
{
  "enabled": true,
  "downloads": {
    "enabled": true,
    "schedule_days": "hourly",
    "schedule_time": "02:00",
    "max_videos": 10
  },
  "discovery": {
    "enabled": true,
    "schedule_days": "daily", 
    "schedule_time": "06:00",
    "max_videos_per_artist": 5,
    "monitored_artists": 25
  },
  "job_count": 3,
  "next_run": "2025-08-07T06:00:00"
}
```

### Discovery Control
- **POST** `/api/settings/scheduler/start` - Start scheduler (includes discovery)
- **POST** `/api/settings/scheduler/stop` - Stop scheduler (stops discovery)
- **POST** `/api/settings/scheduler/reload` - Reload configuration (updates discovery schedule)

### Manual Discovery
The existing manual discovery endpoints continue to work:
- **POST** `/api/video-discovery/artist/{id}` - Discover videos for specific artist
- **POST** `/api/video-discovery/all` - Discover videos for all monitored artists

## Monitoring and Logging

### Discovery Operations
```bash
# Daily discovery startup
[INFO] Starting daily scheduled video discovery...
[INFO] Discovery check: Found 25 monitored artists, attempting to discover up to 5 videos per artist

# Discovery completion
[INFO] Daily discovery completed: 15/25 artists processed, 23 videos discovered, 18 videos stored
[INFO] Successfully discovered and stored 18 new videos
[INFO] 5 videos were duplicates and not stored

# No processing needed
[INFO] No artists needed discovery (too recent or no monitored artists)
```

### Status Monitoring (Every 5 minutes)
```bash
[DEBUG] Discovery scheduler: 25 artists currently monitored for video discovery
```

### Error Handling
```bash
[ERROR] Scheduled discovery failed: MusicBrainz API rate limit exceeded
[ERROR] Error running scheduled discovery: Database connection timeout
```

## Artist Management

### Setting Up Artists for Discovery

#### Via Database
```sql
-- Enable monitoring for an artist
UPDATE artists SET monitored = true WHERE name = 'Artist Name';

-- Enable both monitoring and auto-download
UPDATE artists SET monitored = true, auto_download = true WHERE name = 'Artist Name';

-- Check monitored artists
SELECT id, name, monitored, auto_download, last_discovery FROM artists WHERE monitored = true;
```

#### Via API (if available)
```bash
# Update artist settings to enable monitoring
PUT /api/artists/{id}/settings
{
  "monitored": true,
  "auto_download": true
}
```

### Discovery Timing Logic
- **First Discovery**: Artists with `last_discovery = NULL` are processed immediately
- **Subsequent Discoveries**: Only process if time since `last_discovery` >= 24 hours (configurable via `discovery_interval_hours`)
- **Rate Limiting**: 1-2 second delays between API calls to respect service limits

## Integration with Downloads

### Automatic Workflow
1. **Discovery**: New videos found and stored with `WANTED` status
2. **Download**: Hourly download scheduler picks up `WANTED` videos
3. **Processing**: Videos are downloaded and status updates to `DOWNLOADED`

### Combined Schedule Example
```bash
# 6:00 AM - Discovery runs, finds 10 new videos marked as WANTED
[INFO] Daily discovery completed: 10 videos stored with WANTED status

# 7:00 AM - Hourly download scheduler processes WANTED videos
[INFO] Hourly download completed: 10 queued, 0 failed, 10 total wanted videos

# Result: Fully automated from discovery to download
```

## Performance Characteristics

### Resource Usage
- **Discovery Frequency**: Daily discovery balances freshness with API usage
- **Batch Processing**: Processes multiple artists in single run with rate limiting
- **Database Efficiency**: Uses existing indexes for monitored artists
- **Memory Usage**: Minimal - processes artists sequentially

### Scalability
- **API Rate Limiting**: Built-in delays prevent service overload
- **Time-based Filtering**: Prevents redundant processing of recently checked artists
- **Configurable Limits**: Max videos per artist prevents runaway discovery
- **Error Resilience**: Individual artist failures don't stop entire process

### Expected Performance
- **25 Monitored Artists**: ~2-3 minutes processing time
- **100 Monitored Artists**: ~8-10 minutes processing time
- **API Calls**: ~1-2 per artist (depending on results and rate limiting)

## Benefits

### User Experience
- **Automatic Discovery**: New videos appear without manual searches
- **Timely Updates**: Daily discovery keeps collection current
- **Zero Maintenance**: Set monitored artists and let the system work
- **Combined Workflow**: Discovery + automatic downloads = fully automated

### System Integration
- **Unified Scheduling**: Discovery and downloads managed by single scheduler
- **Database Integration**: Proper status tracking and duplicate prevention
- **API Compatibility**: Works with existing discovery endpoints
- **Settings Management**: Consistent with existing configuration system

### Content Management
- **Fresh Content**: Regular discovery of new releases
- **Duplicate Prevention**: Intelligent filtering prevents duplicate videos
- **Status Tracking**: Clear video lifecycle from discovery to download
- **Artist-Centric**: Organized around artist monitoring preferences

## Troubleshooting

### Discovery Not Running
1. **Check Settings**: Verify `auto_discovery_schedule_enabled = true`
2. **Verify Monitored Artists**: Ensure artists have `monitored = true`
3. **Check Scheduler**: Confirm scheduler service is running
4. **Review Logs**: Check for discovery-related error messages

### No Videos Discovered
1. **API Connectivity**: Verify MusicBrainz service is accessible
2. **Artist Names**: Ensure artist names match MusicBrainz database
3. **Recent Discovery**: Check if artists were recently processed (`last_discovery`)
4. **Manual Test**: Try manual discovery via API to test connectivity

### Common Log Messages
```bash
# Normal operation
[INFO] Scheduled daily video discovery at 06:00
[DEBUG] Discovery scheduler: 25 artists currently monitored

# Configuration issues
[ERROR] Invalid discovery schedule time format: 25:00. Using default 06:00
[WARN] No monitored artists found for video discovery

# API issues  
[ERROR] MusicBrainz search failed for artist Example Artist: API rate limit
[ERROR] Failed to store discovered video: Database constraint violation
```

This automatic video discovery system transforms MVidarr into a fully autonomous music video management platform, combining scheduled discovery with automatic downloads for a complete hands-off experience.