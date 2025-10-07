# MVidarr

**A comprehensive music video management and discovery platform** that helps you organize, discover, and stream your music video collection with intelligent artist management and advanced search capabilities.

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

## 🚀 **NEW in v0.9.8 - Subtitle System & User Testing Fixes!**

**🎉 MAJOR RELEASE: Complete Subtitle Implementation + Critical Bug Fixes**

### Complete Subtitle System ✅
- **🎬 Universal Subtitle Support** - WebVTT, SRT, ASS, SSA, SUB formats fully supported
- **🌐 Smart Language Resolution** - Automatic YouTube non-standard language code handling
- **🎞️ Player Integration** - Subtitles working in popup modal and detail page video players
- **📡 FastAPI Endpoints** - Complete subtitle discovery and serving API with CORS support
- **🎯 Auto-Enable** - First subtitle track automatically loaded and displayed

### User Testing Fixes (8/8 Critical Issues Resolved) ✅
- **✅ Authentication & Core Workflows** - Fixed logout, search, video deletion, bulk operations
- **✅ Playlist System** - Fixed page loading and creation functionality
- **✅ Toast Notifications** - Restored notification system across all workflows
- **✅ Service Integration** - Corrected routing for YouTube, Spotify, Last.fm, Lidarr

### 100% Flask to FastAPI Migration Complete ✅
- **⚡ 200+ API Endpoints** - Migrated across 33 major components with full async support
- **🔧 17 FastAPI Routers** - Created with comprehensive Pydantic validation
- **🛡️ Consistent Authentication** - Session-based auth across all endpoints
- **✨ Pure FastAPI** - Zero Flask API endpoints remain

## 🆕 Previous Updates (v0.9.4-0.9.7)

- **🐳 Docker Optimization** - Reduced build time from timeout failures to consistent 8-minute builds
- **📦 Container Size Optimization** - Efficient multi-stage builds with optimized caching (1.41GB optimized size)
- **🔍 Build Monitoring** - Comprehensive Docker build monitoring and validation infrastructure
- **⚡ Build Reliability** - 100% build success rate with automated size monitoring and performance tracking
- **🛠️ Infrastructure** - Enhanced CI/CD workflows with automated Docker monitoring and health checks

## 🚀 Quick Start

### Docker Deployment (Recommended)

**Quick Start:**
```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
docker-compose up -d
```

**Production Docker Image:**
```bash
# Use the latest release
docker pull ghcr.io/prefect421/mvidarr:v0.9.8
```

**Access the application:**
- Open your browser to `http://localhost:5001`
- Default login: `admin` / `admin` (change immediately)

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

- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Complete deployment with Celery + Redis background jobs
- **[User Guide](docs/USER-GUIDE.md)** - Feature documentation and tutorials
- **[Installation Guide](docs/INSTALLATION-GUIDE.md)** - Comprehensive setup instructions
- **[Celery Background Jobs](CELERY_BACKGROUND_JOBS_IMPLEMENTATION.md)** - Background job system documentation
- **[Docker Optimization Guide](docs/DOCKER_OPTIMIZATION_GUIDE.md)** - Container build optimization and monitoring
- **[Security Implementation](docs/SECURITY_IMPLEMENTATION.md)** - Security features and configuration
- **[Final Project Status](docs/FINAL_PROJECT_STATUS.md)** - Complete feature status and changelog
- **[Authentication Features](docs/AUTHENTICATION_FEATURE_LOG.md)** - User management and security features

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

**MVidarr v0.9.8** - Built with ❤️ for music video enthusiasts
