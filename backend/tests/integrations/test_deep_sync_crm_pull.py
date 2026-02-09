"""Tests for Deep Sync CRM Pull functionality (US-942 Task 3)."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch early to break circular import
with patch("src.core.communication_router"):
    with patch("src.services.email_service"):
        with patch("src.services.notification_service"):
            from src.integrations.deep_sync import DeepSyncService, get_deep_sync_service
from src.integrations.deep_sync_domain import SyncConfig, SyncStatus
from src.integrations.domain import IntegrationType
from src.memory.lead_memory import LifecycleStage, LeadStatus, TriggerType


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client."""
    mock_client = MagicMock()

    # Mock table operations
    def mock_table_factory(table_name):
        mock_table = MagicMock()

        # For user_integrations query
        if table_name == "user_integrations":
            mock_response = MagicMock()
            mock_response.data = {
                "id": "integration-123",
                "composio_connection_id": "conn-123",
                "integration_type": "salesforce",
            }
            mock_table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_response

        # For insert operations
        mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])

        # For update operations
        mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])

        return mock_table

    mock_client.table = mock_table_factory
    mock_client.get_client.return_value = mock_client

    return mock_client


@pytest.fixture
def mock_oauth_client():
    """Mock OAuth client."""
    return AsyncMock()


@pytest.fixture
def mock_lead_memory_service():
    """Mock LeadMemoryService."""
    mock_service = AsyncMock()

    # Mock create method to return a lead-like object
    mock_lead = MagicMock()
    mock_lead.id = "lead-123"
    mock_service.create.return_value = mock_lead

    return mock_service


@pytest.fixture
def sync_service(
    mock_supabase_client,
    mock_oauth_client,
    mock_lead_memory_service,
):
    """Create a DeepSyncService instance with mocked dependencies."""
    with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_supabase_client):
        with patch("src.integrations.oauth.get_oauth_client", return_value=mock_oauth_client):
            with patch("src.memory.lead_memory.LeadMemoryService", return_value=mock_lead_memory_service):
                service = DeepSyncService(config=SyncConfig(sync_interval_minutes=15))
                # Override the injected instances
                service.supabase = type("obj", (object,), {"get_client": lambda: mock_supabase_client})
                service.integration_service = mock_oauth_client
                service.lead_memory_service = mock_lead_memory_service
                yield service


@pytest.mark.asyncio
async def test_deep_sync_service_singleton():
    """Test that get_deep_sync_service returns singleton instance."""
    with patch("src.core.communication_router"):
        with patch("src.services.email_service"):
            with patch("src.services.notification_service"):
                service1 = get_deep_sync_service()
                service2 = get_deep_sync_service()
                assert service1 is service2


@pytest.mark.asyncio
async def test_sync_crm_to_aria_salesforce(
    sync_service,
    mock_oauth_client,
    mock_lead_memory_service,
):
    """Test syncing opportunities from Salesforce to ARIA Lead Memory."""
    user_id = "user-123"
    integration_type = IntegrationType.SALESFORCE

    # Mock Composio actions
    mock_oauth_client.execute_action.side_effect = [
        # Opportunities response
        {
            "data": [
                {
                    "Id": "opp-1",
                    "Name": "Acme Corp Deal",
                    "StageName": "Proposal",
                    "Amount": 100000,
                    "CloseDate": "2025-06-30",
                    "Account": {"Name": "Acme Corp"},
                }
            ]
        },
        # Contacts response
        {"data": []},
        # Activities response
        {"data": []},
    ]

    # Execute sync
    result = await sync_service.sync_crm_to_aria(user_id, integration_type)

    # Verify result
    assert result.records_processed == 1
    assert result.records_succeeded == 1
    assert result.records_failed == 0
    assert result.status == SyncStatus.SUCCESS
    assert result.memory_entries_created == 1

    # Verify LeadMemoryService.create was called with correct parameters
    mock_lead_memory_service.create.assert_called_once()
    call_args = mock_lead_memory_service.create.call_args
    assert call_args[1]["user_id"] == user_id
    assert call_args[1]["company_name"] == "Acme Corp"
    assert call_args[1]["trigger"] == TriggerType.CRM_IMPORT
    assert call_args[1]["crm_id"] == "opp-1"
    assert call_args[1]["crm_provider"] == "salesforce"
    assert call_args[1]["expected_value"] == Decimal("100000")

    # Verify Composio actions were called
    assert mock_oauth_client.execute_action.call_count == 3


