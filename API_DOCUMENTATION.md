# MVidarr API Documentation

**Last Updated**: 2025-10-29 (Phase 4/5 - Post-Refactoring)
**API Version**: 0.9.9-dev
**FastAPI Migration**: 100% Complete ✅

---

## Overview

MVidarr provides a comprehensive **FastAPI-based REST API** with **200+ endpoints** across **17 router modules**. All APIs support **async operations** and include **Pydantic validation**.

### API Features

- ✅ **Auto-Generated Documentation** - Interactive Swagger UI and ReDoc
- ✅ **Async Support** - High-performance async/await operations
- ✅ **Pydantic Validation** - Type-safe request/response models
- ✅ **WebSocket Support** - Real-time job progress and notifications
- ✅ **CORS Enabled** - Cross-origin resource sharing configured
- ✅ **Session Authentication** - Secure session-based auth
- ✅ **Backward Compatible** - All APIs maintain same interface after Phase 3 refactoring

---

## Accessing API Documentation

MVidarr provides **two interactive API documentation interfaces**:

### Swagger UI (Recommended)
```
http://localhost:5000/docs
```
- **Interactive** - Test endpoints directly from browser
- **Example Requests** - Pre-filled example values
- **Authentication** - Login through web interface first
- **Response Schemas** - Full type information

### ReDoc (Alternative)
```
http://localhost:5000/redoc
```
- **Clean Layout** - Better for reading documentation
- **Three-Column Design** - Navigation, content, code examples
- **Searchable** - Find endpoints quickly

### OpenAPI JSON Schema
```
http://localhost:5000/openapi.json
```
- **Machine Readable** - For API client generation
- **Full Schema** - All endpoints, models, and validation rules

---

## API Organization (Phase 3 Refactored Structure)

MVidarr APIs are organized into **17 specialized router modules** following Phase 3 large-file refactoring:

### Core Content APIs

#### 1. Videos API (`/api/videos`)
**Module**: `src/api/fastapi/videos_*.py` (11 modules)
**Endpoints**: 36 endpoints

- **CRUD Operations** (`videos_crud.py`)
  - `GET /api/videos` - List videos with pagination
  - `GET /api/videos/{id}` - Get video details
  - `POST /api/videos` - Create video
  - `PUT /api/videos/{id}` - Update video
  - `DELETE /api/videos/{id}` - Delete video

- **Search** (`videos_search.py`)
  - `GET /api/videos/search` - Advanced search
  - `GET /api/videos/search/advanced` - Multi-field search

- **Thumbnails** (`videos_thumbnails.py`)
  - `GET /api/videos/{id}/thumbnail` - Get thumbnail
  - `POST /api/videos/{id}/thumbnail/regenerate` - Regenerate thumbnail

- **Streaming** (`videos_streaming.py`)
  - `GET /api/videos/{id}/stream` - Stream video
  - `GET /api/videos/{id}/subtitles` - List subtitles
  - `GET /api/videos/{id}/subtitles/{filename}` - Serve subtitle file

- **Downloads** (`videos_downloads.py`)
  - `POST /api/videos/download` - Download from URL
  - `GET /api/videos/{id}/download-status` - Check download progress

- **Bulk Operations** (`videos_bulk.py`)
  - `POST /api/videos/bulk-update` - Bulk update
  - `POST /api/videos/bulk-delete` - Bulk delete
  - `POST /api/videos/bulk-tag` - Bulk tagging

- **Metadata** (`videos_metadata.py`)
  - `POST /api/videos/{id}/extract-metadata` - Extract FFmpeg metadata
  - `POST /api/videos/{id}/refresh-metadata` - Refresh from YouTube

- **Import/Export** (`videos_import.py`)
  - `POST /api/videos/import` - Import from JSON/CSV
  - `GET /api/videos/export` - Export to JSON/CSV

#### 2. Artists API (`/api/artists`)
**Module**: `src/api/fastapi/artists_*.py` (6 modules)
**Endpoints**: 26 endpoints

- **CRUD Operations** (`artists_crud.py`)
  - `GET /api/artists` - List artists
  - `GET /api/artists/{id}` - Get artist details
  - `POST /api/artists` - Create artist
  - `PUT /api/artists/{id}` - Update artist
  - `DELETE /api/artists/{id}` - Delete artist

- **Thumbnails** (`artists_thumbnails.py`)
  - `GET /api/artists/{id}/thumbnail` - Get thumbnail
  - `POST /api/artists/{id}/thumbnail/upload` - Upload custom thumbnail

- **Discovery** (`artists_discovery.py`)
  - `GET /api/artists/discover` - Search IMVDb for artists
  - `POST /api/artists/discover/import` - Import artist from IMVDb

- **Bulk Operations** (`artists_bulk.py`)
  - `POST /api/artists/bulk-update` - Bulk update
  - `POST /api/artists/bulk-merge` - Merge duplicate artists
  - `POST /api/artists/bulk-validate-metadata` - Validate metadata

#### 3. Playlists API (`/api/playlists`)
**Module**: `src/api/fastapi/playlists_*.py` (5 modules)
**Endpoints**: 22 endpoints

