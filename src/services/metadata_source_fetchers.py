"""
Metadata Source Fetchers for MVidarr
Extracted source fetcher methods for metadata enrichment from multiple music services.
This module contains standalone functions for fetching metadata from various sources.
"""

import asyncio
from typing import Dict, Optional

from src.database.connection import get_db
from src.database.models import Artist
from src.services.metadata_models import ArtistMetadata
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.metadata_source_fetchers")


async def gather_all_sources_metadata(
    service, artist_data: Dict, progress_callback=None
) -> Dict[str, ArtistMetadata]:
    """Gather metadata from all available sources"""
    metadata_sources = {}

    # Spotify metadata - using async service (always enabled if configured)
    if progress_callback:
        progress_callback(45, "Fetching Spotify metadata...")
    try:
        logger.debug(f"🎵 ASYNC SPOTIFY ENRICHMENT: Starting for {artist_data['name']}")

        # Temporarily force sync Spotify service due to async event loop issues in Celery
        spotify_metadata = get_spotify_metadata_sync(service, artist_data)
        if spotify_metadata:
            logger.info(
                f"🎵 SPOTIFY ENRICHMENT: Got metadata for {spotify_metadata.name} with {len(spotify_metadata.images)} images"
            )
            logger.debug(
                f"🎵 SPOTIFY ENRICHMENT: Related artists: {spotify_metadata.related_artists}"
            )
            logger.debug(
                f"🎵 SPOTIFY ENRICHMENT: Top tracks: {spotify_metadata.top_tracks}"
            )
            metadata_sources["spotify"] = spotify_metadata
            logger.info(f"🎵 SPOTIFY ENRICHMENT: Added Spotify to metadata sources")
        else:
            logger.warning(
                f"🎵 SPOTIFY ENRICHMENT: No metadata returned for {artist_data['name']}"
            )
    except Exception as e:
        logger.warning(
            f"Failed to get async Spotify metadata for {artist_data['name']}: {e}"
        )

    # Last.fm metadata - check if enabled
    if progress_callback:
        progress_callback(52, "Fetching Last.fm metadata...")
    if hasattr(service.lastfm, "enabled") and service.lastfm.enabled:
        try:
            lastfm_metadata = await get_lastfm_metadata(service, artist_data)
            if lastfm_metadata:
                metadata_sources["lastfm"] = lastfm_metadata
                logger.debug(
                    f"Successfully gathered Last.fm metadata for {artist_data['name']}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to get Last.fm metadata for {artist_data['name']}: {e}"
            )
    else:
        logger.debug(
            f"Last.fm integration disabled or not configured, skipping for {artist_data['name']}"
        )

    # IMVDb metadata - DEEMPHASIZED (low priority fallback)
    # IMVDb is used as a fallback source when primary sources (Spotify, Last.fm) fail
    if progress_callback:
        progress_callback(58, "Fetching IMVDb metadata...")
    try:
        imvdb_metadata = await get_imvdb_metadata(service, artist_data)
        if imvdb_metadata:
            # Set lower confidence for IMVDb to deemphasize it in aggregation
            imvdb_metadata.confidence = max(0.3, imvdb_metadata.confidence * 0.5)
            metadata_sources["imvdb"] = imvdb_metadata
            logger.debug(
                f"Successfully gathered IMVDb metadata for {artist_data['name']} (deemphasized)"
            )
    except Exception as e:
        logger.warning(f"Failed to get IMVDb metadata for {artist_data['name']}: {e}")

    # MusicBrainz metadata - check if enabled
    if progress_callback:
        progress_callback(64, "Fetching MusicBrainz metadata...")
    if hasattr(service.musicbrainz, "enabled") and service.musicbrainz.enabled:
        try:
            musicbrainz_metadata = await get_musicbrainz_metadata(service, artist_data)
            if musicbrainz_metadata:
                metadata_sources["musicbrainz"] = musicbrainz_metadata
                logger.debug(
                    f"Successfully gathered MusicBrainz metadata for {artist_data['name']}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to get MusicBrainz metadata for {artist_data['name']}: {e}"
            )
    else:
        logger.debug(
            f"MusicBrainz integration disabled, skipping for {artist_data['name']}"
        )

    # AllMusic metadata - check if enabled
    if progress_callback:
        progress_callback(70, "Fetching AllMusic metadata...")
    logger.debug(
        f"Checking AllMusic for {artist_data['name']}: hasattr={hasattr(service.allmusic, 'enabled')}, enabled={getattr(service.allmusic, 'enabled', None)}"
    )
    if hasattr(service.allmusic, "enabled") and service.allmusic.enabled:
        try:
            logger.info(f"Calling AllMusic for {artist_data['name']}")
            allmusic_metadata = await get_allmusic_metadata(service, artist_data)
            if allmusic_metadata:
                metadata_sources["allmusic"] = allmusic_metadata
                logger.info(
                    f"Successfully gathered AllMusic metadata for {artist_data['name']}"
                )
            else:
                logger.warning(
                    f"AllMusic returned no metadata for {artist_data['name']}"
                )
        except Exception as e:
            logger.error(
                f"Failed to get AllMusic metadata for {artist_data['name']}: {e}"
            )
    else:
        logger.warning(
            f"AllMusic integration disabled or not available, skipping for {artist_data['name']} - hasattr: {hasattr(service.allmusic, 'enabled')}, enabled: {getattr(service.allmusic, 'enabled', None)}"
        )

    # Wikipedia metadata - basic biography integration
    if progress_callback:
        progress_callback(76, "Fetching Wikipedia metadata...")
    try:
        logger.info(f"Calling Wikipedia for {artist_data['name']}")
        wikipedia_metadata = await get_wikipedia_metadata(service, artist_data)
        if wikipedia_metadata:
            metadata_sources["wikipedia"] = wikipedia_metadata
            logger.info(
                f"Successfully gathered Wikipedia metadata for {artist_data['name']}"
            )
        else:
            logger.debug(f"Wikipedia returned no metadata for {artist_data['name']}")
    except Exception as e:
        logger.warning(
            f"Failed to get Wikipedia metadata for {artist_data['name']}: {e}"
        )

    # Discogs integration removed

    logger.info(
        f"Gathered metadata from {len(metadata_sources)} sources for {artist_data['name']}: {list(metadata_sources.keys())}"
    )
    return metadata_sources


