"""
Async File System Operations for FastAPI Migration
Non-blocking file and directory operations using asyncio
"""

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import aiofiles

from src.utils.async_subprocess import run_system_command
from src.utils.logger import get_logger

logger = get_logger("mvidarr.utils.async_file_operations")


class AsyncFileManager:
    """Manages async file operations for better performance"""

    def __init__(self):
        self._performance_stats = {}

    async def read_file(
        self, file_path: Union[str, Path], encoding: str = "utf-8"
    ) -> str:
        """Read file content asynchronously"""
        start_time = time.time()
        file_path = Path(file_path)

        try:
            async with aiofiles.open(file_path, mode="r", encoding=encoding) as f:
                content = await f.read()

            execution_time = time.time() - start_time
            self._record_performance(f"read_file:{file_path.name}", execution_time)

            logger.debug(f"Read file {file_path} in {execution_time:.3f}s")
            return content

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Error reading file {file_path} after {execution_time:.3f}s: {e}"
            )
            self._record_performance(
                f"read_file:{file_path.name}", execution_time, error=True
            )
            raise

    async def write_file(
        self, file_path: Union[str, Path], content: str, encoding: str = "utf-8"
    ) -> bool:
        """Write file content asynchronously"""
        start_time = time.time()
        file_path = Path(file_path)

        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, mode="w", encoding=encoding) as f:
                await f.write(content)

            execution_time = time.time() - start_time
            self._record_performance(f"write_file:{file_path.name}", execution_time)

            logger.debug(f"Wrote file {file_path} in {execution_time:.3f}s")
            return True

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Error writing file {file_path} after {execution_time:.3f}s: {e}"
            )
            self._record_performance(
                f"write_file:{file_path.name}", execution_time, error=True
            )
            return False

    async def read_json(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Read JSON file asynchronously"""
        content = await self.read_file(file_path)
        return json.loads(content)

    async def write_json(
        self, file_path: Union[str, Path], data: Dict[str, Any], indent: int = 2
    ) -> bool:
        """Write JSON file asynchronously"""
        content = json.dumps(data, indent=indent, ensure_ascii=False)
        return await self.write_file(file_path, content)

    async def file_exists(self, file_path: Union[str, Path]) -> bool:
        """Check if file exists asynchronously"""
        try:
            return await asyncio.to_thread(Path(file_path).exists)
        except Exception:
            return False

    async def get_file_size(self, file_path: Union[str, Path]) -> Optional[int]:
        """Get file size asynchronously"""
        try:
            stat_result = await asyncio.to_thread(os.stat, file_path)
            return stat_result.st_size
        except Exception as e:
            logger.debug(f"Could not get size for {file_path}: {e}")
            return None

    async def get_directory_size(self, directory: Union[str, Path]) -> int:
        """Get total directory size using async du command"""
        try:
            result = await run_system_command(
                ["du", "-sb", str(directory)],
                timeout=10.0,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # du output format: "size_in_bytes    directory_path"
                size_str = result.stdout.strip().split()[0]
                return int(size_str)
            else:
                logger.warning(f"du command failed for {directory}: {result.stderr}")
                return 0

        except Exception as e:
            logger.error(f"Error getting directory size for {directory}: {e}")
            return 0

    async def create_directory(self, directory: Union[str, Path]) -> bool:
        """Create directory asynchronously"""
        try:
            await asyncio.to_thread(Path(directory).mkdir, parents=True, exist_ok=True)
            logger.debug(f"Created directory: {directory}")
            return True
        except Exception as e:
            logger.error(f"Error creating directory {directory}: {e}")
            return False

    async def delete_file(self, file_path: Union[str, Path]) -> bool:
        """Delete file asynchronously"""
        try:
            await asyncio.to_thread(Path(file_path).unlink, missing_ok=True)
            logger.debug(f"Deleted file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return False

    async def delete_directory(self, directory: Union[str, Path]) -> bool:
        """Delete directory and contents asynchronously"""
        try:
            await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)
            logger.debug(f"Deleted directory: {directory}")
            return True
        except Exception as e:
            logger.error(f"Error deleting directory {directory}: {e}")
            return False

    async def copy_file(
        self, source: Union[str, Path], destination: Union[str, Path]
    ) -> bool:
        """Copy file asynchronously"""
        try:
            # Ensure destination directory exists
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            await asyncio.to_thread(shutil.copy2, source, destination)
            logger.debug(f"Copied {source} to {destination}")
            return True
        except Exception as e:
            logger.error(f"Error copying {source} to {destination}: {e}")
            return False

    async def move_file(
        self, source: Union[str, Path], destination: Union[str, Path]
    ) -> bool:
        """Move file asynchronously"""
        try:
            # Ensure destination directory exists
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            await asyncio.to_thread(shutil.move, source, destination)
            logger.debug(f"Moved {source} to {destination}")
            return True
        except Exception as e:
            logger.error(f"Error moving {source} to {destination}: {e}")
            return False

    async def list_directory(
        self, directory: Union[str, Path], pattern: Optional[str] = None
    ) -> List[Path]:
        """List directory contents asynchronously with optional glob pattern"""
        try:
            directory = Path(directory)

            if pattern:
                # Use glob pattern
                entries = await asyncio.to_thread(list, directory.glob(pattern))
            else:
                # List all entries
                entries = await asyncio.to_thread(list, directory.iterdir())

            return sorted(entries)

        except Exception as e:
            logger.error(f"Error listing directory {directory}: {e}")
            return []

    async def get_disk_usage(self, path: Union[str, Path]) -> Dict[str, int]:
        """Get disk usage information asynchronously using df command"""
        try:
            result = await run_system_command(
                ["df", "-B1", str(path)],  # -B1 for bytes
                timeout=5.0,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    # Parse df output: Filesystem 1B-blocks Used Available Use% Mounted
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        return {
                            "total": int(parts[1]),
                            "used": int(parts[2]),
                            "available": int(parts[3]),
                            "filesystem": parts[0],
                            "mount_point": parts[-1] if len(parts) >= 6 else str(path),
                        }

            logger.warning(f"Could not parse df output for {path}")
            return {}

        except Exception as e:
            logger.error(f"Error getting disk usage for {path}: {e}")
            return {}

    async def watch_file_changes(
        self, file_path: Union[str, Path], check_interval: float = 1.0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Watch file for changes asynchronously"""
        file_path = Path(file_path)
        last_mtime = None
        last_size = None

        while True:
            try:
                if await self.file_exists(file_path):
                    stat_result = await asyncio.to_thread(os.stat, file_path)
                    current_mtime = stat_result.st_mtime
                    current_size = stat_result.st_size

                    if last_mtime is not None and (
                        current_mtime != last_mtime or current_size != last_size
                    ):
                        yield {
                            "event": "modified",
                            "file_path": file_path,
                            "mtime": current_mtime,
                            "size": current_size,
                            "timestamp": time.time(),
                        }

                    last_mtime = current_mtime
                    last_size = current_size

                elif last_mtime is not None:
                    # File was deleted
                    yield {
                        "event": "deleted",
                        "file_path": file_path,
                        "timestamp": time.time(),
                    }
                    last_mtime = None
                    last_size = None

                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(f"Error watching file {file_path}: {e}")
                await asyncio.sleep(check_interval)

    def _record_performance(
        self, operation: str, execution_time: float, error: bool = False
    ):
        """Record performance statistics"""
        if operation not in self._performance_stats:
            self._performance_stats[operation] = []

        self._performance_stats[operation].append(
            {"execution_time": execution_time, "error": error, "timestamp": time.time()}
        )

        # Keep only last 100 entries per operation
        if len(self._performance_stats[operation]) > 100:
            self._performance_stats[operation] = self._performance_stats[operation][
                -100:
            ]

    def get_performance_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get file operations performance statistics"""
        stats = {}

        for operation, entries in self._performance_stats.items():
            if not entries:
                continue

            successful_entries = [e for e in entries if not e.get("error", False)]

            if successful_entries:
                execution_times = [e["execution_time"] for e in successful_entries]
                stats[operation] = {
                    "call_count": len(entries),
                    "success_count": len(successful_entries),
                    "avg_execution_time": sum(execution_times) / len(execution_times),
                    "min_execution_time": min(execution_times),
                    "max_execution_time": max(execution_times),
                    "success_rate": len(successful_entries) / len(entries),
                }

        return stats


# Global file manager instance
async_file_manager = AsyncFileManager()


# Convenience functions
async def read_file_async(file_path: Union[str, Path], encoding: str = "utf-8") -> str:
    """Read file asynchronously"""
    return await async_file_manager.read_file(file_path, encoding)


async def write_file_async(
    file_path: Union[str, Path], content: str, encoding: str = "utf-8"
) -> bool:
    """Write file asynchronously"""
    return await async_file_manager.write_file(file_path, content, encoding)


async def read_json_async(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Read JSON file asynchronously"""
    return await async_file_manager.read_json(file_path)


async def write_json_async(
    file_path: Union[str, Path], data: Dict[str, Any], indent: int = 2
) -> bool:
    """Write JSON file asynchronously"""
    return await async_file_manager.write_json(file_path, data, indent)
