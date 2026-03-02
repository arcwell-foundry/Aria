"""Tests for tool_assembly service."""

# Set required env vars BEFORE any src imports trigger config validation
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    return client


@pytest.mark.asyncio
async def test_get_tools_with_email_connected():
    """When user has email integration, EMAIL_TOOL_DEFINITIONS are included."""
    mock_email_int = {"id": "e1", "integration_type": "gmail", "status": "active"}
    with (
        patch("src.services.tool_assembly.get_email_integration", new_callable=AsyncMock, return_value=mock_email_int),
        patch("src.services.tool_assembly.get_composio_meta_tool_definitions", new_callable=AsyncMock, return_value=[]),
        patch("src.services.tool_assembly.get_email_context_for_chat", new_callable=AsyncMock, return_value=""),
        patch("src.services.tool_assembly.get_calendar_context_for_chat", new_callable=AsyncMock, return_value=""),
    ):
        from src.services.tool_assembly import get_tools_for_user
        result = await get_tools_for_user("user-1")
        assert result.email_integration is not None
        # EMAIL_TOOL_DEFINITIONS has at least 3 tools
        email_names = [t["name"] for t in result.tools]
        assert "read_recent_emails" in email_names


@pytest.mark.asyncio
async def test_get_tools_no_email():
    """When no email integration, email tools excluded."""
    with (
        patch("src.services.tool_assembly.get_email_integration", new_callable=AsyncMock, return_value=None),
        patch("src.services.tool_assembly.get_composio_meta_tool_definitions", new_callable=AsyncMock, return_value=[]),
        patch("src.services.tool_assembly.get_email_context_for_chat", new_callable=AsyncMock, return_value=""),
        patch("src.services.tool_assembly.get_calendar_context_for_chat", new_callable=AsyncMock, return_value=""),
    ):
        from src.services.tool_assembly import get_tools_for_user
        result = await get_tools_for_user("user-1")
        assert result.email_integration is None
        email_names = [t.get("name", "") for t in result.tools]
        assert "read_recent_emails" not in email_names


@pytest.mark.asyncio
async def test_dispatch_composio_tool():
    """Composio meta tools route to execute_composio_meta_tool."""
    with patch("src.services.tool_assembly.execute_composio_meta_tool", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"data": "found tools", "successful": True}
        from src.services.tool_assembly import dispatch_tool_call
        result = await dispatch_tool_call(
            user_id="user-1",
            tool_name="COMPOSIO_SEARCH_TOOLS",
            tool_input={"query": "salesforce"},
        )
        mock_exec.assert_called_once()
        assert result["successful"] is True


@pytest.mark.asyncio
async def test_dispatch_email_tool():
    """Email tools route to execute_email_tool when integration provided."""
    mock_integration = {"id": "e1", "integration_type": "gmail"}
    with patch("src.services.tool_assembly.execute_email_tool", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"emails": []}
        from src.services.tool_assembly import dispatch_tool_call
        result = await dispatch_tool_call(
            user_id="user-1",
            tool_name="read_recent_emails",
            tool_input={"count": 5},
            email_integration=mock_integration,
        )
        mock_exec.assert_called_once()
        assert "emails" in result


@pytest.mark.asyncio
async def test_dispatch_unknown_tool():
    """Unknown tool name returns error dict."""
    from src.services.tool_assembly import dispatch_tool_call
    result = await dispatch_tool_call(
        user_id="user-1",
        tool_name="nonexistent_tool",
        tool_input={},
    )
    assert "error" in result
