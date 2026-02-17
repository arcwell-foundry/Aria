"""Tests for debrief scheduler service.

Tests the automatic prompting for meeting debriefs after meetings end.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    mock_client = MagicMock()
    return mock_client


# =========================================================================
# check_and_prompt_debriefs Tests
# =========================================================================


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_finds_recently_ended_meetings(
    mock_db: MagicMock,
) -> None:
    """Test finds meetings that ended in the last 2 hours without debriefs."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        # Setup calendar events that ended 1 hour ago
        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Sales Demo with Acme",
                "start_time": (one_hour_ago - timedelta(hours=1)).isoformat(),
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["john@acme.com", "jane@company.com"],
                "external_company": "Acme Corp",
                "metadata": {"internal_only": False},
            },
        ]

        # No debrief exists for this meeting
        debrief_result = MagicMock()
        debrief_result.data = None

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = debrief_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        result = await scheduler.check_and_prompt_debriefs("user-123")

        assert result["meetings_checked"] == 1
        assert result["notifications_sent"] == 1
        mock_notification.create_notification.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_skips_meetings_with_existing_debriefs(
    mock_db: MagicMock,
) -> None:
    """Test skips meetings that already have debriefs."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Sales Demo",
                "start_time": (one_hour_ago - timedelta(hours=1)).isoformat(),
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["john@acme.com"],
                "metadata": {},
            },
        ]

        # Debrief already exists
        debrief_result = MagicMock()
        debrief_result.data = {"id": "debrief-1"}

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = debrief_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        result = await scheduler.check_and_prompt_debriefs("user-123")

        assert result["meetings_checked"] == 1
        assert result["notifications_sent"] == 0
        mock_notification.create_notification.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_filters_internal_only_meetings(
    mock_db: MagicMock,
) -> None:
    """Test skips internal-only meetings by default."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Team Standup",
                "start_time": (one_hour_ago - timedelta(minutes=30)).isoformat(),
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["colleague@company.com"],
                "metadata": {"internal_only": True},
            },
        ]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        result = await scheduler.check_and_prompt_debriefs("user-123")

        # Internal meeting should be filtered out
        assert result["meetings_checked"] == 1
        assert result["notifications_sent"] == 0
        assert result["internal_filtered"] == 1


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_creates_notification_with_correct_format(
    mock_db: MagicMock,
) -> None:
    """Test notification is created with correct type, title, message, and link."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Sales Demo with Acme",
                "start_time": (one_hour_ago - timedelta(hours=1)).isoformat(),
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["john@acme.com", "jane@company.com"],
                "external_company": "Acme Corp",
                "metadata": {},
            },
        ]

        debrief_result = MagicMock()
        debrief_result.data = None

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = debrief_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        await scheduler.check_and_prompt_debriefs("user-123")

        # Verify notification format
        call_args = mock_notification.create_notification.call_args
        assert call_args.kwargs["user_id"] == "user-123"
        assert call_args.kwargs["type"].value == "meeting_debrief_prompt"
        assert "Sales Demo with Acme" in call_args.kwargs["title"]
        assert "Acme Corp" in call_args.kwargs["message"]
        assert "/dashboard/debriefs/new?meeting_id=meeting-1" == call_args.kwargs["link"]


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_handles_meetings_without_external_company(
    mock_db: MagicMock,
) -> None:
    """Test handles meetings that don't have external_company set."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Call with John",
                "start_time": (one_hour_ago - timedelta(hours=1)).isoformat(),
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["john@example.com"],
                "external_company": None,
                "metadata": {},
            },
        ]

        debrief_result = MagicMock()
        debrief_result.data = None

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = debrief_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        await scheduler.check_and_prompt_debriefs("user-123")

        # Should use attendee email in message
        call_args = mock_notification.create_notification.call_args
        assert "john@example.com" in call_args.kwargs["message"]


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_formats_time_ago_correctly(
    mock_db: MagicMock,
) -> None:
    """Test time_ago is formatted correctly in notification message."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Test Meeting",
                "start_time": (one_hour_ago - timedelta(hours=1)).isoformat(),
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["john@example.com"],
                "external_company": "Test Co",
                "metadata": {},
            },
        ]

        debrief_result = MagicMock()
        debrief_result.data = None

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = debrief_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        await scheduler.check_and_prompt_debriefs("user-123")

        call_args = mock_notification.create_notification.call_args
        # Should contain "1 hour ago" or similar
        message = call_args.kwargs["message"]
        assert "ago" in message.lower()


# =========================================================================
# Overdue Commitments Tests
# =========================================================================


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_finds_overdue_commitments_theirs(
    mock_db: MagicMock,
) -> None:
    """Test finds commitments_theirs from past debriefs that are overdue."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)

        # No recent meetings
        events_result = MagicMock()
        events_result.data = []

        # But there are overdue commitments
        debriefs_result = MagicMock()
        debriefs_result.data = [
            {
                "id": "debrief-1",
                "meeting_title": "Sales Call with Acme",
                "commitments_theirs": ["Send proposal by Friday", "Schedule follow-up call"],
                "linked_lead_id": "lead-123",
                "created_at": yesterday.isoformat(),
            },
        ]

        mock_db_class.get_client.return_value = mock_db

        # Setup calendar events query
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result

        # Setup overdue commitments query
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.lt.return_value.execute.return_value = debriefs_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        result = await scheduler.check_and_prompt_debriefs("user-123")

        assert result["overdue_commitments_found"] >= 1


