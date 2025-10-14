"""
Video Metadata Enrichment Module for MVidarr

Extracted from metadata_enrichment_service.py to improve code modularity.
Handles video metadata enrichment from multiple sources including:
- IMVDb (Internet Music Video Database)
- Spotify (track and album metadata)
- Last.fm (track information and tags)
- MusicBrainz (authoritative music metadata)
- YouTube (video discovery and metadata)
- FFmpeg (local video file analysis)
- Lyrics search (Lyrics.ovh API)
"""

from datetime import datetime
from typing import Optional

import requests
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from src.database.connection import get_db
from src.database.models import Video
from src.services.imvdb_service import imvdb_service
from src.services.lastfm_service import lastfm_service
from src.services.metadata_models import EnrichmentResult
from src.services.spotify_service import spotify_service
from src.services.video_indexing_service import VideoIndexingService
from src.services.youtube_search_service import YouTubeSearchService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.video_enricher")


def search_lyrics_azlyrics(artist: str, title: str) -> Optional[str]:
    """Search for lyrics using Lyrics.ovh API (formerly azlyrics approach)"""
    try:
        # Clean artist and title for API request
        artist_clean = artist.strip()
        title_clean = title.strip()

        # URL encode the parameters to handle special characters
        import urllib.parse

        artist_encoded = urllib.parse.quote(artist_clean)
        title_encoded = urllib.parse.quote(title_clean)

        # Use the free Lyrics.ovh API
        url = f"https://api.lyrics.ovh/v1/{artist_encoded}/{title_encoded}"

        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            lyrics = data.get("lyrics", "")

            # Clean up the lyrics
            if lyrics:
                lyrics = lyrics.strip()
                # Remove excessive whitespace and normalize line breaks
                lyrics = "\n".join(
                    line.strip() for line in lyrics.split("\n") if line.strip()
                )

                # Check if we got substantial content (more than just a few words)
                if len(lyrics) > 50:
                    return lyrics

        return None

    except Exception as e:
        logger.warning(f"Lyrics.ovh search failed for {artist} - {title}: {e}")
        return None


