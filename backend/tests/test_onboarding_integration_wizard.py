"""Tests for the integration wizard service (US-909)."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.integration_wizard import (
    IntegrationPreferences,
    IntegrationStatus,
    IntegrationWizardService,
)


# --- Fixtures ---


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    """Build a fluent Supabase query chain ending in .execute()."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.maybe_single.return_value = chain
    chain.delete.return_value = chain
    chain.table.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    client = MagicMock()
    return client


@pytest.fixture()
def service(mock_db: MagicMock) -> IntegrationWizardService:
    """Create an IntegrationWizardService with mocked DB."""
    with patch("src.onboarding.integration_wizard.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        svc = IntegrationWizardService()
    return svc


@pytest.fixture()
def mock_oauth() -> MagicMock:
    """Create a mock Composio OAuth client."""
    oauth = MagicMock()
    oauth.generate_auth_url = AsyncMock(return_value="https://example.com/oauth")
    oauth.generate_auth_url_with_connection_id = AsyncMock(
        return_value=("https://example.com/oauth", "conn-new-123")
    )
    oauth.disconnect_integration = AsyncMock()
    return oauth


# --- get_integration_status ---


@pytest.mark.asyncio()
async def test_get_status_no_connections(
    service: IntegrationWizardService,
    mock_db: MagicMock,
) -> None:
    """Returns all integrations as disconnected when none are connected."""
    chain = _build_chain([])
    mock_db.table.return_value = chain

    with patch.object(
        service, "_get_preferences", new_callable=AsyncMock, return_value=IntegrationPreferences()
    ):
        status = await service.get_integration_status("user-123")

    assert len(status["crm"]) == 2  # Salesforce, HubSpot
    assert len(status["calendar"]) == 2  # Google Calendar, Outlook
    assert len(status["messaging"]) == 1  # Slack

    # All should be disconnected
    for integration in status["crm"] + status["calendar"] + status["messaging"]:
        assert integration["connected"] is False
        assert integration["connected_at"] is None

    # Verify default preferences
    assert status["preferences"]["slack_channels"] == []
    assert status["preferences"]["notification_enabled"] is True
    assert status["preferences"]["sync_frequency_hours"] == 1


@pytest.mark.asyncio()
async def test_get_status_with_connections(
    service: IntegrationWizardService,
    mock_db: MagicMock,
) -> None:
    """Returns connected status for connected integrations."""
    connected_data = [
        {
            "integration_type": "salesforce",
            "created_at": "2026-02-06T10:00:00+00:00",
            "composio_connection_id": "conn-123",
        },
        {
            "integration_type": "googlecalendar",
            "created_at": "2026-02-06T11:00:00+00:00",
            "composio_connection_id": "conn-456",
        },
    ]
    chain = _build_chain(connected_data)
    mock_db.table.return_value = chain

    with patch.object(
        service, "_get_preferences", new_callable=AsyncMock, return_value=IntegrationPreferences()
    ):
        status = await service.get_integration_status("user-123")

    # Check Salesforce is connected
    salesforce = next(i for i in status["crm"] if i["name"] == "SALESFORCE")
    assert salesforce["connected"] is True
    assert salesforce["connected_at"] == "2026-02-06T10:00:00+00:00"
    assert salesforce["connection_id"] == "conn-123"

    # Check Google Calendar is connected
    gcal = next(i for i in status["calendar"] if i["name"] == "GOOGLECALENDAR")
    assert gcal["connected"] is True
    assert gcal["connected_at"] == "2026-02-06T11:00:00+00:00"

    # HubSpot should be disconnected
    hubspot = next(i for i in status["crm"] if i["name"] == "HUBSPOT")
    assert hubspot["connected"] is False


# --- connect_integration ---


@pytest.mark.asyncio()
async def test_connect_salesflow_success(
    service: IntegrationWizardService,
    mock_oauth: MagicMock,
) -> None:
    """Successfully initiates OAuth for Salesforce."""
    with patch("src.onboarding.integration_wizard.get_oauth_client", return_value=mock_oauth):
        result = await service.connect_integration("user-123", "SALESFORCE")

    assert result["status"] == "pending"
    assert result["auth_url"] == "https://example.com/oauth"
    assert "connection_id" in result

    mock_oauth.generate_auth_url_with_connection_id.assert_called_once()


@pytest.mark.asyncio()
async def test_connect_invalid_app_name(
    service: IntegrationWizardService,
) -> None:
    """Returns error for unknown integration."""
    result = await service.connect_integration("user-123", "INVALID_APP")

    assert result["status"] == "error"
    assert "Unknown integration" in result["message"]


@pytest.mark.asyncio()
async def test_connect_oauth_error(
    service: IntegrationWizardService,
    mock_oauth: MagicMock,
) -> None:
    """Handles OAuth client errors gracefully."""
    mock_oauth.generate_auth_url_with_connection_id.side_effect = Exception("Composio error")

    with patch("src.onboarding.integration_wizard.get_oauth_client", return_value=mock_oauth):
        result = await service.connect_integration("user-123", "SLACK")

    assert result["status"] == "error"
    assert "Composio error" in result["message"]


# --- disconnect_integration ---


@pytest.mark.asyncio()
async def test_disconnect_success(
    service: IntegrationWizardService,
    mock_db: MagicMock,
    mock_oauth: MagicMock,
) -> None:
    """Successfully disconnects an integration."""
    # Mock the connection lookup
    connection_data = {
        "composio_connection_id": "conn-123",
    }
    select_chain = _build_chain(connection_data)
    # Mock the delete
    delete_chain = _build_chain(None)

    mock_db.table.side_effect = [select_chain, delete_chain]

    with patch("src.onboarding.integration_wizard.get_oauth_client", return_value=mock_oauth):
        result = await service.disconnect_integration("user-123", "SALESFORCE")

    assert result["status"] == "disconnected"
    mock_oauth.disconnect_integration.assert_called_once_with(
        user_id="user-123", connection_id="conn-123"
    )


@pytest.mark.asyncio()
async def test_disconnect_not_connected(
    service: IntegrationWizardService,
    mock_db: MagicMock,
) -> None:
    """Returns error when trying to disconnect non-connected integration."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    result = await service.disconnect_integration("user-123", "HUBSPOT")

    assert result["status"] == "error"
    assert "not connected" in result["message"].lower()


@pytest.mark.asyncio()
async def test_disconnect_invalid_app_name(
    service: IntegrationWizardService,
) -> None:
    """Returns error for unknown integration."""
    result = await service.disconnect_integration("user-123", "INVALID_APP")

    assert result["status"] == "error"
    assert "Unknown integration" in result["message"]


@pytest.mark.asyncio()
async def test_disconnect_composio_fallback(
    service: IntegrationWizardService,
    mock_db: MagicMock,
    mock_oauth: MagicMock,
) -> None:
    """Removes local record even if Composio disconnect fails."""
    connection_data = {"connection_id": "conn-123"}
    select_chain = _build_chain(connection_data)
    delete_chain = _build_chain(None)

    mock_db.table.side_effect = [select_chain, delete_chain]
    mock_oauth.disconnect_integration.side_effect = Exception("Composio down")

    with patch("src.onboarding.integration_wizard.get_oauth_client", return_value=mock_oauth):
        result = await service.disconnect_integration("user-123", "SALESFORCE")

    # Should still succeed despite Composio error
    assert result["status"] == "disconnected"


# --- save_integration_preferences ---


@pytest.mark.asyncio()
async def test_save_preferences(
    service: IntegrationWizardService,
    mock_db: MagicMock,
) -> None:
    """Saves preferences and updates readiness score."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    # Mock get_integration_status to return 2 connected integrations
    status_response = {
        "crm": [{"connected": True}, {"connected": False}],
        "calendar": [{"connected": True}, {"connected": False}],
        "messaging": [{"connected": False}],
        "preferences": IntegrationPreferences().model_dump(),
    }

    with patch.object(
        service, "get_integration_status", new_callable=AsyncMock, return_value=status_response
    ):
        with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.update_readiness_scores = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            with patch("src.memory.episodic.EpisodicMemory") as mock_memory_cls:
                mock_memory = MagicMock()
                mock_memory.store_episode = AsyncMock()
                mock_memory_cls.return_value = mock_memory

                preferences = IntegrationPreferences(
                    slack_channels=["#general"],
                    notification_enabled=False,
                    sync_frequency_hours=6,
                )
                result = await service.save_integration_preferences("user-123", preferences)

    assert result["status"] == "saved"
    assert result["connected_count"] == 2
    mock_orch.update_readiness_scores.assert_called_once_with(
        "user-123", {"integrations": 30.0}  # 2 * 15
    )


@pytest.mark.asyncio()
async def test_save_preferences_with_no_connections(
    service: IntegrationWizardService,
    mock_db: MagicMock,
) -> None:
    """Saves preferences with 0 connected integrations."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    status_response = {
        "crm": [{"connected": False}, {"connected": False}],
        "calendar": [{"connected": False}, {"connected": False}],
        "messaging": [{"connected": False}],
        "preferences": IntegrationPreferences().model_dump(),
    }

    with patch.object(
        service, "get_integration_status", new_callable=AsyncMock, return_value=status_response
    ):
        with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.update_readiness_scores = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            with patch("src.memory.episodic.EpisodicMemory") as mock_memory_cls:
                mock_memory = MagicMock()
                mock_memory.store_episode = AsyncMock()
                mock_memory_cls.return_value = mock_memory

                preferences = IntegrationPreferences()
                result = await service.save_integration_preferences("user-123", preferences)

    assert result["status"] == "saved"
    assert result["connected_count"] == 0
    mock_orch.update_readiness_scores.assert_called_once_with("user-123", {"integrations": 0.0})


# --- _get_preferences ---


@pytest.mark.asyncio()
async def test_get_preferences_default(
    service: IntegrationWizardService,
    mock_db: MagicMock,
) -> None:
    """Returns default preferences when none are set."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    prefs = await service._get_preferences("user-123")

    assert prefs.slack_channels == []
    assert prefs.notification_enabled is True
    assert prefs.sync_frequency_hours == 1


@pytest.mark.asyncio()
async def test_get_preferences_saved(
    service: IntegrationWizardService,
    mock_db: MagicMock,
) -> None:
    """Returns saved preferences from database."""
    data = {
        "integrations": {
            "slack_channels": ["#general", "#sales"],
            "notification_enabled": False,
            "sync_frequency_hours": 12,
        }
    }
    chain = _build_chain(data)
    mock_db.table.return_value = chain

    prefs = await service._get_preferences("user-123")

    assert prefs.slack_channels == ["#general", "#sales"]
    assert prefs.notification_enabled is False
    assert prefs.sync_frequency_hours == 12


# --- Integration constants ---


def test_integration_names() -> None:
    """Verify all expected integrations are defined."""
    expected = {
        "SALESFORCE",
        "HUBSPOT",
        "GOOGLECALENDAR",
        "OUTLOOK365CALENDAR",
        "SLACK",
    }
    assert set(IntegrationWizardService.INTEGRATIONS.keys()) == expected


def test_category_descriptions() -> None:
    """Each category has a description."""
    categories = ["crm", "calendar", "messaging"]
    for cat in categories:
        assert cat in IntegrationWizardService.CATEGORY_DESCRIPTIONS
        assert len(IntegrationWizardService.CATEGORY_DESCRIPTIONS[cat]) > 0
