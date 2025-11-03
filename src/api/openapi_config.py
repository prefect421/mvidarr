"""
OpenAPI Configuration and Schema Customization for MVidarr FastAPI
Enhanced documentation with authentication, examples, and comprehensive API descriptions.
"""

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi


def custom_openapi_schema(app: FastAPI) -> Dict[str, Any]:
    """
    Generate custom OpenAPI schema with enhanced security, examples, and documentation
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="MVidarr API",
        version="0.9.8",
        description=app.description,
        routes=app.routes,
        servers=app.servers,
    )

    # Add comprehensive security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "SessionAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "session",
            "description": "Session-based authentication using secure cookies",
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token authentication for API access",
        },
        "OAuth2": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": "/api/auth/oauth/authorize",
                    "tokenUrl": "/api/auth/oauth/token",
                    "scopes": {
                        "read": "Read access to resources",
                        "write": "Write access to resources",
                        "admin": "Administrative access",
                    },
                }
            },
            "description": "OAuth2 authentication with multiple providers",
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key authentication for external integrations",
        },
    }

    # Add global security requirement (can be overridden per endpoint)
    openapi_schema["security"] = [
        {"SessionAuth": []},
        {"BearerAuth": []},
        {"OAuth2": ["read", "write"]},
        {"ApiKeyAuth": []},
    ]

    # Add custom info extensions
    openapi_schema["info"]["x-logo"] = {
        "url": "/static/logo.png",
        "altText": "MVidarr Logo",
    }

    # Add API version history
    openapi_schema["info"]["x-version-history"] = [
        {
            "version": "0.9.8",
            "date": "2025-01-01",
            "changes": "Phase 3 Week 31 - OpenAPI Documentation Complete",
        },
        {
            "version": "0.9.7",
            "date": "2024-12-15",
            "changes": "Phase 3 Week 30 - Admin API Migration Complete",
        },
        {
            "version": "0.9.6",
            "date": "2024-12-08",
            "changes": "Phase 3 Week 29 - Playlists API Migration Complete",
        },
    ]

    # Enhanced contact information
    openapi_schema["info"]["contact"]["x-support"] = {
        "documentation": "https://prefect421.github.io/mvidarr",
        "issues": "https://github.com/prefect421/mvidarr/issues",
        "discussions": "https://github.com/prefect421/mvidarr/discussions",
    }

    # Add external documentation
    openapi_schema["externalDocs"] = {
        "description": "Complete MVidarr Documentation",
        "url": "https://prefect421.github.io/mvidarr",
    }

    # Add comprehensive examples for common operations
    _add_schema_examples(openapi_schema)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


def _add_schema_examples(openapi_schema: Dict[str, Any]):
    """Add comprehensive examples to the OpenAPI schema"""

    # Video examples
    video_example = {
        "id": 1,
        "title": "Example Music Video",
        "artist": "Example Artist",
        "status": "downloaded",
        "url": "https://youtube.com/watch?v=example",
        "file_path": "/videos/example_artist/example_video.mp4",
        "thumbnail": "/thumbnails/example_video.jpg",
        "created_at": "2024-01-01T12:00:00Z",
        "updated_at": "2024-01-01T12:30:00Z",
    }

    # Artist examples
    artist_example = {
        "id": 1,
        "name": "Example Artist",
        "video_count": 5,
        "imvdb_id": 12345,
        "spotify_id": "4uLU6hMCjMI75M1A2tKUQC",
        "formed_year": 2020,
        "location": "Los Angeles, CA",
        "website": "https://exampleartist.com",
        "created_at": "2024-01-01T12:00:00Z",
    }

    # Playlist examples
    playlist_example = {
        "id": 1,
        "name": "My Favorite Videos",
        "description": "Collection of favorite music videos",
        "video_count": 10,
        "is_public": True,
        "is_dynamic": False,
        "created_by": 1,
        "created_at": "2024-01-01T12:00:00Z",
    }

    # Add examples to components
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}

    if "examples" not in openapi_schema["components"]:
        openapi_schema["components"]["examples"] = {}

    openapi_schema["components"]["examples"].update(
        {
            "VideoExample": {
                "summary": "Complete video object",
                "description": "Example of a fully populated video with all metadata",
                "value": video_example,
            },
            "ArtistExample": {
                "summary": "Complete artist object",
                "description": "Example of a fully populated artist with metadata",
                "value": artist_example,
            },
            "PlaylistExample": {
                "summary": "Complete playlist object",
                "description": "Example of a playlist with basic metadata",
                "value": playlist_example,
            },
            "ErrorResponse": {
                "summary": "Standard error response",
                "description": "Example error response format",
                "value": {
                    "detail": "Resource not found",
                    "error_code": "RESOURCE_NOT_FOUND",
                    "timestamp": "2024-01-01T12:00:00Z",
                },
            },
            "ValidationError": {
                "summary": "Validation error response",
                "description": "Example validation error with field details",
                "value": {
                    "detail": [
                        {
                            "loc": ["body", "title"],
                            "msg": "field required",
                            "type": "value_error.missing",
                        }
                    ],
                    "error_code": "VALIDATION_ERROR",
                },
            },
        }
    )


def setup_custom_docs(app: FastAPI):
    """Setup custom documentation with enhanced UI"""

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        """Custom Swagger UI with enhanced styling and configuration"""
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Interactive API Documentation",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_ui_parameters={
                "defaultModelsExpandDepth": 2,
                "defaultModelExpandDepth": 2,
                "displayOperationId": True,
                "displayRequestDuration": True,
                "filter": True,
                "showExtensions": True,
                "showCommonExtensions": True,
                "tryItOutEnabled": True,
                "persistAuthorization": True,
                "layout": "StandaloneLayout",
                "deepLinking": True,
            },
            swagger_css_url="/static/swagger-ui-custom.css",
            swagger_favicon_url="/static/favicon.ico",
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc_html():
        """Custom ReDoc interface with enhanced styling"""
        return get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - API Reference",
            redoc_js_url="/static/redoc.standalone.js",
            redoc_favicon_url="/static/favicon.ico",
            with_google_fonts=True,
        )

    # Custom OpenAPI endpoint with caching
    @app.get("/openapi.json", include_in_schema=False)
    async def custom_openapi():
        """Custom OpenAPI schema endpoint"""
        return custom_openapi_schema(app)


def add_openapi_metadata_to_routers(app: FastAPI):
    """Add enhanced metadata to all routers for better documentation"""

    # This would typically be called after all routers are included
    # to add additional metadata, examples, and descriptions

    for route in app.routes:
        if hasattr(route, "endpoint") and hasattr(route.endpoint, "__doc__"):
            # Enhance route documentation
            if not route.summary and route.endpoint.__doc__:
                # Extract first line as summary
                doc_lines = route.endpoint.__doc__.strip().split("\n")
                route.summary = doc_lines[0]

                # Use remaining lines as description
                if len(doc_lines) > 1:
                    route.description = "\n".join(doc_lines[1:]).strip()


# Response examples for common HTTP status codes
COMMON_RESPONSES = {
    200: {
        "description": "Successful operation",
        "content": {
            "application/json": {
                "example": {
                    "success": True,
                    "message": "Operation completed successfully",
                }
            }
        },
    },
    201: {
        "description": "Resource created successfully",
        "content": {
            "application/json": {
                "example": {"success": True, "message": "Resource created", "id": 1}
            }
        },
    },
    400: {
        "description": "Bad request - Invalid input data",
        "content": {
            "application/json": {
                "example": {"detail": "Invalid input data", "error_code": "BAD_REQUEST"}
            }
        },
    },
    401: {
        "description": "Unauthorized - Authentication required",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Authentication required",
                    "error_code": "UNAUTHORIZED",
                }
            }
        },
    },
    403: {
        "description": "Forbidden - Insufficient permissions",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Insufficient permissions",
                    "error_code": "FORBIDDEN",
                }
            }
        },
    },
    404: {
        "description": "Resource not found",
        "content": {
            "application/json": {
                "example": {"detail": "Resource not found", "error_code": "NOT_FOUND"}
            }
        },
    },
    422: {
        "description": "Validation error",
        "content": {
            "application/json": {
                "example": {
                    "detail": [
                        {
                            "loc": ["body", "field"],
                            "msg": "field required",
                            "type": "value_error.missing",
                        }
                    ]
                }
            }
        },
    },
    500: {
        "description": "Internal server error",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Internal server error",
                    "error_code": "INTERNAL_ERROR",
                }
            }
        },
    },
}
