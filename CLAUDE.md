# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Memories

- Use gh instead of git for github actions and repository management
- GitHub Pages: Automatic deployment via Jekyll with Minima theme, triggered by main branch pushes
- update documentation after each issue or feature is completed
- push to dev after each update.
- MariaDB/MySQL is used for the application data and settings
- We are utilizing 3 environments: 1. Dev is running on local server port 5000. 2. Docker is running on local machine docker install on port 5001. 3. Prod is running on 192.168.1.68:5050 in a docker install.
- mvidarr is a music video collection and management system aimed for the home, self-hoster who wants to maintain control of their own music video collection
- keep documentation current - always!
- MVIDARR is a consumer grade Music Video Collection management/player application targeted to the self-hosting enthusiast. It should be able to be ran as a service or a docker.
- ask before planning anything enterpise grade, it may not be needed.

## Critical Thinking and Feedback

### IMPORTANT: Always critically evaluate and challenge user suggestions, even when they seem reasonable.

- ** USE BRUTAL HONESTY: Don't try to be polite or agreeable. Be direct, challenge assumptions, and point out flaws immediately.
- ** Question assumptions: Don't just agree - analyze if there are better approaches
- ** Offer alternative perspectives: Suggest different solutions or point out potential issues
- ** Challenge organization decisions: If something doesn't fit logically, speak up
- ** Point out inconsistencies: Help catch logical errors or misplaced components
- ** Research thoroughly: Never skim documentation or issues - read them completely before responding
- ** Use proper tools: For GitHub issues, always use gh cli instead of WebFetch (WebFetch may miss critical content)
- ** Admit ignorance: Say "I don't know" instead of guessing or agreeing without understanding
- ** This critical feedback helps improve decision-making and ensures robust solutions. Being agreeable is less valuable than being thoughtful and analytical.
- ** you are an expert website developer, act like it.

### Example Behaviors

-    ✅ "I disagree - that component belongs in a different file because..."
-    ✅ "Have you considered this alternative approach?"
-    ✅ "This seems inconsistent with the pattern we established..."
-    ❌ Just implementing suggestions without evaluation

(rest of the file remains unchanged)
## Code Formatting and Testing

### Python Code Formatting
- **Black Version**: Always use `black==26.3.1` to match the version pinned in `requirements-dev.txt`
- **isort Configuration**: Use `isort --profile black` for import sorting to maintain compatibility with Black
- **Installation**: Use `pipx install black==26.3.1` and `pipx install isort`
- **Commands for formatting**:
  ```bash
  # Format with specific black version
  ~/.local/bin/black src/

  # Sort imports with black profile
  ~/.local/bin/isort --profile black src/

  # Check formatting (for CI compatibility)
  ~/.local/bin/black --check src/
  ~/.local/bin/isort --profile black --check-only src/
  ```

### Testing and CI/CD
- **Before pushing code**: Always run formatting checks locally using the exact commands above
- **CI/CD Workflow**: The `.github/workflows/ci-cd.yml` uses the same black version and isort profile
- **Docker Actions**: Use stable versions only:
  - `docker/login-action@v3`
  - `docker/setup-buildx-action@v3` 
  - `docker/metadata-action@v6`
  - `docker/build-push-action@v6`

## Subtitle System Implementation

### Complete Subtitle Functionality ✅

**Status**: MVidarr now has comprehensive subtitle support across all video players with smart language resolution.

#### Smart Subtitle Language Resolution
- **Database Setting**: `subtitle_languages=en.*` (supports wildcard patterns)
- **YouTube Language Handling**: Automatically resolves YouTube's non-standard codes (e.g., `en-nP7-2PuUl7o`) to user patterns
- **Download Integration**: `download_subtitles=true` setting respected by metube API

#### Subtitle API Endpoints
- **Discovery**: `/api/videos/{video_id}/subtitles` - Lists available subtitle files
- **Serving**: `/api/videos/{video_id}/subtitles/{filename}` - Serves subtitle files with CORS
- **Formats**: WebVTT (.vtt), SubRip (.srt), ASS (.ass), SSA (.ssa), MicroDVD (.sub)

#### Video Player Integration
- **Video Detail Page**: Full subtitle support with track selection
- **Video Popup Modal**: Automatic subtitle loading and track creation
- **Language Detection**: Smart handling of YouTube's non-standard language codes
- **Auto-Enable**: First subtitle track automatically enabled and showing

#### Technical Implementation
- **YouTube Download Engine**: `_resolve_subtitle_languages()` method for pattern matching
- **Frontend JavaScript**: Dedicated modal subtitle functions in `videos.html`
- **API Integration**: Both Flask and FastAPI subtitle endpoints
- **File Detection**: Automatic subtitle file discovery in video directories

