"""
Video discovery service for finding new music videos for tracked artists
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.thumbnail_service import thumbnail_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.video_discovery")


class VideoDiscoveryService:
    """Service for discovering new music videos for tracked artists"""

    def __init__(self):
        self.discovery_enabled = True
        self.max_videos_per_artist = 50
        self.discovery_interval_hours = 24
        self.rate_limit_delay = 1.0  # seconds between API calls

    def discover_videos_for_artist(self, artist_id: int, limit: int = 10) -> Dict:
        """
        Discover new videos for a specific artist

        Args:
            artist_id: Artist ID to discover videos for
            limit: Maximum number of new videos to discover

        Returns:
            Dictionary with discovery results
        """
        try:
            with get_db() as session:
                artist = session.query(Artist).filter_by(id=artist_id).first()
                if not artist:
                    return {"success": False, "error": f"Artist {artist_id} not found"}

                logger.info(f"Starting video discovery for artist: {artist.name}")

                # Get existing video URLs to avoid duplicates
                existing_videos = (
                    session.query(Video).filter_by(artist_id=artist_id).all()
                )
                existing_urls = {video.url for video in existing_videos if video.url}
                logger.info(
                    f"Found {len(existing_videos)} existing videos for {artist.name}, {len(existing_urls)} with URLs"
                )

                discovered_videos = []

                # Search YouTube for new videos (TODO: implement YouTube service)
                # youtube_results = self._search_youtube_for_artist(artist, limit)
                # for video_data in youtube_results:
                #     if video_data['url'] not in existing_urls:
                #         discovered_videos.append({
                #             'source': 'youtube',
                #             **video_data
                #         })
                #         time.sleep(self.rate_limit_delay)

                # Search IMVDb for additional videos
                imvdb_results = self._search_imvdb_for_artist(artist, limit)
                logger.info(
                    f"IMVDb returned {len(imvdb_results)} videos for {artist.name}"
                )

                for video_data in imvdb_results:
                    if video_data.get("url"):
                        if video_data["url"] not in existing_urls:
                            # Check if already found via YouTube
                            if not any(
                                v["url"] == video_data["url"] for v in discovered_videos
                            ):
                                discovered_videos.append(
                                    {"source": "imvdb", **video_data}
                                )
                                logger.info(f"Added new video: {video_data['title']}")
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

                # Use discovered videos directly (TODO: implement video unification service)
                unified_videos = discovered_videos[:limit]

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
                    f"Discovery complete for {artist.name}: found {len(discovered_videos)} videos, stored {stored_count}"
                )

                return {
                    "success": True,
                    "artist_name": artist.name,
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
                    try:
                        # Check if artist needs discovery (based on last discovery time)
                        if not self._should_discover_for_artist(artist):
                            logger.debug(
                                f"Skipping discovery for {artist.name} - too recent"
                            )
                            continue

                        result = self.discover_videos_for_artist(
                            artist.id, limit_per_artist
                        )
                        results.append(
                            {
                                "artist_id": artist.id,
                                "artist_name": artist.name,
                                "result": result,
                            }
                        )

                        if result["success"]:
                            total_discovered += result["discovered_count"]
                            total_stored += result["stored_count"]

                            # Update last discovery time
                            artist.last_discovery = datetime.utcnow()
                            session.add(artist)

                        # Rate limiting between artists
                        time.sleep(self.rate_limit_delay * 2)

                    except Exception as e:
                        logger.error(f"Discovery failed for artist {artist.name}: {e}")
                        results.append(
                            {
                                "artist_id": artist.id,
                                "artist_name": artist.name,
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

    def _search_imvdb_for_artist(self, artist: Artist, limit: int) -> List[Dict]:
        """Search IMVDb for artist videos"""
        try:
            results = imvdb_service.search_artist_videos(artist.name, limit=limit)

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
                    "title": f"{artist.name} - {song_title}",
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

            logger.info(f"Found {len(video_list)} IMVDb videos for {artist.name}")
            return video_list

        except Exception as e:
            logger.error(f"IMVDb search failed for artist {artist.name}: {e}")
            return []

    # def _is_likely_music_video(self, video: Dict, artist_name: str) -> bool:
    #     """Determine if a YouTube video is likely a music video (TODO: implement)"""
    #     return True

    def _should_discover_for_artist(self, artist: Artist) -> bool:
        """Check if discovery should run for an artist based on timing"""
        if not artist.last_discovery:
            return True

        time_since_discovery = datetime.utcnow() - artist.last_discovery
        min_interval = timedelta(hours=self.discovery_interval_hours)

        return time_since_discovery >= min_interval

    def _store_discovered_video(self, session, artist_id: int, video_data: Dict):
        """Store a discovered video in the database"""
        try:
            # Check if video already exists
            existing = (
                session.query(Video)
                .filter_by(artist_id=artist_id, url=video_data.get("url"))
                .first()
            )

            if existing:
                logger.debug(f"Video already exists: {video_data.get('title')}")
                return

            # Create new video record with 'wanted' status
            # Ensure title is always a string (fix for integer title issue)
            video_title = (
                str(video_data.get("title", ""))
                if video_data.get("title") is not None
                else ""
            )
            video = Video(
                artist_id=artist_id,
                title=video_title,
                url=video_data.get("url"),
                duration=video_data.get("duration"),
                release_date=video_data.get("published_date"),
                description=video_data.get("description", ""),
                thumbnail_url=video_data.get("thumbnail_url"),
                imvdb_id=video_data.get("imvdb_id"),
                view_count=video_data.get("view_count", 0),
                status=VideoStatus.WANTED,  # New videos start as 'wanted'
                discovered_date=datetime.utcnow(),
                video_metadata={
                    "source": video_data.get("source", "discovery"),
                    "channel_name": video_data.get("channel_name", ""),
                    "directors": video_data.get("directors", []),
                    "year": video_data.get("year"),
                    "song_title": str(video_data.get("song_title", "")),
                },
            )

            session.add(video)
            session.flush()  # Ensure video ID is available
            logger.debug(f"Stored new video: {video.title}")

            # Download thumbnail if URL is available
            if video.thumbnail_url:
                try:
                    thumbnail_path = thumbnail_service.download_video_thumbnail(
                        video.id, video.thumbnail_url
                    )
                    if thumbnail_path:
                        video.thumbnail_path = thumbnail_path
                        logger.debug(f"Downloaded thumbnail for video: {video.title}")
                    else:
                        logger.warning(
                            f"Failed to download thumbnail for video: {video.title}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error downloading thumbnail for video {video.title}: {e}"
                    )

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
