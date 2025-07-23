import json
import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_filepath(self, key: str, subdirectory: str | None = None) -> Path:
        """Generates the full path for a cache file based on its key and optional subdirectory."""
        base_path = self.cache_dir
        if subdirectory:
            base_path = self.cache_dir / subdirectory
        return base_path / f"{key}.json"

    def load_cache(self, key: str, max_age_seconds: int | None = None, subdirectory: str | None = None) -> dict | None:
        """
        Loads cached data for a given key from an optional subdirectory.
        If max_age_seconds is provided, returns None if the cache is older than max_age_seconds.
        """
        filepath = self._get_cache_filepath(key, subdirectory)
        if not filepath.exists():
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            timestamp = cache_data.get("timestamp")
            data = cache_data.get("data")

            if timestamp is None or data is None:
                logger.warning(f"Cache file {filepath} is malformed. Deleting and returning None.")
                filepath.unlink(missing_ok=True)
                return None

            if max_age_seconds is not None and (time.time() - timestamp > max_age_seconds):
                logger.info(f"Cache for {key} in {subdirectory or 'root'} is expired. Deleting and returning None.")
                filepath.unlink(missing_ok=True)
                return None

            logger.debug(f"Successfully loaded cache for {key} from {subdirectory or 'root'}.")
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading cache file {filepath}: {e}. Deleting and returning None.")
            filepath.unlink(missing_ok=True)
            return None

    def save_cache(self, key: str, data: dict, subdirectory: str | None = None):
        """Saves data to the cache for a given key in an optional subdirectory."""
        filepath = self._get_cache_filepath(key, subdirectory)
        try:
            # Ensure the subdirectory exists before writing
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            cache_data = {
                "timestamp": time.time(),
                "data": data
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Successfully saved cache for {key} in {subdirectory or 'root'}.")
        except IOError as e:
            logger.error(f"Error saving cache file {filepath}: {e}")

    def clear_cache(self, key: str | None = None, key_prefix: str | None = None, subdirectory: str | None = None):
        """
        Clears caches.
        - If only subdirectory is given, removes the entire subdirectory.
        - If key or key_prefix is given, operates within the specified subdirectory (or root if None).
        - If nothing is given, clears the entire root cache directory.
        """
        base_path = self.cache_dir / subdirectory if subdirectory else self.cache_dir

        if not base_path.exists():
            logger.info(f"Cache directory {base_path} does not exist. Nothing to clear.")
            return

        # Scenario 1: Clear a whole subdirectory (and not a specific key in it)
        if subdirectory and not key and not key_prefix:
            try:
                shutil.rmtree(base_path)
                logger.info(f"Cleared entire cache subdirectory: {subdirectory}")
            except OSError as e:
                logger.error(f"Error removing directory {base_path}: {e}")
            return

        # Scenario 2: Clear specific keys or prefixes within a directory (or root)
        if key:
            filepath = self._get_cache_filepath(key, subdirectory)
            if filepath.exists():
                filepath.unlink()
                logger.info(f"Cleared cache for {key} in {subdirectory or 'root'}.")
            else:
                logger.info(f"No cache found for {key} in {subdirectory or 'root'} to clear.")
        elif key_prefix:
            for f in base_path.glob(f"{key_prefix}*.json"):
                f.unlink()
            logger.info(f"Cleared caches with prefix '{key_prefix}' in {subdirectory or 'root'}.")
        elif not subdirectory: # Clear all caches in the root directory
             for f in base_path.glob("*.json"):
                f.unlink()
             logger.info("Cleared all caches in root directory.")


    def get_cache_timestamp(self, key: str, subdirectory: str | None = None) -> float | None:
        """Returns the timestamp of a cached entry from a subdirectory, or None if not found."""
        filepath = self._get_cache_filepath(key, subdirectory)
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                return cache_data.get("timestamp")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading timestamp from cache file {filepath}: {e}")
            return None

    def clear_all_cache(self):
        """Clears all cache files and subdirectories."""
        try:
            for item in self.cache_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            logger.info("Cleared all caches and subdirectories.")
        except Exception as e:
            logger.error(f"Error clearing all cache: {e}")
            raise

    def get(self, key: str, max_age_seconds: int = None, subdirectory: str | None = None) -> dict | None:
        """获取缓存数据（别名方法）"""
        return self.load_cache(key, max_age_seconds, subdirectory)
    
    def set(self, key: str, data: dict, ttl: int = None, subdirectory: str | None = None):
        """设置缓存数据（别名方法）"""
        self.save_cache(key, data, subdirectory)
