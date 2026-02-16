"""
FastAPI Videos Streaming API - Video Streaming and Subtitle Operations
Extracted from videos.py for better code organization

Handles:
- Video streaming with HTTP range support
- Real-time FFmpeg transcoding for MKV files
- Subtitle discovery and serving
- File relocation detection
"""

import asyncio
import json
import mimetypes
import subprocess
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote, unquote

import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication
from src.config.config import Config
from src.database.connection import get_db_session
from src.database.models import Video
from src.utils.logger import get_logger

router = APIRouter(
    prefix="",
    tags=["videos-streaming"],
    responses={
        404: {"description": "Video or file not found"},
        500: {"description": "Internal server error"},
    },
)
logger = get_logger("mvidarr.api.fastapi.videos_streaming")


# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================


async def find_relocated_video(video: Video) -> Optional[Path]:
    """Find video file if it has been relocated"""
    if not getattr(video, "file_path", video.local_path):
        return None

    original_path = Path(getattr(video, "file_path", video.local_path))
    if original_path.exists():
        return original_path

    # Search for relocated file in configured music videos directory
    filename = original_path.name

    # Use configured music videos directory from settings
    search_dirs = [Config.MUSIC_VIDEOS_DIR]

    # Add fallback paths for legacy/relocated files
    if not Config.MUSIC_VIDEOS_DIR.exists():
        search_dirs.extend(
            [
                Path("/app/data/musicvideos"),
                Path("/app/data/music_videos"),
                Path("/data/musicvideos"),
                Path("/data/music_videos"),
                Path("data/musicvideos"),
                Path("data/music_videos"),
            ]
        )

    for search_dir in search_dirs:
        if search_dir.exists():
            for file_path in search_dir.rglob(filename):
                if file_path.is_file():
                    logger.info(f"Found relocated video: {file_path}")
                    return file_path

    return None


