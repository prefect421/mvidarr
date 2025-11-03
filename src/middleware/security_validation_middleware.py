"""
Advanced Security Validation Middleware - Phase 3 Week 34
Comprehensive input validation, sanitization, and security enforcement for FastAPI
"""

import html
import ipaddress
import json
import re
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.security_validation")


class SecurityValidationConfig:
    """Security validation configuration"""

    # Input size limits
    MAX_JSON_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_URL_LENGTH = 2048
    MAX_HEADER_LENGTH = 8192
    MAX_FIELD_LENGTH = 10000

    # Rate limiting
    MAX_REQUESTS_PER_MINUTE = 60
    MAX_REQUESTS_PER_HOUR = 1000

    # Blocked patterns
    SQL_INJECTION_PATTERNS = [
        r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION)\b",
        r"('|\\')|(--|;|\||\`|=|<|>|\+|\*|%|@|#|\$|\^|&|\(|\)|!|\[|\]|\{|\})",
        r"\b(OR|AND)\s+\d+\s*=\s*\d+",
        r"\b(OR|AND)\s+'\w+'\s*=\s*'\w+'",
        r"\bUNION\s+(ALL\s+)?SELECT\b",
        r"\b(WAITFOR|DELAY)\s+'\d+:\d+:\d+'",
    ]

    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"vbscript:",
        r"data:text/html",
        r"on\w+\s*=",
        r"<iframe[^>]*>.*?</iframe>",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>.*?</embed>",
        r"<form[^>]*>.*?</form>",
    ]

    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$(){}\[\]\\]",
        r"\b(cat|ls|pwd|whoami|id|ps|netstat|ifconfig|ping|curl|wget|nc|ncat|telnet)\b",
        r"(\|\||&&|;|`|\$\(|\$\{)",
        r"(\.\.\/|\.\.\\\\)",
    ]

    # Allowed file extensions
    ALLOWED_IMAGE_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".svg",
    }
    ALLOWED_VIDEO_EXTENSIONS = {
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
    }
    ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}

    # Security headers
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: https:; font-src 'self' https://fonts.gstatic.com https:; connect-src 'self'; frame-ancestors 'none';",
    }


