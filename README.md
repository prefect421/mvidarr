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
- **🎨 Advanced Theme System** - 6 built-in themes with export/import functionality

## 🚀 **LATEST: v1.0.2 - Security Sweep: CORS/Proxy-Trust Hardening**

**Released**: September 3, 2026

- **🔒 CORS allowlist is now configurable** (#488) — `CORS_ALLOWED_ORIGINS` env var replaces a hardcoded personal LAN IP that didn't match any real deployment
- **🔒 Proxy trust hardened** (#488) — `TRUSTED_PROXY_HOSTS` now defaults to loopback-only instead of trusting `X-Forwarded-*` headers from any peer, closing a rate-limit-bypass / audit-log-spoofing gap for deployments not behind a reverse proxy
- **⚙️ Settings UI Preferences** (#487) — re-enable the MKV transcoding notice after a permanent "Don't show this again" dismissal, without needing DevTools
- **🔒 Security scan**: zero open Dependabot alerts, zero open code-scanning alerts, pip-audit clean across all requirements files

📜 **[View the full changelog](CHANGELOG.md)** for v1.0.2's complete notes and every earlier release.

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
   - Default login: `admin` / `mvidarr` (change immediately)
   - Complete the first-run setup wizard

**Docker Images:**
- **Latest:** `ghcr.io/prefect421/mvidarr:latest`
- **Specific version:** `ghcr.io/prefect421/mvidarr:v1.0.2`

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
- **[Self-Hosted Production Guide](docs/SELF_HOSTED_PRODUCTION.md)** - Production deployment with background jobs
- **[Dockerfile.production](Dockerfile.production)** - Multi-stage production build
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
- **Containerization**: Optimized Docker Compose with multi-stage builds, automated monitoring, and multi-stage production images

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

# Reverse proxy (required if accessing over HTTPS through nginx/Traefik/etc.)
# Without this, pages behind the proxy can fail to load with a browser
# "mixed active content" error. See docs/CONFIGURATION_GUIDE.md for a gotcha
# when the proxy shares a Docker host with MVidarr.
TRUSTED_PROXY_HOSTS=your-proxy-ip-or-hostname
CORS_ALLOWED_ORIGINS=https://your-domain.example.com
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
- **FastAPI** - Web framework
- **MariaDB** - Database engine

## 📞 Support

- **Documentation**: Check the [docs/](docs/) directory
- **Issues**: Report bugs via GitHub Issues
- **Community**: Join our discussions

---

**MVidarr v1.0.2** - Built with ❤️ for music video enthusiasts
