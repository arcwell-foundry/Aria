"""Integration tests for ComposioSessionManager.

These tests exercise the real Composio Tool Router API and are skipped
when ``COMPOSIO_API_KEY`` is not set in the environment.  They are NOT
unit tests — they hit the Composio servers.

Run with:
    COMPOSIO_API_KEY=<key> pytest tests/test_composio_session.py -v
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.composio_sessions import (
    ComposioSessionManager,
    get_session_manager,
)

# ---------------------------------------------------------------------------
# Unit tests (always run — no API key needed)
# ---------------------------------------------------------------------------


class TestEntityId:
    """Test the entity ID generation logic."""

    def test_entity_id_format(self) -> None:
        manager = ComposioSessionManager()
        entity = manager._entity_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert entity == "aria_user_a1b2c3d4e5f6"

    def test_entity_id_short_uuid(self) -> None:
        manager = ComposioSessionManager()
        entity = manager._entity_id("abc")
        assert entity == "aria_user_abc"

    def test_entity_id_strips_hyphens(self) -> None:
        manager = ComposioSessionManager()
        entity = manager._entity_id("a-b-c-d-e-f")
        assert entity == "aria_user_abcdef"


class TestSessionCaching:
    """Test that sessions are cached and the singleton works."""

    def test_singleton_returns_same_instance(self) -> None:
        import src.integrations.composio_sessions as mod

        mod._session_manager = None
        mgr1 = get_session_manager()
        mgr2 = get_session_manager()
        assert mgr1 is mgr2
        mod._session_manager = None

    @pytest.mark.asyncio
    async def test_cached_session_returned(self) -> None:
        """Second call for same user should return cached session."""
        manager = ComposioSessionManager()

        mock_session = MagicMock()
        mock_session.session_id = "sess_test_123"

        mock_composio = MagicMock()
        mock_composio.create.return_value = mock_session
        manager._composio = mock_composio

        session1 = await manager.get_session("user-1")
        session2 = await manager.get_session("user-1")

        assert session1 is session2
        assert mock_composio.create.call_count == 1

    @pytest.mark.asyncio
    async def test_different_users_get_different_sessions(self) -> None:
        """Different users should get distinct sessions."""
        manager = ComposioSessionManager()

        mock_session_a = MagicMock()
        mock_session_a.session_id = "sess_a"
        mock_session_b = MagicMock()
        mock_session_b.session_id = "sess_b"

        call_count = 0

        def _create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_session_a
            return mock_session_b

        mock_composio = MagicMock()
        mock_composio.create.side_effect = _create
        manager._composio = mock_composio

        session_a = await manager.get_session("user-a")
        session_b = await manager.get_session("user-b")

        assert session_a is not session_b
        assert session_a.session_id == "sess_a"
        assert session_b.session_id == "sess_b"

    @pytest.mark.asyncio
    async def test_close_clears_cache(self) -> None:
        """close() should empty the session cache."""
        manager = ComposioSessionManager()

        mock_session = MagicMock()
        mock_session.session_id = "sess_close"

        mock_composio = MagicMock()
        mock_composio.create.return_value = mock_session
        manager._composio = mock_composio

        await manager.get_session("user-close")
        assert len(manager._sessions) == 1

        await manager.close()
        assert len(manager._sessions) == 0
        assert manager._composio is None


class TestExecuteAction:
    """Test the execute_action delegation."""

    @pytest.mark.asyncio
    async def test_execute_action_requires_connection_id(self) -> None:
        manager = ComposioSessionManager()
        with pytest.raises(ValueError, match="connection_id is required"):
            await manager.execute_action(
                user_id="user-1",
                action="OUTLOOK_GET_MAIL_DELTA",
                params={},
            )

    @pytest.mark.asyncio
    async def test_execute_action_delegates_to_oauth(self) -> None:
        manager = ComposioSessionManager()

        mock_result = {"successful": True, "data": {"emails": []}, "error": None}

        mock_oauth = MagicMock()
        mock_oauth.execute_action = AsyncMock(return_value=mock_result)

        with patch(
            "src.integrations.oauth.get_oauth_client",
            return_value=mock_oauth,
        ):
            result = await manager.execute_action(
                user_id="user-1",
                action="OUTLOOK_GET_MAIL_DELTA",
                params={"folder": "inbox"},
                connection_id="ca_abc123",
            )

            assert result == mock_result
            mock_oauth.execute_action.assert_awaited_once_with(
                connection_id="ca_abc123",
                action="OUTLOOK_GET_MAIL_DELTA",
                params={"folder": "inbox"},
                user_id="user-1",
            )


# ---------------------------------------------------------------------------
# Integration tests (require COMPOSIO_API_KEY)
# ---------------------------------------------------------------------------

_SKIP_REASON = "COMPOSIO_API_KEY not set — skipping Composio integration tests"


@pytest.mark.skipif(not os.environ.get("COMPOSIO_API_KEY"), reason=_SKIP_REASON)
class TestComposioSessionIntegration:
    """Live integration tests that hit the real Composio API."""

    @pytest.mark.asyncio
    async def test_session_creation(self) -> None:
        """Session creates without error and returns a session_id."""
        manager = ComposioSessionManager()
        try:
            session = await manager.get_session("integration-test-user")
            assert session.session_id
            assert hasattr(session, "tools")
            assert hasattr(session, "mcp")
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_tools_available(self) -> None:
        """Session returns tool definitions."""
        manager = ComposioSessionManager()
        try:
            tools = await manager.get_tools("integration-test-user")
            assert isinstance(tools, list)
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_session_caching_live(self) -> None:
        """Same user_id returns the cached session (same session_id)."""
        manager = ComposioSessionManager()
        try:
            session1 = await manager.get_session("cache-test-user")
            session2 = await manager.get_session("cache-test-user")
            assert session1.session_id == session2.session_id
            assert session1 is session2
        finally:
            await manager.close()
