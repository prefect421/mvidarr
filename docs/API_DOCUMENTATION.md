# API Documentation Guide

## Overview

MVidarr provides a comprehensive REST API with full OpenAPI 3.0 specification, interactive documentation, and multiple viewing interfaces. The API supports complete music video management operations, external service integrations, and system monitoring.

## API Access Points

### Interactive Documentation

**These are only served when the app runs with `MVIDARR_ENV=dev`** (see `fastapi_app.py`) — they're disabled entirely in production/Docker deployments, so don't expect them on a normal self-hosted install:

- **Swagger UI**: `http://localhost:5000/docs`
- **ReDoc**: `http://localhost:5000/redoc`
- **OpenAPI JSON**: `http://localhost:5000/openapi.json`

## API Structure

### Base Configuration
```yaml
OpenAPI Version: 3.0.0 (FastAPI-generated)
Base URL: http://localhost:5000/api
Content-Type: application/json
Authentication: Required on every endpoint (session cookie) - see CLAUDE.md
                § API Development & Testing. There is no unauthenticated
                API surface; test through a logged-in browser session.
Rate Limiting: Enforced (src/middleware/rate_limiting_middleware.py) -
                300 requests/min by default, static files exempt
```

### Core Resource Categories

#### 1. Artists Management (`/api/artists`)
**Purpose**: Complete artist lifecycle management

**Key Endpoints**:
- `GET /api/artists` - List all artists with filtering, pagination, sorting
- `POST /api/artists` - Create new artist
- `GET /api/artists/{id}` - Get specific artist details
- `PUT /api/artists/{id}` - Update artist information  
- `DELETE /api/artists/{id}` - Delete artist (with optional video deletion)

**Advanced Features**:
- Search by name with fuzzy matching
- Filter by monitored status, source, creation date
- Sort by name, creation date, last discovery
- Pagination with configurable page sizes (max 200)

**Artist Schema Highlights**:
```json
{
  "id": 1,
  "name": "Taylor Swift",
  "imvdb_id": "1234",
  "spotify_id": "06HL4z0CvFAxyc27GXpf02",
  "lastfm_name": "Taylor Swift",
  "thumbnail_url": "https://example.com/thumb.jpg",
  "auto_download": true,
  "monitored": true,
  "source": "imvdb|spotify_import|lastfm_import|plex_sync|manual",
  "keywords": ["pop", "country"],
  "created_at": "2023-01-01T00:00:00Z"
}
```

#### 2. Videos Management (`/api/videos`)
**Purpose**: Video catalog and status management

**Key Endpoints**:
- `GET /api/videos` - List all videos with comprehensive filtering
- Video-specific operations (creation, updates, status changes)

**Advanced Filtering**:
- Search by title
- Filter by artist, status, source
- Sort by title, creation date, year
- Status filtering: WANTED, DOWNLOADING, DOWNLOADED, IGNORED, FAILED, MONITORED

**Video Schema Highlights**:
```json
{
  "id": 1,
  "artist_id": 1,
  "title": "Shake It Off",
  "youtube_id": "nfWlot6h_JM", 
  "youtube_url": "https://www.youtube.com/watch?v=nfWlot6h_JM",
  "local_path": "/data/downloads/Taylor Swift/Shake It Off.mp4",
  "duration": 242,
  "year": 2014,
  "status": "DOWNLOADED",
  "quality": "720p"
}
```

#### 3. External Integrations (`/api/{service}`)
**Purpose**: External service status and configuration

**Supported Services**:
- **Spotify**: `/api/spotify/status` - Authentication status, profile info
- **YouTube**: `/api/youtube/playlists` - Playlist monitoring management
- **Last.fm**: `/api/lastfm/status` - Account status and authentication  
- **Plex**: `/api/plex/status` - Server connection and configuration

**Integration Features**:
- Real-time connection status
- Authentication state monitoring
- Configuration validation
- Profile and account information

#### 4. System Operations (`/api/system`)
**Purpose**: Health monitoring and system management