async def get_spotify_metadata(service, artist_data: Dict) -> Optional[ArtistMetadata]:
    """Get enhanced metadata from Spotify (using async service)"""
    try:
        # Get async Spotify service with timeout to prevent hanging
        try:
            from src.services.async_spotify_service import get_async_spotify_service

            async_spotify = await asyncio.wait_for(
                get_async_spotify_service(), timeout=5.0
            )
            if not async_spotify:
                logger.warning(
                    "Could not get async Spotify service, falling back to sync"
                )
                return get_spotify_metadata_sync(service, artist_data)
        except asyncio.TimeoutError:
            logger.warning("Async Spotify service timed out, falling back to sync")
            return get_spotify_metadata_sync(service, artist_data)

        # Search for artist if we don't have Spotify ID
        spotify_artist = None
        logger.debug(
            f"🎵 ASYNC SPOTIFY METADATA: Processing {artist_data['name']}, spotify_id: {artist_data.get('spotify_id')}"
        )

        if artist_data.get("spotify_id"):
            # Get artist by ID
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Getting artist by ID {artist_data['spotify_id']}"
            )
            spotify_artist = await async_spotify.get_artist(artist_data["spotify_id"])
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Got artist by ID: {spotify_artist is not None}"
            )
        else:
            # Search for artist
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Searching for artist {artist_data['name']}"
            )
            search_results = await async_spotify.search_artist(
                artist_data["name"], limit=5
            )
            artists = search_results.get("artists", {}).get("items", [])
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Search returned {len(artists)} artists"
            )

            # Find best match
            for candidate in artists:
                if service._is_artist_match(
                    artist_data["name"], candidate.get("name", "")
                ):
                    spotify_artist = candidate
                    break

        if not spotify_artist:
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: No matching artist found for {artist_data['name']}"
            )
            return None

        logger.debug(
            f"🎵 ASYNC SPOTIFY METADATA: Found artist: {spotify_artist.get('name')} (ID: {spotify_artist['id']})"
        )

        # Get related artists
        related_artists = []
        try:
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Getting related artists for {spotify_artist['id']}"
            )
            related_data = await async_spotify.get_artist_related_artists(
                spotify_artist["id"]
            )
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Raw related artists response: {related_data}"
            )

            if related_data and "artists" in related_data:
                related_artists = [
                    a.get("name") for a in related_data.get("artists", [])[:5]
                ]
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Processed {len(related_artists)} related artists: {related_artists}"
                )
            else:
                logger.warning(
                    f"🎵 ASYNC SPOTIFY METADATA: No 'artists' key in related artists response: {related_data}"
                )

        except Exception as e:
            logger.warning(
                f"🎵 ASYNC SPOTIFY METADATA: Could not get related artists: {e}"
            )
            logger.exception(f"🎵 ASYNC SPOTIFY METADATA: Full exception details:")

        # Get top tracks
        top_tracks = []
        try:
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Getting top tracks for {spotify_artist['id']}"
            )
            tracks_data = await async_spotify.get_artist_top_tracks(
                spotify_artist["id"]
            )
            top_tracks = [t.get("name") for t in tracks_data.get("tracks", [])[:5]]
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Got {len(top_tracks)} top tracks: {top_tracks}"
            )
        except Exception as e:
            logger.warning(f"🎵 ASYNC SPOTIFY METADATA: Could not get top tracks: {e}")

        # Create metadata object
        logger.debug(
            f"🎵 ASYNC SPOTIFY METADATA: Creating ArtistMetadata with related_artists: {related_artists}, top_tracks: {top_tracks}"
        )
        metadata = ArtistMetadata(
            name=spotify_artist.get("name", artist_data["name"]),
            source="spotify",
            confidence=service._calculate_name_similarity(
                artist_data["name"], spotify_artist.get("name", "")
            ),
            genres=spotify_artist.get("genres", []),
            popularity=spotify_artist.get("popularity"),
            followers=spotify_artist.get("followers", {}).get("total"),
            images=spotify_artist.get("images", []),
            spotify_id=spotify_artist.get("id"),
            related_artists=related_artists,
            top_tracks=top_tracks,
            raw_data=spotify_artist,
        )
        logger.debug(
            f"🎵 ASYNC SPOTIFY METADATA: Final metadata object - related_artists: {metadata.related_artists}, top_tracks: {metadata.top_tracks}"
        )

        return metadata

    except Exception as e:
        logger.error(f"Error getting async Spotify metadata: {e}")
        # Fall back to sync Spotify service if async fails (e.g., event loop issues in Celery)
        return get_spotify_metadata_sync(service, artist_data)


