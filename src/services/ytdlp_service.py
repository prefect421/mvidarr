"""
yt-dlp Service - Redirects to Download Service Adapter

This file now serves as a compatibility layer, redirecting all imports
to the new unified download service architecture.

The actual implementation is in download_service_adapter.py which uses
the unified_download_service for all download operations.

This provides backwards compatibility for existing code that imports
from src.services.ytdlp_service while using the new unified architecture.
"""

# Import the new adapter and make it available as ytdlp_service
from src.services.download_service_adapter import ytdlp_service

# Export for backwards compatibility
__all__ = ["ytdlp_service"]