- **CRUD Operations** (`playlists_crud.py`)
  - `GET /api/playlists` - List playlists
  - `GET /api/playlists/{id}` - Get playlist details
  - `POST /api/playlists` - Create playlist
  - `PUT /api/playlists/{id}` - Update playlist
  - `DELETE /api/playlists/{id}` - Delete playlist

- **Playlist Items** (`playlists_crud.py`)
  - `POST /api/playlists/{id}/videos` - Add video to playlist
  - `DELETE /api/playlists/{id}/videos/{video_id}` - Remove video
  - `PUT /api/playlists/{id}/reorder` - Reorder videos

- **Dynamic Playlists** (`playlists_features.py`)
  - `POST /api/playlists/dynamic` - Create smart playlist
  - `GET /api/playlists/{id}/refresh` - Refresh dynamic playlist

### Metadata & Enrichment APIs

#### 4. Metadata Enrichment API (`/api/metadata-enrichment`)
**Module**: `src/api/fastapi/metadata_enrichment_*.py` (5 modules)
**Endpoints**: 21 endpoints

- **Search** (`metadata_enrichment_search.py`)
  - `GET /api/metadata-enrichment/search` - Search metadata sources
  - `GET /api/metadata-enrichment/search/artist` - Artist-specific search

- **Operations** (`metadata_enrichment_operations.py`)
  - `POST /api/metadata-enrichment/enrich` - Enrich video metadata
  - `POST /api/metadata-enrichment/enrich-artist` - Enrich artist metadata

- **Background Jobs** (`metadata_enrichment_jobs.py`)
  - `POST /api/metadata-enrichment/jobs/bulk-enrich` - Start bulk enrichment
  - `GET /api/metadata-enrichment/jobs/{job_id}` - Get job status

- **Analytics** (`metadata_enrichment_analytics.py`)
  - `GET /api/metadata-enrichment/stats` - Enrichment statistics
  - `GET /api/metadata-enrichment/quality-score` - Metadata quality metrics

### Background Jobs & System APIs

#### 5. Jobs API (`/api/jobs`)
**Module**: `src/api/fastapi/jobs.py`
**Endpoints**: 12 endpoints

- `GET /api/jobs` - List all jobs
- `GET /api/jobs/{job_id}` - Get job details
- `POST /api/jobs/{job_id}/cancel` - Cancel running job
- `DELETE /api/jobs/{job_id}` - Delete job
- `GET /api/jobs/stats` - Job system statistics
- `WebSocket /api/jobs/ws` - Real-time job updates

#### 6. Analytics API (`/api/analytics`)
**Module**: `src/api/fastapi/analytics.py`
**Endpoints**: 8 endpoints

- `GET /api/analytics/dashboard` - Dashboard statistics
- `GET /api/analytics/videos` - Video analytics
- `GET /api/analytics/artists` - Artist analytics
- `GET /api/analytics/downloads` - Download statistics
- `GET /api/analytics/storage` - Storage usage

#### 7. Settings API (`/api/settings`)
**Module**: `src/api/fastapi/settings.py`
**Endpoints**: 6 endpoints

- `GET /api/settings` - Get all settings
- `GET /api/settings/{key}` - Get specific setting
- `PUT /api/settings/{key}` - Update setting
- `POST /api/settings/reset` - Reset to defaults

### Service Integration APIs

#### 8. YouTube Playlists API (`/api/youtube-playlists`)
**Module**: `src/api/fastapi/youtube_playlists.py`

- `GET /api/youtube-playlists` - List monitored playlists
- `POST /api/youtube-playlists` - Add playlist monitoring
- `POST /api/youtube-playlists/{id}/sync` - Sync playlist

#### 9. Spotify API (`/api/spotify`)
**Module**: `src/api/fastapi/spotify.py`

- OAuth2 authentication flow
- Playlist import
- Artist discovery

#### 10. Last.fm API (`/api/lastfm`)
**Module**: `src/api/fastapi/lastfm.py`

- User authentication
- Scrobbling support
- Artist metadata

#### 11. Lidarr API (`/api/lidarr`)
**Module**: `src/api/fastapi/lidarr.py`

- Instance configuration
- Artist sync
- Webhook integration

#### 12. Discogs API (`/api/discogs`)
**Module**: `src/api/fastapi/discogs.py`

- Artist metadata enrichment
- Release information
- Image fetching

### Admin & Utility APIs

#### 13. Admin API (`/api/admin`)
**Module**: `src/api/fastapi/admin.py`

- User management
- System configuration
- Database maintenance

#### 14. Search API (`/api/search`)
**Module**: `src/api/fastapi/search.py`

- Global search across all content types
- Advanced search with filters

#### 15. Navigation API (`/api/navigation`)
**Module**: `src/api/fastapi/navigation.py`

- Menu structure
- User permissions
- Dynamic navigation

#### 16. Bulk Operations API (`/api/bulk`)
**Module**: `src/api/fastapi/bulk_*.py`

- Cross-entity bulk operations
- Progress tracking
- Error handling

#### 17. Webhooks API (`/api/webhooks`)
**Module**: `src/api/fastapi/webhooks.py`

