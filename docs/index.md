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

## 🚀 **LATEST: v0.12.5 - Security & Bug Fixes**

**Released**: March 19, 2026

> **Note**: Pre-production release following SemVer 0.x conventions. Feature-complete, undergoing testing before v1.0.0.

### Security Fixes
- **CVE-2026-32597**: PyJWT 2.8.0 → 2.12.0 — missing `crit` header validation (HIGH)
- **CVE-2026-32274**: black 24.3.0 → 26.3.1 — arbitrary cache file write (HIGH)

### Bug Fixes
- **#197**: Docker containers no longer log `git not found` errors on every health check; `git_branch` now shown correctly in the sidebar
- **#199**: Credentials set during the installation wizard are now used for login — default `admin`/`mvidarr` no longer overrides the wizard setup
- **#200**: Thumbnails are now downloaded immediately when a video download completes; YouTube URL fallback chain added (`maxresdefault` → `hqdefault` → `mqdefault`)

## 🚀 Quick Start

### Docker Deployment (Recommended)

```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
cp .env.example .env  # edit with your settings
docker-compose up -d
```

**Production Docker Image:**
```bash
# Latest release
docker pull ghcr.io/prefect421/mvidarr:v0.12.5

# Or always latest
docker pull ghcr.io/prefect421/mvidarr:latest
```

**Access the application:**
- Open your browser to `http://localhost:5000`
- Default login: `admin` / `mvidarr` (change immediately)
- Complete the first-run setup wizard

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

**MVidarr v{{ site.data.version.current | default: "0.12.5" }}** - Built with ❤️ for music video enthusiasts