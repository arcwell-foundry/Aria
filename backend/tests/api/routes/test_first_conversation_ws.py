"""Tests for WebSocket first conversation delivery."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMaybeDeliverFirstConversation:
    """Tests for _maybe_deliver_first_conversation WebSocket handler."""

    @pytest.mark.asyncio
    async def test_skips_when_onboarding_not_complete(self):
        """Should return False if onboarding hasn't been completed yet."""
        from src.api.routes.websocket import _maybe_deliver_first_conversation

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"completed_at": None}  # Not completed
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result

        # Patch the SupabaseClient import inside the function
        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_db):
            result = await _maybe_deliver_first_conversation("test-user-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_skips_when_already_delivered(self):
        """Should return False if first conversation was already delivered."""
        from src.api.routes.websocket import _maybe_deliver_first_conversation

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {
            "completed_at": "2026-01-01T00:00:00Z",
            "metadata": {"first_conversation_ws_delivered": True}
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_db):
            result = await _maybe_deliver_first_conversation("test-user-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_delivers_stored_message(self):
        """Should deliver stored first conversation message via WebSocket."""
        from src.api.routes.websocket import _maybe_deliver_first_conversation

        mock_db = MagicMock()

        # Set up chain for onboarding_state query
        ob_chain = MagicMock()
        ob_chain.data = {
            "completed_at": "2026-01-01T00:00:00Z",
            "metadata": {}
        }

        # Set up chain for conversations query
        conv_chain = MagicMock()
        conv_chain.data = [{"id": "conv-123"}]

        # Set up chain for messages query
        msg_chain = MagicMock()
        msg_chain.data = [{
            "content": "Test first conversation content",
            "metadata": {
                "rich_content": [{"type": "goal_plan"}],
                "ui_commands": [],
                "suggestions": ["Tell me more"]
            }
        }]

        # Set up chain for update
        update_chain = MagicMock()
        update_chain.data = [{}]

        def table_side_effect(table_name):
            mock = MagicMock()
            if table_name == "onboarding_state":
                mock.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = ob_chain
                mock.update.return_value.eq.return_value.execute.return_value = update_chain
            elif table_name == "conversations":
                mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = conv_chain
            elif table_name == "messages":
                mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = msg_chain
            return mock

        mock_db.table.side_effect = table_side_effect

        # WebSocket manager mock
        mock_ws_manager = AsyncMock()

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_db), \
             patch("src.api.routes.websocket.ws_manager", mock_ws_manager):
            result = await _maybe_deliver_first_conversation("test-user-id")

        assert result is True
        mock_ws_manager.send_aria_message.assert_called_once()
        call_kwargs = mock_ws_manager.send_aria_message.call_args[1]
        assert call_kwargs["message"] == "Test first conversation content"
        assert call_kwargs["user_id"] == "test-user-id"


class TestGenerateFallbackFirstConversation:
    """Tests for _generate_fallback_first_conversation helper."""

    @pytest.mark.asyncio
    async def test_generates_personalized_greeting(self):
        """Should generate a personalized greeting using user profile."""
        from src.api.routes.websocket import _generate_fallback_first_conversation

        mock_db = MagicMock()
        profile_result = MagicMock()
        profile_result.data = {
            "full_name": "John Doe",
            "title": "Sales Director",
            "companies": {"name": "Acme Corp"}
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = profile_result

        result = await _generate_fallback_first_conversation("test-user-id", mock_db)

        assert result is not None
        assert "John" in result  # First name used
        assert "Acme Corp" in result  # Company name used
        assert "Sales Director" in result  # Title used
        assert "ARIA" in result  # Mentions ARIA

    @pytest.mark.asyncio
    async def test_handles_missing_profile_gracefully(self):
        """Should return None if profile lookup fails."""
        from src.api.routes.websocket import _generate_fallback_first_conversation

        mock_db = MagicMock()
        profile_result = MagicMock()
        profile_result.data = None
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = profile_result

        result = await _generate_fallback_first_conversation("test-user-id", mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_partial_profile(self):
        """Should work with partial profile data (no company or title)."""
        from src.api.routes.websocket import _generate_fallback_first_conversation

        mock_db = MagicMock()
        profile_result = MagicMock()
        profile_result.data = {
            "full_name": "Jane",
            "title": None,
            "companies": None
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = profile_result

        result = await _generate_fallback_first_conversation("test-user-id", mock_db)

        assert result is not None
        assert "Jane" in result
        assert "ARIA" in result
