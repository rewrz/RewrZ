from cachetools import cached, TTLCache
from typing import Any, Callable, Dict
import functools

# A simple in-memory cache with a time-to-live of 5 minutes (300 seconds)
# This cache will store global settings to reduce database queries.
cache = TTLCache(maxsize=100, ttl=300)


def cache_get(key: str) -> Any:
    """
    从缓存中获取值
    
    Args:
        key: 缓存键
        
    Returns:
        缓存值，如果不存在则返回None
    """
    return cache.get(key)


def cache_set(key: str, value: Any, ttl: int = None) -> None:
    """
    设置缓存值
    
    Args:
        key: 缓存键
        value: 缓存值
        ttl: 过期时间（秒），如果为None则使用默认值
    """
    if ttl is not None:
        # 创建临时缓存以支持自定义TTL
        temp_cache = TTLCache(maxsize=1, ttl=ttl)
        temp_cache[key] = value
        cache[key] = temp_cache[key]
    else:
        cache[key] = value


def clear_cache(key: str = None):
    """Clears a specific item from the cache or the entire cache if no key is provided."""
    if key:
        if key in cache:
            del cache[key]
        print(f"INFO: Cache for key '{key}' cleared.")
    else:
        cache.clear()
        print("INFO: All cache cleared.")


def cache_key_for_setting(key: str) -> str:
    """Generates a cache key for a specific setting."""
    return f"setting_{key}"


def cache_settings(func: Callable) -> Callable:
    """Decorator to cache the result of a function that fetches settings."""
    @functools.wraps(func)
    def wrapper(db, key):
        cache_key = cache_key_for_setting(key)
        if cache_key in cache:
            return cache[cache_key]
        result = func(db, key)
        cache[cache_key] = result
        return result
    return wrapper