**Health Monitoring**: `/api/health`
```json
{
  "status": "healthy|degraded|unhealthy",
  "timestamp": "2023-01-01T00:00:00Z",
  "services": {
    "database": {"status": "connected", "latency": 5},
    "metube": {"status": "available", "version": "2023.10.04"},
    "imvdb": {"status": "accessible", "rate_limit": "ok"},
    "filesystem": {"status": "writable", "free_space": "500GB"}
  }
}
```

#### 5. Settings Management (`/api/settings`)
**Purpose**: System configuration and preferences

**Operations**:
- `GET /api/settings` - Retrieve all settings
- `PUT /api/settings` - Update multiple settings atomically

**Setting Schema**:
```json
{
  "id": 1,
  "key": "metube_host",
  "value": "localhost",
  "description": "MeTube server hostname",
  "created_at": "2023-01-01T00:00:00Z"
}
```

## API Design Principles

### 1. RESTful Architecture
- Standard HTTP methods (GET, POST, PUT, DELETE)
- Resource-based URL design
- Stateless request handling
- Consistent error responses

### 2. Consistent Response Format
**Success Responses**:
```json
{
  "data": {...},
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 150,
    "pages": 3
  }
}
```

**Error Responses**:
```json
{
  "error": "Resource not found",
  "message": "The requested resource could not be found",
  "code": 404
}
```

### 3. Advanced Query Capabilities
**Pagination**:
- `page` - Page number (default: 1)
- `limit` - Items per page (default: 50, max: 200)

**Searching**:
- `search` - Full-text search within resource names/titles

**Filtering**:
- Resource-specific filters (status, source, monitored, etc.)
- Boolean filters for true/false values

**Sorting**:
- `sort` - Field to sort by
- `order` - Sort direction (asc/desc)

### 4. Schema Validation
All request/response data follows strict OpenAPI schemas with:
- Type validation
- Format validation (date, email, URL)
- Enum constraints for limited value sets
- Required field validation
- Range validation for numeric fields

## Integration Examples

All examples below need an authenticated session — none of these calls work unauthenticated. Log in through the web UI first and reuse that session's cookie (e.g. `requests.Session()` after a POST to the login endpoint, or your browser's cookie for a quick `curl` test), per `CLAUDE.md` § API Development & Testing.

### 1. Python Integration
```python
import requests

session = requests.Session()
session.post('http://localhost:5000/auth/login', json={"username": "...", "password": "..."})

# Get all monitored artists
response = session.get('http://localhost:5000/api/artists?monitored=true')
artists = response.json()['artists']

# Create new artist
artist_data = {
    "name": "New Artist",
    "auto_download": True,
    "monitored": True,
    "keywords": ["rock", "alternative"]
}
response = session.post('http://localhost:5000/api/artists', json=artist_data)
```

### 2. JavaScript Integration
```javascript
// Runs from a page already served by an authenticated session -
// the session cookie is sent automatically
const response = await fetch('/api/videos?status=DOWNLOADED&limit=100');
const data = await response.json();
const videos = data.videos;

// Update artist settings
const updateData = { auto_download: false, monitored: false };
await fetch(`/api/artists/${artistId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updateData)
});
```

### 3. cURL Examples
```bash
# Reuse your browser's session cookie (DevTools > Application > Cookies)
COOKIE="session=..."

# Get system health
curl -H "Cookie: $COOKIE" http://localhost:5000/api/health

# Search for artists
curl -H "Cookie: $COOKIE" "http://localhost:5000/api/artists?search=taylor&monitored=true"

# Create playlist monitor
curl -X POST http://localhost:5000/api/youtube/playlists \
  -H "Cookie: $COOKIE" -H "Content-Type: application/json" \
  -d '{"playlist_url": "https://youtube.com/playlist?list=...", "auto_download": true}'
