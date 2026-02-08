"""Tests for deep sync API routes (US-942)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.deep_sync_domain import (
    SyncDirection,
    SyncStatus,
)
from src.integrations.domain import IntegrationType


@pytest.fixture
def mock_user() -> MagicMock:
    """Create mock authenticated user."""
    user = MagicMock()
    user.id = "user-test-123"
    return user


@pytest.fixture
def mock_sync_result() -> MagicMock:
    """Create mock sync result."""
    result = MagicMock()
    result.direction = SyncDirection.PULL
    result.integration_type = IntegrationType.SALESFORCE
    result.status = SyncStatus.SUCCESS
    result.records_processed = 100
    result.records_succeeded = 98
    result.records_failed = 2
    result.memory_entries_created = 50
    result.started_at = datetime.now(UTC)
    result.completed_at = datetime.now(UTC)
    result.duration_seconds = 5.5
    result.success_rate = 98.0
    return result


@pytest.mark.asyncio
async def test_trigger_manual_sync_crm(mock_user: MagicMock, mock_sync_result: MagicMock) -> None:
    """POST /integrations/sync/salesforce triggers CRM sync."""
    mock_service = MagicMock()
    mock_service.sync_crm_to_aria = AsyncMock(return_value=mock_sync_result)

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from src.api.routes.deep_sync import trigger_manual_sync

        result = await trigger_manual_sync("salesforce", mock_user)

        assert result["direction"] == "PULL"
        assert result["integration_type"] == "salesforce"
        assert result["status"] == "SUCCESS"
        assert result["records_processed"] == 100
        assert result["records_succeeded"] == 98
        assert result["records_failed"] == 2
        assert result["memory_entries_created"] == 50
        assert result["success_rate"] == 98.0
        mock_service.sync_crm_to_aria.assert_awaited_once_with(
            mock_user.id,
            IntegrationType.SALESFORCE,
        )


@pytest.mark.asyncio
async def test_trigger_manual_sync_calendar(mock_user: MagicMock, mock_sync_result: MagicMock) -> None:
    """POST /integrations/sync/google_calendar triggers calendar sync."""
    mock_sync_result.integration_type = IntegrationType.GOOGLE_CALENDAR
    mock_service = MagicMock()
    mock_service.sync_calendar = AsyncMock(return_value=mock_sync_result)

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from src.api.routes.deep_sync import trigger_manual_sync

        result = await trigger_manual_sync("google_calendar", mock_user)

        assert result["direction"] == "PULL"
        assert result["integration_type"] == "google_calendar"
        assert result["status"] == "SUCCESS"
        mock_service.sync_calendar.assert_awaited_once_with(
            mock_user.id,
            IntegrationType.GOOGLE_CALENDAR,
        )


@pytest.mark.asyncio
async def test_trigger_manual_sync_invalid_type(mock_user: MagicMock) -> None:
    """POST /integrations/sync/invalid returns 400 for invalid type."""
    from fastapi import HTTPException

    from src.api.routes.deep_sync import trigger_manual_sync

    with pytest.raises(HTTPException) as exc_info:
        await trigger_manual_sync("invalid_type", mock_user)

    assert exc_info.value.status_code == 400
    assert "Invalid integration type" in exc_info.value.detail


@pytest.mark.asyncio
async def test_trigger_manual_sync_unsupported_integration(mock_user: MagicMock) -> None:
    """POST /integrations/sync/gmail returns 400 for unsupported integration."""
    from fastapi import HTTPException

    from src.api.routes.deep_sync import trigger_manual_sync

    with pytest.raises(HTTPException) as exc_info:
        await trigger_manual_sync("gmail", mock_user)

    assert exc_info.value.status_code == 400
    assert "does not support sync" in exc_info.value.detail


@pytest.mark.asyncio
async def test_trigger_manual_sync_service_failure(mock_user: MagicMock) -> None:
    """POST /integrations/sync/salesforce returns 500 when service fails."""
    mock_service = MagicMock()
    mock_service.sync_crm_to_aria = AsyncMock(side_effect=Exception("Sync failed"))

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from fastapi import HTTPException

        from src.api.routes.deep_sync import trigger_manual_sync

        with pytest.raises(HTTPException) as exc_info:
            await trigger_manual_sync("salesforce", mock_user)

        assert exc_info.value.status_code == 500
        assert "Sync failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_sync_status(mock_user: MagicMock) -> None:
    """GET /integrations/sync/status returns sync status for all integrations."""
    mock_client = MagicMock()
    mock_states = [
        {
            "id": "state-1",
            "user_id": mock_user.id,
            "integration_type": "salesforce",
            "last_sync_at": "2026-02-07T12:00:00Z",
            "last_sync_status": "SUCCESS",
            "next_sync_at": "2026-02-07T12:15:00Z",
        },
        {
            "id": "state-2",
            "user_id": mock_user.id,
            "integration_type": "google_calendar",
            "last_sync_at": "2026-02-07T11:00:00Z",
            "last_sync_status": "SUCCESS",
            "next_sync_at": "2026-02-07T11:15:00Z",
        },
    ]
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=mock_states
    )

    # Mock logs count
    mock_logs_response = MagicMock()
    mock_logs_response.count = 10
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
        mock_logs_response
    )

    with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
        from src.api.routes.deep_sync import get_sync_status

        result = await get_sync_status(mock_user)

        assert len(result) == 2
        assert result[0]["integration_type"] == "salesforce"
        assert result[0]["last_sync_at"] == "2026-02-07T12:00:00Z"
        assert result[0]["last_sync_status"] == "SUCCESS"
        assert result[0]["sync_count"] == 10
        assert result[1]["integration_type"] == "google_calendar"


@pytest.mark.asyncio
async def test_get_sync_status_empty(mock_user: MagicMock) -> None:
    """GET /integrations/sync/status returns empty list when no syncs."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=None
    )

    with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
        from src.api.routes.deep_sync import get_sync_status

        result = await get_sync_status(mock_user)

        assert result == []


