---
layout: page
title: Documentation
permalink: /documentation/
---

# Documentation

Comprehensive documentation and guides for MVidarr users, administrators, and developers.

## 📖 User Documentation

### Getting Started
- **[Installation Guide](installation/)** - Docker, manual, and Unraid installation
- **[Unraid Installation](https://github.com/prefect421/mvidarr/blob/main/docs/UNRAID_INSTALLATION.md)** - Complete Unraid setup guide
- **[User Guide](https://github.com/prefect421/mvidarr/blob/main/docs/USER-GUIDE.md)** - Feature documentation and tutorials
- **[Configuration Guide](https://github.com/prefect421/mvidarr/blob/main/docs/CONFIGURATION_GUIDE.md)** - Settings and customization
- **[User Workflows](https://github.com/prefect421/mvidarr/blob/main/docs/USER_WORKFLOWS.md)** - Common tasks and procedures

### Core Features
- **[Video Organization](https://github.com/prefect421/mvidarr/blob/main/docs/VIDEO_ORGANIZATION.md)** - Organizing and managing your video library
- **[Automatic Downloads](https://github.com/prefect421/mvidarr/blob/main/docs/AUTOMATIC_DOWNLOADS.md)** - Download queue and automation
- **[Automatic Video Discovery](https://github.com/prefect421/mvidarr/blob/main/docs/AUTOMATIC_VIDEO_DISCOVERY.md)** - How discovery finds new videos
- **[Scheduler V2](https://github.com/prefect421/mvidarr/blob/main/docs/SCHEDULER_V2.md)** - Automated scheduling architecture and configuration
- **[Browser Compatibility](https://github.com/prefect421/mvidarr/blob/main/docs/BROWSER_COMPATIBILITY.md)** - Browser-specific notes (subtitle seeking, etc.)

### Troubleshooting
- **[Troubleshooting Guide](https://github.com/prefect421/mvidarr/blob/main/docs/TROUBLESHOOTING.md)** - Common issues and solutions
- **[Docker Troubleshooting](https://github.com/prefect421/mvidarr/blob/main/docs/TROUBLESHOOTING_DOCKER.md)** - Container-specific issues
- **[Initial Video Load Guide](https://github.com/prefect421/mvidarr/blob/main/docs/INITIAL_VIDEO_LOAD_GUIDE.md)** - Bulk-loading an existing library via CLI

## 🛡️ Security Documentation

- **[Architecture: Security](https://github.com/prefect421/mvidarr/blob/main/docs/ARCHITECTURE.md#-security-architecture)** - Current authentication/authorization design
- **[Security Implementation](https://github.com/prefect421/mvidarr/blob/main/docs/SECURITY_IMPLEMENTATION.md)** - In-app request/input security layer (validation, headers, rate limiting)
- **[CLAUDE.md § Security Implementation](https://github.com/prefect421/mvidarr/blob/main/CLAUDE.md)** - Actively-maintained vulnerability scanning, CVE remediation history, compliance monitoring

## 🐳 Deployment Documentation

- **[Dockerfile.production](https://github.com/prefect421/mvidarr/blob/main/Dockerfile.production)** - Current multi-stage production build
- **[Self-Hosted Production Guide](https://github.com/prefect421/mvidarr/blob/main/docs/SELF_HOSTED_PRODUCTION.md)** - Production deployment with monitoring and backups
- **[Build Process](https://github.com/prefect421/mvidarr/blob/main/docs/BUILD_PROCESS.md)** - Local, Docker, and CI/CD build details

## 💻 Development Documentation

### Contributing
- **[Contributing Guide](https://github.com/prefect421/mvidarr/blob/main/CONTRIBUTING.md)** - How to contribute to the project
- **[Architecture](https://github.com/prefect421/mvidarr/blob/main/docs/ARCHITECTURE.md)** - System architecture and design
- **[API Documentation](https://github.com/prefect421/mvidarr/blob/main/docs/API_DOCUMENTATION.md)** - REST API reference (session-authenticated; interactive docs are dev-only)
- **[Database Migrations](https://github.com/prefect421/mvidarr/blob/main/docs/DATABASE_MIGRATIONS.md)** - Schema migration system
- **[Performance Monitoring](https://github.com/prefect421/mvidarr/blob/main/docs/PERFORMANCE_MONITORING.md)** - Monitoring API, instrumentation, optimization patterns
- **[Database Performance Optimization](https://github.com/prefect421/mvidarr/blob/main/docs/DATABASE_PERFORMANCE_OPTIMIZATION.md)** - Indexing and query optimization deep-dive
- **[System Monitoring](https://github.com/prefect421/mvidarr/blob/main/docs/MONITORING.md)** - Operational monitoring guide

### Release Information
- **[Release Notes](releases/)** - Detailed release information
- **[Changelog](https://github.com/prefect421/mvidarr/blob/main/CHANGELOG.md)** - Full version history
- **[v0.10.1 Scheduler V2 Migration Guide](https://github.com/prefect421/mvidarr/blob/main/docs/MIGRATION_0.10.1.md)** - Upgrading from the legacy scheduler

## 📋 Archive Documentation

### Historical Documentation
- **[Docker Optimization Guide (2025, v0.9.4)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/DOCKER_OPTIMIZATION_GUIDE.md)** - Historical image-size optimization work; its "optimization opportunities" section recommends removing Celery/Redis as unused, which is no longer true (they're core infrastructure) - don't follow it literally. See `Dockerfile.production` for the current build.
- **[Developer Setup Guide (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/DEVELOPER_SETUP_GUIDE.md)** - Superseded by the Contributing Guide; described a config format and database naming no longer used
- **[Legacy Installation Guide](https://github.com/prefect421/mvidarr/blob/main/docs/archive/INSTALLATION-GUIDE.md)** - Superseded by [Installation Guide](installation/); described a config format (`docker-config.yml`) no longer used
- **[Installation Archive](https://github.com/prefect421/mvidarr/blob/main/docs/archive/INSTALLATION_GUIDE.md)** - Historical installation guides
- **[Docker Archive](https://github.com/prefect421/mvidarr/blob/main/docs/archive/DOCKER-QUICKSTART.md)** - Archived Docker documentation
- **[Quickstart Archive](https://github.com/prefect421/mvidarr/blob/main/docs/archive/QUICKSTART.md)** - Historical quick start guides
- **[v1.0.0 Master TODO List (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/V1.0.0_TODO_MASTER_LIST.md)** - Superseded first attempt at v1.0.0 planning; all referenced issues closed
- **[v1.0.0 Development Start (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/V1.0.0_DEVELOPMENT_START.md)** - Superseded, same effort as above
- **[Issues Log (2025 snapshot)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/issues/Issues.md)** - Point-in-time issue log, superseded by [GitHub Issues](https://github.com/prefect421/mvidarr/issues)
- **[Features Snapshot (early)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/requirements/Features.md)** - Early feature-completion snapshot
- **[Production Incident Diagnostics](https://github.com/prefect421/mvidarr/tree/main/docs/archive/diagnostics)** - One-off scripts/notes from specific past production incidents
- **[Development Journal (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/JOURNAL.md)** - Point-in-time issue/lessons log; superseded by [CHANGELOG](https://github.com/prefect421/mvidarr/blob/main/CHANGELOG.md)
- **[Screenshot Capture Reports](https://github.com/prefect421/mvidarr/tree/main/docs/archive)** - One-off notes from the original USER-GUIDE.md screenshot effort
- **[Early Authentication Implementation Log (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/AUTHENTICATION_FEATURE_LOG.md)** - Described a Flask decorator-based plan (`@login_required`, etc.) that was never actually adopted; real enforcement shipped differently in v1.0.0 via FastAPI dependencies

## 📞 Getting Help

### Community Support
- **[GitHub Discussions](https://github.com/prefect421/mvidarr/discussions)** - Community Q&A and discussions
- **[GitHub Issues](https://github.com/prefect421/mvidarr/issues)** - Bug reports and feature requests

---

**Can't find what you're looking for?** Ask in [GitHub Discussions](https://github.com/prefect421/mvidarr/discussions) or open a [GitHub Issue](https://github.com/prefect421/mvidarr/issues)!
