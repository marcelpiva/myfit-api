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
