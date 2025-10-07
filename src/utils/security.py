"""
Security utilities for input validation, sanitization, and protection
"""

import hashlib
import html
import os
import re
import secrets

# Optional import for bleach
try:
    import bleach

    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
from functools import wraps
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from flask import current_app, jsonify, redirect, request, url_for

# Handle different versions of werkzeug
try:
    from werkzeug.security import safe_str_cmp
except ImportError:
    # For newer versions of werkzeug
    import hmac

    def safe_str_cmp(a, b):
        return hmac.compare_digest(a, b)


import time
from collections import defaultdict

# Rate limiting storage
_rate_limit_storage = defaultdict(list)


class InputValidator:
    """Comprehensive input validation and sanitization"""

    # Allowed HTML tags for rich text content (very restrictive)
    ALLOWED_HTML_TAGS = ["b", "i", "em", "strong", "u"]
    ALLOWED_HTML_ATTRIBUTES = {}

    # Common dangerous patterns
    DANGEROUS_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # Script tags
        r"javascript:",  # JavaScript URLs
        r"vbscript:",  # VBScript URLs
        r"onload\s*=",  # Event handlers
        r"onclick\s*=",
        r"onerror\s*=",
        r"eval\s*\(",  # Code evaluation
        r"exec\s*\(",
        r"system\s*\(",  # System calls
        r"shell_exec\s*\(",
        r"\.\./|\.\.\|",  # Path traversal
        r"union\s+select",  # SQL injection
        r"drop\s+table",
        r"delete\s+from",
        r"insert\s+into",
    ]

    @staticmethod
    def sanitize_string(
        value: str, max_length: int = 1000, allow_html: bool = False
    ) -> str:
        """
        Sanitize string input with configurable options

        Args:
            value: Input string to sanitize
            max_length: Maximum allowed length
            allow_html: Whether to allow safe HTML tags

        Returns:
            Sanitized string
        """
        if not isinstance(value, str):
            value = str(value)

        # Truncate to max length
        if len(value) > max_length:
            value = value[:max_length]

        # Remove or escape dangerous patterns
        for pattern in InputValidator.DANGEROUS_PATTERNS:
            value = re.sub(pattern, "", value, flags=re.IGNORECASE)

        if allow_html and BLEACH_AVAILABLE:
            # Use bleach to clean HTML while preserving safe tags
            value = bleach.clean(
                value,
                tags=InputValidator.ALLOWED_HTML_TAGS,
                attributes=InputValidator.ALLOWED_HTML_ATTRIBUTES,
                strip=True,
            )
        else:
            # Escape all HTML (fallback if bleach not available)
            value = html.escape(value)

        # Normalize whitespace
        value = re.sub(r"\s+", " ", value).strip()

        return value

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email)) and len(email) <= 254

    @staticmethod
    def validate_url(url: str, allowed_schemes: List[str] = None) -> bool:
        """
        Validate URL format and scheme

        Args:
            url: URL to validate
            allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])
        """
        if allowed_schemes is None:
            allowed_schemes = ["http", "https"]

        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in allowed_schemes
                and bool(parsed.netloc)
                and len(url) <= 2048
            )
        except Exception:
            return False

    @staticmethod
    def validate_integer(
        value: Any, min_val: int = None, max_val: int = None
    ) -> Optional[int]:
        """
        Validate and convert to integer with optional bounds

        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value

        Returns:
            Validated integer or None if invalid
        """
        try:
            int_val = int(value)

            if min_val is not None and int_val < min_val:
                return None
            if max_val is not None and int_val > max_val:
                return None

            return int_val
        except (ValueError, TypeError):
            return None

    @staticmethod
    def validate_filename(filename: str) -> str:
        """
        Sanitize filename for safe file system operations

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed_file"

        # Remove path components
        filename = os.path.basename(filename)

        # Remove dangerous characters
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

        # Remove control characters
        filename = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", filename)

        # Ensure not too long
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[: 255 - len(ext)] + ext

        # Ensure not empty after sanitization
        if not filename or filename.isspace():
            filename = "sanitized_file"

        return filename

    @staticmethod
    def validate_json_payload(
        data: Dict, required_fields: List[str] = None, max_size: int = 1024 * 1024
    ) -> tuple[bool, str]:
        """
        Validate JSON payload structure and content

        Args:
            data: JSON data to validate
            required_fields: List of required field names
            max_size: Maximum payload size in bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(data, dict):
            return False, "Payload must be a JSON object"

        # Check payload size (approximate)
        import json

        try:
            payload_size = len(json.dumps(data).encode("utf-8"))
            if payload_size > max_size:
                return (
                    False,
                    f"Payload too large: {payload_size} bytes (max: {max_size})",
                )
        except Exception:
            return False, "Invalid JSON structure"

        # Check required fields
        if required_fields:
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return False, f"Missing required fields: {', '.join(missing_fields)}"

        return True, ""