def get_spotify_metadata_sync(service, artist_data: Dict) -> Optional[ArtistMetadata]:
    """Get enhanced metadata from Spotify using sync service (fallback for Celery)"""
    try:
        logger.info(
            f"🎵 SYNC SPOTIFY METADATA: Falling back to sync service for {artist_data['name']}"
        )

        # Use sync Spotify service - prefer existing Spotify ID over search
        spotify_artist = None

        if artist_data.get("spotify_id"):
            # Use existing Spotify ID
            logger.info(
                f"🎵 SYNC SPOTIFY METADATA: Using existing Spotify ID: {artist_data['spotify_id']}"
            )
            try:
                spotify_artist = service.spotify.get_artist(artist_data["spotify_id"])
                if spotify_artist:
                    logger.info(
                        f"🎵 SYNC SPOTIFY METADATA: Found artist by ID: {spotify_artist.get('name')}"
                    )
                else:
                    logger.warning(
                        f"🎵 SYNC SPOTIFY METADATA: No artist found for ID: {artist_data['spotify_id']}"
                    )
            except Exception as e:
                logger.warning(
                    f"🎵 SYNC SPOTIFY METADATA: Error getting artist by ID: {e}"
                )

        if not spotify_artist:
            # Fallback to search by name
            search_query = artist_data.get("spotify_name") or artist_data["name"]
            logger.info(f"🎵 SYNC SPOTIFY METADATA: Searching for: {search_query}")
            spotify_results = service.spotify.search_artist(search_query)

            logger.info(
                f"🎵 SYNC SPOTIFY METADATA: Search results: {spotify_results is not None}"
            )
            if spotify_results:
                artists = spotify_results.get("artists", {}).get("items", [])
                logger.info(f"🎵 SYNC SPOTIFY METADATA: Found {len(artists)} artists")

                # Find best match
                for candidate in artists:
                    if service._is_artist_match(
                        artist_data["name"], candidate.get("name", "")
                    ):
                        spotify_artist = candidate
                        break

            if not spotify_artist:
                logger.warning(
                    f"No matching sync Spotify artist found for: {search_query}"
                )
                return None

        logger.info(
            f"🎵 SYNC SPOTIFY METADATA: Found artist: {spotify_artist.get('name')} (ID: {spotify_artist.get('id')})"
        )

        # Create metadata object with basic info (sync service has limited capabilities)
        metadata = ArtistMetadata(
            name=spotify_artist.get("name", artist_data["name"]),
            source="spotify",
            confidence=service._calculate_name_similarity(
                artist_data["name"], spotify_artist.get("name", "")
            ),
            genres=spotify_artist.get("genres", []),
            popularity=spotify_artist.get("popularity"),
            followers=spotify_artist.get("followers", {}).get("total"),
            images=spotify_artist.get("images", []),
            spotify_id=spotify_artist.get("id"),
            related_artists=[],  # Sync service doesn't support related artists easily
            top_tracks=[],  # Sync service doesn't support top tracks easily
            raw_data=spotify_artist,
        )

        logger.info(
            f"🎵 SYNC SPOTIFY METADATA: Created metadata with {len(metadata.images)} images"
        )
        logger.info(
            f"🎵 SYNC SPOTIFY METADATA: Returning metadata for {metadata.name} with confidence {metadata.confidence}"
        )
        return metadata

    except Exception as e:
        logger.error(f"Error getting sync Spotify metadata: {e}")
        logger.error(f"🎵 SYNC SPOTIFY METADATA: Returning None due to error")
        return None


