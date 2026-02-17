"""Tests for the cache module.

Tests cover:
- TTLCache initialization and configuration
- @cached decorator functionality
- Cache key generation via key_func
- Cache hit/miss behavior
- TTL expiration behavior
- Cache invalidation
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest

from src.core.cache import Cache, cached, get_cache, invalidate_cache, clear_all_caches


class TestCacheInitialization:
    """Tests for cache initialization and configuration."""

    def test_cache_creates_with_default_settings(self) -> None:
        """Cache should initialize with default maxsize and TTL."""
        cache = Cache()
        assert cache.maxsize > 0
        assert cache.default_ttl > 0

    def test_cache_creates_with_custom_settings(self) -> None:
        """Cache should accept custom maxsize and TTL."""
        cache = Cache(maxsize=100, default_ttl=600)
        assert cache.maxsize == 100
        assert cache.default_ttl == 600

    def test_get_cache_returns_singleton(self) -> None:
        """get_cache should return the same cache instance."""
        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2


class TestCachedDecorator:
    """Tests for the @cached decorator."""

    @pytest.mark.asyncio
    async def test_cached_decorator_returns_cached_result(self) -> None:
        """Cached function should return the same result without re-execution."""
        call_count = 0

        @cached(ttl=60)
        async def expensive_operation(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should execute
        result1 = await expensive_operation(5)
        assert result1 == 10
        assert call_count == 1

        # Second call with same args - should use cache
        result2 = await expensive_operation(5)
        assert result2 == 10
        assert call_count == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_cached_decorator_respects_different_args(self) -> None:
        """Cache should distinguish between different arguments."""
        call_count = 0

        @cached(ttl=60)
        async def operation(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await operation(5)
        result2 = await operation(10)
        result3 = await operation(5)  # Should hit cache

        assert result1 == 10
        assert result2 == 20
        assert result3 == 10
        assert call_count == 2  # Only 5 and 10 executed, 5 again is cached

    @pytest.mark.asyncio
    async def test_cached_decorator_with_custom_key_func(self) -> None:
        """Cache should use custom key function for cache key generation."""
        call_count = 0

        def make_key(*args: Any, **kwargs: Any) -> str:
            # Only use first positional arg (user_id) for the cache key
            user_id = args[0] if args else kwargs.get("user_id", "")
            return f"user:{user_id}"

        @cached(ttl=60, key_func=make_key)
        async def get_user_data(user_id: str, _extra: str = "") -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id}

        # First call
        result1 = await get_user_data("user123", "extra1")
        assert result1 == {"user_id": "user123"}
        assert call_count == 1

        # Second call with same user_id but different extra - should hit cache
        result2 = await get_user_data("user123", "extra2")
        assert result2 == {"user_id": "user123"}
        assert call_count == 1  # Not incremented due to cache

        # Different user_id - should miss cache
        result3 = await get_user_data("user456", "extra1")
        assert result3 == {"user_id": "user456"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cached_decorator_with_key_func_receiving_all_args(self) -> None:
        """key_func should receive all function args and kwargs."""
        received_args: list[tuple] = []

        def capture_key(*args: Any, **kwargs: Any) -> str:
            received_args.append((args, kwargs))
            return str((args, frozenset(kwargs.items())))

        @cached(ttl=60, key_func=capture_key)
        async def multi_arg_func(a: int, b: str, c: float = 1.0) -> str:
            return f"{a}-{b}-{c}"

        await multi_arg_func(1, "test", c=2.5)

        assert len(received_args) == 1
        # args should contain positional arguments
        assert received_args[0][0] == (1, "test")
        # kwargs should contain keyword arguments
        assert received_args[0][1] == {"c": 2.5}


class TestCacheTTLExpiration:
    """Tests for TTL (time-to-live) expiration."""

    @pytest.mark.asyncio
    async def test_cached_entry_expires_after_ttl(self) -> None:
        """Cached entries should expire and re-execute after TTL."""
        call_count = 0

        @cached(ttl=1)  # 1 second TTL
        async def time_sensitive() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        # First call
        result1 = await time_sensitive()
        assert result1 == 1
        assert call_count == 1

        # Immediate second call - should be cached
        result2 = await time_sensitive()
        assert result2 == 1
        assert call_count == 1

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Should re-execute after TTL
        result3 = await time_sensitive()
        assert result3 == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_different_ttls_for_different_decorators(self) -> None:
        """Different cached functions can have different TTLs."""
        short_count = 0
        long_count = 0

        @cached(ttl=1)
        async def short_lived() -> int:
            nonlocal short_count
            short_count += 1
            return short_count

        @cached(ttl=10)
        async def long_lived() -> int:
            nonlocal long_count
            long_count += 1
            return long_count

        await short_lived()
        await long_lived()

        await asyncio.sleep(1.1)

        # Short TTL should expire
        result1 = await short_lived()
        assert result1 == 2

        # Long TTL should still be cached
        result2 = await long_lived()
        assert result2 == 1


class TestCacheInvalidation:
    """Tests for cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_by_key(self) -> None:
        """Cache should support invalidation by specific key."""
        call_count = 0

        # Use a custom key function for predictable keys
        def make_key(*args: Any, **kwargs: Any) -> str:
            return args[0] if args else ""

        @cached(ttl=3600, key_func=make_key)
        async def get_data(key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"value-{key}"

        # Cache a value
        await get_data("test-key")
        assert call_count == 1

        # Hit cache
        await get_data("test-key")
        assert call_count == 1

        # Invalidate using the raw key (func_name:key format is handled internally)
        invalidate_cache("get_data", key="test-key")

        # Should re-execute
        await get_data("test-key")
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_cache_by_pattern(self) -> None:
        """Cache should support pattern-based invalidation."""
        call_count = 0

        @cached(ttl=3600, key_func=lambda user_id, **_: f"user:{user_id}")
        async def get_user(user_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"user-{user_id}"

        # Cache multiple values
        await get_user("user1")
        await get_user("user2")
        assert call_count == 2

        # Invalidate all user caches
        invalidate_cache("get_user", pattern="user:*")

        # Both should re-execute
        await get_user("user1")
        await get_user("user2")
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_clear_all_caches(self) -> None:
        """clear_all_caches should remove all cached entries."""
        count1 = 0
        count2 = 0

        @cached(ttl=3600)
        async def func1() -> int:
            nonlocal count1
            count1 += 1
            return count1

        @cached(ttl=3600)
        async def func2() -> int:
            nonlocal count2
            count2 += 1
            return count2

        # Cache both
        await func1()
        await func2()
        assert count1 == 1 and count2 == 1

        # Clear all
        clear_all_caches()

        # Both should re-execute
        await func1()
        await func2()
        assert count1 == 2 and count2 == 2


class TestCacheStatistics:
    """Tests for cache statistics tracking."""

    @pytest.mark.asyncio
    async def test_cache_tracks_hits_and_misses(self) -> None:
        """Cache should track hit and miss counts."""
        cache = get_cache()
        initial_hits = cache.hits
        initial_misses = cache.misses

        @cached(ttl=60)
        async def tracked_func(x: int) -> int:
            return x * 2

        # First call - miss
        await tracked_func(1)
        assert cache.misses == initial_misses + 1

        # Second call - hit
        await tracked_func(1)
        assert cache.hits == initial_hits + 1

        # Different arg - miss
        await tracked_func(2)
        assert cache.misses == initial_misses + 2

    @pytest.mark.asyncio
    async def test_cache_provides_stats_dict(self) -> None:
        """Cache should provide stats as a dictionary."""
        cache = get_cache()
        stats = cache.get_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "size" in stats
        assert "maxsize" in stats
        assert isinstance(stats["hits"], int)
        assert isinstance(stats["misses"], int)


class TestCacheEviction:
    """Tests for cache eviction when maxsize is reached."""

    @pytest.mark.asyncio
    async def test_cache_evicts_oldest_when_full(self) -> None:
        """Cache should evict oldest entries when maxsize is reached."""
        call_count = 0

        # Create a small cache
        cache = Cache(maxsize=3, default_ttl=60)

        @cached(ttl=60, cache_instance=cache)
        async def limited_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # Fill cache
        await limited_func(1)
        await limited_func(2)
        await limited_func(3)
        assert call_count == 3

        # All three should be cached
        await limited_func(1)
        await limited_func(2)
        await limited_func(3)
        assert call_count == 3  # No new calls, all cached

        # Add one more - should evict oldest (1)
        await limited_func(4)
        assert call_count == 4  # New call for 4

        # Verify eviction by accessing all - 2 and 3 should still be cached, 1 should re-execute
        await limited_func(2)
        await limited_func(3)
        assert call_count == 4  # Still 4, both cached

        await limited_func(1)  # 1 was evicted, should re-execute
        assert call_count == 5  # New call for 1


class TestCacheWithExceptions:
    """Tests for cache behavior with exceptions."""

    @pytest.mark.asyncio
    async def test_exception_not_cached(self) -> None:
        """Exceptions should not be cached."""
        call_count = 0

        @cached(ttl=60)
        async def failing_func(should_fail: bool) -> str:
            nonlocal call_count
            call_count += 1
            if should_fail:
                raise ValueError("Intentional failure")
            return "success"

        # First call - fails
        with pytest.raises(ValueError):
            await failing_func(True)
        assert call_count == 1

        # Second call - should retry (exception not cached)
        with pytest.raises(ValueError):
            await failing_func(True)
        assert call_count == 2

        # Success case should cache
        await failing_func(False)
        assert call_count == 3

        await failing_func(False)  # Cached
        assert call_count == 3