class PasswordValidator:
    """Comprehensive password validation with configurable complexity requirements"""

    @staticmethod
    def validate_password_strength(
        password: str, min_length: int = 8
    ) -> tuple[bool, List[str]]:
        """
        Validate password strength with comprehensive requirements

        Args:
            password: Password to validate
            min_length: Minimum password length (default: 8)

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []

        if not password:
            errors.append("Password is required")
            return False, errors

        # Length requirement
        if len(password) < min_length:
            errors.append(f"Password must be at least {min_length} characters long")

        # Maximum length to prevent DoS
        if len(password) > 128:
            errors.append("Password must be no more than 128 characters long")

        # Character complexity requirements
        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

        if not has_lower:
            errors.append("Password must contain at least one lowercase letter")

        if not has_upper:
            errors.append("Password must contain at least one uppercase letter")

        if not has_digit:
            errors.append("Password must contain at least one number")

        if not has_special:
            errors.append(
                "Password must contain at least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)"
            )

        # Common weak password patterns
        weak_patterns = [
            "password",
            "123456",
            "qwerty",
            "admin",
            "login",
            "user",
            "test",
            "guest",
            "root",
            "pass",
            "1234",
        ]

        password_lower = password.lower()
        for pattern in weak_patterns:
            if pattern in password_lower:
                errors.append(
                    f"Password must not contain common weak patterns like '{pattern}'"
                )
                break

        # Sequential characters check
        if len(password) >= 3:
            for i in range(len(password) - 2):
                # Check for ascending sequences (abc, 123)
                if ord(password[i]) + 1 == ord(password[i + 1]) and ord(
                    password[i + 1]
                ) + 1 == ord(password[i + 2]):
                    errors.append(
                        "Password must not contain sequential characters (e.g., abc, 123)"
                    )
                    break

                # Check for descending sequences (cba, 321)
                if ord(password[i]) - 1 == ord(password[i + 1]) and ord(
                    password[i + 1]
                ) - 1 == ord(password[i + 2]):
                    errors.append(
                        "Password must not contain sequential characters (e.g., cba, 321)"
                    )
                    break

        # Repeated characters check
        if len(set(password)) < len(password) / 2:
            errors.append("Password must not have too many repeated characters")

        return len(errors) == 0, errors

    @staticmethod
    def get_password_strength_score(password: str) -> tuple[int, str]:
        """
        Calculate password strength score (0-100) and description

        Args:
            password: Password to evaluate

        Returns:
            Tuple of (score, description)
        """
        if not password:
            return 0, "No password"

        score = 0

        # Length scoring (up to 25 points)
        length_score = min(25, len(password) * 2)
        score += length_score

        # Character variety (up to 40 points)
        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

        char_types = sum([has_lower, has_upper, has_digit, has_special])
        score += char_types * 10

        # Uniqueness (up to 20 points)
        unique_chars = len(set(password))
        uniqueness_ratio = unique_chars / len(password) if password else 0
        score += int(uniqueness_ratio * 20)

        # Pattern penalties (up to -15 points)
        weak_patterns = ["password", "123456", "qwerty", "admin", "test"]
        password_lower = password.lower()
        for pattern in weak_patterns:
            if pattern in password_lower:
                score -= 15
                break

        # Sequential penalties (up to -10 points)
        if len(password) >= 3:
            for i in range(len(password) - 2):
                if ord(password[i]) + 1 == ord(password[i + 1]) and ord(
                    password[i + 1]
                ) + 1 == ord(password[i + 2]):
                    score -= 10
                    break

        # Ensure score is within bounds
        score = max(0, min(100, score))

        # Determine description
        if score >= 80:
            description = "Very Strong"
        elif score >= 60:
            description = "Strong"
        elif score >= 40:
            description = "Moderate"
        elif score >= 20:
            description = "Weak"
        else:
            description = "Very Weak"

        return score, description


class SecurityHeaders:
    """Security headers management"""

    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """Get recommended security headers with dynamic SSL/TLS configuration"""
        headers = {
            # Prevent XSS attacks
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            # Content Security Policy
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://code.iconify.design https://cdn.socket.io; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com http://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "media-src 'self' blob:; "
                "connect-src 'self' https://api.iconify.design https://api.simplesvg.com https://api.unisvg.com ws: wss:; "
                "font-src 'self' https://fonts.gstatic.com http://fonts.gstatic.com; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            ),
            # Referrer policy
            "Referrer-Policy": "strict-origin-when-cross-origin",
            # Feature policy
            "Permissions-Policy": (
                "geolocation=(), "
                "microphone=(), "
                "camera=(), "
                "payment=(), "
                "usb=(), "
                "magnetometer=(), "
                "accelerometer=(), "
                "gyroscope=()"
            ),
        }

        # Add HSTS header only if SSL enforcement is enabled
        try:
            from src.services.settings_service import SettingsService

            hsts_enabled = SettingsService.get_bool("ssl_hsts_enabled", False)
            ssl_required = SettingsService.get_bool("ssl_required", False)

            if hsts_enabled and ssl_required:
                max_age = SettingsService.get("ssl_hsts_max_age", "31536000")
                headers["Strict-Transport-Security"] = (
                    f"max-age={max_age}; includeSubDomains"
                )

        except Exception:
            # Fallback to default HSTS if settings not available
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return headers


class RateLimiter:
    """Simple rate limiting implementation"""

    @staticmethod
    def is_rate_limited(
        identifier: str, max_requests: int = 100, window_seconds: int = 3600
    ) -> bool:
        """
        Check if identifier is rate limited

        Args:
            identifier: Unique identifier (IP, user ID, etc.)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            True if rate limited, False otherwise
        """
        current_time = time.time()
        window_start = current_time - window_seconds

        # Clean old entries
        _rate_limit_storage[identifier] = [
            timestamp
            for timestamp in _rate_limit_storage[identifier]
            if timestamp > window_start
        ]

        # Check if limit exceeded
        if len(_rate_limit_storage[identifier]) >= max_requests:
            return True

        # Add current request
        _rate_limit_storage[identifier].append(current_time)
        return False


def require_rate_limit(max_requests: int = 100, window_seconds: int = 3600):
    """
    Decorator to apply rate limiting to Flask routes

    Args:
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Use IP address as identifier
            identifier = request.environ.get(
                "HTTP_X_FORWARDED_FOR", request.remote_addr
            )

            if RateLimiter.is_rate_limited(identifier, max_requests, window_seconds):
                return (
                    jsonify(
                        {
                            "error": "Rate limit exceeded",
                            "message": f"Maximum {max_requests} requests per {window_seconds} seconds",
                        }
                    ),
                    429,
                )

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def validate_request_data(
    required_fields: List[str] = None, max_payload_size: int = 1024 * 1024
):
    """
    Decorator to validate request data

    Args:
        required_fields: List of required field names
        max_payload_size: Maximum payload size in bytes
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                data = request.get_json()
                if data is None:
                    return jsonify({"error": "Invalid JSON payload"}), 400

                # Validate payload
                is_valid, error_msg = InputValidator.validate_json_payload(
                    data, required_fields, max_payload_size
                )

                if not is_valid:
                    return jsonify({"error": error_msg}), 400

                return f(*args, **kwargs)
            except Exception as e:
                return jsonify({"error": "Request validation failed"}), 400

        return decorated_function

    return decorator


class SecureConfig:
    """Secure configuration management"""

    @staticmethod
    def generate_secret_key(length: int = 32) -> str:
        """Generate a secure random secret key"""
        return secrets.token_hex(length)

    @staticmethod
    def hash_sensitive_data(data: str, salt: str = None) -> tuple[str, str]:
        """
        Hash sensitive data with salt

        Args:
            data: Data to hash
            salt: Optional salt (will generate if not provided)

        Returns:
            Tuple of (hash, salt)
        """
        if salt is None:
            salt = secrets.token_hex(16)

        # Use PBKDF2 for password-like data
        hash_obj = hashlib.pbkdf2_hmac(
            "sha256", data.encode("utf-8"), salt.encode("utf-8"), 100000
        )
        return hash_obj.hex(), salt

    @staticmethod
    def verify_hash(data: str, hash_value: str, salt: str) -> bool:
        """Verify hashed data"""
        computed_hash, _ = SecureConfig.hash_sensitive_data(data, salt)
        return safe_str_cmp(computed_hash, hash_value)


def apply_security_headers(response):
    """Apply security headers to Flask response"""
    headers = SecurityHeaders.get_security_headers()
    for header, value in headers.items():
        response.headers[header] = value
    return response


def safe_redirect(
    url: str, default_endpoint: str = "/", allowed_hosts: List[str] = None
):
    """
    Safely redirect to a URL, preventing open redirect vulnerabilities

    Args:
        url: The URL to redirect to
        default_endpoint: Default endpoint if URL is invalid
        allowed_hosts: List of allowed hostnames (defaults to current app's host)

    Returns:
        Flask redirect response to a safe URL
    """
    if not url:
        return redirect(default_endpoint)

    try:
        parsed = urlparse(url)

        # If it's a relative URL (no scheme or netloc), it's safe
        if not parsed.scheme and not parsed.netloc:
            # Ensure it starts with / to prevent protocol-relative URLs
            if not url.startswith("/"):
                url = "/" + url
            return redirect(url)

        # For absolute URLs, validate the host
        if allowed_hosts is None:
            # Default to current request host if available
            try:
                current_host = request.host
                allowed_hosts = [current_host]
            except RuntimeError:
                # Outside request context, be restrictive
                allowed_hosts = ["localhost", "127.0.0.1"]

        # Check if the host is in the allowed list
        if parsed.netloc.lower() in [host.lower() for host in allowed_hosts]:
            return redirect(url)

        # If host is not allowed, redirect to default
        return redirect(default_endpoint)

    except Exception:
        # If URL parsing fails, redirect to default
        return redirect(default_endpoint)
