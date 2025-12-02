# MVidarr Troubleshooting & FAQ

## Overview

This guide provides solutions to common MVidarr issues, frequently asked questions, and step-by-step troubleshooting procedures. For Docker-specific issues, also see `TROUBLESHOOTING_DOCKER.md`.

## 🚨 Common Issues & Quick Fixes

### Cannot Access MVidarr Interface

#### Problem: Page won't load or shows connection error

**Quick Fixes:**
```bash
# Check if MVidarr is running
ps aux | grep mvidarr
# or for Docker
docker ps | grep mvidarr

# Check port availability
netstat -tulpn | grep 5000
# or
lsof -i :5000

# Test local connection
curl http://localhost:5000/health
```

**Solutions:**
1. **Service not running**: Start MVidarr service
2. **Port conflict**: Change port in settings or kill conflicting process
3. **Firewall blocking**: Allow port 5000 through firewall
4. **Wrong URL**: Verify correct IP address and port

### Login Issues

#### Problem: Can't login with correct credentials

**Check Authentication Settings:**
```bash
# Verify authentication is enabled
curl http://localhost:5000/api/settings/require_authentication

# Check user exists (if using database auth)
sqlite3 database/mvidarr.db "SELECT username, is_active FROM users;"
```

**Solutions:**
1. **Authentication disabled**: Check Settings → Authentication
2. **Account locked**: Wait for lockout period or reset in database
3. **Wrong password**: Use password recovery or reset via database
4. **Session issues**: Clear browser cookies and cache

### Video Discovery Not Working

#### Problem: No videos found when adding artists

**Diagnostic Steps:**
```bash
# Check API keys
curl http://localhost:5000/api/settings/imvdb_api_key
curl http://localhost:5000/api/settings/youtube_api_key

# Test API connectivity
curl -I https://imvdb.com/api/v1/
curl -I https://www.googleapis.com/youtube/v3/
```

**Solutions:**
1. **Missing API keys**: Add IMVDB and YouTube API keys in Settings
2. **Invalid API keys**: Verify keys are correct and active
3. **Network issues**: Check firewall and proxy settings
4. **Service outage**: Check IMVDB/YouTube service status

### Download Failures

#### Problem: Videos fail to download

**Check Download Status:**
```bash
# View recent logs for download errors
tail -100 /path/to/logs/mvidarr.log | grep -i download

# Check download directory permissions
ls -la /path/to/downloads
```

**Common Solutions:**
1. **Permission issues**: Fix download directory permissions
2. **Disk space**: Check available storage space
3. **Network issues**: Verify internet connectivity
4. **YouTube restrictions**: Video may be geo-blocked or removed

### Video Playback Issues

#### Problem: Chrome browser crashes when seeking videos with subtitles

**Symptoms:**
- Browser displays "STATUS_BREAKPOINT" error when seeking
- Video player freezes or becomes unresponsive
- Chrome tab crashes when dragging video timeline
- Only occurs when subtitles are enabled

**Solution (v0.10.0-beta.1):**
This is a known Chrome browser bug that has been addressed with a Chrome-specific workaround:

1. **Automatic Protection**: MVidarr automatically disables subtitles during seek operations in Chrome
2. **Browser Detection**: Workaround only applies to Chrome (Firefox, Safari, Edge unaffected)
3. **Manual Re-enable**: After seeking, manually re-enable subtitles using the CC button if needed

**Alternative Solutions:**
1. **Use Different Browser**: Firefox or Edge provide better subtitle stability
   - Subtitles remain active during seeking
   - No manual re-enabling required
   - Recommended for users who frequently use subtitles

2. **Disable Subtitles**: If crashes persist, disable subtitles in Chrome:
   - Click CC button to turn off subtitles
   - Seek to desired position
   - Re-enable subtitles after seeking

**Technical Details:**
- **Affected**: Chrome 90-130+ (all versions)
- **Root Cause**: Chrome video decoder bug with subtitle tracks
- **Workaround**: JavaScript detection and track disabling
- **Status**: Permanent workaround until Chrome fixes upstream bug

See [Browser Compatibility Guide](BROWSER_COMPATIBILITY.md) for detailed browser support information.

