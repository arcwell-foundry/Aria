"""Tests for NotificationService."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.notification import NotificationType
from src.services.notification_service import NotificationService


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    mock_client = MagicMock()
    return mock_client


@pytest.mark.asyncio
async def test_create_notification(mock_db: MagicMock) -> None:
    """Test creating a notification."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "notif-123",
                    "user_id": "user-456",
                    "type": "signal_detected",
                    "title": "New Signal Detected",
                    "message": "Acme Corp just raised Series B",
                    "link": "/leads/acme-corp",
                    "metadata": {"company": "Acme Corp"},
                    "read_at": None,
                    "created_at": "2026-02-03T10:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        result = await NotificationService.create_notification(
            user_id="user-456",
            type=NotificationType.SIGNAL_DETECTED,
            title="New Signal Detected",
            message="Acme Corp just raised Series B",
            link="/leads/acme-corp",
            metadata={"company": "Acme Corp"},
        )

        assert result.id == "notif-123"
        assert result.user_id == "user-456"
        assert result.type == NotificationType.SIGNAL_DETECTED
        assert result.title == "New Signal Detected"
        assert result.message == "Acme Corp just raised Series B"
        assert result.link == "/leads/acme-corp"
        assert result.metadata["company"] == "Acme Corp"
        assert result.read_at is None
        assert result.created_at is not None


@pytest.mark.asyncio
async def test_get_notifications_returns_paginated_list(mock_db: MagicMock) -> None:
    """Test retrieving notifications with pagination."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        expected_notifications = [
            {
                "id": "notif-1",
                "user_id": "user-456",
                "type": "briefing_ready",
                "title": "Briefing Ready",
                "message": None,
                "link": "/briefing",
                "metadata": {},
                "read_at": None,
                "created_at": "2026-02-03T10:00:00Z",
            },
            {
                "id": "notif-2",
                "user_id": "user-456",
                "type": "task_due",
                "title": "Task Due",
                "message": None,
                "link": "/goals",
                "metadata": {},
                "read_at": None,
                "created_at": "2026-02-03T09:00:00Z",
            },
        ]

        # Create separate table mocks for each call
        main_table_mock = MagicMock()
        main_table_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
            data=expected_notifications, count=2
        )

        count_table_mock = MagicMock()
        count_table_mock.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            count=2
        )

        # Make table() return the appropriate mock based on call order
        table_mock_side_effects = [main_table_mock, count_table_mock]
        mock_db.table.side_effect = table_mock_side_effects

        mock_db_class.get_client.return_value = mock_db

        result = await NotificationService.get_notifications(user_id="user-456", limit=10)

        assert len(result.notifications) == 2
        assert result.total == 2
        assert result.unread_count == 2


@pytest.mark.asyncio
async def test_get_notifications_filters_unread_only(mock_db: MagicMock) -> None:
    """Test filtering for unread notifications only."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        # Create separate table mocks for each call
        main_table_mock = MagicMock()
        main_is = MagicMock()
        main_is.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "notif-1",
                    "user_id": "user-456",
                    "type": "briefing_ready",
                    "title": "Briefing Ready",
                    "message": None,
                    "link": "/briefing",
                    "metadata": {},
                    "read_at": None,
                    "created_at": "2026-02-03T10:00:00Z",
                }
            ],
            count=1,
        )
        main_table_mock.select.return_value.eq.return_value.is_ = main_is

        count_table_mock = MagicMock()
        count_table_mock.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            count=1
        )

        # Make table() return the appropriate mock based on call order
        table_mock_side_effects = [main_table_mock, count_table_mock]
        mock_db.table.side_effect = table_mock_side_effects

        mock_db_class.get_client.return_value = mock_db

        result = await NotificationService.get_notifications(user_id="user-456", unread_only=True)

        # Verify is_ was called with read_at and "null"
        main_is.assert_called_once_with("read_at", "null")


@pytest.mark.asyncio
async def test_get_unread_count_returns_count(mock_db: MagicMock) -> None:
    """Test getting unread count."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            count=5
        )
        mock_db_class.get_client.return_value = mock_db

        result = await NotificationService.get_unread_count(user_id="user-456")

        assert result.count == 5


@pytest.mark.asyncio
async def test_get_unread_count_returns_zero_when_no_notifications(mock_db: MagicMock) -> None:
    """Test getting unread count returns 0 when count is None."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            count=None
        )
        mock_db_class.get_client.return_value = mock_db

        result = await NotificationService.get_unread_count(user_id="user-456")

        assert result.count == 0


@pytest.mark.asyncio
async def test_mark_as_read_updates_timestamp(mock_db: MagicMock) -> None:
    """Test marking a notification as read."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "notif-123",
                    "user_id": "user-456",
                    "type": "briefing_ready",
                    "title": "Briefing Ready",
                    "message": None,
                    "link": "/briefing",
                    "metadata": {},
                    "read_at": "2026-02-03T10:00:00Z",
                    "created_at": "2026-02-03T09:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        result = await NotificationService.mark_as_read(notification_id="notif-123", user_id="user-456")

        assert result.id == "notif-123"
        assert result.read_at is not None


@pytest.mark.asyncio
async def test_mark_as_read_raises_not_found_when_notification_missing(mock_db: MagicMock) -> None:
    """Test mark_as_read raises NotFoundError when notification not found."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        from src.core.exceptions import NotFoundError

        # Setup DB mock to return empty data
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        with pytest.raises(NotFoundError):
            await NotificationService.mark_as_read(notification_id="notif-999", user_id="user-456")


@pytest.mark.asyncio
async def test_mark_all_as_read_updates_all_unread(mock_db: MagicMock) -> None:
    """Test marking all notifications as read."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "notif-1"},
                {"id": "notif-2"},
                {"id": "notif-3"},
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        count = await NotificationService.mark_all_as_read(user_id="user-456")

        assert count == 3


@pytest.mark.asyncio
async def test_delete_notification_removes_notification(mock_db: MagicMock) -> None:
    """Test deleting a notification."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "notif-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Should not raise
        await NotificationService.delete_notification(notification_id="notif-123", user_id="user-456")


@pytest.mark.asyncio
async def test_delete_notification_raises_not_found_when_missing(mock_db: MagicMock) -> None:
    """Test delete_notification raises NotFoundError when notification not found."""
    with patch("src.services.notification_service.SupabaseClient") as mock_db_class:
        from src.core.exceptions import NotFoundError

        # Setup DB mock to return empty data
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        with pytest.raises(NotFoundError):
            await NotificationService.delete_notification(notification_id="notif-999", user_id="user-456")
