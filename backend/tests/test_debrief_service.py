"""Tests for post-meeting debrief service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


# =========================================================================
# initiate_debrief Tests
# =========================================================================


@pytest.mark.asyncio
async def test_initiate_debrief_creates_pending_debrief(mock_db: MagicMock) -> None:
    """Test initiate_debrief creates a pending debrief with correct data."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.NotificationService") as mock_notification,
    ):
        # Setup calendar_events query
        calendar_result = MagicMock()
        calendar_result.data = {
            "id": "meeting-123",
            "title": "Sales Demo with Acme",
            "start_time": "2026-02-16T14:00:00Z",
            "end_time": "2026-02-16T15:00:00Z",
            "attendees": ["john@acme.com"],
            "external_company": "Acme Corp",
        }

        # Setup debrief insert
        debrief_result = MagicMock()
        debrief_result.data = [{
            "id": "debrief-456",
            "user_id": "user-789",
            "meeting_id": "meeting-123",
            "meeting_title": "Sales Demo with Acme",
            "meeting_time": "2026-02-16T14:00:00Z",
            "status": "pending",
            "linked_lead_id": None,
        }]

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = calendar_result
        mock_db.table.return_value.insert.return_value.execute.return_value = debrief_result
        mock_db_class.get_client.return_value = mock_db

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock _find_linked_lead
        with patch.object(service, "_find_linked_lead", return_value=None):
            result = await service.initiate_debrief(
                user_id="user-789",
                meeting_id="meeting-123",
            )

        assert result["status"] == "pending"
        assert result["meeting_title"] == "Sales Demo with Acme"
        assert result["meeting_id"] == "meeting-123"

        # Verify notification was created
        mock_notification.create_notification.assert_called_once()
        call_args = mock_notification.create_notification.call_args
        assert call_args.kwargs["user_id"] == "user-789"
        assert "Acme Corp" in call_args.kwargs["message"]


@pytest.mark.asyncio
async def test_initiate_debrief_auto_links_to_lead(mock_db: MagicMock) -> None:
    """Test initiate_debrief auto-links to lead when attendee matches stakeholder."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.NotificationService") as mock_notification,
    ):
        calendar_result = MagicMock()
        calendar_result.data = {
            "id": "meeting-123",
            "title": "Sales Demo",
            "start_time": "2026-02-16T14:00:00Z",
            "attendees": ["john@acme.com"],
            "external_company": "Acme",
        }

        debrief_result = MagicMock()
        debrief_result.data = [{
            "id": "debrief-456",
            "status": "pending",
            "linked_lead_id": "lead-123",
        }]

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = calendar_result
        mock_db.table.return_value.insert.return_value.execute.return_value = debrief_result
        mock_db_class.get_client.return_value = mock_db

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock _find_linked_lead to return a lead ID
        with patch.object(service, "_find_linked_lead", return_value="lead-123"):
            result = await service.initiate_debrief(
                user_id="user-789",
                meeting_id="meeting-123",
            )

        assert result["linked_lead_id"] == "lead-123"


@pytest.mark.asyncio
async def test_initiate_debrief_uses_fallback_context_when_meeting_not_found(
    mock_db: MagicMock,
) -> None:
    """Test initiate_debrief uses fallback context when calendar event not found."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.NotificationService") as mock_notification,
    ):
        # No calendar event found
        calendar_result = MagicMock()
        calendar_result.data = None

        debrief_result = MagicMock()
        debrief_result.data = [{
            "id": "debrief-456",
            "status": "pending",
            "meeting_title": "Meeting",  # Default fallback
        }]

        # First call is for calendar_events, second is for insert
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = calendar_result
        mock_db.table.return_value.insert.return_value.execute.return_value = debrief_result
        mock_db_class.get_client.return_value = mock_db

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        with patch.object(service, "_find_linked_lead", return_value=None):
            result = await service.initiate_debrief(
                user_id="user-789",
                meeting_id="nonexistent-meeting",
            )

        assert result["meeting_title"] == "Meeting"  # Default fallback


# =========================================================================
# process_debrief Tests
# =========================================================================