class SecurityValidator:
    """Advanced security validation utilities"""

    def __init__(self, config: SecurityValidationConfig):
        self.config = config
        self.sql_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in config.SQL_INJECTION_PATTERNS
        ]
        self.xss_patterns = [
            re.compile(pattern, re.IGNORECASE | re.DOTALL)
            for pattern in config.XSS_PATTERNS
        ]
        self.cmd_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in config.COMMAND_INJECTION_PATTERNS
        ]

    def validate_input_size(self, data: Any, field_name: str = "input") -> bool:
        """Validate input size limits"""
        if isinstance(data, str):
            if len(data) > self.config.MAX_FIELD_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Field '{field_name}' exceeds maximum length ({self.config.MAX_FIELD_LENGTH} chars)",
                )
        elif isinstance(data, bytes):
            if len(data) > self.config.MAX_JSON_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request body too large (max {self.config.MAX_JSON_SIZE} bytes)",
                )
        return True

    def detect_sql_injection(self, text: str) -> bool:
        """Detect potential SQL injection attempts"""
        if not isinstance(text, str):
            return False

        for pattern in self.sql_patterns:
            if pattern.search(text):
                return True
        return False

    def detect_xss(self, text: str) -> bool:
        """Detect potential XSS attempts"""
        if not isinstance(text, str):
            return False

        for pattern in self.xss_patterns:
            if pattern.search(text):
                return True
        return False

    def detect_command_injection(self, text: str) -> bool:
        """Detect potential command injection attempts"""
        if not isinstance(text, str):
            return False

        for pattern in self.cmd_patterns:
            if pattern.search(text):
                return True
        return False

    def sanitize_string(self, text: str, allow_html: bool = False) -> str:
        """Sanitize string input"""
        if not isinstance(text, str):
            return str(text)

        # HTML escape if HTML not allowed
        if not allow_html:
            text = html.escape(text)

        # Remove null bytes and control characters
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def validate_url(self, url: str) -> bool:
        """Validate URL format and safety"""
        if not isinstance(url, str) or len(url) > self.config.MAX_URL_LENGTH:
            return False

        try:
            parsed = urlparse(url)

            # Must have valid scheme
            if parsed.scheme not in ("http", "https"):
                return False

            # Must have valid netloc
            if not parsed.netloc:
                return False

            # Block private/internal IPs
            try:
                ip = ipaddress.ip_address(parsed.hostname or parsed.netloc)
                if ip.is_private or ip.is_loopback or ip.is_multicast:
                    return False
            except (ValueError, TypeError):
                pass  # Not an IP address, which is fine

            return True

        except Exception:
            return False

    def validate_file_upload(self, filename: str, content_type: str) -> bool:
        """Validate file upload safety"""
        if not filename:
            return False

        # Get file extension
        file_ext = "." + filename.lower().split(".")[-1] if "." in filename else ""

        # Check against allowed extensions
        allowed_extensions = (
            self.config.ALLOWED_IMAGE_EXTENSIONS
            | self.config.ALLOWED_VIDEO_EXTENSIONS
            | self.config.ALLOWED_AUDIO_EXTENSIONS
        )

        if file_ext not in allowed_extensions:
            return False

        # Validate content type matches extension
        valid_content_types = {
            ".jpg": ["image/jpeg"],
            ".jpeg": ["image/jpeg"],
            ".png": ["image/png"],
            ".gif": ["image/gif"],
            ".mp4": ["video/mp4"],
            ".avi": ["video/x-msvideo"],
            ".mkv": ["video/x-matroska"],
            ".mov": ["video/quicktime"],
            ".mp3": ["audio/mpeg"],
            ".wav": ["audio/wav"],
            ".flac": ["audio/flac"],
            ".aac": ["audio/aac"],
        }

        if file_ext in valid_content_types:
            if content_type not in valid_content_types[file_ext]:
                return False

        return True

    def validate_json_structure(
        self, data: Dict[str, Any], max_depth: int = 10
    ) -> bool:
        """Validate JSON structure safety"""

        def check_depth(obj, current_depth=0):
            if current_depth > max_depth:
                return False

            if isinstance(obj, dict):
                if len(obj) > 1000:  # Max 1000 keys
                    return False
                for key, value in obj.items():
                    if not isinstance(key, str) or len(key) > 100:
                        return False
                    if not check_depth(value, current_depth + 1):
                        return False
            elif isinstance(obj, list):
                if len(obj) > 10000:  # Max 10000 items
                    return False
                for item in obj:
                    if not check_depth(item, current_depth + 1):
                        return False

            return True

        return check_depth(data)


