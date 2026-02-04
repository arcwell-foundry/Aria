"""Tests for MeetingBriefService."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_brief_returns_none_when_not_found() -> None:
    """Test get_brief returns None when brief doesn't exist."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_brief(user_id="user-123", calendar_event_id="evt-456")

        assert result is None


@pytest.mark.asyncio
async def test_get_brief_returns_brief_when_found() -> None:
    """Test get_brief returns brief when it exists."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "completed",
            "brief_content": {"summary": "Test summary"},
            "generated_at": "2026-02-03T14:00:00Z",
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_brief
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_brief(user_id="user-123", calendar_event_id="evt-456")

        assert result is not None
        assert result["id"] == "brief-123"


@pytest.mark.asyncio
async def test_create_brief_inserts_pending_brief() -> None:
    """Test create_brief creates a pending brief record."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "pending",
            "brief_content": {},
        }

        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[mock_brief]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.create_brief(
            user_id="user-123",
            calendar_event_id="evt-456",
            meeting_title="Discovery Call",
            meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=UTC),
            attendees=["john@example.com"],
        )

        assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_get_upcoming_meetings_returns_list() -> None:
    """Test get_upcoming_meetings returns meetings with brief status."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_briefs = [
            {
                "id": "brief-1",
                "calendar_event_id": "evt-1",
                "meeting_title": "Call 1",
                "meeting_time": "2026-02-04T14:00:00Z",
                "status": "completed",
                "attendees": ["a@example.com"],
            },
            {
                "id": "brief-2",
                "calendar_event_id": "evt-2",
                "meeting_title": "Call 2",
                "meeting_time": "2026-02-05T10:00:00Z",
                "status": "pending",
                "attendees": ["b@example.com"],
            },
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=mock_briefs
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_upcoming_meetings(user_id="user-123", limit=10)

        assert len(result) == 2
        assert result[0]["calendar_event_id"] == "evt-1"


@pytest.mark.asyncio
async def test_get_brief_by_id_returns_none_when_not_found() -> None:
    """Test get_brief_by_id returns None when brief doesn't exist."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_brief_by_id(user_id="user-123", brief_id="brief-999")

        assert result is None


@pytest.mark.asyncio
async def test_get_brief_by_id_returns_brief_when_found() -> None:
    """Test get_brief_by_id returns brief when it exists."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "completed",
            "brief_content": {"summary": "Test summary"},
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_brief
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_brief_by_id(user_id="user-123", brief_id="brief-123")

        assert result is not None
        assert result["id"] == "brief-123"


@pytest.mark.asyncio
async def test_update_brief_status_updates_status() -> None:
    """Test update_brief_status updates the status field."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "status": "generating",
        }

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[mock_brief]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.update_brief_status(
            user_id="user-123",
            brief_id="brief-123",
            status="generating",
        )

        assert result is not None
        assert result["status"] == "generating"


@pytest.mark.asyncio
async def test_update_brief_status_with_content() -> None:
    """Test update_brief_status can update content and generated_at."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "status": "completed",
            "brief_content": {"summary": "Test content"},
            "generated_at": "2026-02-03T14:00:00Z",
        }

        mock_db = MagicMock()
        mock_update = MagicMock()
        mock_update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[mock_brief]
        )
        mock_db.table.return_value.update = mock_update
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.update_brief_status(
            user_id="user-123",
            brief_id="brief-123",
            status="completed",
            brief_content={"summary": "Test content"},
        )

        assert result is not None
        assert result["status"] == "completed"
        assert result["brief_content"] == {"summary": "Test content"}

        # Verify update was called with content and generated_at
        call_args = mock_update.call_args
        update_data = call_args[0][0]
        assert "brief_content" in update_data
        assert "generated_at" in update_data


@pytest.mark.asyncio
async def test_update_brief_status_with_error_message() -> None:
    """Test update_brief_status can set error message for failed briefs."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "status": "failed",
            "error_message": "Research failed: API timeout",
        }

        mock_db = MagicMock()
        mock_update = MagicMock()
        mock_update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[mock_brief]
        )
        mock_db.table.return_value.update = mock_update
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.update_brief_status(
            user_id="user-123",
            brief_id="brief-123",
            status="failed",
            error_message="Research failed: API timeout",
        )

        assert result is not None
        assert result["status"] == "failed"
        assert result["error_message"] == "Research failed: API timeout"


