"""Test push sync functionality (US-942 Task 5).

These tests verify:
1. Push items can be queued for user approval
2. Push items expire after 7 days
3. Approved items are processed correctly
4. Failed items are marked properly
5. Create note action works for Salesforce and HubSpot
6. Update field action works for CRM lead scores
7. Create event action works for calendar integrations
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# Import directly to avoid circular import issues through __init__.py
import src.integrations.deep_sync
from src.integrations.deep_sync_domain import (
    PushActionType,
    PushPriority,
    PushQueueItem,
)
from src.integrations.domain import IntegrationType


class MockSupabaseClient:
    """Mock Supabase client that tracks table access."""

    def __init__(self) -> None:
        self.tables: dict[str, MagicMock] = {}
        self._insert_data: list[dict] = []
        self._update_data: list[tuple[dict, str]] = []  # (data, eq_filter)
        self._approved_items: list[dict] = []
        self._user_integration_data: dict | None = None

    def get_client(self) -> "MockSupabaseClient":
        """Return self to match SupabaseClient interface."""
        return self

    def set_approved_items(self, items: list[dict]) -> None:
        """Set the approved items to return."""
        self._approved_items = items

    def set_user_integration(self, data: dict) -> None:
        """Set the user integration data."""
        self._user_integration_data = data

    def table(self, table_name: str) -> MagicMock:
        """Get or create a mock table."""
        if table_name not in self.tables:
            mock_table = MagicMock()
            self.tables[table_name] = mock_table

            # Set up different chains based on table type
            if table_name == "integration_push_queue":
                self._setup_push_queue_table(mock_table)
            elif table_name == "user_integrations":
                self._setup_user_integrations_table(mock_table)

        return self.tables[table_name]

    def _setup_push_queue_table(self, mock_table: MagicMock) -> None:
        """Set up integration_push_queue table mock."""

        # Insert chain
        def mock_insert(data: dict) -> MagicMock:
            self._insert_data.append(data)
            result = MagicMock()
            result.execute.return_value = MagicMock(data=[{"id": "queue-123"}])
            return result

        mock_table.insert = MagicMock(side_effect=mock_insert)

        # Select -> eq -> eq -> eq -> order -> execute chain
        mock_select_result = MagicMock()

        # First eq() returns a chain that supports multiple eq() calls
        mock_eq1_result = MagicMock()

        # Second eq() result
        mock_eq2_result = MagicMock()

        # Third eq() result
        mock_eq3_result = MagicMock()

        # order() result
        mock_order_result = MagicMock()
        mock_order_result.execute.return_value = MagicMock(data=self._approved_items)

        # Wire up the chain
        def mock_eq_handler(_: str, __: Any) -> MagicMock:
            """Handle eq calls - return the next level."""
            # For simplicity, we return the same object that has order
            result = MagicMock()
            result.order = MagicMock(return_value=mock_order_result)
            return result

        mock_eq1_result.eq = MagicMock(side_effect=mock_eq_handler)

        # The select returns the first eq result
        mock_select_result.eq = MagicMock(return_value=mock_eq1_result)

        mock_table.select = MagicMock(return_value=mock_select_result)

        # Update -> eq -> execute chain
        def mock_update(data: dict) -> MagicMock:
            def mock_eq_filter(_: str, __: Any) -> MagicMock:
                result = MagicMock()
                result.execute.return_value = MagicMock(data=[])
                return result

            mock_eq = MagicMock()
            mock_eq.eq = MagicMock(side_effect=mock_eq_filter)
            return mock_eq

        mock_table.update = MagicMock(side_effect=mock_update)

    def _setup_user_integrations_table(self, mock_table: MagicMock) -> None:
        """Set up user_integrations table mock."""

        # Select -> eq -> eq -> maybe_single -> execute chain
        def mock_select_fields(*_args: Any) -> MagicMock:
            mock_eq1 = MagicMock()

            def mock_eq1_filter(_: str, __: Any) -> MagicMock:
                mock_eq2 = MagicMock()

                def mock_eq2_filter(_: str, __: Any) -> MagicMock:
                    result = MagicMock()
                    result.execute.return_value = MagicMock(
                        data=self._user_integration_data
                        or {
                            "id": "integration-123",
                            "user_id": "user-123",
                            "integration_type": "salesforce",
                            "composio_connection_id": "conn-123",
                            "status": "active",
                        }
                    )
                    result.maybe_single = MagicMock(return_value=result)
                    return result

                mock_eq2.eq = MagicMock(side_effect=mock_eq2_filter)
                return mock_eq2

            mock_eq1.eq = MagicMock(side_effect=mock_eq1_filter)
            return mock_eq1

        mock_table.select = MagicMock(side_effect=mock_select_fields)

    def get_insert_calls(self) -> list[dict]:
        """Get all insert call data."""
        return self._insert_data

    def get_update_calls(self) -> list[tuple[dict, str]]:
        """Get all update call data."""
        return self._update_data


@pytest.fixture
def mock_supabase_client() -> MockSupabaseClient:
    """Create a mocked Supabase client for testing."""
    return MockSupabaseClient()


@pytest.fixture
def mock_oauth_client() -> MagicMock:
    """Create a mocked OAuth client for testing."""
    mock_client = MagicMock()
    mock_client.execute_action = AsyncMock(return_value={"data": {"success": True}})
    return mock_client


@pytest.fixture
def deep_sync_service(
    mock_supabase_client: MagicMock,
    mock_oauth_client: MagicMock,
) -> src.integrations.deep_sync.DeepSyncService:
    """Create a DeepSyncService instance with mocked dependencies."""
    service = src.integrations.deep_sync.DeepSyncService()

    # Replace with mocks
    service.supabase = mock_supabase_client
    service.integration_service = mock_oauth_client

    yield service


class TestQueuePushItem:
    """Test push item queuing."""

    @pytest.mark.asyncio
    async def test_queue_push_item(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_supabase_client: MockSupabaseClient,
    ) -> None:
        """Should queue push item and return queue_id."""
        item = PushQueueItem(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
            action_type=PushActionType.CREATE_NOTE,
            priority=PushPriority.HIGH,
            payload={
                "parentId": "opp-123",
                "title": "ARIA Analysis",
                "body": "Lead score updated to 85",
            },
        )

        queue_id = await deep_sync_service.queue_push_item(item)

        # Verify insert was called
        assert queue_id is not None

        # Verify the insert data
        insert_calls = mock_supabase_client.get_insert_calls()
        assert len(insert_calls) == 1

        insert_data = insert_calls[0]
        assert insert_data["user_id"] == "user-123"
        assert insert_data["integration_type"] == "salesforce"
        assert insert_data["action_type"] == "create_note"
        assert insert_data["priority"] == "high"
        assert insert_data["priority_int"] == 3  # HIGH = 3
        assert insert_data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_queue_push_item_expires_in_7_days(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_supabase_client: MockSupabaseClient,
    ) -> None:
        """Should set expiration to 7 days from now."""
        now = datetime.now(UTC)
        expected_expires = now + timedelta(days=7)

        item = PushQueueItem(
            user_id="user-123",
            integration_type=IntegrationType.HUBSPOT,
            action_type=PushActionType.UPDATE_FIELD,
            priority=PushPriority.MEDIUM,
            payload={"entityId": "deal-456", "field_value": 92},
        )

        await deep_sync_service.queue_push_item(item)

        # Verify expires_at is set
        insert_calls = mock_supabase_client.get_insert_calls()
        insert_data = insert_calls[-1]  # Get the last call

        expires_at = datetime.fromisoformat(insert_data["expires_at"])

        # Should be approximately 7 days from now (within 1 minute tolerance)
        time_diff = abs((expires_at - expected_expires).total_seconds())
        assert time_diff < 60  # Within 1 minute

    @pytest.mark.asyncio
    async def test_queue_push_item_priority_mapping(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_supabase_client: MockSupabaseClient,
    ) -> None:
        """Should map priority enums to integers correctly."""
        # Test CRITICAL priority
        critical_item = PushQueueItem(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
            action_type=PushActionType.CREATE_NOTE,
            priority=PushPriority.CRITICAL,
            payload={},
        )
        await deep_sync_service.queue_push_item(critical_item)

        insert_calls = mock_supabase_client.get_insert_calls()
        assert insert_calls[0]["priority_int"] == 4

        # Test LOW priority
        low_item = PushQueueItem(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
            action_type=PushActionType.CREATE_NOTE,
            priority=PushPriority.LOW,
            payload={},
        )
        await deep_sync_service.queue_push_item(low_item)

        # Check the last call for LOW priority
        insert_calls = mock_supabase_client.get_insert_calls()
        assert insert_calls[-1]["priority_int"] == 1


class TestProcessApprovedPushItems:
    """Test processing of approved push items."""

    @pytest.mark.asyncio
    async def test_process_approved_push_items(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_supabase_client: MockSupabaseClient,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should process approved items and mark as completed."""
        # Mock approved items
        approved_items = [
            {
                "id": "queue-1",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "action_type": "create_note",
                "priority": "high",
                "priority_int": 3,
                "payload": {
                    "parentId": "opp-123",
                    "title": "Note 1",
                    "body": "Body 1",
                },
                "status": "approved",
            },
            {
                "id": "queue-2",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "action_type": "update_field",
                "priority": "medium",
                "priority_int": 2,
                "payload": {
                    "entityId": "opp-123",
                    "field_value": 85,
                },
                "status": "approved",
            },
        ]

        # Use a direct mock for the Supabase client that properly chains
        client = deep_sync_service.supabase.get_client()

        # Create a more complete mock chain for the integration_push_queue table
        push_queue_table = MagicMock()

        # Set up the select chain
        select_result = MagicMock()
        eq_result1 = MagicMock()
        eq_result2 = MagicMock()
        eq_result3 = MagicMock()
        order_result = MagicMock()
        execute_result = MagicMock()
        execute_result.data = approved_items

        # Wire up the chain
        order_result.execute = MagicMock(return_value=execute_result)
        eq_result3.order = MagicMock(return_value=order_result)
        eq_result2.eq = MagicMock(return_value=eq_result3)
        eq_result1.eq = MagicMock(return_value=eq_result2)
        select_result.eq = MagicMock(return_value=eq_result1)
        push_queue_table.select = MagicMock(return_value=select_result)

        # Set up update chain
        update_result = MagicMock()
        update_eq_result = MagicMock()
        update_execute_result = MagicMock()
        update_execute_result.data = []
        update_eq_result.execute = MagicMock(return_value=update_execute_result)
        update_result.eq = MagicMock(return_value=update_eq_result)
        push_queue_table.update = MagicMock(return_value=update_result)

        # Make the table() method return our mocked table
        original_table = client.table

        def table_side_effect(table_name: str):
            if table_name == "integration_push_queue":
                return push_queue_table
            return original_table(table_name)

        client.table = MagicMock(side_effect=table_side_effect)

        # Execute
        result = await deep_sync_service.process_approved_push_items(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
        )

        # Verify result
        assert result.records_processed == 2
        assert result.records_succeeded == 2
        assert result.records_failed == 0
        assert result.push_queue_items == 2

        # Verify items were marked as completed (update should be called twice)
        assert push_queue_table.update.call_count == 2

    @pytest.mark.asyncio
    async def test_process_approved_push_items_handles_failures(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_supabase_client: MockSupabaseClient,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should mark failed items properly."""
        # Mock approved items (one will fail)
        approved_items = [
            {
                "id": "queue-1",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "action_type": "create_note",
                "priority": "high",
                "priority_int": 3,
                "payload": {"parentId": "opp-123", "title": "Note 1", "body": "Body 1"},
                "status": "approved",
            },
            {
                "id": "queue-2",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "action_type": "create_note",
                "priority": "high",
                "priority_int": 3,
                "payload": {"parentId": "opp-456", "title": "Note 2", "body": "Body 2"},
                "status": "approved",
            },
        ]

        # Use a direct mock for the Supabase client that properly chains
        client = deep_sync_service.supabase.get_client()

        # Create a more complete mock chain for the integration_push_queue table
        push_queue_table = MagicMock()

        # Set up the select chain
        select_result = MagicMock()
        eq_result1 = MagicMock()
        eq_result2 = MagicMock()
        eq_result3 = MagicMock()
        order_result = MagicMock()
        execute_result = MagicMock()
        execute_result.data = approved_items

        # Wire up the chain
        order_result.execute = MagicMock(return_value=execute_result)
        eq_result3.order = MagicMock(return_value=order_result)
        eq_result2.eq = MagicMock(return_value=eq_result3)
        eq_result1.eq = MagicMock(return_value=eq_result2)
        select_result.eq = MagicMock(return_value=eq_result1)
        push_queue_table.select = MagicMock(return_value=select_result)

        # Set up update chain
        update_result = MagicMock()
        update_eq_result = MagicMock()
        update_execute_result = MagicMock()
        update_execute_result.data = []
        update_eq_result.execute = MagicMock(return_value=update_execute_result)
        update_result.eq = MagicMock(return_value=update_eq_result)
        push_queue_table.update = MagicMock(return_value=update_result)

        # Make the table() method return our mocked table
        original_table = client.table

        def table_side_effect(table_name: str):
            if table_name == "integration_push_queue":
                return push_queue_table
            return original_table(table_name)

        client.table = MagicMock(side_effect=table_side_effect)

        # Mock execute_action to fail for second item
        call_count = 0

        async def mock_execute_action(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("API rate limit exceeded")
            return {"data": {"success": True}}

        mock_oauth_client.execute_action = AsyncMock(side_effect=mock_execute_action)

        # Execute
        result = await deep_sync_service.process_approved_push_items(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
        )

        # Verify result
        assert result.records_processed == 2
        assert result.records_succeeded == 1
        assert result.records_failed == 1

        # Verify failed item was marked with error
        update_calls = push_queue_table.update.call_args_list

        # One of the updates should have status="failed"
        failed_found = False
        for call in update_calls:
            if call and call[0] and call[0][0].get("status") == "failed":
                failed_found = True
                assert "error_message" in call[0][0]
                break

        assert failed_found, "Failed item not marked properly"

    @pytest.mark.asyncio
    async def test_process_approved_push_items_orders_by_priority(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_supabase_client: MockSupabaseClient,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should process items in priority order (high to low)."""
        # Mock approved items with mixed priorities
        approved_items = [
            {
                "id": "queue-1",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "action_type": "create_note",
                "priority": "medium",
                "priority_int": 2,
                "payload": {"parentId": "opp-1", "title": "Medium", "body": "Body"},
                "status": "approved",
            },
            {
                "id": "queue-2",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "action_type": "create_note",
                "priority": "high",
                "priority_int": 3,
                "payload": {"parentId": "opp-2", "title": "High", "body": "Body"},
                "status": "approved",
            },
            {
                "id": "queue-3",
                "user_id": "user-123",
                "integration_type": "salesforce",
                "action_type": "create_note",
                "priority": "low",
                "priority_int": 1,
                "payload": {"parentId": "opp-3", "title": "Low", "body": "Body"},
                "status": "approved",
            },
        ]

        # Use a direct mock for the Supabase client that properly chains
        client = deep_sync_service.supabase.get_client()

        # Create a more complete mock chain for the integration_push_queue table
        push_queue_table = MagicMock()

        # Set up the select chain with tracking for order call
        select_result = MagicMock()
        eq_result1 = MagicMock()
        eq_result2 = MagicMock()
        eq_result3 = MagicMock()
        order_result = MagicMock()
        execute_result = MagicMock()
        execute_result.data = approved_items

        # Wire up the chain
        order_result.execute = MagicMock(return_value=execute_result)
        eq_result3.order = MagicMock(return_value=order_result)
        eq_result2.eq = MagicMock(return_value=eq_result3)
        eq_result1.eq = MagicMock(return_value=eq_result2)
        select_result.eq = MagicMock(return_value=eq_result1)
        push_queue_table.select = MagicMock(return_value=select_result)

        # Set up update chain
        update_result = MagicMock()
        update_eq_result = MagicMock()
        update_execute_result = MagicMock()
        update_execute_result.data = []
        update_eq_result.execute = MagicMock(return_value=update_execute_result)
        update_result.eq = MagicMock(return_value=update_eq_result)
        push_queue_table.update = MagicMock(return_value=update_result)

        # Make the table() method return our mocked table
        original_table = client.table

        def table_side_effect(table_name: str):
            if table_name == "integration_push_queue":
                return push_queue_table
            return original_table(table_name)

        client.table = MagicMock(side_effect=table_side_effect)

        # Execute
        await deep_sync_service.process_approved_push_items(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
        )

        # Verify order was called with priority_int desc
        eq_result3.order.assert_called_with("priority_int", desc=True)


class TestExecutePushItem:
    """Test individual push item execution."""

    @pytest.mark.asyncio
    async def test_execute_push_item_create_note_salesforce(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should create Salesforce note via Composio."""
        item = {
            "id": "queue-1",
            "action_type": "create_note",
            "payload": {
                "parentId": "001xx000003DI9E",
                "title": "ARIA Insight",
                "body": "Based on recent email analysis, this lead shows strong buying signals.",
            },
        }

        await deep_sync_service._execute_push_item(
            integration_type=IntegrationType.SALESFORCE,
            connection_id="conn-123",
            item=item,
        )

        # Verify Composio was called with correct params
        mock_oauth_client.execute_action.assert_called_once_with(
            connection_id="conn-123",
            action="salesforce_create_note",
            params={
                "parentId": "001xx000003DI9E",
                "title": "ARIA Insight",
                "body": "Based on recent email analysis, this lead shows strong buying signals.",
            },
        )

    @pytest.mark.asyncio
    async def test_execute_push_item_create_note_hubspot(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should create HubSpot engagement via Composio."""
        item = {
            "id": "queue-1",
            "action_type": "create_note",
            "payload": {
                "parentId": "123456789",
                "title": "Meeting Notes",
                "body": "Discussed pricing and timeline. Decision maker present.",
            },
        }

        await deep_sync_service._execute_push_item(
            integration_type=IntegrationType.HUBSPOT,
            connection_id="conn-456",
            item=item,
        )

        # Verify Composio was called with HubSpot params
        mock_oauth_client.execute_action.assert_called_once_with(
            connection_id="conn-456",
            action="hubspot_create_engagement",
            params={
                "associatedObjectId": "123456789",
                "type": "NOTE",
                "body": "Discussed pricing and timeline. Decision maker present.",
            },
        )

    @pytest.mark.asyncio
    async def test_execute_push_item_update_field_salesforce(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should update Salesforce custom field via Composio."""
        item = {
            "id": "queue-1",
            "action_type": "update_field",
            "payload": {
                "entityId": "006xx000003DI9F",
                "field_value": 92,
            },
        }

        await deep_sync_service._execute_push_item(
            integration_type=IntegrationType.SALESFORCE,
            connection_id="conn-123",
            item=item,
        )

        # Verify Composio was called
        mock_oauth_client.execute_action.assert_called_once_with(
            connection_id="conn-123",
            action="salesforce_update_opportunity",
            params={
                "opportunityId": "006xx000003DI9F",
                "aria_Lead_Score__c": 92,
            },
        )

    @pytest.mark.asyncio
    async def test_execute_push_item_update_field_hubspot(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should update HubSpot deal field via Composio."""
        item = {
            "id": "queue-1",
            "action_type": "update_field",
            "payload": {
                "entityId": "987654321",
                "field_value": 88,
            },
        }

        await deep_sync_service._execute_push_item(
            integration_type=IntegrationType.HUBSPOT,
            connection_id="conn-456",
            item=item,
        )

        # Verify Composio was called with HubSpot params
        mock_oauth_client.execute_action.assert_called_once_with(
            connection_id="conn-456",
            action="hubspot_update_deal",
            params={
                "dealId": "987654321",
                "aria_lead_score": 88,
            },
        )

    @pytest.mark.asyncio
    async def test_execute_push_item_create_event_google_calendar(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should create Google Calendar event via Composio."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        item = {
            "id": "queue-1",
            "action_type": "create_event",
            "payload": {
                "summary": "Follow-up Call with Acme Corp",
                "description": "Discuss proposal feedback",
                "start": tomorrow.isoformat(),
                "end": (tomorrow + timedelta(hours=1)).isoformat(),
                "attendees": ["john@acmecorp.com"],
            },
        }

        await deep_sync_service._execute_push_item(
            integration_type=IntegrationType.GOOGLE_CALENDAR,
            connection_id="conn-789",
            item=item,
        )

        # Verify Composio was called
        mock_oauth_client.execute_action.assert_called_once_with(
            connection_id="conn-789",
            action="create_event",
            params={
                "summary": "Follow-up Call with Acme Corp",
                "description": "Discuss proposal feedback",
                "start": tomorrow.isoformat(),
                "end": (tomorrow + timedelta(hours=1)).isoformat(),
                "attendees": ["john@acmecorp.com"],
            },
        )

    @pytest.mark.asyncio
    async def test_execute_push_item_create_event_outlook(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should create Outlook calendar event via Composio."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        item = {
            "id": "queue-1",
            "action_type": "create_event",
            "payload": {
                "summary": "Quarterly Review",
                "description": "Q4 performance review",
                "start": tomorrow.isoformat(),
                "end": (tomorrow + timedelta(hours=2)).isoformat(),
                "attendees": ["manager@company.com", "vp@company.com"],
            },
        }

        await deep_sync_service._execute_push_item(
            integration_type=IntegrationType.OUTLOOK,
            connection_id="conn-outlook",
            item=item,
        )

        # Verify Composio was called with Outlook params
        mock_oauth_client.execute_action.assert_called_once_with(
            connection_id="conn-outlook",
            action="create_calendar_event",
            params={
                "subject": "Quarterly Review",
                "bodyPreview": "Q4 performance review",
                "start": tomorrow.isoformat(),
                "end": (tomorrow + timedelta(hours=2)).isoformat(),
                "attendees": ["manager@company.com", "vp@company.com"],
            },
        )

    @pytest.mark.asyncio
    async def test_execute_push_item_unknown_action_type(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should raise exception for unknown action type."""
        item = {
            "id": "queue-1",
            "action_type": "unknown_action",
            "payload": {},
        }

        with pytest.raises(Exception) as exc_info:
            await deep_sync_service._execute_push_item(
                integration_type=IntegrationType.SALESFORCE,
                connection_id="conn-123",
                item=item,
            )

        assert "Unknown action_type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_push_item_handles_api_failure(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Should raise exception when Composio API fails."""
        item = {
            "id": "queue-1",
            "action_type": "create_note",
            "payload": {
                "parentId": "opp-123",
                "title": "Test",
                "body": "Test",
            },
        }

        # Mock API failure
        mock_oauth_client.execute_action.return_value = {"data": None}

        with pytest.raises(Exception) as exc_info:
            await deep_sync_service._execute_push_item(
                integration_type=IntegrationType.SALESFORCE,
                connection_id="conn-123",
                item=item,
            )

        assert "Failed to create note" in str(exc_info.value)


class TestPushSyncResult:
    """Test push sync result metrics."""

    @pytest.mark.asyncio
    async def test_push_sync_result_direction(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_supabase_client: MockSupabaseClient,
        mock_oauth_client: MagicMock,
    ) -> None:
        """Push sync should have PUSH direction."""
        # Set up the mock to return empty approved items
        mock_supabase_client.set_approved_items([])

        result = await deep_sync_service.process_approved_push_items(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
        )

        from src.integrations.deep_sync_domain import SyncDirection

        assert result.direction == SyncDirection.PUSH