async def get_lastfm_metadata(service, artist_data: Dict) -> Optional[ArtistMetadata]:
    """Get enhanced metadata from Last.fm"""
    try:
        # Get artist info
        artist_info = service.lastfm.get_artist_info(
            artist_data.get("lastfm_name") or artist_data["name"]
        )

        if not artist_info:
            return None

        # Get similar artists
        similar_artists = []
        try:
            artist_name = artist_data.get("lastfm_name") or artist_data["name"]
            similar_artists = service.lastfm.get_similar_artists(
                artist_name, service.similar_artists_limit
            )
            logger.debug(
                f"🎵 LAST.FM METADATA: Got {len(similar_artists)} similar artists: {similar_artists}"
            )
        except Exception as e:
            logger.debug(f"🎵 LAST.FM METADATA: Could not get similar artists: {e}")

        # Get top tracks
        top_tracks = []
        try:
            tracks_data = service.lastfm.get_artist_top_tracks(artist_data["name"], 5)
            top_tracks = [
                t.get("name") for t in tracks_data.get("toptracks", {}).get("track", [])
            ]
        except Exception as e:
            logger.debug(f"Could not get top tracks: {e}")

        metadata = ArtistMetadata(
            name=artist_info.get("name", artist_data["name"]),
            source="lastfm",
            confidence=service._calculate_name_similarity(
                artist_data["name"], artist_info.get("name", "")
            ),
            genres=artist_info.get("tags", []),
            biography=artist_info.get("bio", ""),
            images=artist_info.get("image", []),
            similar_artists=similar_artists,
            top_tracks=top_tracks,
            playcount=artist_info.get("playcount"),
            listeners=artist_info.get("listeners"),
            user_playcount=artist_info.get("user_playcount"),
            lastfm_name=artist_info.get("name"),
            raw_data=artist_info,
        )

        return metadata

    except Exception as e:
        logger.error(f"Error getting Last.fm metadata: {e}")
        return None


