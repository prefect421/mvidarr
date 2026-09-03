# MVidarr System Architecture

## Overview

MVidarr is built with a modern, fully-async **FastAPI** architecture (the earlier Flask implementation was fully migrated away — zero Flask API endpoints remain, see `CHANGELOG.md` v0.9.8). The system follows a layered, service-oriented design with clear separation between the API layer, the service (business logic) layer, and the database layer.

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    External APIs                            │
│  YouTube │ IMVDb │ Spotify │ Last.fm │ Plex/Jellyfin/Emby   │
│                    Lidarr │ Discord/Apprise                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                 Service Layer (src/services/)                │
│  Integration Services │ Core Services │ Background Jobs      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              API Layer (src/api/fastapi/)                    │
│    Async Routers │ Session Auth (Depends) │ Middleware       │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│               Frontend Layer (frontend/)                     │
│      Jinja2 Templates │ JavaScript │ CSS │ Static Assets     │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Database Layer                                │
│   MariaDB/MySQL │ SQLAlchemy Models │ Migration System        │
└─────────────────────────────────────────────────────────────┘
```

Background work (discovery, downloads, metadata enrichment) runs through **Celery + Redis**, alongside the FastAPI process rather than inline in a request.

## 🏛️ Application Structure

### Directory Organization
```
mvidarr/
├── fastapi_app.py               # Main application entry point
├── src/
│   ├── api/fastapi/              # FastAPI routers (one file per resource area)
│   │   ├── videos.py, artists_crud.py, settings.py, performance.py, ...
│   │   └── auth_dependencies.py  # require_authentication / require_admin
│   ├── config/                   # Environment + database-backed configuration
│   ├── database/
│   │   ├── models.py             # SQLAlchemy models
│   │   ├── connection.py         # Connection pooling
│   │   ├── init_db.py            # Table creation + migration runner (runs on startup)
│   │   └── migrations.py         # Custom migration framework (see migrations/)
│   ├── services/                 # Business logic (167+ modules: discovery, downloads,
│   │                              # thumbnails, OAuth, notifications, integrations, ...)
│   ├── jobs/celery_app.py        # Celery application and task registration
│   └── utils/                    # Logging, performance monitoring, shared helpers
├── frontend/
│   ├── templates/                # Jinja2 HTML templates (base.html + page templates)
│   ├── static/                   # JavaScript and images
│   └── CSS/                      # Modular stylesheets
├── migrations/                   # Numbered schema migration scripts
└── data/                         # Runtime data (videos, thumbnails, cache, logs)
```

### Main Application Entry Point

**File**: `fastapi_app.py`

Responsibilities on startup:
- Calls `initialize_database()` (`src/database/init_db.py`), which creates tables if needed, seeds default settings and built-in themes, and runs any pending migrations — no manual DB setup step is required
- Registers all FastAPI routers from `src/api/fastapi/`
- Configures session middleware, CORS, and security headers
- Starts background service hooks

## 🗄️ Database Architecture

### Database Technology Stack
- **ORM**: SQLAlchemy, declarative models
- **Database**: MariaDB 11.4+ / MySQL 8.0+ only — MVidarr does not support SQLite
- **Connection Management**: Pooled connections (see `docs/PERFORMANCE_MONITORING.md` for tuning)
- **Migrations**: Two systems exist historically — the active one is the numbered-script runner in `src/database/migrations.py` + `migrations/`, invoked automatically by `initialize_database()`. An `alembic/` setup also exists but has effectively gone unused since a single early migration; treat `migrations/` as the source of truth.

### Core Domain Models (abbreviated — see `src/database/models.py` for the full schema)

```python
class Artist(Base):
    __tablename__ = "artists"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    folder_path = Column(String(500))
    imvdb_id = Column(Integer, index=True)
    spotify_id = Column(String(255), index=True)
    thumbnail_url = Column(String(500))
    videos = relationship("Video", back_populates="artist")


class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False)
    youtube_id = Column(String(50), unique=True, index=True)   # unique constraint closes a
    imvdb_id = Column(Integer, unique=True, index=True)         # duplicate-download race (#377)
    status = Column(Enum(VideoStatus), default=VideoStatus.WANTED)
    file_path = Column(String(500))
    artist = relationship("Artist", back_populates="videos")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)   # bcrypt
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    two_factor_secret = Column(String(32), nullable=True)
    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    backup_codes = Column(JSON, nullable=True)
