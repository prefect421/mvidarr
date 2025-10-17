"""
Thumbnail Generator - Cache Module
Cache management system for generated thumbnails with JSON index
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Optional

from src.services.thumbnail_models import ThumbnailConfig
from src.utils.logger import get_logger

logger = get_logger("mvidarr.thumbnail_cache")


class ThumbnailCache:
    """Cache system for generated thumbnails"""

    def __init__(self, cache_dir: Path):
        """Initialize thumbnail cache"""
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_index_file = cache_dir / "thumbnail_cache.json"
        self.cache_index = self._load_cache_index()

    def _load_cache_index(self) -> Dict:
        """Load cache index from disk"""
        try:
            if self.cache_index_file.exists():
                with open(self.cache_index_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Could not load thumbnail cache index: {e}")
        return {}

    def _save_cache_index(self):
        """Save cache index to disk"""
        try:
            with open(self.cache_index_file, "w") as f:
                json.dump(self.cache_index, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Could not save thumbnail cache index: {e}")

    def _get_cache_key(self, source_path: Path, config: ThumbnailConfig) -> str:
        """Generate cache key for source file and config"""
        # Include file modification time and size for cache invalidation
        try:
            stat = source_path.stat()
            key_data = f"{source_path}:{stat.st_mtime}:{stat.st_size}:{config}"
            return hashlib.md5(key_data.encode()).hexdigest()
        except OSError:
            # File doesn't exist, use path + config only
            key_data = f"{source_path}:{config}"
            return hashlib.md5(key_data.encode()).hexdigest()

    def get_cached_thumbnail(
        self, source_path: Path, config: ThumbnailConfig
    ) -> Optional[Path]:
        """Get cached thumbnail if available and valid"""
        cache_key = self._get_cache_key(source_path, config)

        if cache_key in self.cache_index:
            cached_path = Path(self.cache_index[cache_key]["path"])
            if cached_path.exists():
                logger.debug(f"📦 Using cached thumbnail: {cached_path}")
                return cached_path
            else:
                # Remove invalid cache entry
                del self.cache_index[cache_key]
                self._save_cache_index()

        return None

    def cache_thumbnail(
        self, source_path: Path, thumbnail_path: Path, config: ThumbnailConfig
    ):
        """Add thumbnail to cache"""
        cache_key = self._get_cache_key(source_path, config)

        self.cache_index[cache_key] = {
            "path": str(thumbnail_path),
            "source": str(source_path),
            "config": str(config),
            "created": time.time(),
            "size": thumbnail_path.stat().st_size if thumbnail_path.exists() else 0,
        }

        self._save_cache_index()

    def clear_cache(self) -> int:
        """Clear all cached thumbnails"""
        cleared = 0
        for entry in self.cache_index.values():
            cached_path = Path(entry["path"])
            if cached_path.exists():
                try:
                    cached_path.unlink()
                    cleared += 1
                except OSError as e:
                    logger.warning(
                        f"⚠️ Could not delete cached thumbnail {cached_path}: {e}"
                    )

        self.cache_index.clear()
        self._save_cache_index()

        logger.info(f"🗑️ Cleared {cleared} cached thumbnails")
        return cleared
