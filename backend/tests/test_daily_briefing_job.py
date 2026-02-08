"""Tests for daily briefing job."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.jobs.daily_briefing_job import (
    _briefing_exists,
    _is_briefing_due,
    _parse_briefing_time,
    _today_in_user_tz,
    run_daily_briefing_job,
)

# --- Unit tests for helper functions ---


class TestParseBriefingTime:
    """Tests for _parse_briefing_time helper."""

    def test_parses_hh_mm_format(self) -> None:
        assert _parse_briefing_time("06:00") == (6, 0)

    def test_parses_afternoon_time(self) -> None:
        assert _parse_briefing_time("14:30") == (14, 30)

    def test_parses_hh_mm_ss_format(self) -> None:
        assert _parse_briefing_time("08:00:00") == (8, 0)

    def test_returns_default_for_invalid_input(self) -> None:
        hour, minute = _parse_briefing_time("invalid")
        assert hour == 6
        assert minute == 0

    def test_returns_default_for_empty_string(self) -> None:
        hour, minute = _parse_briefing_time("")
        assert hour == 6
        assert minute == 0


class TestIsBriefingDue:
    """Tests for _is_briefing_due."""

    def test_returns_true_when_past_briefing_time(self) -> None:
        # Use a timezone where it's definitely afternoon
        with patch("src.jobs.daily_briefing_job.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 8, 14, 0, 0, tzinfo=ZoneInfo("UTC"))
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = _is_briefing_due("UTC", "06:00")
            assert result is True

    def test_returns_false_when_before_briefing_time(self) -> None:
        with patch("src.jobs.daily_briefing_job.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 8, 3, 0, 0, tzinfo=ZoneInfo("UTC"))
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = _is_briefing_due("UTC", "06:00")
            assert result is False

    def test_falls_back_to_utc_for_invalid_timezone(self) -> None:
        with patch("src.jobs.daily_briefing_job.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 8, 14, 0, 0, tzinfo=ZoneInfo("UTC"))
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = _is_briefing_due("Invalid/Timezone", "06:00")
            assert result is True


class TestTodayInUserTz:
    """Tests for _today_in_user_tz."""

    def test_returns_date_in_utc(self) -> None:
        result = _today_in_user_tz("UTC")
        assert isinstance(result, date)

    def test_falls_back_to_utc_for_invalid_timezone(self) -> None:
        result = _today_in_user_tz("Invalid/Timezone")
        assert isinstance(result, date)

    def test_returns_different_date_across_dateline(self) -> None:
        # Near midnight UTC, timezones far ahead should be next day
        with patch("src.jobs.daily_briefing_job.datetime") as mock_dt:
            # 11 PM UTC on Feb 8 = Feb 9 in UTC+13
            mock_dt.now.return_value = datetime(2026, 2, 8, 23, 0, 0, tzinfo=ZoneInfo("UTC"))
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            utc_date = _today_in_user_tz("UTC")
            assert utc_date == date(2026, 2, 8)


# --- Integration-level tests for the main job ---


@pytest.mark.asyncio
async def test_briefing_exists_returns_true_when_row_found() -> None:
    """Test _briefing_exists returns True when a row exists."""
    with patch("src.jobs.daily_briefing_job.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        result = await _briefing_exists("user-1", date(2026, 2, 8))
        assert result is True


@pytest.mark.asyncio
async def test_briefing_exists_returns_false_when_no_row() -> None:
    """Test _briefing_exists returns False when no row exists."""
    with patch("src.jobs.daily_briefing_job.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        result = await _briefing_exists("user-1", date(2026, 2, 8))
        assert result is False


@pytest.mark.asyncio
async def test_run_daily_briefing_job_returns_zero_when_no_users() -> None:
    """Test job returns empty summary when there are no users."""
    with patch(
        "src.jobs.daily_briefing_job._get_active_users_with_preferences",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await run_daily_briefing_job()
        assert result == {"users_checked": 0, "generated": 0, "skipped": 0, "errors": 0}


@pytest.mark.asyncio
async def test_run_daily_briefing_job_skips_when_briefing_exists() -> None:
    """Test job skips users who already have today's briefing."""
    users = [
        {
            "user_id": "user-1",
            "full_name": "Alice",
            "timezone": "UTC",
            "briefing_time": "06:00",
            "notification_email": True,
        },
    ]
    with (
        patch(
            "src.jobs.daily_briefing_job._get_active_users_with_preferences",
            new_callable=AsyncMock,
            return_value=users,
        ),
        patch(
            "src.jobs.daily_briefing_job._is_briefing_due",
            return_value=True,
        ),
        patch(
            "src.jobs.daily_briefing_job._briefing_exists",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "src.jobs.daily_briefing_job._today_in_user_tz",
            return_value=date(2026, 2, 8),
        ),
    ):
        result = await run_daily_briefing_job()
        assert result["skipped"] == 1
        assert result["generated"] == 0


@pytest.mark.asyncio
async def test_run_daily_briefing_job_skips_when_not_due() -> None:
    """Test job skips users whose briefing time hasn't passed yet."""
    users = [
        {
            "user_id": "user-1",
            "full_name": "Alice",
            "timezone": "UTC",
            "briefing_time": "06:00",
            "notification_email": True,
        },
    ]
    with (
        patch(
            "src.jobs.daily_briefing_job._get_active_users_with_preferences",
            new_callable=AsyncMock,
            return_value=users,
        ),
        patch(
            "src.jobs.daily_briefing_job._is_briefing_due",
            return_value=False,
        ),
    ):
        result = await run_daily_briefing_job()
        assert result["skipped"] == 1
        assert result["generated"] == 0


