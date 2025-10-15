"""
IMVDb API service for fetching music video metadata

This is the aggregator module that combines all IMVDb modules into a single interface.
Provides backward compatibility with the original monolithic service.
"""

from typing import Dict, List, Optional

from src.services.imvdb.imvdb_metadata import extract_artist_name, extract_metadata
from src.services.imvdb.imvdb_quality import IMVDbQuality
from src.utils.logger import get_logger

logger = get_logger("mvidarr.imvdb_service")


class IMVDbService(IMVDbQuality):
    """
    Service for interacting with the IMVDb API

    This class aggregates functionality from:
    - IMVDbClient: Core HTTP client and authentication
    - IMVDbSearch: Video and artist search operations
    - IMVDbQuality: Quality analysis and advanced filtering
    - imvdb_metadata: Metadata extraction utilities
    """

    def __init__(self):
        super().__init__()
        logger.debug("IMVDb service initialized with modular architecture")

    def extract_metadata(self, video_data: Dict) -> Dict:
        """
        Extract and standardize metadata from IMVDb video data

        Args:
            video_data: Raw IMVDb video data

        Returns:
            Standardized metadata dictionary
        """
        return extract_metadata(video_data)

    def _extract_artist_name(self, artist_data: Dict) -> Optional[str]:
        """
        Extract artist name from IMVDb data structure, handling nested formats

        Args:
            artist_data: Raw artist data from IMVDb API

        Returns:
            Artist name string or None
        """
        return extract_artist_name(artist_data)


# Convenience instance
imvdb_service = IMVDbService()
