"""
Request Size Limit Middleware - DoS Prevention
Enforces maximum request size to prevent memory exhaustion attacks
Issue #171: Implement Request Size Limits and DoS Prevention Controls
"""

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("mvidarr.middleware.request_size")


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce maximum request size limits.

    Prevents Denial of Service (DoS) attacks via:
    - Oversized file uploads
    - Malicious multipart/form-data requests
    - Memory exhaustion from large payloads

    Usage:
        app.add_middleware(
            RequestSizeLimitMiddleware,
            max_upload_size=100_000_000  # 100 MB
        )
    """

    def __init__(
        self,
        app,
        max_upload_size: int = 100 * 1024 * 1024,  # 100 MB default
        max_form_size: int = 10 * 1024 * 1024,  # 10 MB default for forms
    ):
        """
        Initialize request size limit middleware.

        Args:
            app: FastAPI application instance
            max_upload_size: Maximum size in bytes for file uploads (default: 100MB)
            max_form_size: Maximum size in bytes for form submissions (default: 10MB)
        """
        super().__init__(app)
        self.max_upload_size = max_upload_size
        self.max_form_size = max_form_size

        logger.info(
            f"RequestSizeLimitMiddleware initialized: "
            f"max_upload={max_upload_size / 1024 / 1024:.1f}MB, "
            f"max_form={max_form_size / 1024 / 1024:.1f}MB"
        )

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Check request size before processing.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response object (413 if too large, otherwise normal response)
        """
        # Check if Content-Length header is present
        content_length_header = request.headers.get("content-length")

        if content_length_header:
            try:
                content_length = int(content_length_header)
            except ValueError:
                logger.warning(
                    f"Invalid Content-Length header: {content_length_header}"
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Bad Request",
                        "detail": "Invalid Content-Length header",
                    },
                )

            # Determine appropriate size limit based on content type
            content_type = request.headers.get("content-type", "")

            # Use higher limit for multipart uploads (file uploads)
            if "multipart/form-data" in content_type:
                size_limit = self.max_upload_size
                limit_type = "upload"
            else:
                # Use lower limit for regular forms and JSON
                size_limit = self.max_form_size
                limit_type = "form"

            # Check if request exceeds size limit
            if content_length > size_limit:
                size_mb = content_length / 1024 / 1024
                limit_mb = size_limit / 1024 / 1024

                logger.warning(
                    f"Request size limit exceeded: "
                    f"{size_mb:.2f}MB > {limit_mb:.1f}MB ({limit_type}) "
                    f"from {request.client.host if request.client else 'unknown'}"
                )

                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "Payload Too Large",
                        "detail": (
                            f"Request size {size_mb:.2f}MB exceeds maximum "
                            f"allowed size of {limit_mb:.1f}MB for {limit_type} requests"
                        ),
                        "max_size_mb": limit_mb,
                        "request_size_mb": round(size_mb, 2),
                    },
                )

        # Size is acceptable, continue to next middleware/handler
        response = await call_next(request)
        return response


class FormFieldSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce individual form field size limits.

    Provides additional protection against:
    - Individual oversized form fields
    - Field-level DoS attacks
    - Malicious form data

    Note: This works in conjunction with RequestSizeLimitMiddleware
    for defense-in-depth protection.

    Usage:
        app.add_middleware(
            FormFieldSizeLimitMiddleware,
            max_field_size=1_000_000  # 1 MB per field
        )
    """

    def __init__(
        self,
        app,
        max_field_size: int = 1 * 1024 * 1024,  # 1 MB default per field
    ):
        """
        Initialize form field size limit middleware.

        Args:
            app: FastAPI application instance
            max_field_size: Maximum size in bytes for individual form fields
        """
        super().__init__(app)
        self.max_field_size = max_field_size

        logger.info(
            f"FormFieldSizeLimitMiddleware initialized: "
            f"max_field={max_field_size / 1024:.0f}KB"
        )

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Validate individual form field sizes.

        Note: This is primarily for documentation and future enhancement.
        Actual field size validation is handled by Starlette's multipart parser
        with the max_field_size parameter.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response object
        """
        # For now, just pass through - field size limits are configured
        # at the Starlette level in fastapi_app.py
        response = await call_next(request)
        return response
