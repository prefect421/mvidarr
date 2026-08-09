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

## 🚀 **LATEST: v0.12.24 - Security Sweep (aiohttp CVE fix, MKV warning fix, thumbnail hardening)**

**Released**: August 9, 2026

> **Note**: This is a pre-production release following SemVer 0.x conventions. The software is feature-complete but undergoing testing and validation before the official v1.0.0 production release.

### Security & Fixes
- **🔒 HIGH — CVE-2026-69244 / GHSA-cq5v-8q36-5273**: aiohttp 3.14.1 → 3.14.3 — out-of-bounds heap read in the C HTTP response parser error path
- **🔒 MEDIUM — CVE-2026-69243 / GHSA-mfx4-hv73-q22v**: aiohttp 3.14.1 → 3.14.3 — HTTP request smuggling via WebSocket upgrade
- **🔒 MEDIUM — CVE-2026-59881 / GHSA-mq44-7p77-q5h7**: aiohttp 3.14.1 → 3.14.3 — WebSocket client decompressed frames without a negotiated permessage-deflate extension
- **🐛 #307**: Removed a premature 3-second false-positive "format not supported" warning on MKV/AVI playback that raced against real-time transcoding and destroyed the live video element; the existing 30-second `loadTimeout` already handles genuine load failures
- **🐛 #306** (partial/defensive): Thumbnail stale-path cleanup no longer treats a failed filesystem check as proof a thumbnail was deleted — only a confirmed-missing file now clears the database reference
- Verified via rebuilt local Docker: full pytest suite passed (58 passed, 1 skipped); prod (192.168.1.68:5050) rebuilt and confirmed on v0.12.24
- Closed/superseded Dependabot PR #308

## 🎯 Previous Releases

### v0.12.23 - Dependency Sweep (pytest, tqdm, sphinx, sphinx-rtd-theme, redis, psutil) (August 2, 2026)
- **pytest** 9.0.3 → 9.1.1 (dev), **tqdm** 4.68.3 → 4.70.0
- **sphinx** 7.2.6 → 9.1.0, **sphinx-rtd-theme** 1.3.0 → 3.1.0 (dev-only)
- **redis** 8.0.1 → 8.1.0, **psutil** 5.9.6 → 7.2.2 (2 major versions)

### v0.12.22 - Dependency Sweep (celery, redis, sentry-sdk, imagehash, actions/setup-python, actions/labeler, ruby/setup-ruby) (July 25, 2026)
- **celery** 5.3.4 → 5.6.3, **redis** 5.0.1 → 8.0.1 (3 major versions) — both verified live: celery worker/beat ping successfully, job-progress/cache round-trips through `redis_manager` work correctly
- **sentry-sdk** 2.63.0 → 2.66.1, **imagehash** 4.3.1 → 4.3.2 (dev-only)
- **CI**: actions/setup-python v6 → v7, actions/labeler v6 → v7, ruby/setup-ruby 1.319.0 → 1.321.0

### v0.12.21 - Dependabot Sweep (lxml, marshmallow, flake8, aiomysql, pymysql, ruby/setup-ruby) (July 19, 2026)
- **🔒 lxml** 6.1.0 → 6.1.1 — fixes GHSA-4jhm-jv67-739f (`xlink:href` missing from known link attrs, URL bypass in embedded SVG/MathML) and bundles libxslt fixes for CVE-2025-7424 / CVE-2025-11731
- **🔒 aiomysql** >=0.2.0 → >=0.3.2 — fixes GHSA-r397-ff8c-wv2g (local_infile load bypass)
- **pymysql** 1.1.1 → 1.2.0, **marshmallow** 3.26.2 → 4.3.0, **flake8** 6.1.0 → 7.3.0 (dev-only)

### v0.12.20 - Fix Stuck Download Queue (July 16, 2026)
- **🐛 "Stop Download" 400 error**: queue ids from videos are now unambiguously tagged (`video_123`) and routed to the right table
- **🐛 "Force Clear All"**: now also resets orphaned stuck videos with no backing `Download` row
- **🐛 Misleading "no stuck downloads found" message**: backend now returns the real cleared count

📜 **[View the full changelog](CHANGELOG.md)** for all earlier releases (v0.12.19 back through v0.9.8 and beyond).

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
- **Specific version:** `ghcr.io/prefect421/mvidarr:v0.12.23`

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

**MVidarr v0.12.23** - Built with ❤️ for music video enthusiasts