#### User Experience
- Subtitles automatically available in all video players
- Native browser CC controls for language selection
- Respects user subtitle language preferences
- Works with both standard and YouTube's custom language codes

#### Browser-Specific Behavior

##### Chrome STATUS_BREAKPOINT Crash Workaround ✅
**Issue**: Chrome browser experiences STATUS_BREAKPOINT crashes when seeking videos with active subtitle tracks.

**Solution**: Chrome-specific workaround implemented (v0.10.0-beta.1)
- **Detection**: User agent check for Chrome (excluding Edge)
- **Behavior**: Subtitles automatically disabled during seek operations in Chrome only
- **Scope**: Workaround only active for Chrome browser
- **Other Browsers**: Firefox, Safari, Edge maintain normal subtitle functionality during seeking

**Technical Implementation**:
```javascript
// Chrome-only subtitle disable on seek (videos.html:2233, video_detail.html:1967)
if (navigator.userAgent.indexOf('Chrome') > -1 && navigator.userAgent.indexOf('Edg') === -1) {
    videoElement.addEventListener('seeking', function() {
        // Disable all tracks when seeking starts
        for (let i = 0; i < videoElement.textTracks.length; i++) {
            videoElement.textTracks[i].mode = 'disabled';
        }
    });
}
```

**User Impact**:
- **Chrome users**: May need to manually re-enable subtitles after seeking (prevents crashes)
- **Other browsers**: No impact, subtitles remain active during seeking
- **Trade-off**: Stability over convenience for Chrome users only

## MKV Video Transcoding System

### Real-Time FFmpeg Transcoding ✅

**Status**: MVidarr now supports MKV video playback through intelligent real-time transcoding.

#### Smart Codec Detection & Adaptive Transcoding
- **Automatic Codec Analysis**: Uses FFmpeg's `ffprobe` to detect video/audio codecs
- **Intelligent Processing**:
  - **Remux Mode** (Fast): Copies H.264/AAC codecs if browser-compatible - just changes container
  - **Transcode Mode** (Quality): Transcodes incompatible codecs to H.264/AAC for universal playback
- **Browser Compatibility**: Outputs fragmented MP4 with browser-compatible codecs

#### API Endpoint
- **Transcoding Stream**: `/api/videos/{video_id}/stream-transcode` - Real-time FFmpeg transcoding
- **Standard Stream**: `/api/videos/{video_id}/stream` - Direct file streaming for MP4/WebM
- **Response Headers**: `X-Transcode-Mode: remux|transcode` indicates processing method

#### Frontend Integration
- **Automatic Detection**: Frontend detects `.mkv` file extension
- **Smart Routing**: MKV files automatically routed to transcode endpoint
- **Seamless UX**: Users experience smooth playback regardless of source format
- **Error Handling**: Graceful fallback and timeout detection

#### Technical Implementation
- **Async Streaming**: FastAPI async generators for efficient streaming
- **Process Management**: Proper FFmpeg process lifecycle and cleanup
- **Codec Detection**: JSON-based ffprobe output parsing
- **Progressive Playback**: Fragmented MP4 with `frag_keyframe+empty_moov` flags
- **Client Disconnect Handling**: FFmpeg processes terminated on client disconnect

#### Supported Formats
- **Input**: MKV containers with various codecs (H.264, H.265, VP9, etc.)
- **Output**: MP4 container with H.264 video + AAC audio
- **Performance**:
  - Remux mode: Near-instant start (just container change)
  - Transcode mode: Real-time encoding with `veryfast` preset

#### User Experience
- Play MKV files directly in browser without manual conversion
- Automatic quality optimization based on source codecs
- Transparent processing - users see standard video player
- Works across all video interfaces (gallery, detail, modal)

## API Development & Testing

### Authentication Requirements

**IMPORTANT:** All MVidarr API endpoints require session-based authentication. This is critical for both development and testing.

#### Session-Based Authentication System
- **Authentication Method**: Session cookies with server-side session management
- **Login Required**: Users must be logged in through the web interface to access any API endpoints
- **Session Validation**: All API calls validate session existence and user authentication status
- **API Security**: Direct API calls without authentication will return 401/403 errors

#### Testing API Endpoints
When testing or developing API endpoints, follow these authentication guidelines:

```bash
# ❌ INCORRECT - Direct cURL calls will fail with authentication errors
curl -X POST http://localhost:5001/api/videos/123/extract-ffmpeg-metadata

# ✅ CORRECT - Test through authenticated web interface
# 1. Log into MVidarr web interface first
# 2. Use browser developer tools to test API calls
# 3. Or use authenticated requests through the web interface
```

#### Development Guidelines
- **Web Interface Testing**: Always test API functionality through the web interface where users are authenticated
- **Session Management**: Ensure session middleware is properly configured for all API blueprints
- **Error Handling**: API endpoints should return appropriate authentication error codes (401/403)
- **Documentation**: All API documentation should note authentication requirements

