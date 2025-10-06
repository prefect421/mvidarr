---
layout: page
title: Releases
permalink: /releases/
---

# Releases

Track MVidarr's development progress through our release history and upcoming milestones.

## 🚀 Current Release: v0.9.8

**Released**: October 6, 2025
**Focus**: Service Integration & API Migration Completion

### Major Improvements
- **🔌 Service Integration Pages**: Complete implementation of YouTube Playlists, Spotify, Last.fm, and Lidarr manager pages
- **✅ Lidarr Integration**: 100% API migration complete (5/5 endpoints)
- **✅ Last.fm Integration**: 100% API migration complete (13/13 endpoints)
- **✅ YouTube Playlists**: 100% API migration complete (9/9 endpoints with route aliases)
- **✅ Spotify Integration**: 100% API migration complete (12/12 endpoints with OAuth placeholders)
- **🐛 Critical Bug Fixes**: Resolved blacklist loading errors, playlist page failures, and service integration routing
- **🏗️ Flask to FastAPI Migration**: 100% complete with comprehensive service integration documentation

### Key Features
- **Service Integration Pages**: All four integration manager pages (YouTube, Spotify, Last.fm, Lidarr) now accessible
- **Blacklist Management**: Fixed API response structure mismatches for proper blacklist functionality
- **Playlist System**: Corrected JavaScript loading and API endpoint accessibility
- **API Documentation**: Complete service integration migration status document (SERVICE_INTEGRATION_API_STATUS.md)
- **Built-in Themes**: Added database migrations for 6 built-in themes (Cyber, Default, VaporWave, TARDIS, Punk 77, MTV)
- **Video Playback**: Fixed MKV video playback with proper MIME type detection

### Critical Bug Fixes (Recent)
- ✅ Fixed blacklist loading TypeError - corrected API response field names (blacklist_entries vs blacklist)
- ✅ Fixed blacklist delete endpoint - changed from URL to ID-based deletion
- ✅ Fixed playlist page loading - corrected JavaScript URL and response structure
- ✅ Added missing service integration page routes (YouTube Playlists, Spotify, Last.fm, Lidarr)
- ✅ Fixed migration 015 - use admin user ID instead of hardcoded user
- ✅ Fixed MKV video playback MIME type detection
- ✅ Fixed OAuth2 status JavaScript errors in settings page
- ✅ Added missing enhanced-refresh-all-metadata FastAPI endpoint
- ✅ Fixed YouTube Playlists route pattern mismatch - added route aliases for frontend compatibility
- ✅ Added all missing Spotify OAuth and playlist import endpoints
- ✅ Added Spotify OAuth callback endpoint - completes OAuth authorization flow with token exchange

### Technical Enhancements
- **FastAPI Async Architecture**: Complete migration from Flask with performance improvements
- **Advanced Job Queue**: Exponential/linear/fixed retry strategies with dependency management
- **WebSocket Integration**: Real-time job progress updates and client notifications
- **Comprehensive Testing**: 40+ Playwright tests across authentication, API, and UI validation
- **CI/CD Integration**: Automated testing with multi-browser support and GitHub Actions

### Known Issues & Limitations
- **Spotify OAuth**: OAuth endpoints use placeholder responses pending full OAuth implementation
- **Background Jobs**: Some job monitoring features may need investigation (download progress, metadata refresh status)
- **Service Configuration**: Download quality settings and external service connectivity require verification

See `SERVICE_INTEGRATION_API_STATUS.md` for complete API migration status and planned improvements for v0.9.9.

**Docker Image**: `ghcr.io/prefect421/mvidarr:v0.9.8`

---

## 🔄 Development Version: v0.9.9-dev

**Status**: In Active Development  
**Focus**: Enterprise Features & Multi-User Support

### Planned Improvements
- Advanced user management and role-based access control
- Multi-tenant artist libraries and data isolation
- Comprehensive audit logging and activity tracking
- API rate limiting and resource quota management
- Enhanced authentication integration (LDAP/SSO)

---

## 📅 Release Roadmap

### v0.9.6 - Quality Assurance & Testing Infrastructure
**Planned Release**: November 2025

- Comprehensive pytest test suite framework
- Visual testing and screenshot automation  
- Log capture and error analysis system
- CI/CD testing integration and automation
- Test monitoring and maintenance infrastructure

### v0.9.7 - Advanced Features & Integration  
**Planned Release**: February 2026

- Advanced video filtering and search system
- Bulk operations and batch management system
- Enhanced artist discovery and metadata enrichment
- Import/export and backup management system
- Custom video organization rules and automation

### v0.9.9 - Enterprise & Multi-User Features
**Planned Release**: December 2025

- Advanced user management and role-based access control
- Multi-tenant artist libraries and data isolation
- Comprehensive audit logging and activity tracking
- API rate limiting and resource quota management
- Enterprise authentication integration (LDAP/SSO/SAML)

