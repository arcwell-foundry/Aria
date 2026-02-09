"""Tests for email integration onboarding step (US-907)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.email_integration import (
    EmailIntegrationConfig,
    EmailIntegrationService,
    PrivacyExclusion,
)


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    db = MagicMock()
    db.table = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create EmailIntegrationService with mocked dependencies."""
    with patch("src.onboarding.email_integration.SupabaseClient.get_client", return_value=mock_db):
        return EmailIntegrationService()


@pytest.mark.asyncio
async def test_initiate_oauth_generates_url_for_gmail(service):
    """initiate_oauth generates correct OAuth URL for Gmail provider."""
    # Mock the OAuth client
    mock_oauth = MagicMock()
    mock_oauth.generate_auth_url_with_connection_id = AsyncMock(
        return_value=("https://auth.composio.dev/authorize?code=test_gmail_url", "conn-123")
    )

    with patch(
        "src.onboarding.email_integration.get_oauth_client",
        return_value=mock_oauth,
    ):
        result = await service.initiate_oauth("user-123", "google")

        assert result["status"] == "pending"
        assert result["auth_url"] == "https://auth.composio.dev/authorize?code=test_gmail_url"
        assert "connection_id" in result
        mock_oauth.generate_auth_url_with_connection_id.assert_called_once()


@pytest.mark.asyncio
async def test_initiate_oauth_generates_url_for_outlook(service):
    """initiate_oauth generates correct OAuth URL for Outlook/Microsoft provider."""
    mock_oauth = MagicMock()
    mock_oauth.generate_auth_url_with_connection_id = AsyncMock(
        return_value=("https://auth.composio.dev/authorize?code=test_outlook_url", "conn-456")
    )

    with patch(
        "src.onboarding.email_integration.get_oauth_client",
        return_value=mock_oauth,
    ):
        result = await service.initiate_oauth("user-456", "microsoft")

        assert result["status"] == "pending"
        assert result["auth_url"] == "https://auth.composio.dev/authorize?code=test_outlook_url"


@pytest.mark.asyncio
async def test_initiate_oauth_handles_errors_gracefully(service):
    """initiate_oauth handles errors gracefully and returns error status."""
    mock_oauth = MagicMock()
    mock_oauth.generate_auth_url = AsyncMock(side_effect=Exception("Composio API error"))

    with patch(
        "src.onboarding.email_integration.get_oauth_client",
        return_value=mock_oauth,
    ):
        result = await service.initiate_oauth("user-789", "google")

        assert result["status"] == "error"
        assert "message" in result
        assert result["auth_url"] == ""


@pytest.mark.asyncio
async def test_check_connection_status_returns_connected(service, mock_db):
    """check_connection_status returns True for connected user."""
    # Mock DB response with existing connection
    mock_response = MagicMock()
    mock_response.data = {
        "id": "conn-123",
        "provider": "google",
        "created_at": "2026-02-01T00:00:00Z",
    }
    mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        mock_response
    )

    result = await service.check_connection_status("user-123", "google")

    assert result["connected"] is True
    assert result["provider"] == "google"
    assert "connected_at" in result


@pytest.mark.asyncio
async def test_check_connection_status_returns_disconnected(service, mock_db):
    """check_connection_status returns False for disconnected user."""
    # Create fresh mocks for the chain to avoid state from previous tests
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_eq2 = MagicMock()
    mock_maybe = MagicMock()
    mock_execute = MagicMock()

    # Set up the chain: table().select().eq().eq().maybe_single().execute()
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.eq.return_value = mock_eq2
    mock_eq2.maybe_single.return_value = mock_maybe
    mock_maybe.execute.return_value = None  # No connection found

    mock_db.table.return_value = mock_table

    result = await service.check_connection_status("user-456", "microsoft")

    assert result["connected"] is False
    assert result["provider"] == "microsoft"


@pytest.mark.asyncio
async def test_save_privacy_config_saves_to_user_settings(service, mock_db):
    """save_privacy_config saves privacy configuration to user_settings table."""
    config = EmailIntegrationConfig(
        provider="google",
        scopes=["gmail.readonly"],
        privacy_exclusions=[
            PrivacyExclusion(type="sender", value="personal@gmail.com"),
            PrivacyExclusion(type="domain", value="bank.com"),
        ],
        ingestion_scope_days=365,
        attachment_ingestion=False,
    )

    # Mock the select chain for reading existing settings
    mock_existing_response = MagicMock()
    mock_existing_response.data = {"integrations": {}}
    mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_existing_response

    # Mock DB upsert
    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    # Mock orchestrator for readiness update
    with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch:
        mock_orch.return_value.update_readiness_scores = AsyncMock()

        # Mock episodic memory
        with patch("src.memory.episodic.EpisodicMemory"):
            result = await service.save_privacy_config("user-123", config)

            assert result["status"] == "saved"
            assert result["exclusions"] == 2

            # Verify upsert was called with correct data
            call_args = mock_db.table.return_value.upsert.call_args[0][0]
            assert call_args["user_id"] == "user-123"
            assert "integrations" in call_args
            assert call_args["integrations"]["email"]["provider"] == "google"


@pytest.mark.asyncio
async def test_save_privacy_config_updates_readiness_scores(service, mock_db):
    """save_privacy_config updates relationship_graph and digital_twin readiness scores."""
    config = EmailIntegrationConfig(
        provider="microsoft",
        scopes=["Mail.Read"],
        privacy_exclusions=[],
        ingestion_scope_days=180,
        attachment_ingestion=False,
    )

    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch:
        mock_orch_instance = MagicMock()
        mock_orch_instance.update_readiness_scores = AsyncMock()
        mock_orch.return_value = mock_orch_instance

        with patch("src.memory.episodic.EpisodicMemory"):
            await service.save_privacy_config("user-123", config)

            # Verify readiness scores were updated
            mock_orch_instance.update_readiness_scores.assert_called_once()
            call_args = mock_orch_instance.update_readiness_scores.call_args[0][1]
            assert "relationship_graph" in call_args
            assert "digital_twin" in call_args


@pytest.mark.asyncio
async def test_save_privacy_config_records_episodic_memory(service, mock_db):
    """save_privacy_config records the event in episodic memory."""
    config = EmailIntegrationConfig(
        provider="google",
        scopes=["gmail.readonly"],
        privacy_exclusions=[PrivacyExclusion(type="category", value="medical")],
        ingestion_scope_days=365,
        attachment_ingestion=False,
    )

    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch:
        mock_orch.return_value.update_readiness_scores = AsyncMock()

        with patch("src.memory.episodic.EpisodicMemory") as mock_memory:
            mock_instance = MagicMock()
            mock_instance.store_episode = AsyncMock()
            mock_memory.return_value = mock_instance

            await service.save_privacy_config("user-123", config)

            # Verify episodic memory was called
            mock_instance.store_episode.assert_called_once()
            call_args = mock_instance.store_episode.call_args[0][0]
            assert call_args.user_id == "user-123"
            assert call_args.event_type == "onboarding_email_connected"
            assert "exclusions_count" in call_args.context
