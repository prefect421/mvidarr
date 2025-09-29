"""
FastAPI Template System - Issue 130 Template System Migration
Comprehensive template migration from Flask to FastAPI with async support
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja2.ext import Extension

from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.template_system")


class AsyncTemplateSystem:
    """FastAPI template system with Flask compatibility"""

    def __init__(
        self,
        template_directory: str = "frontend/templates",
        static_directory: str = "frontend/static",
    ):
        self.template_directory = template_directory
        self.static_directory = static_directory

        # Initialize Jinja2 templates with async support
        self.templates = Jinja2Templates(directory=template_directory)

        # Enhanced Jinja2 environment for compatibility
        self.env = Environment(
            loader=FileSystemLoader(template_directory),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=True,
            auto_reload=True,
        )

        # Flask compatibility functions
        self._setup_flask_compatibility()

        # Template context processors
        self.context_processors: List[Callable] = []

        # Cache for compiled templates
        self.template_cache: Dict[str, Any] = {}

        # URL generation mapping
        self.url_mappings: Dict[str, str] = {}
        self._setup_url_mappings()

    def _setup_flask_compatibility(self):
        """Setup Flask-compatible template functions"""

        # Add Flask-like url_for function
        def url_for(endpoint: str, **kwargs) -> str:
            """Flask-compatible URL generation for FastAPI"""

            # Map Flask blueprint endpoints to FastAPI routes
            endpoint_mapping = {
                # Frontend routes
                "frontend.index": "/",
                "frontend.dashboard": "/",
                "frontend.videos": "/videos",
                "frontend.artists": "/artists",
                "frontend.playlists": "/playlists",
                "frontend.settings": "/settings",
                "frontend.jobs": "/frontend.jobs",
                "frontend.mvtv": "/frontend.mvtv",
                # Detail pages
                "frontend.video_detail": "/video",
                "frontend.artist_detail": "/artist",
                "frontend.playlist_detail": "/playlist",
                # Admin routes
                "frontend.admin_dashboard": "/admin",
                "admin.dashboard": "/admin",
                "frontend.admin_users": "/admin/users",
                "admin.users": "/admin/users",
                "frontend.admin_create_user": "/admin/users/create",
                "admin.create_user": "/admin/users/create",
                # Authentication routes
                "auth.login": "/auth/login",
                "auth.logout": "/auth/logout",
                "auth.simple_login": "/auth/simple-login",
                "auth.2fa_setup": "/auth/2fa/setup",
                "auth.2fa_verify": "/auth/2fa/verify",
                # API routes
                "api.videos": "/api/videos",
                "api.artists": "/api/artists",
                "api.playlists": "/api/playlists",
                "api.settings": "/api/settings",
                "api.admin": "/api/admin",
                "api.jobs": "/api/jobs",
                "api.health": "/api/health",
                "api.search": "/api/search",
                "api.discover": "/discover",
                # MeTube/Download API routes
                "api.metube_queue": "/api/metube/queue",
                "api.metube_history": "/api/metube/history",
                # Theme/UI routes
                "api.themes": "/api/themes",
                "themes.current": "/api/themes/current",
                # Static files
                "static": "/static",
                "frontend.static_files": "/static",
                "frontend.css_files": "/css",
                "frontend.js_files": "/static/js",
            }

            base_url = endpoint_mapping.get(endpoint, endpoint)

            # Special handling for static files
            if endpoint in ("static", "frontend.static_files"):
                filename = kwargs.get("filename", "")
                if filename:
                    return f"/static/{filename}"
                return "/static/"

            # Handle CSS and JS file endpoints
            if endpoint == "frontend.css_files":
                filename = kwargs.get("filename", "")
                if filename:
                    return f"/css/{filename}"
                return "/css/"

            if endpoint == "frontend.js_files":
                filename = kwargs.get("filename", "")
                if filename:
                    return f"/static/js/{filename}"
                return "/static/js/"

            # Handle query parameters for non-static routes
            if kwargs:
                params = []
                for key, value in kwargs.items():
                    if key == "_external":
                        continue  # Skip Flask-specific parameters
                    params.append(f"{key}={value}")

                if params:
                    base_url += "?" + "&".join(params)

            return base_url

        # Add to Jinja2 environment
        self.env.globals["url_for"] = url_for
        self.templates.env.globals["url_for"] = url_for

        # Add other Flask-like functions
        def get_flashed_messages():
            """Placeholder for Flask flash messages"""
            # TODO: Implement FastAPI session-based flash messages
            return []

        self.env.globals["get_flashed_messages"] = get_flashed_messages
        self.templates.env.globals["get_flashed_messages"] = get_flashed_messages

        # Add config access
        def config_get(key: str, default=None):
            """Get configuration values in templates"""
            return settings.get(key, default)

        self.env.globals["config"] = {"get": config_get}
        self.templates.env.globals["config"] = {"get": config_get}

    def _setup_url_mappings(self):
        """Setup URL mappings for template compatibility"""
        self.url_mappings = {
            # Frontend pages
            "/": "index.html",
            "/videos": "videos.html",
            "/artists": "artists.html",
            "/playlists": "playlists.html",
            "/settings": "settings.html",
            # Admin pages
            "/admin": "admin/dashboard.html",
            "/admin/users": "admin/users.html",
            "/admin/users/create": "admin/create_user.html",
            # Authentication pages
            "/auth/login": "auth/login.html",
            "/auth/simple-login": "auth/simple_login.html",
            "/auth/2fa/setup": "auth/2fa_setup.html",
            "/auth/2fa/verify": "auth/2fa_verify.html",
        }

    def add_context_processor(self, processor: Callable):
        """Add a template context processor"""
        self.context_processors.append(processor)

    async def get_template_context(
        self, request: Request, additional_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Build template context with all processors"""
        context = {
            "request": request,
            "datetime": datetime,
            "len": len,
            "str": str,
            "int": int,
            "bool": bool,
            "list": list,
            "dict": dict,
        }

        # Add authentication context
        auth_context = await self._get_auth_context(request)
        context.update(auth_context)

        # Add settings context
        settings_context = await self._get_settings_context(request)
        context.update(settings_context)

        # Add application context
        app_context = await self._get_app_context(request)
        context.update(app_context)

        # Add theme context for server-side rendering
        current_theme = await self._get_current_theme_for_ssr()
        context.update({"current_theme": current_theme})

        # Run context processors
        for processor in self.context_processors:
            try:
                if asyncio.iscoroutinefunction(processor):
                    processor_context = await processor(request)
                else:
                    processor_context = processor(request)

                if isinstance(processor_context, dict):
                    context.update(processor_context)

            except Exception as e:
                logger.error(f"Context processor error: {e}")

        # Add additional context
        if additional_context:
            context.update(additional_context)

        return context

    async def _get_current_theme_for_ssr(self) -> Dict[str, Any]:
        """Get current theme data for server-side rendering to prevent FOUC"""
        try:
            # Import here to avoid circular imports
            from sqlalchemy.orm import Session

            from src.api.fastapi.themes import router as themes_router
            from src.database.connection import get_db_session
            from src.database.models import CustomTheme, Setting

            # Get database session
            session_gen = get_db_session()
            session = next(session_gen)

            try:
                # Get current theme setting
                theme_setting = (
                    session.query(Setting).filter(Setting.key == "ui_theme").first()
                )
                current_theme_name = theme_setting.value if theme_setting else "default"

                # Look for theme in database
                theme = (
                    session.query(CustomTheme)
                    .filter(CustomTheme.name == current_theme_name)
                    .first()
                )

                if theme and theme.theme_data:
                    return {
                        "name": theme.name,
                        "variables": theme.theme_data,
                        "display_name": theme.display_name or theme.name,
                    }

                # Fallback for built-in themes without database records
                if current_theme_name != "default":
                    # Try to extract built-in theme data
                    logger.info(
                        f"Extracting built-in theme data for: {current_theme_name}"
                    )

                    # Get default theme variables for fallback
                    return {
                        "name": current_theme_name,
                        "variables": {},  # Will fall back to CSS defaults
                        "display_name": current_theme_name.title(),
                    }

                # Default theme
                return {"name": "default", "variables": {}, "display_name": "Default"}

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error getting current theme for SSR: {e}")
            # Fallback to default theme
            return {"name": "default", "variables": {}, "display_name": "Default"}

    async def _get_auth_context(self, request: Request) -> Dict[str, Any]:
        """Get authentication context for templates"""
        auth_context = {
            "current_user": None,
            "is_authenticated": False,
            "user_role": None,
            "session": {},
            "auth_enabled": True,  # Default to enabled
        }

        try:
            # Check if authentication middleware is enabled
            from src.services.settings_service import settings

            auth_enabled = settings.get("require_authentication", True)
            auth_context["auth_enabled"] = auth_enabled

            # If authentication is disabled, provide a mock user context
            if not auth_enabled:
                auth_context.update(
                    {
                        "current_user": {
                            "id": 1,
                            "username": "admin",
                            "role": "admin",
                            "is_authenticated": True,
                        },
                        "is_authenticated": True,
                        "user_role": "admin",
                    }
                )
                return auth_context

            # Check for session data (when auth middleware is enabled)
            if hasattr(request.state, "user"):
                user = request.state.user
                auth_context.update(
                    {
                        "current_user": user,
                        "is_authenticated": True,
                        "user_role": getattr(user, "role", "user"),
                    }
                )

            # Check session
            if hasattr(request.state, "session"):
                auth_context["session"] = request.state.session

            # Check for mock authentication in development
            elif request.url.path not in ["/auth/login", "/auth/simple-login"]:
                # Provide temporary auth context for template compatibility
                auth_context.update(
                    {
                        "current_user": {
                            "id": 1,
                            "username": "dev_user",
                            "role": "admin",
                        },
                        "is_authenticated": True,
                        "user_role": "admin",
                    }
                )

        except Exception as e:
            logger.warning(f"Auth context error: {e}")

        return auth_context

    async def _get_settings_context(self, request: Request) -> Dict[str, Any]:
        """Get application settings context for templates"""
        try:
            return {
                "app_name": settings.get("app_name", "MVidarr"),
                "app_version": settings.get("app_version", "1.0.0"),
                "theme": settings.get("default_theme", "dark"),
                "require_authentication": settings.get("require_authentication", True),
                "enable_2fa": settings.get("enable_2fa", False),
                "max_upload_size": settings.get("max_upload_size_mb", 100),
            }
        except Exception as e:
            logger.error(f"Settings context error: {e}")
            return {}

    async def _get_app_context(self, request: Request) -> Dict[str, Any]:
        """Get general application context"""
        return {
            "current_time": datetime.utcnow(),
            "base_url": str(request.base_url).rstrip("/"),
            "path": request.url.path,
            "method": request.method,
            "user_agent": request.headers.get("user-agent", ""),
            "remote_addr": request.client.host if request.client else "unknown",
        }

    async def render_template(
        self, template_name: str, request: Request, context: Dict[str, Any] = None
    ) -> str:
        """Render template with async context"""
        try:
            # Build full context
            full_context = await self.get_template_context(request, context)

            # Load and render template
            template = self.env.get_template(template_name)

            if template.environment.is_async:
                rendered = await template.render_async(**full_context)
            else:
                rendered = template.render(**full_context)

            return rendered

        except Exception as e:
            logger.error(f"Template rendering error for {template_name}: {e}")

            # Try to render a fallback error template
            try:
                if template_name != "errors/500.html":  # Prevent infinite recursion
                    error_context = {
                        "error_message": f"Template rendering failed: {template_name}",
                        "error_code": 500,
                        "template_error": str(e),
                        "requested_template": template_name,
                    }
                    error_template = self.env.get_template("errors/500.html")
                    if error_template.environment.is_async:
                        rendered = await error_template.render_async(**error_context)
                    else:
                        rendered = error_template.render(**error_context)
                    return rendered
            except Exception as fallback_error:
                logger.error(f"Fallback template rendering failed: {fallback_error}")

            # Final fallback: simple HTML error page
            return f"""
            <!DOCTYPE html>
            <html>
            <head><title>Template Error - MVidarr</title></head>
            <body>
                <h1>Template Error</h1>
                <p>Failed to render template: {template_name}</p>
                <p>Error: {str(e)}</p>
                <a href="/">Return to Dashboard</a>
            </body>
            </html>
            """

    async def render_response(
        self, template_name: str, request: Request, context: Dict[str, Any] = None
    ) -> HTMLResponse:
        """Render template and return HTML response"""
        rendered_content = await self.render_template(template_name, request, context)
        return HTMLResponse(content=rendered_content)

    def get_static_url(self, path: str) -> str:
        """Get static file URL"""
        return f"/static/{path.lstrip('/')}"

    def register_template_filter(self, name: str, func: Callable):
        """Register custom template filter"""
        self.env.filters[name] = func
        self.templates.env.filters[name] = func

    def register_template_global(self, name: str, value: Any):
        """Register global template variable"""
        self.env.globals[name] = value
        self.templates.env.globals[name] = value


