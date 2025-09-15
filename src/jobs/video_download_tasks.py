"""
Video Download Background Tasks
Phase 2: Media Processing Optimization - yt-dlp Background Jobs
"""

import json
import os
import subprocess
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from celery import current_task

from src.jobs.base_task import VideoProcessingTask
from src.jobs.celery_app import celery_app
from src.jobs.redis_manager import redis_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.video_download_tasks")


@celery_app.task(
    base=VideoProcessingTask, bind=True, name="video_download_tasks.download_video"
)
def download_video(
    self, video_url: str, download_options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Download video using yt-dlp as background job

    Args:
        video_url: URL of video to download
        download_options: yt-dlp options and preferences

    Returns:
        Dict with download result information
    """
    try:
        task_id = self.request.id
        self.update_progress(5, f"Starting download: {video_url}")

        # Validate arguments
        if not video_url:
            raise ValueError("video_url is required")

        # Set default download options
        default_options = {
            "format": "best[height<=720]",
            "output_template": "%(title)s.%(ext)s",
            "extract_info": True,
            "download_path": "/tmp/mvidarr_downloads",
            "max_filesize": "500M",
        }

        options = {**default_options, **(download_options or {})}

        self.update_progress(10, "Preparing download environment")

        # Ensure download directory exists
        download_path = options.get("download_path", "/tmp/mvidarr_downloads")
        os.makedirs(download_path, exist_ok=True)

        # Build yt-dlp command
        cmd = [
            "yt-dlp",
            "--format",
            options.get("format", "best[height<=720]"),
            "--output",
            os.path.join(
                download_path, options.get("output_template", "%(title)s.%(ext)s")
            ),
            "--no-playlist",
            "--write-info-json",
            "--write-thumbnail",
            "--progress-template",
            'download:{"percent":"%(progress.downloaded_bytes)s/%(progress.total_bytes)s","speed":"%(progress.speed)s"}',
        ]

        # Add optional parameters
        if options.get("max_filesize"):
            cmd.extend(["--max-filesize", options["max_filesize"]])

        if options.get("extract_info"):
            cmd.append("--write-info-json")

        # Add the video URL
        cmd.append(video_url)

        self.update_progress(15, "Starting yt-dlp download process")

        # Execute yt-dlp with progress monitoring
        result = self._execute_ytdlp_with_progress(cmd, task_id)

        # Process download result
        if result["success"]:
            self.update_progress(90, "Processing download result")

            # Extract video information
            video_info = self._extract_video_info(
                result.get("output_file"), download_path
            )

            # Store in database (if needed)
            if video_info:
                self._store_video_in_database(video_info)

            self.update_progress(100, "Download completed successfully")

            return {
                "success": True,
                "video_url": video_url,
                "output_file": result.get("output_file"),
                "video_info": video_info,
                "download_path": download_path,
                "task_id": task_id,
                "completed_at": datetime.utcnow().isoformat(),
            }
        else:
            raise Exception(
                f"yt-dlp download failed: {result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        logger.error(f"Video download task failed: {e}")
        self.update_progress(-1, f"Download failed: {str(e)}")
        raise

    def _execute_ytdlp_with_progress(
        self, cmd: List[str], task_id: str
    ) -> Dict[str, Any]:
        """Execute yt-dlp command with progress monitoring"""
        try:
            # Start subprocess
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            output_lines = []
            current_progress = 15

            # Monitor output for progress updates
            while True:
                # Check for cancellation
                if self.is_cancelled():
                    process.terminate()
                    process.wait()
                    raise Exception("Task was cancelled")

                # Read output line
                line = process.stdout.readline()
                if not line:
                    break

                output_lines.append(line.strip())

                # Parse progress from yt-dlp output
                progress_info = self._parse_ytdlp_progress(line)
                if progress_info:
                    # Update progress (map download progress to 15-85% range)
                    download_percent = progress_info.get("percent", 0)
                    overall_percent = 15 + int(
                        download_percent * 0.7
                    )  # 15% + (70% * download_percent)

                    message = f"Downloading: {download_percent:.1f}%"
                    if progress_info.get("speed"):
                        message += f" ({progress_info['speed']})"

                    if overall_percent > current_progress:
                        current_progress = overall_percent
                        self.update_progress(current_progress, message)

                # Log important lines
                if any(
                    keyword in line.lower()
                    for keyword in ["error", "warning", "downloading"]
                ):
                    logger.info(f"yt-dlp: {line.strip()}")

            # Wait for process completion
            return_code = process.wait()

            if return_code == 0:
                # Find output file from the logs
                output_file = self._extract_output_file_from_logs(output_lines)

                return {
                    "success": True,
                    "return_code": return_code,
                    "output": "\n".join(output_lines),
                    "output_file": output_file,
                }
            else:
                return {
                    "success": False,
                    "return_code": return_code,
                    "error": "\n".join(
                        output_lines[-10:]
                    ),  # Last 10 lines for error context
                }

        except Exception as e:
            logger.error(f"Error executing yt-dlp: {e}")
            return {"success": False, "error": str(e)}

    def _parse_ytdlp_progress(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse progress information from yt-dlp output"""
        try:
            # Look for download progress indicators
            if "[download]" in line and "%" in line:
                # Extract percentage
                import re

                percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
                if percent_match:
                    percent = float(percent_match.group(1))

                    # Extract speed if available
                    speed_match = re.search(r"(\d+(?:\.\d+)?(?:KiB|MiB|GiB)/s)", line)
                    speed = speed_match.group(1) if speed_match else None

                    return {"percent": percent, "speed": speed, "raw_line": line}

            return None

        except Exception as e:
            logger.debug(f"Error parsing yt-dlp progress: {e}")
            return None

    def _extract_output_file_from_logs(self, output_lines: List[str]) -> Optional[str]:
        """Extract the output file path from yt-dlp logs"""
        try:
            for line in reversed(output_lines):  # Search from end
                if "[download] Destination:" in line:
                    return line.split("[download] Destination:", 1)[1].strip()
                elif "has already been downloaded" in line:
                    # File was already downloaded
                    import re

                    match = re.search(r"\[(.*?)\]", line)
                    if match:
                        return match.group(1)

            return None

        except Exception as e:
            logger.error(f"Error extracting output file: {e}")
            return None

    def _extract_video_info(
        self, output_file: str, download_path: str
    ) -> Optional[Dict[str, Any]]:
        """Extract video information from downloaded files"""
        try:
            if not output_file:
                return None

            # Look for .info.json file
            base_name = os.path.splitext(output_file)[0]
            info_file = f"{base_name}.info.json"

            if os.path.exists(info_file):
                import json

                with open(info_file, "r", encoding="utf-8") as f:
                    info = json.load(f)

                return {
                    "title": info.get("title", ""),
                    "description": info.get("description", ""),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", ""),
                    "upload_date": info.get("upload_date", ""),
                    "view_count": info.get("view_count", 0),
                    "thumbnail": info.get("thumbnail", ""),
                    "webpage_url": info.get("webpage_url", ""),
                    "format": info.get("format", ""),
                    "filesize": info.get("filesize", 0),
                    "video_id": info.get("id", ""),
                    "extractor": info.get("extractor", ""),
                }

            return None

        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            return None

    def _store_video_in_database(self, video_info: Dict[str, Any]) -> bool:
        """Store video information in database"""
        try:
            # This would integrate with your existing database models
            # For now, just log the information
            logger.info(
                f"Would store video in database: {video_info.get('title', 'Unknown')}"
            )

            # TODO: Integrate with actual database storage
            # from src.services.video_service import video_service
            # video_service.create_video_from_info(video_info)

            return True

        except Exception as e:
            logger.error(f"Error storing video in database: {e}")
            return False


@celery_app.task(
    base=VideoProcessingTask, bind=True, name="video_download_tasks.download_playlist"
)
def download_playlist(
    self, playlist_url: str, download_options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Download entire playlist as background job

    Args:
        playlist_url: URL of playlist to download
        download_options: yt-dlp options and preferences

    Returns:
        Dict with playlist download results
    """
    try:
        task_id = self.request.id
        self.update_progress(5, f"Starting playlist download: {playlist_url}")

        # Set default options
        default_options = {
            "format": "best[height<=720]",
            "output_template": "%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s",
            "download_path": "/tmp/mvidarr_downloads",
            "max_videos": 50,  # Limit playlist size
            "max_filesize": "500M",
        }

        options = {**default_options, **(download_options or {})}

        self.update_progress(10, "Extracting playlist information")

        # Get playlist info first
        playlist_info = self._get_playlist_info(playlist_url)
        if not playlist_info:
            raise Exception("Failed to extract playlist information")

        total_videos = min(
            len(playlist_info.get("entries", [])), options.get("max_videos", 50)
        )
        self.update_progress(15, f"Found {total_videos} videos in playlist")

        # Download videos one by one
        downloaded_videos = []
        failed_downloads = []

        for i, entry in enumerate(playlist_info.get("entries", [])[:total_videos]):
            if self.is_cancelled():
                break

            video_url = entry.get("webpage_url") or entry.get("url")
            video_title = entry.get("title", f"Video {i+1}")

            # Update progress
            percent = 15 + int((i / total_videos) * 70)  # 15-85% for downloads
            self.update_progress(
                percent, f"Downloading {i+1}/{total_videos}: {video_title[:50]}..."
            )

            try:
                # Download individual video
                result = self._download_single_video(video_url, options, video_title)
                if result["success"]:
                    downloaded_videos.append(result)
                else:
                    failed_downloads.append(
                        {
                            "video_url": video_url,
                            "title": video_title,
                            "error": result.get("error", "Unknown error"),
                        }
                    )

            except Exception as e:
                logger.error(f"Failed to download video {video_title}: {e}")
                failed_downloads.append(
                    {"video_url": video_url, "title": video_title, "error": str(e)}
                )

        self.update_progress(90, "Processing playlist results")

        # Store playlist information
        playlist_result = {
            "success": True,
            "playlist_url": playlist_url,
            "playlist_title": playlist_info.get("title", "Unknown Playlist"),
            "total_videos": total_videos,
            "downloaded_count": len(downloaded_videos),
            "failed_count": len(failed_downloads),
            "downloaded_videos": downloaded_videos,
            "failed_downloads": failed_downloads,
            "task_id": task_id,
            "completed_at": datetime.utcnow().isoformat(),
        }

        self.update_progress(
            100,
            f"Playlist download completed: {len(downloaded_videos)}/{total_videos} successful",
        )

        return playlist_result

    except Exception as e:
        logger.error(f"Playlist download task failed: {e}")
        self.update_progress(-1, f"Playlist download failed: {str(e)}")
        raise

    def _get_playlist_info(self, playlist_url: str) -> Optional[Dict[str, Any]]:
        """Get playlist information without downloading videos"""
        try:
            import json
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w+", suffix=".json", delete=False
            ) as tmp_file:
                cmd = [
                    "yt-dlp",
                    "--dump-json",
                    "--flat-playlist",
                    "--no-download",
                    playlist_url,
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode == 0:
                    # Parse JSON lines
                    entries = []
                    for line in result.stdout.strip().split("\n"):
                        if line:
                            try:
                                entry = json.loads(line)
                                entries.append(entry)
                            except json.JSONDecodeError:
                                continue

                    if entries:
                        return {
                            "title": entries[0].get(
                                "playlist_title", "Unknown Playlist"
                            ),
                            "entries": entries,
                            "playlist_count": len(entries),
                        }

                return None

        except Exception as e:
            logger.error(f"Error getting playlist info: {e}")
            return None
        finally:
            try:
                os.unlink(tmp_file.name)
            except:
                pass

    def _download_single_video(
        self, video_url: str, options: Dict[str, Any], title: str
    ) -> Dict[str, Any]:
        """Download a single video with simplified options"""
        try:
            # Simplified download for playlist items
            cmd = [
                "yt-dlp",
                "--format",
                options.get("format", "best[height<=720]"),
                "--output",
                os.path.join(
                    options.get("download_path", "/tmp"),
                    options.get("output_template", "%(title)s.%(ext)s"),
                ),
                "--no-playlist",
                "--quiet",
                video_url,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300  # 5 minutes per video
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "video_url": video_url,
                    "title": title,
                    "output": result.stdout,
                }
            else:
                return {
                    "success": False,
                    "video_url": video_url,
                    "title": title,
                    "error": result.stderr,
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "video_url": video_url,
                "title": title,
                "error": "Download timeout (5 minutes)",
            }
        except Exception as e:
            return {
                "success": False,
                "video_url": video_url,
                "title": title,
                "error": str(e),
            }


@celery_app.task(
    base=VideoProcessingTask, bind=True, name="video_download_tasks.extract_video_info"
)
def extract_video_info(self, video_url: str) -> Dict[str, Any]:
    """
    Extract video information without downloading

    Args:
        video_url: URL of video to analyze

    Returns:
        Dict with video information
    """
    try:
        task_id = self.request.id
        self.update_progress(10, f"Extracting info: {video_url}")

        # Use yt-dlp to extract information
        cmd = ["yt-dlp", "--dump-json", "--no-download", video_url]

        self.update_progress(30, "Running yt-dlp info extraction")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            import json

            info = json.loads(result.stdout)

            self.update_progress(80, "Processing video information")

            # Extract relevant information
            video_info = {
                "success": True,
                "video_url": video_url,
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", ""),
                "upload_date": info.get("upload_date", ""),
                "view_count": info.get("view_count", 0),
                "like_count": info.get("like_count", 0),
                "thumbnail": info.get("thumbnail", ""),
                "webpage_url": info.get("webpage_url", ""),
                "formats": [
                    {
                        "format_id": fmt.get("format_id", ""),
                        "ext": fmt.get("ext", ""),
                        "resolution": fmt.get("resolution", ""),
                        "filesize": fmt.get("filesize", 0),
                        "format_note": fmt.get("format_note", ""),
                    }
                    for fmt in info.get("formats", [])
                ],
                "video_id": info.get("id", ""),
                "extractor": info.get("extractor", ""),
                "task_id": task_id,
                "extracted_at": datetime.utcnow().isoformat(),
            }

            self.update_progress(100, "Video information extracted successfully")
            return video_info

        else:
            raise Exception(f"yt-dlp failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        self.update_progress(-1, "Video info extraction timeout")
        raise Exception("Video info extraction timeout")
    except Exception as e:
        logger.error(f"Video info extraction failed: {e}")
        self.update_progress(-1, f"Info extraction failed: {str(e)}")
        raise


@celery_app.task(
    base=VideoProcessingTask,
    bind=True,
    name="video_download_tasks.bulk_download_videos",
)
def bulk_download_videos(
    self, video_data: List[Dict[str, Any]], download_options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Download multiple videos in a single background job

    Args:
        video_data: List of video info dicts with 'url' and optionally 'video_id'
        download_options: Common download options for all videos

    Returns:
        Dict with bulk download results
    """
    try:
        task_id = self.request.id
        total_videos = len(video_data)
        results = []

        self.update_progress(0, f"Starting bulk download of {total_videos} videos")

        for i, video_info in enumerate(video_data):
            video_url = video_info.get("url")
            video_id = video_info.get("video_id")

            if not video_url:
                results.append(
                    {"video_id": video_id, "success": False, "error": "No URL provided"}
                )
                continue

            # Update progress
            progress_percent = int(
                (i / total_videos) * 90
            )  # Leave 10% for final processing
            self.update_progress(
                progress_percent, f"Downloading video {i+1}/{total_videos}: {video_url}"
            )

            try:
                # Perform individual video download within the bulk task
                individual_options = {**(download_options or {}), "video_id": video_id}

                # Use yt-dlp directly (same logic as individual download task)
                output_dir = individual_options.get("output_dir", "/tmp")
                format_spec = individual_options.get("format", "best[height<=720]")

                cmd = [
                    "yt-dlp",
                    "--format",
                    format_spec,
                    "--output",
                    f"{output_dir}/%(title)s.%(ext)s",
                    "--no-playlist",
                    video_url,
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minutes per video
                )

                if result.returncode == 0:
                    results.append(
                        {
                            "video_id": video_id,
                            "video_url": video_url,
                            "success": True,
                            "output": result.stdout,
                        }
                    )
                else:
                    results.append(
                        {
                            "video_id": video_id,
                            "video_url": video_url,
                            "success": False,
                            "error": result.stderr,
                        }
                    )

            except Exception as e:
                logger.error(f"Failed to download video {video_url}: {e}")
                results.append(
                    {
                        "video_id": video_id,
                        "video_url": video_url,
                        "success": False,
                        "error": str(e),
                    }
                )

        # Final processing
        self.update_progress(
            100,
            f"Completed bulk download: {len([r for r in results if r['success']])} successful, {len([r for r in results if not r['success']])} failed",
        )

        return {
            "success": True,
            "total_videos": total_videos,
            "successful_downloads": len([r for r in results if r["success"]]),
            "failed_downloads": len([r for r in results if not r["success"]]),
            "results": results,
            "completed_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Bulk download failed: {e}")
        self.update_progress(-1, f"Bulk download failed: {str(e)}")
        raise


# Utility functions for task management
def submit_video_download(
    video_url: str, download_options: Dict[str, Any] = None
) -> str:
    """Submit video download job and return task ID"""
    task = download_video.delay(video_url, download_options)
    logger.info(f"Submitted video download job {task.id} for URL: {video_url}")
    return task.id


def submit_playlist_download(
    playlist_url: str, download_options: Dict[str, Any] = None
) -> str:
    """Submit playlist download job and return task ID"""
    task = download_playlist.delay(playlist_url, download_options)
    logger.info(f"Submitted playlist download job {task.id} for URL: {playlist_url}")
    return task.id


def submit_video_info_extraction(video_url: str) -> str:
    """Submit video info extraction job and return task ID"""
    task = extract_video_info.delay(video_url)
    logger.info(f"Submitted video info extraction job {task.id} for URL: {video_url}")
    return task.id


def submit_bulk_download(
    video_data: List[Dict[str, Any]], download_options: Dict[str, Any] = None
) -> str:
    """Submit bulk video download job and return task ID"""
    task = bulk_download_videos.delay(video_data, download_options)
    logger.info(f"Submitted bulk download job {task.id} for {len(video_data)} videos")
    return task.id


if __name__ == "__main__":
    # For testing: python -m src.jobs.video_download_tasks
    print("Video Download Tasks Test")
    print("=" * 50)

    # Test video info extraction (quick test)
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll for testing

    try:
        print(f"Testing video info extraction for: {test_url}")
        task_id = submit_video_info_extraction(test_url)
        print(f"Task submitted with ID: {task_id}")

        # You would normally wait for the task to complete and check results
        # For testing, we just confirm the task was submitted
        print("✅ Video download tasks test completed!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
