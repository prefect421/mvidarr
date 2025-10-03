"""
Service for automatically processing newly added artists with auto-match and metadata enrichment
"""

import asyncio
from typing import Any, Dict

from flask import current_app

from src.database.models import Artist
from src.utils.logger import get_logger

logger = get_logger("mvidarr.artist_auto_processing")


class ArtistAutoProcessingService:
    """Service for auto-match and metadata enrichment of newly created artists"""

    @staticmethod
    def process_new_artist(artist: Artist, session) -> Dict[str, Any]:
        """
        Process a newly created artist with auto-match and metadata enrichment

        Args:
            artist: The newly created Artist object
            session: Database session

        Returns:
            Dict containing processing results
        """
        # Extract essential data immediately to avoid session issues
        try:
            artist_id = artist.id
            artist_name = artist.name
        except Exception as e:
            logger.error(f"Failed to extract artist data: {e}")
            return {
                "auto_match": {"matches": {}, "match_count": 0},
                "metadata_enrichment": None,
                "errors": [f"Failed to extract artist data: {e}"],
            }

        logger.info(
            f"Auto-processing newly created artist: {artist_name} (ID: {artist_id})"
        )

        results = {
            "auto_match": {"matches": {}, "match_count": 0},
            "metadata_enrichment": None,
            "thumbnail_generation": None,
            "errors": [],
        }

        try:
            # Run auto-match - pass only the ID and name to avoid session issues
            logger.debug(f"Starting auto-match for {artist_name} (ID: {artist_id})")
            auto_match_results = ArtistAutoProcessingService._run_auto_match(
                artist_id, artist_name, session
            )
            results["auto_match"] = auto_match_results
            logger.debug(f"Auto-match completed for {artist_name}")

            # Run metadata enrichment
            logger.debug(
                f"Starting metadata enrichment for {artist_name} (ID: {artist_id})"
            )
            try:
                enrichment_results = (
                    ArtistAutoProcessingService._run_metadata_enrichment(artist_id)
                )
                results["metadata_enrichment"] = enrichment_results
                logger.debug(f"Metadata enrichment completed for {artist_name}")
            except Exception as enrichment_error:
                logger.error(
                    f"Metadata enrichment failed for {artist_name}: {enrichment_error}"
                )
                logger.error(
                    f"Metadata enrichment traceback for {artist_name}:", exc_info=True
                )
                results["metadata_enrichment"] = {
                    "success": False,
                    "error": str(enrichment_error),
                }

            # Run thumbnail generation for new artist
            logger.debug(
                f"Starting thumbnail generation for {artist_name} (ID: {artist_id})"
            )
            try:
                thumbnail_results = (
                    ArtistAutoProcessingService._run_thumbnail_generation(
                        artist_id, artist_name
                    )
                )
                results["thumbnail_generation"] = thumbnail_results
                logger.debug(f"Thumbnail generation completed for {artist_name}")
            except Exception as thumbnail_error:
                logger.error(
                    f"Thumbnail generation failed for {artist_name}: {thumbnail_error}"
                )
                results["thumbnail_generation"] = {
                    "success": False,
                    "error": str(thumbnail_error),
                }

            logger.info(
                f"Auto-processing completed for {artist_name} - {auto_match_results['match_count']} services matched"
            )

        except Exception as e:
            error_msg = f"Auto-processing failed for artist {artist_name}: {e}"
            logger.error(error_msg)
            logger.error(f"Full traceback for {artist_name}:", exc_info=True)
            results["errors"].append(error_msg)

        return results

    @staticmethod
    def _run_auto_match(artist_id: int, artist_name: str, session) -> Dict[str, Any]:
        """Run auto-matching against external services"""
        # Get a fresh copy of the artist from the database to avoid session issues
        artist = session.query(Artist).filter_by(id=artist_id).first()
        if not artist:
            logger.error(f"Artist with ID {artist_id} not found in database")
            return {"matches": {}, "match_count": 0}

        matches = {}

        # Store pending updates to apply after all service calls complete
        pending_updates = {}

        try:
            # Import services for auto-match
            from src.services.imvdb_service import imvdb_service
            from src.services.lastfm_service import lastfm_service
            from src.services.musicbrainz_service import musicbrainz_service
            from src.services.spotify_service import spotify_service

            # Check current values from database to avoid session issues
            current_imvdb_id = artist.imvdb_id
            current_spotify_id = artist.spotify_id
            current_lastfm_name = artist.lastfm_name
            current_metadata = artist.imvdb_metadata or {}
            current_musicbrainz_id = current_metadata.get("musicbrainz_id")

            # IMVDb auto-match
            try:
                if not current_imvdb_id:  # Only if not already set
                    imvdb_match = imvdb_service.search_artist(artist_name)
                    if imvdb_match and imvdb_match.get("id"):
                        matches["imvdb"] = {
                            "id": imvdb_match["id"],
                            "name": imvdb_match.get("name"),
                            "url": imvdb_match.get("url"),
                        }
                        pending_updates["imvdb_id"] = str(imvdb_match["id"])
                        logger.info(
                            f"Auto-matched IMVDb ID: {imvdb_match['id']} for {artist_name}"
                        )
            except Exception as e:
                logger.warning(f"IMVDb auto-match failed for {artist_name}: {e}")

            # Spotify auto-match
            try:
                if not current_spotify_id:
                    spotify_results = spotify_service.search_artist(artist_name)
                    if spotify_results and spotify_results.get("artists", {}).get(
                        "items"
                    ):
                        best_match = spotify_results["artists"]["items"][0]
                        matches["spotify"] = {
                            "id": best_match.get("id"),
                            "name": best_match.get("name"),
                            "popularity": best_match.get("popularity"),
                            "followers": best_match.get("followers", {}).get("total"),
                        }
                        pending_updates["spotify_id"] = best_match.get("id")
                        logger.info(
                            f"Auto-matched Spotify ID: {best_match.get('id')} for {artist_name}"
                        )
            except Exception as e:
                logger.warning(f"Spotify auto-match failed for {artist_name}: {e}")

            # Last.fm auto-match
            try:
                if not current_lastfm_name:
                    lastfm_results = lastfm_service.search_artist(artist_name)
                    if lastfm_results:
                        match_data = (
                            lastfm_results[0]
                            if isinstance(lastfm_results, list)
                            else lastfm_results
                        )
                        matches["lastfm"] = {
                            "name": match_data.get("name"),
                            "mbid": match_data.get("mbid"),
                            "url": match_data.get("url"),
                            "listeners": match_data.get("listeners"),
                        }
                        pending_updates["lastfm_name"] = match_data.get(
                            "name", artist_name
                        )
                        logger.info(f"Auto-matched Last.fm for {artist_name}")
            except Exception as e:
                logger.warning(f"Last.fm auto-match failed for {artist_name}: {e}")

            # MusicBrainz auto-match
            try:
                if not current_musicbrainz_id:
                    mb_results = musicbrainz_service.search_artist(artist_name)
                    if mb_results and mb_results.get("artists"):
                        best_match = mb_results["artists"][0]
                        matches["musicbrainz"] = {
                            "id": best_match.get("id"),
                            "name": best_match.get("name"),
                            "disambiguation": best_match.get("disambiguation"),
                            "type": best_match.get("type"),
                        }
                        # Store MusicBrainz ID in metadata - defer this update too
                        updated_metadata = current_metadata.copy()
                        updated_metadata["musicbrainz_id"] = best_match.get("id")
                        pending_updates["imvdb_metadata"] = updated_metadata
                        logger.info(
                            f"Auto-matched MusicBrainz ID: {best_match.get('id')} for {artist_name}"
                        )
            except Exception as e:
                logger.warning(f"MusicBrainz auto-match failed for {artist_name}: {e}")

            # Now apply all pending updates at once
            if pending_updates:
                # Merge the artist instance to handle any session conflicts
                artist = session.merge(artist)

                for field, value in pending_updates.items():
                    setattr(artist, field, value)

                # Handle JSON field flagging for imvdb_metadata
                if "imvdb_metadata" in pending_updates:
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(artist, "imvdb_metadata")

                logger.debug(
                    f"Applied {len(pending_updates)} field updates to {artist_name}"
                )

        except Exception as e:
            logger.error(f"Auto-match process failed for {artist_name}: {e}")
            logger.error(f"Full auto-match traceback for {artist_name}:", exc_info=True)

        return {"matches": matches, "match_count": len(matches)}

    @staticmethod
    def _run_metadata_enrichment(artist_id: int) -> Dict[str, Any]:
        """Run metadata enrichment for the artist"""
        try:
            from src.services.metadata_enrichment_service import (
                metadata_enrichment_service,
            )

            # Run metadata enrichment with Flask context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                enrichment_result = loop.run_until_complete(
                    metadata_enrichment_service.enrich_artist_metadata(
                        artist_id, force_refresh=True, app_context=current_app
                    )
                )
                return enrichment_result
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Metadata enrichment failed for artist {artist_id}: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _run_thumbnail_generation(artist_id: int, artist_name: str) -> Dict[str, Any]:
        """Run thumbnail generation for the artist"""
        try:
            from src.services.imvdb_service import imvdb_service

            logger.info(
                f"Attempting thumbnail generation for {artist_name} (ID: {artist_id})"
            )

            # Try to get thumbnail from IMVDb service
            thumbnail_url = None
            if hasattr(imvdb_service, "get_artist_thumbnail"):
                try:
                    # Run the async method in a synchronous context
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        thumbnail_url = loop.run_until_complete(
                            imvdb_service.get_artist_thumbnail(artist_name)
                        )
                    finally:
                        loop.close()
                except Exception as imvdb_error:
                    logger.warning(
                        f"IMVDb thumbnail lookup failed for {artist_name}: {imvdb_error}"
                    )

            # Try alternative thumbnail sources if IMVDb fails
            if not thumbnail_url:
                try:
                    # Try to get thumbnail from any matched metadata services
                    from src.database.connection import get_db_session
                    from src.database.models import Artist

                    with next(get_db_session()) as session:
                        artist = session.query(Artist).filter_by(id=artist_id).first()
                        if artist:
                            # Check if we have Spotify ID and can get image from there
                            if artist.spotify_id:
                                try:
                                    from src.services.spotify_service import (
                                        spotify_service,
                                    )

                                    spotify_data = spotify_service.get_artist(
                                        artist.spotify_id
                                    )
                                    if spotify_data and spotify_data.get("images"):
                                        # Get the largest image
                                        images = spotify_data["images"]
                                        if images:
                                            thumbnail_url = images[0]["url"]
                                            logger.info(
                                                f"Found Spotify thumbnail for {artist_name}: {thumbnail_url}"
                                            )
                                except Exception as spotify_error:
                                    logger.warning(
                                        f"Spotify thumbnail lookup failed for {artist_name}: {spotify_error}"
                                    )

                            # Check if we have Last.fm data
                            if not thumbnail_url and artist.lastfm_name:
                                try:
                                    from src.services.lastfm_service import (
                                        lastfm_service,
                                    )

                                    lastfm_data = lastfm_service.get_artist_info(
                                        artist.lastfm_name
                                    )
                                    if lastfm_data and lastfm_data.get("image"):
                                        images = lastfm_data["image"]
                                        # Get the largest image (usually the last one)
                                        if images and isinstance(images, list):
                                            for img in reversed(images):
                                                if img.get("#text"):
                                                    thumbnail_url = img["#text"]
                                                    logger.info(
                                                        f"Found Last.fm thumbnail for {artist_name}: {thumbnail_url}"
                                                    )
                                                    break
                                except Exception as lastfm_error:
                                    logger.warning(
                                        f"Last.fm thumbnail lookup failed for {artist_name}: {lastfm_error}"
                                    )

                except Exception as alt_error:
                    logger.warning(
                        f"Alternative thumbnail lookup failed for {artist_name}: {alt_error}"
                    )

            if thumbnail_url:
                logger.info(
                    f"Successfully found thumbnail for {artist_name}: {thumbnail_url}"
                )
                return {
                    "success": True,
                    "thumbnail_url": thumbnail_url,
                    "source": "auto_discovery",
                }
            else:
                logger.info(f"No thumbnail found for {artist_name}")
                return {
                    "success": False,
                    "message": "No thumbnail sources available",
                    "searched_sources": ["imvdb", "spotify", "lastfm"],
                }

        except Exception as e:
            logger.error(f"Thumbnail generation failed for artist {artist_id}: {e}")
            return {"success": False, "error": str(e)}


# Convenience instance
artist_auto_processing_service = ArtistAutoProcessingService()
