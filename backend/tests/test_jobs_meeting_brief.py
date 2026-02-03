"""Tests for meeting brief generation background job."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_job_finds_meetings_within_window() -> None:
    """Test that find_meetings_needing_briefs returns a list of pending briefs."""
    with patch("src.jobs.meeting_brief_generator.SupabaseClient") as mock_db_class:
        mock_briefs = [
            {
                "id": "brief-1",
                "user_id": "user-123",
                "calendar_event_id": "evt-1",
                "meeting_title": "Discovery Call",
                "meeting_time": "2026-02-04T14:00:00Z",
                "status": "pending",
                "attendees": ["john@example.com"],
            },
            {
                "id": "brief-2",
                "user_id": "user-456",
                "calendar_event_id": "evt-2",
                "meeting_title": "Follow-up",
                "meeting_time": "2026-02-04T16:00:00Z",
                "status": "pending",
                "attendees": ["jane@example.com"],
            },
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(
            data=mock_briefs
        )
        mock_db_class.get_client.return_value = mock_db

        from src.jobs.meeting_brief_generator import find_meetings_needing_briefs

        result = await find_meetings_needing_briefs(hours_ahead=24)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "brief-1"
        assert result[1]["id"] == "brief-2"


@pytest.mark.asyncio
async def test_job_finds_meetings_returns_empty_list_when_none() -> None:
    """Test that find_meetings_needing_briefs returns empty list when no pending briefs."""
    with patch("src.jobs.meeting_brief_generator.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.jobs.meeting_brief_generator import find_meetings_needing_briefs

        result = await find_meetings_needing_briefs(hours_ahead=24)

        assert isinstance(result, list)
        assert len(result) == 0


@pytest.mark.asyncio
async def test_run_meeting_brief_job_returns_summary() -> None:
    """Test that run_meeting_brief_job returns summary with expected keys."""
    with (
        patch("src.jobs.meeting_brief_generator.SupabaseClient") as mock_db_class,
        patch("src.jobs.meeting_brief_generator.MeetingBriefService") as mock_service_class,
    ):
        mock_briefs = [
            {
                "id": "brief-1",
                "user_id": "user-123",
                "calendar_event_id": "evt-1",
                "meeting_title": "Discovery Call",
                "meeting_time": "2026-02-04T14:00:00Z",
                "status": "pending",
                "attendees": ["john@example.com"],
            },
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(
            data=mock_briefs
        )
        mock_db_class.get_client.return_value = mock_db

        # Mock the service's generate_brief_content
        mock_service = MagicMock()

        async def mock_generate(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"summary": "Test brief content"}

        mock_service.generate_brief_content = mock_generate
        mock_service_class.return_value = mock_service

        from src.jobs.meeting_brief_generator import run_meeting_brief_job

        result = await run_meeting_brief_job(hours_ahead=24)

        assert isinstance(result, dict)
        assert "meetings_found" in result
        assert "briefs_generated" in result
        assert "errors" in result
        assert "hours_ahead" in result
        assert result["meetings_found"] == 1
        assert result["briefs_generated"] == 1
        assert result["errors"] == 0
        assert result["hours_ahead"] == 24


@pytest.mark.asyncio
async def test_run_meeting_brief_job_handles_errors() -> None:
    """Test that run_meeting_brief_job tracks errors when generation fails."""
    with (
        patch("src.jobs.meeting_brief_generator.SupabaseClient") as mock_db_class,
        patch("src.jobs.meeting_brief_generator.MeetingBriefService") as mock_service_class,
    ):
        mock_briefs = [
            {
                "id": "brief-1",
                "user_id": "user-123",
                "calendar_event_id": "evt-1",
                "meeting_title": "Discovery Call",
                "meeting_time": "2026-02-04T14:00:00Z",
                "status": "pending",
                "attendees": ["john@example.com"],
            },
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(
            data=mock_briefs
        )
        mock_db_class.get_client.return_value = mock_db

        # Mock the service to return None (failure)
        mock_service = MagicMock()

        async def mock_generate_fail(*_args: object, **_kwargs: object) -> None:
            return None

        mock_service.generate_brief_content = mock_generate_fail
        mock_service_class.return_value = mock_service

        from src.jobs.meeting_brief_generator import run_meeting_brief_job

        result = await run_meeting_brief_job(hours_ahead=24)

        assert result["meetings_found"] == 1
        assert result["briefs_generated"] == 0
        assert result["errors"] == 1


@pytest.mark.asyncio
async def test_run_meeting_brief_job_with_no_pending_briefs() -> None:
    """Test that run_meeting_brief_job handles no pending briefs gracefully."""
    with (
        patch("src.jobs.meeting_brief_generator.SupabaseClient") as mock_db_class,
        patch("src.jobs.meeting_brief_generator.MeetingBriefService"),
    ):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.jobs.meeting_brief_generator import run_meeting_brief_job

        result = await run_meeting_brief_job(hours_ahead=48)

        assert result["meetings_found"] == 0
        assert result["briefs_generated"] == 0
        assert result["errors"] == 0
        assert result["hours_ahead"] == 48
