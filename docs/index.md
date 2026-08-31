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
- **🎨 Theme System** - 6 built-in themes with automatic switching and export/import
- **🔐 2FA & OAuth** - TOTP two-factor auth, plus Authentik/Google/GitHub login
- **🔔 Notifications** - Native Discord and Apprise providers for download/artist activity

## 🚀 **LATEST: v1.0.1 - Dependency & Bugfix Sweep**

**Released**: August 28, 2026

> First production-ready release line (since v1.0.0). SemVer 1.x — see the [changelog]({{ site.github.repository_url }}/blob/main/CHANGELOG.md) for the full v1.0.0 feature set.

### This Release
- MKV transcoding notice on the video detail page is now dismissible
- Fixed production Docker image missing Node.js/pot-provider (PO tokens were silently unavailable)
- isort pinned in CI after an unpinned bump silently broke the required pipeline check
- Security scan: zero open Dependabot alerts, zero open code-scanning alerts, pip-audit clean

See the [full changelog]({{ site.github.repository_url }}/blob/main/CHANGELOG.md) for v1.0.1's complete notes and every earlier release.

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
docker pull ghcr.io/prefect421/mvidarr:v1.0.1

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

**MVidarr v{{ site.data.version.current | default: "1.0.1" }}** - Built with ❤️ for music video enthusiasts