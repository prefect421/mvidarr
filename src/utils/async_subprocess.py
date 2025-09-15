"""
Async Subprocess Utilities for FastAPI Migration
Provides non-blocking subprocess execution patterns for system commands
"""

import asyncio
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.utils.logger import get_logger

logger = get_logger("mvidarr.utils.async_subprocess")


class AsyncSubprocessManager:
    """
    Manages async subprocess operations with ThreadPoolExecutor and async subprocess patterns
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._thread_pool = None
        self._performance_stats = {}

    @property
    def thread_pool(self) -> ThreadPoolExecutor:
        """Lazy initialization of thread pool executor"""
        if self._thread_pool is None:
            self._thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._thread_pool

    async def run_command_async(
        self,
        cmd: Union[List[str], str],
        timeout: Optional[float] = None,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Run subprocess command asynchronously with proper result format

        Returns:
            Dict with 'success', 'stdout', 'stderr', 'returncode' keys
        """
        try:
            result = await self.run_in_thread_pool(
                cmd, timeout, capture_output, text, check, cwd, env, **kwargs
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "returncode": result.returncode,
            }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}

    async def run_in_thread_pool(
        self,
        cmd: Union[List[str], str],
        timeout: Optional[float] = None,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """
        Run subprocess command in thread pool for non-blocking execution

        Args:
            cmd: Command to execute (list or string)
            timeout: Command timeout in seconds
            capture_output: Capture stdout/stderr
            text: Return text instead of bytes
            check: Raise exception on non-zero exit code
            cwd: Working directory
            env: Environment variables
            **kwargs: Additional subprocess.run arguments

        Returns:
            CompletedProcess object with result
        """
        start_time = time.time()
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

        try:
            logger.debug(f"Running subprocess in thread pool: {cmd_str}")

            # Prepare subprocess.run arguments
            run_kwargs = {
                "timeout": timeout,
                "capture_output": capture_output,
                "text": text,
                "check": check,
                "cwd": cwd,
                "env": env,
                **kwargs,
            }

            # Run in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.thread_pool, lambda: subprocess.run(cmd, **run_kwargs)
            )

            execution_time = time.time() - start_time
            self._record_performance(cmd_str, execution_time, "thread_pool")

            logger.debug(f"Subprocess completed in {execution_time:.2f}s: {cmd_str}")
            return result

        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            logger.error(f"Subprocess timeout after {execution_time:.2f}s: {cmd_str}")
            self._record_performance(cmd_str, execution_time, "timeout")
            raise
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Subprocess error after {execution_time:.2f}s: {cmd_str} - {e}"
            )
            self._record_performance(cmd_str, execution_time, "error")
            raise

    async def run_async_subprocess(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[bytes, bytes, int]:
        """
        Run subprocess using asyncio.create_subprocess_exec for true async execution

        Args:
            cmd: Command as list of strings
            timeout: Command timeout in seconds
            cwd: Working directory
            env: Environment variables

        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        start_time = time.time()
        cmd_str = " ".join(cmd)

        try:
            logger.debug(f"Running async subprocess: {cmd_str}")

            # Create async subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            # Wait for completion with timeout
            if timeout:
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    process.terminate()
                    await process.wait()
                    raise subprocess.TimeoutExpired(cmd, timeout)
            else:
                stdout, stderr = await process.communicate()

            execution_time = time.time() - start_time
            self._record_performance(cmd_str, execution_time, "async_subprocess")

            logger.debug(
                f"Async subprocess completed in {execution_time:.2f}s: {cmd_str}"
            )
            return stdout, stderr, process.returncode

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Async subprocess error after {execution_time:.2f}s: {cmd_str} - {e}"
            )
            self._record_performance(cmd_str, execution_time, "error")
            raise

    async def stream_subprocess(
        self,
        cmd: List[str],
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None,
        buffer_size: int = 8192,
    ):
        """
        Stream subprocess output for long-running processes like FFmpeg

        Args:
            cmd: Command as list of strings
            cwd: Working directory
            env: Environment variables
            buffer_size: Buffer size for reading output

        Yields:
            Output chunks as they become available
        """
        cmd_str = " ".join(cmd)
        start_time = time.time()

        try:
            logger.debug(f"Starting streaming subprocess: {cmd_str}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            # Stream output chunks
            while True:
                chunk = await process.stdout.read(buffer_size)
                if not chunk:
                    break
                yield chunk

            # Wait for process completion
            await process.wait()

            execution_time = time.time() - start_time
            self._record_performance(cmd_str, execution_time, "streaming")

            logger.debug(
                f"Streaming subprocess completed in {execution_time:.2f}s: {cmd_str}"
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Streaming subprocess error after {execution_time:.2f}s: {cmd_str} - {e}"
            )
            self._record_performance(cmd_str, execution_time, "error")

            # Ensure process cleanup
            if "process" in locals():
                try:
                    process.terminate()
                    await process.wait()
                except:
                    pass
            raise

    def _record_performance(self, cmd: str, execution_time: float, result_type: str):
        """Record performance statistics for monitoring"""
        if cmd not in self._performance_stats:
            self._performance_stats[cmd] = []

        self._performance_stats[cmd].append(
            {
                "execution_time": execution_time,
                "result_type": result_type,
                "timestamp": time.time(),
            }
        )

        # Keep only last 100 entries per command
        if len(self._performance_stats[cmd]) > 100:
            self._performance_stats[cmd] = self._performance_stats[cmd][-100:]

    def get_performance_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get performance statistics for monitoring"""
        stats = {}

        for cmd, entries in self._performance_stats.items():
            if not entries:
                continue

            execution_times = [
                e["execution_time"] for e in entries if e["result_type"] != "error"
            ]

            if execution_times:
                stats[cmd] = {
                    "call_count": len(entries),
                    "avg_execution_time": sum(execution_times) / len(execution_times),
                    "min_execution_time": min(execution_times),
                    "max_execution_time": max(execution_times),
                    "success_rate": len(execution_times) / len(entries),
                    "recent_calls": entries[-10:],  # Last 10 calls
                }

        return stats

    async def cleanup(self):
        """Cleanup thread pool resources"""
        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)
            self._thread_pool = None
            logger.info("AsyncSubprocessManager cleanup completed")


