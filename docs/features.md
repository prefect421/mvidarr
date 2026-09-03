---
layout: page
title: Features
permalink: /features/
---

# Features

## 🎯 Artist Management

- **Multi-criteria Search**: Find artists by name, genre, source, monitoring status
- **Bulk Operations**: Edit multiple artists simultaneously with progress tracking
- **Metadata Enrichment**: Automatic thumbnail fetching (Spotify/Last.fm prioritized over Wikipedia), genre tagging, biography updates
- **Per-Artist Video-Type Filtering**: Choose which video types (Official Video, Official Music Video, Live, Lyric Video, etc.) auto-download per artist
- **Monitoring Controls**: Enable/disable monitoring and auto-download per artist

## 🔍 Video Discovery & Download

- **Dual-Source Discovery**: IMVDb + YouTube, with quota-aware search batching
- **Scheduler V2**: Prioritized, automated discovery/download runs with exponential/linear/fixed retry strategies
- **Duplicate Detection**: DB-level unique constraints on `youtube_id`/`imvdb_id` close race conditions between concurrent imports
- **Quality Control**: Configurable min/max/default quality, format sorting, automatic quality upgrades
- **Video Status Tracking**: WANTED, DOWNLOADING, DOWNLOADED, IGNORED, FAILED, MONITORED
- **"Recently Found"**: Live view of newly discovered videos

## 📺 Streaming Experience

- **Built-in HTML5 Player** with real-time MKV transcoding (FFmpeg remux/transcode, browser-compatible output)
- **Subtitle Support**: WebVTT, SRT, ASS, SSA, SUB, with smart language-pattern resolution for YouTube's non-standard codes
- **MvTV Mode**: Continuous playback for uninterrupted viewing
- **Responsive Design** across desktop, tablet, and mobile
- **Theme System**: 6 built-in themes (Default, Cyber, VaporWave, TARDIS, Punk 77, MTV) with export/import

## 🛡️ Security & Access Control

- **Enforced RBAC**: Admin, Manager, User, ReadOnly roles — actually checked on every request, not decorative
- **OAuth Login**: Authentik, Google, GitHub, alongside local accounts, with a signup allowlist and admin-only account creation policy
- **Two-Factor Authentication**: TOTP + backup codes
- **Session-Based Auth**: Every API endpoint requires an authenticated session
- **bcrypt Password Hashing**, account lockout on repeated failed logins, secure password-reset flow
- **Audit Logging** for authentication and security-relevant events

## 🔔 Notifications & Integrations

- **Discord** and **Apprise** notification providers, wired to real download/artist activity
- **Webhooks** for event-driven external integration
- **Spotify** (OAuth import, similar-artist discovery), **Last.fm** thumbnail/metadata sourcing
- **Media Server Sync**: Plex, Jellyfin, and Emby library synchronization
- **Lidarr** integration for music library sync

## 📊 Management & Monitoring

- **System Health Dashboard**: Database, cache, and system resource status (`/api/performance/*`)
- **Download Queue**: Real-time progress, priority management, automatic retry with backoff
- **Database-Driven Configuration**: Change most settings at runtime, no restart required
- **Backup Management**: Scheduled backups with retention policies

## 🎨 User Interface

- **Left Sidebar Navigation** with collapsible sections
- **Real-Time Search** with advanced multi-criteria filters and bulk selection
- **Responsive Layout** across screen sizes

## 🔧 Architecture Highlights

- **FastAPI** backend, fully async — the Flask-to-FastAPI migration is complete, no Flask API endpoints remain
- **Celery + Redis** for background job processing (discovery, downloads, metadata enrichment)
- **MariaDB 11.4+** with SQLAlchemy, connection pooling tuned for library size
- **Docker**: simple 3-container deployment (app+Celery via supervisord, MariaDB, Redis)

## What's Next

Release history, in-progress work, and planned changes are tracked in the [changelog]({{ site.github.repository_url }}/blob/main/CHANGELOG.md) and the [GitHub milestones]({{ site.github.repository_url }}/milestones) — those are kept current release-to-release, unlike a hand-maintained roadmap on this page would be.

## 💡 Feature Requests

Have an idea for a new feature? We'd love to hear about it!

- **GitHub Issues**: [Submit feature requests]({{ site.github.repository_url }}/issues/new?template=feature_request.md)
- **Discussions**: [Join the conversation]({{ site.github.repository_url }}/discussions)
- **Contributing**: [Help build the features you want]({{ site.github.repository_url }}/blob/main/CONTRIBUTING.md)
