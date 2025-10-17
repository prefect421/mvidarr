"""
Artist Metadata Enrichment Module for MVidarr
Extracted from metadata_enrichment_service.py for better modularity

This module handles all artist-specific metadata enrichment operations:
- Multi-source artist metadata gathering (Spotify, Last.fm, MusicBrainz, AllMusic, Wikipedia, IMVDb)
- Intelligent metadata aggregation and conflict resolution
- Artist record updates with enriched data
- Metadata freshness checks and caching
- Batch artist enrichment operations
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.database.connection import get_db
from src.database.models import Artist
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.metadata_artist_enricher")


async def enrich_artist_metadata(
    service,
    artist_id: int,
    force_refresh: bool = False,
    app_context=None,
    progress_callback=None,
    session=None,
):
    """
    Enrich artist metadata from multiple sources with intelligent aggregation

    Args:
        service: MetadataEnrichmentService instance with configured services
        artist_id: ID of the artist to enrich
        force_refresh: Force refresh even if metadata is fresh
        app_context: Flask app context for database access
        progress_callback: Optional callback for progress updates
        session: Optional database session to use

    Returns:
        EnrichmentResult with success status and enriched data
    """
    from src.services.metadata_enrichment_service import EnrichmentResult

    start_time = time.time()
    result = EnrichmentResult(success=False, artist_id=artist_id)

    # Set up Flask app context if provided to ensure database and settings access
    app_context_manager = None
    if app_context:
        app_context_manager = app_context.app_context()
        app_context_manager.__enter__()

    try:
        # Use provided session or create a new one
        if session is not None:
            # Use the provided session (don't create a context manager)
            return await _enrich_artist_with_session(
                service,
                session,
                artist_id,
                force_refresh,
                app_context,
                progress_callback,
                result,
                start_time,
            )
        else:
            # Use a SINGLE session throughout the entire enrichment process
            with get_db() as session:
                # Mark that we created this session so we know to commit
                session.info["_created_by_enrich_artist"] = True
                return await _enrich_artist_with_session(
                    service,
                    session,
                    artist_id,
                    force_refresh,
                    app_context,
                    progress_callback,
                    result,
                    start_time,
                )

    except Exception as e:
        logger.error(f"Error enriching metadata for artist {artist_id}: {str(e)}")
        result.errors.append(str(e))
    finally:
        # Clean up Flask app context
        if app_context_manager:
            try:
                app_context_manager.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error cleaning up app context: {e}")

    result.processing_time = time.time() - start_time
    return result


async def _enrich_artist_with_session(
    service,
    session,
    artist_id: int,
    force_refresh: bool,
    app_context,
    progress_callback,
    result,
    start_time,
):
    """Helper method to perform artist enrichment with an existing session"""

    artist = session.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        result.errors.append(f"Artist with ID {artist_id} not found")
        return result

    # Store artist name for logging
    artist_name = artist.name

    logger.info(
        f"🔄 ENRICHMENT DEBUG: Artist {artist_name} - force_refresh={force_refresh}"
    )

    # Check if we need to refresh metadata
    is_fresh = _is_metadata_fresh(service, artist)
    logger.info(
        f"🔄 ENRICHMENT DEBUG: Artist {artist_name} - metadata_is_fresh={is_fresh}"
    )

    if not force_refresh and is_fresh:
        logger.info(
            f"🔄 ENRICHMENT SKIPPED: Artist {artist_name} metadata is fresh and force_refresh=False"
        )
        result.success = True
        result.confidence_score = 0.8  # Assume good confidence for cached data
        return result

    logger.info(f"Starting metadata enrichment for artist: {artist_name}")

    # Create a simple artist data structure for API calls
    artist_data = {
        "id": artist.id,
        "name": artist.name,
        "spotify_id": artist.spotify_id,
        "lastfm_name": artist.lastfm_name,
        "imvdb_id": artist.imvdb_id,
    }

    # Gather metadata from all sources
    if progress_callback:
        progress_callback(40, "Gathering metadata from external sources...")
    metadata_sources = await service._gather_all_sources_metadata(
        artist_data, progress_callback
    )

    if not metadata_sources:
        result.errors.append("No metadata found from any source")
        return result

    # Aggregate and resolve conflicts
    if progress_callback:
        progress_callback(80, "Aggregating and resolving metadata conflicts...")

    logger.info(
        f"🔄 Starting metadata aggregation for {artist_name} with {len(metadata_sources)} sources"
    )
    try:
        # Import the standalone aggregation function
        from src.services.metadata_aggregators import aggregate_metadata

        # Add timeout to prevent hanging
        async with asyncio.timeout(30):  # 30 second timeout for aggregation
            unified_metadata = aggregate_metadata(
                metadata_sources,
                source_weights=service.source_weights,
                genre_aggregation_threshold=service.genre_aggregation_threshold,
                similar_artists_limit=service.similar_artists_limit,
            )
        logger.info(f"✅ Metadata aggregation complete for {artist_name}")
    except asyncio.TimeoutError:
        error_msg = f"Metadata aggregation timed out after 30 seconds for {artist_name}"
        logger.error(f"❌ {error_msg}")
        result.errors.append(error_msg)
        if progress_callback:
            progress_callback(100, "Error: Aggregation timed out")
        return result
    except Exception as e:
        error_msg = f"Metadata aggregation failed for {artist_name}: {str(e)}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        result.errors.append(error_msg)
        if progress_callback:
            progress_callback(100, f"Error: {str(e)[:50]}")
        return result

    # Update artist record using the SAME session
    if progress_callback:
        progress_callback(90, "Updating artist record with enriched metadata...")

    try:
        # Add detailed logging for debugging
        logger.info(f"About to update artist record for {artist_name}")
        # No need to re-query - we already have the artist object in this session
        updated_fields = _update_artist_record(
            service, session, artist, unified_metadata, force_refresh
        )
        logger.info(
            f"Successfully updated artist record for {artist_name}: {updated_fields}"
        )
    except Exception as e:
        logger.error(f"ERROR in _update_artist_record for {artist_name}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details:", exc_info=True)
        raise

    logger.info(f"Committing enriched metadata for {artist_name}: {updated_fields}")

    if progress_callback:
        progress_callback(95, "Saving changes to database...")

    # Flush changes to database before verification
    session.flush()

    # Verify the data was actually saved BEFORE final commit
    verification = session.query(Artist).filter(Artist.id == artist_id).first()
    if verification and verification.imvdb_metadata:
        logger.info(
            f"Pre-commit verification: Artist {artist_name} has metadata with enrichment_date: {verification.imvdb_metadata.get('enrichment_date')}"
        )
    else:
        logger.error(
            f"Pre-commit verification failed: Artist {artist_name} metadata was not updated properly"
        )

    # Only commit if we're managing our own session (session was created in this method)
    # If session was passed from outside (like from video enrichment), let the caller commit
    if session.info.get("_created_by_enrich_artist"):
        session.commit()
        logger.info(f"Successfully committed enriched metadata for {artist_name}")

    if progress_callback:
        progress_callback(98, "Verifying saved data...")

    # Verify the data was actually saved
    session.refresh(verification)
    verification = session.query(Artist).filter(Artist.id == artist_id).first()
    if verification and verification.imvdb_metadata:
        logger.info(
            f"Verification: Artist {artist_name} now has metadata with enrichment_date: {verification.imvdb_metadata.get('enrichment_date')}"
        )
    else:
        logger.error(
            f"Verification failed: Artist {artist_name} metadata was not saved properly"
        )

    # Validate that meaningful enrichment data was actually gathered
    meaningful_fields = [
        unified_metadata.biography,
        unified_metadata.related_artists,
        unified_metadata.top_tracks,
        unified_metadata.images,
        unified_metadata.popularity,
        unified_metadata.followers,
        unified_metadata.playcount,
        unified_metadata.listeners,
        unified_metadata.genres,  # Include genres as meaningful data
        unified_metadata.similar_artists,  # Include similar artists as meaningful data
    ]

    has_meaningful_data = any(field for field in meaningful_fields)

    logger.info(f"Meaningful data check for {artist_name}: {has_meaningful_data}")
    logger.info(
        f"Meaningful fields content: {[(i, bool(field)) for i, field in enumerate(meaningful_fields)]}"
    )

    if not has_meaningful_data:
        result.errors.append(
            f"No meaningful enrichment data found for {artist_name}. "
            f"Sources returned basic data only: {list(metadata_sources.keys())}"
        )
        logger.warning(
            f"Enrichment failed for {artist_name}: no meaningful data from {list(metadata_sources.keys())}"
        )
        return result

    # Build successful result
    result.success = True
    result.sources_used = list(metadata_sources.keys())
    result.enriched_fields = updated_fields  # Fields that were actually updated
    result.metadata_found = updated_fields
    result.confidence_score = unified_metadata.confidence
    result.processing_time = time.time() - start_time

    # Final progress update
    if progress_callback:
        progress_callback(
            100, f"Enrichment completed! Updated: {', '.join(updated_fields)}"
        )

    logger.info(
        f"Successfully enriched metadata for {artist_name} using sources: {result.sources_used}"
    )

    return result


def _update_artist_record(
    service,
    session: Session,
    artist: Artist,
    metadata,
    force_refresh: bool = False,
) -> Dict:
    """Update artist record with aggregated metadata"""
    updated_fields = {}

    # CRITICAL FIX: Ensure artist is attached to the session
    # The artist object might be detached from the session, causing DetachedInstanceError
    # when accessing lazy-loaded attributes. Re-attach it to the current session.
    if artist not in session:
        artist = session.merge(artist)

    # Alternatively, we can use session.add(artist) but merge is safer for detached objects
    # session.add(artist)

    # Update external IDs
    if metadata.spotify_id and artist.spotify_id != metadata.spotify_id:
        artist.spotify_id = metadata.spotify_id
        updated_fields["spotify_id"] = metadata.spotify_id

    if metadata.lastfm_name and artist.lastfm_name != metadata.lastfm_name:
        artist.lastfm_name = metadata.lastfm_name
        updated_fields["lastfm_name"] = metadata.lastfm_name

    if metadata.imvdb_id and artist.imvdb_id != metadata.imvdb_id:
        artist.imvdb_id = metadata.imvdb_id
        updated_fields["imvdb_id"] = metadata.imvdb_id

    # Store MusicBrainz ID in metadata JSON since there's no dedicated field
    if metadata.mbid:
        if not artist.imvdb_metadata:
            artist.imvdb_metadata = {}
        if artist.imvdb_metadata.get("musicbrainz_id") != metadata.mbid:
            artist.imvdb_metadata["musicbrainz_id"] = metadata.mbid
            updated_fields["musicbrainz_id"] = metadata.mbid

    # Store AllMusic ID and URL from enriched metadata
    if metadata.raw_data.get("allmusic_id"):
        if not artist.imvdb_metadata:
            artist.imvdb_metadata = {}
        if artist.imvdb_metadata.get("allmusic_id") != metadata.raw_data["allmusic_id"]:
            artist.imvdb_metadata["allmusic_id"] = metadata.raw_data["allmusic_id"]
            updated_fields["allmusic_id"] = metadata.raw_data["allmusic_id"]

    if metadata.raw_data.get("allmusic_url"):
        if not artist.imvdb_metadata:
            artist.imvdb_metadata = {}
        if (
            artist.imvdb_metadata.get("allmusic_url")
            != metadata.raw_data["allmusic_url"]
        ):
            artist.imvdb_metadata["allmusic_url"] = metadata.raw_data["allmusic_url"]
            updated_fields["allmusic_url"] = metadata.raw_data["allmusic_url"]

    # Store Wikipedia URL from enriched metadata
    if metadata.raw_data.get("wikipedia_url"):
        if not artist.imvdb_metadata:
            artist.imvdb_metadata = {}
        if (
            artist.imvdb_metadata.get("wikipedia_url")
            != metadata.raw_data["wikipedia_url"]
        ):
            artist.imvdb_metadata["wikipedia_url"] = metadata.raw_data["wikipedia_url"]
            updated_fields["wikipedia_url"] = metadata.raw_data["wikipedia_url"]

    # Update genres
    if metadata.genres:
        genres_list = metadata.genres
        if artist.genres != genres_list:
            artist.genres = genres_list  # Store as JSON array
            updated_fields["genres"] = genres_list

    # Extract extended information directly from raw data
    extended_info = {}
    if metadata.raw_data:
        # Extract from various sources
        for source_name, source_data in metadata.raw_data.get("sources", {}).items():
            if isinstance(source_data, dict):
                # Extract labels
                if source_data.get("labels") and not extended_info.get("labels"):
                    extended_info["labels"] = source_data["labels"]
                # Extract members
                if source_data.get("members") and not extended_info.get("members"):
                    extended_info["members"] = source_data["members"]
                # Extract formed year
                if source_data.get("formed_year") and not extended_info.get(
                    "formed_year"
                ):
                    extended_info["formed_year"] = source_data["formed_year"]
                # Extract disbanded year
                if source_data.get("disbanded_year") and not extended_info.get(
                    "disbanded_year"
                ):
                    extended_info["disbanded_year"] = source_data["disbanded_year"]
                # Extract origin country
                if source_data.get("origin_country") and not extended_info.get(
                    "origin_country"
                ):
                    extended_info["origin_country"] = source_data["origin_country"]

    # Update labels from enriched metadata
    if extended_info.get("labels"):
        labels_list = extended_info["labels"]
        if isinstance(labels_list, str):
            labels_list = [labels_list]  # Convert single string to list
        if artist.labels != labels_list:
            artist.labels = labels_list
            updated_fields["labels"] = labels_list

    # Update members from enriched metadata
    if extended_info.get("members"):
        members_str = extended_info["members"]
        if isinstance(members_str, list):
            members_str = ", ".join(members_str)  # Convert list to string
        if artist.members != members_str:
            artist.members = members_str
            updated_fields["members"] = members_str

    # Extract external links directly from metadata
    external_links = {}
    if metadata.raw_data:
        # Extract from various sources
        for source_name, source_data in metadata.raw_data.get("sources", {}).items():
            if isinstance(source_data, dict):
                # Extract website URL
                if source_data.get("website_url") and not external_links.get(
                    "website_url"
                ):
                    external_links["website_url"] = source_data["website_url"]
                # Extract Spotify URL
                if source_data.get("spotify_url") and not external_links.get(
                    "spotify_url"
                ):
                    external_links["spotify_url"] = source_data["spotify_url"]
                # Extract YouTube URL
                if source_data.get("youtube_url") and not external_links.get(
                    "youtube_url"
                ):
                    external_links["youtube_url"] = source_data["youtube_url"]
                # Extract Apple Music URL
                if source_data.get("apple_music_url") and not external_links.get(
                    "apple_music_url"
                ):
                    external_links["apple_music_url"] = source_data["apple_music_url"]
                # Extract Twitter URL
                if source_data.get("twitter_url") and not external_links.get(
                    "twitter_url"
                ):
                    external_links["twitter_url"] = source_data["twitter_url"]
                # Extract Facebook URL
                if source_data.get("facebook_url") and not external_links.get(
                    "facebook_url"
                ):
                    external_links["facebook_url"] = source_data["facebook_url"]
                # Extract Instagram URL
                if source_data.get("instagram_url") and not external_links.get(
                    "instagram_url"
                ):
                    external_links["instagram_url"] = source_data["instagram_url"]

    # Update metadata JSON
    enriched_metadata = {
        "enrichment_date": datetime.now().isoformat(),
        "confidence_score": metadata.confidence,
        "sources_used": list(metadata.raw_data.get("sources", {}).keys()),
        "popularity": metadata.popularity,
        "followers": metadata.followers,
        "biography": metadata.biography,
        "related_artists": metadata.related_artists,
        "top_tracks": metadata.top_tracks,
        "images": metadata.images,
        "playcount": metadata.playcount,
        "listeners": metadata.listeners,
        "user_playcount": metadata.user_playcount,
        # Extended Information fields
        "formed_year": extended_info.get("formed_year"),
        "disbanded_year": extended_info.get("disbanded_year"),
        "origin_country": extended_info.get("origin_country"),
        "labels": extended_info.get("labels"),
        "members": extended_info.get("members"),
        # External Links fields
        "website_url": external_links.get("website_url"),
        "spotify_url": external_links.get("spotify_url"),
        "youtube_url": external_links.get("youtube_url"),
        "apple_music_url": external_links.get("apple_music_url"),
        "twitter_url": external_links.get("twitter_url"),
        "facebook_url": external_links.get("facebook_url"),
        "instagram_url": external_links.get("instagram_url"),
    }

    # Store in imvdb_metadata field (repurpose as general metadata storage)
    existing_metadata = (
        artist.imvdb_metadata if isinstance(artist.imvdb_metadata, dict) else {}
    )

    # Merge enriched metadata, ensuring enriched data takes precedence over existing null values
    logger.info(
        f"🔄 METADATA MERGE: Before merge - existing images: {len(existing_metadata.get('images', []))} items"
    )
    logger.info(
        f"🔄 METADATA MERGE: New enriched images: {len(enriched_metadata.get('images', []))} items"
    )

    for key, value in enriched_metadata.items():
        # Only update if the enriched value is meaningful (not None, not empty)
        if value is not None and value != "" and value != []:
            existing_metadata[key] = value
            if key == "images":
                logger.info(
                    f"🔄 METADATA MERGE: Updated {key} with new non-empty value ({len(value)} items)"
                )
        # If existing field is null/empty and we have a meaningful enriched value, use it
        elif key not in existing_metadata or existing_metadata[key] in [
            None,
            "",
            [],
        ]:
            existing_metadata[key] = value
            if key == "images":
                logger.info(
                    f"🔄 METADATA MERGE: Set {key} with empty value (existing was empty)"
                )
        else:
            if key == "images":
                logger.info(
                    f"🔄 METADATA MERGE: Preserved existing {key} ({len(existing_metadata[key])} items) - new was empty"
                )

    logger.info(
        f"🔄 METADATA MERGE: After merge - final images: {len(existing_metadata.get('images', []))} items"
    )

    # Store thumbnail URL for later download (avoid network delays during enrichment)
    if (not artist.thumbnail_url or force_refresh) and existing_metadata.get("images"):
        try:
            images = existing_metadata["images"]
            # Prefer high-quality images (largest size first)
            best_image = None

            # Define size priority for Last.fm images (larger is better)
            lastfm_size_priority = {
                "mega": 5,
                "extralarge": 4,
                "large": 3,
                "medium": 2,
                "small": 1,
                "": 0,  # Unknown size
            }

            for image in images:
                if isinstance(image, dict):
                    # Handle both standard "url" field and LastFM "#text" field
                    image_url = image.get("url") or image.get("#text")
                    if image_url:
                        # Prefer images with known dimensions (larger is better)
                        if image.get("width") and image.get("height"):
                            if not best_image or (
                                image.get("width", 0) * image.get("height", 0)
                                > (
                                    best_image.get("width", 0)
                                    * best_image.get("height", 0)
                                )
                            ):
                                best_image = image
                        # Handle Last.fm size field priority
                        elif image.get("size") is not None:
                            current_priority = lastfm_size_priority.get(
                                image.get("size", ""), 0
                            )
                            best_priority = lastfm_size_priority.get(
                                best_image.get("size", "") if best_image else "", -1
                            )
                            if current_priority > best_priority:
                                best_image = image
                        elif not best_image:
                            best_image = image

            # Find the best non-placeholder image
            selected_image = None
            selected_image_url = None

            # Sort images by preference (best_image first, then others)
            image_candidates = []
            if best_image:
                image_candidates.append(best_image)

            # Add other images as fallbacks
            for image in images:
                if isinstance(image, dict) and image != best_image:
                    image_candidates.append(image)

            # Find first non-placeholder image
            for candidate in image_candidates:
                candidate_url = candidate.get("url") or candidate.get("#text")
                if candidate_url and not service._is_placeholder_image(candidate_url):
                    selected_image = candidate
                    selected_image_url = candidate_url
                    break

            if selected_image_url:
                # Store thumbnail URL for later background download (avoid hanging here)
                artist.thumbnail_url = selected_image_url
                updated_fields["thumbnail_url"] = artist.thumbnail_url

                # Store thumbnail info in metadata for later processing
                existing_metadata["thumbnail_pending"] = True
                existing_metadata["thumbnail_source"] = selected_image.get(
                    "source", "unknown"
                )
                existing_metadata["best_thumbnail_url"] = selected_image_url

                logger.info(
                    f"Stored thumbnail URL for artist {artist.name}: {selected_image_url}"
                )
            else:
                logger.info(
                    f"No valid (non-placeholder) thumbnail found for artist {artist.name}"
                )

        except Exception as e:
            logger.error(f"Error processing artist thumbnail metadata: {e}")

    # Ensure enrichment_date is always updated to show fresh data
    existing_metadata["enrichment_date"] = datetime.now().isoformat()
    existing_metadata["sources_used"] = list(
        metadata.raw_data.get("sources", {}).keys()
    )
    existing_metadata["confidence_score"] = metadata.confidence

    logger.info(f"Setting artist.imvdb_metadata to: {existing_metadata}")
    logger.info(f"Artist.imvdb_metadata before assignment: {artist.imvdb_metadata}")

    artist.imvdb_metadata = existing_metadata

    # CRITICAL: Mark the JSON field as modified so SQLAlchemy knows to save it
    try:
        flag_modified(artist, "imvdb_metadata")
        logger.info(
            f"Successfully flagged imvdb_metadata as modified for {artist.name}"
        )
    except Exception as e:
        logger.error(
            f"Failed to flag imvdb_metadata as modified for {artist.name}: {e}"
        )
        # Continue anyway - the assignment might still work
        pass

    logger.info(f"Artist.imvdb_metadata after assignment: {artist.imvdb_metadata}")
    logger.info(f"Marked imvdb_metadata as modified for SQLAlchemy tracking")
    updated_fields["metadata"] = enriched_metadata

    # Update timestamps
    artist.updated_at = datetime.now()
    updated_fields["updated_at"] = artist.updated_at

    return updated_fields


def _is_metadata_fresh(service, artist: Artist) -> bool:
    """Check if artist metadata is fresh enough AND contains meaningful data"""
    if not artist.imvdb_metadata or not isinstance(artist.imvdb_metadata, dict):
        return False

    enrichment_date_str = artist.imvdb_metadata.get("enrichment_date")
    if not enrichment_date_str:
        return False

    # Check if the cached data actually contains meaningful metadata
    metadata = artist.imvdb_metadata
    meaningful_fields = [
        metadata.get("biography"),
        metadata.get("related_artists"),
        metadata.get("top_tracks"),
        metadata.get("images"),
        metadata.get("popularity"),
        metadata.get("followers"),
        metadata.get("playcount"),
        metadata.get("listeners"),
        metadata.get("genres"),
        metadata.get("similar_artists"),
    ]

    # Only consider metadata "fresh" if it has meaningful data
    has_meaningful_data = any(
        field and field != [] and field != {} and field != ""
        for field in meaningful_fields
    )

    if not has_meaningful_data:
        logger.debug(
            f"Artist {artist.name} has enrichment_date but no meaningful data - forcing refresh"
        )
        return False

    try:
        enrichment_date = datetime.fromisoformat(enrichment_date_str)
        is_fresh = datetime.now() - enrichment_date < timedelta(
            hours=service.cache_duration_hours
        )
        if is_fresh:
            logger.debug(
                f"Artist {artist.name} metadata is fresh with meaningful data - using cache"
            )
        return is_fresh
    except (ValueError, TypeError):
        return False


def _is_artist_match(service, name1: str, name2: str) -> bool:
    """Check if two artist names are a match"""
    return _calculate_name_similarity(name1, name2) >= service.min_confidence_threshold


def _calculate_name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two artist names"""
    if not name1 or not name2:
        return 0.0

    name1_clean = name1.lower().strip()
    name2_clean = name2.lower().strip()

    # Exact match
    if name1_clean == name2_clean:
        return 1.0

    # Check if one contains the other
    if name1_clean in name2_clean or name2_clean in name1_clean:
        return 0.9

    # Simple token matching
    tokens1 = set(name1_clean.split())
    tokens2 = set(name2_clean.split())

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)

    return len(intersection) / len(union) if union else 0.0


async def enrich_multiple_artists(
    service, artist_ids: List[int], force_refresh: bool = False, app_context=None
) -> List:
    """Enrich metadata for multiple artists"""
    from src.services.metadata_enrichment_service import EnrichmentResult

    results = []

    for artist_id in artist_ids:
        try:
            result = await enrich_artist_metadata(
                service, artist_id, force_refresh, app_context
            )
            results.append(result)

            # Rate limiting between requests
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Failed to enrich artist {artist_id}: {e}")
            results.append(
                EnrichmentResult(success=False, artist_id=artist_id, errors=[str(e)])
            )

    return results
