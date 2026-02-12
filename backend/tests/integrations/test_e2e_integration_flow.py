"""End-to-end tests for integration connection flow."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.domain import IntegrationStatus, IntegrationType, SyncStatus
from src.integrations.oauth import ComposioOAuthClient
from src.integrations.service import IntegrationService


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Mock Supabase client."""
    with patch("src.integrations.service.SupabaseClient") as m:
        client = MagicMock()
        m.get_client.return_value = client
        yield client


@pytest.fixture
def mock_oauth_client() -> AsyncMock:
    """Mock OAuth client."""
    with patch("src.integrations.service.get_oauth_client") as m:
        client = AsyncMock()
        m.return_value = client
        yield client


class TestFullOAuthFlow:
    """Tests for complete OAuth connection flow."""

    @pytest.mark.asyncio
    async def test_full_oauth_flow_google_calendar(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test complete OAuth flow for Google Calendar integration.

        Flow:
        1. Generate authorization URL (returns URL + connection_id)
        2. Create integration record using returned connection_id
        3. Verify integration exists
        """
        oauth_client = ComposioOAuthClient()
        service = IntegrationService()

        # Mock Composio SDK for auth URL generation
        mock_composio = MagicMock()
        oauth_client._composio = mock_composio

        mock_config = MagicMock()
        mock_config.id = "auth-config-gcal"
        mock_config.toolkit.slug = "google_calendar"
        mock_list_response = MagicMock()
        mock_list_response.items = [mock_config]
        mock_composio.client.auth_configs.list.return_value = mock_list_response

        mock_link_response = MagicMock()
        mock_link_response.redirect_url = "https://auth.composio.dev/authorize?code=test_auth_code_123"
        mock_link_response.connected_account_id = "conn-abc123"
        mock_composio.client.link.create.return_value = mock_link_response

        # Step 1: Generate auth URL with connection ID
        auth_url, connection_id = await oauth_client.generate_auth_url_with_connection_id(
            user_id="user-123",
            integration_type="google_calendar",
            redirect_uri="http://localhost:5173/integrations/callback",
        )

        assert auth_url == "https://auth.composio.dev/authorize?code=test_auth_code_123"
        assert connection_id == "conn-abc123"

        # Step 2: Create integration record - use proper mocking pattern
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-456",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "composio_connection_id": "conn-abc123",
                "composio_account_id": "acct-xyz789",
                "display_name": "user@example.com",
                "status": "active",
                "sync_status": "success",
                "last_sync_at": None,
                "error_message": None,
                "metadata": {},
                "created_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                "updated_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            }
        ]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_response

        integration = await service.create_integration(
            user_id="user-123",
            integration_type=IntegrationType.GOOGLE_CALENDAR,
            composio_connection_id=connection_id,
            display_name="user@example.com",
        )

        assert integration["integration_type"] == "google_calendar"
        assert integration["composio_connection_id"] == "conn-abc123"
        assert integration["display_name"] == "user@example.com"
        assert integration["status"] == "active"

        # Step 4: Verify integration can be retrieved
        mock_get_response = MagicMock()
        mock_get_response.data = integration
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_get_response

        retrieved = await service.get_integration("user-123", IntegrationType.GOOGLE_CALENDAR)
        assert retrieved is not None
        assert retrieved["id"] == "int-456"
        assert retrieved["integration_type"] == "google_calendar"

    @pytest.mark.asyncio
    async def test_full_oauth_flow_gmail(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test complete OAuth flow for Gmail integration."""
        oauth_client = ComposioOAuthClient()
        service = IntegrationService()

        # Mock Composio SDK for auth URL generation
        mock_composio = MagicMock()
        oauth_client._composio = mock_composio

        mock_config = MagicMock()
        mock_config.id = "auth-config-gmail"
        mock_config.toolkit.slug = "gmail"
        mock_list_response = MagicMock()
        mock_list_response.items = [mock_config]
        mock_composio.client.auth_configs.list.return_value = mock_list_response

        mock_link_response = MagicMock()
        mock_link_response.redirect_url = "https://accounts.google.com/o/oauth2/auth?gmail"
        mock_link_response.connected_account_id = "conn-gmail-123"
        mock_composio.client.link.create.return_value = mock_link_response

        # Step 1: Generate auth URL with connection ID
        auth_url, connection_id = await oauth_client.generate_auth_url_with_connection_id(
            user_id="user-123",
            integration_type="gmail",
            redirect_uri="http://localhost:5173/integrations/callback",
        )

        assert auth_url == "https://accounts.google.com/o/oauth2/auth?gmail"
        assert connection_id == "conn-gmail-123"

        # Create integration
        mock_insert_response = MagicMock()
        mock_insert_response.data = [
            {
                "id": "int-gmail-789",
                "user_id": "user-123",
                "integration_type": "gmail",
                "composio_connection_id": "conn-gmail-123",
                "composio_account_id": "acct-gmail-456",
                "display_name": "test@gmail.com",
                "status": "active",
                "sync_status": "success",
                "last_sync_at": None,
                "error_message": None,
                "metadata": {},
                "created_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                "updated_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            }
        ]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_insert_response

        integration = await service.create_integration(
            user_id="user-123",
            integration_type=IntegrationType.GMAIL,
            composio_connection_id=connection_id,
            display_name="test@gmail.com",
        )

        assert integration["integration_type"] == "gmail"
        assert integration["display_name"] == "test@gmail.com"
        assert integration["status"] == "active"

    @pytest.mark.asyncio
    async def test_full_oauth_flow_salesforce(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test complete OAuth flow for Salesforce integration."""
        oauth_client = ComposioOAuthClient()
        service = IntegrationService()

        # Mock Composio SDK for auth URL generation
        mock_composio = MagicMock()
        oauth_client._composio = mock_composio

        mock_config = MagicMock()
        mock_config.id = "auth-config-sfdc"
        mock_config.toolkit.slug = "salesforce"
        mock_list_response = MagicMock()
        mock_list_response.items = [mock_config]
        mock_composio.client.auth_configs.list.return_value = mock_list_response

        mock_link_response = MagicMock()
        mock_link_response.redirect_url = "https://login.salesforce.com/services/oauth2/authorize"
        mock_link_response.connected_account_id = "conn-sfdc-123"
        mock_composio.client.link.create.return_value = mock_link_response

        # Step 1: Generate auth URL with connection ID
        auth_url, connection_id = await oauth_client.generate_auth_url_with_connection_id(
            user_id="user-123",
            integration_type="salesforce",
            redirect_uri="http://localhost:5173/integrations/callback",
        )

        assert auth_url == "https://login.salesforce.com/services/oauth2/authorize"
        assert connection_id == "conn-sfdc-123"

        # Create integration
        mock_insert_response = MagicMock()
        mock_insert_response.data = [
            {
                "id": "int-sfdc-789",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "composio_connection_id": "conn-sfdc-123",
                "composio_account_id": "acct-sfdc-456",
                "display_name": "sales@example.com",
                "status": "active",
                "sync_status": "success",
                "last_sync_at": None,
                "error_message": None,
                "metadata": {},
                "created_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                "updated_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            }
        ]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_insert_response

        integration = await service.create_integration(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
            composio_connection_id=connection_id,
            display_name="sales@example.com",
        )

        assert integration["integration_type"] == "salesforce"
        assert integration["display_name"] == "sales@example.com"


class TestDisconnectFlow:
    """Tests for integration disconnection flow."""

    @pytest.mark.asyncio
    async def test_disconnect_flow_success(
        self,
        mock_supabase: MagicMock,
        mock_oauth_client: AsyncMock,
    ) -> None:
        """Test successful disconnection flow.

        Flow:
        1. User has existing integration
        2. Disconnect is requested
        3. Composio connection is closed
        4. Database record is deleted
        """
        service = IntegrationService()

        # Mock existing integration
        mock_get_response = MagicMock()
        mock_get_response.data = {
            "id": "int-123",
            "user_id": "user-123",
            "integration_type": "google_calendar",
            "composio_connection_id": "conn-abc123",
            "status": "active",
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_get_response

        result = await service.disconnect_integration("user-123", IntegrationType.GOOGLE_CALENDAR)

        assert result is True
        mock_oauth_client.disconnect_integration.assert_called_once_with("user-123", "conn-abc123")

    @pytest.mark.asyncio
    async def test_disconnect_flow_integration_not_found(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test disconnection when integration doesn't exist."""
        service = IntegrationService()

        # Mock no existing integration
        mock_get_response = MagicMock()
        mock_get_response.data = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_get_response

        with pytest.raises(Exception, match="Integration not found"):
            await service.disconnect_integration("user-123", IntegrationType.HUBSPOT)

    @pytest.mark.asyncio
    async def test_disconnect_flow_multiple_integrations(
        self,
        mock_supabase: MagicMock,
        mock_oauth_client: AsyncMock,
    ) -> None:
        """Test disconnecting multiple integrations sequentially."""
        service = IntegrationService()

        # Disconnect Google Calendar
        mock_get_response = MagicMock()
        mock_get_response.data = {
            "id": "int-gcal",
            "user_id": "user-123",
            "integration_type": "google_calendar",
            "composio_connection_id": "conn-gcal-123",
            "status": "active",
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_get_response

        result = await service.disconnect_integration("user-123", IntegrationType.GOOGLE_CALENDAR)
        assert result is True

        # Disconnect Gmail
        mock_get_response.data = {
            "id": "int-gmail",
            "user_id": "user-123",
            "integration_type": "gmail",
            "composio_connection_id": "conn-gmail-456",
            "status": "active",
        }

        result = await service.disconnect_integration("user-123", IntegrationType.GMAIL)
        assert result is True

        # Disconnect Salesforce
        mock_get_response.data = {
            "id": "int-sfdc",
            "user_id": "user-123",
            "integration_type": "salesforce",
            "composio_connection_id": "conn-sfdc-789",
            "status": "active",
        }

        result = await service.disconnect_integration("user-123", IntegrationType.SALESFORCE)
        assert result is True

        # Verify 3 disconnect calls
        assert mock_oauth_client.disconnect_integration.call_count == 3


class TestSyncFlow:
    """Tests for integration sync flow."""

    @pytest.mark.asyncio
    async def test_sync_flow_success(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test successful sync flow."""
        service = IntegrationService()

        # Mock update responses
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-123",
                "sync_status": "success",
                "last_sync_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            }
        ]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        result = await service.update_sync_status("int-123", SyncStatus.SUCCESS)

        assert result["sync_status"] == "success"

    @pytest.mark.asyncio
    async def test_trigger_sync_flow(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test triggering a manual sync."""
        service = IntegrationService()

        # Mock update responses for pending then success
        call_count = 0

        def mock_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                status_val = "pending"
            else:
                status_val = "success"

            mock_resp = MagicMock()
            mock_resp.data = [
                {
                    "id": "int-123",
                    "sync_status": status_val,
                    "last_sync_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                }
            ]
            return mock_resp

        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = mock_execute

        result = await service.trigger_sync("int-123")

        assert result["sync_status"] == "success"
        assert call_count == 2


class TestListIntegrations:
    """Tests for listing integrations."""

    @pytest.mark.asyncio
    async def test_list_user_integrations(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test listing all user integrations."""
        service = IntegrationService()

        # Mock existing integrations
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-1",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "status": "active",
                "display_name": "user@example.com",
                "composio_connection_id": "conn-1",
                "composio_account_id": "acct-1",
                "last_sync_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                "sync_status": "success",
                "error_message": None,
                "metadata": {},
                "created_at": datetime(2024, 1, 10, 9, 0, 0, tzinfo=UTC).isoformat(),
                "updated_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            },
            {
                "id": "int-2",
                "user_id": "user-123",
                "integration_type": "gmail",
                "status": "active",
                "display_name": "test@gmail.com",
                "composio_connection_id": "conn-2",
                "composio_account_id": "acct-2",
                "last_sync_at": datetime(2024, 1, 14, 10, 0, 0, tzinfo=UTC).isoformat(),
                "sync_status": "success",
                "error_message": None,
                "metadata": {},
                "created_at": datetime(2024, 1, 9, 9, 0, 0, tzinfo=UTC).isoformat(),
                "updated_at": datetime(2024, 1, 14, 10, 0, 0, tzinfo=UTC).isoformat(),
            },
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        integrations = await service.get_user_integrations("user-123")

        assert len(integrations) == 2
        integration_types = {i["integration_type"] for i in integrations}
        assert integration_types == {"google_calendar", "gmail"}

    @pytest.mark.asyncio
    async def test_list_available_integrations(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test listing available integrations with connection status."""
        service = IntegrationService()

        # Mock user has Google Calendar connected
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-1",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "status": "active",
                "display_name": "user@example.com",
                "composio_connection_id": "conn-1",
                "composio_account_id": "acct-1",
                "last_sync_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                "sync_status": "success",
                "error_message": None,
                "metadata": {},
                "created_at": datetime(2024, 1, 10, 9, 0, 0, tzinfo=UTC).isoformat(),
                "updated_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            }
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        available = await service.get_available_integrations("user-123")

        # Should return all defined integration types
        assert len(available) > 0

        # Check Google Calendar is connected
        gcal = next((i for i in available if i["integration_type"] == "google_calendar"), None)
        assert gcal is not None
        assert gcal["is_connected"] is True
        assert gcal["display_name"] == "Google Calendar"

        # Check Gmail is not connected
        gmail = next((i for i in available if i["integration_type"] == "gmail"), None)
        assert gmail is not None
        assert gmail["is_connected"] is False


class TestUpdateIntegration:
    """Tests for updating integration records."""

    @pytest.mark.asyncio
    async def test_update_integration_status(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test updating integration status."""
        service = IntegrationService()

        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-123",
                "status": "error",
                "error_message": "Sync failed",
            }
        ]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        result = await service.update_integration("int-123", {"status": "error", "error_message": "Sync failed"})

        assert result["status"] == "error"
        assert result["error_message"] == "Sync failed"

    @pytest.mark.asyncio
    async def test_update_integration_not_found(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test updating non-existent integration."""
        service = IntegrationService()

        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        with pytest.raises(Exception, match="Integration not found"):
            await service.update_integration("non-existent", {"status": "active"})


class TestDeleteIntegration:
    """Tests for deleting integration records."""

    @pytest.mark.asyncio
    async def test_delete_integration_success(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test deleting an integration record."""
        service = IntegrationService()

        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

        result = await service.delete_integration("int-123")

        assert result is True
