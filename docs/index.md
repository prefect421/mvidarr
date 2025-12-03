---
layout: home
title: Home
---

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
- **🌙 Dark/Light Themes** - Multiple theme options with automatic switching

## 🚀 **NEW in v0.10.0-beta.1 - First Beta Release with Critical Fixes!**

**🔒 BETA RELEASE: Security & Stability Improvements**

- **🐛 Chrome Fix** - Resolved STATUS_BREAKPOINT crash when seeking videos with subtitles
- **🔒 Security Updates** - Fixed 10 critical vulnerabilities + FastAPI/Starlette DoS patches
- **🐛 MariaDB Health Check** - Updated to use mariadb-admin instead of deprecated mysqladmin
- **📚 Browser Compatibility** - Comprehensive guide for Chrome, Firefox, Safari, Edge support
- **🔧 Installation Wizard** - Guided first-run setup with validation
- **🎬 Video Import** - Reliable import system with duplicate detection
- **📊 Performance Monitoring** - System health dashboard and diagnostics
- **🐳 Docker Improvements** - Better health checks and container reliability

### **v0.10.0-beta.1 Achievements:**
- ✅ **Chrome Stability**: Fixed crash during video seeking with active subtitles
- ✅ **Security**: 10 critical CVEs resolved, DoS vulnerability patches applied
- ✅ **Documentation**: New browser compatibility guide and enhanced troubleshooting
- ✅ **CI/CD**: Fixed security audit workflow with official Semgrep action
- ✅ **Beta Testing**: Active development phase, production validation in progress

## 🚀 Quick Start

### Docker Deployment (Recommended)

```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
docker-compose up -d
```

**Production Docker Image:**
```bash
# Use the latest beta release
docker pull ghcr.io/prefect421/mvidarr:v0.10.0-beta.1

# Or use the latest tag (points to current beta)
docker pull ghcr.io/prefect421/mvidarr:latest
```

**Access the application:**
- Open your browser to `http://localhost:5001`
- Default login: `admin` / `admin` (change immediately)

## 🏗️ Architecture

MVidarr is built with:

- **Backend**: FastAPI (Python 3.12+) with async operations and modular service architecture
- **Database**: MariaDB 11.4+ with automatic table initialization
- **Frontend**: Modern HTML5/CSS3/JavaScript with responsive design
- **Media Processing**: FFmpeg, yt-dlp for video downloading and processing
- **Authentication**: Secure user management with role-based access control
- **Security**: bcrypt password hashing, session management, audit logging
- **Containerization**: Optimized Docker Compose with multi-stage builds, automated monitoring, and 1.41GB production images

## 📄 License

This project is licensed under the MIT License - see the [LICENSE]({{ site.github.repository_url }}/blob/main/LICENSE) file for details.

---

**MVidarr v{{ site.data.version.current | default: "0.10.0-beta.1" }}** - Built with ❤️ for music video enthusiasts