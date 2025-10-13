"""
Metadata Parsing Utilities for Enhanced Metadata Enrichment Service

This module contains utility functions for parsing and extracting information
from various metadata sources including Last.fm biographies, MusicBrainz data,
Spotify metadata, and IMVDb information.

Extracted from metadata_enrichment_service.py as part of code cleanup.
"""

import re
import urllib.parse
from typing import Dict, List

from src.services.metadata_models import ArtistMetadata
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.metadata_parsers")


def extract_extended_information(metadata: ArtistMetadata) -> Dict:
    """Extract extended information from aggregated metadata

    Args:
        metadata: ArtistMetadata object containing raw data from multiple sources

    Returns:
        Dictionary containing extended information like formed_year, disbanded_year,
        origin_country, artist_type, aliases, labels, etc.
    """
    extended_info = {}

    # Check all sources for extended information
    if hasattr(metadata, "raw_data") and isinstance(metadata.raw_data, dict):
        sources = metadata.raw_data.get("sources", {})

        # Extract from Last.fm data (often has formation/disbanded years and country)
        if "lastfm" in sources:
            lastfm_data = sources["lastfm"]

            # Parse biography for formation year and country
            bio = lastfm_data.get("bio", {})
            if isinstance(bio, dict):
                bio_content = bio.get("content", "") or bio.get("summary", "")
                extended_info.update(parse_biography_info(bio_content))

            # Tags can sometimes indicate origin
            tags = lastfm_data.get("tags", {})
            if isinstance(tags, dict) and "tag" in tags:
                tag_list = (
                    tags["tag"] if isinstance(tags["tag"], list) else [tags["tag"]]
                )
                extended_info.update(extract_country_from_tags(tag_list))

        # Extract from Spotify data (has related artists, sometimes country info)
        if "spotify" in sources:
            spotify_data = sources["spotify"]

            # Spotify may have country info in some cases
            if "origin_country" in spotify_data:
                extended_info["origin_country"] = spotify_data["origin_country"]

            # Extract record labels from external_urls or other fields
            if "external_urls" in spotify_data:
                extended_info.update(
                    extract_labels_from_urls(spotify_data["external_urls"])
                )

        # Extract from IMVDb data
        if "imvdb" in sources:
            imvdb_data = sources["imvdb"]

            # IMVDb sometimes has formation year
            if "formed" in imvdb_data:
                try:
                    extended_info["formed_year"] = int(
                        str(imvdb_data["formed"]).strip()
                    )
                except (ValueError, TypeError):
                    pass

            # IMVDb may have country info
            if "country" in imvdb_data:
                extended_info["origin_country"] = imvdb_data["country"]

        # Extract from MusicBrainz data (most authoritative source)
        if "musicbrainz" in sources:
            musicbrainz_data = sources["musicbrainz"]

            # Formation/disbanded years from life_span (most reliable)
            life_span = musicbrainz_data.get("life_span", {})
            if isinstance(life_span, dict):
                if life_span.get("begin"):
                    try:
                        # Parse YYYY-MM-DD or YYYY format
                        begin_date = life_span["begin"]
                        formed_year = (
                            int(begin_date.split("-")[0]) if begin_date else None
                        )
                        if formed_year and not extended_info.get("formed_year"):
                            extended_info["formed_year"] = formed_year
                    except (ValueError, AttributeError, IndexError):
                        pass

                if life_span.get("end"):
                    try:
                        # Parse YYYY-MM-DD or YYYY format
                        end_date = life_span["end"]
                        disbanded_year = (
                            int(end_date.split("-")[0]) if end_date else None
                        )
                        if disbanded_year and not extended_info.get("disbanded_year"):
                            extended_info["disbanded_year"] = disbanded_year
                    except (ValueError, AttributeError, IndexError):
                        pass

            # Origin country/area (most authoritative)
            if musicbrainz_data.get("country") and not extended_info.get(
                "origin_country"
            ):
                extended_info["origin_country"] = musicbrainz_data["country"]
            elif musicbrainz_data.get("area") and not extended_info.get(
                "origin_country"
            ):
                extended_info["origin_country"] = musicbrainz_data["area"]

            # Artist type information
            if musicbrainz_data.get("type"):
                extended_info["artist_type"] = musicbrainz_data["type"]

            # Aliases (alternative names)
            if musicbrainz_data.get("aliases"):
                aliases = musicbrainz_data["aliases"]
                if isinstance(aliases, list) and aliases:
                    extended_info["aliases"] = [alias for alias in aliases if alias]

            # Record labels (most authoritative)
            if musicbrainz_data.get("labels"):
                labels = musicbrainz_data["labels"]
                if isinstance(labels, list) and labels:
                    extended_info["labels"] = [label for label in labels if label]

            # Sort name (for proper alphabetization)
            if musicbrainz_data.get("sort_name"):
                extended_info["sort_name"] = musicbrainz_data["sort_name"]

            # Begin area (where artist was formed, more specific than country)
            if musicbrainz_data.get("begin_area") and not extended_info.get(
                "origin_area"
            ):
                extended_info["origin_area"] = musicbrainz_data["begin_area"]

            # Disambiguation (helps identify the specific artist)
            if musicbrainz_data.get("disambiguation"):
                extended_info["disambiguation"] = musicbrainz_data["disambiguation"]

            # Additional genres from MusicBrainz tags (supplement existing genres)
            mb_tags = musicbrainz_data.get("tags", [])
            mb_genres = musicbrainz_data.get("genres", [])

            if mb_tags or mb_genres:
                all_mb_genres = []
                if isinstance(mb_tags, list):
                    all_mb_genres.extend(mb_tags)
                if isinstance(mb_genres, list):
                    all_mb_genres.extend(mb_genres)

                if all_mb_genres:
                    # Filter to music-related genres only
                    music_genres = [g for g in all_mb_genres if is_music_genre(g)]
                    if music_genres and not extended_info.get("additional_genres"):
                        extended_info["additional_genres"] = music_genres[
                            :10
                        ]  # Limit to avoid clutter

    return extended_info


