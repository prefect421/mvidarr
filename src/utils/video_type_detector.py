"""
Video Type Detection Utility
Detects video type classification from titles and metadata

Issue #191: Per-artist video type filtering
"""

import re
from typing import Optional


class VideoTypeDetector:
    """Utility class to detect video types from titles and metadata"""

    # Video type classification keywords (order matters - more specific first)
    TYPE_KEYWORDS = {
        "lyric_video": [
            "lyric video",
            "lyrics",
            "lyric",
            "letra",
            "paroles",
            "with lyrics",
            "w/ lyrics",
            "official lyrics",
        ],
        "live_performance": [
            "live performance",
            "live at",
            "live from",
            "live in",
            "live on",
            "live session",
            "live",
            "concert",
            "tour",
            "festival",
            "unplugged",
        ],
        "acoustic_version": [
            "acoustic version",
            "acoustic",
            "stripped",
            "unplugged",
        ],
        "remix_version": [
            "remix",
            "remixed",
            "mix",
            " edit",  # Space before to avoid matching words like "edited"
            "version",
            "bootleg",
            "mashup",
        ],
        "cover_version": [
            "cover",
            "covers",
            "tribute",
            "karaoke",
            "instrumental",
        ],
        "music_documentary": [
            "documentary",
            "behind the scenes",
            "making of",
            "the making",
            "bts",
        ],
        "concert_footage": [
            "concert footage",
            "live concert",
            "full concert",
            "concert",
        ],
        "official_music_video": [
            "official video",
            "official music video",
            "official mv",
            "official",
            "music video",
            "video oficial",
            "videoclip",
            "video clip",
            "mv",
        ],
    }

    @classmethod
    def detect_from_title(cls, title: str, description: str = "") -> Optional[str]:
        """
        Detect video type from title and description

        Args:
            title: Video title
            description: Video description (optional)

        Returns:
            Video type string (e.g., 'lyric_video', 'official_music_video') or None
        """
        if not title:
            return None

        # Combine title and description for better detection
        search_text = f"{title} {description}".lower()

        # Check for each type in priority order
        for video_type, keywords in cls.TYPE_KEYWORDS.items():
            for keyword in keywords:
                # Use word boundary matching for better accuracy
                pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
                if re.search(pattern, search_text):
                    return video_type

        # Default: If no specific type detected but has "official" or "music video"
        # keywords, classify as official_music_video
        if any(
            keyword in search_text
            for keyword in ["official", "music video", "mv", "videoclip"]
        ):
            return "official_music_video"

        # If no classification found, return None (unknown/other)
        return None

    # Channel name patterns that indicate official artist channels
    OFFICIAL_CHANNEL_PATTERNS = [
        "vevo",
        "official",
        " - topic",  # YouTube auto-generated topic channels
    ]

    @classmethod
    def detect_from_metadata(cls, video_data: dict) -> Optional[str]:
        """
        Detect video type from video metadata dictionary

        Uses multiple signals: title, description, tags, channel name, and
        contextual clues to improve classification accuracy.

        Args:
            video_data: Dictionary with video metadata (title, description, tags, etc.)

        Returns:
            Video type string or None
        """
        title = video_data.get("title", "")
        description = video_data.get("description", "")
        channel_name = video_data.get("channel_name", "") or video_data.get(
            "channel_title", ""
        )
        song_title = video_data.get("song_title", "")

        # First try detection from title and description
        video_type = cls.detect_from_title(title, description)
        if video_type:
            return video_type

        # Check tags if available
        tags = video_data.get("tags", [])
        if tags:
            tags_text = " ".join(str(tag).lower() for tag in tags)
            for vtype, keywords in cls.TYPE_KEYWORDS.items():
                if any(keyword in tags_text for keyword in keywords):
                    return vtype

        # Check channel name for live indicators
        channel_lower = channel_name.lower()
        if any(
            kw in channel_lower for kw in ["live", "concert", "festival", "sessions"]
        ):
            return "live_performance"

        # Check description for type hints (first 500 chars to avoid processing huge descriptions)
        desc_preview = description[:500].lower() if description else ""
        for vtype, keywords in cls.TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in desc_preview:
                    return vtype

        # If from an official channel (VEVO, artist name, or Topic channel),
        # and no other type detected, assume it's an official music video
        if channel_name:
            channel_lower = channel_name.lower()

            # Check for VEVO or official channel patterns
            if any(
                pattern in channel_lower for pattern in cls.OFFICIAL_CHANNEL_PATTERNS
            ):
                return "official_music_video"

            # Check if channel name matches or contains artist name from title
            # Extract artist name (usually before " - " in title)
            if " - " in title:
                artist_from_title = title.split(" - ")[0].strip().lower()
                # Clean up "The" prefix for matching
                artist_clean = artist_from_title.replace("the ", "")
                channel_clean = channel_lower.replace("the ", "")

                if artist_clean in channel_clean or channel_clean in artist_clean:
                    # Video is from artist's own channel - likely official
                    return "official_music_video"

        return None

    @classmethod
    def get_display_name(cls, video_type: Optional[str]) -> str:
        """
        Get human-readable display name for video type

        Args:
            video_type: Video type string

        Returns:
            Display name
        """
        display_names = {
            "official_music_video": "Official Music Video",
            "live_performance": "Live Performance",
            "lyric_video": "Lyric Video",
            "acoustic_version": "Acoustic Version",
            "remix_version": "Remix/Edit",
            "cover_version": "Cover Version",
            "music_documentary": "Music Documentary",
            "concert_footage": "Concert Footage",
        }
        return display_names.get(video_type, "Other/Unknown")

    @classmethod
    def get_all_types(cls) -> list:
        """
        Get list of all supported video types

        Returns:
            List of video type strings
        """
        return list(cls.TYPE_KEYWORDS.keys())

    @classmethod
    def get_type_options_for_ui(cls) -> list:
        """
        Get video type options formatted for UI display

        Returns:
            List of dicts with 'value' and 'label' keys
        """
        return [
            {"value": vtype, "label": cls.get_display_name(vtype)}
            for vtype in cls.get_all_types()
        ]