#### Problem: Video won't play or shows error

**Quick Fixes:**
```bash
# Check video file exists
ls -la /path/to/videos/

# Check file permissions
ls -l /path/to/videos/videofile.mp4

# Test video file integrity
ffmpeg -v error -i /path/to/videos/videofile.mp4 -f null -
```

**Common Solutions:**
1. **Unsupported format**: MVidarr auto-transcodes MKV files to MP4
2. **Corrupted file**: Re-download the video
3. **Permission issues**: Fix video directory permissions
4. **Missing codecs**: Ensure FFmpeg is installed with H.264/AAC support

#### Problem: Subtitles not showing

**Diagnostic Steps:**
```bash
# Check subtitle files exist
ls /path/to/videos/*.{vtt,srt,ass,ssa,sub}

# Verify subtitle API endpoint
curl http://localhost:5000/api/videos/{video_id}/subtitles
```

**Solutions:**
1. **No subtitle files**: Enable subtitle download in Settings → Downloads
2. **Wrong language**: Check subtitle_languages setting matches available subtitles
3. **Browser cache**: Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
4. **CC button**: Manually enable using browser's CC controls

## 🔍 Detailed Troubleshooting Procedures

### Database Issues

#### Database Connection Errors

**Symptoms:**
- "Database connection failed" errors
- Settings not loading
- Artists/videos not displaying

**Diagnostic Steps:**
```bash
# Check database file exists and permissions
ls -la database/mvidarr.db

# Test database connectivity
sqlite3 database/mvidarr.db ".tables"

# Check database integrity
sqlite3 database/mvidarr.db "PRAGMA integrity_check;"
```

**Solutions:**
1. **File permissions**:
   ```bash
   chmod 664 database/mvidarr.db
   chown mvidarr:mvidarr database/mvidarr.db
   ```

2. **Database corruption**:
   ```bash
   # Create backup first
   cp database/mvidarr.db database/mvidarr.db.backup
   
   # Try to repair
   sqlite3 database/mvidarr.db ".recover" | sqlite3 database/mvidarr_recovered.db
   ```

3. **Missing database**:
   - Restore from backup
   - Or restart MVidarr to create new database

#### Database Performance Issues

**Symptoms:**
- Slow page loading
- Timeouts when browsing large libraries

**Solutions:**
1. **Database optimization**:
   ```sql
   PRAGMA optimize;
   VACUUM;
   REINDEX;
   ```

2. **Increase connection pool**:
   - Settings → Database → Pool Size: Increase to 20
   - Settings → Database → Max Overflow: Increase to 40

### Performance Issues

#### Slow Interface Response

**Diagnostic Steps:**
```bash
# Check system resources
htop
free -h
df -h

# Check MVidarr process resources
ps aux | grep mvidarr
```

**Solutions:**
1. **High memory usage**:
   - Restart MVidarr service
   - Increase system RAM if consistently high
   - Check for memory leaks in logs

2. **High CPU usage**:
   - Check for runaway background processes
   - Reduce concurrent downloads
   - Optimize database queries

3. **Disk I/O issues**:
   - Move database to faster storage (SSD)
   - Check for disk errors
   - Optimize file system

#### Large Library Performance

**For libraries with 10,000+ videos:**

1. **Database optimization**:
   ```bash
   # Increase cache size
   sqlite3 database/mvidarr.db "PRAGMA cache_size=10000;"
   
   # Enable WAL mode
   sqlite3 database/mvidarr.db "PRAGMA journal_mode=WAL;"
   ```

2. **Frontend optimization**:
   - Enable virtualization for large lists
   - Use filters to reduce displayed items
   - Consider pagination settings

### Network and API Issues

#### External API Failures

**IMVDB API Issues:**
```bash
# Test IMVDB connectivity
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "https://imvdb.com/api/v1/search/videos?q=test"

# Check API quota
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "https://imvdb.com/api/v1/account"
```

**YouTube API Issues:**
```bash
# Test YouTube API
curl "https://www.googleapis.com/youtube/v3/search?part=snippet&q=test&key=YOUR_API_KEY"
```

**Solutions:**
1. **API key issues**:
   - Verify keys are correct
   - Check API key permissions and quotas
   - Regenerate keys if necessary

