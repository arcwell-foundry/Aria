"""Tests for rate limiter middleware (US-930)."""

import asyncio
import time
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from src.core.exceptions import RateLimitError
from src.core.rate_limiter import (
    RateLimitConfig,
    RateLimitTracker,
    get_rate_limit_config,
    rate_limit,
)


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_rate_limit_config_creation(self) -> None:
        """Test creating a RateLimitConfig."""
        config = RateLimitConfig(requests=100, window_seconds=3600)
        assert config.requests == 100
        assert config.window_seconds == 3600

    def test_rate_limit_config_defaults(self) -> None:
        """Test RateLimitConfig with default values."""
        config = RateLimitConfig()
        assert config.requests == 100
        assert config.window_seconds == 60


class TestRateLimitTracker:
    """Tests for RateLimitTracker class."""

    def test_tracker_initialization(self) -> None:
        """Test tracker initializes with empty state."""
        tracker = RateLimitTracker()
        assert len(tracker._requests) == 0

    def test_check_rate_limit_under_limit(self) -> None:
        """Test check_rate_limit returns True when under limit."""
        tracker = RateLimitTracker()
        config = RateLimitConfig(requests=5, window_seconds=60)

        # Make 5 requests, all should be allowed
        for i in range(5):
            result = tracker.check_rate_limit("user_123", config)
            assert result is True, f"Request {i+1} should be allowed"

    def test_check_rate_limit_exceeds_limit(self) -> None:
        """Test check_rate_limit returns False when limit exceeded."""
        tracker = RateLimitTracker()
        config = RateLimitConfig(requests=3, window_seconds=60)

        # First 3 requests should be allowed
        for _ in range(3):
            assert tracker.check_rate_limit("user_456", config) is True

        # 4th request should be denied
        result = tracker.check_rate_limit("user_456", config)
        assert result is False

    def test_check_rate_limit_different_users(self) -> None:
        """Test that different users have independent rate limits."""
        tracker = RateLimitTracker()
        config = RateLimitConfig(requests=2, window_seconds=60)

        # User 1 makes 2 requests
        assert tracker.check_rate_limit("user_1", config) is True
        assert tracker.check_rate_limit("user_1", config) is True
        assert tracker.check_rate_limit("user_1", config) is False

        # User 2 should still have their full quota
        assert tracker.check_rate_limit("user_2", config) is True
        assert tracker.check_rate_limit("user_2", config) is True
        assert tracker.check_rate_limit("user_2", config) is False

    def test_get_retry_after(self) -> None:
        """Test get_retry_after returns correct seconds."""
        tracker = RateLimitTracker()
        config = RateLimitConfig(requests=2, window_seconds=60)

        # Make requests to use up the limit
        tracker.check_rate_limit("user_789", config)
        tracker.check_rate_limit("user_789", config)

        # Get retry_after for next request
        retry_after = tracker.get_retry_after("user_789", config)
        assert 0 <= retry_after <= 60

    def test_reset_for_user(self) -> None:
        """Test resetting rate limit for a specific user."""
        tracker = RateLimitTracker()
        config = RateLimitConfig(requests=2, window_seconds=60)

        # Use up the limit
        assert tracker.check_rate_limit("user_reset", config) is True
        assert tracker.check_rate_limit("user_reset", config) is True
        assert tracker.check_rate_limit("user_reset", config) is False

        # Reset for this user
        tracker.reset_for_user("user_reset")

        # Should be able to make requests again
        assert tracker.check_rate_limit("user_reset", config) is True

    def test_reset_all(self) -> None:
        """Test resetting all rate limits."""
        tracker = RateLimitTracker()
        config = RateLimitConfig(requests=1, window_seconds=60)

        # Multiple users hit their limits
        assert tracker.check_rate_limit("user_a", config) is True
        assert tracker.check_rate_limit("user_a", config) is False
        assert tracker.check_rate_limit("user_b", config) is True
        assert tracker.check_rate_limit("user_b", config) is False

        # Reset all
        tracker.reset_all()

        # All users should be able to make requests again
        assert tracker.check_rate_limit("user_a", config) is True
        assert tracker.check_rate_limit("user_b", config) is True

    def test_sliding_window_expiration(self) -> None:
        """Test that old requests expire from the sliding window."""
        tracker = RateLimitTracker()
        config = RateLimitConfig(requests=3, window_seconds=1)  # 1 second window

        # Make 3 requests
        for _ in range(3):
            assert tracker.check_rate_limit("sliding_user", config) is True

        # 4th request should be denied
        assert tracker.check_rate_limit("sliding_user", config) is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be able to make requests again
        assert tracker.check_rate_limit("sliding_user", config) is True


