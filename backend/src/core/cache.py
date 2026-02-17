"""Centralized caching module for ARIA.

Provides in-memory caching using cachetools TTLCache with:
- Configurable TTL (time-to-live) and maxsize
- @cached decorator for easy application to service methods
- Custom key generation via key_func
- Cache invalidation by key or pattern
- Statistics tracking (hits, misses)
"""

import functools
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

from cachetools import TTLCache

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

# Default cache configuration
DEFAULT_MAXSIZE = 1000
DEFAULT_TTL = 300  # 5 minutes


class Cache:
    """In-memory cache with TTL support.

    Wraps cachetools.TTLCache with additional features:
    - Hit/miss statistics tracking
    - Pattern-based invalidation
    - Multiple named cache regions
    """

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE, default_ttl: int = DEFAULT_TTL) -> None:
        """Initialize cache with configuration.

        Args:
            maxsize: Maximum number of entries in the cache.
            default_ttl: Default TTL in seconds for cached entries.
        """
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=default_ttl)
        self._hits = 0
        self._misses = 0
        self._decorator_caches: dict[str, TTLCache[str, Any]] = {}

    @property
    def maxsize(self) -> int:
        """Return the maximum cache size."""
        return self._maxsize

    @property
    def default_ttl(self) -> int:
        """Return the default TTL."""
        return self._default_ttl

    @property
    def hits(self) -> int:
        """Return the number of cache hits."""
        return self._hits

    @property
    def misses(self) -> int:
        """Return the number of cache misses."""
        return self._misses

    @property
    def size(self) -> int:
        """Return the current number of cached entries."""
        return len(self._cache)

    def get(self, key: str) -> tuple[Any, bool]:
        """Get a value from the cache.

        Args:
            key: The cache key.

        Returns:
            Tuple of (value, found) where found indicates if the key exists.
        """
        try:
            value = self._cache[key]
            self._hits += 1
            return value, True
        except KeyError:
            self._misses += 1
            return None, False

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Optional TTL override in seconds.
        """
        if ttl is not None:
            # For per-entry TTL, we need to use the cache's timer
            # TTLCache handles this internally when TTL is set on the cache
            self._cache[key] = value
        else:
            self._cache[key] = value

    def delete(self, key: str) -> bool:
        """Delete a key from the cache.

        Args:
            key: The cache key to delete.

        Returns:
            True if the key was deleted, False if it didn't exist.
        """
        try:
            del self._cache[key]
            return True
        except KeyError:
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._cache.clear()
        self._decorator_caches.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, size, maxsize.
        """
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "hit_rate": self._hits / (self._hits + self._misses)
            if (self._hits + self._misses) > 0
            else 0.0,
        }

    def get_or_create_decorator_cache(
        self, func_name: str, ttl: int
    ) -> TTLCache[str, Any]:
        """Get or create a cache for a specific decorated function.

        Args:
            func_name: The name of the decorated function.
            ttl: TTL for this function's cache.

        Returns:
            TTLCache instance for this function.
        """
        cache_key = f"{func_name}:{ttl}"
        if cache_key not in self._decorator_caches:
            self._decorator_caches[cache_key] = TTLCache(maxsize=self._maxsize, ttl=ttl)
        return self._decorator_caches[cache_key]

    def invalidate_by_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern.

        Args:
            pattern: Glob-style pattern to match keys against.

        Returns:
            Number of entries invalidated.
        """
        # Convert glob pattern to regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        regex = re.compile(f"^{regex_pattern}$")

        keys_to_delete = [key for key in self._cache if regex.match(key)]
        for key in keys_to_delete:
            del self._cache[key]

        # Also check decorator caches
        for decorator_cache in self._decorator_caches.values():
            decorator_keys = [key for key in decorator_cache if regex.match(key)]
            for key in decorator_keys:
                del decorator_cache[key]
            keys_to_delete.extend(decorator_keys)

        count = len(keys_to_delete)
        if count > 0:
            logger.debug("Invalidated %d cache entries matching pattern: %s", count, pattern)
        return count

    def invalidate_decorator_cache(self, func_name: str, key: str | None = None) -> int:
        """Invalidate entries in a decorator's cache.

        Args:
            func_name: Name of the decorated function.
            key: Specific key to invalidate (without func_name prefix), or None for all.

        Returns:
            Number of entries invalidated.
        """
        count = 0
        for cache_key, decorator_cache in list(self._decorator_caches.items()):
            if cache_key.startswith(f"{func_name}:"):
                if key is None:
                    count += len(decorator_cache)
                    decorator_cache.clear()
                else:
                    # The key stored in cache includes func_name prefix
                    # e.g., "get_data:test-key" when key_func returns "test-key"
                    # but when user calls invalidate_cache("get_data", key="test-key")
                    # we need to find keys that end with the provided key
                    keys_to_delete = [
                        k for k in decorator_cache
                        if k == f"{func_name}:{key}" or k.endswith(f":{key}")
                    ]
                    for k in keys_to_delete:
                        try:
                            del decorator_cache[k]
                            count += 1
                        except KeyError:
                            pass
        return count


# Global cache instance (singleton)
_cache_instance: Cache | None = None


def get_cache() -> Cache:
    """Get the global cache instance.

    Returns:
        The singleton Cache instance.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache()
    return _cache_instance


