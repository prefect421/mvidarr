"""
First-Run Detection Middleware for Installation Wizard
v1.0.0 Feature: Redirect to wizard if not completed
Issue #163: https://github.com/prefect421/mvidarr/issues/163
"""

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.database.connection import get_db
from src.database.models import WizardState, WizardStatus

logger = logging.getLogger("mvidarr.wizard_middleware")


class FirstRunDetectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to detect first-run and redirect to installation wizard.

    This middleware checks if the installation wizard has been completed.
    If not completed, it redirects users to the wizard, except for:
    - Wizard API endpoints (/api/wizard/*)
    - Static assets (/static/*)
    - Health checks (/health, /api/health)
    - OpenAPI docs (/docs, /redoc, /openapi.json)
    """

    # Paths that are always allowed (bypass wizard check)
    ALLOWED_PATHS = [
        "/api/wizard",  # All wizard endpoints
        "/static",  # Static assets
        "/health",  # Health check
        "/api/health",  # Health check API
        "/docs",  # OpenAPI docs
        "/redoc",  # ReDoc docs
        "/openapi.json",  # OpenAPI schema
    ]

    def __init__(self, app, wizard_redirect_url: str = "/wizard"):
        """
        Initialize middleware.

        Args:
            app: FastAPI application
            wizard_redirect_url: URL to redirect to if wizard not completed
        """
        super().__init__(app)
        self.wizard_redirect_url = wizard_redirect_url

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and check wizard completion status.

        Args:
            request: Incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response (may be redirect if wizard not completed)
        """
        # Check if path is allowed (bypass wizard check)
        if self._is_allowed_path(request.url.path):
            return await call_next(request)

        # Check wizard completion status
        wizard_completed = await self._check_wizard_completed()

        if not wizard_completed:
            # Wizard not completed - redirect based on request type
            if self._is_api_request(request.url.path):
                # API requests get JSON response
                return JSONResponse(
                    status_code=503,  # Service Unavailable
                    content={
                        "error": "First-run setup required",
                        "message": "Please complete the installation wizard at /wizard",
                        "wizard_url": self.wizard_redirect_url,
                    },
                )
            else:
                # Web requests get redirect
                return RedirectResponse(url=self.wizard_redirect_url, status_code=307)

        # Wizard completed - proceed normally
        return await call_next(request)

    def _is_allowed_path(self, path: str) -> bool:
        """
        Check if path is allowed without wizard completion.

        Args:
            path: Request path to check

        Returns:
            True if path is allowed, False otherwise
        """
        return any(path.startswith(allowed) for allowed in self.ALLOWED_PATHS)

    def _is_api_request(self, path: str) -> bool:
        """
        Check if request is an API request.

        Args:
            path: Request path to check

        Returns:
            True if API request, False otherwise
        """
        return path.startswith("/api/")

    async def _check_wizard_completed(self) -> bool:
        """
        Check if installation wizard has been completed.

        Returns:
            True if wizard completed or skipped, False otherwise
        """
        try:
            # Get database session
            db = next(get_db())

            try:
                # Query wizard state
                wizard_state = db.query(WizardState).first()

                if not wizard_state:
                    # No wizard state exists - wizard not started/completed
                    logger.debug("No wizard state found - wizard not completed")
                    return False

                # Check if wizard is completed or skipped
                is_completed = wizard_state.status in [
                    WizardStatus.COMPLETED,
                    WizardStatus.SKIPPED,
                ]

                logger.debug(
                    f"Wizard status: {wizard_state.status.value}, completed: {is_completed}"
                )
                return is_completed

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error checking wizard status: {str(e)}")
            # On error, assume wizard not completed to be safe
            # This prevents potential security issues if database is down
            return False


def setup_wizard_middleware(app, wizard_redirect_url: str = "/wizard"):
    """
    Set up first-run detection middleware on FastAPI app.

    Args:
        app: FastAPI application
        wizard_redirect_url: URL to redirect to if wizard not completed

    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> setup_wizard_middleware(app)
    """
    app.add_middleware(
        FirstRunDetectionMiddleware, wizard_redirect_url=wizard_redirect_url
    )
    logger.info(
        f"✅ First-run detection middleware enabled (redirect: {wizard_redirect_url})"
    )


def disable_wizard_middleware():
    """
    Utility function to disable wizard middleware.

    This is useful for:
    - Development/testing
    - Maintenance mode
    - Manual database recovery

    Note: This function returns a boolean that can be used
    to conditionally set up the middleware.
    """
    import os

    # Check environment variable to disable middleware
    return os.getenv("DISABLE_WIZARD_MIDDLEWARE", "false").lower() == "true"
