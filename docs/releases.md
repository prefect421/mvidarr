---
layout: page
title: Releases
permalink: /releases/
---

# Releases

## 🚀 Current Release: v1.0.1

**Released**: August 28, 2026 — Dependency & Bugfix Sweep

- MKV transcoding notice on the video detail page is now dismissible (close button + persistent "don't show again")
- Fixed `Dockerfile.production` missing the Node.js/pot-provider additions, which caused PO tokens to be silently unavailable in production
- isort pinned in CI after an unpinned version bump silently broke the required pipeline check
- Dependency updates: fastapi, uvicorn, python-dotenv, mypy
- Security scan: zero open Dependabot alerts, zero open code-scanning alerts, pip-audit clean across all requirements files

### Docker Image
```bash
docker pull ghcr.io/prefect421/mvidarr:v1.0.1
docker pull ghcr.io/prefect421/mvidarr:latest
```

## 📌 v1.0.0 — First Production-Ready Release (August 17, 2026)

The milestone release: real RBAC enforcement (previously decorative), a modern login page with working OAuth (Authentik, Google, GitHub), two-factor authentication, native Discord/Apprise notifications, and a wave of live-testing bug fixes across downloads, playlists, and metadata sourcing.

## 📖 Full Release History

Every release — v1.0.1 back through the project's earliest versions — is documented in the [**CHANGELOG**]({{ site.github.repository_url }}/blob/main/CHANGELOG.md). That file is updated with every release and is the source of truth; this page intentionally doesn't duplicate it, since a second hand-maintained copy only goes stale.

For planned/in-progress work, see the [GitHub milestones]({{ site.github.repository_url }}/milestones) and the [project roadmap]({{ site.github.repository_url }}/projects/1).

## 📦 Getting a Release

### Docker
```bash
# Latest stable release
docker pull ghcr.io/prefect421/mvidarr:latest

# A specific version
docker pull ghcr.io/prefect421/mvidarr:v1.0.1

# Development build (dev branch)
docker pull ghcr.io/prefect421/mvidarr:dev
```

### Source
```bash
# Latest release tag
git clone --branch v1.0.1 https://github.com/prefect421/mvidarr.git

# Development branch
git clone --branch dev https://github.com/prefect421/mvidarr.git
```

## 🔄 Release Process

- **Development** happens on `dev`; changes merge to `main` for release once stable
- **Versioning**: SemVer 2.0.0 — `1.x.y` is the production-ready line
- **Security**: dependency and code scanning run continuously; see `docs/SECURITY_IMPLEMENTATION.md`

---

**Looking for details on a specific version?** The [CHANGELOG]({{ site.github.repository_url }}/blob/main/CHANGELOG.md) has full notes for every release.
