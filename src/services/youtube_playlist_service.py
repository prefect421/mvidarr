"""
YouTube Playlist Monitoring Service for tracking and downloading playlist videos
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, PlaylistMonitor, Video, VideoStatus
from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.youtube_playlist")

# Default timeout for HTTP requests (in seconds)
DEFAULT_REQUEST_TIMEOUT = 30


class YouTubePlaylistService:
    """Service for monitoring YouTube playlists and downloading videos"""

    def __init__(self):
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.metube_host = os.getenv("METUBE_HOST", "localhost")
        self.metube_port = os.getenv("METUBE_PORT", "8081")
        self.metube_url = f"http://{self.metube_host}:{self.metube_port}"

    @property
    def api_key(self):
        """Get YouTube API key from database settings"""
        try:
            return settings.get("youtube_api_key")
        except Exception as e:
            logger.error(f"Failed to get YouTube API key from settings: {e}")
            return None

    def extract_playlist_id(self, url: str) -> Optional[str]:
        """Extract playlist ID from YouTube URL"""
        try:
            # Handle various YouTube playlist URL formats
            patterns = [
                r"list=([a-zA-Z0-9_-]+)",
                r"youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)",
                r"youtube\.com/watch\?.*list=([a-zA-Z0-9_-]+)",
                r"youtu\.be/.*\?list=([a-zA-Z0-9_-]+)",
            ]

            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)

            return None

        except Exception as e:
            logger.error(f"Failed to extract playlist ID from URL: {e}")
            return None

    def get_playlist_info(self, playlist_id: str) -> Dict:
        """Get playlist information from YouTube API"""
        if not self.api_key:
            raise ValueError("YouTube API key not configured")

        url = f"{self.base_url}/playlists"
        params = {
            "part": "snippet,contentDetails,status",
            "id": playlist_id,
            "key": self.api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()

            data = response.json()
            if not data.get("items"):
                return None

            playlist = data["items"][0]
            snippet = playlist.get("snippet", {})
            content_details = playlist.get("contentDetails", {})

            return {
                "id": playlist_id,
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "channel_title": snippet.get("channelTitle"),
                "channel_id": snippet.get("channelId"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail_url": snippet.get("thumbnails", {})
                .get("high", {})
                .get("url"),
                "item_count": content_details.get("itemCount", 0),
                "privacy_status": playlist.get("status", {}).get("privacyStatus"),
            }

        except requests.RequestException as e:
            logger.error(f"Failed to get playlist info: {e}")
            raise

    def get_playlist_videos(
        self, playlist_id: str, max_results: int = 50
    ) -> List[Dict]:
        """Get all videos from a YouTube playlist"""
        if not self.api_key:
            raise ValueError("YouTube API key not configured")

        videos = []
        page_token = None

        while True:
            url = f"{self.base_url}/playlistItems"
            params = {
                "part": "snippet,contentDetails,status",
                "playlistId": playlist_id,
                "maxResults": min(max_results, 50),
                "key": self.api_key,
            }

            if page_token:
                params["pageToken"] = page_token

            try:
                response = requests.get(
                    url, params=params, timeout=DEFAULT_REQUEST_TIMEOUT
                )
                response.raise_for_status()

                data = response.json()
                items = data.get("items", [])

                for item in items:
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})

                    # Skip private or deleted videos
                    if (
                        snippet.get("title") == "Private video"
                        or snippet.get("title") == "Deleted video"
                    ):
                        continue

                    video_data = {
                        "video_id": snippet.get("resourceId", {}).get("videoId"),
                        "title": snippet.get("title"),
                        "description": snippet.get("description"),
                        "channel_title": snippet.get("videoOwnerChannelTitle"),
                        "channel_id": snippet.get("videoOwnerChannelId"),
                        "published_at": snippet.get("publishedAt"),
                        "thumbnail_url": snippet.get("thumbnails", {})
                        .get("high", {})
                        .get("url"),
                        "position": snippet.get("position"),
                        "playlist_id": playlist_id,
                        "added_to_playlist": snippet.get("publishedAt"),
                        "privacy_status": item.get("status", {}).get("privacyStatus"),
                    }

                    videos.append(video_data)

                # Check if there are more pages
                page_token = data.get("nextPageToken")
                if not page_token or len(videos) >= max_results:
                    break

            except requests.RequestException as e:
                logger.error(f"Failed to get playlist videos: {e}")
                break

        return videos

    def get_video_details(self, video_ids: List[str]) -> Dict[str, Dict]:
        """Get detailed information for multiple videos"""
        if not self.api_key:
            raise ValueError("YouTube API key not configured")

        if not video_ids:
            return {}

        video_details = {}

        # Process in batches of 50 (YouTube API limit)
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i : i + 50]

            url = f"{self.base_url}/videos"
            params = {
                "part": "snippet,contentDetails,statistics,status",
                "id": ",".join(batch_ids),
                "key": self.api_key,
            }

            try:
                response = requests.get(
                    url, params=params, timeout=DEFAULT_REQUEST_TIMEOUT
                )
                response.raise_for_status()

                data = response.json()

                for video in data.get("items", []):
                    video_id = video.get("id")
                    snippet = video.get("snippet", {})
                    content_details = video.get("contentDetails", {})
                    statistics = video.get("statistics", {})

                    video_details[video_id] = {
                        "duration": content_details.get("duration"),
                        "view_count": statistics.get("viewCount"),
                        "like_count": statistics.get("likeCount"),
                        "comment_count": statistics.get("commentCount"),
                        "tags": snippet.get("tags", []),
                        "category_id": snippet.get("categoryId"),
                        "live_broadcast_content": snippet.get("liveBroadcastContent"),
                        "upload_status": video.get("status", {}).get("uploadStatus"),
                    }

            except requests.RequestException as e:
                logger.error(f"Failed to get video details: {e}")

        return video_details

    def create_playlist_monitor(
        self,
        playlist_url: str,
        name: str = None,
        auto_download: bool = True,
        quality: str = "720p",
        keywords: List[str] = None,
    ) -> Dict:
        """Create a new playlist monitor"""
        try:
            playlist_id = self.extract_playlist_id(playlist_url)
            if not playlist_id:
                raise ValueError("Invalid playlist URL")

            # Get playlist info
            playlist_info = self.get_playlist_info(playlist_id)
            if not playlist_info:
                raise ValueError("Playlist not found or is private")

            with get_db() as session:
                # Check if playlist is already monitored
                existing_monitor = (
                    session.query(PlaylistMonitor)
                    .filter(PlaylistMonitor.playlist_id == playlist_id)
                    .first()
                )

                if existing_monitor:
                    return {
                        "success": False,
                        "message": "Playlist is already being monitored",
                        "monitor_id": existing_monitor.id,
                    }

                # Create new monitor
                monitor = PlaylistMonitor(
                    playlist_id=playlist_id,
                    playlist_url=playlist_url,
                    name=name or playlist_info["title"],
                    channel_title=playlist_info["channel_title"],
                    channel_id=playlist_info["channel_id"],
                    auto_download=auto_download,
                    quality=quality,
                    keywords=json.dumps(keywords) if keywords else None,
                    last_check=datetime.now(),
                    created_at=datetime.now(),
                )

                session.add(monitor)
                session.commit()

                # Initial sync
                sync_results = self.sync_playlist_videos(playlist_id, session)

                logger.info(f"Created playlist monitor for: {playlist_info['title']}")
                return {
                    "success": True,
                    "message": f"Successfully created monitor for playlist: {playlist_info['title']}",
                    "monitor_id": monitor.id,
                    "sync_results": sync_results,
                }

        except Exception as e:
            logger.error(f"Failed to create playlist monitor: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create playlist monitor: {str(e)}",
            }

    def sync_playlist_videos(self, playlist_id: str, session: Session = None) -> Dict:
        """Sync videos from a monitored playlist"""
        if session is None:
            with get_db() as session:
                return self.sync_playlist_videos(playlist_id, session)

        try:
            # Get monitor
            monitor = (
                session.query(PlaylistMonitor)
                .filter(PlaylistMonitor.playlist_id == playlist_id)
                .first()
            )

            if not monitor:
                raise ValueError("Playlist monitor not found")

            # Get current videos in playlist
            playlist_videos = self.get_playlist_videos(playlist_id, max_results=1000)

            # Get video details
            video_ids = [v["video_id"] for v in playlist_videos if v["video_id"]]
            video_details = self.get_video_details(video_ids)

            # Track existing videos
            existing_videos = {}
            for video in (
                session.query(Video).filter(Video.youtube_id.in_(video_ids)).all()
            ):
                existing_videos[video.youtube_id] = video

            results = {
                "total_videos": len(playlist_videos),
                "new_videos": 0,
                "updated_videos": 0,
                "downloaded_videos": 0,
                "errors": [],
            }

            # Parse keywords filter
            keywords = []
            if monitor.keywords:
                try:
                    keywords = json.loads(monitor.keywords)
                except:
                    keywords = []

            for video_data in playlist_videos:
                try:
                    video_id = video_data["video_id"]
                    if not video_id:
                        continue

                    # Get additional details
                    details = video_details.get(video_id, {})

                    # Check if video matches keywords filter
                    if keywords and not self._matches_keywords(
                        video_data["title"], keywords
                    ):
                        continue

                    # Update existing video or create new one
                    if video_id in existing_videos:
                        video = existing_videos[video_id]
                        # Update metadata
                        video.title = video_data["title"]
                        video.description = video_data.get("description", "")
                        video.thumbnail_url = video_data.get("thumbnail_url")
                        video.playlist_position = video_data.get("position")
                        video.duration = self._parse_duration(details.get("duration"))
                        video.view_count = details.get("view_count")
                        video.updated_at = datetime.now()

                        results["updated_videos"] += 1
                    else:
                        # Try to match with existing artist
                        artist = self._find_or_create_artist(
                            video_data["channel_title"], session
                        )

                        # Create new video
                        video = Video(
                            title=video_data["title"],
                            artist_id=artist.id,
                            youtube_id=video_id,
                            youtube_url=f"https://www.youtube.com/watch?v={video_id}",
                            description=video_data.get("description", ""),
                            thumbnail_url=video_data.get("thumbnail_url"),
                            duration=self._parse_duration(details.get("duration")),
                            view_count=details.get("view_count"),
                            playlist_id=playlist_id,
                            playlist_position=video_data.get("position"),
                            status=(
                                VideoStatus.WANTED
                                if monitor.auto_download
                                else VideoStatus.MONITORED
                            ),
                            source="youtube_playlist",
                            created_at=datetime.now(),
                        )

                        session.add(video)
                        results["new_videos"] += 1

                        # Auto-download if enabled
                        if monitor.auto_download:
                            try:
                                download_result = self.download_video(
                                    video_id, monitor.quality
                                )
                                if download_result.get("success"):
                                    video.status = VideoStatus.DOWNLOADING
                                    results["downloaded_videos"] += 1
                            except Exception as e:
                                logger.error(
                                    f"Failed to download video {video_id}: {e}"
                                )
                                results["errors"].append(
                                    f"Download failed for {video_data['title']}: {str(e)}"
                                )

                except Exception as e:
                    logger.error(
                        f"Error processing video {video_data.get('video_id')}: {e}"
                    )
                    results["errors"].append(f"Error processing video: {str(e)}")

            # Update monitor last check time
            monitor.last_check = datetime.now()
            session.commit()

            logger.info(f"Synced playlist {playlist_id}: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to sync playlist videos: {e}")
            raise

    def _matches_keywords(self, title: str, keywords: List[str]) -> bool:
        """Check if video title matches any of the keywords"""
        if not keywords:
            return True

        title_lower = title.lower()
        for keyword in keywords:
            if keyword.lower() in title_lower:
                return True

        return False

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse YouTube duration string to seconds"""
        if not duration_str:
            return None

        try:
            # YouTube returns duration in ISO 8601 format (PT4M13S)
            import re

            match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
            if match:
                hours = int(match.group(1) or 0)
                minutes = int(match.group(2) or 0)
                seconds = int(match.group(3) or 0)
                return hours * 3600 + minutes * 60 + seconds
        except:
            pass

        return None

    def _find_or_create_artist(self, channel_title: str, session: Session) -> Artist:
        """Find existing artist or create new one"""
        # Try to find existing artist
        existing_artist = (
            session.query(Artist)
            .filter(Artist.name.ilike(f"%{channel_title}%"))
            .first()
        )

        if existing_artist:
            return existing_artist

        # Generate default folder path
        from src.utils.filename_cleanup import FilenameCleanup

        folder_path = FilenameCleanup.sanitize_folder_name(channel_title)

        # Create new artist
        new_artist = Artist(
            name=channel_title,
            monitored=True,
            auto_download=False,
            source="youtube_playlist",
            created_at=datetime.now(),
            folder_path=folder_path,
        )

        session.add(new_artist)
        session.flush()  # Get the ID

        # Run auto-processing for newly created artist
        try:
            from src.services.artist_auto_processing_service import (
                artist_auto_processing_service,
            )

            # Ensure artist is bound to session for auto-processing
            session.refresh(new_artist)
            auto_processing_results = artist_auto_processing_service.process_new_artist(
                new_artist, session
            )
            # Refresh artist after auto-processing to get any metadata enrichment updates
            session.refresh(new_artist)
            match_count = auto_processing_results.get("auto_match", {}).get(
                "match_count", 0
            )
            logger.info(
                f"Auto-processing completed for {channel_title} - {match_count} services matched"
            )
        except Exception as e:
            logger.warning(
                f"Auto-processing failed for newly created artist {channel_title}: {e}"
            )

        return new_artist

    def download_video(self, video_id: str, quality: str = "720p") -> Dict:
        """Download a video using MeTube"""
        try:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # MeTube download request
            download_data = {"url": video_url, "format": "mp4", "quality": quality}

            response = requests.post(
                f"{self.metube_url}/add", json=download_data, timeout=30
            )

            if response.status_code == 200:
                logger.info(f"Successfully queued download for video: {video_id}")
                return {
                    "success": True,
                    "message": "Video queued for download",
                    "video_id": video_id,
                }
            else:
                logger.error(
                    f"MeTube download failed: {response.status_code} - {response.text}"
                )
                return {
                    "success": False,
                    "error": f"Download failed: {response.status_code}",
                }

        except Exception as e:
            logger.error(f"Failed to download video {video_id}: {e}")
            return {"success": False, "error": str(e)}

    def get_monitored_playlists(self) -> List[Dict]:
        """Get all monitored playlists"""
        try:
            with get_db() as session:
                monitors = session.query(PlaylistMonitor).all()

                playlist_data = []
                for monitor in monitors:
                    # Get video count
                    video_count = (
                        session.query(Video)
                        .filter(Video.playlist_id == monitor.playlist_id)
                        .count()
                    )

                    # Get recent videos
                    recent_videos = (
                        session.query(Video)
                        .filter(Video.playlist_id == monitor.playlist_id)
                        .order_by(Video.created_at.desc())
                        .limit(5)
                        .all()
                    )

                    playlist_data.append(
                        {
                            "id": monitor.id,
                            "playlist_id": monitor.playlist_id,
                            "playlist_url": monitor.playlist_url,
                            "name": monitor.name,
                            "channel_title": monitor.channel_title,
                            "auto_download": monitor.auto_download,
                            "quality": monitor.quality,
                            "keywords": (
                                json.loads(monitor.keywords) if monitor.keywords else []
                            ),
                            "video_count": video_count,
                            "last_check": (
                                monitor.last_check.isoformat()
                                if monitor.last_check
                                else None
                            ),
                            "created_at": monitor.created_at.isoformat(),
                            "recent_videos": [
                                {
                                    "id": v.id,
                                    "title": v.title,
                                    "status": v.status.value,
                                    "created_at": v.created_at.isoformat(),
                                }
                                for v in recent_videos
                            ],
                        }
                    )

                return playlist_data

        except Exception as e:
            logger.error(f"Failed to get monitored playlists: {e}")
            raise

    def update_playlist_monitor(self, monitor_id: int, updates: Dict) -> Dict:
        """Update playlist monitor settings"""
        try:
            with get_db() as session:
                monitor = (
                    session.query(PlaylistMonitor)
                    .filter(PlaylistMonitor.id == monitor_id)
                    .first()
                )

                if not monitor:
                    raise ValueError("Playlist monitor not found")

                # Update allowed fields
                allowed_fields = ["name", "auto_download", "quality", "keywords"]
                for field in allowed_fields:
                    if field in updates:
                        if field == "keywords":
                            setattr(monitor, field, json.dumps(updates[field]))
                        else:
                            setattr(monitor, field, updates[field])

                session.commit()

                logger.info(f"Updated playlist monitor {monitor_id}")
                return {
                    "success": True,
                    "message": "Playlist monitor updated successfully",
                }

        except Exception as e:
            logger.error(f"Failed to update playlist monitor: {e}")
            raise

    def delete_playlist_monitor(
        self, monitor_id: int, delete_videos: bool = False
    ) -> Dict:
        """Delete playlist monitor"""
        try:
            with get_db() as session:
                monitor = (
                    session.query(PlaylistMonitor)
                    .filter(PlaylistMonitor.id == monitor_id)
                    .first()
                )

                if not monitor:
                    raise ValueError("Playlist monitor not found")

                playlist_id = monitor.playlist_id

                # Optionally delete associated videos
                if delete_videos:
                    videos_deleted = (
                        session.query(Video)
                        .filter(Video.playlist_id == playlist_id)
                        .delete()
                    )
                    logger.info(
                        f"Deleted {videos_deleted} videos from playlist {playlist_id}"
                    )

                # Delete monitor
                session.delete(monitor)
                session.commit()

                logger.info(f"Deleted playlist monitor {monitor_id}")
                return {
                    "success": True,
                    "message": "Playlist monitor deleted successfully",
                    "videos_deleted": delete_videos,
                }

        except Exception as e:
            logger.error(f"Failed to delete playlist monitor: {e}")
            raise

    def sync_all_playlists(self) -> Dict:
        """Sync all monitored playlists"""
        try:
            with get_db() as session:
                monitors = session.query(PlaylistMonitor).all()

                results = {
                    "total_playlists": len(monitors),
                    "synced_playlists": 0,
                    "total_new_videos": 0,
                    "total_downloads": 0,
                    "errors": [],
                }

                for monitor in monitors:
                    try:
                        sync_result = self.sync_playlist_videos(
                            monitor.playlist_id, session
                        )

                        results["synced_playlists"] += 1
                        results["total_new_videos"] += sync_result["new_videos"]
                        results["total_downloads"] += sync_result["downloaded_videos"]

                        if sync_result["errors"]:
                            results["errors"].extend(sync_result["errors"])

                    except Exception as e:
                        error_msg = f"Failed to sync playlist {monitor.name}: {str(e)}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

                logger.info(f"Synced all playlists: {results}")
                return results

        except Exception as e:
            logger.error(f"Failed to sync all playlists: {e}")
            raise


# Global instance
youtube_playlist_service = YouTubePlaylistService()
