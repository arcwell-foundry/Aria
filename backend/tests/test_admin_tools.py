"""Tests for admin tool governance API."""

# Set required env vars BEFORE any src imports trigger config validation
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_toolkit_catalog():
    """Admin can get the toolkit catalog."""
    from src.api.routes.admin_tools import get_toolkit_catalog

    mock_admin = MagicMock()
    mock_admin.id = "admin-user-123"

    mock_db = MagicMock()
    # capability_graph query
    mock_db.table.return_value.select.return_value.not_.is_.return_value.execute.return_value = MagicMock(
        data=[
            {"composio_app_name": "SALESFORCE", "provider_type": "composio_oauth", "capability_category": "crm", "quality_score": 0.9, "is_active": True},
            {"composio_app_name": "GMAIL", "provider_type": "composio_oauth", "capability_category": "email", "quality_score": 0.95, "is_active": True},
        ]
    )

    with (
        patch("src.api.routes.admin_tools._get_admin_company_id", new_callable=AsyncMock, return_value="company-1"),
        patch("src.api.routes.admin_tools.get_supabase_client", return_value=mock_db),
    ):
        # Mock the config query (second call to table)
        config_mock = MagicMock()
        config_mock.data = [{"toolkit_slug": "SALESFORCE", "status": "approved"}]

        # Set up chained calls for both queries
        table_calls = [MagicMock(), MagicMock()]
        # First call: capability_graph
        table_calls[0].select.return_value.not_.is_.return_value.execute.return_value = MagicMock(
            data=[
                {"composio_app_name": "SALESFORCE", "provider_type": "composio_oauth", "capability_category": "crm", "quality_score": 0.9, "is_active": True},
            ]
        )
        # Second call: tenant_toolkit_config
        table_calls[1].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"toolkit_slug": "SALESFORCE", "status": "approved"}]
        )
        mock_db.table.side_effect = lambda name: table_calls[0] if name == "capability_graph" else table_calls[1]

        result = await get_toolkit_catalog(admin=mock_admin)
        assert "catalog" in result
        assert len(result["catalog"]) == 1
        assert result["catalog"][0]["composio_app_name"] == "SALESFORCE"
        assert result["catalog"][0]["org_status"] == "approved"


@pytest.mark.asyncio
async def test_create_toolkit_config():
    """Admin can approve a toolkit."""
    from src.api.routes.admin_tools import create_toolkit_config, ToolkitConfigCreate

    mock_admin = MagicMock()
    mock_admin.id = "admin-user-123"

    mock_db = MagicMock()
    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
        data=[{"id": "t1", "toolkit_slug": "SALESFORCE", "status": "approved"}]
    )

    body = ToolkitConfigCreate(
        toolkit_slug="SALESFORCE",
        status="approved",
    )

    with (
        patch("src.api.routes.admin_tools._get_admin_company_id", new_callable=AsyncMock, return_value="company-1"),
        patch("src.api.routes.admin_tools.get_supabase_client", return_value=mock_db),
    ):
        result = await create_toolkit_config(body=body, admin=mock_admin)
        assert result["status"] == "approved"
        assert result["toolkit"]["toolkit_slug"] == "SALESFORCE"


@pytest.mark.asyncio
async def test_list_access_requests():
    """Admin can list pending requests."""
    from src.api.routes.admin_tools import list_access_requests

    mock_admin = MagicMock()
    mock_admin.id = "admin-user-123"

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "r1", "toolkit_slug": "VEEVA", "status": "pending", "user_id": "user-1"},
        ]
    )

    with (
        patch("src.api.routes.admin_tools._get_admin_company_id", new_callable=AsyncMock, return_value="company-1"),
        patch("src.api.routes.admin_tools.get_supabase_client", return_value=mock_db),
    ):
        result = await list_access_requests(admin=mock_admin, status_filter=None)
        assert "requests" in result
        assert len(result["requests"]) == 1


@pytest.mark.asyncio
async def test_review_access_request_approve():
    """Admin can approve a user request."""
    from src.api.routes.admin_tools import review_access_request, RequestReviewBody

    mock_admin = MagicMock()
    mock_admin.id = "admin-user-123"

    mock_db = MagicMock()
    # Fetch the request
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data={"id": "r1", "user_id": "user-1", "toolkit_slug": "VEEVA", "toolkit_display_name": "Veeva", "tenant_id": "company-1"}
    )
    # Update and upsert calls
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])

    body = RequestReviewBody(status="approved", admin_notes="Looks good")

    with (
        patch("src.api.routes.admin_tools._get_admin_company_id", new_callable=AsyncMock, return_value="company-1"),
        patch("src.api.routes.admin_tools.get_supabase_client", return_value=mock_db),
        patch("src.api.routes.admin_tools.ws_manager") as mock_ws,
    ):
        mock_ws.send_to_user = AsyncMock()
        result = await review_access_request(request_id="r1", body=body, admin=mock_admin)
        assert result["status"] == "approved"
