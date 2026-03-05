"""Tests for ChatService quick action handlers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.chat import ChatService


class TestQuickActionDataGathering:
    """Tests for _gather_quick_action_data method."""

    @pytest.fixture
    def chat_service(self):
        """Create a ChatService instance for testing."""
        return ChatService()

    @pytest.mark.asyncio
    async def test_gather_meeting_prep_data(self, chat_service):
        """Test that meeting_prep gathers meetings, signals, battle cards, and drafts."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            # Mock chain for meetings query
            mock_meetings_chain = MagicMock()
            mock_meetings_chain.execute.return_value = MagicMock(
                data=[
                    {"title": "Demo with Acme", "start_time": "2026-03-06T10:00:00Z", "end_time": "2026-03-06T11:00:00Z", "attendees": []},
                ]
            )
            mock_db.table.return_value.select.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value = mock_meetings_chain

            # Mock chain for signals query
            mock_signals_chain = MagicMock()
            mock_signals_chain.execute.return_value = MagicMock(
                data=[
                    {"company_name": "Acme Corp", "headline": "Acme raises Series B", "signal_type": "funding", "detected_at": "2026-03-05T12:00:00Z"},
                ]
            )
            # Set up side effects for multiple different query chains
            calls = [mock_meetings_chain, mock_signals_chain]

            def get_next_chain(*args, **kwargs):
                return calls.pop(0) if calls else MagicMock()

            mock_db.table.return_value.select.return_value.eq.return_value.gt.return_value.order.return_value.limit = get_next_chain

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "meeting_prep", "prepare for my meeting"
            )

            assert "meetings" in result
            assert "signals" in result

    @pytest.mark.asyncio
    async def test_gather_calendar_query_data(self, chat_service):
        """Test that calendar_query gathers upcoming meetings."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_chain = MagicMock()
            mock_chain.execute.return_value = MagicMock(
                data=[
                    {"title": "Team Sync", "start_time": "2026-03-06T09:00:00Z", "end_time": "2026-03-06T09:30:00Z", "attendees": []},
                ]
            )
            mock_db.table.return_value.select.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value = mock_chain

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "calendar_query", "what meetings do I have today"
            )

            assert "meetings" in result

    @pytest.mark.asyncio
    async def test_gather_signal_review_data(self, chat_service):
        """Test that signal_review gathers market signals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_chain = MagicMock()
            mock_chain.execute.return_value = MagicMock(
                data=[
                    {"company_name": "BioTech Inc", "headline": "New drug approved", "summary": "FDA approval received", "signal_type": "regulatory", "relevance_score": 0.9, "source_url": "https://example.com", "detected_at": "2026-03-05T10:00:00Z"},
                ]
            )
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value = mock_chain

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "signal_review", "show me recent signals"
            )

            assert "signals" in result
            assert result["signals"][0]["company_name"] == "BioTech Inc"

    @pytest.mark.asyncio
    async def test_gather_task_review_data(self, chat_service):
        """Test that task_review gathers active goals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_chain = MagicMock()
            mock_chain.execute.return_value = MagicMock(
                data=[
                    {"title": "Q1 Pipeline Review", "status": "in_progress", "description": "Review Q1 pipeline", "created_at": "2026-03-01T00:00:00Z"},
                ]
            )
            mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value = mock_chain

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "task_review", "what tasks do I have"
            )

            assert "tasks" in result

    @pytest.mark.asyncio
    async def test_gather_pipeline_review_data(self, chat_service):
        """Test that pipeline_review gathers leads and goals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            # First call for leads
            mock_leads_chain = MagicMock()
            mock_leads_chain.execute.return_value = MagicMock(data=[{"id": "lead-1", "company_name": "Acme"}])
            # Second call for goals
            mock_goals_chain = MagicMock()
            mock_goals_chain.execute.return_value = MagicMock(data=[{"title": "Close Acme Deal", "status": "active"}])

            calls = [mock_leads_chain, mock_goals_chain]

            def get_next_chain(*args, **kwargs):
                return calls.pop(0) if calls else MagicMock()

            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit = get_next_chain

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "pipeline_review", "show my pipeline"
            )

            assert "leads" in result
            assert "goals" in result

    @pytest.mark.asyncio
    async def test_gather_draft_review_data(self, chat_service):
        """Test that draft_review gathers pending email drafts."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_chain = MagicMock()
            mock_chain.execute.return_value = MagicMock(
                data=[
                    {"recipient_name": "Jane Smith", "subject": "Proposal Follow-up", "status": "draft", "created_at": "2026-03-04T00:00:00Z"},
                ]
            )
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value = mock_chain

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "draft_review", "any drafts waiting"
            )

            assert "drafts" in result

    @pytest.mark.asyncio
    async def test_gather_competitive_lookup_data(self, chat_service):
        """Test that competitive_lookup gathers battle cards and signals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            # First call for battle_cards: db.table("battle_cards").select("*").limit(10).execute()
            mock_battle_chain = MagicMock()
            mock_battle_chain.execute.return_value = MagicMock(data=[{"competitor_name": "CompetitorA", "overview": "Big competitor"}])

            # Second call for signals: db.table("market_signals").select(...).eq(...).order(...).limit(5).execute()
            mock_signals_chain = MagicMock()
            mock_signals_chain.execute.return_value = MagicMock(data=[{"company_name": "CompetitorA", "headline": "New product launch"}])

            # Track which table is being queried
            table_calls = {"battle_cards": mock_battle_chain, "market_signals": mock_signals_chain}

            def mock_table(table_name):
                mock_table_obj = MagicMock()
                if table_name in table_calls:
                    mock_table_obj.select.return_value.limit.return_value = table_calls[table_name]
                    # For signals, also need the eq().order().limit() chain
                    if table_name == "market_signals":
                        mock_table_obj.select.return_value.eq.return_value.order.return_value.limit.return_value = table_calls[table_name]
                else:
                    mock_table_obj.select.return_value.limit.return_value = MagicMock()
                    mock_table_obj.select.return_value.eq.return_value.order.return_value.limit.return_value = MagicMock()
                return mock_table_obj

            mock_db.table.side_effect = mock_table

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "competitive_lookup", "compare vs CompetitorA"
            )

            assert "battle_cards" in result
            assert "signals" in result

    @pytest.mark.asyncio
    async def test_gather_data_handles_exception(self, chat_service):
        """Test that _gather_quick_action_data handles exceptions gracefully."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_get_supabase.side_effect = Exception("Database connection failed")

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "calendar_query", "what meetings"
            )

            # Should return empty dict on error
            assert result == {}


class TestBuildQuickActionPrompt:
    """Tests for _build_quick_action_prompt method."""

    @pytest.fixture
    def chat_service(self):
        """Create a ChatService instance for testing."""
        return ChatService()

    def test_build_meeting_prep_prompt(self, chat_service):
        """Test that meeting_prep prompt includes all key elements."""
        data = {
            "meetings": [{"title": "Client Call", "start_time": "2026-03-06T14:00:00Z"}],
            "signals": [{"company_name": "Client Inc", "headline": "CEO change"}],
            "battle_cards": [{"competitor_name": "Rival"}],
            "drafts": [{"recipient_name": "John", "subject": "Follow-up"}],
        }

        prompt = chat_service._build_quick_action_prompt(
            "meeting_prep", data, "prepare for my meeting"
        )

        assert "prepare for a meeting" in prompt.lower()
        assert "Client Call" in prompt
        assert "Client Inc" in prompt
        assert "Rival" in prompt
        assert "John" in prompt
        assert "CRITICAL RULES" in prompt

    def test_build_calendar_query_prompt(self, chat_service):
        """Test that calendar_query prompt includes timezone instruction."""
        data = {"meetings": [{"title": "Sync", "start_time": "2026-03-06T09:00:00Z"}]}

        prompt = chat_service._build_quick_action_prompt(
            "calendar_query", data, "what's on my calendar"
        )

        assert "calendar" in prompt.lower()
        assert "Eastern Time" in prompt
        assert "Sync" in prompt

    def test_build_signal_review_prompt(self, chat_service):
        """Test that signal_review prompt asks for summary."""
        data = {"signals": [{"company_name": "Acme", "headline": "Funding round"}]}

        prompt = chat_service._build_quick_action_prompt(
            "signal_review", data, "show signals"
        )

        assert "market signals" in prompt.lower()
        assert "Acme" in prompt
        assert "Funding round" in prompt

    def test_build_unknown_action_type_prompt(self, chat_service):
        """Test that unknown action_type falls back to generic prompt."""
        data = {"some_data": "value"}

        prompt = chat_service._build_quick_action_prompt(
            "unknown_type", data, "some question"
        )

        assert "direct and concise" in prompt.lower()
        assert "some question" in prompt


class TestHandleQuickAction:
    """Tests for _handle_quick_action method."""

    @pytest.fixture
    def chat_service(self):
        """Create a ChatService instance for testing."""
        return ChatService()

    @pytest.mark.asyncio
    async def test_handle_quick_action_orchestrates_methods(self, chat_service):
        """Test that _handle_quick_action calls all the sub-methods."""
        intent = {"action_type": "calendar_query", "is_quick_action": True}

        with patch.object(chat_service, "_gather_quick_action_data") as mock_gather, \
             patch.object(chat_service, "_build_quick_action_prompt") as mock_build, \
             patch.object(chat_service, "_synthesize_quick_action_response") as mock_synthesize:

            mock_gather.return_value = {"meetings": []}
            mock_build.return_value = "test prompt"
            mock_synthesize.return_value = {
                "response": "You have no meetings today.",
                "conversation_id": "conv-123",
                "intent": "quick_action",
                "action_type": "calendar_query",
            }

            result = await chat_service._handle_quick_action(
                user_id="user-123",
                conversation_id="conv-123",
                message="what meetings do I have",
                intent=intent,
                working_memory=None,
                conversation_messages=[],
            )

            mock_gather.assert_called_once_with("user-123", "calendar_query", "what meetings do I have")
            mock_build.assert_called_once_with("calendar_query", {"meetings": []}, "what meetings do I have")
            mock_synthesize.assert_called_once()

            assert result["intent"] == "quick_action"
            assert result["action_type"] == "calendar_query"
