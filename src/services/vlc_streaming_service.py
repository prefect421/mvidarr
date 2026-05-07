"""
VLC Streaming Service for MVidarr

Handles video streaming using VLC's built-in HTTP streaming capabilities
to provide browser-compatible video playback for various formats including MKV.
"""

import os
import signal
import subprocess
import time

import requests
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.vlc_streaming")


class VLCStreamingService:
    def __init__(self):
        self.active_streams = {}  # video_id -> {'process': process, 'port': port}
        self.base_port = 8090  # Starting port for VLC streams
        self.stream_timeout = 3600  # 1 hour timeout for streams

    def start_stream(self, video_id, video_path):
        """
        Start a VLC stream for the given video file

        Args:
            video_id (int): Database ID of the video
            video_path (str): Path to the video file

        Returns:
            dict: Stream info with URL and status
        """
        try:
            # Check if stream is already active
            if video_id in self.active_streams:
                stream_info = self.active_streams[video_id]
                if self._is_stream_active(stream_info["port"]):
                    logger.info(
                        f"Stream already active for video {video_id} on port {stream_info['port']}"
                    )
                    return {
                        "success": True,
                        "stream_url": f'http://localhost:{stream_info["port"]}/stream.mp4',
                        "port": stream_info["port"],
                        "status": "active",
                    }
                else:
                    # Clean up dead stream
                    self._cleanup_stream(video_id)

            # Find available port
            port = self._find_available_port()
            if not port:
                logger.error("No available ports for VLC streaming")
                return {"success": False, "error": "No available ports"}

            # Check if video file exists
            if not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                return {"success": False, "error": "Video file not found"}

            # Start VLC stream
            process = self._start_vlc_process(video_path, port)
            if not process:
                return {"success": False, "error": "Failed to start VLC process"}

            # Store stream info
            self.active_streams[video_id] = {
                "process": process,
                "port": port,
                "video_path": video_path,
                "start_time": time.time(),
            }

            # Wait for VLC HTTP interface to be ready
            if self._wait_for_stream_ready(port):
                logger.info(
                    f"VLC HTTP interface started for video {video_id} on port {port}"
                )
                return {
                    "success": True,
                    "stream_url": f"http://localhost:{port}/",
                    "vlc_interface": f"http://localhost:{port}/",
                    "port": port,
                    "status": "ready",
                }
            else:
                self._cleanup_stream(video_id)
                return {"success": False, "error": "Stream failed to start properly"}

        except Exception as e:
            logger.error(f"Error starting VLC stream for video {video_id}: {e}")
            return {"success": False, "error": str(e)}

    def _start_vlc_process(self, video_path, port):
        """Start VLC process with HTTP streaming"""
        try:
            # Simple VLC HTTP server approach
            cmd = [
                "sudo",
                "-u",
                "mike",
                "cvlc",
                video_path,
                "--intf",
                "http",
                "--http-host",
                "0.0.0.0",
                "--http-port",
                str(port),
                "--http-password",
                "",
                "--loop",
            ]

            logger.info(f"Starting VLC with command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,  # Create new process group
            )

            return process

        except Exception as e:
            logger.error(f"Failed to start VLC process: {e}")
            return None

    def _find_available_port(self):
        """Find an available port for streaming"""
        for port in range(self.base_port, self.base_port + 100):
            if not self._is_port_in_use(port):
                return port
        return None

    def _is_port_in_use(self, port):
        """Check if a port is already in use"""
        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                result = s.connect_ex(("localhost", port))
                return result == 0
        except:
            return False

    def _wait_for_stream_ready(self, port, timeout=30):
        """Wait for the VLC HTTP interface to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://localhost:{port}/", timeout=2)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(1)
        return False

    def _is_stream_active(self, port):
        """Check if a stream is still active"""
        try:
            response = requests.get(
                f"http://localhost:{port}/stream.mp4", timeout=2, stream=True
            )
            return response.status_code == 200
        except:
            return False

    def stop_stream(self, video_id):
        """Stop a VLC stream"""
        try:
            if video_id in self.active_streams:
                self._cleanup_stream(video_id)
                logger.info(f"Stopped VLC stream for video {video_id}")
                return {"success": True}
            else:
                return {"success": False, "error": "Stream not found"}
        except Exception as e:
            logger.error(f"Error stopping VLC stream for video {video_id}: {e}")
            return {"success": False, "error": str(e)}

    def _cleanup_stream(self, video_id):
        """Clean up a stream and its process"""
        if video_id in self.active_streams:
            stream_info = self.active_streams[video_id]
            process = stream_info["process"]

            try:
                # Kill the process group
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=5)
            except:
                try:
                    # Force kill if needed
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except:
                    pass

            del self.active_streams[video_id]

    def cleanup_old_streams(self):
        """Clean up streams that have been running too long"""
        current_time = time.time()
        to_cleanup = []

        for video_id, stream_info in self.active_streams.items():
            if current_time - stream_info["start_time"] > self.stream_timeout:
                to_cleanup.append(video_id)
            elif not self._is_stream_active(stream_info["port"]):
                to_cleanup.append(video_id)

        for video_id in to_cleanup:
            logger.info(f"Cleaning up expired/dead stream for video {video_id}")
            self._cleanup_stream(video_id)

    def get_stream_info(self, video_id):
        """Get information about an active stream"""
        if video_id in self.active_streams:
            stream_info = self.active_streams[video_id]
            return {
                "success": True,
                "stream_url": f'http://localhost:{stream_info["port"]}/stream.mp4',
                "port": stream_info["port"],
                "active": self._is_stream_active(stream_info["port"]),
                "uptime": time.time() - stream_info["start_time"],
            }
        else:
            return {"success": False, "error": "Stream not found"}

    def list_active_streams(self):
        """List all active streams"""
        streams = []
        for video_id, stream_info in self.active_streams.items():
            streams.append(
                {
                    "video_id": video_id,
                    "port": stream_info["port"],
                    "video_path": stream_info["video_path"],
                    "uptime": time.time() - stream_info["start_time"],
                    "active": self._is_stream_active(stream_info["port"]),
                }
            )
        return streams


# Global instance
vlc_streaming_service = VLCStreamingService()