2. **Rate limiting**:
   - Reduce request frequency
   - Implement longer delays between requests
   - Check API usage quotas

3. **Network restrictions**:
   - Check corporate firewall settings
   - Configure proxy if required
   - Test from different network

### File System Issues

#### Permission Problems

**Symptoms:**
- "Permission denied" errors
- Files not organizing properly
- Download failures

**Solutions:**
```bash
# Fix file permissions
sudo chown -R mvidarr:mvidarr /path/to/mvidarr/data
sudo chmod -R 755 /path/to/mvidarr/data
sudo chmod -R 777 /path/to/mvidarr/data/downloads

# Check directory structure
ls -la /path/to/mvidarr/data
```

#### Storage Issues

**Disk Space Problems:**
```bash
# Check available space
df -h /path/to/video/storage

# Find largest files
du -sh /path/to/video/storage/* | sort -rh | head -20

# Clean up temporary files
find /path/to/downloads -name "*.part" -mtime +1 -delete
find /path/to/downloads -name "*.tmp" -mtime +1 -delete
```

## ❓ Frequently Asked Questions

### General Questions

**Q: How do I change the port MVidarr runs on?**
A: Settings → General → App Port, or set `PORT` environment variable

**Q: Can I run multiple MVidarr instances?**
A: Yes, but each needs separate database and file paths, plus different ports

**Q: How do I backup my MVidarr library?**
A: Settings → Backup → Create Backup, or manually copy database and configuration files

**Q: Does MVidarr support other video formats besides MP4?**
A: Yes, MVidarr can download various formats. Set quality preference in Settings → Downloads

### Setup and Configuration

**Q: What API keys do I need?**
A: IMVDB API key is essential. YouTube API key is optional but recommended for better discovery

**Q: How do I get an IMVDB API key?**
A: Visit https://imvdb.com/developers and request an API key

**Q: Can I use MVidarr without API keys?**
A: Limited functionality. You can manually add videos by URL but won't have automatic discovery

**Q: How do I set up HTTPS/SSL?**
A: Settings → Security → SSL Settings, or use reverse proxy (see Configuration Guide)

### Library Management

**Q: How does MVidarr organize videos?**
A: By default: `/Artist Name/Song Title.ext`. Configurable in Settings → Downloads

**Q: Can I change video quality after download?**
A: Yes, use "Upgrade Quality" feature to download higher quality versions

**Q: How do I handle duplicate videos?**
A: MVidarr detects duplicates automatically. Use Videos → Duplicates to review and merge

**Q: What happens when I mark a video as "Ignored"?**
A: It won't be downloaded and will be hidden from most views. Use filters to view ignored videos

### Downloads and Processing

**Q: Why are downloads slow?**
A: Check concurrent download setting, internet connection, and YouTube throttling

**Q: Can I download entire playlists?**
A: Yes, use Add Video → Playlist tab to import YouTube playlists

**Q: How do I resume failed downloads?**
A: Go to Videos → Filter by "Failed" → Select videos → Retry Download

**Q: Does MVidarr support scheduling downloads?**
A: Yes, Settings → Scheduling → Auto-Download Schedule

### Troubleshooting

**Q: Videos page is blank/empty**
A: Check database connection, API keys, and browser console for errors

**Q: "Health check failed" error**
A: Usually indicates service isn't running or database issues. Check logs for details

**Q: Artist thumbnails not loading**
A: Check thumbnail directory permissions and IMVDB API key

**Q: Search not working**
A: Verify database connection and check for JavaScript errors in browser console

## 🔧 Advanced Troubleshooting

### Log Analysis

#### Finding and Reading Logs

**Log Locations:**
```bash
# Docker deployment
docker logs mvidarr-app

# Local installation
~/.local/share/mvidarr/logs/mvidarr.log
/var/log/mvidarr/mvidarr.log
```

**Useful Log Commands:**
```bash
# View recent errors
tail -100 mvidarr.log | grep -i error

# Monitor live logs
tail -f mvidarr.log

# Search for specific issues
grep -i "download.*fail" mvidarr.log
grep -i "database" mvidarr.log | grep -i error
```

#### Common Log Patterns