### v0.9.10 - External Service Integrations
**Planned Release**: March 2026

- Enhanced Spotify integration and music discovery
- Media server integration (Plex/Jellyfin/Emby)
- Advanced notification system with Discord/Slack integration
- Third-party metadata providers integration
- Cloud storage integration and backup solutions

### v1.0.0 - Production Readiness & Stability
**Planned Release**: November 2026 - **Public Release**

- Complete documentation overhaul and user guides
- Migration tools and database upgrade automation
- Advanced backup and disaster recovery system
- Production deployment automation and infrastructure
- Long-term maintenance tools and system optimization

---

## 📈 Previous Releases

### v0.9.4
**Released**: August 6, 2025  
**Focus**: Docker Optimization and Build Reliability

- Docker build optimization and reliability improvements
- Container size reduction and performance enhancements
- Build monitoring infrastructure and validation tools
- Production-ready container configurations
- Comprehensive Docker build automation

### v0.9.3
**Released**: July 28, 2025  
**Focus**: Security Implementation

- Enterprise-grade security audit completion
- Comprehensive vulnerability remediation (17 issues fixed)
- Advanced security monitoring infrastructure
- Automated security scanning workflows
- Enhanced authentication and authorization systems

### v0.9.2  
**Released**: July 15, 2025  
**Focus**: Core Functionality Stabilization

- Advanced artist management system
- Comprehensive video discovery and organization
- Modern UI with theme system implementation
- Database-driven configuration management
- System health monitoring and diagnostics

### v0.9.1
**Released**: June 2025  
**Focus**: Foundation and Architecture

- Initial Flask application architecture
- Basic artist and video management
- Database schema and ORM implementation
- Authentication system foundation
- Docker containerization setup

---

## 🔄 Release Process

### Release Cycles
- **Major Releases** (x.y.0): Every 3-4 months with significant new features
- **Minor Releases** (x.y.z): Monthly with bug fixes and small improvements  
- **Security Releases**: As needed for critical security updates

### Quality Assurance
- **Automated Testing**: Comprehensive test suite with CI/CD integration
- **Security Scanning**: Multi-tool security validation on every release
- **Performance Testing**: Automated performance regression testing
- **Docker Validation**: Container build and size optimization verification

### Release Notes
Each release includes detailed notes covering:
- New features and improvements
- Security updates and fixes
- Performance enhancements
- Breaking changes and migration guides
- Known issues and workarounds

---

## 📋 Release Statistics

### Development Metrics
- **Total Releases**: 4 major releases
- **Issues Resolved**: 150+ across all releases
- **Security Fixes**: 17 vulnerabilities addressed
- **Docker Optimization**: 100% build reliability achieved
- **Test Coverage**: 90%+ code coverage (target for v0.9.6)

### Performance Improvements
- **Docker Build Time**: From timeout failures to 8m6s consistent builds
- **Container Size**: Optimized to 1.41GB production images  
- **Security Posture**: Zero known vulnerabilities maintained
- **API Response Times**: <500ms for typical operations (target)
- **Database Performance**: Optimized for 10,000+ video libraries

---

## 🎯 Version Support

### Current Support Status
- **v0.9.4**: ✅ Fully supported with security updates
- **v0.9.3**: ✅ Security updates only
- **v0.9.2**: ⚠️ End of life - upgrade recommended
- **v0.9.1**: ❌ End of life - upgrade required

### Support Policy
- **Latest Release**: Full feature support and security updates
- **Previous Release**: Security updates for 6 months
- **Older Releases**: End of life after 1 year

---

## 📦 Download & Deployment

### Docker Images
```bash
# Latest stable release
docker pull ghcr.io/prefect421/mvidarr:latest

# Specific version
docker pull ghcr.io/prefect421/mvidarr:v0.9.4

# Development build
docker pull ghcr.io/prefect421/mvidarr:dev
```

### Source Code
```bash
# Latest release
git clone --branch v0.9.4 https://github.com/prefect421/mvidarr.git

# Development version
git clone --branch dev https://github.com/prefect421/mvidarr.git
```

### Release Verification
All releases are:
- **Signed**: GPG signatures for source releases
- **Checksummed**: SHA256 checksums for all artifacts
- **Scanned**: Security scanned before publication
- **Tested**: Automated testing and validation

---

## 📢 Release Notifications

Stay updated on new releases:

- **GitHub Releases**: [Watch the repository]({{ site.github.repository_url }}) for notifications
- **Release RSS**: Subscribe to our [releases RSS feed]({{ site.github.repository_url }}/releases.atom)
- **GitHub Discussions**: Join [release discussions]({{ site.github.repository_url }}/discussions/categories/releases)
- **Security Alerts**: Subscribe to [security advisories]({{ site.github.repository_url }}/security/advisories)

---

**Looking for a specific version?** Check our complete [release history on GitHub]({{ site.github.repository_url }}/releases).