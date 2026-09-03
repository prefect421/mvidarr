---
layout: page
title: About
permalink: /about/
---

# About MVidarr

MVidarr is a music video collection and management system built for the home self-hoster who wants to organize, discover, and stream their own music video library without depending on a third-party service.

## Key Capabilities

### 🎯 Artist Management
- Multi-criteria search and filtering
- Bulk operations for efficient management
- Automated metadata enrichment (thumbnails, genres, biography)
- Per-artist video-type filtering and monitoring controls

### 🔍 Video Discovery & Download
- Dual-source discovery (IMVDb + YouTube)
- yt-dlp-based downloading with quality preferences and automatic retry
- Duplicate detection at the database level
- Scheduler V2 for automated, prioritized discovery/download runs

### 📺 Streaming Experience
- Built-in HTML5 player with real-time MKV transcoding (FFmpeg)
- Full subtitle support (WebVTT, SRT, ASS, SSA, SUB) with smart language resolution
- MvTV continuous-playback mode
- Multiple built-in themes

### 🛡️ Security
- Real, enforced role-based access control (Admin, Manager, User, ReadOnly)
- OAuth login (Authentik, Google, GitHub) alongside local accounts
- Two-factor authentication (TOTP + backup codes)
- bcrypt password hashing, session-based auth on every API endpoint
- Native Discord and Apprise notifications for download/artist activity

## Technology Stack

- **Backend**: FastAPI (Python 3.12+), async throughout
- **Database**: MariaDB 11.4+ / MySQL 8.0+ via SQLAlchemy
- **Background Jobs**: Celery + Redis
- **Frontend**: HTML5/CSS3/JavaScript, server-rendered Jinja2 templates
- **Media Processing**: FFmpeg, yt-dlp
- **Containerization**: Docker (3-container: app+Celery, MariaDB, Redis)

## Development Philosophy

- **Security first** — every endpoint is authenticated; RBAC is enforced, not decorative
- **Self-hoster scale** — built for a personal or small home-server library, not an enterprise deployment
- **Maintainability** — clean architecture, current documentation, active dependency hygiene
- **Extensibility** — service-integration points for Spotify, Last.fm, Plex, Lidarr, and more

## Project Status

**Current Version**: v1.0.1 (Released August 28, 2026) — first production-ready release line
**Development Branch**: `dev`, targeting v1.0.2

See the [full changelog](https://github.com/prefect421/mvidarr/blob/main/CHANGELOG.md) for release-by-release history, and the [documentation index](documentation/) for guides.

## Contributing

We welcome contributions — feature development, documentation improvements, bug reports, security reviews, or performance work. Check out our [Contributing Guide]({{ site.github.repository_url }}/blob/main/CONTRIBUTING.md) to get started.

## Support

- **Documentation**: [docs directory]({{ site.github.repository_url }}/tree/main/docs)
- **Issues**: [GitHub Issues]({{ site.github.repository_url }}/issues)
- **Discussions**: [GitHub Discussions]({{ site.github.repository_url }}/discussions)

---

MVidarr is developed with ❤️ by music video enthusiasts, for music video enthusiasts.