class SecurityValidationMiddleware(BaseHTTPMiddleware):
    """Comprehensive security validation middleware"""

    def __init__(self, app, config: Optional[SecurityValidationConfig] = None):
        super().__init__(app)
        self.config = config or SecurityValidationConfig()
        self.validator = SecurityValidator(self.config)
        self.request_counts = {}  # Simple rate limiting cache
        logger.info("🛡️ Security validation middleware initialized")

    async def dispatch(self, request: Request, call_next):
        """Process request with comprehensive security validation"""
        start_time = time.time()

        try:
            # 1. Rate limiting check
            await self._check_rate_limiting(request)

            # 2. Validate request headers
            await self._validate_headers(request)

            # 3. Validate URL and path
            await self._validate_url_path(request)

            # 4. Validate request body if present
            await self._validate_request_body(request)

            # 5. Process request
            response = await call_next(request)

            # 6. Add security headers to response
            self._add_security_headers(response)

            # Log security validation success
            processing_time = time.time() - start_time
            logger.debug(
                f"🛡️ Security validation passed for {request.url.path} in {processing_time:.3f}s"
            )

            return response

        except HTTPException as e:
            # Log security violation
            logger.warning(
                f"🚨 Security validation failed: {e.detail} for {request.client.host}:{request.url.path}"
            )
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail, "security_violation": True},
            )
        except Exception as e:
            logger.error(f"❌ Security middleware error: {e}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal security validation error"},
            )

    async def _check_rate_limiting(self, request: Request):
        """Simple rate limiting implementation"""
        client_ip = request.client.host
        current_time = time.time()
        current_minute = int(current_time // 60)
        current_hour = int(current_time // 3600)

        # Initialize client tracking
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = {
                "minute": {current_minute: 0},
                "hour": {current_hour: 0},
            }

        # Clean old entries
        client_data = self.request_counts[client_ip]
        client_data["minute"] = {
            k: v for k, v in client_data["minute"].items() if k >= current_minute - 1
        }
        client_data["hour"] = {
            k: v for k, v in client_data["hour"].items() if k >= current_hour - 1
        }

        # Check limits
        minute_requests = client_data["minute"].get(current_minute, 0)
        hour_requests = sum(client_data["hour"].values())

        if minute_requests >= self.config.MAX_REQUESTS_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded: too many requests per minute",
            )

        if hour_requests >= self.config.MAX_REQUESTS_PER_HOUR:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded: too many requests per hour",
            )

        # Update counts
        client_data["minute"][current_minute] = minute_requests + 1
        client_data["hour"][current_hour] = client_data["hour"].get(current_hour, 0) + 1

    async def _validate_headers(self, request: Request):
        """Validate request headers"""
        # Standard browser headers that should be exempt from strict validation
        BROWSER_HEADERS = {
            "user-agent",
            "accept",
            "accept-language",
            "accept-encoding",
            "connection",
            "cache-control",
            "upgrade-insecure-requests",
            "sec-fetch-site",
            "sec-fetch-mode",
            "sec-fetch-user",
            "sec-fetch-dest",
            "referer",
            "origin",
            "host",
            "content-type",
            "content-length",
            "priority",  # HTTP/2 priority header
            "sec-ch-ua",
            "sec-ch-ua-mobile",
            "sec-ch-ua-platform",  # Client Hints headers
        }

        # Check header sizes
        for name, value in request.headers.items():
            if len(value) > self.config.MAX_HEADER_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Header '{name}' too large",
                )

            # Skip validation for standard browser headers to avoid false positives
            if name.lower() in BROWSER_HEADERS:
                continue

            # Check for injection attempts in non-standard headers only
            if self.validator.detect_xss(value) or self.validator.detect_sql_injection(
                value
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Malicious content detected in header '{name}'",
                )

    async def _validate_url_path(self, request: Request):
        """Validate URL and path"""
        url_str = str(request.url)
        path = request.url.path

        # Check URL length
        if len(url_str) > self.config.MAX_URL_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_414_REQUEST_URI_TOO_LONG, detail="URL too long"
            )

        # Check for path traversal
        if "../" in path or "..\\" in path or "%2e%2e" in path.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal attempt detected",
            )

        # Check for injection in path and query parameters
        for param_value in request.query_params.values():
            if (
                self.validator.detect_sql_injection(param_value)
                or self.validator.detect_xss(param_value)
                or self.validator.detect_command_injection(param_value)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Malicious content detected in query parameters",
                )

    async def _validate_request_body(self, request: Request):
        """Validate request body content"""
        # Skip validation for certain content types
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            try:
                # Read and parse JSON
                body = await request.body()
                if body:
                    self.validator.validate_input_size(body, "request_body")

                    # Parse JSON
                    json_data = json.loads(body)

                    # Validate JSON structure
                    if not self.validator.validate_json_structure(json_data):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid JSON structure",
                        )

                    # Validate all string values in JSON
                    await self._validate_json_values(json_data)

            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format",
                )

    async def _validate_json_values(self, data: Any, path: str = ""):
        """Recursively validate JSON values"""
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                await self._validate_json_values(value, current_path)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]" if path else f"[{i}]"
                await self._validate_json_values(item, current_path)
        elif isinstance(data, str):
            self.validator.validate_input_size(data, path)

            if (
                self.validator.detect_sql_injection(data)
                or self.validator.detect_xss(data)
                or self.validator.detect_command_injection(data)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Malicious content detected in field '{path}'",
                )

    def _add_security_headers(self, response):
        """Add security headers to response"""
        for header, value in self.config.SECURITY_HEADERS.items():
            response.headers[header] = value

        # Add custom security headers
        response.headers["X-Security-Validated"] = "true"
        response.headers["X-MVidarr-Security"] = "enhanced"