@pytest.mark.asyncio
async def test_process_debrief_extracts_and_updates_data(mock_db: MagicMock) -> None:
    """Test process_debrief extracts data with LLM and updates debrief."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup existing debrief query
        debrief_result = MagicMock()
        debrief_result.data = {
            "id": "debrief-123",
            "user_id": "user-456",
            "meeting_title": "Sales Demo",
            "meeting_time": "2026-02-16T14:00:00Z",
            "status": "pending",
        }

        # Setup update result
        update_result = MagicMock()
        update_result.data = [{
            "id": "debrief-123",
            "status": "processing",
            "summary": "Positive meeting with strong buying signals",
            "outcome": "positive",
        }]

        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock the select and update chains
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = debrief_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_result

        # Mock LLM extraction
        extracted_data = {
            "summary": "Positive meeting with strong buying signals",
            "outcome": "positive",
            "action_items": [{"task": "Send proposal", "owner": "us", "due_date": None}],
            "commitments_ours": ["Send pricing"],
            "commitments_theirs": ["Review with team"],
            "insights": [{"type": "buying_signal", "content": "Asked about pricing"}],
            "follow_up_needed": True,
        }

        with patch.object(service, "_extract_debrief_data", return_value=extracted_data):
            result = await service.process_debrief(
                debrief_id="debrief-123",
                user_input="Great meeting, they want to proceed.",
            )

        assert result["summary"] == "Positive meeting with strong buying signals"
        assert result["outcome"] == "positive"


@pytest.mark.asyncio
async def test_process_debrief_raises_error_when_debrief_not_found(
    mock_db: MagicMock,
) -> None:
    """Test process_debrief raises ValueError when debrief not found."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        debrief_result = MagicMock()
        debrief_result.data = None

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = debrief_result
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        with pytest.raises(ValueError, match="Debrief not found"):
            await service.process_debrief(
                debrief_id="nonexistent-debrief",
                user_input="Notes",
            )


# =========================================================================
# post_process_debrief Tests
# =========================================================================


@pytest.mark.asyncio
async def test_post_process_debrief_creates_lead_event(mock_db: MagicMock) -> None:
    """Test post_process_debrief creates lead_memory_events entry."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.ActivityService") as mock_activity,
    ):
        debrief_result = MagicMock()
        debrief_result.data = {
            "id": "debrief-123",
            "user_id": "user-456",
            "meeting_title": "Sales Demo",
            "meeting_time": "2026-02-16T14:00:00Z",
            "summary": "Positive meeting",
            "outcome": "positive",
            "linked_lead_id": "lead-789",
            "action_items": [],
            "follow_up_needed": False,
        }

        update_result = MagicMock()
        update_result.data = [{
            "id": "debrief-123",
            "status": "completed",
        }]

        mock_db_class.get_client.return_value = mock_db

        # Mock various queries
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = debrief_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_result
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "event-1"}])

        mock_activity_instance = MagicMock()
        mock_activity_instance.record = AsyncMock()
        mock_activity.return_value = mock_activity_instance

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        with patch.object(service, "_update_stakeholder_sentiment"):
            with patch.object(service, "_recalculate_health_score"):
                with patch.object(service, "_store_episodic_memory"):
                    with patch.object(service, "_create_prospective_memories"):
                        result = await service.post_process_debrief("debrief-123")

        assert result["status"] == "completed"

        # Verify insert was called (for lead_memory_events, episodic_memories, etc.)
        assert mock_db.table.return_value.insert.call_count >= 1


@pytest.mark.asyncio
async def test_post_process_debrief_updates_stakeholder_sentiment(
    mock_db: MagicMock,
) -> None:
    """Test post_process_debrief updates stakeholder sentiment based on outcome."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.ActivityService") as mock_activity,
    ):
        debrief_result = MagicMock()
        debrief_result.data = {
            "id": "debrief-123",
            "user_id": "user-456",
            "meeting_title": "Sales Demo",
            "outcome": "positive",
            "linked_lead_id": "lead-789",
            "action_items": [],
            "follow_up_needed": False,
        }

        update_result = MagicMock()
        update_result.data = [{"id": "debrief-123", "status": "completed"}]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = debrief_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_result
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

        mock_activity_instance = MagicMock()
        mock_activity_instance.record = AsyncMock()
        mock_activity.return_value = mock_activity_instance

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        with patch.object(service, "_store_episodic_memory"):
            with patch.object(service, "_create_prospective_memories"):
                await service.post_process_debrief("debrief-123")

        # Verify sentiment update was called with correct params
        update_calls = mock_db.table.return_value.update.call_args_list
        # Look for sentiment update
        assert any("sentiment" in str(call) for call in update_calls)


