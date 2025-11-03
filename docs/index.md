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

## 🚀 **NEW in v0.9.9 - Production-Ready Code Cleanup & Security Hardening!**

**🎉 MAJOR MILESTONE: Production-Ready with Enterprise-Grade Code Quality**

- **🎥 Real-Time MKV Transcoding** - Smart FFmpeg codec detection with adaptive remux/transcode
- **♻️ Massive Code Refactoring** - 10 large files refactored into 58 modular files (71.4% size reduction)
- **🧹 Complete Code Cleanup** - 607 unused imports removed (100% cleanup across 264 files)
- **🔒 Security Hardening** - 30 medium-severity issues fixed (69.8% improvement, zero high-severity)
- **📚 Complete Documentation** - Comprehensive API docs, scripts guides, and release notes
- **🧪 Rigorous Testing** - 222/230 E2E tests passing (96.5%), 100% critical smoke tests
- **📦 Script Organization** - 26 obsolete scripts archived with comprehensive documentation

### **v0.9.9 Achievements:**
- ✅ **MKV Video Support**: Real-time transcoding with intelligent codec detection
- ✅ **Code Architecture**: 15,133 lines → 58 modular files with backward compatibility
- ✅ **Security**: SQL injection protection, HMAC verification, XXE prevention, HTTP timeouts
- ✅ **Documentation**: API_DOCUMENTATION.md (17 routers, 200+ endpoints), scripts/README.md
- ✅ **Production Ready**: Zero blocking issues, comprehensive testing, complete cleanup

## 🚀 Quick Start

### Docker Deployment (Recommended)

```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
docker-compose up -d
```

**Production Docker Image:**
```bash
# Use the latest production-ready release
docker pull ghcr.io/prefect421/mvidarr:v0.9.9
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

**MVidarr v{{ site.data.version.current | default: "0.9.9" }}** - Built with ❤️ for music video enthusiasts