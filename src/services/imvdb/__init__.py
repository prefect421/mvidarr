"""
IMVDb service package - Modular music video metadata API client
"""

from src.services.imvdb.imvdb_client import IMVDbClient
from src.services.imvdb.imvdb_metadata import extract_artist_name, extract_metadata
from src.services.imvdb.imvdb_quality import IMVDbQuality
from src.services.imvdb.imvdb_search import IMVDbSearch

__all__ = [
    "IMVDbClient",
    "IMVDbSearch",
    "IMVDbQuality",
    "extract_artist_name",
    "extract_metadata",
]