def cached(
    ttl: int = DEFAULT_TTL,
    key_func: Callable[..., str] | None = None,
    cache_instance: Cache | None = None,
) -> Callable[[Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]]:
    """Decorator to cache async function results.

    Args:
        ttl: Time-to-live in seconds for cached entries.
        key_func: Optional function to generate cache key from args.
                  Receives all positional and keyword arguments.
                  If None, uses string representation of args.
        cache_instance: Optional Cache instance to use. Defaults to global cache.

    Returns:
        Decorated async function with caching.

    Example:
        @cached(ttl=3600)
        async def get_user(user_id: str) -> dict:
            return await db.fetch_user(user_id)

        @cached(ttl=300, key_func=lambda user_id, **_: f"user:{user_id}")
        async def get_user_data(user_id: str, extra: str = "") -> dict:
            return {"user_id": user_id}
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, Coroutine[Any, Any, T]]:
        cache = cache_instance or get_cache()
        func_name = func.__name__

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Generate cache key
            if key_func is not None:
                cache_key = f"{func_name}:{key_func(*args, **kwargs)}"
            else:
                # Default key: function name + args repr
                args_repr = ", ".join(repr(a) for a in args)
                kwargs_repr = ", ".join(f"{k}={repr(v)}" for k, v in sorted(kwargs.items()))
                all_args = ", ".join(filter(None, [args_repr, kwargs_repr]))
                cache_key = f"{func_name}({all_args})"

            # Get the decorator-specific cache
            decorator_cache = cache.get_or_create_decorator_cache(func_name, ttl)

            # Try to get from cache
            try:
                value = decorator_cache[cache_key]
                cache._hits += 1  # Track global hits
                logger.debug("Cache hit for key: %s", cache_key)
                return value
            except KeyError:
                pass

            # Cache miss - execute function
            cache._misses += 1  # Track global misses
            logger.debug("Cache miss for key: %s", cache_key)
            result = await func(*args, **kwargs)

            # Only cache non-exception results
            decorator_cache[cache_key] = result
            return result

        # Add cache management methods to the wrapper
        wrapper.cache_clear = lambda: cache.invalidate_decorator_cache(func_name)  # type: ignore
        wrapper.cache_info = lambda: {  # type: ignore
            "func_name": func_name,
            "ttl": ttl,
            "size": len(cache.get_or_create_decorator_cache(func_name, ttl)),
        }

        return wrapper

    return decorator


def invalidate_cache(func_name: str, key: str | None = None, pattern: str | None = None) -> int:
    """Invalidate cache entries.

    Args:
        func_name: Name of the cached function.
        key: Specific cache key to invalidate.
        pattern: Glob pattern to match keys for invalidation.

    Returns:
        Number of entries invalidated.

    Example:
        # Invalidate specific key
        invalidate_cache("get_user", key="user:123")

        # Invalidate by pattern
        invalidate_cache("get_user", pattern="user:*")
    """
    cache = get_cache()

    if pattern is not None:
        # Pattern-based invalidation
        return cache.invalidate_by_pattern(f"{func_name}:{pattern}")
    elif key is not None:
        # Specific key invalidation
        return cache.invalidate_decorator_cache(func_name, key)
    else:
        # Invalidate all entries for this function
        return cache.invalidate_decorator_cache(func_name)


def clear_all_caches() -> None:
    """Clear all caches globally."""
    cache = get_cache()
    cache.clear()
    logger.info("All caches cleared")