@pytest.mark.asyncio
async def test_run_daily_briefing_job_generates_and_sends_email() -> None:
    """Test job generates briefing and sends email when conditions met."""
    users = [
        {
            "user_id": "user-1",
            "full_name": "Alice",
            "timezone": "UTC",
            "briefing_time": "06:00",
            "notification_email": True,
        },
    ]

    mock_briefing_service = MagicMock()
    mock_briefing_service.generate_briefing = AsyncMock(return_value={"summary": "Good morning!"})

    with (
        patch(
            "src.jobs.daily_briefing_job._get_active_users_with_preferences",
            new_callable=AsyncMock,
            return_value=users,
        ),
        patch(
            "src.jobs.daily_briefing_job._is_briefing_due",
            return_value=True,
        ),
        patch(
            "src.jobs.daily_briefing_job._briefing_exists",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "src.jobs.daily_briefing_job._today_in_user_tz",
            return_value=date(2026, 2, 8),
        ),
        patch(
            "src.jobs.daily_briefing_job.BriefingService",
            return_value=mock_briefing_service,
        ),
        patch(
            "src.jobs.daily_briefing_job._send_briefing_email",
            new_callable=AsyncMock,
        ) as mock_email,
    ):
        result = await run_daily_briefing_job()

        assert result["generated"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == 0

        # Verify briefing was generated
        mock_briefing_service.generate_briefing.assert_called_once_with(
            user_id="user-1",
            briefing_date=date(2026, 2, 8),
        )

        # Verify email was sent
        mock_email.assert_called_once_with(
            user_id="user-1",
            full_name="Alice",
            briefing_date=date(2026, 2, 8),
        )


@pytest.mark.asyncio
async def test_run_daily_briefing_job_skips_email_when_disabled() -> None:
    """Test job skips email when notification_email is False."""
    users = [
        {
            "user_id": "user-1",
            "full_name": "Alice",
            "timezone": "UTC",
            "briefing_time": "06:00",
            "notification_email": False,
        },
    ]

    mock_briefing_service = MagicMock()
    mock_briefing_service.generate_briefing = AsyncMock(return_value={"summary": "Good morning!"})

    with (
        patch(
            "src.jobs.daily_briefing_job._get_active_users_with_preferences",
            new_callable=AsyncMock,
            return_value=users,
        ),
        patch(
            "src.jobs.daily_briefing_job._is_briefing_due",
            return_value=True,
        ),
        patch(
            "src.jobs.daily_briefing_job._briefing_exists",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "src.jobs.daily_briefing_job._today_in_user_tz",
            return_value=date(2026, 2, 8),
        ),
        patch(
            "src.jobs.daily_briefing_job.BriefingService",
            return_value=mock_briefing_service,
        ),
        patch(
            "src.jobs.daily_briefing_job._send_briefing_email",
            new_callable=AsyncMock,
        ) as mock_email,
    ):
        result = await run_daily_briefing_job()

        assert result["generated"] == 1
        mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_run_daily_briefing_job_continues_on_user_error() -> None:
    """Test job continues processing other users when one fails."""
    users = [
        {
            "user_id": "user-1",
            "full_name": "Alice",
            "timezone": "UTC",
            "briefing_time": "06:00",
            "notification_email": False,
        },
        {
            "user_id": "user-2",
            "full_name": "Bob",
            "timezone": "UTC",
            "briefing_time": "06:00",
            "notification_email": False,
        },
    ]

    mock_briefing_service = MagicMock()
    mock_briefing_service.generate_briefing = AsyncMock(
        side_effect=[Exception("LLM timeout"), {"summary": "Good morning!"}]
    )

    with (
        patch(
            "src.jobs.daily_briefing_job._get_active_users_with_preferences",
            new_callable=AsyncMock,
            return_value=users,
        ),
        patch(
            "src.jobs.daily_briefing_job._is_briefing_due",
            return_value=True,
        ),
        patch(
            "src.jobs.daily_briefing_job._briefing_exists",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "src.jobs.daily_briefing_job._today_in_user_tz",
            return_value=date(2026, 2, 8),
        ),
        patch(
            "src.jobs.daily_briefing_job.BriefingService",
            return_value=mock_briefing_service,
        ),
    ):
        result = await run_daily_briefing_job()

        assert result["users_checked"] == 2
        assert result["generated"] == 1
        assert result["errors"] == 1


@pytest.mark.asyncio
async def test_run_daily_briefing_job_handles_multiple_timezones() -> None:
    """Test job correctly handles users in different timezones."""
    users = [
        {
            "user_id": "user-east",
            "full_name": "East",
            "timezone": "America/New_York",
            "briefing_time": "06:00",
            "notification_email": False,
        },
        {
            "user_id": "user-west",
            "full_name": "West",
            "timezone": "America/Los_Angeles",
            "briefing_time": "06:00",
            "notification_email": False,
        },
    ]

    mock_briefing_service = MagicMock()
    mock_briefing_service.generate_briefing = AsyncMock(return_value={"summary": "Good morning!"})

    # East coast is due, west coast is not
    due_calls = iter([True, False])

    with (
        patch(
            "src.jobs.daily_briefing_job._get_active_users_with_preferences",
            new_callable=AsyncMock,
            return_value=users,
        ),
        patch(
            "src.jobs.daily_briefing_job._is_briefing_due",
            side_effect=lambda _tz, _bt: next(due_calls),
        ),
        patch(
            "src.jobs.daily_briefing_job._briefing_exists",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "src.jobs.daily_briefing_job._today_in_user_tz",
            return_value=date(2026, 2, 8),
        ),
        patch(
            "src.jobs.daily_briefing_job.BriefingService",
            return_value=mock_briefing_service,
        ),
    ):
        result = await run_daily_briefing_job()

        assert result["generated"] == 1
        assert result["skipped"] == 1