def is_music_genre(genre: str) -> bool:
    """Check if a tag/genre is music-related and not a general descriptor

    Args:
        genre: Genre or tag string to check

    Returns:
        True if the genre appears to be a legitimate music genre, False otherwise
    """
    if not genre or not isinstance(genre, str):
        return False

    genre_lower = genre.lower().strip()

    # Skip very general or non-musical tags
    skip_tags = {
        "seen live",
        "favorite",
        "favourites",
        "awesome",
        "great",
        "good",
        "bad",
        "love",
        "hate",
        "cool",
        "hot",
        "new",
        "old",
        "best",
        "worst",
        "top",
        "albums i own",
        "artists i've seen live",
        "male",
        "female",
        "american",
        "british",
        "english",
        "canadian",
        "australian",
        "instrumental",
        "vocal",
        "solo",
        "group",
        "band",
        "artist",
        "singer",
        "musician",
        "composer",
    }

    if genre_lower in skip_tags:
        return False

    # Skip country names (these should go in origin_country)
    country_indicators = [
        "american",
        "british",
        "canadian",
        "australian",
        "german",
        "french",
        "japanese",
    ]
    if any(country in genre_lower for country in country_indicators):
        return False

    # Skip decades (these are time periods, not genres)
    if any(
        decade in genre_lower
        for decade in ["60s", "70s", "80s", "90s", "00s", "10s", "20s"]
    ):
        return False

    # Accept anything that looks like a legitimate music genre
    return len(genre_lower) > 2


