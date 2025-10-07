"""
Settings service for database-driven configuration
"""

from typing import Any, Dict, Optional

from src.database.connection import get_db
from src.database.models import Setting
from src.utils.logger import get_logger

logger = get_logger("mvidarr.settings")


class SettingsService:
    """Service for managing application settings in database"""

    _cache: Dict[str, str] = {}
    _cache_loaded = False

    @classmethod
    def load_cache(cls):
        """Load all settings into cache"""
        if cls._cache_loaded:
            return

        try:
            # Check if database manager is available
            from src.database.connection import db_manager

            if db_manager is None:
                raise RuntimeError("Database not initialized")

            with get_db() as session:
                settings = session.query(Setting).all()
                cls._cache = {setting.key: setting.value for setting in settings}
                cls._cache_loaded = True
                logger.debug(f"Loaded {len(cls._cache)} settings into cache")
        except Exception as e:
            logger.error(f"Failed to load settings cache: {e}")
            cls._cache = {}
            # Don't set _cache_loaded = True if database is not available
            # This allows retry when database becomes available

    @classmethod
    def get(cls, key: str, default: Any = None) -> str:
        """Get setting value by key"""
        try:
            cls.load_cache()
        except Exception as e:
            logger.error(f"Failed to load settings cache in get(): {e}")
            # Don't prevent future retries - database might become available later

        value = cls._cache.get(key)

        if value is None:
            if default is not None:
                return str(default)
            else:
                logger.warning(f"Setting '{key}' not found and no default provided")
                return ""

        return value

    @classmethod
    def get_setting(cls, category: str, key: str, default: Any = None) -> str:
        """Get setting value by category and key (for compatibility)"""
        full_key = f"{category}.{key}"
        return cls.get(full_key, default)

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Get setting as integer"""
        value = cls.get(key, str(default))
        try:
            return int(value)
        except ValueError:
            logger.warning(
                f"Setting '{key}' value '{value}' is not a valid integer, using default {default}"
            )
            return default

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Get setting as boolean"""
        value = cls.get(key, str(default).lower())
        return value.lower() in ("true", "1", "yes", "on")

    @classmethod
    def get_float(cls, key: str, default: float = 0.0) -> float:
        """Get setting as float"""
        value = cls.get(key, str(default))
        try:
            return float(value)
        except ValueError:
            logger.warning(
                f"Setting '{key}' value '{value}' is not a valid float, using default {default}"
            )
            return default

    @classmethod
    def get_json(cls, key: str, default: Dict = None) -> Dict:
        """Get setting as JSON object"""
        import json

        if default is None:
            default = {}

        value = cls.get(key, "{}")
        if not value:
            return default

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Setting '{key}' value is not valid JSON, using default")
            return default

    @classmethod
    def set_json(cls, key: str, value: Dict, description: str = "") -> bool:
        """Set setting as JSON object"""
        import json

        try:
            json_value = json.dumps(value)
            return cls.set(key, json_value, description)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize JSON for setting '{key}': {e}")
            return False

    @classmethod
    def set(cls, key: str, value: str, description: str = "") -> bool:
        """Set setting value"""
        try:
            with get_db() as session:
                setting = session.query(Setting).filter_by(key=key).first()

                if setting:
                    setting.value = value
                    if description:
                        setting.description = description
                else:
                    setting = Setting(key=key, value=value, description=description)
                    session.add(setting)

                session.commit()

                # Update cache
                cls._cache[key] = value

                logger.info(f"Setting '{key}' updated to '{value}'")
                return True

        except Exception as e:
            logger.error(f"Failed to set setting '{key}': {e}")
            return False

    @classmethod
    def set_multiple(cls, settings: Dict[str, str]) -> bool:
        """Set multiple settings at once"""
        try:
            with get_db() as session:
                for key, value in settings.items():
                    setting = session.query(Setting).filter_by(key=key).first()

                    if setting:
                        setting.value = value
                    else:
                        setting = Setting(key=key, value=value)
                        session.add(setting)

                    # Update cache
                    cls._cache[key] = value

                session.commit()

                logger.info(f"Updated {len(settings)} settings")
                return True

        except Exception as e:
            logger.error(f"Failed to set multiple settings: {e}")
            return False

    @classmethod
    def get_all(cls) -> Dict[str, Dict[str, str]]:
        """Get all settings with metadata"""
        try:
            with get_db() as session:
                settings = session.query(Setting).order_by(Setting.key).all()

                result = {}
                for setting in settings:
                    result[setting.key] = {
                        "value": setting.value,
                        "description": setting.description or "",
                        "updated_at": (
                            setting.updated_at.isoformat()
                            if setting.updated_at
                            else None
                        ),
                    }

                return result

        except Exception as e:
            logger.error(f"Failed to get all settings: {e}")
            return {}

    @classmethod
    def delete(cls, key: str) -> bool:
        """Delete a setting"""
        try:
            with get_db() as session:
                setting = session.query(Setting).filter_by(key=key).first()

                if setting:
                    session.delete(setting)
                    session.commit()

                    # Remove from cache
                    cls._cache.pop(key, None)

                    logger.info(f"Setting '{key}' deleted")
                    return True
                else:
                    logger.warning(f"Setting '{key}' not found for deletion")
                    return False

        except Exception as e:
            logger.error(f"Failed to delete setting '{key}': {e}")
            return False

    @classmethod
    def reload_cache(cls):
        """Force reload settings cache"""
        cls._cache_loaded = False
        cls._cache.clear()
        cls.load_cache()
        logger.info("Settings cache reloaded")


# Convenience instance
settings = SettingsService()