- External service webhooks
- Event notifications
- Integration callbacks

---

## Authentication

### Session-Based Authentication

All API endpoints (except `/health` and `/docs`) require authentication.

**Login Process**:
1. Navigate to `http://localhost:5000/auth/login` in browser
2. Login with credentials (default: username=`admin`, password=`mvidarr`)
3. Session cookie is set automatically
4. Access API documentation at `/docs`
5. Test endpoints directly (authentication persists)

**Important**: API calls require a valid session. Direct API calls via `curl` or external tools require session cookie handling.

---

## Request/Response Format

### Standard Response Format

All APIs return JSON responses following this structure:

```json
{
  "status": "success|error",
  "data": { ... },
  "message": "Optional message",
  "errors": [ ... ]
}
```

### Pagination

List endpoints support pagination:

```json
{
  "items": [ ... ],
  "total": 1234,
  "page": 1,
  "per_page": 50,
  "pages": 25
}
```

**Query Parameters**:
- `page` - Page number (default: 1)
- `per_page` - Items per page (default: 50, max: 100)
- `sort_by` - Sort field
- `sort_order` - `asc` or `desc`

### Error Handling

HTTP Status Codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation error)
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `500` - Internal Server Error

Error Response:
```json
{
  "status": "error",
  "message": "Error description",
  "errors": [
    {
      "field": "field_name",
      "message": "Validation error",
      "type": "validation_error"
    }
  ]
}
```

---

## WebSocket APIs

### Real-Time Job Updates

**Endpoint**: `ws://localhost:5000/api/jobs/ws`

**Message Format**:
```json
{
  "type": "job_update",
  "job_id": "abc123",
  "status": "running|completed|failed",
  "progress": 75,
  "message": "Processing video...",
  "result": { ... }
}
```

**Usage Example**:
```javascript
const ws = new WebSocket('ws://localhost:5000/api/jobs/ws');
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log(`Job ${update.job_id}: ${update.progress}%`);
};
```

---

## Phase 3 Refactoring Changes

### What Changed in Phase 3

**Code Organization**: Large monolithic API files split into specialized modules
- `videos.py` (4,029 lines) → 11 modules
- `artists.py` (2,874 lines) → 6 modules
- `playlists.py` (1,480 lines) → 5 modules
- `metadata_enrichment.py` (1,433 lines) → 5 modules

**What Stayed the Same**:
- ✅ All endpoint URLs unchanged
- ✅ All request/response formats identical
- ✅ Authentication requirements unchanged
- ✅ Backward compatibility 100%

### Benefits

1. **Maintainability**: Easier to find and modify specific functionality
2. **Testing**: Each module can be tested independently
3. **Performance**: No impact - same async performance
4. **Documentation**: Auto-generated docs unchanged
5. **Development**: Faster development and code reviews

---

## API Client Generation

FastAPI's OpenAPI schema enables automatic client generation:

### Python Client
```bash
# Install OpenAPI Generator
pip install openapi-generator-cli

# Generate Python client
openapi-generator-cli generate \
  -i http://localhost:5000/openapi.json \
  -g python \
  -o ./mvidarr-client
```

### TypeScript/JavaScript Client
```bash
openapi-generator-cli generate \
  -i http://localhost:5000/openapi.json \
  -g typescript-fetch \
  -o ./mvidarr-ts-client
```

---

## Rate Limiting

Currently **no rate limiting** is enforced (self-hosted application).

For production deployment, consider adding rate limiting via:
- FastAPI middleware
- Reverse proxy (Nginx/Caddy)
- API gateway

---

## CORS Configuration

CORS is enabled for:
- `http://localhost:*` - Development
- Same-origin requests - Production

Custom origins can be configured in `fastapi_app.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Add your origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Testing the API

### Using Swagger UI (Easiest)
1. Login at `http://localhost:5000/auth/login`
2. Navigate to `http://localhost:5000/docs`
3. Click endpoint → "Try it out" → Fill parameters → "Execute"

### Using cURL (Advanced)
```bash
# Login and save cookies
curl -c cookies.txt -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"mvidarr"}'

# Use cookies for API calls
curl -b cookies.txt http://localhost:5000/api/videos
```

### Using Python Requests
```python
import requests

# Create session
session = requests.Session()

# Login
session.post('http://localhost:5000/auth/login', json={
    'username': 'admin',
    'password': 'mvidarr'
})

# Make API calls
response = session.get('http://localhost:5000/api/videos')
videos = response.json()
```

---

## Support & Issues

- **API Bugs**: Create issue on GitHub with `Area: API` label
- **Documentation Issues**: Create issue with `documentation` label
- **Feature Requests**: Create issue with `enhancement` label

---

## Future Enhancements

Planned for 1.0 release:
- [ ] API versioning (`/api/v1/...`)
- [ ] Rate limiting
- [ ] API key authentication (alternative to sessions)
- [ ] GraphQL endpoint (in addition to REST)
- [ ] Webhook management UI
- [ ] API usage analytics

---

**Maintained By**: MVidarr Development Team
**Last Review**: Phase 5 (Cleanup) - Milestone 0.9.9
**Next Review**: 1.0.0 Release