def extract_external_links(metadata: ArtistMetadata) -> Dict:
    """Extract external links from aggregated metadata

    Args:
        metadata: ArtistMetadata object containing raw data from multiple sources

    Returns:
        Dictionary containing external links like spotify_url, website_url,
        twitter_url, facebook_url, instagram_url, youtube_url, etc.
    """
    external_links = {}

    # Check all sources for external links
    if hasattr(metadata, "raw_data") and isinstance(metadata.raw_data, dict):
        sources = metadata.raw_data.get("sources", {})

        # Extract from Spotify data
        if "spotify" in sources:
            spotify_data = sources["spotify"]

            # Spotify external URLs
            if "external_urls" in spotify_data:
                spotify_urls = spotify_data["external_urls"]
                if "spotify" in spotify_urls:
                    external_links["spotify_url"] = spotify_urls["spotify"]

            # Generate Spotify URL from ID if not present
            if not external_links.get("spotify_url") and metadata.spotify_id:
                external_links["spotify_url"] = (
                    f"https://open.spotify.com/artist/{metadata.spotify_id}"
                )

        # Extract from Last.fm data
        if "lastfm" in sources:
            lastfm_data = sources["lastfm"]

            # Last.fm URL
            if "url" in lastfm_data:
                # Don't add Last.fm URL to external links (not in UI)
                pass

            # Parse biography for social media links
            bio = lastfm_data.get("bio", {})
            if isinstance(bio, dict):
                bio_content = bio.get("content", "") or bio.get("summary", "")
                external_links.update(parse_social_links_from_bio(bio_content))

        # Extract from IMVDb data
        if "imvdb" in sources:
            imvdb_data = sources["imvdb"]

            # IMVDb sometimes has official website
            if "website" in imvdb_data:
                external_links["website_url"] = imvdb_data["website"]

            # IMVDb may have social media links
            for social_key in ["twitter", "facebook", "instagram", "youtube"]:
                if social_key in imvdb_data:
                    external_links[f"{social_key}_url"] = imvdb_data[social_key]

        # Extract from MusicBrainz data
        if "musicbrainz" in sources:
            musicbrainz_data = sources["musicbrainz"]

            # MusicBrainz external URLs (most authoritative source)
            if "external_urls" in musicbrainz_data:
                mb_urls = musicbrainz_data["external_urls"]

                # Map MusicBrainz URLs to our standard format
                url_mapping = {
                    "homepage": "website_url",
                    "spotify": "spotify_url",
                    "youtube": "youtube_url",
                    "twitter": "twitter_url",
                    "facebook": "facebook_url",
                    "instagram": "instagram_url",
                    "apple_music": "apple_music_url",
                }

                for mb_key, our_key in url_mapping.items():
                    if mb_key in mb_urls and mb_urls[mb_key]:
                        # MusicBrainz is authoritative, only override if we don't have it
                        if not external_links.get(our_key):
                            external_links[our_key] = mb_urls[mb_key]

    return external_links


def parse_biography_info(bio_content: str) -> Dict:
    """Parse biography text for formation year, country, etc.

    Args:
        bio_content: Biography text to parse

    Returns:
        Dictionary containing parsed information like formed_year, disbanded_year,
        origin_country
    """
    info = {}

    if not bio_content:
        return info

    # Look for formation year patterns
    year_patterns = [
        r"formed in (\d{4})",
        r"founded in (\d{4})",
        r"started in (\d{4})",
        r"began in (\d{4})",
        r"established in (\d{4})",
    ]

    for pattern in year_patterns:
        match = re.search(pattern, bio_content, re.IGNORECASE)
        if match:
            try:
                info["formed_year"] = int(match.group(1))
                break
            except ValueError:
                pass

    # Look for disbanded year patterns
    disbanded_patterns = [
        r"disbanded in (\d{4})",
        r"broke up in (\d{4})",
        r"ended in (\d{4})",
        r"split up in (\d{4})",
    ]

    for pattern in disbanded_patterns:
        match = re.search(pattern, bio_content, re.IGNORECASE)
        if match:
            try:
                info["disbanded_year"] = int(match.group(1))
                break
            except ValueError:
                pass

    # Look for country patterns
    country_patterns = [
        r"from ([A-Z][a-z]+ [A-Z][a-z]+)",  # "from United States"
        r"from ([A-Z][a-z]+)",  # "from England"
        r"([A-Z][a-z]+) band",  # "American band"
        r"([A-Z][a-z]+) group",  # "British group"
    ]

    for pattern in country_patterns:
        match = re.search(pattern, bio_content, re.IGNORECASE)
        if match:
            country = match.group(1).strip()
            # Map common country names to ISO codes
            country_mapping = {
                "United States": "US",
                "America": "US",
                "American": "US",
                "United Kingdom": "UK",
                "Britain": "UK",
                "British": "UK",
                "England": "UK",
                "Canada": "CA",
                "Canadian": "CA",
                "Australia": "AU",
                "Australian": "AU",
                "Germany": "DE",
                "German": "DE",
                "France": "FR",
                "French": "FR",
                "Japan": "JP",
                "Japanese": "JP",
            }
            info["origin_country"] = country_mapping.get(country, country)
            break

    return info