async def enrich_video_metadata(
    video_id: int,
    youtube_search_service: YouTubeSearchService,
    force_refresh: bool = False,
) -> EnrichmentResult:
    """Enhanced video metadata enrichment using multiple sources

    Args:
        video_id: The ID of the video to enrich
        youtube_search_service: YouTube search service instance
        force_refresh: If True, refresh all metadata even if it already exists

    Returns:
        EnrichmentResult containing success status, updated fields, and sources used
    """
    try:
        with get_db() as session:
            # Eagerly load the video with its artist relationship to avoid lazy loading issues
            video = (
                session.query(Video)
                .options(joinedload(Video.artist))
                .filter(Video.id == video_id)
                .first()
            )

            if not video:
                return EnrichmentResult(
                    video_id=video_id, success=False, errors=["Video not found"]
                )

            if not video.artist:
                return EnrichmentResult(
                    video_id=video_id,
                    success=False,
                    errors=["No artist associated with video"],
                )

            # Extract data before API calls
            artist_name = video.artist.name
            video_title = video.title
            current_imvdb_id = video.imvdb_id

            logger.info(
                f"Enhanced enrichment for video: {video_title} by {artist_name}"
            )

            # Collect metadata from multiple sources
            metadata_sources = {}
            updated_fields = []
            errors = []

            # 1. IMVDb enrichment (re-enabled with improved handling)
            try:
                # Ensure video stays attached to session
                video = session.merge(video)

                if not current_imvdb_id or force_refresh:
                    # Search for video on IMVDb if not already linked
                    imvdb_videos = imvdb_service.search_videos(artist_name, video_title)

                    if imvdb_videos:
                        best_match = imvdb_service.find_best_video_match(
                            artist_name, video_title
                        )

                        if best_match:
                            metadata_sources["imvdb"] = best_match
                            imvdb_metadata = imvdb_service.extract_metadata(best_match)

                            # Apply IMVDb metadata with conflict resolution
                            if not video.imvdb_id and imvdb_metadata.get("imvdb_id"):
                                video.imvdb_id = str(imvdb_metadata["imvdb_id"])
                                updated_fields.append("imvdb_id")

                            if not video.year and imvdb_metadata.get("year"):
                                video.year = imvdb_metadata["year"]
                                updated_fields.append("year")

                            if not video.directors and imvdb_metadata.get("directors"):
                                video.directors = imvdb_metadata["directors"]
                                updated_fields.append("directors")

                            if not video.producers and imvdb_metadata.get("producers"):
                                video.producers = imvdb_metadata["producers"]
                                updated_fields.append("producers")

                            # Handle thumbnail extraction with validation and force refresh support
                            thumbnail_url = imvdb_metadata.get("thumbnail_url")
                            if (
                                thumbnail_url
                                and thumbnail_url != "https://imvdb.com/"
                                and len(thumbnail_url) > 20
                            ):
                                if (
                                    not video.thumbnail_url
                                    or force_refresh
                                    or not video.thumbnail_source
                                ):
                                    video.thumbnail_url = thumbnail_url
                                    video.thumbnail_source = "imvdb"
                                    updated_fields.extend(
                                        ["thumbnail_url", "thumbnail_source"]
                                    )
                                    logger.info(
                                        f"Added thumbnail from IMVDb for video {video_id}: {video.thumbnail_url}"
                                    )
                            elif video.thumbnail_url:
                                logger.debug(
                                    f"Video {video_id} already has thumbnail: {video.thumbnail_url}"
                                )
                            elif not thumbnail_url:
                                logger.debug(
                                    f"No valid thumbnail available in IMVDb metadata for video {video_id}"
                                )
                            else:
                                logger.debug(
                                    f"Rejected invalid IMVDb thumbnail for video {video_id}: {thumbnail_url}"
                                )

                            # Store raw IMVDb metadata
                            video.imvdb_metadata = imvdb_metadata.get("raw_metadata")
                            updated_fields.append("imvdb_metadata")

            except Exception as e:
                errors.append(f"IMVDb enrichment failed: {str(e)}")
                logger.warning(f"IMVDb enrichment failed for video {video_id}: {e}")

            # 2. Enhanced Spotify enrichment
            try:
                # Ensure video stays attached to session
                video = session.merge(video)

                if video.artist.spotify_id:
                    # Search for track on Spotify with improved matching
                    track_search = spotify_service.search_tracks(
                        f'track:"{video_title}" artist:"{artist_name}"'
                    )

                    if not track_search or not track_search.get("tracks", {}).get(
                        "items"
                    ):
                        # Fallback to broader search
                        track_search = spotify_service.search_tracks(
                            f"{video_title} {artist_name}"
                        )

                    if track_search and track_search.get("tracks", {}).get("items"):
                        best_track = track_search["tracks"]["items"][0]
                        metadata_sources["spotify"] = best_track

                        # Enhanced Spotify metadata extraction
                        album_data = best_track.get("album", {})

                        if not video.album and album_data.get("name"):
                            video.album = album_data["name"]
                            updated_fields.append("album")

                        if not video.year and album_data.get("release_date"):
                            try:
                                release_year = album_data["release_date"].split("-")[0]
                                video.year = int(release_year)
                                updated_fields.append("year")
                            except (ValueError, IndexError):
                                pass

                        # Fallback: Extract year from YouTube upload_date if not set by MusicBrainz
                        if not video.year and video.video_metadata:
                            upload_date = video.video_metadata.get("upload_date")
                            if upload_date:
                                try:
                                    # upload_date format is YYYYMMDD
                                    if (
                                        isinstance(upload_date, str)
                                        and len(upload_date) >= 4
                                    ):
                                        video.year = int(upload_date[:4])
                                        updated_fields.append("year")
                                        logger.info(
                                            f"Extracted year {video.year} from YouTube upload_date for video {video_id}"
                                        )
                                except (ValueError, TypeError) as e:
                                    logger.debug(
                                        f"Could not extract year from upload_date '{upload_date}': {e}"
                                    )

                        # Extract track duration
                        if not video.duration and best_track.get("duration_ms"):
                            video.duration = (
                                best_track["duration_ms"] // 1000
                            )  # Convert to seconds
                            updated_fields.append("duration")

                        # Get genres from artist or album
                        if not video.genres:
                            # Try to get genres from artist
                            if video.artist.spotify_id:
                                try:
                                    artist_data = spotify_service.get_artist(
                                        video.artist.spotify_id
                                    )
                                    if artist_data and artist_data.get("genres"):
                                        video.genres = artist_data["genres"][
                                            :3
                                        ]  # Top 3 genres
                                        updated_fields.append("genres")
                                except Exception:
                                    pass

                        # Extract Spotify album artwork as thumbnail if needed
                        if (
                            not video.thumbnail_url or force_refresh
                        ) and album_data.get("images"):
                            # Get the highest quality image (first one is usually the best)
                            album_images = album_data["images"]
                            if album_images and len(album_images) > 0:
                                spotify_thumbnail_url = album_images[0].get("url")
                                if spotify_thumbnail_url:
                                    video.thumbnail_url = spotify_thumbnail_url
                                    video.thumbnail_source = "spotify"
                                    updated_fields.extend(
                                        ["thumbnail_url", "thumbnail_source"]
                                    )
                                    metadata_sources["Spotify Album Art"] = (
                                        "Thumbnail extraction"
                                    )
                                    logger.info(
                                        f"Added Spotify album art thumbnail for video {video_id}: {spotify_thumbnail_url}"
                                    )

                        # Store additional metadata
                        video_metadata = video.video_metadata or {}
                        video_metadata.update(
                            {
                                "spotify_track_id": best_track.get("id"),
                                "spotify_popularity": best_track.get("popularity"),
                                "spotify_preview_url": best_track.get("preview_url"),
                                "spotify_album_type": album_data.get("album_type"),
                                "spotify_album_images": album_data.get("images", []),
                            }
                        )
                        video.video_metadata = video_metadata
                        updated_fields.append("video_metadata")

            except Exception as e:
                errors.append(f"Spotify enrichment failed: {str(e)}")
                logger.warning(f"Spotify enrichment failed for video {video_id}: {e}")

            # 3. Enhanced Last.fm enrichment
            try:
                # Ensure video stays attached to session
                video = session.merge(video)

                if video.artist.lastfm_name:
                    # Get detailed track info from Last.fm
                    track_info = lastfm_service.get_track_info(
                        video.artist.lastfm_name, video_title
                    )

                    if track_info:
                        metadata_sources["lastfm"] = track_info

                        # Album information
                        album_data = track_info.get("album", {})
                        if not video.album and album_data.get("title"):
                            video.album = album_data["title"]
                            updated_fields.append("album")

                        # Track duration
                        if not video.duration and track_info.get("duration"):
                            try:
                                video.duration = (
                                    int(track_info["duration"]) // 1000
                                )  # Convert from ms
                                updated_fields.append("duration")
                            except (ValueError, TypeError):
                                pass

                        # Genres from tags
                        if not video.genres and track_info.get("toptags", {}).get(
                            "tag"
                        ):
                            tags = track_info["toptags"]["tag"]
                            if isinstance(tags, list):
                                genre_tags = [tag["name"] for tag in tags[:3]]
                                video.genres = genre_tags
                                updated_fields.append("genres")

                        # Additional metadata
                        video_metadata = video.video_metadata or {}
                        video_metadata.update(
                            {
                                "lastfm_play_count": track_info.get("playcount"),
                                "lastfm_listeners": track_info.get("listeners"),
                                "lastfm_url": track_info.get("url"),
                            }
                        )
                        video.video_metadata = video_metadata
                        if "video_metadata" not in updated_fields:
                            updated_fields.append("video_metadata")

            except Exception as e:
                errors.append(f"Last.fm enrichment failed: {str(e)}")
                logger.warning(f"Last.fm enrichment failed for video {video_id}: {e}")

            # 4. MusicBrainz enrichment (for authoritative metadata)
            try:
                # Ensure video stays attached to session
                video = session.merge(video)

                if video.artist.mbid or not video.album:
                    # Search for recording in MusicBrainz
                    # Note: This is a basic implementation - MusicBrainz recording search would need to be added to the service
                    logger.debug(
                        f"MusicBrainz recording enrichment not yet implemented for video {video_id}"
                    )
                    # TODO: Implement MusicBrainz recording search when service supports it

            except Exception as e:
                errors.append(f"MusicBrainz enrichment failed: {str(e)}")
                logger.warning(
                    f"MusicBrainz enrichment failed for video {video_id}: {e}"
                )

            # 5. YouTube ID discovery (if we don't have YouTube ID)
            try:
                # Ensure video stays attached to session
                video = session.merge(video)

                if not video.youtube_id or force_refresh:
                    # Search for YouTube video using title and artist
                    search_result = youtube_search_service.search_video_by_title(
                        video_title, artist_name, limit=5
                    )

                    if search_result and search_result.get("videos"):
                        # Find the best match based on title similarity
                        best_match = None
                        best_score = 0.0

                        for youtube_video in search_result["videos"]:
                            yt_title = youtube_video.get("title", "").lower()
                            clean_video_title = (
                                video_title.lower()
                                .replace(artist_name.lower(), "")
                                .strip()
                            )

                            # Simple title matching - look for key words
                            title_words = set(clean_video_title.split())
                            yt_words = set(yt_title.split())

                            if title_words and yt_words:
                                # Calculate similarity score (intersection over union)
                                intersection = len(title_words.intersection(yt_words))
                                union = len(title_words.union(yt_words))
                                score = intersection / union if union > 0 else 0

                                # Bonus for exact artist name match
                                if artist_name.lower() in yt_title:
                                    score += 0.2

                                # Bonus for official video indicators
                                if any(
                                    indicator in yt_title
                                    for indicator in [
                                        "official",
                                        "music video",
                                        "mv",
                                    ]
                                ):
                                    score += 0.1

                                if (
                                    score > best_score and score > 0.3
                                ):  # Minimum threshold
                                    best_score = score
                                    best_match = youtube_video

                        if best_match:
                            video.youtube_id = best_match["youtube_id"]
                            video.youtube_url = best_match["youtube_url"]
                            updated_fields.extend(["youtube_id", "youtube_url"])
                            metadata_sources["YouTube"] = "Video ID discovery"
                            logger.info(
                                f"Found YouTube ID for video {video_id}: {video.youtube_id} "
                                f"(match score: {best_score:.2f})"
                            )
                        else:
                            logger.debug(
                                f"No suitable YouTube match found for video {video_id}"
                            )

            except Exception as e:
                errors.append(f"YouTube ID discovery failed: {str(e)}")
                logger.warning(f"YouTube ID discovery failed for video {video_id}: {e}")

            # 6. YouTube metadata enhancement (if we have YouTube ID)
            try:
                if video.youtube_id:
                    # Re-attach video to session if needed to prevent detachment issues
                    video = session.merge(video)

                    # Extract YouTube thumbnail if no thumbnail exists or force refresh
                    if not video.thumbnail_url or force_refresh:
                        # YouTube thumbnail URLs follow a standard pattern
                        youtube_thumbnail_url = f"https://img.youtube.com/vi/{video.youtube_id}/maxresdefault.jpg"

                        # Verify the thumbnail exists by making a HEAD request
                        try:
                            response = requests.head(youtube_thumbnail_url, timeout=5)
                            if response.status_code == 200:
                                video.thumbnail_url = youtube_thumbnail_url
                                video.thumbnail_source = "youtube"
                                updated_fields.extend(
                                    ["thumbnail_url", "thumbnail_source"]
                                )
                                metadata_sources["YouTube"] = "Thumbnail extraction"
                                logger.info(
                                    f"Added YouTube thumbnail for video {video_id}: {youtube_thumbnail_url}"
                                )
                            else:
                                # Try medium quality if maxres doesn't exist
                                youtube_thumbnail_url = f"https://img.youtube.com/vi/{video.youtube_id}/mqdefault.jpg"
                                response = requests.head(
                                    youtube_thumbnail_url, timeout=5
                                )
                                if response.status_code == 200:
                                    video.thumbnail_url = youtube_thumbnail_url
                                    video.thumbnail_source = "youtube"
                                    updated_fields.extend(
                                        ["thumbnail_url", "thumbnail_source"]
                                    )
                                    metadata_sources["YouTube"] = "Thumbnail extraction"
                                    logger.info(
                                        f"Added YouTube thumbnail (medium) for video {video_id}: {youtube_thumbnail_url}"
                                    )
                        except Exception as thumb_error:
                            logger.debug(
                                f"YouTube thumbnail verification failed for video {video_id}: {thumb_error}"
                            )

                    # TODO: Implement YouTube video metadata extraction
                    logger.debug(
                        f"YouTube metadata enrichment not yet implemented for video {video_id}"
                    )

            except Exception as e:
                errors.append(f"YouTube enrichment failed: {str(e)}")
                logger.warning(f"YouTube enrichment failed for video {video_id}: {e}")

            # 7. FFmpeg metadata extraction (if local file exists)
            try:
                if video.local_path and (
                    force_refresh
                    or not video.video_metadata
                    or not video.video_metadata.get("ffmpeg_extracted")
                ):
                    import os

                    if os.path.exists(video.local_path):
                        video_indexing_service = VideoIndexingService()
                        ffmpeg_metadata = (
                            video_indexing_service.extract_ffmpeg_metadata(
                                video.local_path
                            )
                        )

                        if ffmpeg_metadata:
                            # Update direct fields
                            if ffmpeg_metadata.get("duration") and not video.duration:
                                video.duration = ffmpeg_metadata["duration"]
                                updated_fields.append("duration")

                            # Update quality if we have ffmpeg data and (force_refresh OR no existing quality)
                            if ffmpeg_metadata.get("quality") and (
                                force_refresh or not video.quality
                            ):
                                video.quality = ffmpeg_metadata["quality"]
                                updated_fields.append("quality")

                            # Update metadata JSON
                            if not video.video_metadata:
                                video.video_metadata = {}

                            video.video_metadata.update(
                                {
                                    "width": ffmpeg_metadata.get("width"),
                                    "height": ffmpeg_metadata.get("height"),
                                    "video_codec": ffmpeg_metadata.get("video_codec"),
                                    "audio_codec": ffmpeg_metadata.get("audio_codec"),
                                    "fps": ffmpeg_metadata.get("fps"),
                                    "bitrate": ffmpeg_metadata.get("bitrate"),
                                    "file_size": ffmpeg_metadata.get("file_size"),
                                    "ffmpeg_extracted": True,
                                    "ffmpeg_extraction_date": datetime.utcnow().isoformat(),
                                }
                            )
                            flag_modified(video, "video_metadata")
                            updated_fields.append("video_metadata")
                            metadata_sources["FFmpeg"] = "Video file analysis"
                            logger.info(
                                f"FFmpeg metadata extracted for video {video_id}"
                            )

            except Exception as e:
                errors.append(f"FFmpeg extraction failed: {str(e)}")
                logger.warning(f"FFmpeg extraction failed for video {video_id}: {e}")

            # 8. Lyrics search (if no existing lyrics or force refresh)
            try:
                logger.info(
                    f"Starting lyrics search for video {video_id}. Current lyrics: {'exists' if video.lyrics else 'empty'}, force_refresh: {force_refresh}"
                )
                if force_refresh or not video.lyrics:
                    if video.artist and video.artist.name and video.title:
                        logger.info(
                            f"Searching lyrics for: '{video.artist.name}' - '{video.title}'"
                        )
                        # Try lyrics search using the existing azlyrics function
                        try:
                            lyrics_result = search_lyrics_azlyrics(
                                video.artist.name, video.title
                            )
                            if lyrics_result and len(lyrics_result.strip()) > 50:
                                video.lyrics = lyrics_result
                                updated_fields.append("lyrics")
                                metadata_sources["Lyrics.ovh"] = "Lyrics search"
                                logger.info(
                                    f"Lyrics found and saved for video {video_id} ({len(lyrics_result)} chars)"
                                )
                            else:
                                logger.info(
                                    f"No substantial lyrics found for video {video_id} (result: {lyrics_result[:100] if lyrics_result else 'None'})"
                                )
                        except Exception as lyrics_error:
                            logger.warning(
                                f"Lyrics search failed for video {video_id}: {lyrics_error}"
                            )
                    else:
                        logger.info(
                            f"Cannot search lyrics for video {video_id}: missing artist name ({video.artist.name if video.artist else 'None'}) or title ({video.title})"
                        )

            except Exception as e:
                errors.append(f"Lyrics search failed: {str(e)}")
                logger.warning(f"Lyrics search failed for video {video_id}: {e}")

            # 9. Genre fallback - Use artist genres if video still has no genres
            try:
                logger.info(
                    f"Checking genre fallback for video {video_id}. Video genres: {video.genres}, Artist genres: {video.artist.genres if video.artist else 'No artist'}"
                )
                if not video.genres and video.artist and video.artist.genres:
                    video.genres = video.artist.genres[:3]  # Top 3 genres from artist
                    updated_fields.append("genres")
                    metadata_sources["Artist Database"] = "Genre fallback"
                    logger.info(
                        f"Applied genre fallback from artist for video {video_id}: {video.genres}"
                    )
                elif video.genres:
                    logger.info(f"Video {video_id} already has genres: {video.genres}")
                elif not video.artist:
                    logger.info(f"Video {video_id} has no artist for genre fallback")
                elif not video.artist.genres:
                    logger.info(f"Video {video_id} artist has no genres for fallback")

            except Exception as e:
                errors.append(f"Genre fallback failed: {str(e)}")
                logger.warning(f"Genre fallback failed for video {video_id}: {e}")

            # Update enrichment timestamp
            video.last_enriched = datetime.utcnow()
            updated_fields.append("last_enriched")

            # Commit changes
            session.commit()

            logger.info(
                f"Video {video_id} enrichment completed. Updated fields: {updated_fields}"
            )

            return EnrichmentResult(
                video_id=video_id,
                success=True,
                enriched_fields=updated_fields,
                sources_used=list(metadata_sources.keys()),
                metadata_sources=list(metadata_sources.keys()),
                errors=errors if errors else None,
            )

    except Exception as e:
        logger.error(f"Failed to enrich video {video_id}: {e}")
        return EnrichmentResult(video_id=video_id, success=False, errors=[str(e)])
