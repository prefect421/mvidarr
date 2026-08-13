"""
Unified artist thumbnail source search.

Consolidates what were two separate, drifting cascades — the
single-artist thumbnail search endpoint (Wikipedia -> YouTube -> cached
metadata images) and the bulk-scan endpoint (Wikipedia -> YouTube only,
no metadata fallback at all) — into one shared function and one
priority order (#320).

#320 reported IMVDb as "limited" and Wikipedia as "not always
reliable," asking for MusicBrainz/Last.fm/Spotify to be tried first
instead. Spotify and Last.fm are added here as real, live image
sources, ahead of Wikipedia. MusicBrainz is deliberately NOT a source:
confirmed by reading musicbrainz_service.py's actual methods before
assuming otherwise, its API provides metadata and cross-service links
(genres, relations, release data), not artist photography — there is
no MusicBrainz-hosted artist image to fetch.

Note on Last.fm specifically: its artist.getInfo image field has, for
years, mostly returned a fixed set of gray placeholder images rather
than real artist photos — this is why the placeholder-URL filtering
below (shared with thumbnail_service.py, not a second copy of it)
matters as much for Last.fm as it does for Wikipedia/YouTube scraping.
Spotify remains the most reliable of the three explicitly-requested
sources.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from src.database.models import Artist
from src.services.lastfm_service import lastfm_service
from src.services.spotify_service import spotify_service
from src.services.thumbnail_service import thumbnail_service
from src.services.wikipedia_service import wikipedia_service
from src.services.youtube_search_service import youtube_search_service

logger = logging.getLogger("mvidarr.services.artist_thumbnail_search")

# Priority order for "auto" mode.
_AUTO_SOURCE_ORDER = ["spotify", "lastfm", "metadata", "wikipedia", "youtube"]

_METADATA_SIZE_PRIORITY = {
    "mega": 5,
    "extralarge": 4,
    "large": 3,
    "medium": 2,
    "small": 1,
    "": 0,
    "unknown": 0,
}


def _search_spotify(artist_name: str, artist: Optional[Artist]) -> List[Dict[str, Any]]:
    if not spotify_service.enabled:
        return []
    try:
        response = spotify_service.search_artist(artist_name, limit=1)
        items = (response or {}).get("artists", {}).get("items", [])
        if not items:
            return []
        images = items[0].get("images", []) or []
        return [
            {
                "source": "spotify",
                "url": img["url"],
                "title": f"{artist_name} - Spotify",
                "size": f"{img.get('width')}x{img.get('height')}",
            }
            for img in images
            if img.get("url") and not thumbnail_service.is_placeholder_url(img["url"])
        ]
    except Exception as e:
        logger.warning(f"Spotify thumbnail search failed for {artist_name}: {e}")
        return []


def _search_lastfm(artist_name: str, artist: Optional[Artist]) -> List[Dict[str, Any]]:
    if not lastfm_service.enabled:
        return []
    try:
        info = lastfm_service.get_artist_info(artist_name)
        results = []
        for img in info.get("image", []) or []:
            url = img.get("#text") if isinstance(img, dict) else None
            if url and not thumbnail_service.is_placeholder_url(url):
                size = img.get("size", "unknown")
                results.append(
                    {
                        "source": "lastfm",
                        "url": url,
                        "title": f"{artist_name} - Last.fm ({size})",
                        "size": size,
                    }
                )
        return results
    except Exception as e:
        logger.warning(f"Last.fm thumbnail search failed for {artist_name}: {e}")
        return []


def _search_cached_metadata(
    artist_name: str, artist: Optional[Artist]
) -> List[Dict[str, Any]]:
    """Images IMVDb already cached (typically sourced from Last.fm) on
    a prior enrichment pass — a useful fallback when the live Spotify/
    Last.fm sources above are unconfigured or disabled."""
    if not artist or not artist.imvdb_metadata:
        return []

    metadata = artist.imvdb_metadata
    images = metadata.get("images", []) if isinstance(metadata, dict) else []

    valid = []
    for img in images:
        if isinstance(img, dict):
            url = img.get("#text") or img.get("url")
            size = img.get("size", "unknown")
        elif isinstance(img, str):
            url, size = img, "unknown"
        else:
            continue

        if url and not thumbnail_service.is_placeholder_url(url):
            source = "lastfm" if "lastfm" in url else "metadata"
            valid.append(
                {
                    "source": source,
                    "url": url,
                    "title": f"{artist_name} - {source.title()} Image ({size})",
                    "size": size,
                }
            )

    valid.sort(key=lambda r: _METADATA_SIZE_PRIORITY.get(r["size"], 0), reverse=True)
    return valid[:3]


def _search_wikipedia(
    artist_name: str, artist: Optional[Artist]
) -> List[Dict[str, Any]]:
    try:
        search_terms = [artist_name]
        if artist_name.upper() == "REM":
            search_terms.extend(["R.E.M.", "R.E.M. band", "REM band"])
        elif "." not in artist_name and len(artist_name.split()) == 1:
            search_terms.extend([f"{artist_name} band", f"{artist_name} musician"])

        for term in search_terms:
            url = wikipedia_service.search_artist_thumbnail(term)
            if url and not thumbnail_service.is_placeholder_url(url):
                return [
                    {
                        "source": "wikipedia",
                        "url": url,
                        "title": f"{artist_name} - Wikipedia",
                        "description": f"Wikipedia thumbnail for {artist_name}",
                    }
                ]
        return []
    except Exception as e:
        logger.warning(f"Wikipedia thumbnail search failed for {artist_name}: {e}")
        return []


def _search_youtube(artist_name: str, artist: Optional[Artist]) -> List[Dict[str, Any]]:
    try:
        url = youtube_search_service.search_artist_channel_thumbnail(artist_name)
        if url and not thumbnail_service.is_placeholder_url(url):
            return [
                {
                    "source": "youtube",
                    "url": url,
                    "title": f"{artist_name} - YouTube Channel",
                    "channel": artist_name,
                }
            ]
        return []
    except Exception as e:
        logger.warning(f"YouTube thumbnail search failed for {artist_name}: {e}")
        return []


_SOURCE_SEARCHERS: Dict[
    str, Callable[[str, Optional[Artist]], List[Dict[str, Any]]]
] = {
    "spotify": _search_spotify,
    "lastfm": _search_lastfm,
    "metadata": _search_cached_metadata,
    "wikipedia": _search_wikipedia,
    "youtube": _search_youtube,
}


def search_artist_thumbnails(
    artist_name: str,
    artist: Optional[Artist] = None,
    source_filter: str = "auto",
    stop_at_first_result: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search configured thumbnail sources for an artist.

    Args:
        artist_name: Name to search for.
        artist: The Artist row, if available — enables the cached-
            metadata fallback source. Optional; pass None for a search
            with no associated database row yet.
        source_filter: "auto" tries every source in priority order
            (spotify, lastfm, metadata, wikipedia, youtube), skipping
            any that are unconfigured. Any other value restricts the
            search to just that one named source.
        stop_at_first_result: If True, stop after the first source that
            returns at least one result, instead of gathering results
            from every source. Use for automated/bulk scans where one
            good hit per artist is enough; leave False for interactive
            search UIs that let a user pick among multiple options.

    Returns:
        A list of {"source", "url", "title", ...} dicts, most-preferred
        source first. Known placeholder images (dead Last.fm/Wikipedia/
        YouTube defaults) are already filtered out.
    """
    sources = _AUTO_SOURCE_ORDER if source_filter == "auto" else [source_filter]

    results: List[Dict[str, Any]] = []
    for source in sources:
        searcher = _SOURCE_SEARCHERS.get(source)
        if not searcher:
            continue
        source_results = searcher(artist_name, artist)
        results.extend(source_results)
        if stop_at_first_result and source_results:
            break

    return results