def extract_country_from_tags(tags: List) -> Dict:
    """Extract country information from tags

    Args:
        tags: List of tag dictionaries or strings

    Returns:
        Dictionary containing origin_country if found in tags
    """
    info = {}

    country_tags = {
        "american": "US",
        "usa": "US",
        "united states": "US",
        "british": "UK",
        "uk": "UK",
        "english": "UK",
        "scottish": "UK",
        "welsh": "UK",
        "canadian": "CA",
        "canada": "CA",
        "australian": "AU",
        "australia": "AU",
        "german": "DE",
        "germany": "DE",
        "french": "FR",
        "france": "FR",
        "japanese": "JP",
        "japan": "JP",
    }

    for tag in tags:
        tag_name = (
            tag.get("name", "").lower() if isinstance(tag, dict) else str(tag).lower()
        )
        if tag_name in country_tags:
            info["origin_country"] = country_tags[tag_name]
            break

    return info


def extract_labels_from_urls(external_urls: Dict) -> Dict:
    """Extract record label info from external URLs (limited effectiveness)

    Args:
        external_urls: Dictionary of external URLs

    Returns:
        Dictionary containing label information (currently empty as this is complex)
    """
    # This is a placeholder - extracting label info from URLs is complex
    # Could be enhanced to recognize major label domains
    return {}


def parse_social_links_from_bio(bio_content: str) -> Dict:
    """Parse social media links from biography text

    Args:
        bio_content: Biography text to parse for social media URLs

    Returns:
        Dictionary containing social media links like website_url, twitter_url,
        facebook_url, instagram_url, youtube_url
    """
    links = {}

    if not bio_content:
        return links

    # Social media URL patterns
    social_patterns = {
        "website_url": r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.(?:com|org|net|io))",
        "twitter_url": r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)",
        "facebook_url": r"(?:https?://)?(?:www\.)?facebook\.com/([a-zA-Z0-9.]+)",
        "instagram_url": r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)",
        "youtube_url": r"(?:https?://)?(?:www\.)?youtube\.com/(?:user/|channel/|c/)?([a-zA-Z0-9_-]+)",
    }

    for link_type, pattern in social_patterns.items():
        matches = re.findall(pattern, bio_content, re.IGNORECASE)
        if matches and link_type == "website_url":
            # For website, be more selective - avoid social media domains
            for match in matches:
                if not any(
                    social in match.lower()
                    for social in [
                        "twitter",
                        "facebook",
                        "instagram",
                        "youtube",
                        "spotify",
                    ]
                ):
                    links[link_type] = (
                        f"https://{match}" if not match.startswith("http") else match
                    )
                    break
        elif matches:
            username = matches[0]
            if link_type == "twitter_url":
                links[link_type] = f"https://twitter.com/{username}"
            elif link_type == "facebook_url":
                links[link_type] = f"https://facebook.com/{username}"
            elif link_type == "instagram_url":
                links[link_type] = f"https://instagram.com/{username}"
            elif link_type == "youtube_url":
                links[link_type] = f"https://youtube.com/c/{username}"

    return links
