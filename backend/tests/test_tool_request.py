"""Tests for user tool request endpoint."""

# Set required env vars BEFORE any src imports trigger config validation
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_request_new_toolkit():
    """User can request a new toolkit."""
    from src.api.routes.tool_request import request_tool_access, ToolRequestCreate

    mock_user = MagicMock()
    mock_user.id = "user-123"

    body = ToolRequestCreate(
        toolkit_slug="VEEVA",
        reason="Need for pharma pipeline",
    )

    with (
        patch("src.api.routes.tool_request._get_user_tenant_id", new_callable=AsyncMock, return_value="tenant-1"),
        patch("src.api.routes.tool_request._is_toolkit_approved", new_callable=AsyncMock, return_value=False),
        patch("src.api.routes.tool_request._has_pending_request", new_callable=AsyncMock, return_value=False),
        patch("src.api.routes.tool_request._create_request", new_callable=AsyncMock, return_value={"id": "r1", "status": "pending"}),
        patch("src.api.routes.tool_request._notify_admins", new_callable=AsyncMock),
    ):
        result = await request_tool_access(body=body, user=mock_user)
        assert result["status"] == "submitted"


@pytest.mark.asyncio
async def test_request_already_approved():
    """If toolkit already approved, return already_approved."""
    from src.api.routes.tool_request import request_tool_access, ToolRequestCreate

    mock_user = MagicMock()
    mock_user.id = "user-123"

    body = ToolRequestCreate(toolkit_slug="SALESFORCE")

    with (
        patch("src.api.routes.tool_request._get_user_tenant_id", new_callable=AsyncMock, return_value="tenant-1"),
        patch("src.api.routes.tool_request._is_toolkit_approved", new_callable=AsyncMock, return_value=True),
    ):
        result = await request_tool_access(body=body, user=mock_user)
        assert result["status"] == "already_approved"


@pytest.mark.asyncio
async def test_request_already_pending():
    """If toolkit request already pending, return already_pending."""
    from src.api.routes.tool_request import request_tool_access, ToolRequestCreate

    mock_user = MagicMock()
    mock_user.id = "user-123"

    body = ToolRequestCreate(toolkit_slug="VEEVA")

    with (
        patch("src.api.routes.tool_request._get_user_tenant_id", new_callable=AsyncMock, return_value="tenant-1"),
        patch("src.api.routes.tool_request._is_toolkit_approved", new_callable=AsyncMock, return_value=False),
        patch("src.api.routes.tool_request._has_pending_request", new_callable=AsyncMock, return_value=True),
    ):
        result = await request_tool_access(body=body, user=mock_user)
        assert result["status"] == "already_pending"


@pytest.mark.asyncio
async def test_list_own_requests():
    """User can list their own requests."""
    from src.api.routes.tool_request import list_own_requests

    mock_user = MagicMock()
    mock_user.id = "user-123"

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[{"id": "r1", "toolkit_slug": "VEEVA", "status": "pending"}]
    )

    with patch("src.api.routes.tool_request.get_supabase_client", return_value=mock_db):
        result = await list_own_requests(user=mock_user)
        assert len(result["requests"]) == 1
