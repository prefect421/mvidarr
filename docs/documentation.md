---
layout: page
title: Documentation
permalink: /documentation/
---

# Documentation

Comprehensive documentation and guides for MVidarr users, administrators, and developers.

## 📖 User Documentation

### Getting Started
- **[Installation Guide](installation/)** - Complete setup instructions for all environments
- **[User Guide](https://github.com/prefect421/mvidarr/blob/main/docs/USER-GUIDE.md)** - Feature documentation and tutorials
- **[Docker Optimization Guide](https://github.com/prefect421/mvidarr/blob/main/docs/DOCKER_OPTIMIZATION_GUIDE.md)** - Container optimization and monitoring

### Core Features
- **[Video Organization](https://github.com/prefect421/mvidarr/blob/main/docs/VIDEO_ORGANIZATION.md)** - Organizing and managing your video library

## 🛡️ Security Documentation

### Authentication & Access Control
- **[Security Implementation](https://github.com/prefect421/mvidarr/blob/main/docs/SECURITY_IMPLEMENTATION.md)** - Complete security overview
- **[Architecture: Security](https://github.com/prefect421/mvidarr/blob/main/docs/ARCHITECTURE.md#-security-architecture)** - Current authentication/authorization design


## 🐳 Deployment Documentation

### Docker & Containerization
- **[Docker Optimization Guide](https://github.com/prefect421/mvidarr/blob/main/docs/DOCKER_OPTIMIZATION_GUIDE.md)** - Container build optimization and monitoring


## 💻 Development Documentation

### Contributing
- **[Contributing Guide](https://github.com/prefect421/mvidarr/blob/main/CONTRIBUTING.md)** - How to contribute to the project

### Release Information
- **[Release Notes](releases/)** - Detailed release information
- **[Changelog](https://github.com/prefect421/mvidarr/blob/main/CHANGELOG.md)** - Full version history

## 📋 Archive Documentation

### Historical Documentation
- **[Docker Optimization Guide (2025, v0.9.4)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/DOCKER_OPTIMIZATION_GUIDE.md)** - Historical image-size optimization work; its "optimization opportunities" section recommends removing Celery/Redis as unused, which is no longer true (they're core infrastructure) - don't follow it literally. See `Dockerfile.production` for the current build.
- **[Installation Archive](https://github.com/prefect421/mvidarr/blob/main/docs/archive/INSTALLATION_GUIDE.md)** - Historical installation guides
- **[Docker Archive](https://github.com/prefect421/mvidarr/blob/main/docs/archive/DOCKER-QUICKSTART.md)** - Archived Docker documentation
- **[Quickstart Archive](https://github.com/prefect421/mvidarr/blob/main/docs/archive/QUICKSTART.md)** - Historical quick start guides
- **[v1.0.0 Master TODO List (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/V1.0.0_TODO_MASTER_LIST.md)** - Superseded first attempt at v1.0.0 planning; all referenced issues closed
- **[v1.0.0 Development Start (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/V1.0.0_DEVELOPMENT_START.md)** - Superseded, same effort as above
- **[Issues Log (2025 snapshot)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/issues/Issues.md)** - Point-in-time issue log, superseded by [GitHub Issues](https://github.com/prefect421/mvidarr/issues)
- **[Features Snapshot (early)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/requirements/Features.md)** - Early feature-completion snapshot
- **[Production Incident Diagnostics](https://github.com/prefect421/mvidarr/tree/main/docs/archive/diagnostics)** - One-off scripts/notes from specific past production incidents
- **[Legacy Installation Guide](https://github.com/prefect421/mvidarr/blob/main/docs/archive/INSTALLATION-GUIDE.md)** - Superseded by [Installation Guide](installation/); described a config format (`docker-config.yml`) no longer used
- **[Development Journal (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/JOURNAL.md)** - Point-in-time issue/lessons log; superseded by [CHANGELOG](https://github.com/prefect421/mvidarr/blob/main/CHANGELOG.md)
- **[Screenshot Capture Reports](https://github.com/prefect421/mvidarr/tree/main/docs/archive)** - One-off notes from the original USER-GUIDE.md screenshot effort
- **[Early Authentication Implementation Log (2025)](https://github.com/prefect421/mvidarr/blob/main/docs/archive/AUTHENTICATION_FEATURE_LOG.md)** - Described a Flask decorator-based plan (`@login_required`, etc.) that was never actually adopted; real enforcement shipped differently in v1.0.0 via FastAPI dependencies


## 📞 Getting Help

### Community Support
- **[GitHub Discussions](https://github.com/prefect421/mvidarr/discussions)** - Community Q&A and discussions
- **[GitHub Issues](https://github.com/prefect421/mvidarr/issues)** - Bug reports and feature requests



---

**Can't find what you're looking for?** Ask in [GitHub Discussions](https://github.com/prefect421/mvidarr/discussions) or open a [GitHub Issue](https://github.com/prefect421/mvidarr/issues)!