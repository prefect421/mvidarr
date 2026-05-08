"""
Video discovery service for finding new music videos for tracked artists
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from typing import Dict, List

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.settings_service import SettingsService
from src.services.thumbnail_service import thumbnail_service
from src.services.video_batch_service import get_ytdlp_path
from src.services.youtube_search_service import youtube_search_service
from src.utils.logger import get_logger
from src.utils.video_type_detector import VideoTypeDetector

logger = get_logger("mvidarr.video_discovery")


class VideoDiscoveryService:
    """Service for discovering new music videos for tracked artists"""

    def __init__(self):
        self.discovery_enabled = True
        self.max_videos_per_artist = 50
        self.discovery_interval_hours = 24
        self.rate_limit_delay = 1.0  # seconds between API calls

    def discover_videos_for_artist(self, artist_id: int, limit: int = None) -> Dict:
        """
        Discover new videos for a specific artist

        Scheduler V2 enhancement (v0.10.1): Respects per-artist max_videos_per_discovery

        Args:
            artist_id: Artist ID to discover videos for
            limit: Maximum number of new videos to discover (overrides artist setting)

        Returns:
            Dictionary with discovery results
        """
        try:
            with get_db() as session:
                artist = session.query(Artist).filter_by(id=artist_id).first()
                if not artist:
                    return {"success": False, "error": f"Artist {artist_id} not found"}

                # Capture artist name early to avoid DetachedInstanceError
                artist_name = artist.name

                # Use per-artist limit if not explicitly provided (Scheduler V2)
                if limit is None:
                    limit = (
                        artist.max_videos_per_discovery
                        if hasattr(artist, "max_videos_per_discovery")
                        and artist.max_videos_per_discovery
                        else 10
                    )

                logger.info(
                    f"Starting video discovery for artist: {artist_name} (limit: {limit})"
                )

                # Get existing video URLs to avoid duplicates
                existing_videos = (
                    session.query(Video).filter_by(artist_id=artist_id).all()
                )
                existing_urls = {video.url for video in existing_videos if video.url}
                logger.info(
                    f"Found {len(existing_videos)} existing videos for {artist_name}, {len(existing_urls)} with URLs"
                )

                discovered_videos = []

                # Search YouTube for new videos
                youtube_results = self._search_youtube_for_artist(artist_name, limit)
                logger.info(
                    f"YouTube returned {len(youtube_results)} videos for {artist_name}"
                )

                for video_data in youtube_results:
                    if video_data.get("url"):
                        if video_data["url"] not in existing_urls:
                            discovered_videos.append(video_data)
                            logger.info(
                                f"Added new YouTube video: {video_data['title']}"
                            )
                        else:
                            logger.info(
                                f"YouTube video URL already exists: {video_data['title']}"
                            )
                    time.sleep(self.rate_limit_delay)

                # Search IMVDb for additional videos
                imvdb_results = self._search_imvdb_for_artist(artist_name, limit)
                logger.info(
                    f"IMVDb returned {len(imvdb_results)} videos for {artist_name}"
                )

                for video_data in imvdb_results:
                    if video_data.get("url"):
                        if video_data["url"] not in existing_urls:
                            # Check if already found via YouTube
                            if not any(
                                v["url"] == video_data["url"] for v in discovered_videos
                            ):
                                discovered_videos.append(video_data)
                                logger.info(
                                    f"Added new IMVDb video: {video_data['title']}"
                                )
                            else:
                                logger.info(
                                    f"Video already in discovered list: {video_data['title']}"
                                )
                        else:
                            logger.info(
                                f"Video URL already exists: {video_data['title']} - {video_data['url']}"
                            )
                    else:
                        logger.info(
                            f"Video has no URL: {video_data.get('title', 'Unknown')}"
                        )
                    time.sleep(self.rate_limit_delay)

                # Merge duplicates: IMVDb base + YouTube overlay
                merged_videos = self._merge_duplicate_videos(discovered_videos)
                unified_videos = merged_videos[:limit]

                # Store discovered videos with 'wanted' status
                stored_count = 0
                for video_data in unified_videos:
                    try:
                        self._store_discovered_video(session, artist_id, video_data)
                        stored_count += 1
                    except Exception as e:
                        logger.error(f"Failed to store discovered video: {e}")
                        continue

                session.commit()

                logger.info(
                    f"Discovery complete for {artist_name}: found {len(discovered_videos)} videos, stored {stored_count}"
                )

                return {
                    "success": True,
                    "artist_name": artist_name,
                    "discovered_count": len(discovered_videos),
                    "stored_count": stored_count,
                    "videos": unified_videos,
                }

        except Exception as e:
            logger.error(f"Video discovery failed for artist {artist_id}: {e}")
            return {"success": False, "error": str(e)}

    def discover_videos_for_all_artists(self, limit_per_artist: int = 5) -> Dict:
        """
        Discover new videos for all tracked artists

        Args:
            limit_per_artist: Maximum videos to discover per artist

        Returns:
            Dictionary with overall discovery results
        """
        try:
            with get_db() as session:
                # Get all artists that should be monitored
                artists = session.query(Artist).filter_by(monitored=True).all()

                if not artists:
                    return {
                        "success": True,
                        "message": "No monitored artists found",
                        "results": [],
                    }

                logger.info(f"Starting bulk video discovery for {len(artists)} artists")

                results = []
                total_discovered = 0
                total_stored = 0

                for artist in artists:
                    # Capture artist attributes early to avoid DetachedInstanceError
                    artist_id = artist.id
                    artist_name = artist.name

                    try:
                        # Check if artist needs discovery (based on last discovery time)
                        if not self._should_discover_for_artist(artist):
                            logger.debug(
                                f"Skipping discovery for {artist_name} - too recent"
                            )
                            continue

                        result = self.discover_videos_for_artist(
                            artist_id, limit_per_artist
                        )
                        results.append(
                            {
                                "artist_id": artist_id,
                                "artist_name": artist_name,
                                "result": result,
                            }
                        )

                        if result["success"]:
                            total_discovered += result["discovered_count"]
                            total_stored += result["stored_count"]

                            # Commit per-artist so interrupted runs don't re-process
                            artist.last_discovery = datetime.utcnow()
                            session.add(artist)
                            session.commit()

                        # Rate limiting between artists
                        time.sleep(self.rate_limit_delay * 2)

                    except Exception as e:
                        logger.error(f"Discovery failed for artist {artist_name}: {e}")
                        results.append(
                            {
                                "artist_id": artist_id,
                                "artist_name": artist_name,
                                "result": {"success": False, "error": str(e)},
                            }
                        )
                        continue

                session.commit()

                logger.info(
                    f"Bulk discovery complete: {total_discovered} videos discovered, {total_stored} stored"
                )

                return {
                    "success": True,
                    "total_artists": len(artists),
                    "processed_artists": len(results),
                    "total_discovered": total_discovered,
                    "total_stored": total_stored,
                    "results": results,
                }

        except Exception as e:
            logger.error(f"Bulk video discovery failed: {e}")
            return {"success": False, "error": str(e)}

    # def _search_youtube_for_artist(self, artist: Artist, limit: int) -> List[Dict]:
    #     """Search YouTube for artist videos (TODO: implement)"""
    #     logger.info(f"YouTube search not yet implemented for {artist.name}")
    #     return []

    def _search_imvdb_for_artist(self, artist_name: str, limit: int) -> List[Dict]:
        """Search IMVDb for artist videos"""
        try:
            results = imvdb_service.search_artist_videos(artist_name, limit=limit)

            if not results or "videos" not in results:
                return []

            video_list = []
            for video in results["videos"]:
                # Ensure song_title is always a string (fix for integer title issue)
                song_title = (
                    str(video.get("song_title", "Unknown"))
                    if video.get("song_title") is not None
                    else "Unknown"
                )
                video_data = {
                    "title": f"{artist_name} - {song_title}",
                    "song_title": song_title,
                    "year": video.get("year"),
                    "directors": video.get("directors", []),
                    "imvdb_id": video.get("id"),
                    "thumbnail_url": (
                        video.get("image", {}).get("l") if video.get("image") else None
                    ),
                }

                # Try to get YouTube URL from IMVDb
                youtube_url = video.get("sources", {}).get("youtube")
                if youtube_url:
                    video_data["url"] = youtube_url
                else:
                    # If no YouTube URL, create a placeholder URL based on IMVDb ID
                    video_data["url"] = f"https://imvdb.com/video/{video.get('id')}"
                    logger.debug(
                        f"No YouTube URL for {video.get('song_title')}, using IMVDb URL"
                    )

                video_list.append(video_data)
                logger.info(
                    f"Added video: {video_data['title']} - URL: {video_data['url']}"
                )

            logger.info(f"Found {len(video_list)} IMVDb videos for {artist_name}")
            return video_list

        except Exception as e:
            logger.error(f"IMVDb search failed for artist {artist_name}: {e}")
            return []

    def _search_youtube_for_artist(self, artist_name: str, limit: int) -> List[Dict]:
        """
        Search YouTube for artist videos using API or yt-dlp fallback

        Args:
            artist_name: Name of the artist to search for
            limit: Maximum number of videos to return

        Returns:
            List of video_data dicts with standardized format
        """
        try:
            # Get settings
            min_score = SettingsService.get_float("youtube_discovery_min_score", 1.5)
            allow_ytdlp_fallback = SettingsService.get_bool(
                "youtube_discovery_fallback_ytdlp", True
            )

            # Try YouTube API first
            try:
                results = youtube_search_service.search_artist_videos(
                    artist_name, limit=limit
                )

                if results and "videos" in results and len(results["videos"]) > 0:
                    logger.info(
                        f"YouTube API returned {len(results['videos'])} videos for {artist_name}"
                    )
                    return self._process_youtube_api_results(
                        results["videos"], artist_name, min_score
                    )
            except Exception as e:
                logger.warning(f"YouTube API search failed for {artist_name}: {e}")

                # Fall back to yt-dlp if enabled
                if allow_ytdlp_fallback:
                    logger.info(f"Falling back to yt-dlp search for {artist_name}")
                    return self._search_youtube_with_ytdlp(
                        artist_name, limit, min_score
                    )
                else:
                    logger.error(f"YouTube API failed and yt-dlp fallback disabled")
                    return []

            return []

        except Exception as e:
            logger.error(f"YouTube search failed for {artist_name}: {e}")
            return []

    def _process_youtube_api_results(
        self, videos: List[Dict], artist_name: str, min_score: float
    ) -> List[Dict]:
        """
        Process YouTube API results into discovery format

        Args:
            videos: Raw YouTube API results
            artist_name: Name of the artist
            min_score: Minimum search score threshold

        Returns:
            List of processed video_data dicts
        """
        processed_videos = []

        for video in videos:
            # Filter by search score
            search_score = video.get("search_score", 0.0)
            if search_score < min_score:
                logger.debug(
                    f"Skipping video '{video.get('title')}' - score {search_score} < {min_score}"
                )
                continue

            # Map to discovery format
            video_data = {
                "title": f"{artist_name} - {video.get('title', 'Unknown')}",
                "song_title": video.get("title", "Unknown"),
                "youtube_id": video.get("youtube_id"),
                "url": video.get("youtube_url"),
                "youtube_url": video.get("youtube_url"),
                "thumbnail_url": video.get("thumbnail_url"),
                "duration": video.get("duration"),
                "view_count": video.get("view_count", 0),
                "like_count": video.get("like_count", 0),
                "published_date": video.get("published_at"),
                "description": video.get("description", ""),
                "channel_name": video.get("channel_title", ""),
                "source": "youtube",
                "search_score": search_score,
                "tags": video.get("tags", []),
            }

            processed_videos.append(video_data)
            logger.info(
                f"Added YouTube video: {video_data['title']} (score: {search_score:.2f})"
            )

        return processed_videos

    def _search_youtube_with_ytdlp(
        self, artist_name: str, limit: int, min_score: float
    ) -> List[Dict]:
        """
        Fallback YouTube search using yt-dlp (when API unavailable)

        Similar to resolve_video_url() in video_batch_service.py but for discovery

        Args:
            artist_name: Name of the artist to search for
            limit: Maximum videos to find
            min_score: Minimum score (not applicable for yt-dlp, but kept for consistency)

        Returns:
            List of video_data dicts
        """
        try:
            search_query = f"{artist_name} music video"

            cmd = [
                get_ytdlp_path(),
                "--dump-json",
                "--no-download",
                "--playlist-items",
                f"1-{limit}",  # Get top N results
                f"ytsearch{limit}:{search_query}",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                logger.error(f"yt-dlp search failed: {result.stderr}")
                return []

            # Parse JSON output (one JSON object per line)
            videos = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                try:
                    video_info = json.loads(line)

                    video_data = {
                        "title": f"{artist_name} - {video_info.get('title', 'Unknown')}",
                        "song_title": video_info.get("title", "Unknown"),
                        "youtube_id": video_info.get("id"),
                        "url": video_info.get("webpage_url") or video_info.get("url"),
                        "youtube_url": video_info.get("webpage_url"),
                        "thumbnail_url": video_info.get("thumbnail"),
                        "duration": video_info.get("duration"),
                        "view_count": video_info.get("view_count", 0),
                        "like_count": video_info.get("like_count", 0),
                        "description": video_info.get("description", ""),
                        "channel_name": video_info.get("uploader", ""),
                        "source": "youtube_ytdlp",
                        "search_score": 0.0,  # yt-dlp doesn't provide scores
                    }

                    videos.append(video_data)
                    logger.info(f"yt-dlp found: {video_data['title']}")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse yt-dlp JSON: {e}")
                    continue

            logger.info(f"yt-dlp returned {len(videos)} videos for {artist_name}")
            return videos

        except subprocess.TimeoutExpired:
            logger.error(f"yt-dlp search timed out for {artist_name}")
            return []
        except Exception as e:
            logger.error(f"yt-dlp search error for {artist_name}: {e}")
            return []

    def _merge_duplicate_videos(self, discovered_videos: List[Dict]) -> List[Dict]:
        """
        Merge duplicate videos found in multiple sources

        Strategy: IMVDb metadata as base, overlay YouTube-specific fields

        Args:
            discovered_videos: List of video_data dicts from all sources

        Returns:
            Deduplicated list with merged metadata
        """
        # Group by URL
        url_map = {}

        for video in discovered_videos:
            url = video.get("url")
            if not url:
                continue

            if url not in url_map:
                url_map[url] = []
            url_map[url].append(video)

        # Merge duplicates
        merged = []

        for url, video_list in url_map.items():
            if len(video_list) == 1:
                # No duplicates, use as-is
                merged.append(video_list[0])
            else:
                # Multiple sources found same video - merge
                imvdb_data = next(
                    (v for v in video_list if v["source"] == "imvdb"), None
                )
                youtube_data = next(
                    (
                        v
                        for v in video_list
                        if v["source"] in ["youtube", "youtube_ytdlp"]
                    ),
                    None,
                )

                if imvdb_data and youtube_data:
                    # Merge: IMVDb base + YouTube overlay
                    merged_video = {**imvdb_data}  # Start with IMVDb

                    # Overlay YouTube-specific fields
                    merged_video["youtube_id"] = youtube_data.get("youtube_id")
                    merged_video["youtube_url"] = youtube_data.get("youtube_url")
                    merged_video["view_count"] = youtube_data.get("view_count", 0)
                    merged_video["like_count"] = youtube_data.get("like_count", 0)
                    merged_video["tags"] = youtube_data.get("tags", [])
                    merged_video["search_score"] = youtube_data.get("search_score", 0.0)

                    # Fill missing IMVDb fields with YouTube data
                    if not merged_video.get("duration"):
                        merged_video["duration"] = youtube_data.get("duration")
                    if not merged_video.get("published_date"):
                        merged_video["published_date"] = youtube_data.get(
                            "published_date"
                        )
                    if not merged_video.get("description"):
                        merged_video["description"] = youtube_data.get("description")

                    merged_video["source"] = "imvdb+youtube"  # Mark as merged

                    logger.info(
                        f"Merged duplicate: {merged_video['title']} (IMVDb + YouTube)"
                    )
                    merged.append(merged_video)
                else:
                    # Shouldn't happen, but fallback to first result
                    merged.append(video_list[0])

        return merged

    # def _is_likely_music_video(self, video: Dict, artist_name: str) -> bool:
    #     """Determine if a YouTube video is likely a music video (TODO: implement)"""
    #     return True

    def _should_discover_for_artist(self, artist: Artist) -> bool:
        """
        Check if discovery should run for an artist based on timing and settings

        Scheduler V2 enhancement (v0.10.1): Uses per-artist discovery settings
        """
        # Check if discovery is enabled for this artist (Scheduler V2)
        if hasattr(artist, "discovery_enabled") and not artist.discovery_enabled:
            logger.debug(
                f"Discovery disabled for artist {artist.name} (discovery_enabled=False)"
            )
            return False

        # Check if artist is monitored
        if not artist.monitored:
            logger.debug(f"Artist {artist.name} is not monitored")
            return False

        # If never discovered before, allow discovery
        if not artist.last_discovery:
            logger.debug(f"Artist {artist.name} has never been discovered - allowing")
            return True

        # Use per-artist discovery interval (Scheduler V2) or fallback to global
        interval_hours = (
            artist.discovery_interval_hours
            if hasattr(artist, "discovery_interval_hours")
            and artist.discovery_interval_hours
            else self.discovery_interval_hours
        )

        time_since_discovery = datetime.utcnow() - artist.last_discovery
        min_interval = timedelta(hours=interval_hours)

        should_discover = time_since_discovery >= min_interval

        if not should_discover:
            next_discovery = artist.last_discovery + min_interval
            logger.debug(
                f"Artist {artist.name} not ready for discovery. "
                f"Last: {artist.last_discovery}, Next: {next_discovery}"
            )

        return should_discover

    def _clean_duplicate_artist_from_title(self, title: str, artist_name: str) -> str:
        """
        Remove duplicate artist name from video title

        Example: "Wet Leg - Wet Leg - Oh No" -> "Wet Leg - Oh No"
        Example: "Kid Kapichi - Kid Kapichi - Smash the Gaff" -> "Kid Kapichi - Smash the Gaff"

        Args:
            title: Original video title
            artist_name: Artist name to check for duplication

        Returns:
            Cleaned title without duplicate artist prefix
        """
        if not title or not artist_name:
            return title

        # Check if title starts with "Artist - Artist - "
        duplicate_prefix = f"{artist_name} - {artist_name} - "
        if title.startswith(duplicate_prefix):
            # Remove the duplicate prefix, keeping one artist name
            cleaned = title[len(artist_name) + 3 :]  # Remove "Artist - "
            logger.debug(
                f"Cleaned duplicate artist from title: '{title}' -> '{cleaned}'"
            )
            return cleaned

        return title

    def _store_discovered_video(self, session, artist_id: int, video_data: Dict):
        """Store a discovered video in the database"""
        try:
            # Check if video already exists by URL, YouTube URL, or YouTube ID
            from sqlalchemy import or_

            youtube_id = video_data.get("youtube_id")
            url = video_data.get("url")
            youtube_url = video_data.get("youtube_url")

            # Build deduplication filters
            filters = [Video.artist_id == artist_id]

            # Check by YouTube ID first (most reliable)
            if youtube_id:
                filters.append(Video.youtube_id == youtube_id)
            # Then check by URL or youtube_url
            elif url or youtube_url:
                url_filters = []
                if url:
                    url_filters.append(Video.url == url)
                    url_filters.append(Video.youtube_url == url)
                if youtube_url:
                    url_filters.append(Video.url == youtube_url)
                    url_filters.append(Video.youtube_url == youtube_url)
                filters.append(or_(*url_filters))

            existing = session.query(Video).filter(*filters).first()

            # Get artist name for title cleaning (needed for both existing and new videos)
            from src.database.models import Artist

            artist = session.query(Artist).filter(Artist.id == artist_id).first()

            if existing:
                # If the video exists as MONITORED but the artist now has auto_download
                # enabled, promote it to WANTED so it gets picked up by the downloader.
                if (
                    artist
                    and artist.auto_download
                    and existing.status == VideoStatus.MONITORED
                ):
                    existing.status = VideoStatus.WANTED
                    session.commit()
                    logger.info(
                        f"Promoted video '{existing.title}' (ID: {existing.id}) "
                        f"from MONITORED to WANTED (artist auto_download enabled)"
                    )
                else:
                    logger.debug(
                        f"Video already exists (ID: {existing.id}): {video_data.get('title')}"
                    )
                return
            artist_name = artist.name if artist else ""

            # Create new video record with 'wanted' status
            # Ensure title is always a string (fix for integer title issue)
            video_title = (
                str(video_data.get("title", ""))
                if video_data.get("title") is not None
                else ""
            )

            # Clean duplicate artist name from title
            video_title = self._clean_duplicate_artist_from_title(
                video_title, artist_name
            )

            # Parse published_date - YouTube returns ISO 8601 with 'Z' timezone
            release_date = None
            if video_data.get("published_date"):
                try:
                    from dateutil import parser as dateutil_parser

                    # Parse and convert to timezone-naive datetime for MySQL
                    parsed_date = dateutil_parser.parse(video_data["published_date"])
                    release_date = parsed_date.replace(tzinfo=None)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse published_date '{video_data.get('published_date')}': {e}"
                    )

            # Detect video type from title and metadata (Issue #191)
            detected_video_type = VideoTypeDetector.detect_from_metadata(video_data)
            # Plain "Artist - Song" titles produce no type signals and return None.
            # Default these to official_music_video so they aren't silently dropped
            # when an artist has allowed_video_types configured.
            if detected_video_type is None:
                detected_video_type = "official_music_video"

            # Check if video type matches artist's allowed types (Issue #191)
            if artist and artist.allowed_video_types:
                # Artist has video type filtering enabled
                allowed_types = artist.allowed_video_types
                if isinstance(allowed_types, list) and len(allowed_types) > 0:
                    # Check if detected type is in allowed list
                    if detected_video_type not in allowed_types:
                        logger.info(
                            f"Skipping video '{video_title}' - type '{detected_video_type}' "
                            f"not in artist's allowed types: {allowed_types}"
                        )
                        return  # Skip this video
                elif isinstance(allowed_types, list) and len(allowed_types) == 0:
                    # Empty list means download nothing
                    logger.info(
                        f"Skipping video '{video_title}' - artist has empty allowed_video_types (download nothing)"
                    )
                    return  # Skip this video

            video = Video(
                artist_id=artist_id,
                title=video_title,
                url=video_data.get("url"),
                youtube_url=video_data.get("youtube_url"),  # YouTube-specific URL
                youtube_id=video_data.get("youtube_id"),  # YouTube video ID
                duration=video_data.get("duration"),
                release_date=release_date,
                description=video_data.get("description", ""),
                thumbnail_url=video_data.get("thumbnail_url"),
                imvdb_id=video_data.get("imvdb_id"),
                view_count=video_data.get("view_count", 0),
                like_count=video_data.get("like_count", 0),  # YouTube like count
                video_type=detected_video_type,  # Auto-detected video type (Issue #191)
                status=(
                    VideoStatus.WANTED
                    if artist and artist.auto_download
                    else VideoStatus.MONITORED
                ),
                discovered_date=datetime.utcnow(),
                source=video_data.get("source", "discovery"),  # Track source
                video_metadata={
                    "source": video_data.get("source", "discovery"),
                    "channel_name": video_data.get("channel_name", ""),
                    "directors": video_data.get("directors", []),
                    "year": video_data.get("year"),
                    "song_title": str(video_data.get("song_title", "")),
                    "search_score": video_data.get(
                        "search_score", 0.0
                    ),  # YouTube relevance score
                    "tags": video_data.get("tags", []),  # YouTube tags
                },
            )

            session.add(video)
            session.flush()  # Ensure video ID is available
            logger.debug(f"Stored new video: {video.title}")

            # TODO: Download thumbnail - requires artist name, but artist may be detached
            # Skipping for now to prevent discovery failures
            # Will be implemented in a separate fix

        except Exception as e:
            logger.error(f"Failed to store video: {e}")
            raise

    def get_discovery_stats(self) -> Dict:
        """Get statistics about video discovery"""
        try:
            with get_db() as session:
                # Count videos by status
                total_videos = session.query(Video).count()
                wanted_videos = (
                    session.query(Video).filter_by(status=VideoStatus.WANTED).count()
                )
                downloaded_videos = (
                    session.query(Video)
                    .filter_by(status=VideoStatus.DOWNLOADED)
                    .count()
                )

                # Count artists
                total_artists = session.query(Artist).count()
                monitored_artists = (
                    session.query(Artist).filter_by(monitored=True).count()
                )

                # Recent discovery stats (last 7 days)
                week_ago = datetime.utcnow() - timedelta(days=7)
                recent_discoveries = (
                    session.query(Video)
                    .filter(Video.discovered_date >= week_ago)
                    .count()
                )

                return {
                    "total_videos": total_videos,
                    "wanted_videos": wanted_videos,
                    "downloaded_videos": downloaded_videos,
                    "total_artists": total_artists,
                    "monitored_artists": monitored_artists,
                    "recent_discoveries": recent_discoveries,
                    "discovery_enabled": self.discovery_enabled,
                }

        except Exception as e:
            logger.error(f"Failed to get discovery stats: {e}")
            return {}


# Convenience instance
video_discovery_service = VideoDiscoveryService()