async def get_imvdb_metadata(service, artist_data: Dict) -> Optional[ArtistMetadata]:
    """Get enhanced metadata from IMVDb"""
    try:
        # Use existing IMVDb integration
        if artist_data.get("imvdb_id"):
            # Get fresh artist data by ID
            imvdb_artist_data = service.imvdb.get_artist(artist_data["imvdb_id"])
        else:
            # Search for artist
            search_results = service.imvdb.search_artist(artist_data["name"])
            if not search_results or not search_results.get("results"):
                return None
            imvdb_artist_data = search_results["results"][0]

        if not imvdb_artist_data:
            return None

        metadata = ArtistMetadata(
            name=imvdb_artist_data.get("name", artist_data["name"]),
            source="imvdb",
            confidence=service._calculate_name_similarity(
                artist_data["name"], imvdb_artist_data.get("name", "")
            ),
            imvdb_id=str(imvdb_artist_data.get("id")),
            raw_data=imvdb_artist_data,
        )

        return metadata

    except Exception as e:
        logger.error(f"Error getting IMVDb metadata: {e}")
        return None


async def get_musicbrainz_metadata(
    service, artist_data: Dict
) -> Optional[ArtistMetadata]:
    """Get enhanced metadata from MusicBrainz"""
    try:
        # Check if we have a MusicBrainz ID from Last.fm or elsewhere
        mbid = None

        # Try to get MBID from existing data sources if available
        # This could come from Last.fm data or stored metadata
        with get_db() as session:
            artist = (
                session.query(Artist).filter(Artist.id == artist_data["id"]).first()
            )
            if artist and artist.imvdb_metadata:
                # Check if we have stored MBID in metadata
                stored_mbid = artist.imvdb_metadata.get("musicbrainz_id")
                if stored_mbid:
                    mbid = stored_mbid

        # Get metadata from MusicBrainz
        mb_metadata = service.musicbrainz.get_artist_metadata_for_enrichment(
            artist_data["name"], mbid
        )

        if not mb_metadata:
            return None

        # Convert to ArtistMetadata format
        metadata = ArtistMetadata(
            name=mb_metadata.get("name", artist_data["name"]),
            source="musicbrainz",
            confidence=mb_metadata.get("confidence", 0.95),
            genres=mb_metadata.get("genres", []),
            mbid=mb_metadata.get("mbid"),
            raw_data=mb_metadata.get("raw_data", {}),
        )

        # Add additional MusicBrainz-specific fields if available
        if mb_metadata.get("formed_year"):
            metadata.raw_data["formed_year"] = mb_metadata["formed_year"]
        if mb_metadata.get("country"):
            metadata.raw_data["country"] = mb_metadata["country"]
        if mb_metadata.get("area"):
            metadata.raw_data["area"] = mb_metadata["area"]
        if mb_metadata.get("type"):
            metadata.raw_data["type"] = mb_metadata["type"]
        if mb_metadata.get("labels"):
            metadata.raw_data["labels"] = mb_metadata["labels"]
        if mb_metadata.get("external_urls"):
            metadata.raw_data["external_urls"] = mb_metadata["external_urls"]

        return metadata

    except Exception as e:
        logger.error(f"Error getting MusicBrainz metadata: {e}")
        return None


