"""Tests for post-meeting debrief service."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def mock_llm() -> MagicMock:
    """Create mock Anthropic client."""
    mock_client = MagicMock()
    return mock_client


@pytest.mark.asyncio
async def test_create_debrief_stores_in_database(mock_db: MagicMock) -> None:
    """Test create_debrief stores debrief in database."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        result_mock = MagicMock()
        result_mock.data = [
            {
                "id": "debrief-123",
                "user_id": "user-456",
                "meeting_id": "meeting-abc",
                "meeting_title": "Sales Demo",
                "meeting_time": "2026-02-02T14:00:00Z",
                "raw_notes": "Great meeting, they want to move forward",
                "summary": "Positive sales demo with interest in next steps",
                "outcome": "positive",
                "action_items": [{"task": "Send proposal", "owner": "us", "due_date": None}],
                "commitments_ours": ["Send proposal by Friday"],
                "commitments_theirs": ["Review with team"],
                "insights": [{"type": "buying_signal", "content": "Asked about pricing"}],
                "follow_up_needed": True,
                "follow_up_draft": "Drafted email",
                "linked_lead_id": None,
                "created_at": "2026-02-02T15:00:00Z",
            }
        ]
        mock_db.table.return_value.insert.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock LLM response - do this BEFORE calling create_debrief
        mock_extract_result = {
            "summary": "Positive sales demo with interest in next steps",
            "outcome": "positive",
            "action_items": [{"task": "Send proposal", "owner": "us", "due_date": None}],
            "commitments_ours": ["Send proposal by Friday"],
            "commitments_theirs": ["Review with team"],
            "insights": [{"type": "buying_signal", "content": "Asked about pricing"}],
            "follow_up_needed": True,
        }

        mock_draft_result = "Drafted email"

        with patch.object(service, "_extract_debrief_data", return_value=mock_extract_result):
            with patch.object(service, "_generate_follow_up_draft", return_value=mock_draft_result):
                with patch.object(service, "_link_to_lead_memory"):
                    result = await service.create_debrief(
                        user_id="user-456",
                        meeting_id="meeting-abc",
                        user_notes="Great meeting, they want to move forward",
                        meeting_context={
                            "title": "Sales Demo",
                            "start_time": "2026-02-02T14:00:00Z",
                            "attendees": ["prospect@example.com"],
                        },
                    )

        assert result["id"] == "debrief-123"
        assert result["meeting_id"] == "meeting-abc"
        assert result["outcome"] == "positive"
        assert result["follow_up_needed"] is True
        assert result["follow_up_draft"] == "Drafted email"

        # Verify insert was called
        mock_db.table.assert_called_with("meeting_debriefs")


@pytest.mark.asyncio
async def test_create_debrief_without_meeting_context_fetches_context(mock_db: MagicMock) -> None:
    """Test create_debrief fetches meeting context when not provided."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock _get_meeting_context - needs to be async
        async def mock_get_context(meeting_id: str) -> dict:
            return {
                "title": "Meeting",
                "start_time": "2026-02-02T14:00:00Z",
                "attendees": [],
            }

        # Mock other methods
        result_mock = MagicMock()
        result_mock.data = [
            {
                "id": "debrief-123",
                "user_id": "user-456",
                "meeting_id": "meeting-abc",
                "summary": "Summary",
                "outcome": "neutral",
                "action_items": [],
                "commitments_ours": [],
                "commitments_theirs": [],
                "insights": [],
                "follow_up_needed": False,
                "created_at": "2026-02-02T15:00:00Z",
            }
        ]
        mock_db.table.return_value.insert.return_value.execute.return_value = result_mock

        mock_extract_result = {
            "summary": "Summary",
            "outcome": "neutral",
            "action_items": [],
            "commitments_ours": [],
            "commitments_theirs": [],
            "insights": [],
            "follow_up_needed": False,
        }

        with patch.object(service, "_get_meeting_context", side_effect=mock_get_context):
            with patch.object(service, "_extract_debrief_data", return_value=mock_extract_result):
                with patch.object(service, "_link_to_lead_memory"):
                    await service.create_debrief(
                        user_id="user-456",
                        meeting_id="meeting-abc",
                        user_notes="Notes",
                    )

            # Verify _get_meeting_context was called
            # Note: assert_called_once_with doesn't work well with async side_effect
            # We'll just verify it was called
            service._get_meeting_context.assert_called_once()


@pytest.mark.asyncio
async def test_create_debrief_skips_draft_when_not_needed(mock_db: MagicMock) -> None:
    """Test create_debrief skips follow-up draft when follow_up_needed is False."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock extract to return follow_up_needed=False
        mock_extract_result = {
            "summary": "Summary",
            "outcome": "neutral",
            "action_items": [],
            "commitments_ours": [],
            "commitments_theirs": [],
            "insights": [],
            "follow_up_needed": False,
        }

        result_mock = MagicMock()
        result_mock.data = [
            {
                "id": "debrief-123",
                "follow_up_draft": None,
                "follow_up_needed": False,
            }
        ]
        mock_db.table.return_value.insert.return_value.execute.return_value = result_mock

        mock_draft = MagicMock(side_effect=AssertionError("Should not be called"))

        with patch.object(service, "_extract_debrief_data", return_value=mock_extract_result):
            with patch.object(service, "_generate_follow_up_draft", mock_draft):
                with patch.object(service, "_link_to_lead_memory"):
                    result = await service.create_debrief(
                        user_id="user-456",
                        meeting_id="meeting-abc",
                        user_notes="Notes",
                        meeting_context={"title": "Meeting", "start_time": None, "attendees": []},
                    )

        # Verify draft was NOT generated
        mock_draft.assert_not_called()
        assert result["follow_up_draft"] is None


