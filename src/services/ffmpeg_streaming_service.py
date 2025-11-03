"""
FFmpeg Streaming Service for MVidarr

A simpler, more reliable approach to stream MKV files using FFmpeg
"""

import os
import subprocess

from flask import Response

from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_streaming")


class FFmpegStreamingService:
    def __init__(self):
        self.active_streams = {}

    def stream_video(self, video_path):
        """
        Stream video file using FFmpeg with on-demand transcoding
        Returns a Flask Response object for direct streaming
        """
        try:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")

            # FFmpeg command to transcode and stream
            cmd = [
                "ffmpeg",
                "-i",
                video_path,
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-tune",
                "zerolatency",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-f",
                "mp4",
                "-movflags",
                "frag_keyframe+empty_moov",
                "-",
            ]

            logger.info(f"Starting FFmpeg streaming: {' '.join(cmd)}")

            # Create generator function for streaming
            def generate():
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
                )

                try:
                    while True:
                        data = process.stdout.read(8192)
                        if not data:
                            break
                        yield data
                finally:
                    process.terminate()
                    process.wait()

            return Response(
                generate(),
                mimetype="video/mp4",
                headers={
                    "Content-Type": "video/mp4",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-cache",
                },
            )

        except Exception as e:
            logger.error(f"Error streaming video {video_path}: {e}")
            raise


# Global instance
ffmpeg_streaming_service = FFmpegStreamingService()
