"""Tests for CommunicationRouter service (US-938)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.communication_router import CommunicationRouter, get_communication_router
from src.models.communication import (
    ChannelType,
    CommunicationRequest,
    MessagePriority,
)


class TestMessagePriorityToChannels:
    """Test priority -> channel mapping."""

    @pytest.mark.asyncio
    async def test_critical_priority_uses_in_app_and_push(self):
        """CRITICAL priority should always use in_app + push."""
        router = CommunicationRouter()
        channels = router._determine_channels(
            MessagePriority.CRITICAL, {"preferred_channels": ["email"]}
        )
        assert set(channels) == {"in_app", "push"}

    @pytest.mark.asyncio
    async def test_important_priority_uses_in_app_plus_preferred(self):
        """IMPORTANT priority should use in_app + user's preferred channel."""
        router = CommunicationRouter()
        channels = router._determine_channels(
            MessagePriority.IMPORTANT, {"preferred_channels": ["slack"]}
        )
        assert set(channels) == {"in_app", "slack"}

    @pytest.mark.asyncio
    async def test_important_priority_with_no_preference_uses_in_app_only(self):
        """IMPORTANT with no preference defaults to in_app only."""
        router = CommunicationRouter()
        channels = router._determine_channels(
            MessagePriority.IMPORTANT, {"preferred_channels": []}
        )
        assert channels == ["in_app"]

    @pytest.mark.asyncio
    async def test_fyi_priority_uses_in_app_only(self):
        """FYI priority should only use in_app notifications."""
        router = CommunicationRouter()
        channels = router._determine_channels(
            MessagePriority.FYI, {"preferred_channels": ["slack", "email"]}
        )
        assert channels == ["in_app"]

    @pytest.mark.asyncio
    async def test_background_priority_uses_no_channels(self):
        """BACKGROUND priority should not send any notifications."""
        router = CommunicationRouter()
        channels = router._determine_channels(
            MessagePriority.BACKGROUND, {"preferred_channels": ["slack"]}
        )
        assert channels == []


class TestUserPreferenceRetrieval:
    """Test getting user communication preferences."""

    @pytest.mark.asyncio
    async def test_get_user_preferences_returns_defaults(self):
        """Should return default preferences when none set."""
        router = CommunicationRouter()
        with patch.object(
            router, "_get_user_settings", return_value={"preferences": {}}
        ):
            prefs = await router._get_user_preferences("user-123")
            assert prefs == {
                "preferred_channels": ["in_app"],
                "email_enabled": True,
                "slack_enabled": False,
            }

    @pytest.mark.asyncio
    async def test_get_user_preferences_returns_saved_preferences(self):
        """Should return user's saved preferences."""
        router = CommunicationRouter()
        with patch.object(
            router,
            "_get_user_settings",
            return_value={
                "preferences": {
                    "communication": {
                        "preferred_channels": ["slack", "email"],
                        "email_enabled": True,
                        "slack_enabled": True,
                    }
                }
            },
        ):
            prefs = await router._get_user_preferences("user-123")
            assert prefs["preferred_channels"] == ["slack", "email"]


class TestChannelSending:
    """Test sending to individual channels."""

    @pytest.mark.asyncio
    async def test_send_to_in_app_channel(self):
        """Should use NotificationService for in_app channel."""
        router = CommunicationRouter()
        request = CommunicationRequest(
            user_id="user-123",
            message="Test message",
            priority=MessagePriority.FYI,
            title="Test",
        )

        with patch(
            "src.core.communication_router.NotificationService.create_notification",
            new_callable=AsyncMock,
            return_value=MagicMock(id="notif-123"),
        ) as mock_create:
            result = await router._send_to_channel(
                request.user_id, request.message, "in_app", request
            )

            assert result["success"] is True
            assert result["channel"] == "in_app"
            assert result["message_id"] == "notif-123"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_to_email_channel(self):
        """Should use EmailService for email channel."""
        router = CommunicationRouter()
        request = CommunicationRequest(
            user_id="user-123",
            message="Test email body",
            priority=MessagePriority.IMPORTANT,
            title="Test Subject",
        )

        with patch(
            "src.core.communication_router.EmailService",
        ) as mock_email_service:
            mock_instance = AsyncMock()
            mock_instance._send_email = AsyncMock(return_value="email-123")
            mock_email_service.return_value = mock_instance

            # Mock getting user email
            with patch.object(
                router, "_get_user_email", return_value="user@example.com"
            ):
                result = await router._send_to_channel(
                    request.user_id, request.message, "email", request
                )

                assert result["success"] is True
                assert result["channel"] == "email"

    @pytest.mark.asyncio
    async def test_send_to_slack_channel_not_implemented(self):
        """Slack channel should return not implemented status."""
        router = CommunicationRouter()
        request = CommunicationRequest(
            user_id="user-123",
            message="Test Slack message",
            priority=MessagePriority.IMPORTANT,
        )

        result = await router._send_to_channel(
            request.user_id, request.message, "slack", request
        )

        # Should not crash, but indicate not configured
        assert result["success"] is False
        assert "not implemented" in result["error"].lower()


class TestRouteMessage:
    """Test the main route_message method."""

    @pytest.mark.asyncio
    async def test_route_fyi_message_to_in_app_only(self):
        """FYI message should route to in_app only."""
        router = CommunicationRouter()
        request = CommunicationRequest(
            user_id="user-123",
            message="FYI message",
            priority=MessagePriority.FYI,
            title="FYI",
        )

        with patch.object(
            router, "_get_user_preferences", return_value={"preferred_channels": ["in_app"]}
        ), patch.object(
            router,
            "_send_to_channel",
            new_callable=AsyncMock,
            return_value={"success": True, "channel": "in_app", "message_id": "notif-1"},
        ):
            response = await router.route_message(request)

            assert response.user_id == "user-123"
            assert response.priority == MessagePriority.FYI
            assert ChannelType.IN_APP in response.channels_used

    @pytest.mark.asyncio
    async def test_route_with_force_channels_override(self):
        """force_channels should bypass priority routing."""
        router = CommunicationRouter()
        request = CommunicationRequest(
            user_id="user-123",
            message="Forced message",
            priority=MessagePriority.FYI,  # Normally in_app only
            force_channels=[ChannelType.EMAIL],  # But force email
        )

        with patch.object(
            router,
            "_send_to_channel",
            new_callable=AsyncMock,
            return_value={"success": True, "channel": "email", "message_id": "email-1"},
        ):
            response = await router.route_message(request)

            assert ChannelType.EMAIL in response.channels_used

    @pytest.mark.asyncio
    async def test_route_continues_on_partial_failure(self):
        """Should attempt all channels even if some fail."""
        router = CommunicationRouter()
        request = CommunicationRequest(
            user_id="user-123",
            message="Test",
            priority=MessagePriority.CRITICAL,
        )

        call_count = 0

        async def mock_send(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": False, "channel": "in_app", "error": "Failed"}
            return {"success": True, "channel": "push", "message_id": "push-1"}

        with patch.object(
            router, "_get_user_preferences", return_value={}
        ), patch.object(router, "_send_to_channel", side_effect=mock_send):
            response = await router.route_message(request)

            # Both channels attempted
            assert len(response.results) == 2
            # One succeeded
            assert any(r.success for r in response.results.values())


class TestSingleton:
    """Test singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_communication_router_returns_singleton(self):
        """Should return the same instance on multiple calls."""
        router1 = get_communication_router()
        router2 = get_communication_router()
        assert router1 is router2