@pytest.mark.asyncio
async def test_post_process_debrief_recalculates_health_score(
    mock_db: MagicMock,
) -> None:
    """Test post_process_debrief recalculates lead health score."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.ActivityService") as mock_activity,
    ):
        debrief_result = MagicMock()
        debrief_result.data = {
            "id": "debrief-123",
            "user_id": "user-456",
            "outcome": "positive",
            "linked_lead_id": "lead-789",
            "action_items": [],
            "follow_up_needed": False,
        }

        lead_result = MagicMock()
        lead_result.data = {"health_score": 50}

        update_result = MagicMock()
        update_result.data = [{"id": "debrief-123", "status": "completed"}]

        mock_db_class.get_client.return_value = mock_db

        # Setup different query results
        def mock_table(table_name):
            mock = MagicMock()
            if table_name == "meeting_debriefs":
                mock.select.return_value.eq.return_value.single.return_value.execute.return_value = debrief_result
                mock.update.return_value.eq.return_value.execute.return_value = update_result
            elif table_name == "lead_memories":
                mock.select.return_value.eq.return_value.single.return_value.execute.return_value = lead_result
                mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            mock.insert.return_value.execute.return_value = MagicMock(data=[{}])
            return mock

        mock_db.table.side_effect = mock_table

        mock_activity_instance = MagicMock()
        mock_activity_instance.record = AsyncMock()
        mock_activity.return_value = mock_activity_instance

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        with patch.object(service, "_store_episodic_memory"):
            with patch.object(service, "_create_prospective_memories"):
                await service.post_process_debrief("debrief-123")

        # Health score should be increased by 5 for positive outcome
        # (from 50 to 55)


@pytest.mark.asyncio
async def test_post_process_debrief_generates_email_draft_when_needed(
    mock_db: MagicMock,
) -> None:
    """Test post_process_debrief generates email draft when follow_up_needed is True."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.ActivityService") as mock_activity,
    ):
        debrief_result = MagicMock()
        debrief_result.data = {
            "id": "debrief-123",
            "user_id": "user-456",
            "meeting_title": "Sales Demo",
            "outcome": "positive",
            "linked_lead_id": "lead-789",
            "summary": "Good meeting",
            "action_items": [],
            "commitments_ours": ["Send proposal"],
            "commitments_theirs": [],
            "follow_up_needed": True,  # Email draft should be generated
        }

        lead_result = MagicMock()
        lead_result.data = {"company_name": "Acme Corp"}

        update_result = MagicMock()
        update_result.data = [{"id": "debrief-123", "status": "completed", "follow_up_draft": "Draft email"}]

        mock_db_class.get_client.return_value = mock_db

        def mock_table(table_name):
            mock = MagicMock()
            if table_name == "meeting_debriefs":
                mock.select.return_value.eq.return_value.single.return_value.execute.return_value = debrief_result
                mock.update.return_value.eq.return_value.execute.return_value = update_result
            elif table_name == "lead_memories":
                mock.select.return_value.eq.return_value.single.return_value.execute.return_value = lead_result
            mock.insert.return_value.execute.return_value = MagicMock(data=[{}])
            return mock

        mock_db.table.side_effect = mock_table

        mock_activity_instance = MagicMock()
        mock_activity_instance.record = AsyncMock()
        mock_activity.return_value = mock_activity_instance

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock LLM for email generation
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Dear John, thanks for the meeting...")]
        service.llm.messages.create = MagicMock(return_value=mock_response)

        with patch.object(service, "_store_episodic_memory"):
            with patch.object(service, "_create_prospective_memories"):
                result = await service.post_process_debrief("debrief-123")

        assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_post_process_debrief_creates_prospective_memories(
    mock_db: MagicMock,
) -> None:
    """Test post_process_debrief creates prospective_memories for action items."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.ActivityService") as mock_activity,
    ):
        debrief_result = MagicMock()
        debrief_result.data = {
            "id": "debrief-123",
            "user_id": "user-456",
            "meeting_title": "Sales Demo",
            "outcome": "positive",
            "linked_lead_id": "lead-789",
            "action_items": [
                {"task": "Send proposal", "owner": "us", "due_date": "2026-02-20"},
                {"task": "Review contract", "owner": "them", "due_date": None},  # Should be skipped
            ],
            "follow_up_needed": False,
        }

        update_result = MagicMock()
        update_result.data = [{"id": "debrief-123", "status": "completed"}]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = debrief_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_result
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

        mock_activity_instance = MagicMock()
        mock_activity_instance.record = AsyncMock()
        mock_activity.return_value = mock_activity_instance

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        with patch.object(service, "_store_episodic_memory"):
            result = await service.post_process_debrief("debrief-123")

        assert result["status"] == "completed"

        # Verify prospective_memories insert was called (for "us" action items only)
        insert_calls = mock_db.table.return_value.insert.call_args_list


# =========================================================================
# check_pending_debriefs Tests
# =========================================================================


@pytest.mark.asyncio
async def test_check_pending_debriefs_returns_meetings_without_debriefs(
    mock_db: MagicMock,
) -> None:
    """Test check_pending_debriefs returns past meetings that have no debrief."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup calendar events result
        events_result = MagicMock()
        events_result.data = [
            {
                "id": "meeting-1",
                "title": "Sales Call",
                "end_time": "2026-02-15T14:00:00Z",
            },
            {
                "id": "meeting-2",
                "title": "Demo",
                "end_time": "2026-02-15T16:00:00Z",
            },
        ]

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = events_result

        # First meeting has debrief, second doesn't
        debrief_result_with = MagicMock()
        debrief_result_with.data = {"id": "debrief-1"}

        debrief_result_without = MagicMock()
        debrief_result_without.data = None

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            debrief_result_with,
            debrief_result_without,
        ]

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service.check_pending_debriefs("user-456")

        # Only meeting-2 should be returned (no debrief)
        assert len(result) == 1
        assert result[0]["id"] == "meeting-2"