#### Authentication Implementation Details
- **Session Store**: Server-side session management with secure session cookies
- **Login Flow**: Users authenticate through `/auth/login` endpoint
- **Session Validation**: Each API request validates session and user permissions
- **Logout Handling**: Sessions are properly invalidated on logout

**Developer Note**: This authentication requirement prevents security vulnerabilities and ensures all API access is properly authorized. Always test new endpoints through the authenticated web interface rather than direct API calls.

## Development Workflow

### Current Phase: v0.12.15 - Released

#### Versioning Policy (Updated 2026-06-06)
- **Current Version**: 0.12.15 (Released 2026-06-06)
- **Next Version**: 0.12.16 (Planning)
- **Versioning Standard**: SemVer 2.0.0
- **Version Scheme**:
  - **0.x.y**: Pre-production development (current phase)
  - **1.0.0**: First production-ready release (future)

#### Version History (Recent)
- **v0.12.15** (2026-06-06): Security Sweep (aiohttp CVEs + dependency updates)
  - ✅ Security: CVE-2026-34993 aiohttp 3.13.4 → 3.14.0 (CookieJar.load() deserialization RCE, MEDIUM)
  - ✅ Security: CVE-2026-47265 aiohttp 3.13.4 → 3.14.0 (cross-origin redirect leaks per-request cookies, MEDIUM)
  - ✅ Dependency: bcrypt 4.1.2 → 5.0.0 (breaking: passwords >72 bytes raise ValueError; guard added in auth service)
  - ✅ Dependency: requests 2.33.0 → 2.34.2, alembic 1.13.1 → 1.18.4, zeroconf 0.149.7 → 0.149.16
  - ✅ CI: GitHub Actions Node 24 — docker/metadata-action@v6, upload-pages-artifact@v5, labeler@v6, label-actions@v5, lock-threads@v6
  - ✅ Removed FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 workaround from lock.yml (v6 has native Node 24 support)