@pytest.mark.asyncio
async def test_update_brief_status_returns_none_when_not_found() -> None:
    """Test update_brief_status returns None when brief doesn't exist."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.update_brief_status(
            user_id="user-123",
            brief_id="nonexistent-brief",
            status="generating",
        )

        assert result is None


@pytest.mark.asyncio
async def test_upsert_brief_creates_new_brief() -> None:
    """Test upsert_brief creates a new brief when none exists."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "pending",
            "brief_content": {},
        }

        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[mock_brief]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.upsert_brief(
            user_id="user-123",
            calendar_event_id="evt-456",
            meeting_title="Discovery Call",
            meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=UTC),
            attendees=["john@example.com"],
        )

        assert result["id"] == "brief-123"
        assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_create_brief_stores_attendees() -> None:
    """Test create_brief stores attendee list correctly."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "attendees": ["john@example.com", "jane@example.com"],
            "status": "pending",
        }

        mock_db = MagicMock()
        mock_insert = MagicMock()
        mock_insert.return_value.execute.return_value = MagicMock(data=[mock_brief])
        mock_db.table.return_value.insert = mock_insert
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        await service.create_brief(
            user_id="user-123",
            calendar_event_id="evt-456",
            meeting_title="Team Meeting",
            meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=UTC),
            attendees=["john@example.com", "jane@example.com"],
        )

        # Verify insert was called with attendees
        call_args = mock_insert.call_args
        insert_data = call_args[0][0]
        assert insert_data["attendees"] == ["john@example.com", "jane@example.com"]


@pytest.mark.asyncio
async def test_get_upcoming_meetings_orders_by_meeting_time() -> None:
    """Test get_upcoming_meetings orders results by meeting_time ascending."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_order = MagicMock()
        mock_order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order = (
            mock_order
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        await service.get_upcoming_meetings(user_id="user-123", limit=10)

        # Verify order was called with meeting_time ascending
        mock_order.assert_called_once_with("meeting_time", desc=False)


@pytest.mark.asyncio
async def test_generate_brief_content_creates_brief() -> None:
    """Test generate_brief_content calls LLM and updates brief."""
    with (
        patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
        patch("src.services.meeting_brief.anthropic.Anthropic") as mock_llm_class,
        patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
        patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
    ):
        # Setup DB mock
        mock_db = MagicMock()
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "pending",
            "attendees": ["john@acme.com"],
        }
        # For get_brief_by_id
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_brief
        )
        # For update calls
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{**mock_brief, "status": "completed"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_response = MagicMock()
        mock_llm_content = MagicMock()
        mock_llm_content.text = '{"summary": "Meeting with Acme Corp", "suggested_agenda": ["Intro"], "risks_opportunities": []}'
        mock_llm_response.content = [mock_llm_content]
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        # Setup profile service mock - make it async
        mock_profile_service = MagicMock()

        async def mock_get_profiles(
            *_args: object, **_kwargs: object
        ) -> dict[str, dict[str, object]]:
            return {
                "john@acme.com": {
                    "email": "john@acme.com",
                    "name": "John Smith",
                    "title": "VP Sales",
                    "company": "Acme Corp",
                    "profile_data": {},
                }
            }

        mock_profile_service.get_profiles_batch = mock_get_profiles
        mock_profile_class.return_value = mock_profile_service

        # Setup Scout agent mock - make it async
        mock_scout = MagicMock()

        async def mock_execute(*_args: object, **_kwargs: object) -> MagicMock:
            return MagicMock(
                success=True,
                data=[{"company_name": "Acme Corp", "headline": "Raised funding"}],
            )

        mock_scout.execute = mock_execute
        mock_scout.validate_input.return_value = True
        mock_scout_class.return_value = mock_scout

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.generate_brief_content(
            user_id="user-123",
            brief_id="brief-123",
        )

        assert result is not None
        assert "summary" in result
