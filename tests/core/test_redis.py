"""Tests for Redis utilities and token blacklist."""
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.core.redis import (
    RateLimiter,
    TokenBlacklist,
    _memory_store,
    cache_delete,
    cache_get,
    cache_set,
)


@pytest.fixture(autouse=True)
def clear_memory_store():
    """Clear the memory store before and after each test."""
    _memory_store.clear()
    yield
    _memory_store.clear()


@pytest.fixture
def mock_redis_unavailable():
    """Mock Redis as unavailable (use memory fallback)."""
    with patch("src.core.redis.get_redis", return_value=None):
        yield


class TestTokenBlacklistAddToBlacklist:
    """Tests for TokenBlacklist.add_to_blacklist."""

    @pytest.mark.asyncio
    async def test_add_to_blacklist_memory_fallback(self, mock_redis_unavailable):
        """Should add token to memory store when Redis unavailable."""
        token = "test_token_123"
        expires_in = 3600

        await TokenBlacklist.add_to_blacklist(token, expires_in)

        key = f"blacklist:{token}"
        assert key in _memory_store
        value, expiry = _memory_store[key]
        assert value == "1"
        assert expiry is not None

    @pytest.mark.asyncio
    async def test_add_to_blacklist_sets_expiry(self, mock_redis_unavailable):
        """Should set correct expiry time."""
        token = "expiry_test_token"
        expires_in = 100

        before = time.time()
        await TokenBlacklist.add_to_blacklist(token, expires_in)
        after = time.time()

        key = f"blacklist:{token}"
        _, expiry = _memory_store[key]

        assert before + expires_in <= expiry <= after + expires_in


class TestTokenBlacklistIsBlacklisted:
    """Tests for TokenBlacklist.is_blacklisted."""

    @pytest.mark.asyncio
    async def test_is_blacklisted_returns_true_for_blacklisted(
        self, mock_redis_unavailable
    ):
        """Should return True for blacklisted token."""
        token = "blacklisted_token"
        await TokenBlacklist.add_to_blacklist(token, 3600)

        result = await TokenBlacklist.is_blacklisted(token)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_blacklisted_returns_false_for_not_blacklisted(
        self, mock_redis_unavailable
    ):
        """Should return False for non-blacklisted token."""
        result = await TokenBlacklist.is_blacklisted("not_blacklisted")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_blacklisted_returns_false_for_expired(
        self, mock_redis_unavailable
    ):
        """Should return False for expired blacklist entry."""
        token = "expired_token"
        # Add with already expired time
        key = f"blacklist:{token}"
        _memory_store[key] = ("1", time.time() - 1)  # Expired 1 second ago

        result = await TokenBlacklist.is_blacklisted(token)

        assert result is False
        # Should have been cleaned up
        assert key not in _memory_store

    @pytest.mark.asyncio
    async def test_is_blacklisted_respects_expiry(self, mock_redis_unavailable):
        """Should respect expiry time correctly."""
        token = "expiring_token"
        # Add with future expiry
        await TokenBlacklist.add_to_blacklist(token, 3600)

        # Should be blacklisted now
        assert await TokenBlacklist.is_blacklisted(token) is True


