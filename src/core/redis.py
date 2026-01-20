"""Redis client and utilities for caching and token management."""
import logging
from typing import Any

from src.config.settings import settings

logger = logging.getLogger(__name__)

# In-memory fallback for development when Redis is not available
_memory_store: dict[str, tuple[str, float | None]] = {}
_use_memory_fallback = False


async def get_redis():
    """Get Redis client instance or memory fallback."""
    global _use_memory_fallback

    if _use_memory_fallback:
        return None

    try:
        import redis.asyncio as redis

        pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        client = redis.Redis(connection_pool=pool)
        await client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis not available, using in-memory fallback: {e}")
        _use_memory_fallback = True
        return None


class TokenBlacklist:
    """Token blacklist manager using Redis or in-memory fallback."""

    BLACKLIST_PREFIX = "blacklist:"

    @classmethod
    async def add_to_blacklist(
        cls,
        token: str,
        expires_in_seconds: int,
    ) -> None:
        """Add a token to the blacklist."""
        client = await get_redis()
        key = f"{cls.BLACKLIST_PREFIX}{token}"

        if client:
            await client.setex(key, expires_in_seconds, "1")
        else:
            import time
            _memory_store[key] = ("1", time.time() + expires_in_seconds)

    @classmethod
    async def is_blacklisted(cls, token: str) -> bool:
        """Check if a token is blacklisted."""
        client = await get_redis()
        key = f"{cls.BLACKLIST_PREFIX}{token}"

        if client:
            result = await client.get(key)
            return result is not None
        else:
            import time
            if key in _memory_store:
                value, expiry = _memory_store[key]
                if expiry is None or time.time() < expiry:
                    return True
                else:
                    del _memory_store[key]
            return False

    @classmethod
    async def add_refresh_token(
        cls,
        user_id: str,
        token: str,
        expires_in_seconds: int,
    ) -> None:
        """Store a refresh token for a user."""
        client = await get_redis()
        key = f"refresh:{user_id}:{token[:16]}"

        if client:
            await client.setex(key, expires_in_seconds, token)
        else:
            import time
            _memory_store[key] = (token, time.time() + expires_in_seconds)

    @classmethod
    async def invalidate_all_user_tokens(cls, user_id: str) -> None:
        """Invalidate all refresh tokens for a user."""
        client = await get_redis()
        pattern = f"refresh:{user_id}:"

        if client:
            keys = []
            async for key in client.scan_iter(match=f"{pattern}*"):
                keys.append(key)
            if keys:
                await client.delete(*keys)
        else:
            keys_to_delete = [k for k in _memory_store.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del _memory_store[key]


async def cache_get(key: str) -> Any | None:
    """Get a value from cache."""
    client = await get_redis()
    if client:
        return await client.get(key)
    else:
        import time
        if key in _memory_store:
            value, expiry = _memory_store[key]
            if expiry is None or time.time() < expiry:
                return value
            else:
                del _memory_store[key]
        return None


async def cache_set(key: str, value: Any, expire_seconds: int = 3600) -> None:
    """Set a value in cache with optional expiration."""
    client = await get_redis()
    if client:
        await client.setex(key, expire_seconds, value)
    else:
        import time
        _memory_store[key] = (value, time.time() + expire_seconds)


async def cache_delete(key: str) -> None:
    """Delete a value from cache."""
    client = await get_redis()
    if client:
        await client.delete(key)
    else:
        _memory_store.pop(key, None)


class RateLimiter:
    """Rate limiter using Redis or in-memory fallback.

    Uses a sliding window algorithm to limit requests per time window.
    """

    RATE_LIMIT_PREFIX = "ratelimit:"

    @classmethod
    async def check_rate_limit(
        cls,
        identifier: str,
        action: str,
        max_requests: int,
        window_seconds: int = 3600,
    ) -> tuple[bool, int]:
        """Check if an action is within rate limits.

        Args:
            identifier: Unique identifier (e.g., user_id)
            action: Action being rate limited (e.g., "assignment")
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds (default: 1 hour)

        Returns:
            Tuple of (is_allowed, current_count)
        """
        key = f"{cls.RATE_LIMIT_PREFIX}{action}:{identifier}"
        client = await get_redis()

        if client:
            # Use Redis INCR with EXPIRE for atomic increment
            current = await client.incr(key)
            if current == 1:
                # First request in window, set expiration
                await client.expire(key, window_seconds)

            return current <= max_requests, current
        else:
            import time
            now = time.time()

            if key in _memory_store:
                data, expiry = _memory_store[key]
                if expiry and now < expiry:
                    # Increment counter
                    current = int(data) + 1
                    _memory_store[key] = (str(current), expiry)
                    return current <= max_requests, current
                else:
                    # Window expired, reset
                    del _memory_store[key]

            # First request in window
            _memory_store[key] = ("1", now + window_seconds)
            return True, 1

    @classmethod
    async def get_remaining(
        cls,
        identifier: str,
        action: str,
        max_requests: int,
    ) -> int:
        """Get remaining requests in the current window.

        Args:
            identifier: Unique identifier (e.g., user_id)
            action: Action being rate limited
            max_requests: Maximum requests allowed

        Returns:
            Number of remaining requests
        """
        key = f"{cls.RATE_LIMIT_PREFIX}{action}:{identifier}"
        client = await get_redis()

        if client:
            current = await client.get(key)
            if current is None:
                return max_requests
            return max(0, max_requests - int(current))
        else:
            import time
            now = time.time()

            if key in _memory_store:
                data, expiry = _memory_store[key]
                if expiry and now < expiry:
                    return max(0, max_requests - int(data))

            return max_requests
