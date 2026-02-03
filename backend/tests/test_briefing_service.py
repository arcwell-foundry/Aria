"""Tests for briefing service."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_llm_response() -> MagicMock:
    """Create mock LLM response."""
    response = MagicMock()
    content = MagicMock()
    content.text = "Good morning! You have a light schedule today."
    response.content = [content]
    return response


@pytest.mark.asyncio
async def test_generate_briefing_creates_summary_with_llm(
    mock_llm_response: MagicMock,
) -> None:
    """Test generate_briefing uses LLM to create summary."""
    with (
        patch("src.services.briefing.SupabaseClient") as mock_db_class,
        patch("src.services.briefing.anthropic.Anthropic") as mock_llm_class,
    ):
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.generate_briefing(user_id="test-user-123")

        assert "summary" in result
        assert "calendar" in result
        assert "leads" in result
        assert "signals" in result
        assert "tasks" in result
        assert "generated_at" in result

        # Verify LLM was called for summary generation
        mock_llm_class.return_value.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_briefing_stores_result_in_db(
    mock_llm_response: MagicMock,
) -> None:
    """Test generate_briefing stores briefing in database."""
    with (
        patch("src.services.briefing.SupabaseClient") as mock_db_class,
        patch("src.services.briefing.anthropic.Anthropic") as mock_llm_class,
    ):
        # Setup DB mock
        mock_db = MagicMock()
        mock_upsert = MagicMock()
        mock_upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db.table.return_value.upsert = mock_upsert
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.generate_briefing(user_id="test-user-123")

        # Verify upsert was called
        mock_db.table.assert_called_with("daily_briefings")
        mock_upsert.assert_called_once()

        # Verify the call included user_id and content
        call_args = mock_upsert.call_args
        data = call_args[0][0] if call_args[0] else call_args[1][0]
        assert data["user_id"] == "test-user-123"
        assert "content" in data
        assert "briefing_date" in data


@pytest.mark.asyncio
async def test_get_briefing_returns_none_when_not_found() -> None:
    """Test get_briefing returns None when briefing doesn't exist."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        # Setup DB mock to return None
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.get_briefing(user_id="test-user-123")

        assert result is None


@pytest.mark.asyncio
async def test_get_briefing_returns_existing_briefing() -> None:
    """Test get_briefing returns existing briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        expected_briefing = {
            "id": "briefing-123",
            "user_id": "test-user-123",
            "briefing_date": "2026-02-02",
            "content": {"summary": "Existing briefing"},
        }
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=expected_briefing
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.get_briefing(user_id="test-user-123")

        assert result == expected_briefing


@pytest.mark.asyncio
async def test_get_or_generate_briefing_generates_when_not_exists(
    mock_llm_response: MagicMock,
) -> None:
    """Test get_or_generate_briefing generates new briefing when none exists."""
    with (
        patch("src.services.briefing.SupabaseClient") as mock_db_class,
        patch("src.services.briefing.anthropic.Anthropic") as mock_llm_class,
    ):
        # Setup DB mock to return None (not found)
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_upsert = MagicMock()
        mock_upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db.table.return_value.upsert = mock_upsert
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.get_or_generate_briefing(user_id="test-user-123")

        assert "summary" in result
        assert "calendar" in result


@pytest.mark.asyncio
async def test_get_or_generate_briefing_returns_existing_when_exists() -> None:
    """Test get_or_generate_briefing returns existing briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        existing_content = {"summary": "Existing briefing summary"}
        # Setup DB mock to return existing
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"content": existing_content}
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.get_or_generate_briefing(user_id="test-user-123")

        assert result == existing_content


@pytest.mark.asyncio
async def test_list_briefings_returns_recent_briefings() -> None:
    """Test list_briefings returns recent briefings."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        expected_briefings = [
            {"id": "briefing-1", "briefing_date": "2026-02-02"},
            {"id": "briefing-2", "briefing_date": "2026-02-01"},
        ]
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=expected_briefings
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.list_briefings(user_id="test-user-123", limit=7)

        assert len(result) == 2
        assert result == expected_briefings


@pytest.mark.asyncio
async def test_list_briefings_respects_limit_parameter() -> None:
    """Test list_briefings respects the limit parameter."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_order = MagicMock()
        mock_order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.order = mock_order
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        await service.list_briefings(user_id="test-user-123", limit=5)

        # Verify limit was passed correctly
        mock_order.return_value.limit.assert_called_once_with(5)


@pytest.mark.asyncio
async def test_get_calendar_data_returns_empty_dict_when_no_integration() -> None:
    """Test _get_calendar_data returns empty structure when calendar not integrated."""
    with patch("src.services.briefing.SupabaseClient"):
        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_calendar_data(
            user_id="test-user-123", briefing_date=date.today()
        )

        assert result == {"meeting_count": 0, "key_meetings": []}


