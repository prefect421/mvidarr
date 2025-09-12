"""
FastAPI Frontend Router - Issue 130 Template System Migration
Complete frontend route handlers with template integration
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Query, Path
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, Any
import asyncio
import logging

from src.api.fastapi.template_system import (
    template_system, 
    template_routes, 
    require_authentication, 
    require_admin
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.frontend_router")

# Create main frontend router
frontend_router = APIRouter(
    tags=["frontend"],
    responses={404: {"description": "Page not found"}}
)

# =====================================
# Main Application Pages
# =====================================

@frontend_router.get("/", response_class=HTMLResponse, name="frontend_index")
async def index(request: Request):
    """Dashboard/Index page"""
    try:
        return await template_routes.index(request)
    except Exception as e:
        logger.error(f"Error rendering index page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")

@frontend_router.get("/videos", response_class=HTMLResponse, name="frontend_videos")
async def videos(request: Request):
    """Videos management page"""
    try:
        return await template_routes.videos(request)
    except Exception as e:
        logger.error(f"Error rendering videos page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load videos page")

@frontend_router.get("/videos/{video_id}", response_class=HTMLResponse, name="frontend_video_detail")
async def video_detail(request: Request, video_id: int):
    """Video detail page (plural URL)"""
    try:
        context = {
            'video_id': video_id,
            'page_title': 'Video Details'
        }
        return await template_system.render_response('video_detail.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering video detail page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load video detail page")

@frontend_router.get("/video/{video_id}", response_class=HTMLResponse, name="frontend_video_detail_singular")
async def video_detail_singular(request: Request, video_id: int):
    """Video detail page (singular URL)"""
    try:
        context = {
            'video_id': video_id,
            'page_title': 'Video Details'
        }
        return await template_system.render_response('video_detail.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering video detail page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load video detail page")

@frontend_router.get("/artists", response_class=HTMLResponse, name="frontend_artists")
async def artists(request: Request):
    """Artists management page"""
    try:
        return await template_routes.artists(request)
    except Exception as e:
        logger.error(f"Error rendering artists page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load artists page")

@frontend_router.get("/artist/{artist_id}", response_class=HTMLResponse, name="frontend_artist_detail")
async def artist_detail(request: Request, artist_id: int = Path(..., ge=1)):
    """Artist detail page"""
    try:
        return await template_routes.artist_detail(request, artist_id)
    except Exception as e:
        logger.error(f"Error rendering artist detail page for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load artist detail page")

@frontend_router.get("/playlists", response_class=HTMLResponse, name="frontend_playlists")
async def playlists(request: Request):
    """Playlists management page"""
    try:
        return await template_routes.playlists(request)
    except Exception as e:
        logger.error(f"Error rendering playlists page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load playlists page")

@frontend_router.get("/discover", response_class=HTMLResponse, name="frontend_discover")
async def discover(request: Request, q: Optional[str] = Query(None)):
    """Universal search/discover page"""
    try:
        context = {
            'page_title': 'Discover Music Videos',
            'search_query': q or ''
        }
        return await template_system.render_response('discover.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering discover page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load discover page")

@frontend_router.get("/frontend.mvtv", response_class=HTMLResponse, name="frontend_mvtv")
async def mvtv(request: Request):
    """MvTV continuous video player page"""
    try:
        context = {
            'page_title': 'MvTV - Continuous Video Player'
        }
        return await template_system.render_response('mvtv.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering MvTV page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load MvTV page")

@frontend_router.get("/frontend.jobs", response_class=HTMLResponse, name="frontend_jobs")
async def jobs(request: Request):
    """Background Jobs Dashboard"""
    try:
        context = {
            'page_title': 'Background Jobs'
        }
        return await template_system.render_response('jobs.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering jobs page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load jobs page")

@frontend_router.get("/settings", response_class=HTMLResponse, name="frontend_settings")
async def settings(request: Request, user=Depends(require_authentication)):
    """Settings page (authentication required)"""
    try:
        return await template_routes.settings(request)
    except Exception as e:
        logger.error(f"Error rendering settings page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load settings page")

# =====================================
# Authentication Pages
# =====================================

@frontend_router.get("/auth/login", response_class=HTMLResponse, name="auth_login")
async def login_page(request: Request):
    """Login page"""
    try:
        # Temporary simple HTML response to verify route works
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MVidarr Login</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; 
                    margin: 0; 
                    padding: 40px 20px; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    min-height: 100vh;
                    box-sizing: border-box;
                }
                .login-container { 
                    max-width: 400px; 
                    margin: 0 auto; 
                    background: white; 
                    padding: 40px 30px; 
                    border-radius: 12px; 
                    box-shadow: 0 8px 32px rgba(0,0,0,0.1); 
                }
                h1 { 
                    color: #2c3e50; 
                    text-align: center; 
                    margin: 0 0 30px 0; 
                    font-weight: 600;
                    font-size: 28px;
                }
                .form-group { margin-bottom: 20px; }
                label { 
                    display: block; 
                    margin-bottom: 8px; 
                    color: #555; 
                    font-weight: 500;
                    font-size: 14px;
                }
                input { 
                    width: 100%; 
                    padding: 12px 15px; 
                    border: 2px solid #e1e8ed; 
                    border-radius: 8px; 
                    box-sizing: border-box; 
                    font-size: 16px;
                    transition: border-color 0.3s ease;
                }
                input:focus {
                    outline: none;
                    border-color: #667eea;
                    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
                }
                /* Remove IE clear button */
                input::-ms-clear { display: none; width: 0; height: 0; }
                /* Remove webkit autofill styling */
                input:-webkit-autofill,
                input:-webkit-autofill:hover, 
                input:-webkit-autofill:focus {
                    -webkit-text-fill-color: #333;
                    -webkit-box-shadow: 0 0 0px 1000px white inset;
                    transition: background-color 5000s ease-in-out 0s;
                }
                button { 
                    width: 100%; 
                    padding: 14px; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; 
                    border: none; 
                    border-radius: 8px; 
                    cursor: pointer; 
                    font-size: 16px; 
                    font-weight: 600;
                    transition: all 0.3s ease;
                }
                button:hover:not(:disabled) { 
                    transform: translateY(-1px);
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                }
                button:disabled {
                    opacity: 0.7;
                    cursor: not-allowed;
                    transform: none;
                }
                .auth-info { 
                    margin-top: 25px; 
                    padding: 20px; 
                    background: #f8f9fa; 
                    border-radius: 8px; 
                    font-size: 14px; 
                    color: #6c757d; 
                    border-left: 4px solid #28a745;
                }
                .security-warning {
                    margin-top: 15px;
                    padding: 12px;
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    border-radius: 6px;
                    font-size: 13px;
                    color: #856404;
                }
                .security-warning strong {
                    color: #b45309;
                }
            </style>
        </head>
        <body>
            <div class="login-container">
                <h1>MVidarr Login</h1>
                <form id="loginForm">
                    <div class="form-group">
                        <label for="username">Username:</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    <div class="form-group">
                        <label for="password">Password:</label>
                        <input type="password" id="password" name="password" required>
                    </div>
                    <button type="submit">Login</button>
                </form>
                <div id="loginMessage" style="margin-top: 15px; padding: 10px; border-radius: 4px; display: none;"></div>
                <div class="auth-info">
                    <strong>✅ Authentication System Working</strong><br>
                    Browser requests are now properly redirected to this login page.<br>
                    Default credentials: admin / mvidarr
                </div>
                <div class="security-warning">
                    <strong>⚠️ Security Notice:</strong> This page is using HTTP instead of HTTPS. 
                    In production, always use HTTPS to encrypt login credentials during transmission.
                </div>
            </div>
            
            <script>
            document.getElementById('loginForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const username = document.getElementById('username').value;
                const password = document.getElementById('password').value;
                const messageDiv = document.getElementById('loginMessage');
                const submitButton = e.target.querySelector('button[type="submit"]');
                
                // Show loading state
                submitButton.disabled = true;
                submitButton.textContent = 'Logging in...';
                messageDiv.style.display = 'none';
                
                try {
                    // Create abort controller for timeout
                    const abortController = new AbortController();
                    const timeoutId = setTimeout(() => abortController.abort(), 10000); // 10 second timeout
                    
                    const response = await fetch('/test-login', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            username: username,
                            password: password
                        }),
                        signal: abortController.signal
                    });
                    
                    clearTimeout(timeoutId);
                    
                    let data;
                    const contentType = response.headers.get('content-type');
                    
                    if (contentType && contentType.includes('application/json')) {
                        data = await response.json();
                    } else {
                        // Handle non-JSON responses
                        const text = await response.text();
                        console.error('Non-JSON response:', text);
                        throw new Error('Server returned invalid response format');
                    }
                    
                    if (response.ok && data.success) {
                        // Success - redirect to dashboard
                        messageDiv.innerHTML = '✅ Login successful! Redirecting...';
                        messageDiv.style.background = '#d4edda';
                        messageDiv.style.color = '#155724';
                        messageDiv.style.border = '1px solid #c3e6cb';
                        messageDiv.style.display = 'block';
                        
                        setTimeout(() => {
                            window.location.href = '/';
                        }, 1500);
                    } else {
                        // Error
                        messageDiv.innerHTML = '❌ ' + (data.detail || data.message || 'Login failed');
                        messageDiv.style.background = '#f8d7da';
                        messageDiv.style.color = '#721c24';
                        messageDiv.style.border = '1px solid #f5c6cb';
                        messageDiv.style.display = 'block';
                    }
                } catch (error) {
                    console.error('Login error:', error);
                    
                    let errorMessage = 'Login failed';
                    
                    if (error.name === 'AbortError') {
                        errorMessage = 'Request timeout - please try again';
                    } else if (error.message) {
                        errorMessage = error.message;
                    }
                    
                    messageDiv.innerHTML = '❌ ' + errorMessage;
                    messageDiv.style.background = '#f8d7da';
                    messageDiv.style.color = '#721c24';
                    messageDiv.style.border = '1px solid #f5c6cb';
                    messageDiv.style.display = 'block';
                }
                
                // Reset button
                submitButton.disabled = false;
                submitButton.textContent = 'Login';
            });
            </script>
        </body>
        </html>
        """, status_code=200)
    except Exception as e:
        logger.error(f"Error rendering login page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load login page")