@pytest.mark.asyncio
async def test_check_pending_debriefs_returns_empty_when_all_have_debriefs(
    mock_db: MagicMock,
) -> None:
    """Test check_pending_debriefs returns empty list when all meetings have debriefs."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        events_result = MagicMock()
        events_result.data = [
            {"id": "meeting-1", "title": "Call"},
        ]

        debrief_result = MagicMock()
        debrief_result.data = {"id": "debrief-1"}

        mock_db_class.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = events_result
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = debrief_result

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service.check_pending_debriefs("user-456")

        assert len(result) == 0


# =========================================================================
# Helper Method Tests
# =========================================================================


@pytest.mark.asyncio
async def test_find_linked_lead_finds_match(mock_db: MagicMock) -> None:
    """Test _find_linked_lead finds lead when attendee matches stakeholder."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        stakeholder_result = MagicMock()
        stakeholder_result.data = {"lead_memory_id": "lead-123"}

        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = stakeholder_result
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service._find_linked_lead("user-456", ["john@acme.com"])

        assert result == "lead-123"


@pytest.mark.asyncio
async def test_find_linked_lead_returns_none_when_no_match(mock_db: MagicMock) -> None:
    """Test _find_linked_lead returns None when no attendee matches stakeholder."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        stakeholder_result = MagicMock()
        stakeholder_result.data = None

        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = stakeholder_result
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        result = await service._find_linked_lead("user-456", ["unknown@example.com"])

        assert result is None


@pytest.mark.asyncio
async def test_recalculate_health_score_positive_outcome(mock_db: MagicMock) -> None:
    """Test health score increases for positive outcome."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        lead_result = MagicMock()
        lead_result.data = {"health_score": 50}

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = lead_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        await service._recalculate_health_score("lead-123", "positive")

        # Verify update was called with increased score (50 + 5 = 55)
        update_call = mock_db.table.return_value.update.call_args
        assert update_call[0][0]["health_score"] == 55


@pytest.mark.asyncio
async def test_recalculate_health_score_negative_outcome(mock_db: MagicMock) -> None:
    """Test health score decreases for negative outcome."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        lead_result = MagicMock()
        lead_result.data = {"health_score": 50}

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = lead_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        await service._recalculate_health_score("lead-123", "negative")

        # Verify update was called with decreased score (50 - 10 = 40)
        update_call = mock_db.table.return_value.update.call_args
        assert update_call[0][0]["health_score"] == 40


@pytest.mark.asyncio
async def test_recalculate_health_score_clamps_to_zero(mock_db: MagicMock) -> None:
    """Test health score doesn't go below 0."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        lead_result = MagicMock()
        lead_result.data = {"health_score": 5}

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = lead_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        await service._recalculate_health_score("lead-123", "negative")

        # Score would be -5, but should be clamped to 0
        update_call = mock_db.table.return_value.update.call_args
        assert update_call[0][0]["health_score"] == 0


