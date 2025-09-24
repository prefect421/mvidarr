"""
Simple Video Download Task - Fixed version
"""

import os
import subprocess
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional

from src.jobs.celery_app import celery_app
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.simple_download_task")


@celery_app.task(bind=True, name="simple_download_task.download_video")
def simple_download_video(
    self, video_url: str, download_options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Simple video download using yt-dlp directly
    
    Args:
        video_url: URL of video to download
        download_options: Download configuration
        
    Returns:
        Dict with download result
    """
    try:
        task_id = self.request.id
        options = download_options or {}
        
        # Extract options
        video_id = options.get("video_id")
        download_id = options.get("download_id")
        artist = options.get("artist", "Unknown Artist")
        title = options.get("title", "Unknown Title")
        quality = options.get("quality", "best")
        upgrade_mode = options.get("upgrade_mode", False)
        artist_id = options.get("artist_id")
        
        logger.info(f"Starting download task {task_id}: {artist} - {title}")
        if upgrade_mode:
            logger.info(f"Video quality upgrade mode enabled for video {video_id}")
        
        # Update progress in database
        _update_download_progress(download_id, 10, "Starting download...")
        
        # Set up download directory
        from src.services.settings_service import settings
        music_videos_path = settings.get("music_videos_path", "data/musicvideos")
        
        # Create artist directory
        artist_dir = os.path.join(music_videos_path, _sanitize_filename(artist))
        os.makedirs(artist_dir, exist_ok=True)
        
        # Build yt-dlp command with appropriate format string
        output_template = os.path.join(artist_dir, f"{_sanitize_filename(title)}.%(ext)s")
        
        # Determine the best format string to use
        if upgrade_mode:
            # Use advanced format selection for video quality upgrades
            try:
                from src.services.video_quality_service import video_quality_service
                format_string = video_quality_service.generate_ytdlp_format_string(
                    user_id=None, artist_id=artist_id
                )
                logger.info(f"Using advanced format string for upgrade: {format_string[:100]}...")
            except Exception as e:
                logger.warning(f"Failed to generate advanced format string: {e}")
                # Fall back to audio-guaranteed format string that supports 4K
                format_string = "best[height<=2160][ext=mp4]/best[height<=2160]/bv[height<=2160]+ba/bestvideo[height<=2160]+bestaudio/best"
                logger.info(f"Using fallback high-quality format string (4K capable)")
        else:
            # Use optimized format for regular downloads that respects user quality settings
            try:
                from src.services.video_quality_service import video_quality_service
                format_string = video_quality_service.generate_ytdlp_format_string(
                    user_id=None, artist_id=artist_id
                )
                logger.info(f"Using user-configured format string for regular download: {format_string[:100]}...")
            except Exception as e:
                logger.warning(f"Failed to generate user format string: {e}")
                # Fall back to audio-guaranteed 4K capable format
                format_string = "best[height<=2160][ext=mp4]/best[height<=2160]/bv[height<=2160]+ba/bestvideo[height<=2160]+bestaudio/best"
                logger.info(f"Using fallback format string for regular download")
        
        cmd = [
            "yt-dlp",
            "--format", format_string,
            "--output", output_template,
            "--no-playlist",
            "--write-info-json",
            "--embed-metadata",
            "--ignore-errors",
            video_url
        ]
        
        _update_download_progress(download_id, 30, "Downloading video...")
        
        # Execute download
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes timeout
        )
        
        if result.returncode == 0:
            # Find the downloaded file
            downloaded_files = []
            for ext in ['.mp4', '.webm', '.mkv', '.avi']:
                potential_file = output_template.replace('%(ext)s', ext.lstrip('.'))
                if os.path.exists(potential_file):
                    downloaded_files.append(potential_file)
                    break
            
            # Store task result in download metadata for upgrade processing
            task_result = {
                "success": True,
                "task_id": task_id,
                "video_url": video_url,
                "output_files": downloaded_files,
                "artist": artist,
                "title": title,
                "stdout": result.stdout,
                "completed_at": datetime.utcnow().isoformat()
            }
            
            # Update download metadata with task result BEFORE calling progress update
            # This ensures the metadata is available when _update_video_after_download is called
            if download_id:
                try:
                    from src.database.connection import get_db
                    from src.database.models import Download
                    with get_db() as session:
                        download = session.query(Download).filter(Download.id == download_id).first()
                        if download:
                            if not download.download_metadata:
                                download.download_metadata = {}
                            download.download_metadata['task_result'] = task_result
                            session.commit()
                            logger.info(f"Updated download metadata for download {download_id}")
                except Exception as e:
                    logger.error(f"Failed to update download metadata: {e}")
            
            # Call progress update AFTER metadata is saved to ensure proper file linking
            _update_download_progress(download_id, 100, "Download completed successfully")
            
            # Additional validation: Ensure the video was properly linked
            if download_id and video_id:
                try:
                    from src.database.models import Video
                    with get_db() as session:
                        video = session.query(Video).filter(Video.id == video_id).first()
                        if video and video.local_path is None:
                            logger.warning(f"⚠️  Video {video_id} was not properly linked after download completion")
                            logger.warning(f"   Attempting emergency file linking recovery...")
                            
                            # Try emergency recovery by calling the linking function again
                            download_record = session.query(Download).filter(Download.id == download_id).first()
                            if download_record:
                                _update_video_after_download(video, download_record, session)
                                session.commit()
                                session.refresh(video)
                                if video.local_path:
                                    logger.info(f"✅ Emergency linking recovery successful: {video.local_path}")
                                else:
                                    logger.error(f"❌ Emergency linking recovery FAILED for video {video_id}")
                                    logger.error(f"   Manual intervention required - check fix_unlinked_videos.py")
                            else:
                                logger.error(f"❌ No download record found for emergency recovery")
                        elif video:
                            logger.info(f"✅ Video {video_id} successfully linked to {video.local_path}")
                except Exception as e:
                    logger.error(f"Failed to validate video linking: {e}")
            logger.info(f"Download completed successfully: {task_id}")
            
            return task_result
        else:
            error_msg = f"yt-dlp failed: {result.stderr}"
            logger.error(f"Download failed for {task_id}: {error_msg}")
            _update_download_progress(download_id, -1, f"Download failed: {result.stderr[:100]}")
            
            return {
                "success": False,
                "task_id": task_id,
                "error": error_msg,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
    except subprocess.TimeoutExpired:
        error_msg = "Download timed out after 30 minutes"
        logger.error(f"Download timeout for {task_id}")
        _update_download_progress(download_id, -1, error_msg)
        return {"success": False, "error": error_msg}
        
    except Exception as e:
        error_msg = f"Download failed: {str(e)}"
        logger.error(f"Download exception for {task_id}: {error_msg}")
        _update_download_progress(download_id, -1, error_msg)
        return {"success": False, "error": error_msg}


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename for filesystem"""
    import re
    # Remove or replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    sanitized = re.sub(r'[^\w\s-]', '', sanitized).strip()
    return sanitized[:100] if sanitized else "Unknown"


def _update_download_progress(download_id: Optional[int], progress: int, message: str):
    """Update download progress in database"""
    if not download_id:
        return
        
    try:
        from src.database.connection import get_db
        from src.database.models import Download, Video, VideoStatus
        
        with get_db() as session:
            download = session.query(Download).filter(Download.id == download_id).first()
            if download:
                download.progress = progress
                if progress == 100:
                    download.status = "completed"
                    download.completed_at = datetime.utcnow()
                    
                    # CRITICAL: Update the associated video status and quality information
                    if download.video_id:
                        video = session.query(Video).filter(Video.id == download.video_id).first()
                        if video:
                            video.status = VideoStatus.DOWNLOADED
                            
                            # Always update the video record with file info and technical details
                            upgrade_mode = download.download_metadata and download.download_metadata.get('upgrade_mode', False)
                            if upgrade_mode:
                                logger.info(f"Processing quality upgrade for video {download.video_id}")
                                _update_video_after_quality_upgrade(video, download, session)
                            else:
                                # For regular downloads, ensure we update file path and technical details
                                logger.info(f"Processing regular download completion for video {download.video_id}")
                                logger.info(f"Before _update_video_after_download: video.local_path = {video.local_path}")
                                _update_video_after_download(video, download, session)
                                # Refresh the video object to get latest data
                                session.refresh(video)
                                logger.info(f"After _update_video_after_download: video.local_path = {video.local_path}")
                                
                                # Additional verification
                                if not video.local_path:
                                    logger.error(f"❌ CRITICAL: _update_video_after_download failed to set local_path for video {download.video_id}")
                                    logger.error(f"   Download metadata: {download.download_metadata}")
                                    
                                    # DEFENSIVE: Retry the linking one more time with fresh session
                                    logger.warning(f"🔄 Attempting emergency retry for video {download.video_id}")
                                    try:
                                        # Force refresh the objects
                                        session.refresh(video)
                                        session.refresh(download)
                                        
                                        # Try again
                                        _update_video_after_download(video, download, session)
                                        session.commit()
                                        session.refresh(video)
                                        
                                        if video.local_path:
                                            logger.info(f"✅ Emergency retry SUCCESSFUL for video {download.video_id}: {video.local_path}")
                                        else:
                                            logger.error(f"❌ Emergency retry FAILED for video {download.video_id}")
                                            
                                            # Last resort: try to directly set from metadata
                                            if download.download_metadata:
                                                task_result = download.download_metadata.get('task_result', {})
                                                output_files = task_result.get('output_files', [])
                                                if output_files and os.path.exists(output_files[0]):
                                                    logger.warning(f"🚨 LAST RESORT: Setting local_path directly from metadata")
                                                    video.local_path = output_files[0]
                                                    session.commit()
                                                    logger.info(f"✅ Last resort fix successful: {video.local_path}")
                                    except Exception as retry_error:
                                        logger.error(f"❌ Emergency retry failed with error: {retry_error}")
                                else:
                                    logger.info(f"✅ Successfully updated video {download.video_id} local_path")
                            
                            logger.info(f"Updated video {download.video_id} status to DOWNLOADED")
                            
                            # Trigger automatic metadata enrichment for newly downloaded video
                            try:
                                from src.services.metadata_enrichment_service import MetadataEnrichmentService
                                enrichment_service = MetadataEnrichmentService()
                                
                                # Enrich metadata asynchronously (don't wait for completion)
                                import asyncio
                                async def enrich_metadata():
                                    result = await enrichment_service.enrich_video_metadata(
                                        download.video_id, force_refresh=True
                                    )
                                    if result.success:
                                        logger.info(f"Metadata enrichment completed for video {download.video_id}: "
                                                   f"enriched {len(result.enriched_fields or [])} fields")
                                    else:
                                        logger.warning(f"Metadata enrichment failed for video {download.video_id}: "
                                                      f"{result.errors}")
                                
                                # Run in background without blocking download completion
                                try:
                                    loop = asyncio.get_event_loop()
                                    loop.create_task(enrich_metadata())
                                except RuntimeError:
                                    # If no event loop exists, create one for this task
                                    asyncio.run(enrich_metadata())
                                    
                                logger.info(f"Triggered metadata enrichment for newly downloaded video {download.video_id}")
                                
                            except Exception as enrichment_error:
                                logger.error(f"Failed to trigger metadata enrichment for video {download.video_id}: {enrichment_error}")
                                # Don't fail the download if metadata enrichment fails
                            
                            # Final validation: Ensure video record has essential metadata
                            session.refresh(video)  # Get latest data
                            validation_warnings = []
                            if not video.local_path:
                                validation_warnings.append("Missing local_path")
                            if not video.duration:
                                validation_warnings.append("Missing duration")
                            if not video.quality:
                                validation_warnings.append("Missing quality")
                            
                            if validation_warnings:
                                logger.warning(f"⚠️ Video {download.video_id} download validation issues: {validation_warnings}")
                                logger.warning(f"   This may cause playback issues. Consider running metadata extraction manually.")
                            else:
                                logger.info(f"✅ Video {download.video_id} download validation passed - all metadata present")
                    
                elif progress == -1:
                    download.status = "failed"
                    download.error_message = message
                    
                    # Update video status to FAILED if download failed
                    if download.video_id:
                        video = session.query(Video).filter(Video.id == download.video_id).first()
                        if video:
                            video.status = VideoStatus.FAILED
                            logger.info(f"Updated video {download.video_id} status to FAILED")
                else:
                    download.status = "downloading"
                
                session.commit()
                logger.info(f"Updated download {download_id}: {progress}% - {message}")
    except Exception as e:
        logger.error(f"Failed to update download progress: {e}")


def _update_video_after_quality_upgrade(video, download, session):
    """Update video record with new quality information after successful upgrade"""
    try:
        import os
        import glob
        # Find the downloaded file
        downloaded_files = []
        if hasattr(download, 'download_metadata') and download.download_metadata:
            # Try to get output files from the task result stored in download metadata
            task_result = download.download_metadata.get('task_result', {})
            downloaded_files = task_result.get('output_files', [])
        
        # If no files found in metadata, try to find the file by pattern matching
        if not downloaded_files:
            from src.services.settings_service import settings
            music_videos_path = settings.get("music_videos_path", "data/musicvideos")
            
            # Get artist name
            artist_name = "Unknown Artist"
            if video.artist_id:
                from src.database.models import Artist
                artist = session.query(Artist).filter(Artist.id == video.artist_id).first()
                if artist:
                    artist_name = artist.name
            
            # Look for files matching the upgrade pattern
            pattern = os.path.join(music_videos_path, _sanitize_filename(artist_name), "*Quality Upgrade*")
            potential_files = glob.glob(pattern)
            
            # Filter for video files and find the most recent one for this video
            video_exts = ['.mp4', '.webm', '.mkv', '.avi']
            for file_path in potential_files:
                if any(file_path.endswith(ext) for ext in video_exts):
                    # Check if this file was recently created (within last 10 minutes)
                    import time
                    file_time = os.path.getmtime(file_path)
                    if time.time() - file_time < 600:  # 10 minutes
                        downloaded_files.append(file_path)
        
        if downloaded_files:
            new_file_path = downloaded_files[0]  # Use the first (or only) file
            logger.info(f"Found upgraded file for video {video.id}: {new_file_path}")
            
            # Extract video metadata from the new file
            try:
                import subprocess
                import json
                
                # Use ffprobe to get video information
                result = subprocess.run([
                    'ffprobe', '-v', 'quiet', '-print_format', 'json',
                    '-show_format', '-show_streams', new_file_path
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    probe_data = json.loads(result.stdout)
                    
                    # Extract video stream info
                    video_stream = next((s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video'), None)
                    if video_stream:
                        new_width = video_stream.get('width')
                        new_height = video_stream.get('height')
                        new_codec = video_stream.get('codec_name')
                        
                        # Update video record
                        video.local_path = new_file_path
                        
                        # Update quality based on height
                        if new_height:
                            video.quality = f"{new_height}p"
                        
                        # Update metadata
                        if not video.video_metadata:
                            video.video_metadata = {}
                        
                        video.video_metadata.update({
                            'width': new_width,
                            'height': new_height,
                            'video_codec': new_codec,
                            'quality_upgraded': True,
                            'quality_upgrade_date': datetime.utcnow().isoformat(),
                            'original_file_path': video.video_metadata.get('original_file_path', video.local_path),
                            'file_size': os.path.getsize(new_file_path) if os.path.exists(new_file_path) else None
                        })
                        
                        session.commit()
                        logger.info(f"Updated video {video.id} quality to {video.quality} with new file: {new_file_path}")
                        
                    else:
                        logger.warning(f"No video stream found in upgraded file: {new_file_path}")
                else:
                    logger.error(f"ffprobe failed for file {new_file_path}: {result.stderr}")
                    
            except Exception as e:
                logger.error(f"Failed to extract metadata from upgraded file {new_file_path}: {e}")
        else:
            logger.warning(f"No upgraded file found for video {video.id}")
            
    except Exception as e:
        logger.error(f"Failed to update video after quality upgrade: {e}")


def _update_video_after_download(video, download, session):
    """Update video record with file path and technical details after successful download"""
    try:
        import os
        import glob
        
        # Find the downloaded file
        downloaded_files = []
        
        # First, try to get output files from the task result stored in download metadata
        if hasattr(download, 'download_metadata') and download.download_metadata:
            task_result = download.download_metadata.get('task_result', {})
            downloaded_files = task_result.get('output_files', [])
            logger.info(f"🔍 Found {len(downloaded_files)} files in download metadata for video {video.id}: {downloaded_files}")
            
            # Detailed validation of each file
            for i, file_path in enumerate(downloaded_files):
                if file_path and os.path.exists(file_path):
                    logger.info(f"  ✅ File {i+1} exists: {file_path}")
                elif file_path:
                    logger.warning(f"  ❌ File {i+1} missing: {file_path}")
                else:
                    logger.warning(f"  ❌ File {i+1} is empty/None")
        else:
            logger.warning(f"No download metadata found for video {video.id}, will search filesystem")
        
        # If no files found in metadata, try to find the file by searching download locations
        if not downloaded_files:
            from src.services.settings_service import settings
            music_videos_path = settings.get("music_videos_path", "data/musicvideos")
            
            # Get artist name for file location
            artist_name = "Unknown Artist"
            if video.artist_id:
                from src.database.models import Artist
                artist = session.query(Artist).filter(Artist.id == video.artist_id).first()
                if artist:
                    artist_name = artist.name
            
            # Clean video title for filename matching
            video_title = video.title or f"Video_{video.id}"
            clean_title = _sanitize_filename(video_title)
            
            # Search patterns for downloaded files
            search_patterns = [
                # Organized location: data/musicvideos/Artist/Title.ext
                os.path.join(music_videos_path, _sanitize_filename(artist_name), f"*{clean_title[:20]}*"),
                # YouTube download location: data/musicvideos/YouTube/Date-Title/file
                os.path.join(music_videos_path, "YouTube", f"*{clean_title[:20]}*", "*.mp4"),
                os.path.join(music_videos_path, "YouTube", f"*{clean_title[:20]}*", "*.webm"),
                # Direct download location
                os.path.join(music_videos_path, "*", f"*{clean_title[:20]}*"),
            ]
            
            # Search for video files
            video_exts = ['.mp4', '.webm', '.mkv', '.avi']
            for pattern in search_patterns:
                potential_files = glob.glob(pattern)
                for file_path in potential_files:
                    if any(file_path.endswith(ext) for ext in video_exts):
                        # Check if this file was recently created (within last 30 minutes)
                        import time
                        if os.path.exists(file_path):
                            file_time = os.path.getmtime(file_path)
                            if time.time() - file_time < 1800:  # 30 minutes
                                downloaded_files.append(file_path)
                                break  # Use first match
                if downloaded_files:
                    break  # Stop searching if we found a file
        
        if downloaded_files:
            new_file_path = downloaded_files[0]  # Use the first (or only) file
            logger.info(f"Found downloaded file for video {video.id}: {new_file_path}")
            
            # Extract video metadata from the file using FFprobe
            try:
                import subprocess
                import json
                
                # Use ffprobe to get video information
                result = subprocess.run([
                    'ffprobe', '-v', 'quiet', '-print_format', 'json',
                    '-show_format', '-show_streams', new_file_path
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    probe_data = json.loads(result.stdout)
                    
                    # Extract duration from format
                    format_info = probe_data.get('format', {})
                    duration = float(format_info.get('duration', 0))
                    
                    # Extract video stream info
                    video_stream = next((s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video'), None)
                    if video_stream:
                        width = video_stream.get('width', 0)
                        height = video_stream.get('height', 0)
                        codec = video_stream.get('codec_name', 'unknown')
                        
                        # Determine quality based on height
                        if height >= 2160:
                            quality = "4K"
                        elif height >= 1440:
                            quality = "1440p"
                        elif height >= 1080:
                            quality = "1080p"
                        elif height >= 720:
                            quality = "720p"
                        elif height >= 480:
                            quality = "480p"
                        else:
                            quality = "SD"
                        
                        # Update video record with file path and technical details
                        video.local_path = new_file_path
                        video.duration = duration
                        video.quality = quality
                        
                        # Update or create video_metadata
                        existing_metadata = video.video_metadata or {}
                        existing_metadata.update({
                            'width': width,
                            'height': height,
                            'video_codec': codec,
                            'file_size': os.path.getsize(new_file_path) if os.path.exists(new_file_path) else None,
                            'file_path': new_file_path,
                            'extraction_date': datetime.utcnow().isoformat()
                        })
                        video.video_metadata = existing_metadata
                        
                        session.commit()
                        logger.info(f"✅ Updated video {video.id} with complete metadata:")
                        logger.info(f"   File: {new_file_path}")
                        logger.info(f"   Duration: {duration:.1f}s")
                        logger.info(f"   Quality: {quality} ({width}x{height})")
                        logger.info(f"   Codec: {codec}")
                        
                    else:
                        logger.warning(f"No video stream found in file: {new_file_path}")
                        # Still update the file path even if we can't get technical details
                        video.local_path = new_file_path
                        session.commit()
                        logger.info(f"Updated video {video.id} with file path (no technical details): {new_file_path}")
                        
                else:
                    logger.error(f"ffprobe failed for file {new_file_path}: {result.stderr}")
                    # Still update the file path
                    video.local_path = new_file_path
                    session.commit()
                    logger.info(f"Updated video {video.id} with file path (ffprobe failed): {new_file_path}")
                    
            except Exception as e:
                logger.error(f"Failed to extract metadata from file {new_file_path}: {e}")
                # Still update the file path if we found the file
                video.local_path = new_file_path
                session.commit()
                logger.info(f"Updated video {video.id} with file path (metadata extraction failed): {new_file_path}")
                
        else:
            logger.warning(f"No downloaded file found for video {video.id}")
            logger.warning(f"Searched for video {video.id} ({video.title}) by artist {video.artist_id}")
            
            # Log search details for debugging
            if video.artist_id:
                from src.database.models import Artist
                artist = session.query(Artist).filter(Artist.id == video.artist_id).first()
                if artist:
                    logger.warning(f"Artist: {artist.name}, Video title: '{video.title}'")
                    clean_title = _sanitize_filename(video.title or f"Video_{video.id}")
                    logger.warning(f"Clean title used in search: '{clean_title[:20]}'")
                    
                    # Show what files exist in the artist directory
                    from src.services.settings_service import settings
                    music_videos_path = settings.get("music_videos_path", "data/musicvideos")
                    artist_dir = os.path.join(music_videos_path, _sanitize_filename(artist.name))
                    if os.path.exists(artist_dir):
                        video_files = [f for f in os.listdir(artist_dir) if f.endswith(('.mp4', '.webm', '.mkv', '.avi'))]
                        logger.warning(f"Available video files in {artist_dir}: {video_files[:5]}...")  # Show first 5
            
    except Exception as e:
        logger.error(f"Failed to update video after download: {e}")


def _sanitize_filename(filename):
    """Sanitize filename for file system compatibility"""
    import re
    # Remove or replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    sanitized = re.sub(r'[^\w\s-]', '', sanitized)
    return sanitized.strip()