async def detect_codecs(video_path: Path) -> Dict[str, str]:
    """
    Detect video and audio codecs using ffprobe

    Returns dict with 'video_codec' and 'audio_codec' keys
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(video_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"ffprobe failed: {stderr.decode()}")
            return {"video_codec": "unknown", "audio_codec": "unknown"}

        data = json.loads(stdout.decode())
        streams = data.get("streams", [])

        video_codec = "unknown"
        audio_codec = "unknown"

        for stream in streams:
            codec_type = stream.get("codec_type")
            codec_name = stream.get("codec_name", "unknown")

            if codec_type == "video" and video_codec == "unknown":
                video_codec = codec_name
            elif codec_type == "audio" and audio_codec == "unknown":
                audio_codec = codec_name

        logger.info(
            f"Detected codecs for {video_path.name}: video={video_codec}, audio={audio_codec}"
        )
        return {"video_codec": video_codec, "audio_codec": audio_codec}

    except Exception as e:
        logger.error(f"Error detecting codecs: {e}")
        return {"video_codec": "unknown", "audio_codec": "unknown"}


def is_browser_compatible(video_codec: str, audio_codec: str) -> bool:
    """
    Check if codecs are browser-compatible

    Browser-compatible codecs:
    - Video: h264, vp8, vp9, av1
    - Audio: aac, mp3, opus, vorbis
    """
    compatible_video = ["h264", "vp8", "vp9", "av1"]
    compatible_audio = ["aac", "mp3", "opus", "vorbis"]

    return video_codec in compatible_video and audio_codec in compatible_audio


# ========================================================================================
# VIDEO STREAMING ENDPOINTS
# ========================================================================================


@router.get("/{video_id}/stream")
@router.head("/{video_id}/stream")
async def stream_video(
    request: Request,
    video_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Stream video with HTTP range support"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Find the video file
        video_path = None
        if video.local_path and Path(video.local_path).exists():
            video_path = Path(video.local_path)
        else:
            # Try to find relocated file
            video_path = await find_relocated_video(video)

        if not video_path or not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        # Get file size
        file_size = video_path.stat().st_size

        # Handle range requests for video streaming
        range_header = request.headers.get("Range")

        if range_header:
            # Parse range header
            range_match = range_header.replace("bytes=", "").split("-")
            range_start = int(range_match[0]) if range_match[0] else 0
            range_end = int(range_match[1]) if range_match[1] else file_size - 1

            # Ensure valid range
            range_start = max(0, min(range_start, file_size - 1))
            range_end = max(range_start, min(range_end, file_size - 1))
            content_length = range_end - range_start + 1

            # Create async streaming response for range
            async def generate_range():
                """Async generator for streaming video ranges"""
                try:
                    async with aiofiles.open(video_path, "rb") as f:
                        await f.seek(range_start)
                        remaining = content_length
                        chunk_size = 65536  # 64KB chunks for better performance

                        while remaining > 0:
                            # Read smaller chunk if remaining is less than chunk_size
                            read_size = min(chunk_size, remaining)
                            chunk = await f.read(read_size)

                            if not chunk:
                                # End of file reached unexpectedly
                                logger.warning(
                                    f"EOF reached early during range {range_start}-{range_end}, "
                                    f"sent {content_length - remaining}/{content_length} bytes"
                                )
                                break

                            remaining -= len(chunk)
                            yield chunk

                except Exception as e:
                    logger.error(
                        f"Error streaming range {range_start}-{range_end}: {e}"
                    )
                    raise

            # Get MIME type - handle common video formats explicitly
            # For MKV files, use MP4 MIME type to trick browsers into attempting playback
            # Most MKV files contain H.264/AAC which browsers can decode
            content_type, _ = mimetypes.guess_type(str(video_path))
            suffix = video_path.suffix.lower()

            if not content_type or suffix == ".mkv":
                # Explicit handling for common video formats
                if suffix == ".mkv":
                    # Serve MKV as MP4 MIME type - browsers can often decode the codecs
                    content_type = "video/mp4"
                elif suffix == ".webm":
                    content_type = "video/webm"
                elif suffix == ".avi":
                    content_type = "video/x-msvideo"
                elif suffix in [".mp4", ".m4v"]:
                    content_type = "video/mp4"
                elif suffix == ".mov":
                    content_type = "video/quicktime"
                else:
                    content_type = "video/mp4"  # Default fallback

            headers = {
                "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": content_type,
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff",
            }

            return StreamingResponse(generate_range(), status_code=206, headers=headers)
        else:
            # Return full file - handle common video formats explicitly
            # For MKV files, use MP4 MIME type to trick browsers into attempting playback
            content_type, _ = mimetypes.guess_type(str(video_path))
            suffix = video_path.suffix.lower()

            if not content_type or suffix == ".mkv":
                # Explicit handling for common video formats
                if suffix == ".mkv":
                    # Serve MKV as MP4 MIME type - browsers can often decode the codecs
                    content_type = "video/mp4"
                elif suffix == ".webm":
                    content_type = "video/webm"
                elif suffix == ".avi":
                    content_type = "video/x-msvideo"
                elif suffix in [".mp4", ".m4v"]:
                    content_type = "video/mp4"
                elif suffix == ".mov":
                    content_type = "video/quicktime"
                else:
                    content_type = "video/mp4"  # Default fallback

            response = FileResponse(
                video_path, media_type=content_type, filename=video_path.name
            )
            # Add Accept-Ranges header to indicate range request support
            response.headers["Accept-Ranges"] = "bytes"
            return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming video {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{video_id}/stream-transcode")
@router.head("/{video_id}/stream-transcode")
async def stream_video_transcode(
    request: Request,
    video_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Stream video with real-time FFmpeg transcoding for MKV files

    Automatically detects codecs and:
    - Remuxes (fast, copy codecs) if H.264/AAC compatible
    - Transcodes (slower) if incompatible codecs
    - Supports HTTP range requests for seeking
    """
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Find the video file
        video_path = None
        if video.local_path and Path(video.local_path).exists():
            video_path = Path(video.local_path)
        else:
            # Try to find relocated file
            video_path = await find_relocated_video(video)

        if not video_path or not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        # Detect codecs
        codecs = await detect_codecs(video_path)
        video_codec = codecs["video_codec"]
        audio_codec = codecs["audio_codec"]

        # Determine if we need to transcode or just remux
        needs_transcode = not is_browser_compatible(video_codec, audio_codec)

        logger.info(
            f"Transcoding video {video_id} ({video_path.name}): "
            f"video_codec={video_codec}, audio_codec={audio_codec}, "
            f"needs_transcode={needs_transcode}"
        )

        # Build FFmpeg command
        if needs_transcode:
            # Full transcode for incompatible codecs
            ffmpeg_cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-f",
                "mp4",
                "-movflags",
                "frag_keyframe+empty_moov+default_base_moof",
                "pipe:1",
            ]
        else:
            # Fast remux for compatible codecs (just change container)
            ffmpeg_cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-c",
                "copy",  # Copy both video and audio streams
                "-f",
                "mp4",
                "-movflags",
                "frag_keyframe+empty_moov+default_base_moof",
                "pipe:1",
            ]

        # Handle HEAD requests
        if request.method == "HEAD":
            headers = {
                "Content-Type": "video/mp4",
                "Accept-Ranges": "none",  # Seeking not supported during transcoding
                "X-Transcode-Mode": "remux" if not needs_transcode else "transcode",
            }
            return StreamingResponse(
                iter([]), status_code=200, headers=headers, media_type="video/mp4"
            )

        # Create async generator for streaming
        async def transcode_and_stream():
            """Generate transcoded video chunks"""
            process = None
            try:
                logger.info(f"Starting FFmpeg process: {' '.join(ffmpeg_cmd)}")

                process = await asyncio.create_subprocess_exec(
                    *ffmpeg_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                )

                # Stream chunks from FFmpeg stdout
                chunk_size = 8192
                while True:
                    chunk = await process.stdout.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

                # Wait for process completion
                await process.wait()

                if process.returncode != 0:
                    stderr_output = await process.stderr.read()
                    logger.error(
                        f"FFmpeg process failed with code {process.returncode}: {stderr_output.decode()}"
                    )

            except asyncio.CancelledError:
                # Client disconnected, terminate FFmpeg
                if process and process.returncode is None:
                    logger.info("Client disconnected, terminating FFmpeg process")
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                raise
            except Exception as e:
                logger.error(f"Error during transcoding: {e}")
                if process and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                raise

        # Return streaming response
        headers = {
            "Content-Type": "video/mp4",
            "Accept-Ranges": "none",  # Seeking not fully supported during transcoding
            "X-Transcode-Mode": "remux" if not needs_transcode else "transcode",
            "Cache-Control": "no-cache",
        }

        return StreamingResponse(
            transcode_and_stream(),
            status_code=200,
            headers=headers,
            media_type="video/mp4",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in transcode streaming for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# SUBTITLE OPERATIONS
# ========================================================================================


@router.get("/{video_id}/subtitles")
async def get_subtitles(
    video_id: int = FastAPIPath(..., description="Video ID"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get available subtitle tracks for a video"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video or not video.local_path:
            return {"subtitles": []}

        video_path = Path(video.local_path)
        if not video_path.exists():
            return {"subtitles": []}

        # Look for subtitle files in the same directory
        video_dir = video_path.parent
        video_name_stem = video_path.stem

        subtitle_extensions = [".srt", ".vtt", ".ass", ".ssa", ".sub"]
        subtitles = []

        # Look for all subtitle files in the directory and filter by base name
        for subtitle_file in video_dir.iterdir():
            if (
                subtitle_file.is_file()
                and subtitle_file.suffix.lower() in subtitle_extensions
            ):
                # Check if this subtitle file belongs to our video
                if subtitle_file.name.startswith(video_name_stem):
                    # Extract language from filename (e.g., video.en.srt -> en)
                    relative_name = subtitle_file.name
                    parts = relative_name.split(".")

                    language = "unknown"
                    if len(parts) >= 3:  # video.en.srt
                        language = parts[-2]
                    elif len(parts) == 2:  # video.srt (assume default language)
                        language = "default"

                    subtitles.append(
                        {
                            "language": language,
                            "filename": relative_name,
                            "url": f"/api/videos/{video_id}/subtitles/{quote(relative_name)}",
                            "format": subtitle_file.suffix[1:],  # Remove the dot
                        }
                    )

        return {"subtitles": subtitles}

    except Exception as e:
        logger.error(f"Failed to get subtitles for video {video_id}: {e}")
        return {"subtitles": []}


@router.get("/{video_id}/subtitles/{subtitle_filename}")
async def serve_subtitle(
    video_id: int = FastAPIPath(..., description="Video ID"),
    subtitle_filename: str = FastAPIPath(..., description="Subtitle filename"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Serve subtitle file for a video with positioning stripped for proper centering"""
    try:
        # URL decode the subtitle filename
        decoded_filename = unquote(subtitle_filename)

        video = session.query(Video).filter(Video.id == video_id).first()

        if not video or not video.local_path:
            raise HTTPException(status_code=404, detail="Video not found")

        video_path = Path(video.local_path)
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        video_dir = video_path.parent

        # Security check: ensure subtitle filename doesn't contain path traversal
        if ".." in decoded_filename or "/" in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid subtitle filename")

        # Find subtitle file in the same directory as the video
        subtitle_path = video_dir / decoded_filename

        if not subtitle_path.exists():
            raise HTTPException(status_code=404, detail="Subtitle file not found")

        # Security check: ensure subtitle file is in the same directory as video
        if not str(subtitle_path).startswith(str(video_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        # Determine MIME type
        subtitle_ext = subtitle_path.suffix.lower()
        if subtitle_ext == ".srt":
            mimetype = "text/srt"
        elif subtitle_ext == ".vtt":
            mimetype = "text/vtt"
        elif subtitle_ext in [".ass", ".ssa"]:
            mimetype = "text/x-ssa"
        else:
            mimetype = "text/plain"

        # For VTT files, strip positioning to allow proper centering via CSS
        if subtitle_ext == ".vtt":
            import re

            async with aiofiles.open(subtitle_path, "r", encoding="utf-8") as f:
                content = await f.read()

            # COMPREHENSIVE WEBVTT SANITIZATION
            # Fixes Chrome STATUS_BREAKPOINT crash when seeking video timeline
            # Issue: YouTube auto-generated subtitles have nested timestamps, empty cues,
            # and micro-duration cues that crash Chrome's renderer during seek operations

            # Step 1: Remove ALL WebVTT cue settings (align, position, line, size, vertical)
            # These settings can cause Chrome renderer crashes during video seeking
            content = re.sub(
                r"(\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+.*$",
                r"\1",
                content,
                flags=re.MULTILINE,
            )

            # Step 2: Remove nested word-level timestamps (YouTube's format)
            # Example: "forget <00:00:07.933><c>to </c><00:00:08.376><c>thumbs </c>"
            # becomes: "forget to thumbs"
            content = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", "", content)
            content = re.sub(r"</?c>", "", content)

            # Step 3: Parse cues and filter out problematic ones
            lines = content.split("\n")
            sanitized_lines = []
            i = 0

            while i < len(lines):
                line = lines[i]

                # Keep header and non-cue lines
                if (
                    line.startswith("WEBVTT")
                    or line.startswith("Kind:")
                    or line.startswith("Language:")
                    or not line.strip()
                    or "-->" not in line
                ):
                    sanitized_lines.append(line)
                    i += 1
                    continue

                # This is a timestamp line
                timestamp_line = line
                cue_text_lines = []

                # Collect cue text (lines after timestamp until blank line)
                i += 1
                while i < len(lines) and lines[i].strip() and "-->" not in lines[i]:
                    cue_text_lines.append(lines[i])
                    i += 1

                # Check if cue has actual text content
                cue_text = "\n".join(cue_text_lines).strip()

                # Skip empty cues (no text or only whitespace)
                if not cue_text:
                    continue

                # Parse timestamp to check duration
                timestamp_match = re.match(
                    r"(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})",
                    timestamp_line,
                )

                if timestamp_match:
                    start_time = timestamp_match.group(1)
                    end_time = timestamp_match.group(2)

                    # Convert to milliseconds
                    def time_to_ms(time_str):
                        h, m, s = time_str.split(":")
                        s, ms = s.split(".")
                        return (
                            int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)
                        )

                    duration = time_to_ms(end_time) - time_to_ms(start_time)

                    # Skip micro-duration cues (< 100ms) that cause seek crashes
                    if duration < 100:
                        logger.debug(
                            f"Skipping micro-duration cue ({duration}ms): {cue_text[:30]}"
                        )
                        continue

                # Keep valid cue
                sanitized_lines.append(timestamp_line)
                sanitized_lines.extend(cue_text_lines)

            content = "\n".join(sanitized_lines)

            # Return modified content as streaming response
            from fastapi.responses import Response

            response = Response(content=content, media_type=mimetype)

            # Cache-Control for subtitle files (CORS handled by global middleware)
            response.headers["Cache-Control"] = "public, max-age=3600"

            logger.debug(
                f"Served VTT subtitle with positioning stripped: {decoded_filename}"
            )
            return response

        # For non-VTT files, serve as-is
        response = FileResponse(
            path=subtitle_path, media_type=mimetype, filename=decoded_filename
        )

        # CORS handled by global middleware
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to serve subtitle {subtitle_filename} for video {video_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Internal server error")