**Database Issues:**
```
ERROR: database is locked
ERROR: no such table
WARNING: connection timeout
```

**API Issues:**
```
ERROR: IMVDB API request failed
WARNING: YouTube quota exceeded
ERROR: connection refused to api.imvdb.com
```

**File System Issues:**
```
ERROR: Permission denied
ERROR: No space left on device
WARNING: File not found
```

### Performance Profiling

#### Identifying Bottlenecks

**Database Performance:**
```sql
-- Check slow queries
PRAGMA compile_options;
PRAGMA optimize;

-- Analyze table statistics
ANALYZE;
```

**API Performance:**
```bash
# Test API response times
time curl http://localhost:5000/api/videos
time curl http://localhost:5000/api/artists
```

**System Performance:**
```bash
# Monitor resource usage
iostat -x 1 5
sar -u 1 5
```

### Recovery Procedures

#### Complete System Recovery

**When MVidarr won't start:**

1. **Check service status**:
   ```bash
   systemctl status mvidarr
   journalctl -u mvidarr -f
   ```

2. **Verify configuration**:
   ```bash
   # Test configuration syntax
   python -c "from src.config import Config; Config()"
   ```

3. **Database recovery**:
   ```bash
   # Backup current state
   cp database/mvidarr.db database/mvidarr.db.broken
   
   # Try repair
   sqlite3 database/mvidarr.db ".dump" | sqlite3 database/mvidarr_fixed.db
   ```

4. **Fresh installation** (last resort):
   ```bash
   # Backup important data
   cp -r database/ backup/
   cp -r config/ backup/
   
   # Reinstall MVidarr
   # Restore configuration and database
   ```

## 📞 Getting Additional Help

### Self-Diagnostic Tools

**Health Check:**
```bash
# Built-in health check
curl http://localhost:5000/health

# Comprehensive system check
curl http://localhost:5000/api/system/status
```

**Configuration Validation:**
```bash
# Verify all settings
curl http://localhost:5000/api/settings/validate
```

### Support Resources

**Documentation:**
- Configuration Guide: `CONFIGURATION_GUIDE.md`
- Docker Troubleshooting: `TROUBLESHOOTING_DOCKER.md`
- Architecture Guide: `ARCHITECTURE.md`
- User Workflows: `USER_WORKFLOWS.md`

**Community Support:**
- GitHub Issues: Report bugs and get help
- Documentation: Comprehensive guides
- Community Forums: User discussions

### Reporting Issues

**When reporting issues, include:**

1. **System Information:**
   ```bash
   # OS and version
   uname -a
   
   # MVidarr version
   curl http://localhost:5000/api/version
   
   # Python version
   python --version
   ```

2. **Configuration Details:**
   ```bash
   # Sanitized settings (remove API keys)
   curl http://localhost:5000/api/settings/ | jq 'del(.imvdb_api_key, .youtube_api_key)'
   ```

3. **Error Logs:**
   ```bash
   # Recent errors
   tail -50 mvidarr.log | grep -i error
   ```

4. **Steps to Reproduce:**
   - Exact steps that cause the issue
   - Expected vs actual behavior
   - Browser/client information

### Emergency Contacts

**Critical Issues:**
- Data loss or corruption
- Security vulnerabilities  
- Service completely unavailable

**Non-Critical Issues:**
- Feature requests
- Performance optimization
- Documentation improvements

## 📋 Troubleshooting Checklist

### Basic Checks
- [ ] Service is running
- [ ] Database is accessible
- [ ] Network connectivity works
- [ ] API keys are configured
- [ ] File permissions are correct
- [ ] Sufficient disk space available

### Advanced Checks
- [ ] Log files for errors
- [ ] System resource usage
- [ ] Database integrity
- [ ] API service availability
- [ ] Network firewall rules
- [ ] SSL certificate validity (if using HTTPS)

### Performance Checks
- [ ] Response times acceptable
- [ ] Memory usage reasonable
- [ ] CPU usage normal
- [ ] Disk I/O not excessive
- [ ] Database queries optimized
- [ ] Cache hit rates good

This troubleshooting guide should resolve most MVidarr issues. For problems not covered here, consult the specific documentation guides or seek community support.