# Global template system instance
template_system = AsyncTemplateSystem()


# Template context processors
async def inject_navigation_context(request: Request) -> Dict[str, Any]:
    """Inject navigation context"""
    return {
        "navigation": {
            "dashboard": {
                "name": "Dashboard",
                "url": "/",
                "icon": "mdi:view-dashboard",
            },
            "videos": {"name": "Videos", "url": "/videos", "icon": "mdi:video"},
            "artists": {
                "name": "Artists",
                "url": "/artists",
                "icon": "mdi:account-music",
            },
            "playlists": {
                "name": "Playlists",
                "url": "/playlists",
                "icon": "mdi:playlist-play",
            },
            "settings": {"name": "Settings", "url": "/settings", "icon": "mdi:cog"},
        }
    }


async def inject_ui_context(request: Request) -> Dict[str, Any]:
    """Inject UI-related context"""
    return {
        "ui": {
            "sidebar_collapsed": False,
            "theme": "dark",
            "notifications_enabled": True,
            "search_enabled": True,
        }
    }


async def inject_system_info(request: Request) -> Dict[str, Any]:
    """Inject system information"""
    try:
        # Read version info
        version_file = Path("version.json")
        if version_file.exists():
            with open(version_file, "r") as f:
                version_info = json.load(f)
        else:
            version_info = {"version": "1.0.0", "git_commit": "unknown"}

        return {
            "system_info": {
                "version": version_info.get("version", "1.0.0"),
                "commit": version_info.get("git_commit", "unknown")[:8],
                "uptime": "N/A",  # TODO: Calculate actual uptime
            }
        }
    except Exception as e:
        logger.error(f"System info context error: {e}")
        return {
            "system_info": {"version": "1.0.0", "commit": "unknown", "uptime": "N/A"}
        }