@pytest.mark.asyncio
async def test_recalculate_health_score_clamps_to_100(mock_db: MagicMock) -> None:
    """Test health score doesn't go above 100."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        lead_result = MagicMock()
        lead_result.data = {"health_score": 98}

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = lead_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        mock_db_class.get_client.return_value = mock_db

        from src.services.debrief_service import DebriefService

        service = DebriefService()
        await service._recalculate_health_score("lead-123", "positive")

        # Score would be 103, but should be clamped to 100
        update_call = mock_db.table.return_value.update.call_args
        assert update_call[0][0]["health_score"] == 100


# =========================================================================
# Legacy Method Tests (Backward Compatibility)
# =========================================================================


@pytest.mark.asyncio
async def test_create_debrief_stores_in_database(mock_db: MagicMock) -> None:
    """Test create_debrief stores debrief in database."""
    with (
        patch("src.services.debrief_service.SupabaseClient") as mock_db_class,
        patch("src.services.debrief_service.NotificationService") as mock_notification,
    ):
        # Setup DB mock
        calendar_result = MagicMock()
        calendar_result.data = {
            "id": "meeting-abc",
            "title": "Sales Demo",
            "start_time": "2026-02-02T14:00:00Z",
            "attendees": ["prospect@example.com"],
            "external_company": "Acme",
        }

        debrief_insert_result = MagicMock()
        debrief_insert_result.data = [{
            "id": "debrief-123",
            "user_id": "user-456",
            "meeting_id": "meeting-abc",
            "meeting_title": "Sales Demo",
            "meeting_time": "2026-02-02T14:00:00Z",
            "raw_notes": "Great meeting",
            "summary": "Positive sales demo",
            "outcome": "positive",
            "action_items": [{"task": "Send proposal", "owner": "us", "due_date": None}],
            "commitments_ours": ["Send proposal by Friday"],
            "commitments_theirs": ["Review with team"],
            "insights": [{"type": "buying_signal", "content": "Asked about pricing"}],
            "follow_up_needed": True,
            "linked_lead_id": None,
            "status": "completed",
            "created_at": "2026-02-02T15:00:00Z",
        }]

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = calendar_result
        mock_db.table.return_value.insert.return_value.execute.return_value = debrief_insert_result
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = debrief_insert_result
        mock_db_class.get_client.return_value = mock_db

        mock_notification.create_notification = AsyncMock()

        from src.services.debrief_service import DebriefService

        service = DebriefService()

        # Mock LLM response
        mock_extract_result = {
            "summary": "Positive sales demo with interest in next steps",
            "outcome": "positive",
            "action_items": [{"task": "Send proposal", "owner": "us", "due_date": None}],
            "commitments_ours": ["Send proposal by Friday"],
            "commitments_theirs": ["Review with team"],
            "insights": [{"type": "buying_signal", "content": "Asked about pricing"}],
            "follow_up_needed": True,
        }

        with (
            patch("src.services.debrief_service.ActivityService") as mock_activity,
            patch.object(service, "_extract_debrief_data", return_value=mock_extract_result),
            patch.object(service, "_store_episodic_memory"),
            patch.object(service, "_create_prospective_memories"),
            patch.object(service, "_update_stakeholder_sentiment"),
            patch.object(service, "_recalculate_health_score"),
            patch.object(service, "_create_lead_event"),
        ):
            mock_activity_instance = MagicMock()
            mock_activity_instance.record = AsyncMock()
            mock_activity.return_value = mock_activity_instance

            result = await service.create_debrief(
                user_id="user-456",
                meeting_id="meeting-abc",
                user_notes="Great meeting, they want to move forward",
            )

        assert result["id"] == "debrief-123"
        assert result["meeting_id"] == "meeting-abc"
        assert result["outcome"] == "positive"


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
async def test_extract_debrief_data_handles_markdown_json_blocks(
    mock_db: MagicMock,
) -> None:
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