class TestTokenBlacklistRefreshTokens:
    """Tests for refresh token management."""

    @pytest.mark.asyncio
    async def test_add_refresh_token(self, mock_redis_unavailable):
        """Should add refresh token to store."""
        user_id = str(uuid.uuid4())
        token = "refresh_token_abc123456789"
        expires_in = 86400

        await TokenBlacklist.add_refresh_token(user_id, token, expires_in)

        # Key uses first 16 chars of token
        key = f"refresh:{user_id}:{token[:16]}"
        assert key in _memory_store
        value, _ = _memory_store[key]
        assert value == token

    @pytest.mark.asyncio
    async def test_invalidate_all_user_tokens(self, mock_redis_unavailable):
        """Should invalidate all refresh tokens for a user."""
        user_id = str(uuid.uuid4())
        token1 = "token1_0123456789abcdef"
        token2 = "token2_0123456789abcdef"

        await TokenBlacklist.add_refresh_token(user_id, token1, 86400)
        await TokenBlacklist.add_refresh_token(user_id, token2, 86400)

        # Verify tokens exist
        key1 = f"refresh:{user_id}:{token1[:16]}"
        key2 = f"refresh:{user_id}:{token2[:16]}"
        assert key1 in _memory_store
        assert key2 in _memory_store

        # Invalidate all
        await TokenBlacklist.invalidate_all_user_tokens(user_id)

        # Verify tokens removed
        assert key1 not in _memory_store
        assert key2 not in _memory_store

    @pytest.mark.asyncio
    async def test_invalidate_only_specific_user_tokens(self, mock_redis_unavailable):
        """Should only invalidate tokens for the specified user."""
        user1 = str(uuid.uuid4())
        user2 = str(uuid.uuid4())
        token1 = "user1_token_abcdef"
        token2 = "user2_token_abcdef"

        await TokenBlacklist.add_refresh_token(user1, token1, 86400)
        await TokenBlacklist.add_refresh_token(user2, token2, 86400)

        # Invalidate only user1
        await TokenBlacklist.invalidate_all_user_tokens(user1)

        # user1's token should be gone
        key1 = f"refresh:{user1}:{token1[:16]}"
        assert key1 not in _memory_store

        # user2's token should remain
        key2 = f"refresh:{user2}:{token2[:16]}"
        assert key2 in _memory_store


