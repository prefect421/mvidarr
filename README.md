# MVidarr

**A comprehensive music video management and discovery platform** that helps you organize, discover, and stream your music video collection with intelligent artist management and advanced search capabilities.

![Artist Screen](mvidarr-screen.png)

## ✨ Key Features

- **🎯 Advanced Artist Management** - Multi-criteria search and bulk operations
- **🔍 Comprehensive Video Discovery** - Dual-source integration (IMVDb + YouTube)  
- **🖼️ Advanced Thumbnail Management** - Multi-source search and cropping
- **📁 Intelligent Organization** - Automatic folder creation and cleanup
- **🔎 Advanced Search System** - Real-time suggestions and filtering
- **⚡ Bulk Operations** - Multi-select editing and batch processing
- **📺 Video Streaming** - Built-in player with transcoding support
- **💚 System Health Monitoring** - Comprehensive diagnostics
- **⚙️ Database-Driven Settings** - Complete configuration management
- **📥 Download Management** - Queue visualization and progress tracking
- **🎨 Modern UI** - Left sidebar navigation with theme system
- **📺 MvTV Continuous Player** - Cinematic mode for uninterrupted viewing
- **🎭 Genre Management** - Automatic genre tagging and filtering
- **🔐 User Authentication** - Role-based access control with security features
- **🎨 Advanced Theme System** - 7 built-in themes with export/import functionality

## 🚀 **LATEST: v0.12.19 - YouTube Max-Quality Downloads & Dead-URL Recovery**

**Released**: July 16, 2026

> **Note**: This is a pre-production release following SemVer 0.x conventions. The software is feature-complete but undergoing testing and validation before the official v1.0.0 production release.