@frontend_router.get("/auth/simple-login", response_class=HTMLResponse, name="auth_simple_login")
async def simple_login_page(request: Request):
    """Simple login page"""
    try:
        return await template_routes.simple_login(request)
    except Exception as e:
        logger.error(f"Error rendering simple login page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load simple login page")

@frontend_router.get("/auth/2fa/setup", response_class=HTMLResponse, name="auth_2fa_setup")
async def two_fa_setup_page(request: Request, user=Depends(require_authentication)):
    """Two-factor authentication setup page"""
    try:
        return await template_routes.two_fa_setup(request)
    except Exception as e:
        logger.error(f"Error rendering 2FA setup page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load 2FA setup page")

@frontend_router.get("/auth/2fa/verify", response_class=HTMLResponse, name="auth_2fa_verify")
async def two_fa_verify_page(request: Request):
    """Two-factor authentication verification page"""
    try:
        return await template_routes.two_fa_verify(request)
    except Exception as e:
        logger.error(f"Error rendering 2FA verify page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load 2FA verify page")

@frontend_router.get("/auth/logout", name="auth_logout")
async def logout(request: Request):
    """Logout handler"""
    try:
        # Clear session data
        if hasattr(request.state, 'session'):
            request.state.session.clear()
        
        # Redirect to login page
        return RedirectResponse(url="/auth/login", status_code=302)
        
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        return RedirectResponse(url="/auth/login", status_code=302)