class TestCacheOperations:
    """Tests for cache_get, cache_set, cache_delete."""

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, mock_redis_unavailable):
        """Should set and get cache values."""
        key = "test_cache_key"
        value = "test_value"

        await cache_set(key, value, expire_seconds=3600)
        result = await cache_get(key)

        assert result == value

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_for_missing(self, mock_redis_unavailable):
        """Should return None for missing key."""
        result = await cache_get("nonexistent_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_for_expired(self, mock_redis_unavailable):
        """Should return None for expired cache entry."""
        key = "expired_cache"
        _memory_store[key] = ("cached_value", time.time() - 1)  # Expired

        result = await cache_get(key)

        assert result is None
        assert key not in _memory_store  # Should be cleaned up

    @pytest.mark.asyncio
    async def test_cache_delete(self, mock_redis_unavailable):
        """Should delete cache entry."""
        key = "to_delete"
        await cache_set(key, "value", expire_seconds=3600)

        await cache_delete(key)

        result = await cache_get(key)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_delete_nonexistent(self, mock_redis_unavailable):
        """Should not raise error when deleting nonexistent key."""
        # Should not raise
        await cache_delete("does_not_exist")

    @pytest.mark.asyncio
    async def test_cache_set_default_expiry(self, mock_redis_unavailable):
        """Should use default expiry of 3600 seconds."""
        key = "default_expiry"
        before = time.time()

        await cache_set(key, "value")  # No explicit expire_seconds

        _, expiry = _memory_store[key]
        # Default is 3600 seconds
        assert 3590 <= expiry - before <= 3610


class TestRateLimiter:
    """Tests for RateLimiter class."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_first_request_allowed(
        self, mock_redis_unavailable
    ):
        """First request should always be allowed."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            allowed, count = await RateLimiter.check_rate_limit(
                identifier="user123",
                action="test_action",
                max_requests=10,
                window_seconds=3600,
            )

            assert allowed is True
            assert count == 1

    @pytest.mark.asyncio
    async def test_check_rate_limit_increments_counter(self, mock_redis_unavailable):
        """Should increment counter on each request."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            identifier = "user_increment"
            action = "increment_action"

            _, count1 = await RateLimiter.check_rate_limit(
                identifier, action, max_requests=10
            )
            _, count2 = await RateLimiter.check_rate_limit(
                identifier, action, max_requests=10
            )
            _, count3 = await RateLimiter.check_rate_limit(
                identifier, action, max_requests=10
            )

            assert count1 == 1
            assert count2 == 2
            assert count3 == 3

    @pytest.mark.asyncio
    async def test_check_rate_limit_blocks_when_exceeded(self, mock_redis_unavailable):
        """Should block requests when limit exceeded."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            identifier = "user_exceeded"
            action = "exceeded_action"
            max_requests = 3

            # Make 3 allowed requests
            for i in range(max_requests):
                allowed, _ = await RateLimiter.check_rate_limit(
                    identifier, action, max_requests=max_requests
                )
                assert allowed is True

            # 4th request should be blocked
            allowed, count = await RateLimiter.check_rate_limit(
                identifier, action, max_requests=max_requests
            )

            assert allowed is False
            assert count == 4

    @pytest.mark.asyncio
    async def test_check_rate_limit_disabled(self, mock_redis_unavailable):
        """Should always allow when rate limiting disabled."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", False):
            allowed, count = await RateLimiter.check_rate_limit(
                identifier="any_user",
                action="any_action",
                max_requests=1,
            )

            assert allowed is True
            assert count == 0  # Not tracked when disabled

    @pytest.mark.asyncio
    async def test_check_rate_limit_separate_identifiers(self, mock_redis_unavailable):
        """Different identifiers should have separate limits."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            action = "shared_action"

            # User1 makes 2 requests
            await RateLimiter.check_rate_limit("user1", action, max_requests=5)
            await RateLimiter.check_rate_limit("user1", action, max_requests=5)

            # User2 should start from 0
            _, count = await RateLimiter.check_rate_limit("user2", action, max_requests=5)

            assert count == 1

    @pytest.mark.asyncio
    async def test_check_rate_limit_separate_actions(self, mock_redis_unavailable):
        """Different actions should have separate limits."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            identifier = "same_user"

            # Action1 makes 2 requests
            await RateLimiter.check_rate_limit(identifier, "action1", max_requests=5)
            await RateLimiter.check_rate_limit(identifier, "action1", max_requests=5)

            # Action2 should start from 0
            _, count = await RateLimiter.check_rate_limit(
                identifier, "action2", max_requests=5
            )

            assert count == 1

    @pytest.mark.asyncio
    async def test_get_remaining_full_limit(self, mock_redis_unavailable):
        """Should return full limit when no requests made."""
        remaining = await RateLimiter.get_remaining(
            identifier="new_user",
            action="new_action",
            max_requests=10,
        )

        assert remaining == 10

    @pytest.mark.asyncio
    async def test_get_remaining_after_requests(self, mock_redis_unavailable):
        """Should return correct remaining after requests."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            identifier = "remaining_user"
            action = "remaining_action"
            max_requests = 10

            # Make 3 requests
            for _ in range(3):
                await RateLimiter.check_rate_limit(
                    identifier, action, max_requests=max_requests
                )

            remaining = await RateLimiter.get_remaining(
                identifier, action, max_requests=max_requests
            )

            assert remaining == 7

    @pytest.mark.asyncio
    async def test_get_remaining_zero_when_exceeded(self, mock_redis_unavailable):
        """Should return 0 when limit exceeded."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            identifier = "zero_remaining"
            action = "zero_action"
            max_requests = 2

            # Exceed limit
            for _ in range(5):
                await RateLimiter.check_rate_limit(
                    identifier, action, max_requests=max_requests
                )

            remaining = await RateLimiter.get_remaining(
                identifier, action, max_requests=max_requests
            )

            assert remaining == 0

    @pytest.mark.asyncio
    async def test_rate_limit_window_expiry(self, mock_redis_unavailable):
        """Should reset counter after window expires."""
        with patch("src.config.settings.settings.RATE_LIMIT_ENABLED", True):
            identifier = "window_user"
            action = "window_action"
            key = f"ratelimit:{action}:{identifier}"

            # Simulate an expired window
            _memory_store[key] = ("5", time.time() - 1)  # Expired

            # New request should start fresh
            allowed, count = await RateLimiter.check_rate_limit(
                identifier, action, max_requests=10, window_seconds=3600
            )

            assert allowed is True
            assert count == 1