```

`UserRole` is hierarchical: `READONLY < USER < MANAGER < ADMIN`. RBAC is enforced on every route via `Depends(require_authentication)` / `Depends(require_admin)` — see Security Architecture below.

## 🔧 Service Layer Architecture

Services in `src/services/` follow a consistent shape: a class wrapping one area of business logic, using `get_logger("mvidarr.<name>")` for logging and `SettingsService` for database-backed configuration. Long-running or externally-facing methods are wrapped with `@monitor_performance("service.method")` (see `docs/PERFORMANCE_MONITORING.md`).

Representative service groups:
- **Discovery & downloads**: `video_discovery_service`, `youtube_download_engine`, `ytdlp_download_manager`, `video_quality_service`
- **Metadata & thumbnails**: `imvdb_discovery_service`, `imvdb_analytics_service`, `thumbnail_service`
- **External integrations**: `async_spotify_service`, `spotify_sync_service`, `lastfm_service`, `plex_service`, `jellyfin_service`, `emby_service`
- **Notifications**: `discord_notification_formatter`, `apprise_notification_service`, `webhook_service`
- **Auth & security**: `auth_service`, `oauth_service`, `two_factor_service`
- **Scheduling**: Scheduler V2 (Celery Beat-based) — see `docs/SCHEDULER_V2.md`

### External Service Integration Pattern

External API clients share a common shape: pull the API key from `SettingsService`, rate-limit outbound requests, and raise a domain-specific exception on failure so callers don't have to inspect raw HTTP responses.

## 🌐 API Layer Architecture

### Router Organization

Each resource area is a FastAPI `APIRouter` in `src/api/fastapi/`, registered on the main app in `fastapi_app.py`:

```python
router = APIRouter(prefix="/api/videos", tags=["videos"])

@router.get("/")
async def list_videos(current_user: dict = Depends(require_authentication)):
    ...

@router.post("/{video_id}/download")
async def download_video(video_id: int, current_user: dict = Depends(require_authentication)):
    ...
```

### Authentication & Authorization

Every API endpoint requires an authenticated session — there is no unauthenticated API surface (see `CLAUDE.md` § API Development & Testing). This is enforced per-route via FastAPI dependencies, not a global before-request hook:

```python
# src/api/fastapi/auth_dependencies.py
async def require_authentication(current_user: dict = Depends(get_current_user)) -> dict:
    """Any authenticated user (any role)"""
    ...

async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """ADMIN role only"""
    ...
```

Routes pick the dependency matching the access level they need. This replaced an earlier, decorative RBAC implementation where every session was effectively hardcoded to admin — real enforcement shipped in v1.0.0.

OAuth login (Authentik, Google, GitHub) and TOTP-based two-factor authentication sit in front of this — see `src/services/oauth_service.py` and `src/services/two_factor_service.py`.

## 🖥️ Frontend Architecture

### Template System

Server-rendered Jinja2 templates, all extending a shared `base.html`:

```jinja2
{% extends "base.html" %}
{% block content %}
  ...
{% endblock %}
```

`base.html` loads the core scripts on every page: `toast.js`, `main.js`, `loading-feedback.js`, `js/background-jobs.js`, plus Socket.IO (client-side) for real-time job/download progress updates.

### Static Asset Organization

```
frontend/CSS/
├── main.css              # Base styles and layout
├── themes.css            # Theme variables (6 built-in themes)
├── layout.css, typography.css, buttons.css
├── videos.css            # Video-specific styling
├── bulk-operations-enhanced.css
└── accessibility.css
```

## 🔐 Security Architecture

1. **Session-based authentication**, enforced per-endpoint via FastAPI `Depends`
2. **Role-Based Access Control**: `READONLY < USER < MANAGER < ADMIN`, actually checked (not decorative)
3. **OAuth 2.0 / OIDC**: Authentik, Google, GitHub, with a signup allowlist and admin-only account creation policy
4. **Two-Factor Authentication**: TOTP + backup codes
5. **Account protection**: failed-login lockout, bcrypt password hashing, secure password reset
6. **Audit logging** for authentication and security-relevant events

## 🚀 Performance

See `docs/PERFORMANCE_MONITORING.md` for the live monitoring API, instrumentation pattern, and database/frontend optimization guidance, and `docs/DATABASE_PERFORMANCE_OPTIMIZATION.md` for the indexing/query-optimization work behind `DatabasePerformanceOptimizer`.

## 🔍 Logging

```python
from src.utils.logger import get_logger
logger = get_logger("mvidarr.<component>")
```

Rotating file handler, size and retention configurable via database settings (`log_max_size`, `log_backup_count`).

## 📚 Related Documentation

- **Configuration Guide**: `CONFIGURATION_GUIDE.md`
- **API Documentation**: `API_DOCUMENTATION.md`
- **Database Migrations**: `DATABASE_MIGRATIONS.md`
- **Performance Monitoring**: `PERFORMANCE_MONITORING.md`
- **Scheduler V2**: `SCHEDULER_V2.md`
- **Security**: `SECURITY_IMPLEMENTATION.md`

## 🔄 Design Principles

- **Layered separation**: API routers stay thin; business logic lives in services
- **Database-driven configuration**: most settings changeable at runtime via `SettingsService`, no redeploy needed
- **Async throughout**: the FastAPI layer and Celery background jobs both use async I/O where it matters (external API calls, downloads)
- **Structured migrations**: schema changes are numbered, tracked, and applied automatically on startup