@pytest.mark.asyncio
async def test_queue_push_item(mock_user: MagicMock) -> None:
    """POST /integrations/sync/queue queues a push item for approval."""
    mock_service = MagicMock()
    mock_service.queue_push_item = AsyncMock(return_value="queue-123")

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from src.api.routes.deep_sync import PushItemRequest, queue_push_item

        request = PushItemRequest(
            integration_type="salesforce",
            action_type="create_note",
            priority="high",
            payload={"parentId": "opp-1", "title": "Test", "body": "Note content"},
        )

        result = await queue_push_item(request, mock_user)

        assert result["queue_id"] == "queue-123"
        assert result["status"] == "pending"
        mock_service.queue_push_item.assert_called_once()


@pytest.mark.asyncio
async def test_queue_push_item_invalid_action(mock_user: MagicMock) -> None:
    """POST /integrations/sync/queue returns 400 for invalid action type."""
    from fastapi import HTTPException

    from src.api.routes.deep_sync import PushItemRequest, queue_push_item

    request = PushItemRequest(
        integration_type="salesforce",
        action_type="invalid_action",
        priority="medium",
        payload={},
    )

    with pytest.raises(HTTPException) as exc_info:
        await queue_push_item(request, mock_user)

    assert exc_info.value.status_code == 400
    assert "Invalid action type" in exc_info.value.detail


@pytest.mark.asyncio
async def test_queue_push_item_invalid_priority(mock_user: MagicMock) -> None:
    """POST /integrations/sync/queue returns 400 for invalid priority."""
    from fastapi import HTTPException

    from src.api.routes.deep_sync import PushItemRequest, queue_push_item

    request = PushItemRequest(
        integration_type="salesforce",
        action_type="create_note",
        priority="invalid_priority",
        payload={},
    )

    with pytest.raises(HTTPException) as exc_info:
        await queue_push_item(request, mock_user)

    assert exc_info.value.status_code == 400
    assert "Invalid priority" in exc_info.value.detail


@pytest.mark.asyncio
async def test_queue_push_item_service_failure(mock_user: MagicMock) -> None:
    """POST /integrations/sync/queue returns 500 when service fails."""
    mock_service = MagicMock()
    mock_service.queue_push_item = AsyncMock(side_effect=Exception("Queue failed"))

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from fastapi import HTTPException

        from src.api.routes.deep_sync import PushItemRequest, queue_push_item

        request = PushItemRequest(
            integration_type="salesforce",
            action_type="create_note",
            priority="medium",
            payload={},
        )

        with pytest.raises(HTTPException) as exc_info:
            await queue_push_item(request, mock_user)

        assert exc_info.value.status_code == 500
        assert "Failed to queue push item" in exc_info.value.detail


@pytest.mark.asyncio
async def test_update_sync_config(mock_user: MagicMock) -> None:
    """PUT /integrations/sync/config updates sync configuration."""
    mock_client = MagicMock()
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "settings-1"}]
    )

    with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
        from src.api.routes.deep_sync import SyncConfigUpdateRequest, update_sync_config

        request = SyncConfigUpdateRequest(
            sync_interval_minutes=30,
            auto_push_enabled=True,
        )

        result = await update_sync_config(request, mock_user)

        assert result["message"] == "Sync configuration updated successfully"
        mock_client.table.return_value.update.assert_called_once()
        call_args = mock_client.table.return_value.update.call_args
        assert call_args[0][0]["deep_sync_config"]["sync_interval_minutes"] == 30
        assert call_args[0][0]["deep_sync_config"]["auto_push_enabled"] is True


