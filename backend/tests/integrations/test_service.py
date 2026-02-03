"""Tests for integration service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.domain import (
    Integration,
    IntegrationStatus,
    IntegrationType,
    SyncStatus,
)
from src.integrations.service import IntegrationService, get_integration_service


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


class TestIntegrationServiceSingleton:
    """Tests for get_integration_service singleton."""

    def test_get_integration_service_singleton(self) -> None:
        """Test that get_integration_service returns singleton instance."""
        service1 = get_integration_service()
        service2 = get_integration_service()
        assert service1 is service2


class TestGetUserIntegrations:
    """Tests for get_user_integrations method."""

    @pytest.mark.asyncio
    async def test_get_user_integrations_empty(self, mock_supabase: AsyncMock) -> None:
        """Test retrieving user integrations when none exist."""
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        integrations = await service.get_user_integrations("user-123")

        assert len(integrations) == 0

    @pytest.mark.asyncio
    async def test_get_user_integrations_with_data(self, mock_supabase: AsyncMock) -> None:
        """Test retrieving user integrations with existing integrations."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-1",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "status": "active",
                "display_name": "user@example.com",
                "composio_connection_id": "conn-123",
                "composio_account_id": "acct-123",
                "last_sync_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                "sync_status": "success",
                "error_message": None,
                "metadata": {},
                "created_at": datetime(2024, 1, 10, 9, 0, 0, tzinfo=UTC).isoformat(),
                "updated_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            }
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        integrations = await service.get_user_integrations("user-123")

        assert len(integrations) == 1
        assert integrations[0]["integration_type"] == "google_calendar"


class TestGetIntegration:
    """Tests for get_integration method."""

    @pytest.mark.asyncio
    async def test_get_integration_found(self, mock_supabase: AsyncMock) -> None:
        """Test getting a specific integration that exists."""
        mock_response = MagicMock()
        mock_response.data = {
            "id": "int-1",
            "user_id": "user-123",
            "integration_type": "google_calendar",
            "status": "active",
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        integration = await service.get_integration("user-123", IntegrationType.GOOGLE_CALENDAR)

        assert integration is not None
        assert integration["integration_type"] == "google_calendar"

    @pytest.mark.asyncio
    async def test_get_integration_not_found(self, mock_supabase: AsyncMock) -> None:
        """Test getting a specific integration that doesn't exist."""
        mock_response = MagicMock()
        mock_response.data = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        integration = await service.get_integration("user-123", IntegrationType.GMAIL)

        assert integration is None


class TestCreateIntegration:
    """Tests for create_integration method."""

    @pytest.mark.asyncio
    async def test_create_integration_success(self, mock_supabase: AsyncMock) -> None:
        """Test creating an integration connection."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-1",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "status": "active",
                "composio_connection_id": "conn-123",
            }
        ]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_response

        service = IntegrationService()
        result = await service.create_integration(
            user_id="user-123",
            integration_type=IntegrationType.GOOGLE_CALENDAR,
            composio_connection_id="conn-123",
            display_name="user@example.com",
        )

        assert result["integration_type"] == "google_calendar"
        assert result["composio_connection_id"] == "conn-123"


class TestGetAvailableIntegrations:
    """Tests for get_available_integrations method."""

    @pytest.mark.asyncio
    async def test_get_available_integrations(self, mock_supabase: AsyncMock) -> None:
        """Test getting available integrations with connection status."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-1",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "status": "active",
            }
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        available = await service.get_available_integrations("user-123")

        # Should return all integration types with connection status
        assert len(available) > 0
        google_calendar = next((i for i in available if i["integration_type"] == "google_calendar"), None)
        assert google_calendar is not None
        assert google_calendar["is_connected"] is True


class TestDisconnectIntegration:
    """Tests for disconnect_integration method."""

    @pytest.mark.asyncio
    async def test_disconnect_integration_success(
        self, mock_supabase: AsyncMock, mock_oauth_client: AsyncMock
    ) -> None:
        """Test disconnecting an integration."""
        mock_response = MagicMock()
        mock_response.data = {
            "id": "int-1",
            "composio_connection_id": "conn-123",
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        result = await service.disconnect_integration(
            user_id="user-123", integration_type=IntegrationType.GOOGLE_CALENDAR
        )

        assert result is True
        mock_oauth_client.disconnect_integration.assert_called_once_with("conn-123")


class TestUpdateSyncStatus:
    """Tests for update_sync_status method."""

    @pytest.mark.asyncio
    async def test_update_sync_status_success(self, mock_supabase: AsyncMock) -> None:
        """Test updating sync status."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-1",
                "sync_status": "success",
                "last_sync_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            }
        ]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        result = await service.update_sync_status("int-1", SyncStatus.SUCCESS)

        assert result["sync_status"] == "success"


class TestTriggerSync:
    """Tests for trigger_sync method."""

    @pytest.mark.asyncio
    async def test_trigger_sync_success(self, mock_supabase: AsyncMock) -> None:
        """Test triggering a manual sync."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "int-1",
                "sync_status": "success",
            }
        ]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        service = IntegrationService()
        result = await service.trigger_sync("int-1")

        assert result["sync_status"] == "success"
