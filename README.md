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

## 🚀 **NEW in v1.0.0 - FastAPI Migration Complete!**

**🎉 MASSIVE MILESTONE: Complete Flask-to-FastAPI Migration**

- **⚡ Complete Architecture Migration** - Migrated from Flask to FastAPI with zero functionality loss
- **🔥 Advanced FastAPI Features** - API versioning, request logging, auto-generated client libraries, dependency injection
- **📈 Performance Optimization** - Load testing framework, performance benchmarking, evidence-based validation
- **🎨 Template System Migration** - 46+ HTML templates with async context and modern JavaScript patterns
- **🔌 WebSocket Integration** - Real-time features replacing Flask-SocketIO with native FastAPI WebSockets
- **🛡️ Enterprise-Grade Testing** - 50+ validation tests ensuring zero functionality loss
- **🏗️ Modern Architecture** - Async operations, advanced caching, compression, and optimization
- **📊 Comprehensive Validation** - Migration validation framework with performance evidence

### **🎯 Migration Achievements**
- ✅ **11 Major Systems**: Template system, WebSocket integration, performance optimization, validation frameworks
- ✅ **10,472+ Lines of Code**: Complete FastAPI implementation with enterprise features
- ✅ **Zero Functionality Loss**: Comprehensive validation ensuring 100% feature parity
- ✅ **Performance Improvements**: Advanced caching, compression, and async operations
- ✅ **Modern JavaScript**: Automated modernization to async patterns and ES6+ features

## 🆕 Previous Updates (v0.9.4)

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
# Use the latest FastAPI release
docker pull ghcr.io/prefect421/mvidarr:v1.0.0
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
pip install -r requirements.txt

# Start application
python app.py
```

**Access:** `http://localhost:5000`

## 📚 Documentation

- **[User Guide](docs/USER-GUIDE.md)** - Feature documentation and tutorials
- **[Installation Guide](docs/INSTALLATION-GUIDE.md)** - Comprehensive setup instructions
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
DB_HOST=mariadb
DB_PASSWORD=secure_password
SECRET_KEY=your-secret-key
IMVDB_API_KEY=your-imvdb-key
YOUTUBE_API_KEY=your-youtube-key
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

**MVidarr v0.9.4** - Built with ❤️ for music video enthusiasts