# =========================================================================
# Debrief Count for Daily Briefing Tests
# =========================================================================


@pytest.mark.asyncio
async def test_get_debrief_prompt_count_returns_count_of_meetings_needing_debrief(
    mock_db: MagicMock,
) -> None:
    """Test get_debrief_prompt_count returns correct count for daily briefing."""
    with patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class:
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Meeting 1",
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["john@example.com"],
                "metadata": {},
            },
            {
                "id": "meeting-2",
                "title": "Meeting 2",
                "end_time": (one_hour_ago - timedelta(hours=2)).isoformat(),
                "attendees": ["jane@example.com"],
                "metadata": {},
            },
        ]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        count = await scheduler.get_debrief_prompt_count("user-123")

        assert count == 2


@pytest.mark.asyncio
async def test_get_debrief_prompt_count_excludes_internal_meetings(
    mock_db: MagicMock,
) -> None:
    """Test get_debrief_prompt_count excludes internal meetings."""
    with patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class:
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "External Meeting",
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["john@external.com"],
                "metadata": {"internal_only": False},
            },
            {
                "id": "meeting-2",
                "title": "Team Standup",
                "end_time": (one_hour_ago - timedelta(hours=1)).isoformat(),
                "attendees": ["jane@company.com"],
                "metadata": {"internal_only": True},
            },
        ]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        count = await scheduler.get_debrief_prompt_count("user-123")

        # Only external meeting should count
        assert count == 1


# =========================================================================
# Configurable Internal Filtering Tests
# =========================================================================


@pytest.mark.asyncio
async def test_check_and_prompt_debriefs_respects_include_internal_flag(
    mock_db: MagicMock,
) -> None:
    """Test can be configured to include internal meetings."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.NotificationService") as mock_notification,
    ):
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Team Standup",
                "start_time": (one_hour_ago - timedelta(minutes=30)).isoformat(),
                "end_time": one_hour_ago.isoformat(),
                "attendees": ["colleague@company.com"],
                "metadata": {"internal_only": True},
            },
        ]

        debrief_result = MagicMock()
        debrief_result.data = None

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = debrief_result

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_scheduler import DebriefScheduler

        scheduler = DebriefScheduler()
        result = await scheduler.check_and_prompt_debriefs(
            "user-123",
            include_internal=True,
        )

        # Internal meeting should NOT be filtered when include_internal=True
        assert result["notifications_sent"] == 1


# =========================================================================
# Scheduler Integration Tests
# =========================================================================


@pytest.mark.asyncio
async def test_run_debrief_prompt_scheduler_processes_all_users(
    mock_db: MagicMock,
) -> None:
    """Test scheduler job processes all active users."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.DebriefScheduler") as mock_scheduler_class,
    ):
        # Setup active users
        users_result = MagicMock()
        users_result.data = [
            {"user_id": "user-1"},
            {"user_id": "user-2"},
        ]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.not_.is_.return_value.execute.return_value = users_result

        # Mock scheduler instance
        mock_scheduler = MagicMock()
        mock_scheduler.check_and_prompt_debriefs = AsyncMock(
            return_value={"meetings_checked": 0, "notifications_sent": 0}
        )
        mock_scheduler_class.return_value = mock_scheduler

        from src.services.debrief_scheduler import run_debrief_prompt_scheduler

        result = await run_debrief_prompt_scheduler()

        assert result["users_processed"] == 2


@pytest.mark.asyncio
async def test_run_debrief_prompt_scheduler_handles_user_errors_gracefully(
    mock_db: MagicMock,
) -> None:
    """Test scheduler continues processing even if one user fails."""
    with (
        patch("src.services.debrief_scheduler.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_scheduler.DebriefScheduler") as mock_scheduler_class,
    ):
        users_result = MagicMock()
        users_result.data = [
            {"user_id": "user-1"},
            {"user_id": "user-2"},
            {"user_id": "user-3"},
        ]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.not_.is_.return_value.execute.return_value = users_result

        mock_scheduler = MagicMock()
        # First call succeeds, second fails, third succeeds
        mock_scheduler.check_and_prompt_debriefs = AsyncMock()
        mock_scheduler.check_and_prompt_debriefs.side_effect = [
            {"meetings_checked": 1, "notifications_sent": 1},
            Exception("Database error"),
            {"meetings_checked": 2, "notifications_sent": 1},
        ]
        mock_scheduler_class.return_value = mock_scheduler

        from src.services.debrief_scheduler import run_debrief_prompt_scheduler

        result = await run_debrief_prompt_scheduler()

        # Should have processed all users, with one error
        assert result["users_processed"] == 2
        assert result["errors"] == 1