@pytest.mark.asyncio
async def test_update_sync_config_validation_interval_too_low() -> None:
    """PUT /integrations/sync/config validates sync_interval_minutes minimum."""
    from pydantic import ValidationError

    from src.api.routes.deep_sync import SyncConfigUpdateRequest

    with pytest.raises(ValidationError) as exc_info:
        SyncConfigUpdateRequest(
            sync_interval_minutes=2,  # Below minimum of 5
            auto_push_enabled=False,
        )

    assert "greater than or equal to 5" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_sync_config_validation_interval_too_high() -> None:
    """PUT /integrations/sync/config validates sync_interval_minutes maximum."""
    from pydantic import ValidationError

    from src.api.routes.deep_sync import SyncConfigUpdateRequest

    with pytest.raises(ValidationError) as exc_info:
        SyncConfigUpdateRequest(
            sync_interval_minutes=2000,  # Above maximum of 1440
            auto_push_enabled=False,
        )

    assert "less than or equal to 1440" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_sync_config_default_values(mock_user: MagicMock) -> None:
    """PUT /integrations/sync/config uses default values when not provided."""
    mock_client = MagicMock()
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "settings-1"}]
    )

    with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
        from src.api.routes.deep_sync import SyncConfigUpdateRequest, update_sync_config

        # Request with no fields (uses defaults)
        request = SyncConfigUpdateRequest()

        result = await update_sync_config(request, mock_user)

        assert result["message"] == "Sync configuration updated successfully"
        call_args = mock_client.table.return_value.update.call_args
        assert call_args[0][0]["deep_sync_config"]["sync_interval_minutes"] == 15
        assert call_args[0][0]["deep_sync_config"]["auto_push_enabled"] is False


@pytest.mark.asyncio
async def test_trigger_manual_sync_hubspot(mock_user: MagicMock, mock_sync_result: MagicMock) -> None:
    """POST /integrations/sync/hubspot triggers HubSpot sync."""
    mock_sync_result.integration_type = IntegrationType.HUBSPOT
    mock_service = MagicMock()
    mock_service.sync_crm_to_aria = AsyncMock(return_value=mock_sync_result)

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from src.api.routes.deep_sync import trigger_manual_sync

        result = await trigger_manual_sync("hubspot", mock_user)

        assert result["integration_type"] == "hubspot"
        mock_service.sync_crm_to_aria.assert_awaited_once_with(
            mock_user.id,
            IntegrationType.HUBSPOT,
        )


@pytest.mark.asyncio
async def test_trigger_manual_sync_outlook(mock_user: MagicMock, mock_sync_result: MagicMock) -> None:
    """POST /integrations/sync/outlook triggers Outlook calendar sync."""
    mock_sync_result.integration_type = IntegrationType.OUTLOOK
    mock_service = MagicMock()
    mock_service.sync_calendar = AsyncMock(return_value=mock_sync_result)

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from src.api.routes.deep_sync import trigger_manual_sync

        result = await trigger_manual_sync("outlook", mock_user)

        assert result["integration_type"] == "outlook"
        mock_service.sync_calendar.assert_awaited_once_with(
            mock_user.id,
            IntegrationType.OUTLOOK,
        )


@pytest.mark.asyncio
async def test_queue_push_item_all_priorities(mock_user: MagicMock) -> None:
    """POST /integrations/sync/queue accepts all valid priority levels."""
    mock_service = MagicMock()
    mock_service.queue_push_item = AsyncMock(return_value="queue-123")

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from src.api.routes.deep_sync import PushItemRequest, queue_push_item

        priorities = ["low", "medium", "high", "critical"]

        for priority in priorities:
            request = PushItemRequest(
                integration_type="salesforce",
                action_type="create_note",
                priority=priority,
                payload={},
            )

            result = await queue_push_item(request, mock_user)
            assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_queue_push_item_all_action_types(mock_user: MagicMock) -> None:
    """POST /integrations/sync/queue accepts all valid action types."""
    mock_service = MagicMock()
    mock_service.queue_push_item = AsyncMock(return_value="queue-123")

    with patch(
        "src.integrations.deep_sync.get_deep_sync_service",
        return_value=mock_service,
    ):
        from src.api.routes.deep_sync import PushItemRequest, queue_push_item

        action_types = ["create_note", "update_field", "create_event"]

        for action_type in action_types:
            request = PushItemRequest(
                integration_type="salesforce",
                action_type=action_type,
                priority="medium",
                payload={},
            )

            result = await queue_push_item(request, mock_user)
            assert result["status"] == "pending"