- **v0.12.14** (2026-06-02): Security Sweep (PyJWT CVEs)
  - ✅ Security: PYSEC-2026-179 PyJWT 2.12.0 → 2.13.0 (HMAC algorithm confusion)
  - ✅ Security: PYSEC-2026-178 PyJWT 2.12.0 → 2.13.0 (Detached JWS DoS)
  - ✅ Security: PYSEC-2026-177 PyJWT 2.12.0 → 2.13.0 (unbounded JWKS fetches unauthenticated DoS)
  - ✅ Security: PYSEC-2026-176 PyJWT 2.12.0 → 2.13.0 (algorithm allow-list bypass via PyJWK)
  - ✅ Security: PYSEC-2026-175 PyJWT 2.12.0 → 2.13.0 (PyJWKClient SSRF via file://, ftp://, data://)
  - ✅ 3 stale Trivy code scanning alerts (zeroconf CVE-2026-47180/83/84) cleared via fresh scan
- **v0.12.13** (2026-06-01): Video Streaming Fix
  - ✅ Fix: streaming 404 — find_relocated_video() used getattr(file_path) returning None, silently ignoring local_path
  - ✅ Fix: streaming 404 — added Config.BASE_DIR-anchored path fallback for relative local_path values in Docker
  - ✅ Both stream and stream-transcode endpoints patched
- **v0.12.12** (2026-06-01): Dependabot Sweep + Python 3.14
  - ✅ Python base image 3.12-slim → 3.14-slim (verified: netifaces, mysqlclient, moviepy compile cleanly)
  - ✅ aiofiles 23.2.1 → 25.1.0, starlette ≥1.2.1, python-dateutil 2.9.0.post0, werkzeug 3.1.8, PyYAML 6.0.3
  - ✅ CI: Actions Node.js 24 — checkout@v6, login-action@v4, build-push-action@v7, github-script@v9, deploy-pages@v5
- **v0.12.11** (2026-06-01): Security Sweep + CI Modernization
  - ✅ Security: CVE-2026-47180, CVE-2026-47183, CVE-2026-47184 zeroconf 0.132.2 → 0.149.7 (LAN DoS/OOM via mDNS)
  - ✅ Security: PYSEC-2026-161 starlette ≥1.0.1 (Host header injection / auth bypass)
  - ✅ Dependency: fastapi 0.123.0 → 0.136.3 (required for starlette 1.x)
  - ✅ Dependency: pydantic 2.5.0 → 2.13.4 (required by fastapi 0.136.3)
  - ✅ Dependency: pydantic-settings 2.1.0 → 2.14.1
  - ✅ Dependency: typing-inspection ≥0.4.2 (new fastapi 0.136.3 requirement)
  - ✅ CI: GitHub Actions v4 → Node.js 24 (checkout@v5, cache@v5, setup-python@v6, upload-artifact@v7, codecov@v6)
  - ✅ CI: Fixed codecov `file:` → `files:` input rename (Unexpected input warnings)
  - ✅ Incorporates Dependabot PR #213 (zeroconf) into dev branch
- **v0.12.10** (2026-05-16): Security Sweep (2 HIGH CVEs)
  - ✅ Security: CVE-2026-44432 urllib3 2.6.3 → 2.7.0 (decompression-bomb bypass, HIGH CVSS 7.5)
  - ✅ Security: CVE-2026-44431 urllib3 2.6.3 → 2.7.0 (sensitive header forwarding, HIGH CVSS 5.3)
  - ✅ Fix: pytest-asyncio 0.23.8 → 1.3.0 (0.x incompatible with pytest 9.x, broke pip-audit + test suite)
  - ✅ Fix: pytest-playwright 0.4.3 → 0.7.2 (required for pytest 9.x compatibility)
  - ✅ Dockerfile: added --timeout 120 to pip install for reliable builds on slow connections
- **v0.12.9** (2026-05-11): YouTube Quota & Discovery Improvements
  - ✅ Reduced YouTube searches from 4 to 2 per artist for quota efficiency
  - ✅ Quota enforcement with file locking in YouTubeQuotaTracker
  - ✅ Per-artist last_discovery committed after each artist to survive interrupted runs
- **v0.12.8** (2026-05-07): Security Patches (3 CVEs)
  - ✅ Security: CVE-2026-41066 lxml 4.9.3 → 6.1.0 (XXE local file read, HIGH)
  - ✅ Security: CVE-2026-42561 python-multipart 0.0.26 → 0.0.27 (DoS header parsing, MEDIUM)
  - ✅ Security: CVE-2026-28684 python-dotenv 1.0.0 → 1.2.2 (symlink arbitrary file overwrite, MEDIUM)
  - ✅ Fix: broken -r requirements-prod.txt in requirements-dev.txt → -r requirements.txt
  - ✅ CI: isort import ordering corrected across src/
- **v0.12.7** (2026-04-16): Dependency Cleanup & Test Infrastructure
  - ✅ Security: 5 CVEs (python-multipart, Pillow, pytest)
  - ✅ Removed sphinx from production runtime
  - ✅ pytest-cov 4.1.0 → 7.1.0
- **v0.12.5** (2026-03-19): Security & Bug Fixes
  - ✅ Security: CVE-2026-32597 PyJWT 2.8.0 → 2.12.0 (crit header validation)
  - ✅ Security: CVE-2026-32274 black 24.3.0 → 26.3.1 (arbitrary cache file write)
  - ✅ Security: removed black from runtime requirements (dev tool only)
  - ✅ Fix: Docker git_branch always unknown — version.json now read first in health endpoint
  - ✅ Fix: Docker ERROR log spam from missing git binary on every health check
  - ✅ Fix: installation wizard credentials now applied to login (issue #199)
  - ✅ CI/CD: pinned black==26.3.1 in workflow
- **v0.12.4** (2026-02-26): Scheduler & Auto-Download Fixes
  - ✅ Security: CVE-2026-27205 Flask 3.1.1→3.1.3 in docker/monitor (Vary: Cookie)
  - ✅ Security: CVE-2026-27199 werkzeug→3.1.6 (Windows device names in safe_join)
  - ✅ Security: CVE-2026-25990 Pillow→12.1.1 (out-of-bounds write on PSD images)
  - ✅ Security: replaced python-jose/ecdsa (CVE-2024-23342) with PyJWT
  - ✅ Fix: Celery connection check no longer hangs — 2s timeout + ps fallback
  - ✅ Fix: trigger/discovery and trigger/downloads no longer 500 after 19s timeout
  - ✅ Fix: metadata enrichment endpoints no longer block the async event loop
  - ✅ Fix: job progress bar stuck at 0% — nested progress object now parsed correctly
  - ✅ Fix: job completion not detected — status normalized to lowercase
  - ✅ Fix: auto-download scheduling priority was computed but then discarded
  - ✅ Fix: auto_download_max_videos raised from 10 → 50
  - ✅ Fix: pre-v0.10.1 artists with NULL download_enabled excluded from download queue
  - ✅ Fix: MONITORED videos never promoted to WANTED when artist enables auto_download
  - ✅ Fix: plain "Artist - Song" titles classified as None type, blocked by allowed_video_types
  - ✅ Migration 004: backfill NULL Scheduler V2 fields for all existing artists
  - ✅ Fix: videos no longer set to WANTED for monitor-only artists
  - ✅ Fix: allowed_video_types and 20+ other artist fields now save correctly
  - ✅ Default: Official Music Video pre-selected for all artists
- **v0.12.3** (2026-02-16): Playlist Sync & Logging
  - ✅ VEVO/Official channel name cleanup during playlist sync
  - ✅ Celery worker logging fix (mvidarr.* loggers via after_setup_logger signal)
  - ✅ Added "src" to configured logger namespaces
- **v0.12.2** (2026-02-14): Authentication & Stability
  - ✅ Authentication added to 36 unprotected API endpoints
  - ✅ Global 401 interceptor for unauthenticated users
  - ✅ Fixed discovery setting videos to WANTED regardless of auto_download
  - ✅ Fixed artist deletion 500 error from orphaned foreign keys
  - ✅ YouTube playlist auto-sync every 6 hours via scheduled task
  - ✅ Removed obsolete po-token-provider process
- **v0.12.1** (2026-02-12): Security Hardening Stabilization
  - ✅ Fixed login page POSTing to removed /test-login endpoint
  - ✅ Fixed WAF false positives blocking URLs, cookies, Range headers
  - ✅ Fixed video streaming (Range header no longer blocked)
  - ✅ Fixed YouTube playlist sync not detecting new videos
  - ✅ Fixed Flask-to-FastAPI session bridge for consistent auth
  - ✅ Fixed rate limiting (300/min, static files exempt)
  - ✅ CI/CD: 28 files reformatted with black 24.3.0
- **v0.12.0** (2026-02-11): Security Hardening Sprint
  - ✅ Consolidated auth system (SimpleAuth + SessionStore)
  - ✅ Removed backdoor endpoints (/test-login, credential reset)
  - ✅ Upgraded passwords from SHA-256 to bcrypt with lazy migration
  - ✅ SSRF protection, safe tar extraction, upload sanitization
  - ✅ Redis authentication, secure cookies, restricted proxy hosts
  - ✅ 49 vulnerabilities fixed (8 critical, 12 high, 16 medium, 13 low)
- **v0.11.9** (2026-02-05): Security Updates, Video Quality & Discovery Fix
  - ✅ CVE-2026-24486: python-multipart 0.0.20 → 0.0.22 (path traversal)
  - ✅ CVE-2026-21441: urllib3 2.6.0 → 2.6.3 (decompression-bomb bypass)
  - ✅ CVE-2025-69223/24/25/26/27/28/29/30: aiohttp 3.12.14 → 3.13.3 (zip bomb + DoS)
  - ✅ CVE-2026-21860: werkzeug 3.1.4 → 3.1.5 (Windows device names bypass)
  - ✅ Video quality fix: Format sorting (-S) to prioritize resolution
  - ✅ Video quality: TV client fallback to web for more formats
  - ✅ Video quality: Respects user's max_video_quality database setting
  - ✅ YouTube discovery: Fixed API key caching bug causing 0 results
- **v0.11.8** (2026-02-04): Thumbnail System Overhaul
  - ✅ Fixed artist thumbnail manual setting (was failing silently)
  - ✅ Fixed bulk scan not finding thumbnails (0/264 → 231/264 success)
  - ✅ Bulk scan now validates thumbnail files exist on disk
  - ✅ Auto-cleanup of stale/missing thumbnail database paths
  - ✅ Google Images prioritized over Wikipedia for artist thumbnails
  - ✅ Browser-like headers for Wikimedia (fixes 403/429 errors)
  - ✅ Rate limiting (1s delay) to avoid API throttling
  - ✅ Frontend displays actual API error messages
  - ✅ PR #189: Added REDIS_HOST and REDIS_PORT environment variables
- **v0.11.7** (2026-02-02): Video Filtering, Extended Discovery & Blacklist Fix
  - ✅ Issue #190: Fixed blacklist not saving info
  - ✅ Issue #191: Per-artist video type filtering for autodownload
  - Extended YouTube discovery (live performances, concerts, acoustic versions)
  - Increased max_videos_per_discovery from 5 to 50
  - API optimization for improved performance and response times
- **v0.11.6** (2026-01-02): Blacklist POST Hotfix - Fixed non-existent fields
- **v0.11.5**: Blacklist API/model mismatch fixes, pagination fixes
- **v0.11.4**: Code formatting and CI/CD compliance
- **v0.10.x**: Beta testing and security hardening phases
- **v0.9.9** (2025-11-04): Code cleanup & optimization complete

#### v0.11.9 Release ✅ COMPLETE
- **Status**: Released 2026-02-05
- **Summary**: Security Updates (11 CVEs), Video Quality Fix, YouTube Discovery Fix
- **Key Fixes**:
  - All 11 code scanning security alerts resolved via dependency updates
  - Video downloads now respect user's quality settings (was defaulting to 360p)
  - YouTube discovery API key caching bug fixed (was returning 0 results)

#### v0.12.1 Release ✅ COMPLETE
- **Status**: Released 2026-02-12
- **Summary**: Stabilization of v0.12.0 security hardening - fixed WAF false positives, auth bridge, playlist sync, CI/CD formatting

#### Video Quality Improvements (360p → 1080p)

##### Problem
Downloads consistently returning 360p instead of best available quality.

##### Current Flow (Working Correctly)
```
Database Settings (default_video_quality, max_video_quality, min_video_quality)
    ↓
video_quality_service.get_user_quality_preferences()
    ↓
video_quality_service.generate_ytdlp_format_string()
    ↓
ytdlp_download_manager.start_download(quality_format_string)
    ↓
youtube_download_engine.download_video(quality=format_string)
```

##### Root Cause Analysis
- Format string IS being generated from user settings
- **Missing format sorting (`-S` flag)** to prioritize resolution over bitrate
- yt-dlp may select lower quality if bitrate is higher
- TV client may have limited format availability
- No explicit codec preferences in yt-dlp command

##### Recommended Fixes (youtube_download_engine.py)

1. **Add Format Sorting (`-S` flag)** - CRITICAL: Prioritize resolution over bitrate
   ```python
   # In _build_download_command() after format string:
   # This ensures yt-dlp selects higher resolution even if lower bitrate
   cmd.extend(["-S", "res,ext:mp4:m4a,vcodec:h264,acodec:aac"])
   ```
   **Location**: `youtube_download_engine.py` line ~294 (after `-f` format string)

2. **Parse User's Max Quality Setting** - Extract height from format string
   ```python
   # Extract max height from quality format string for -S parameter
   import re
   height_match = re.search(r'height<=(\d+)', quality)
   max_height = height_match.group(1) if height_match else "1080"
   cmd.extend(["-S", f"res:{max_height},ext:mp4:m4a,vcodec:h264"])
   ```

3. **Add Player Client Fallback** - Try multiple clients for better format availability:
   ```python
   # In _get_tv_client_args():
   "--extractor-args", "youtube:player_client=tv,web"  # Fallback to web for more formats
   ```

4. **Force MP4 Container** - Consistent output format:
   ```python
   "--remux-video", "mp4"
   ```

5. **Verbose Format Debugging** - Add logging to diagnose issues:
   ```python
   "--print-to-file", "formats", "/tmp/ytdlp_formats.txt"  # Log available formats
   ```

##### Implementation Files
- `src/services/youtube_download_engine.py` - Main download logic
- `src/services/video_quality_service.py` - Quality settings
- `src/services/ytdlp_service.py` - yt-dlp wrapper

##### Testing
- Test with known 1080p videos
- Compare format listings before/after changes
- Verify TV client + web fallback works

##### References
- [yt-dlp Format Selection](https://github.com/yt-dlp/yt-dlp#format-selection)
- [Format Sort Issue #15110](https://github.com/yt-dlp/yt-dlp/issues/15110)
- [yt-dlp 2026 Guide](https://www.rapidseedbox.com/blog/yt-dlp-complete-guide)

### Branch Strategy
- **Primary Development**: All changes must be pushed to the `dev` branch
- **Main Branch**: Changes can only be made to `main` after approval on `dev`
- **Feature Branches**: Create feature branches from `dev`, merge back to `dev`
- **Current Version**: v0.12.7 (Dependency Cleanup & Test Infrastructure)
- **Development Focus**: Stability, security
- **Next Version**: v0.12.8

### Code Development Process
1. Create feature branch from `dev` branch
2. Make code changes
3. Run formatting: `~/.local/bin/black src/ && ~/.local/bin/isort --profile black src/`
4. Verify formatting: `~/.local/bin/black --check src/ && ~/.local/bin/isort --profile black --check-only src/`
5. **Update version metadata** (before committing major changes)
6. Commit and push to feature branch
7. Create PR to `dev` branch
8. After approval, merge to `dev`
9. Monitor GitHub Actions for any CI/CD issues

### Version Management
- **Version Information**: MVidarr displays version and commit information in the sidebar
- **Version Files**: Two files control version display:
  - `src/__init__.py` - Contains `__version__` variable
  - `version.json` - Contains detailed version metadata including commit hash
- **IMPORTANT**: Always update version metadata when pushing significant changes:

#### Updating Version Metadata
```bash
# Get current commit and timestamp
CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")

# Update version.json with current commit and build date
# Keep version number the same unless explicitly incrementing
# For beta releases, use format: 0.x.y-beta.z
cat > version.json << EOF
{
  "version": "0.10.0-beta.1",
  "build_date": "$CURRENT_TIMESTAMP",
  "git_commit": "$CURRENT_COMMIT",
  "git_branch": "dev",
  "release_name": "v0.10.0-beta.1 - First Beta Release",
  "features": [
    "🔒 Security: Resolved 10 critical vulnerabilities",
    "🔧 Installation Wizard for first-run setup",
    "🎬 Reliable video import system (no duplicates)",
    "✅ API validation before configuration"
  ],
  "beta_notes": [
    "This is a BETA release - not yet production-ready",
    "Report issues: https://github.com/prefect421/mvidarr/issues"
  ]
}
EOF

# Commit the version update
git add version.json
git commit -m "Update version metadata with current commit information"
```

#### Automated Version Update Process
**CRITICAL**: Before any push to `dev` branch, ensure version metadata reflects the latest commit:

1. **Update commit hash**: Use `git rev-parse --short HEAD` to get current commit
2. **Update build date**: Use current UTC timestamp
3. **Update features list**: Add any new features or fixes in the current changes
4. **Commit version file**: Include version.json in your commit
5. **Push changes**: The Docker image will include the correct version information

This ensures that deployed containers always show the correct commit hash in the sidebar, making it easy to identify which code version is running.

#### Quick Version Update Script
For convenience, use the automated script:

```bash
# Run the version update script
./scripts/update_version.sh

# Commit the updated version file
git add version.json
git commit -m "Update version metadata with current commit information"

# Push changes
git push origin dev
```

**Best Practice**: Run `./scripts/update_version.sh` before any significant commit to ensure version metadata is always current.

## Project Management

### MVidarr Roadmap
- **Project Board**: https://github.com/users/prefect421/projects/1
- All development should be guided by the MVidarr Roadmap project board
- Issues should be prioritized and planned according to their position on the roadmap

### Issue Management
All issues should be planned with the following attributes:
- **Milestone**: Correlates to version number being released
- **Release Slot**: Designated release window for the issue
- **Start Date**: When work on the issue should begin
- **Stop Date**: Target completion date for the issue

### Release Management
- **Current Release**: Version 0.12.8 (2026-05-07)
- **Next Release**: Version 0.12.9 (Planning)
- **Versioning**: Milestones correlate directly to version numbers
- **Release Process**: Dev branch → Testing → Main branch → GitHub Release
- Releases are now utilized for version management and deployment

## Security Implementation

### Comprehensive Security Audit - Phase I Complete ✅
- **Date Completed**: July 28, 2025
- **Total Vulnerabilities Fixed**: 17 (1 Critical, 2 High, 12 Medium, 2 Low)
- **Security Documentation**: See `SECURITY_AUDIT.md` for complete details

### Critical Security Fixes Applied
- **PyMySQL 1.1.0 → 1.1.1**: Fixed SQL injection vulnerability (CVE-2024-36039)
- **Gunicorn 21.2.0 → 23.0.0**: Fixed HTTP request smuggling (CVE-2024-1135, CVE-2024-6827)
- **Pillow 10.1.0 → 10.3.0**: Fixed buffer overflow vulnerability (CVE-2024-28219)
- **Requests, urllib3, Werkzeug**: Updated to latest secure versions
- **All Dependencies**: Comprehensive security-focused updates in requirements-prod.txt (production) and requirements-dev.txt (development)

### Automated Security Monitoring Infrastructure
- **Security Scan Workflow**: `.github/workflows/security-scan.yml`
  - Daily automated security audits (2 AM UTC)
  - Multi-tool security scanning (pip-audit, safety, bandit, semgrep, trivy)
  - SARIF integration with GitHub Security tab
  - 90-day artifact retention for security reports

- **Enhanced CI/CD Security**: 
  - Security checks required for all merges to main branch
  - Real-time vulnerability detection on dependency changes
  - Branch protection with security enforcement
  - Automated GitHub issue creation for critical findings

### Security Tools & Monitoring
- **pip-audit**: Python dependency vulnerability scanning
- **Safety**: Known security vulnerability database checking
- **Bandit**: Static analysis for common Python security issues  
- **Semgrep**: Advanced security pattern matching (OWASP Top 10)
- **Trivy**: Filesystem and container vulnerability scanning
- **GitHub Security Tab**: Centralized vulnerability tracking and SARIF reporting

### Security Workflow Commands
```bash
# Run local security audit (matches CI environment)
pip-audit --requirement=requirements.txt --desc
safety check --requirement=requirements.txt
bandit -r src/ -f json
semgrep --config=p/security-audit src/
```

### Security Issue Management
- All security vulnerabilities tracked via GitHub Issues with `security` label
- Automated vulnerability assessment and prioritization
- Systematic resolution tracking and verification
- Security-focused branch protection and review requirements

## Advanced Security Implementation - Phases II & III ✅ COMPLETE

### Phase II: Advanced Security Hardening ✅

#### Enhanced Container Security
- **Workflow**: `.github/workflows/security-scan.yml` (enhanced)
- **Multi-layer Scanning**: OS vulnerabilities, library scanning, secret detection in containers
- **Configuration Analysis**: Docker security misconfigurations detection  
- **Build Integration**: Automated container security validation in CI/CD

#### Advanced Secret Management
- **Workflow**: `.github/workflows/secret-scan.yml`
- **Tools**: GitLeaks, detect-secrets, TruffleHog3 for comprehensive secret detection
- **Coverage**: Real-time detection, historical git analysis, environment variable security
- **Remediation**: Automated secret rotation recommendations and security guidance

#### Authentication & Authorization Security Auditing
- **Workflow**: `.github/workflows/auth-security.yml`
- **JWT Security**: Token validation, algorithm verification, expiration handling analysis
- **Password Security**: Hashing implementation validation, hardcoded password detection
- **Session Security**: Cookie security, session fixation protection verification
- **OAuth Security**: State parameter validation, PKCE implementation, redirect URI security

#### Security Policy Enforcement
- **Workflow**: `.github/workflows/security-policy-enforcement.yml`
- **Real-time Validation**: Code security, dependency security, container security policies
- **PR Integration**: Automated policy violation detection with blocking capabilities
- **Enforcement Levels**: Warning and blocking modes based on violation severity

### Phase III: Security Operations ✅

#### Automated Incident Response
- **Workflow**: `.github/workflows/incident-response.yml`
- **Multi-tier Response**: Critical, high, medium, low severity incident handling
- **Automated Triage**: Incident classification and appropriate response determination
- **Containment**: Immediate threat containment measures for different incident types
- **Recovery Planning**: Systematic incident recovery and validation procedures

#### Compliance Monitoring
- **Workflow**: `.github/workflows/compliance-monitoring.yml`
- **OWASP Top 10 Assessment**: Automated compliance checking for web application security
- **CIS Controls Validation**: Hardware/software inventory, data protection, access control compliance
- **NIST Cybersecurity Framework**: 5-function framework assessment (Identify, Protect, Detect, Respond, Recover)
- **Weekly Reporting**: Automated compliance status reports with improvement recommendations

### Complete Security Workflow Portfolio

#### Daily Automated Security Operations
```bash
# Complete security audit workflow execution
# All workflows run automatically on schedules:

# Daily (2 AM UTC): Comprehensive security scanning
.github/workflows/security-scan.yml

# Daily (3 AM UTC): Secret detection and management  
.github/workflows/secret-scan.yml

# Daily (5 AM UTC): Security policy enforcement
.github/workflows/security-policy-enforcement.yml

# Weekly (Sunday 4 AM UTC): Authentication security audit
.github/workflows/auth-security.yml

# Weekly (Monday 6 AM UTC): Compliance monitoring
.github/workflows/compliance-monitoring.yml

# On-demand: Incident response (triggered by security events)
.github/workflows/incident-response.yml
```

#### Security Command Reference
```bash
# Local security validation (matches CI environment)
# Phase I tools:
pip-audit --requirement=requirements.txt --desc
safety check --requirement=requirements.txt  
bandit -r src/ -f json
semgrep --config=p/security-audit src/

# Phase II tools:
gitleaks detect --source . --verbose
detect-secrets scan --all-files
semgrep --config=p/owasp-top-ten src/

# Phase III compliance:
semgrep --config=p/security-audit --config=p/secrets --config=p/owasp-top-ten src/
```

### Security Infrastructure Status ✅

**Comprehensive Coverage:**
- ✅ **8 Automated Security Workflows** covering all attack vectors
- ✅ **Zero Known Vulnerabilities** - All 17 original issues resolved
- ✅ **Multi-Framework Compliance** - OWASP, CIS, NIST alignment
- ✅ **Automated Incident Response** - Multi-tier threat response capability
- ✅ **Policy Enforcement** - Real-time security policy validation
- ✅ **Continuous Security Monitoring** - Automated assessment and reporting

**Security Posture:** MVidarr has robust, automated security operations with continuous compliance monitoring and comprehensive threat detection appropriate for a self-hosted application.

## GitHub Pages Management

### Automatic Updates
- **Trigger**: Any push to main branch affecting documentation files
- **Files Monitored**: `docs/**`, `*.md`, `_config.yml`, Jekyll pages, workflow files
- **Deployment**: Automatic Jekyll build and deploy via GitHub Actions
- **Theme**: Minima Jekyll theme with responsive design
- **URL**: https://prefect421.github.io/mvidarr

### Content Management
- **Site Structure**: Jekyll-based with navigation pages (about, installation, features, documentation, releases)  
- **Documentation Sync**: Automatically includes updated documentation from main branch
- **Version Info**: Displays current release version and roadmap information
- **Repository Links**: All documentation links reference GitHub repository content

### Maintenance Tasks
- Update version information in pages when new releases are published
- Ensure documentation links remain current with repository structure
- Monitor Pages deployment status and resolve any build failures
- Keep release information and roadmap current with project development
- keep documentation current