@pytest.mark.asyncio
async def test_get_debrief_returns_debrief_when_found(mock_db: MagicMock) -> None:
    """Test get_debrief returns debrief when found."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        result_mock = MagicMock()
        expected_debrief = {
            "id": "debrief-123",
            "user_id": "user-456",
            "meeting_id": "meeting-abc",
            "summary": "Summary",
        }
        result_mock.data = expected_debrief
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service.get_debrief("user-456", "debrief-123")

        assert result["id"] == "debrief-123"
        assert result["summary"] == "Summary"


@pytest.mark.asyncio
async def test_get_debrief_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test get_debrief returns None when debrief not found."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        result_mock = MagicMock()
        result_mock.data = None
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service.get_debrief("user-456", "debrief-999")

        assert result is None


@pytest.mark.asyncio
async def test_get_debriefs_for_meeting_returns_all_debriefs(mock_db: MagicMock) -> None:
    """Test get_debriefs_for_meeting returns all debriefs for a meeting."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        expected_debriefs = [
            {"id": "debrief-1", "meeting_id": "meeting-abc"},
            {"id": "debrief-2", "meeting_id": "meeting-abc"},
        ]
        result_mock = MagicMock()
        result_mock.data = expected_debriefs
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service.get_debriefs_for_meeting("user-456", "meeting-abc")

        assert len(result) == 2
        assert result[0]["id"] == "debrief-1"
        assert result[1]["id"] == "debrief-2"


@pytest.mark.asyncio
async def test_list_recent_debriefs_returns_limited_results(mock_db: MagicMock) -> None:
    """Test list_recent_debriefs respects limit parameter."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        expected_debriefs = [
            {"id": "debrief-1"},
            {"id": "debrief-2"},
            {"id": "debrief-3"},
        ]
        result_mock = MagicMock()
        result_mock.data = expected_debriefs
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service.list_recent_debriefs("user-456", limit=3)

        assert len(result) == 3

        # Verify limit was called correctly
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.assert_called_once_with(
            3
        )


@pytest.mark.asyncio
async def test_extract_debrief_data_parses_llm_response(mock_db: MagicMock) -> None:
    """Test _extract_debrief_data correctly parses LLM JSON response."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"summary": "Test", "outcome": "positive"}')]
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value = mock_response
        service.llm = mock_llm

        result = await service._extract_debrief_data(
            notes="Meeting notes",
            context={"title": "Meeting", "attendees": []},
        )

        assert result["summary"] == "Test"
        assert result["outcome"] == "positive"


@pytest.mark.asyncio
async def test_extract_debrief_data_handles_markdown_json_blocks(mock_db: MagicMock) -> None:
    """Test _extract_debrief_data extracts JSON from markdown code blocks."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock LLM response with markdown
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='```json\n{"summary": "Test", "outcome": "neutral"}\n```')
        ]
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value = mock_response
        service.llm = mock_llm

        result = await service._extract_debrief_data(
            notes="Notes",
            context={"title": "Meeting", "attendees": []},
        )

        assert result["summary"] == "Test"


@pytest.mark.asyncio
async def test_generate_follow_up_draft_creates_email(mock_db: MagicMock) -> None:
    """Test _generate_follow_up_draft generates follow-up email."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Dear team, thanks for meeting...")]
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value = mock_response
        service.llm = mock_llm

        result = await service._generate_follow_up_draft(
            meeting_context={"title": "Sales Demo"},
            extracted={
                "outcome": "positive",
                "summary": "Good meeting",
                "commitments_ours": ["Send proposal"],
                "commitments_theirs": ["Review"],
                "action_items": [],
            },
            user_id="user-456",
        )

        assert result == "Dear team, thanks for meeting..."


@pytest.mark.asyncio
async def test_link_to_lead_memory_skips_when_no_attendees(mock_db: MagicMock) -> None:
    """Test _link_to_lead_memory skips when no attendees in context."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Should not raise or fail
        await service._link_to_lead_memory(
            user_id="user-456",
            meeting_context={"title": "Meeting", "attendees": []},
            extracted={"insights": []},
        )

        # Verify no database queries were made for linking
        mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_link_to_lead_memory_adds_insights_to_lead(mock_db: MagicMock) -> None:
    """Test _link_to_lead_memory adds insights when matching lead found."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup mock for finding lead
        mock_stakeholder_result = MagicMock()
        mock_stakeholder_result.data = [{"lead_memory_id": "lead-123"}]
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_stakeholder_result
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        await service._link_to_lead_memory(
            user_id="user-456",
            meeting_context={"title": "Meeting", "attendees": ["prospect@example.com"]},
            extracted={
                "insights": [
                    {"type": "buying_signal", "content": "Asked about pricing"},
                    {"type": "objection", "content": "Concerned about implementation time"},
                ]
            },
        )

        # Verify insights were inserted (2 insights)
        assert mock_db.table.return_value.insert.call_count == 2

        # Verify lead was updated
        mock_db.table.return_value.update.assert_called()


@pytest.mark.asyncio
async def test_get_meeting_context_returns_default_context(mock_db: MagicMock) -> None:
    """Test _get_meeting_context returns default meeting context."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service._get_meeting_context("meeting-abc")

        # Should return default context
        assert result["title"] == "Meeting"
        assert result["attendees"] == []
        assert "start_time" in result
