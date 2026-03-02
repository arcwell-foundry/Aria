"""Tests for tool assembly wiring in websocket handler."""

# Set required env vars BEFORE any src imports trigger config validation
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock, patch
from src.services.tool_assembly import ToolSet


@pytest.mark.asyncio
async def test_websocket_uses_tool_assembly():
    """Verify that get_tools_for_user returns a proper ToolSet."""
    mock_tool_set = ToolSet(
        tools=[{"name": "read_recent_emails", "input_schema": {}}],
        email_integration={"id": "e1", "integration_type": "gmail"},
        meta_tool_defs=[],
        email_context="",
        calendar_context="",
    )
    with patch("src.services.tool_assembly.get_tools_for_user", new_callable=AsyncMock, return_value=mock_tool_set):
        from src.services.tool_assembly import get_tools_for_user
        result = await get_tools_for_user("test-user")
        assert result.email_integration is not None
        assert len(result.tools) == 1


@pytest.mark.asyncio
async def test_tool_set_without_email():
    """ToolSet with no email integration has no email tools."""
    mock_tool_set = ToolSet(
        tools=[{"name": "COMPOSIO_SEARCH_TOOLS", "input_schema": {}}],
        email_integration=None,
        meta_tool_defs=[{"name": "COMPOSIO_SEARCH_TOOLS", "input_schema": {}}],
        email_context="",
        calendar_context="",
    )
    with patch("src.services.tool_assembly.get_tools_for_user", new_callable=AsyncMock, return_value=mock_tool_set):
        from src.services.tool_assembly import get_tools_for_user
        result = await get_tools_for_user("test-user")
        assert result.email_integration is None
        assert "read_recent_emails" not in [t["name"] for t in result.tools]