@pytest.mark.asyncio
async def test_sync_crm_to_aria_hubspot(
    sync_service,
    mock_oauth_client,
    mock_lead_memory_service,
):
    """Test syncing deals from HubSpot to ARIA Lead Memory."""
    user_id = "user-123"
    integration_type = IntegrationType.HUBSPOT

    # Override integration response for HubSpot
    def mock_table_factory(table_name):
        mock_table = MagicMock()
        mock_response = MagicMock()
        mock_response.data = {
            "id": "integration-456",
            "composio_connection_id": "conn-456",
            "integration_type": "hubspot",
        }
        mock_table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_response
        mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])
        mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])
        return mock_table

    sync_service.supabase = type("obj", (object,), {"get_client": lambda: MagicMock(table=mock_table_factory)})

    # Mock Composio actions
    mock_oauth_client.execute_action.side_effect = [
        # Deals response
        {
            "data": [
                {
                    "dealId": "deal-1",
                    "dealname": "TechStart Partnership",
                    "properties": {
                        "amount": "250000",
                        "closedate": "1751241600000",  # Timestamp
                        "dealstage": "presentation_scheduled",
                    },
                }
            ]
        },
        # Contacts response
        {"data": []},
        # Activities response
        {"data": []},
    ]

    # Execute sync
    result = await sync_service.sync_crm_to_aria(user_id, integration_type)

    # Verify result
    assert result.records_processed == 1
    assert result.records_succeeded == 1
    assert result.records_failed == 0
    assert result.status == SyncStatus.SUCCESS

    # Verify LeadMemoryService.create was called
    mock_lead_memory_service.create.assert_called_once()
    call_args = mock_lead_memory_service.create.call_args
    assert call_args[1]["crm_provider"] == "hubspot"
    assert call_args[1]["crm_id"] == "deal-1"


@pytest.mark.asyncio
async def test_sync_crm_to_aria_unsupported_integration(
    sync_service,
):
    """Test that unsupported integration types raise an error."""
    user_id = "user-123"
    integration_type = IntegrationType.GOOGLE_CALENDAR

    with pytest.raises(Exception) as exc_info:
        await sync_service.sync_crm_to_aria(user_id, integration_type)

    assert "Unsupported integration type for CRM sync" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sync_crm_to_aria_no_integration_found(
    sync_service,
):
    """Test sync when no integration is found for the user."""
    user_id = "user-123"
    integration_type = IntegrationType.SALESFORCE

    # Override to return no integration
    def mock_table_factory(table_name):
        mock_table = MagicMock()
        mock_response = MagicMock()
        mock_response.data = None
        mock_table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_response
        return mock_table

    sync_service.supabase = type("obj", (object,), {"get_client": lambda: MagicMock(table=mock_table_factory)})

    with pytest.raises(Exception) as exc_info:
        await sync_service.sync_crm_to_aria(user_id, integration_type)

    assert "No active salesforce integration found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sync_crm_to_aria_no_connection_id(
    sync_service,
):
    """Test sync when integration has no connection ID."""
    user_id = "user-123"
    integration_type = IntegrationType.SALESFORCE

    # Override to return integration without connection_id
    def mock_table_factory(table_name):
        mock_table = MagicMock()
        mock_response = MagicMock()
        mock_response.data = {"id": "integration-123", "integration_type": "salesforce", "composio_connection_id": None}
        mock_table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_response
        return mock_table

    sync_service.supabase = type("obj", (object,), {"get_client": lambda: MagicMock(table=mock_table_factory)})

    with pytest.raises(Exception) as exc_info:
        await sync_service.sync_crm_to_aria(user_id, integration_type)

    assert "No connection ID found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sync_crm_to_aria_partial_failure(
    sync_service,
    mock_oauth_client,
    mock_lead_memory_service,
):
    """Test sync when some records fail to process."""
    user_id = "user-123"
    integration_type = IntegrationType.SALESFORCE

    # Mock Composio actions - return multiple opportunities
    mock_oauth_client.execute_action.side_effect = [
        {
            "data": [
                {"Id": "opp-1", "Name": "Good Deal", "StageName": "Proposal"},
                {"Id": "opp-2", "Name": "Bad Deal", "StageName": "Prospecting"},
            ]
        },
        {"data": []},
        {"data": []},
    ]

    # Mock lead creation - first succeeds, second fails
    async def mock_create_side_effect(*args, **kwargs):
        crm_id = kwargs.get("crm_id")
        if crm_id == "opp-2":
            # Simulate failure
            from src.core.exceptions import LeadMemoryError
            raise LeadMemoryError("Database error")
        mock_lead = MagicMock()
        mock_lead.id = f"lead-{crm_id}"
        return mock_lead

    mock_lead_memory_service.create.side_effect = mock_create_side_effect

    # Execute sync
    result = await sync_service.sync_crm_to_aria(user_id, integration_type)

    # Verify partial success
    assert result.records_processed == 2
    assert result.records_succeeded == 1
    assert result.records_failed == 1
    assert result.status == SyncStatus.PARTIAL