async def get_allmusic_metadata(service, artist_data: Dict) -> Optional[ArtistMetadata]:
    """Get enhanced metadata from AllMusic"""
    try:
        # Get metadata from AllMusic service
        allmusic_metadata = service.allmusic.get_artist_metadata_for_enrichment(
            artist_data["name"]
        )

        if not allmusic_metadata:
            return None

        # Convert to ArtistMetadata format
        metadata = ArtistMetadata(
            name=allmusic_metadata.get("name", artist_data["name"]),
            source="allmusic",
            confidence=allmusic_metadata.get("confidence", 0.88),
            genres=allmusic_metadata.get("genres", []),
            biography=allmusic_metadata.get("biography"),
            similar_artists=allmusic_metadata.get("similar_artists", []),
            raw_data=allmusic_metadata.get("raw_data", {}),
        )

        # Add AllMusic-specific fields if available
        if allmusic_metadata.get("formed_year"):
            metadata.raw_data["formed_year"] = allmusic_metadata["formed_year"]
        if allmusic_metadata.get("origin_country"):
            metadata.raw_data["origin_country"] = allmusic_metadata["origin_country"]
        if allmusic_metadata.get("members"):
            metadata.raw_data["members"] = allmusic_metadata["members"]
        if allmusic_metadata.get("moods"):
            metadata.raw_data["moods"] = allmusic_metadata["moods"]
        if allmusic_metadata.get("themes"):
            metadata.raw_data["themes"] = allmusic_metadata["themes"]
        if allmusic_metadata.get("active_years"):
            metadata.raw_data["active_years"] = allmusic_metadata["active_years"]
        if allmusic_metadata.get("discography"):
            metadata.raw_data["discography"] = allmusic_metadata["discography"]
        if allmusic_metadata.get("allmusic_rating"):
            metadata.raw_data["allmusic_rating"] = allmusic_metadata["allmusic_rating"]
        if allmusic_metadata.get("allmusic_url"):
            metadata.raw_data["allmusic_url"] = allmusic_metadata["allmusic_url"]
            # Extract AllMusic ID from URL for frontend linking
            allmusic_url = allmusic_metadata["allmusic_url"]
            if "/artist/" in allmusic_url:
                # Extract ID from URL like https://www.allmusic.com/artist/the-beatles-mn0000754032
                allmusic_id = allmusic_url.split("/artist/")[-1].split("-")[-1]
                metadata.raw_data["allmusic_id"] = allmusic_id

        return metadata

    except Exception as e:
        logger.error(f"Error getting AllMusic metadata: {e}")
        return None


async def get_wikipedia_metadata(
    service, artist_data: Dict
) -> Optional[ArtistMetadata]:
    """Get basic metadata from Wikipedia (primarily thumbnails for now)"""
    try:
        # For now, Wikipedia service only provides thumbnails
        # This is a placeholder for future Wikipedia biography integration
        thumbnail_url = service.wikipedia.search_artist_thumbnail(artist_data["name"])

        if thumbnail_url:
            # Construct Wikipedia article URL for the artist
            artist_name_clean = artist_data["name"].replace(" ", "_")
            wikipedia_url = f"https://en.wikipedia.org/wiki/{artist_name_clean}"

            # Create minimal metadata with thumbnail and URL
            metadata = ArtistMetadata(
                name=artist_data["name"],
                source="wikipedia",
                confidence=0.7,  # Lower confidence since we're only getting thumbnails
                images=[{"url": thumbnail_url, "source": "wikipedia"}],
                raw_data={
                    "wikipedia_thumbnail": thumbnail_url,
                    "wikipedia_url": wikipedia_url,
                },
            )
            return metadata

        return None

    except Exception as e:
        logger.error(f"Error getting Wikipedia metadata: {e}")
        return None