# =====================================
# Admin Pages
# =====================================

@frontend_router.get("/admin", response_class=HTMLResponse, name="admin_dashboard")
async def admin_dashboard(request: Request, user=Depends(require_admin)):
    """Admin dashboard page"""
    try:
        return await template_routes.admin_dashboard(request)
    except Exception as e:
        logger.error(f"Error rendering admin dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to load admin dashboard")

@frontend_router.get("/admin/users", response_class=HTMLResponse, name="admin_users")
async def admin_users(request: Request, user=Depends(require_admin)):
    """Admin user management page"""
    try:
        return await template_routes.admin_users(request)
    except Exception as e:
        logger.error(f"Error rendering admin users page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load admin users page")

@frontend_router.get("/admin/users/create", response_class=HTMLResponse, name="admin_create_user")
async def admin_create_user(request: Request, user=Depends(require_admin)):
    """Admin create user page"""
    try:
        return await template_routes.admin_create_user(request)
    except Exception as e:
        logger.error(f"Error rendering admin create user page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load admin create user page")

@frontend_router.get("/admin/users/{user_id}", response_class=HTMLResponse, name="admin_user_details")
async def admin_user_details(request: Request, user_id: int = Path(...), admin_user=Depends(require_admin)):
    """Admin user details page"""
    try:
        context = {
            'page_title': f'User Details - {user_id}',
            'page_description': f'Manage user {user_id}',
            'user_id': user_id,
            'admin_only': True
        }
        return await template_system.render_response('admin/user_details.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering admin user details page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load user details page")

# =====================================
# Component and Modal Endpoints
# =====================================

@frontend_router.get("/components/add-video-modal", response_class=HTMLResponse, name="component_add_video_modal")
async def add_video_modal_component(request: Request):
    """Add video modal component"""
    try:
        context = {
            'modal_only': True,
            'component_name': 'add_video_modal'
        }
        return await template_system.render_response('components/add_video_modal.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering add video modal: {e}")
        raise HTTPException(status_code=500, detail="Failed to load add video modal")

@frontend_router.get("/components/job-dashboard-modal", response_class=HTMLResponse, name="component_job_dashboard_modal")
async def job_dashboard_modal_component(request: Request):
    """Job dashboard modal component"""
    try:
        context = {
            'modal_only': True,
            'component_name': 'job_dashboard_modal'
        }
        return await template_system.render_response('components/job_dashboard_modal.html', request, context)
    except Exception as e:
        logger.error(f"Error rendering job dashboard modal: {e}")
        raise HTTPException(status_code=500, detail="Failed to load job dashboard modal")

# =====================================
# API Proxy Endpoints for Template Compatibility
# =====================================

@frontend_router.get("/api/search", name="frontend_search")
async def frontend_search(request: Request, q: Optional[str] = Query(None)):
    """Frontend search endpoint for universal search"""
    try:
        if not q:
            return {"results": [], "total": 0}
        
        # TODO: Implement actual search logic
        # This would integrate with the search API endpoints
        from src.api.fastapi.search import search_all
        results = await search_all(q)
        
        return results
    except Exception as e:
        logger.error(f"Frontend search error: {e}")
        return {"results": [], "total": 0, "error": str(e)}

@frontend_router.get("/api/navigation", name="frontend_navigation")
async def frontend_navigation(request: Request):
    """Get navigation structure for frontend"""
    try:
        navigation = {
            'main': [
                {'name': 'Dashboard', 'url': '/', 'icon': 'mdi:view-dashboard', 'active': False},
                {'name': 'Videos', 'url': '/videos', 'icon': 'mdi:video', 'active': False},
                {'name': 'Artists', 'url': '/artists', 'icon': 'mdi:account-music', 'active': False},
                {'name': 'Playlists', 'url': '/playlists', 'icon': 'mdi:playlist-play', 'active': False}
            ],
            'admin': [
                {'name': 'Dashboard', 'url': '/admin', 'icon': 'mdi:shield-account', 'active': False},
                {'name': 'Users', 'url': '/admin/users', 'icon': 'mdi:account-multiple', 'active': False}
            ],
            'settings': [
                {'name': 'Settings', 'url': '/settings', 'icon': 'mdi:cog', 'active': False}
            ]
        }
        
        # Mark current page as active
        current_path = request.url.path
        for section in navigation.values():
            for item in section:
                if item['url'] == current_path:
                    item['active'] = True
        
        return navigation
    except Exception as e:
        logger.error(f"Navigation endpoint error: {e}")
        return {'main': [], 'admin': [], 'settings': []}

# =====================================
# Health Check and Status Endpoints
# =====================================

@frontend_router.get("/health", name="frontend_health")
async def frontend_health():
    """Frontend health check"""
    try:
        # Check template system
        template_status = template_system is not None
        
        # Check static files
        import os
        static_status = os.path.exists("frontend/static")
        templates_status = os.path.exists("frontend/templates")
        
        return {
            "status": "healthy" if all([template_status, static_status, templates_status]) else "degraded",
            "template_system": template_status,
            "static_files": static_status,
            "templates": templates_status,
            "timestamp": "2025-01-08T00:00:00Z"
        }
    except Exception as e:
        logger.error(f"Frontend health check error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": "2025-01-08T00:00:00Z"
        }

@frontend_router.get("/manifest.json", name="frontend_manifest")
async def web_app_manifest():
    """Web app manifest for PWA support"""
    return {
        "name": "MVidarr",
        "short_name": "MVidarr",
        "description": "Media Management Application",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1a1a1a",
        "theme_color": "#6366f1",
        "icons": [
            {
                "src": "/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }

# =====================================
# Error Handlers
# =====================================

async def not_found_handler(request: Request, exc):
    """Custom 404 handler"""
    try:
        context = {
            'page_title': 'Page Not Found',
            'page_description': 'The requested page could not be found',
            'error_code': 404,
            'error_message': 'Page Not Found',
            'back_url': '/'
        }
        return await template_system.render_response('errors/404.html', request, context)
    except Exception as e:
        logger.error(f"Error in 404 handler: {e}")
        return HTMLResponse(
            content="""
            <html>
                <head><title>404 - Page Not Found</title></head>
                <body>
                    <h1>404 - Page Not Found</h1>
                    <p>The requested page could not be found.</p>
                    <a href="/">Return to Dashboard</a>
                </body>
            </html>
            """,
            status_code=404
        )

async def internal_server_error_handler(request: Request, exc):
    """Custom 500 handler"""
    try:
        context = {
            'page_title': 'Server Error',
            'page_description': 'An internal server error occurred',
            'error_code': 500,
            'error_message': 'Internal Server Error',
            'back_url': '/'
        }
        return await template_system.render_response('errors/500.html', request, context)
    except Exception as e:
        logger.error(f"Error in 500 handler: {e}")
        return HTMLResponse(
            content="""
            <html>
                <head><title>500 - Server Error</title></head>
                <body>
                    <h1>500 - Internal Server Error</h1>
                    <p>An error occurred while processing your request.</p>
                    <a href="/">Return to Dashboard</a>
                </body>
            </html>
            """,
            status_code=500
        )

# =====================================
# Template Development Helpers
# =====================================

@frontend_router.get("/dev/template-info", name="dev_template_info")
async def template_development_info(request: Request):
    """Development endpoint for template information"""
    try:
        from src.api.fastapi.template_system import TemplateMigrationHelper
        
        migration_report = TemplateMigrationHelper.generate_migration_report()
        
        return {
            "template_system": "FastAPI Jinja2 with async support",
            "migration_report": migration_report,
            "context_processors": len(template_system.context_processors),
            "registered_filters": list(template_system.env.filters.keys()),
            "registered_globals": list(template_system.env.globals.keys())
        }
    except Exception as e:
        logger.error(f"Template dev info error: {e}")
        return {"error": str(e)}

@frontend_router.get("/dev/context-preview", name="dev_context_preview")
async def template_context_preview(request: Request):
    """Development endpoint to preview template context"""
    try:
        context = await template_system.get_template_context(request)
        
        # Remove complex objects for JSON serialization
        preview_context = {}
        for key, value in context.items():
            try:
                if isinstance(value, (str, int, float, bool, list, dict)):
                    preview_context[key] = value
                elif hasattr(value, '__dict__'):
                    preview_context[key] = f"<{type(value).__name__} object>"
                else:
                    preview_context[key] = str(type(value))
            except:
                preview_context[key] = "<unable to serialize>"
        
        return preview_context
    except Exception as e:
        logger.error(f"Context preview error: {e}")
        return {"error": str(e)}

# Function to get the router
def get_frontend_router() -> APIRouter:
    """Get the frontend router for app integration"""
    return frontend_router