# Register context processors
template_system.add_context_processor(inject_navigation_context)
template_system.add_context_processor(inject_ui_context)
template_system.add_context_processor(inject_system_info)


# Custom template filters
def datetime_format(value: datetime, format_string: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime for templates"""
    if isinstance(value, datetime):
        return value.strftime(format_string)
    return str(value)


def filesize_format(value: Union[int, float]) -> str:
    """Format file size for templates"""
    try:
        size = float(value)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    except (ValueError, TypeError):
        return str(value)


def truncate_string(value: str, length: int = 50) -> str:
    """Truncate string for templates"""
    if len(value) <= length:
        return value
    return value[: length - 3] + "..."


# Register filters
template_system.register_template_filter("datetime_format", datetime_format)
template_system.register_template_filter("filesize_format", filesize_format)
template_system.register_template_filter("truncate", truncate_string)


class FastAPITemplateRoutes:
    """FastAPI route handlers for template pages"""

    def __init__(self, template_system: AsyncTemplateSystem):
        self.template_system = template_system

    async def index(self, request: Request) -> HTMLResponse:
        """Dashboard page"""
        context = {
            "page_title": "Dashboard",
            "page_description": "MVidarr Dashboard - Overview of your media collection",
        }
        return await self.template_system.render_response(
            "index.html", request, context
        )

    async def videos(self, request: Request) -> HTMLResponse:
        """Videos management page"""
        context = {
            "page_title": "Videos",
            "page_description": "Manage your video collection",
            "show_add_video": True,
        }
        return await self.template_system.render_response(
            "videos.html", request, context
        )

    async def artists(self, request: Request) -> HTMLResponse:
        """Artists management page"""
        context = {
            "page_title": "Artists",
            "page_description": "Browse and manage artists",
        }
        return await self.template_system.render_response(
            "artists.html", request, context
        )

    async def artist_detail(self, request: Request, artist_id: int) -> HTMLResponse:
        """Artist detail page"""
        context = {
            "page_title": f"Artist Details",
            "page_description": f"View artist information and videos",
            "artist_id": artist_id,
        }
        return await self.template_system.render_response(
            "artist_detail.html", request, context
        )

    async def playlists(self, request: Request) -> HTMLResponse:
        """Playlists management page"""
        context = {
            "page_title": "Playlists",
            "page_description": "Create and manage playlists",
        }
        return await self.template_system.render_response(
            "playlists.html", request, context
        )

    async def settings(self, request: Request) -> HTMLResponse:
        """Settings page"""
        context = {
            "page_title": "Settings",
            "page_description": "Application configuration and preferences",
        }
        return await self.template_system.render_response(
            "settings.html", request, context
        )

    # Authentication pages
    async def login(self, request: Request) -> HTMLResponse:
        """Login page"""
        context = {
            "page_title": "Login",
            "page_description": "Sign in to MVidarr",
            "hide_navigation": True,
        }
        return await self.template_system.render_response(
            "auth/login.html", request, context
        )

    async def simple_login(self, request: Request) -> HTMLResponse:
        """Simple login page"""
        context = {
            "page_title": "Simple Login",
            "page_description": "Quick sign in",
            "hide_navigation": True,
        }
        return await self.template_system.render_response(
            "auth/simple_login.html", request, context
        )

    async def two_fa_setup(self, request: Request) -> HTMLResponse:
        """Two-factor authentication setup"""
        context = {
            "page_title": "2FA Setup",
            "page_description": "Set up two-factor authentication",
            "hide_navigation": True,
        }
        return await self.template_system.render_response(
            "auth/2fa_setup.html", request, context
        )

    async def two_fa_verify(self, request: Request) -> HTMLResponse:
        """Two-factor authentication verification"""
        context = {
            "page_title": "2FA Verification",
            "page_description": "Verify your two-factor authentication code",
            "hide_navigation": True,
        }
        return await self.template_system.render_response(
            "auth/2fa_verify.html", request, context
        )

    # Admin pages
    async def admin_dashboard(self, request: Request) -> HTMLResponse:
        """Admin dashboard"""
        context = {
            "page_title": "Admin Dashboard",
            "page_description": "Administration and system management",
            "admin_only": True,
        }
        return await self.template_system.render_response(
            "admin/dashboard.html", request, context
        )

    async def admin_users(self, request: Request) -> HTMLResponse:
        """User management page"""
        context = {
            "page_title": "User Management",
            "page_description": "Manage system users",
            "admin_only": True,
        }
        return await self.template_system.render_response(
            "admin/users.html", request, context
        )

    async def admin_create_user(self, request: Request) -> HTMLResponse:
        """Create user page"""
        context = {
            "page_title": "Create User",
            "page_description": "Add new system user",
            "admin_only": True,
        }
        return await self.template_system.render_response(
            "admin/create_user.html", request, context
        )


# Create global route handlers
template_routes = FastAPITemplateRoutes(template_system)


# Helper functions for FastAPI integration
def get_template_system() -> AsyncTemplateSystem:
    """Get global template system instance"""
    return template_system


def render_template_response(template_name: str):
    """Decorator to simplify template rendering"""

    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            context = (
                await func(request, *args, **kwargs)
                if asyncio.iscoroutinefunction(func)
                else func(request, *args, **kwargs)
            )
            if not isinstance(context, dict):
                context = {}
            return await template_system.render_response(
                template_name, request, context
            )

        return wrapper

    return decorator


# Authentication dependency for protected templates
async def require_authentication(request: Request):
    """Require authentication for template access"""
    if not hasattr(request.state, "user") or request.state.user is None:
        if settings.get("require_authentication", True):
            # Redirect to login page
            from fastapi.responses import RedirectResponse

            return RedirectResponse(url="/auth/login", status_code=302)

    return request.state.user


async def require_admin(request: Request):
    """Require admin role for template access"""
    user = await require_authentication(request)
    if user and getattr(user, "role", "user") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Static file handling
def setup_static_files(app):
    """Setup static file serving for FastAPI"""
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

    # Add CSS and JS file routes for compatibility
    @app.get("/static/css")
    async def css_files():
        """Serve CSS files"""
        css_files = [
            "/static/css/main.css",
            "/static/css/themes.css",
            "/static/css/responsive.css",
        ]
        return {"files": css_files}

    @app.get("/static/js")
    async def js_files():
        """Serve JS files"""
        js_files = [
            "/static/js/main.js",
            "/static/js/core.js",
            "/static/toast.js",
            "/static/loading-feedback.js",
        ]
        return {"files": js_files}


# Template migration utilities
class TemplateMigrationHelper:
    """Helper for migrating Flask templates to FastAPI"""

    @staticmethod
    def find_template_references(template_content: str) -> Dict[str, List[str]]:
        """Find Flask-specific references in templates"""
        import re

        references = {
            "url_for_calls": re.findall(
                r'url_for\([\'"]([^\'"]+)[\'"]', template_content
            ),
            "static_refs": re.findall(r'url_for\([\'"]static[\'"]', template_content),
            "session_refs": re.findall(
                r'session\[?[\'"]?([^\'">\]]*)', template_content
            ),
            "flash_messages": re.findall(r"get_flashed_messages\(\)", template_content),
            "current_user": re.findall(
                r"current_user\.?([a-zA-Z_]*)", template_content
            ),
        }

        return references

    @staticmethod
    def generate_migration_report(
        template_directory: str = "frontend/templates",
    ) -> Dict[str, Any]:
        """Generate migration report for all templates"""
        report = {
            "templates": [],
            "total_templates": 0,
            "migration_complexity": {},
            "common_patterns": {},
        }

        template_path = Path(template_directory)

        for template_file in template_path.rglob("*.html"):
            try:
                with open(template_file, "r", encoding="utf-8") as f:
                    content = f.read()

                references = TemplateMigrationHelper.find_template_references(content)

                template_info = {
                    "file": str(template_file.relative_to(template_path)),
                    "size": len(content),
                    "references": references,
                    "complexity": "low",
                }

                # Assess complexity
                total_refs = sum(len(refs) for refs in references.values())
                if total_refs > 20:
                    template_info["complexity"] = "high"
                elif total_refs > 10:
                    template_info["complexity"] = "medium"

                report["templates"].append(template_info)
                report["total_templates"] += 1

            except Exception as e:
                logger.error(f"Error analyzing template {template_file}: {e}")

        return report
