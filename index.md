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

## 🚀 **NEW in v0.9.8 - Subtitle System & User Testing Fixes!**

**🎉 MAJOR RELEASE: Complete Subtitle Implementation + Critical Bug Fixes**

### Complete Subtitle System ✅
- **🎬 Universal Subtitle Support** - WebVTT, SRT, ASS, SSA, SUB formats fully supported
- **🌐 Smart Language Resolution** - Automatic YouTube non-standard language code handling
- **🎞️ Player Integration** - Subtitles working in popup modal and detail page video players

### User Testing Fixes (8/8 Critical Issues Resolved) ✅
- **✅ Authentication & Core Workflows** - Fixed logout, search, video deletion, bulk operations
- **✅ Playlist System** - Fixed page loading and creation functionality
- **✅ Service Integration** - Corrected routing for YouTube, Spotify, Last.fm, Lidarr

### 100% Flask to FastAPI Migration Complete ✅
- **⚡ 200+ API Endpoints** - Migrated across 33 major components with full async support
- **✨ Pure FastAPI** - Zero Flask API endpoints remain

## 🚀 Quick Start

### Docker Deployment (Recommended)

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

**MVidarr v{{ site.data.version.current | default: "0.9.8" }}** - Built with ❤️ for music video enthusiasts