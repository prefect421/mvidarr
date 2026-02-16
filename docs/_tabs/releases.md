---
# the default layout is 'page'
icon: fas fa-rocket
order: 5
---

# Releases

Track MVidarr's development progress through our release history and upcoming milestones.

## 🚀 Current Release: v0.12.3

**Released**: February 16, 2026
**Focus**: Playlist Sync & Logging

### Key Fixes
- **🎵 VEVO Name Cleanup**: YouTube channel suffixes (VEVO, Official, Music, Records, etc.) automatically stripped during playlist sync to prevent duplicate artists
- **📋 Celery Task Logging**: Scheduled task logs were silently dropped because worker process lacked logger configuration. Fixed via `after_setup_logger` signal
- **🔐 Authentication**: 36 API endpoints secured with session-based auth
- **🛡️ Security**: 49 vulnerabilities fixed across v0.12.0-v0.12.3 (bcrypt passwords, SSRF protection, secure cookies)

### Download v0.12.3
- **[GitHub Release](https://github.com/prefect421/mvidarr/releases)** - Source code and installation packages
- **[Docker Image](https://ghcr.io/prefect421/mvidarr:latest)** - Production-ready container
- **[Documentation](https://prefect421.github.io/mvidarr)** - Complete user and developer guides

## 📋 Recent Releases

### v0.12.2 - Authentication & Stability
**Released**: February 14, 2026

- Authentication added to 36 unprotected API endpoints
- Global 401 interceptor redirects unauthenticated users
- Fixed discovery setting videos to WANTED regardless of artist auto_download
- Fixed artist deletion 500 error from orphaned foreign key references
- YouTube monitored playlists auto-sync every 6 hours

### v0.12.1 - Security Hardening Stabilization
**Released**: February 12, 2026

- Fixed WAF false positives blocking URLs, cookies, Range headers
- Fixed video streaming (Range header no longer blocked)
- Fixed Flask-to-FastAPI session bridge for consistent auth
- Rate limiting set to 300/min with static files exempt

### v0.12.0 - Security Hardening Sprint
**Released**: February 11, 2026

- Consolidated auth system (SimpleAuth + SessionStore)
- Removed backdoor endpoints (/test-login, credential reset)
- Upgraded passwords from SHA-256 to bcrypt with lazy migration
- 49 vulnerabilities fixed (8 critical, 12 high, 16 medium, 13 low)

### v0.11.9 - Security Updates & Video Quality
**Released**: February 5, 2026

- 11 CVEs fixed via dependency updates
- Video downloads now respect user quality settings
- YouTube discovery API key caching bug fixed

### v0.11.8 - Thumbnail System Overhaul
**Released**: February 4, 2026

- Bulk scan success improved from 0% to 87% (231/264 artists)
- Google Images prioritized for artist thumbnails
- Added REDIS_HOST and REDIS_PORT environment variables

## 🗓️ Earlier Release History

### v0.11.7 - Video Filtering & Discovery (February 2, 2026)
- Per-artist video type filtering for autodownload
- Extended YouTube discovery (live, concerts, acoustic)

### v0.10.1 - Scheduler V2 (December 22, 2025)
- Complete Celery-based distributed task scheduling
- 23 REST API endpoints for scheduler management
- Per-artist discovery scheduling

### v0.10.0-beta.1 - First Beta (December 1, 2025)
- Security fixes, installation wizard, video import system

### v0.9.x (June-August 2025)
- Core architecture, Docker support, theme system, security audit

## 🔮 Future: v1.0.0 - Stable Production Release

### Goals
- **🎯 Production Ready**: Stability and performance validation
- **📚 Complete Documentation**: Comprehensive guides and API documentation
- **🔒 Security Certification**: Professional security audit
- **🤝 Community Features**: Plugin system and community contributions

## 📊 Release Statistics

### Development Metrics
- **Total Releases**: 15+ versions from v0.9.0 to v0.12.3
- **Features Implemented**: 35+ comprehensive capabilities
- **Security Fixes**: 60+ vulnerabilities resolved across all releases
- **Docker Architecture**: Simplified 3-container deployment

## 🔗 Release Resources

### Download Options
- **[GitHub Releases](https://github.com/prefect421/mvidarr/releases)** - All versions with release notes
- **[Docker Hub](https://ghcr.io/prefect421/mvidarr)** - Container images for all versions
- **[Source Code](https://github.com/prefect421/mvidarr)** - Latest development code

### Documentation
- **[Installation Guide]({% link _tabs/installation.md %})** - Setup instructions for all versions
- **[Migration Guides](https://github.com/prefect421/mvidarr/tree/main/docs/migrations)** - Upgrade procedures
- **[Breaking Changes](https://github.com/prefect421/mvidarr/blob/main/BREAKING_CHANGES.md)** - Compatibility information

### Support
- **[GitHub Issues](https://github.com/prefect421/mvidarr/issues)** - Bug reports and feature requests
- **[Discussions](https://github.com/prefect421/mvidarr/discussions)** - Community Q&A and feedback
- **[Project Board](https://github.com/users/prefect421/projects/1)** - Development roadmap and progress

---

## 📅 Release Schedule

MVidarr follows a regular release schedule:

- **Major Releases** (x.0.0): Quarterly, with significant new features
- **Minor Releases** (x.y.0): Monthly, with feature additions and improvements  
- **Patch Releases** (x.y.z): As needed, for bug fixes and security updates
- **Beta Releases**: Available for testing new features before official release

### Versioning Policy
- **Semantic Versioning**: Following semver.org standards
- **Backward Compatibility**: Maintained within minor version increments
- **Deprecation Notice**: 2 release cycles for deprecated features
- **LTS Support**: Long-term support for select stable versions

---

*Stay updated with the latest releases by watching our [GitHub repository](https://github.com/prefect421/mvidarr) and subscribing to release notifications.*