@pytest.mark.asyncio
async def test_pull_contacts_stores_semantic_memory(
    sync_service,
    mock_oauth_client,
    mock_supabase_client,
):
    """Test that contacts are stored in semantic memory."""
    user_id = "user-123"
    integration_type = IntegrationType.SALESFORCE

    # Mock Composio actions
    mock_oauth_client.execute_action.side_effect = [
        {"data": []},  # No opportunities
        {
            "data": [
                {
                    "Id": "contact-1",
                    "FirstName": "John",
                    "LastName": "Doe",
                    "Title": "CTO",
                    "Email": "john@example.com",
                    "Account": {"Name": "Acme Corp"},
                }
            ]
        },
        {"data": []},  # No activities
    ]

    # Mock semantic memory insert
    def mock_table_factory_with_memory(table_name):
        mock_table = MagicMock()

        if table_name == "user_integrations":
            mock_response = MagicMock()
            mock_response.data = {
                "id": "integration-123",
                "composio_connection_id": "conn-123",
                "integration_type": "salesforce",
            }
            mock_table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_response
        elif table_name == "memory_semantic":
            mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "memory-123"}])
        else:
            mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])
            mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])

        return mock_table

    sync_service.supabase = type("obj", (object,), {"get_client": lambda: MagicMock(table=mock_table_factory_with_memory)})

    # Mock SemanticMemory to avoid Neo4j connection
    mock_semantic = MagicMock()
    mock_semantic.add_fact = AsyncMock(return_value="memory-123")

    with patch("src.memory.semantic.SemanticMemory", return_value=mock_semantic):
        # Execute sync
        result = await sync_service.sync_crm_to_aria(user_id, integration_type)

    # Verify contact was stored
    assert result.records_processed == 1
    assert result.records_succeeded == 1


@pytest.mark.asyncio
async def test_pull_activities_stores_episodic_memory(
    sync_service,
    mock_oauth_client,
    mock_supabase_client,
):
    """Test that activities are stored as episodic memories."""
    user_id = "user-123"
    integration_type = IntegrationType.SALESFORCE

    # Mock Composio actions
    mock_oauth_client.execute_action.side_effect = [
        {"data": []},  # No opportunities
        {"data": []},  # No contacts
        {
            "data": [
                {
                    "Id": "task-1",
                    "Subject": "Follow-up call",
                    "ActivityDate": "2025-02-01",
                    "Description": "Discussed pricing options",
                    "Account": {"Name": "Acme Corp"},
                }
            ]
        },
    ]

    # Mock episodic memory insert
    def mock_table_factory_with_memory(table_name):
        mock_table = MagicMock()

        if table_name == "user_integrations":
            mock_response = MagicMock()
            mock_response.data = {
                "id": "integration-123",
                "composio_connection_id": "conn-123",
                "integration_type": "salesforce",
            }
            mock_table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_response
        elif table_name == "episodic_memories":
            mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "episodic-123"}])
        else:
            mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])
            mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])

        return mock_table

    sync_service.supabase = type("obj", (object,), {"get_client": lambda: MagicMock(table=mock_table_factory_with_memory)})

    # Mock EpisodicMemory to avoid Neo4j connection
    mock_episodic = MagicMock()
    mock_episodic.store_episode = AsyncMock(return_value="episodic-123")

    with patch("src.memory.episodic.EpisodicMemory", return_value=mock_episodic):
        # Execute sync
        result = await sync_service.sync_crm_to_aria(user_id, integration_type)

    # Verify activity was stored
    assert result.records_processed == 1
    assert result.records_succeeded == 1


@pytest.mark.asyncio
async def test_map_opportunity_to_crm_entity_salesforce(sync_service):
    """Test mapping Salesforce opportunity to CRMEntity."""
    data = {
        "Id": "opp-123",
        "Name": "Test Deal",
        "StageName": "Negotiation",
        "Amount": 50000,
    }

    entity = sync_service._map_opportunity_to_crm_entity(
        data=data,
        integration_type=IntegrationType.SALESFORCE,
    )

    assert entity.entity_type == "opportunity"
    assert entity.external_id == "opp-123"
    assert entity.name == "Test Deal"
    assert entity.confidence == 0.85
    assert entity.data == data


@pytest.mark.asyncio
async def test_map_opportunity_to_crm_entity_hubspot(sync_service):
    """Test mapping HubSpot deal to CRMEntity."""
    data = {
        "dealId": "deal-456",
        "dealname": "HubSpot Deal",
        "properties": {"amount": "75000"},
    }

    entity = sync_service._map_opportunity_to_crm_entity(
        data=data,
        integration_type=IntegrationType.HUBSPOT,
    )

    assert entity.entity_type == "opportunity"
    assert entity.external_id == "deal-456"
    assert entity.name == "HubSpot Deal"


@pytest.mark.asyncio
async def test_map_contact_to_crm_entity(sync_service):
    """Test mapping contact to CRMEntity."""
    data = {
        "Id": "contact-789",
        "Name": "Jane Smith",
    }

    entity = sync_service._map_contact_to_crm_entity(
        data=data,
        integration_type=IntegrationType.SALESFORCE,
    )

    assert entity.entity_type == "contact"
    assert entity.external_id == "contact-789"
    assert entity.name == "Jane Smith"


@pytest.mark.asyncio
async def test_map_activity_to_crm_entity(sync_service):
    """Test mapping activity to CRMEntity."""
    data = {
        "Id": "task-101",
        "Subject": "Email follow-up",
    }

    entity = sync_service._map_activity_to_crm_entity(
        data=data,
        integration_type=IntegrationType.SALESFORCE,
    )

    assert entity.entity_type == "activity"
    assert entity.external_id == "task-101"
    assert entity.name == "Email follow-up"