class TestGetRateLimitConfig:
    """Tests for get_rate_limit_config function."""

    @patch("src.core.rate_limiter.get_settings")
    def test_default_config(self, mock_get_settings: MagicMock) -> None:
        """Test default rate limit configuration."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = False
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = get_rate_limit_config("/api/test")
        assert config.requests == 100
        assert config.window_seconds == 60

    @patch("src.core.rate_limiter.get_settings")
    def test_chat_endpoint_config(self, mock_get_settings: MagicMock) -> None:
        """Test chat endpoints have stricter rate limits."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = False
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = get_rate_limit_config("/api/chat")
        # Chat endpoints get 10% of base limit (100 // 10 = 10)
        assert config.requests == 10
        assert config.window_seconds == 60

    @patch("src.core.rate_limiter.get_settings")
    def test_generation_endpoint_config(self, mock_get_settings: MagicMock) -> None:
        """Test generation endpoints have very strict rate limits."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = False
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = get_rate_limit_config("/api/generate")
        assert config.requests == 20
        assert config.window_seconds == 60

    @patch("src.core.rate_limiter.get_settings")
    def test_auth_endpoint_config(self, mock_get_settings: MagicMock) -> None:
        """Test auth endpoints have strict rate limits."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = False
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = get_rate_limit_config("/api/auth/login")
        assert config.requests == 10
        assert config.window_seconds == 60

    @patch("src.core.rate_limiter.get_settings")
    def test_webhook_endpoint_no_limit(self, mock_get_settings: MagicMock) -> None:
        """Test webhook endpoints have no rate limiting."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = False
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = get_rate_limit_config("/api/webhooks/stripe")
        assert config.requests == 10_000
        assert config.window_seconds == 60


class TestRateLimitDecorator:
    """Tests for rate_limit decorator."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.app = FastAPI()
        self.tracker = RateLimitTracker()
        # Reset global tracker before each test
        from src.core.rate_limiter import _global_tracker

        _global_tracker.reset_all()

    def create_mock_request(
        self,
        user_id: str = "test_user",
        path: str = "/api/test",
    ) -> Request:
        """Create a mock FastAPI request."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
        }
        request = Request(scope)
        # Attach user_id to request state
        request.state.user_id = user_id  # type: ignore[attr-defined]
        return request

    async def mock_endpoint(self, request: Request) -> JSONResponse:
        """Mock endpoint function for testing."""
        return JSONResponse(content={"message": "success"})

    @patch("src.core.rate_limiter.get_settings")
    async def test_rate_limit_allows_requests_under_limit(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Test decorator allows requests under the rate limit."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = RateLimitConfig(requests=3, window_seconds=60)
        decorated_func = rate_limit(config)(self.mock_endpoint)

        # Make 3 requests - all should succeed
        for _ in range(3):
            request = self.create_mock_request()
            response = await decorated_func(request)
            assert response.status_code == 200

    @patch("src.core.rate_limiter.get_settings")
    async def test_rate_limit_blocks_requests_over_limit(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Test decorator blocks requests over the rate limit."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = RateLimitConfig(requests=2, window_seconds=60)
        decorated_func = rate_limit(config)(self.mock_endpoint)

        # First 2 requests should succeed
        for _ in range(2):
            request = self.create_mock_request()
            response = await decorated_func(request)
            assert response.status_code == 200

        # 3rd request should be rate limited
        request = self.create_mock_request()
        with pytest.raises(RateLimitError) as exc_info:
            await decorated_func(request)

        assert exc_info.value.status_code == 429
        assert "retry_after" in exc_info.value.details

    @patch("src.core.rate_limiter.get_settings")
    async def test_rate_limit_disabled(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Test decorator allows all requests when rate limiting is disabled."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = False
        mock_get_settings.return_value = mock_settings

        config = RateLimitConfig(requests=1, window_seconds=60)
        decorated_func = rate_limit(config)(self.mock_endpoint)

        # Even though limit is 1, make multiple requests
        for _ in range(5):
            request = self.create_mock_request()
            response = await decorated_func(request)
            assert response.status_code == 200

    @patch("src.core.rate_limiter.get_settings")
    async def test_rate_limit_tracks_by_user(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Test that rate limiting tracks by user_id."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = RateLimitConfig(requests=1, window_seconds=60)
        decorated_func = rate_limit(config)(self.mock_endpoint)

        # User 1 makes a request
        request1 = self.create_mock_request(user_id="user_1")
        response1 = await decorated_func(request1)
        assert response1.status_code == 200

        # User 1's second request should be blocked
        request1_again = self.create_mock_request(user_id="user_1")
        with pytest.raises(RateLimitError):
            await decorated_func(request1_again)

        # User 2 should still be able to make a request
        request2 = self.create_mock_request(user_id="user_2")
        response2 = await decorated_func(request2)
        assert response2.status_code == 200

    @patch("src.core.rate_limiter.get_settings")
    async def test_rate_limit_fallback_to_ip(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Test that rate limiting falls back to IP address when no user_id."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = RateLimitConfig(requests=1, window_seconds=60)
        decorated_func = rate_limit(config)(self.mock_endpoint)

        # Create request without user_id
        request = self.create_mock_request()
        # Remove user_id from state to test IP fallback
        delattr(request.state, "user_id")

        # First request from this IP should succeed
        response = await decorated_func(request)
        assert response.status_code == 200

        # Second request from same IP should be blocked
        with pytest.raises(RateLimitError):
            await decorated_func(request)

    @patch("src.core.rate_limiter.get_settings")
    async def test_rate_limit_concurrent_requests(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Test rate limiting handles concurrent requests correctly."""
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 100
        mock_get_settings.return_value = mock_settings

        config = RateLimitConfig(requests=5, window_seconds=60)
        decorated_func = rate_limit(config)(self.mock_endpoint)

        # Make concurrent requests
        async def make_request(n: int) -> tuple[int, Exception | None]:
            request = self.create_mock_request(user_id=f"concurrent_user_{n % 3}")
            try:
                response = await decorated_func(request)
                return response.status_code, None
            except Exception as e:
                return 0, e

        results = await asyncio.gather(*[make_request(i) for i in range(10)])

        # Check that some requests succeeded and some were rate limited
        success_count = sum(1 for status, _ in results if status == 200)
        rate_limited_count = sum(1 for _, exc in results if exc is not None)

        # Each of the 3 users can make 5 requests, so at most 15 total
        # But we made 10 requests, so all should succeed
        assert success_count == 10
        assert rate_limited_count == 0