# Global instance for application use
async_subprocess_manager = AsyncSubprocessManager()


# Convenience functions for common operations
async def run_system_command(
    cmd: Union[List[str], str], timeout: Optional[float] = None, **kwargs
) -> subprocess.CompletedProcess:
    """
    Run system command in thread pool (non-blocking)

    Example:
        result = await run_system_command(['systemctl', 'is-active', 'mvidarr'])
        if result.returncode == 0:
            print("Service is active")
    """
    return await async_subprocess_manager.run_in_thread_pool(
        cmd, timeout=timeout, **kwargs
    )


async def run_media_command(
    cmd: List[str], timeout: Optional[float] = None, **kwargs
) -> Tuple[bytes, bytes, int]:
    """
    Run media processing command with async subprocess (better for FFmpeg/FFprobe)

    Example:
        stdout, stderr, returncode = await run_media_command([
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', video_path
        ])
    """
    return await async_subprocess_manager.run_async_subprocess(
        cmd, timeout=timeout, **kwargs
    )


async def stream_media_process(cmd: List[str], **kwargs):
    """
    Stream media processing output (for real-time FFmpeg streaming)

    Example:
        async for chunk in stream_media_process(['ffmpeg', '-i', input_file, ...]):
            # Process chunk of output
            yield chunk
    """
    async for chunk in async_subprocess_manager.stream_subprocess(cmd, **kwargs):
        yield chunk


# System-specific helper functions
async def check_service_status(service_name: str) -> bool:
    """Check if systemd service is active (non-blocking)"""
    try:
        result = await run_system_command(
            ["systemctl", "is-active", service_name], timeout=5.0
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking service status for {service_name}: {e}")
        return False


async def get_git_version() -> Optional[str]:
    """Get git commit hash (non-blocking)"""
    try:
        result = await run_system_command(
            ["git", "rev-parse", "--short", "HEAD"],
            timeout=3.0,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        logger.error(f"Error getting git version: {e}")
        return None


async def get_git_branch() -> Optional[str]:
    """Get git branch name (non-blocking)"""
    try:
        result = await run_system_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            timeout=3.0,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        logger.error(f"Error getting git branch: {e}")
        return None


async def check_port_availability(port: int) -> bool:
    """Check if port is available using netstat (non-blocking)"""
    try:
        result = await run_system_command(
            ["netstat", "-tlnp"], timeout=3.0, capture_output=True, text=True
        )
        if result.returncode == 0:
            return f":{port} " not in result.stdout
        return False
    except Exception as e:
        logger.error(f"Error checking port {port}: {e}")
        return False