### Community Contribution 🎉
- Core fix contributed by **@Ktell123** in [#282](https://github.com/prefect421/mvidarr/pull/282) — thank you!

### Fixes
- **🐛 Anti-detection setting ignored**: `enable_aggressive_anti_detection` was read with `settings.get()`, which returns the string `'False'` — truthy in Python — forcing AGGRESSIVE anti-detection (and the Android YouTube client) on every download and capping quality at ~360p. Now uses `settings.get_bool()`.
- **🎬 Player client priority**: prefer `web,mweb,tv` YouTube clients over android-first clients that hide adaptive HD/4K formats.
- **📈 Format selection**: yt-dlp Node JS runtime + resolution-first format sort (`-S res,br`), improved `best` format string, and an automatic MODERATE retry when an escalated (AGGRESSIVE/STEALTH) download still lands at ≤360p.
- **🔗 Dead YouTube URL recovery**: when a stored YouTube URL is private, unavailable, or terminated, MVidarr now searches for an official alternate upload, persists the new URL, and retries the download once.
- **🐛 Retry file-preservation bug** (found in code review): the low-res retry logic deleted the original download's file before confirming the retry actually succeeded or was better, so a failed or worse retry could report success while pointing at a deleted file. Fixed, with 16 new unit tests covering the retry paths.

> **Upgrade Note**: No database migrations required. `docker compose pull && docker compose up -d`

## 🎯 Previous Releases

### v0.12.18 - Dependency Sweep (fastapi, Pillow, opencv, click, tqdm) (July 5, 2026)
- All clear — zero CVEs, zero Dependabot security alerts, zero code scanning alerts
- **fastapi** 0.138.1 → 0.139.0, **Pillow** 12.2.0 → 12.3.0, **opencv-python-headless** >=4.13.0.92 → >=5.0.0.93
- **click** 8.1.7 → 8.4.2, **tqdm** 4.66.3 → 4.68.3, **ruby/setup-ruby** 1.314.0 → 1.315.0

### v0.12.17 - Security Sweep (pydantic-settings CVE + dependency updates) (June 27, 2026)
- **🔒 GHSA-4xgf-cpjx-pc3j** (MEDIUM): pydantic-settings 2.14.1 → 2.14.2 — `NestedSecretsSettingsSource` symlink traversal
- **fastapi** 0.136.3 → 0.138.1, **alembic** 1.18.4 → 1.18.5, **httpx** 0.25.2 → 0.28.1, **python-slugify** 8.0.1 → 8.0.4
- **mypy** 1.7.1 → 2.1.0 (dev), **actions/cache** v5 → v6, **ruby/setup-ruby** 1.313.0 → 1.314.0

### v0.12.16 - Security Sweep (python-multipart, bleach) (June 19, 2026)
- **🔒 CVE-2026-53539** (HIGH, CVSS 7.5): python-multipart 0.0.27 → 0.0.32 — quadratic CPU DoS
- **🔒 Dependabot #20** (MEDIUM, CVSS 6.1): bleach 6.1.0 → 6.4.0 — `formaction` URI bypass
- **🔒 CVE-2026-53538/53537/45152** (LOW): python-multipart — parameter smuggling + buffer fixes
- **sentry-sdk** 2.8.0 → 2.63.0, **starlette** >=1.3.1, **actions/checkout** v6 → v7

### v0.12.15 - Security Sweep (aiohttp CVEs) (June 6, 2026)
- **🔒 CVE-2026-34993**: aiohttp 3.13.4 → 3.14.0 — `CookieJar.load()` deserialization → arbitrary code execution (MEDIUM)
- **🔒 CVE-2026-47265**: aiohttp 3.13.4 → 3.14.0 — per-request cookies leaked via cross-origin redirect (MEDIUM)
- **bcrypt** 4.1.2 → 5.0.0, **requests** 2.33.0 → 2.34.2, **alembic** 1.13.1 → 1.18.4, **zeroconf** 0.149.7 → 0.149.16
- GitHub Actions Node 24 CI updates

### v0.12.14 - Security Sweep (PyJWT CVEs) (June 2, 2026)
- **🔒 PYSEC-2026-179/178/177/176/175**: PyJWT 2.12.0 → 2.13.0 — HMAC confusion, JWS DoS, JWKS unauthenticated DoS, algorithm bypass, SSRF
- 3 stale Trivy code scanning alerts for zeroconf auto-closed after fresh scan

### v0.12.13 - Video Streaming Fix (June 1, 2026)
- **Fixed video streaming 404 errors** — Two bugs in the streaming endpoint caused videos to return HTTP 404 when `local_path` in the database is stored as a relative path
- `find_relocated_video()` incorrectly used `getattr()` returning `None`; path resolution now tries both CWD-relative and `BASE_DIR`-anchored paths
- Both `stream` and `stream-transcode` endpoints patched

### v0.12.12 - Dependabot Sweep + Python 3.14 (June 1, 2026)
- **Python 3.12-slim → 3.14-slim** — base image upgraded; netifaces, mysqlclient, moviepy verified clean
- aiofiles 23.2.1 → 25.1.0, starlette ≥1.2.1, python-dateutil 2.9.0.post0, werkzeug 3.1.8, PyYAML 6.0.3
- GitHub Actions upgraded to Node.js 24: checkout@v6, login-action@v4, build-push-action@v7, github-script@v9, deploy-pages@v5

### v0.12.11 - Security Sweep (June 1, 2026)
- **🔒 CVE-2026-47180, CVE-2026-47183, CVE-2026-47184**: zeroconf 0.132.2 → 0.149.7 — LAN-local DoS/OOM via mDNS flood
- **🔒 PYSEC-2026-161**: starlette ≥1.0.1 — Host header injection / authentication bypass
- fastapi 0.123.0 → 0.136.3, pydantic 2.5.0 → 2.13.4, pydantic-settings 2.1.0 → 2.14.1
- GitHub Actions: setup-python@v6, upload-artifact@v7, codecov@v6 — Node.js 24 migration

### v0.12.10 - Security Sweep (May 16, 2026)
- **🔒 CVE-2026-44432** (HIGH, CVSS 7.5): urllib3 2.6.3 → 2.7.0 — decompression-bomb bypass
- **🔒 CVE-2026-44431** (HIGH, CVSS 5.3): urllib3 2.6.3 → 2.7.0 — sensitive header forwarding
- pytest-asyncio 0.23.8 → 1.3.0, pytest-playwright 0.4.3 → 0.7.2 for pytest 9.x compatibility

### v0.12.9 - YouTube Quota & Discovery Improvements (May 11, 2026)
- Reduced YouTube searches from 4 to 2 per artist for better API quota efficiency
- Quota enforcement added to YouTubeQuotaTracker with file locking to prevent overruns
- Per-artist `last_discovery` now committed after each artist completes, surviving interrupted runs

### v0.12.8 - Security Patches (3 CVEs) (May 7, 2026)
- **🔒 CVE-2026-41066** (HIGH): lxml 4.9.3 → 6.1.0 — XXE local file read
- **🔒 CVE-2026-42561** (MEDIUM): python-multipart 0.0.26 → 0.0.27 — DoS via oversized headers
- **🔒 CVE-2026-28684** (MEDIUM): python-dotenv 1.0.0 → 1.2.2 — symlink arbitrary file overwrite
- Fixed broken `-r requirements-prod.txt` include in `requirements-dev.txt`
- Import ordering corrected across `src/` for CI compliance

### v0.12.7 - Dependency Cleanup & Test Infrastructure (April 16, 2026)
- Removed sphinx from production runtime (dev-only)
- pytest-cov 4.1.0 → 7.1.0 for pytest 9.x compatibility
- 5 CVEs resolved (python-multipart, Pillow, pytest)

### v0.12.6 - Security Dependency Updates (April 9, 2026)
- CVE-2026-25645: requests 2.32.4 → 2.33.0 — predictable temporary file creation (MEDIUM)
- CVE-2026-22815/34513-34520: aiohttp 3.13.3 → 3.13.4 — multiple DoS and injection fixes
- 12 CVEs total resolved


### v0.12.5 - Security & Bug Fixes (March 19, 2026)
- CVE-2026-32597: PyJWT 2.8.0 → 2.12.0 (missing `crit` header validation)
- CVE-2026-32274: black 24.3.0 → 26.3.1 (arbitrary cache file write)
- Fixed Docker `git not found` error spam on health checks
- Fixed installation wizard credentials being overridden by defaults (#199)
- Fixed thumbnail download on video completion (#200)

### v0.12.4 - Scheduler & Auto-Download Fixes (February 26, 2026)
- Auto-download scheduling priority fix, auto_download_max_videos raised from 10 to 50
- Multiple security CVEs patched (Flask, werkzeug, Pillow, PyJWT)
- Fixed allowed_video_types and 20+ artist settings not saving correctly

### v0.12.3 - Playlist Sync & Logging (February 16, 2026)
- VEVO/Official channel name cleanup during playlist sync
- Celery worker logging fix, authentication added to 36 API endpoints

### v0.12.2 - Authentication & Stability (February 14, 2026)
- **🔐 API Security**: Added authentication to 36 unprotected API endpoints across 6 files
- **🔐 Global 401 Interceptor**: Unauthenticated users redirected to login instead of seeing error counts
- **🎬 Discovery Fix**: Videos no longer set to WANTED when artist `auto_download` is disabled
- **🗑️ Artist Deletion**: Fixed 500 error from orphaned playlist/download foreign key references
- **📺 Playlist Auto-Sync**: YouTube monitored playlists now auto-sync every 6 hours via Celery scheduled task
- **🧹 Cleanup**: Removed obsolete po-token-provider process causing FATAL crashes on startup

### v0.12.1 - Security Hardening Stabilization (February 12, 2026)
- **🛡️ WAF Fixes**: Resolved false positives blocking URLs, cookies, and Range headers
- **📺 Video Streaming**: Range header no longer blocked by security middleware
- **🔐 Auth Bridge**: Fixed Flask-to-FastAPI session bridge for consistent authentication
- **📺 Playlist Sync**: Fixed not detecting new videos in YouTube playlists
- **⚡ Rate Limiting**: Set to 300/min with static files exempt
- **🔧 CI/CD**: 28 files reformatted with black 24.3.0

### v0.12.0 - Security Hardening Sprint (February 11, 2026)
- **🔐 Auth Consolidation**: Unified SimpleAuth + SessionStore authentication system
- **🚫 Backdoors Removed**: Eliminated `/test-login` and credential reset endpoints
- **🔒 Bcrypt Passwords**: Upgraded from SHA-256 to bcrypt with lazy migration on login
- **🛡️ SSRF Protection**: Safe tar extraction, upload sanitization, restricted proxy hosts
- **🔑 Redis Auth**: Redis authentication enabled, secure cookies enforced
- **🐛 49 Vulnerabilities Fixed**: 8 critical, 12 high, 16 medium, 13 low

### v0.11.9 - Security Updates & Video Quality (February 5, 2026)
- 11 CVEs fixed via dependency updates
- Video downloads now respect user quality settings (was defaulting to 360p)
- YouTube discovery API key caching bug fixed

### v0.11.8 - Thumbnail System Overhaul (February 4, 2026)
- Complete fix of artist thumbnail system (0% → 87% bulk scan success)
- Manual thumbnail setting fixed, Google Images priority, Wikimedia compatibility
- Redis configuration environment variables (REDIS_HOST, REDIS_PORT)

### v0.11.7 - Video Filtering, Extended Discovery & Blacklist Fix (February 2, 2026)
- Per-artist video type filtering for autodownload (Issue #191)
- Extended YouTube discovery (live performances, concerts, acoustic versions)
- Increased max_videos_per_discovery from 5 to 50
- Fixed blacklist not saving info (Issue #190)

### v0.11.6 - Blacklist POST Hotfix (January 2, 2026)
- Fixed non-existent fields from blacklist POST endpoint
- Blacklist API/model mismatch fixes
- Pagination fixes

### v0.11.0 - Scheduler V2 Release
- Database-driven scheduling with web UI management
- Code cleanup & optimization (71.4% size reduction)
- Security hardening (30 issues fixed)
- Docker architecture simplification (3-container deployment)

### v0.9.8 - Subtitle System & User Testing Fixes
- Complete subtitle implementation (WebVTT, SRT, ASS, SSA, SUB)
- Smart YouTube language resolution
- User testing fixes (8/8 critical issues resolved)
- 100% Flask to FastAPI migration complete

## 🚀 Quick Start

### Docker Deployment (Recommended)

**Simple 3-Container Architecture:**
- **mvidarr** - FastAPI application + Celery worker (managed by supervisord)
- **mariadb** - Database
- **redis** - Cache and job queue

**Installation Steps:**

1. **Clone the repository:**
   ```bash
   git clone https://github.com/prefect421/mvidarr.git
   cd mvidarr
   ```

2. **Create your environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Edit .env with your configuration:**
   ```bash
   nano .env  # or use your preferred editor
   ```

   **Required settings:**
   - `DB_PASSWORD` - Set a secure database password
   - `MYSQL_ROOT_PASSWORD` - Set a secure root password
   - `SECRET_KEY` - Generate with: `openssl rand -hex 32`
   - `MUSIC_VIDEOS_PATH` - Path to your music video collection

4. **Start MVidarr:**
   ```bash
   docker-compose up -d
   ```

5. **Access the application:**
   - Open your browser to `http://localhost:5000`
   - Default login: `admin` / `admin` (change immediately)
   - Complete the first-run setup wizard

**Docker Images:**
- **Latest:** `ghcr.io/prefect421/mvidarr:latest`
- **Specific version:** `ghcr.io/prefect421/mvidarr:v0.12.19`

**What's Running:**
- All background jobs (Celery) run automatically inside the main container
- Supervisord manages both FastAPI and Celery processes
- Simple, efficient, and optimized for home users

### Manual Installation

**Prerequisites:**
- Python 3.12+
- MariaDB 11.4+ (recommended)
- FFmpeg (for video processing)

**Installation:**
```bash
# Clone and setup
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start FastAPI application
python fastapi_app.py
```

**Production Service:**
```bash
# Install as systemd service (recommended)
sudo cp mvidarr.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mvidarr.service
sudo systemctl start mvidarr.service

# Check service status
sudo systemctl status mvidarr.service
```

**Access:** `http://localhost:5000`

## 📚 Documentation

### Getting Started
- **[Installation Guide](docs/installation.md)** - Docker, Manual, and Unraid installation
- **[Unraid Installation](docs/UNRAID_INSTALLATION.md)** - Complete Unraid setup guide
- **[User Guide](docs/USER-GUIDE.md)** - Feature documentation and tutorials
- **[Configuration Guide](docs/CONFIGURATION_GUIDE.md)** - Settings and customization
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

### Advanced Topics
- **[API Documentation](docs/API_DOCUMENTATION.md)** - REST API reference and OpenAPI docs
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Production deployment with background jobs
- **[Docker Optimization](docs/DOCKER_OPTIMIZATION_GUIDE.md)** - Container optimization
- **[Security Implementation](docs/SECURITY_IMPLEMENTATION.md)** - Security features
- **[Architecture](docs/ARCHITECTURE.md)** - System architecture and design

## 🏗️ Architecture

MVidarr is built with modern, high-performance architecture:

- **Backend**: **FastAPI** (Python 3.12+) with async operations and advanced features
- **API Layer**: Comprehensive FastAPI with versioning, request logging, and auto-generated clients
- **Template System**: Async Jinja2 templates with performance optimization and caching
- **WebSocket Support**: Native FastAPI WebSockets for real-time features
- **Background Jobs**: **Celery + Redis** for reliable metadata enrichment and processing
- **Database**: MariaDB 11.4+ with async connection pooling and optimization
- **Frontend**: Modern HTML5/CSS3/JavaScript with ES6+ async patterns
- **Performance**: Multi-layer caching (Memory + Redis), compression, and optimization
- **Testing**: Enterprise-grade validation and load testing frameworks
- **Media Processing**: FFmpeg, yt-dlp for video downloading and processing
- **Authentication**: Secure user management with role-based access control
- **Security**: bcrypt password hashing, session management, audit logging
- **Containerization**: Optimized Docker Compose with multi-stage builds, automated monitoring, and 1.41GB production images

## 🔧 Configuration

Configuration is managed through:
- Database settings (preferred for production)
- Environment variables
- Docker Compose environment files

Key environment variables:
```bash
# Database
DB_HOST=mariadb
DB_PASSWORD=secure_password
SECRET_KEY=your-secret-key

# External APIs
IMVDB_API_KEY=your-imvdb-key
YOUTUBE_API_KEY=your-youtube-key

# Background Jobs (New!)
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
BACKGROUND_JOBS_ENABLED=true
```

## 🛡️ Security

MVidarr includes comprehensive security features:

- **Multi-user authentication** with role-based access (Admin, Manager, User, ReadOnly)
- **Secure password hashing** with bcrypt
- **Session management** with secure tokens and expiration
- **Account lockout** protection against brute force attacks
- **Password reset** functionality with secure tokens
- **Audit logging** for user actions and system events
- **SQL injection prevention** with parameterized queries and ORM
- **Docker security** with non-root containers and isolated networking

## 🎯 Use Cases

- **Personal Music Video Collections** - Organize and stream your collection
- **Music Discovery** - Find new videos through integrated search
- **Media Center Integration** - Works with Plex and other media servers
- **Home Entertainment** - MvTV mode for continuous viewing
- **Music Research** - Advanced search and filtering capabilities

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

1. Fork the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/bin/activate` (Linux/macOS) or `venv\Scripts\activate` (Windows)
4. Install dev dependencies: `pip install -r requirements.txt`
5. Run tests: `pytest`

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **yt-dlp** - Video download and processing
- **IMVDb** - Music video metadata database
- **YouTube API** - Video discovery and streaming
- **Flask** - Web framework
- **MariaDB** - Database engine

## 📞 Support

- **Documentation**: Check the [docs/](docs/) directory
- **Issues**: Report bugs via GitHub Issues
- **Community**: Join our discussions

---

**MVidarr v0.12.19** - Built with ❤️ for music video enthusiasts