@pytest.mark.asyncio
async def test_get_lead_data_returns_empty_dict_when_no_leads() -> None:
    """Test _get_lead_data returns empty structure when no leads."""
    with patch("src.services.briefing.SupabaseClient"):
        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_lead_data(user_id="test-user-123")

        assert result == {"hot_leads": [], "needs_attention": [], "recently_active": []}


@pytest.mark.asyncio
async def test_get_signal_data_returns_empty_dict_when_no_signals() -> None:
    """Test _get_signal_data returns empty structure when no signals."""
    with patch("src.services.briefing.SupabaseClient"):
        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_signal_data(user_id="test-user-123")

        assert result == {
            "company_news": [],
            "market_trends": [],
            "competitive_intel": [],
        }


@pytest.mark.asyncio
async def test_get_task_data_returns_empty_dict_when_no_tasks() -> None:
    """Test _get_task_data returns empty structure when no tasks."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        # Setup DB mock to return empty results
        mock_db = MagicMock()
        mock_table = MagicMock()

        # Both queries return empty data
        mock_table.select.return_value.eq.return_value.eq.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_table.select.return_value.eq.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_task_data(user_id="test-user-123")

        assert result == {"overdue": [], "due_today": []}


@pytest.mark.asyncio
async def test_generate_summary_calls_llm_with_context(
    mock_llm_response: MagicMock,
) -> None:
    """Test _generate_summary calls LLM with briefing context."""
    with (
        patch("src.services.briefing.SupabaseClient"),
        patch("src.services.briefing.anthropic.Anthropic") as mock_llm_class,
    ):
        # Setup LLM mock
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        from src.services.briefing import BriefingService

        service = BriefingService()
        calendar = {"meeting_count": 3}
        leads = {"needs_attention": ["lead-1", "lead-2"]}
        signals = {"company_news": ["news-1"]}
        tasks = {"overdue": ["task-1"]}

        result = await service._generate_summary(calendar, leads, signals, tasks)

        # Verify LLM was called
        mock_llm_class.return_value.messages.create.assert_called_once()
        call_kwargs = mock_llm_class.return_value.messages.create.call_args.kwargs
        assert "messages" in call_kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert "max_tokens" in call_kwargs


@pytest.mark.asyncio
async def test_generate_briefing_uses_custom_date_when_provided(
    mock_llm_response: MagicMock,
) -> None:
    """Test generate_briefing uses custom briefing_date when provided."""
    with (
        patch("src.services.briefing.SupabaseClient") as mock_db_class,
        patch("src.services.briefing.anthropic.Anthropic") as mock_llm_class,
    ):
        # Setup DB mock
        mock_db = MagicMock()
        mock_upsert = MagicMock()
        mock_upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db.table.return_value.upsert = mock_upsert
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        from src.services.briefing import BriefingService

        service = BriefingService()
        custom_date = date(2026, 2, 1)
        await service.generate_briefing(user_id="test-user-123", briefing_date=custom_date)

        # Verify the date was passed to upsert
        call_args = mock_upsert.call_args
        data = call_args[0][0] if call_args[0] else call_args[1][0]
        assert data["briefing_date"] == "2026-02-01"


@pytest.mark.asyncio
async def test_get_task_data_returns_overdue_tasks() -> None:
    """Test _get_task_data returns overdue tasks from prospective_memories."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        overdue_tasks = [
            {
                "id": "task-1",
                "task": "Follow up with Acme Corp",
                "priority": "high",
                "trigger_config": {"due_at": "2026-02-01T09:00:00Z"},
            },
        ]
        today_tasks = [
            {
                "id": "task-2",
                "task": "Send proposal",
                "priority": "medium",
                "trigger_config": {"due_at": "2026-02-03T17:00:00Z"},
            },
        ]

        # Setup DB mock for two separate queries
        mock_db = MagicMock()
        mock_table = MagicMock()

        # First call returns overdue, second call returns today
        mock_table.select.return_value.eq.return_value.eq.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=overdue_tasks
        )
        mock_table.select.return_value.eq.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=today_tasks
        )
        mock_db.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_task_data(user_id="test-user-123")

        assert "overdue" in result
        assert "due_today" in result

        # Verify overdue tasks are populated correctly
        assert len(result["overdue"]) == 1
        assert result["overdue"][0]["id"] == "task-1"
        assert result["overdue"][0]["task"] == "Follow up with Acme Corp"
        assert result["overdue"][0]["priority"] == "high"
        assert result["overdue"][0]["due_at"] == "2026-02-01T09:00:00Z"

        # Verify due_today tasks are populated correctly
        assert len(result["due_today"]) == 1
        assert result["due_today"][0]["id"] == "task-2"
        assert result["due_today"][0]["task"] == "Send proposal"
        assert result["due_today"][0]["priority"] == "medium"
        assert result["due_today"][0]["due_at"] == "2026-02-03T17:00:00Z"

        # Verify the table was queried
        mock_db.table.assert_called_with("prospective_memories")