```

## Development Integration

### 1. Code Generation
Use the OpenAPI specification for automatic client generation:

```bash
# Generate Python client
openapi-generator-cli generate \
  -i http://localhost:5000/api/docs/openapi.json \
  -g python \
  -o ./mvidarr-python-client

# Generate TypeScript client  
openapi-generator-cli generate \
  -i http://localhost:5000/api/docs/openapi.json \
  -g typescript-fetch \
  -o ./mvidarr-ts-client
```

### 2. API Testing
The OpenAPI spec enables automated testing:

```python
# Pytest with OpenAPI validation
import pytest
from openapi_spec_validator import validate_spec
import requests

def test_openapi_spec_valid():
    spec = requests.get('http://localhost:5000/api/docs/openapi.json').json()
    validate_spec(spec)  # Validates OpenAPI specification

def test_artists_endpoint_schema():
    response = requests.get('http://localhost:5000/api/artists')
    assert response.status_code == 200
    # Additional schema validation against OpenAPI spec
```

### 3. Documentation Integration  
Integrate API docs into CI/CD:

```yaml
# GitHub Actions example
- name: Generate API Documentation
  run: |
    curl http://localhost:5000/api/docs/openapi.json > openapi.json
    redoc-cli build openapi.json --output docs/api.html

- name: Validate API Spec
  run: |
    swagger-codegen-cli validate -i openapi.json
```

## API Security Considerations

### Current Security Model
- **No Authentication**: Currently open access (development/local use)
- **No Rate Limiting**: Unlimited request rates
- **Local Access**: Designed for localhost deployment

### Future Security Enhancements
- API key authentication
- JWT token-based access
- Rate limiting per client
- CORS configuration for web clients
- HTTPS enforcement
- Request/response logging

## Performance Characteristics

### Response Times
- Simple queries (single resource): < 50ms
- Complex queries with filters: < 200ms
- Bulk operations: 1-5 seconds depending on size
- Health checks: < 10ms

### Pagination Efficiency
- Default page size: 50 items
- Maximum page size: 200 items
- Large datasets handled efficiently with database indexing
- Cursor-based pagination for very large results (future enhancement)

## Error Handling

### Standard HTTP Status Codes
- **200 OK**: Successful operation
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid request parameters or body
- **404 Not Found**: Resource not found
- **409 Conflict**: Duplicate resource or constraint violation
- **500 Internal Server Error**: Server-side error

### Error Response Schema
```json
{
  "error": "Brief error description",
  "message": "Detailed error message for developers",
  "code": 400,
  "details": {
    "field": "Specific field validation errors",
    "constraint": "Database constraint information"
  }
}
```

## Extending the API

### Adding New Endpoints
1. Define endpoint in `openapi.py` schema
2. Implement handler in appropriate API module
3. Add request/response validation
4. Update interactive documentation
5. Add integration tests

### Schema Evolution
- Backward compatible changes preferred
- Version API endpoints when breaking changes needed
- Maintain multiple schema versions during transitions
- Document breaking changes in release notes

## Monitoring and Analytics

### API Usage Tracking
- Request volume by endpoint
- Response time distribution
- Error rate monitoring
- Popular query parameters

### Performance Monitoring
```python
# Example monitoring integration
import time
from flask import request, g

@app.before_request
def before_request():
    g.start_time = time.time()

@app.after_request  
def after_request(response):
    duration = time.time() - g.start_time
    # Log API performance metrics
    logger.info(f"API {request.method} {request.path} - {response.status_code} - {duration:.3f}s")
    return response
```

## Related Documentation
- [User Guide](USER-GUIDE.md) - Using the web interface
- [Contributing Guide](https://github.com/prefect421/mvidarr/blob/main/CONTRIBUTING.md) - Development environment setup
- [Architecture Documentation](ARCHITECTURE.md) - System design
- [Troubleshooting Guide](TROUBLESHOOTING.md) - Common API issues

---

**Note**: The API documentation is automatically updated when the OpenAPI specification changes. Always refer to the interactive documentation at `/api/docs/swagger` for the most current endpoint information and examples.