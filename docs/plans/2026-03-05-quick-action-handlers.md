# Quick Action Handlers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add quick action handlers to ChatService that query Supabase and synthesize immediate responses using the conversational LLM — no goal creation, no agent spawning.

 no execution plans.

**Architecture:** The quick action system uses a three-step pipeline:
1) `_gather_quick_action_data` queries Supabase tables based on action_type
2) `_build_quick_action_prompt` creates a synthesis prompt with data
3) `_synthesize_quick_action_response` calls the conversational LLM and saves messages to DB

**Tech Stack:** Python 3.11+ / FastAPI / Supabase / Anthropic Claude API (via LLMClient)

**Key Design Decisions:**
- Reuse existing LLMClient infrastructure (not LLMGateway - that doesn't exist)
- Follow existing patterns in ChatService for DB operations
- Action type routing via if/elif for 7 action types
- All responses use Jarvis voice: specific, opinionated, concise

---

## Task 1: Add _gather_quick_action_data Method

**Files:**
- Modify: `backend/src/services/chat.py` (add after `_classify_intent` method, ~line 1080)

**Step 1: Write the data gathering method**

Add this method after `_classify_intent` (around line 1080):

```python
    async def _gather_quick_action_data(self, user_id: str, action_type: str, message: str) -> dict[str, Any]:
        """Query Supabase for data relevant to the quick action.

        Args:
            user_id: The user's ID for filtering user-specific data
            action_type: The type of quick action (meeting_prep, calendar_query, etc.)
            message: The user's original message (for potential parsing)

        Returns:
            Dictionary containing data relevant to the action type.
            Empty dict on error (logged, not raised).
        """
        try:
            db = get_supabase_client()
            data: dict[str, Any] = {}

            if action_type == "meeting_prep":
                # Upcoming meetings
                meetings = db.table("calendar_events").select(
                    "title, start_time, end_time, attendees"
                ).eq("user_id", user_id).gt(
                    "start_time", "now()"
                ).order("start_time").limit(5).execute()
                data["meetings"] = meetings.data or []

                # Relevant signals for meeting companies
                signals = db.table("market_signals").select(
                    "company_name, headline, signal_type, detected_at"
                ).eq("user_id", user_id).order("detected_at", desc=True).limit(5).execute()
                data["signals"] = signals.data or []

                # Battle cards
                battle_cards = db.table("battle_cards").select(
                    "competitor_name, overview, strengths, weaknesses, differentiation"
                ).limit(10).execute()
                data["battle_cards"] = battle_cards.data or []

                # Pending drafts for meeting contacts
                drafts = db.table("email_drafts").select(
                    "recipient_name, subject, status"
                ).eq("user_id", user_id).eq("status", "draft").limit(5).execute()
                data["drafts"] = drafts.data or []

            elif action_type == "calendar_query":
                meetings = db.table("calendar_events").select(
                    "title, start_time, end_time, attendees"
                ).eq("user_id", user_id).gt(
                    "start_time", "now()"
                ).order("start_time").limit(10).execute()
                data["meetings"] = meetings.data or []

            elif action_type == "signal_review":
                signals = db.table("market_signals").select(
                    "company_name, headline, summary, signal_type, relevance_score, source_url, detected_at"
                ).eq("user_id", user_id).order("detected_at", desc=True).limit(10).execute()
                data["signals"] = signals.data or []

            elif action_type == "draft_review":
                drafts = db.table("email_drafts").select(
                    "recipient_name, subject, status, created_at"
                ).eq("user_id", user_id).eq("status", "draft").order(
                    "created_at", desc=True
                ).limit(10).execute()
                data["drafts"] = drafts.data or []

            elif action_type == "task_review":
                tasks = db.table("goals").select(
                    "title, status, description, created_at"
                ).eq("user_id", user_id).in_(
                    "status", ["draft", "active", "plan_ready", "in_progress"]
                ).order("created_at", desc=True).limit(10).execute()
                data["tasks"] = tasks.data or []

            elif action_type == "pipeline_review":
                leads = db.table("leads").select("*").eq(
                    "user_id", user_id
                ).order("created_at", desc=True).limit(10).execute()
                data["leads"] = leads.data or []
                goals = db.table("goals").select(
                    "title, status, description"
                ).eq("user_id", user_id).in_(
                    "status", ["draft", "active", "plan_ready", "in_progress"]
                ).limit(10).execute()
                data["goals"] = goals.data or []

            elif action_type == "competitive_lookup":
                battle_cards = db.table("battle_cards").select("*").limit(10).execute()
                data["battle_cards"] = battle_cards.data or []
                signals = db.table("market_signals").select(
                    "company_name, headline, signal_type, detected_at"
                ).eq("user_id", user_id).order("detected_at", desc=True).limit(5).execute()
                data["signals"] = signals.data or []

            return data
        except Exception as e:
            logger.error("Quick action data gather failed: %s", e, exc_info=True)
            return {}
```

**Step 2: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.services.chat import ChatService; print('Syntax OK')"`
Expected: `Syntax OK`

---

## Task 2: Add _build_quick_action_prompt Method

**Files:**
- Modify: `backend/src/services/chat.py` (add after `_gather_quick_action_data`)

**Step 1: Write the prompt builder method**

Add this static method after `_gather_quick_action_data`:

```python
    def _build_quick_action_prompt(self, action_type: str, data: dict[str, Any], user_message: str) -> str:
        """Build a synthesis prompt with gathered data for the LLM.

        Args:
            action_type: The type of quick action
            data: Dictionary containing the gathered data
            user_message: The user's original message

        Returns:
            Formatted prompt string for the LLM to synthesize a response.
        """
        import json as _json

        data_json = _json.dumps(data, indent=2, default=str)

        prompts = {
            "meeting_prep": (
                "The user asked you to prepare for a meeting. You have their calendar, "
                "market signals, battle cards, and email drafts below. "
                "Synthesize a concise, actionable meeting brief. Include: who they are meeting, "
                "key context about attendees/companies, any relevant signals or news, "
                "suggested talking points, and any pending drafts for those contacts. "
                "Be specific and opinionated. Do NOT propose a research plan or execution plan.\n\n"
            ),
            "calendar_query": (
                "The user asked about their calendar/schedule. You have their upcoming "
                "meetings below. Answer directly with times in Eastern Time. Be concise. "
                "Filter out buffer events (titles containing 'buffer'). Do NOT propose a plan.\n\n"
            ),
            "signal_review": (
                "The user wants to review market signals/intelligence. You have their "
                "latest signals below. Summarize the most important ones, "
                "grouped by company or type. Highlight anything that needs attention. "
                "Be concise and opinionated. Do NOT propose a research plan.\n\n"
            ),
            "draft_review": (
                "The user wants to review their email drafts. You have their pending "
                "drafts below. Summarize what is waiting: who it is for, the subject, and "
                "recommend which to send first. Do NOT propose a plan.\n\n"
            ),
            "task_review": (
                "The user wants to review their tasks/goals. You have their active "
                "tasks below. Summarize what is open, what is overdue, and recommend priorities. "
                "Be direct and opinionated. Do NOT propose a plan.\n\n"
            ),
            "pipeline_review": (
                "The user wants to see their pipeline. You have their leads and goals below. "
                "Summarize the current state, highlight risks or opportunities, and "
                "recommend next actions. Do NOT propose a plan.\n\n"
            ),
            "competitive_lookup": (
                "The user wants competitive intelligence. You have battle cards and "
                "competitor signals below. Give a direct competitive comparison with strengths, "
                "weaknesses, and recent moves. Be opinionated. Do NOT propose a plan.\n\n"
            ),
        }

        base = prompts.get(
            action_type,
            "Answer the user's question using the available data. Be direct and concise.\n\n"
        )

        return (
            f"{base}"
            f'User request: "{user_message}"\n\n'
            f"Available data from database:\n{data_json}\n\n"
            "CRITICAL RULES:\n"
            "- Respond directly with the information. NO execution plans. NO 'Here is my plan'. NO 'Let me break this down'.\n"
            "- Use the Jarvis voice: specific, opinionated, concise.\n"
            "- Format times in Eastern Time (user timezone is America/New_York).\n"
            "- If the data is insufficient, say what you know and offer to research deeper.\n"
        )
```

**Step 2: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.services.chat import ChatService; print('Syntax OK')"`
Expected: `Syntax OK`

---

## Task 3: Add _synthesize_quick_action_response Method

**Files:**
- Modify: `backend/src/services/chat.py` (add after `_build_quick_action_prompt`)

**Step 1: Write the LLM synthesis method**

Add this async method after `_build_quick_action_prompt`:

```python
    async def _synthesize_quick_action_response(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        action_type: str,
        synthesis_prompt: str,
        conversation_messages: list,
        working_memory: Any,
    ) -> dict[str, Any]:
        """Use conversational LLM to synthesize a quick action response.

        Args:
            user_id: The user's ID
            conversation_id: The conversation ID
            message: The user's original message
            action_type: The type of quick action (for logging)
            synthesis_prompt: The pre-built synthesis prompt with data
            conversation_messages: Recent conversation history
            working_memory: Working memory object (may be None)

        Returns:
            Dictionary with response, conversation_id, intent, and action_type.
        """
        # Build system prompt
        try:
            if self._use_persona_builder:
                system_prompt = await self._build_system_prompt_v2(user_id, [], None)
            else:
                system_prompt = ARIA_SYSTEM_PROMPT
        except Exception:
            system_prompt = ARIA_SYSTEM_PROMPT

        enhanced_prompt = (
            f"{system_prompt}\n\n"
            "## QUICK ACTION CONTEXT\n"
            "The user is asking a question you can answer from existing data. "
            "Respond immediately with the information below. Do NOT create a goal "
            "or execution plan. Do NOT say 'let me break this down' or propose phases.\n\n"
            f"{synthesis_prompt}"
        )

        # Build messages for LLM
        messages: list[dict[str, str]] = [{"role": "system", "content": enhanced_prompt}]
        for msg in conversation_messages[-6:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        # Use existing LLMClient
        llm = LLMClient()
        response = await llm.generate_response(
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
            user_id=user_id,
            task=TaskType.CHAT_RESPONSE,
        )

        assistant_content = response.strip()

        # Save to DB
        db = get_supabase_client()
        db.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "user",
            "content": message,
        }).execute()
        db.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": assistant_content,
        }).execute()

        # Update working memory if available
        if working_memory:
            working_memory.add_message("user", message)
            working_memory.add_message("assistant", assistant_content)

        logger.info(
            "Quick action response generated: action_type=%s, response_len=%d",
            action_type,
            len(assistant_content),
        )

        return {
            "response": assistant_content,
            "conversation_id": conversation_id,
            "intent": "quick_action",
            "action_type": action_type,
        }
```

**Step 2: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.services.chat import ChatService; print('Syntax OK')"`
Expected: `Syntax OK`

---

## Task 4: Add _handle_quick_action Method

**Files:**
- Modify: `backend/src/services/chat.py` (add after `_synthesize_quick_action_response`)

**Step 1: Write the main handler method**

Add this async method after `_synthesize_quick_action_response`

```python
    async def _handle_quick_action(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        intent: dict[str, Any],
        working_memory: Any,
        conversation_messages: list,
    ) -> dict[str, Any]:
        """Handle quick action requests by querying existing data and synthesizing a response.

        This is the main entry point for quick action handling. It orchestrates:
        1. Gathering relevant data from Supabase
        2. Building a synthesis prompt with the data
        3. Calling the LLM to synthesize a natural response

        Args:
            user_id: The user's ID
            conversation_id: The conversation ID
            message: The user's original message
            intent: The intent dict containing action_type
            working_memory: Working memory object (may be None)
            conversation_messages: Recent conversation history

        Returns:
            Dictionary with response, conversation_id, intent, and action_type.
        """
        action_type = intent.get("action_type", "")

        # Gather relevant data from Supabase
        context_data = await self._gather_quick_action_data(user_id, action_type, message)

        # Build synthesis prompt
        synthesis_prompt = self._build_quick_action_prompt(action_type, context_data, message)

        # Synthesize response using conversational LLM
        response = await self._synthesize_quick_action_response(
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
            action_type=action_type,
            synthesis_prompt=synthesis_prompt,
            conversation_messages=conversation_messages,
            working_memory=working_memory,
        )

        return response
```

**Step 2: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.services.chat import ChatService; print('Syntax OK')"`
Expected: `Syntax OK`

---

## Task 5: Write Tests for Quick Action Handlers

**Files:**
- Create: `backend/tests/test_quick_action_handlers.py`

**Step 1: Write the test file**

Create `backend/tests/test_quick_action_handlers.py`:

```python
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

            # Mock responses for each query
            mock_db.table.return_value.select.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"title": "Demo with Acme", "start_time": "2026-03-06T10:00:00Z", "end_time": "2026-03-06T11:00:00Z", "attendees": []},
                ]
            )
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"company_name": "Acme Corp", "headline": "Acme raises Series B", "signal_type": "funding", "detected_at": "2026-03-05T12:00:00Z"},
                ]
            )
            mock_db.table.return_value.select.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"competitor_name": "CompetitorX", "overview": "A competitor", "strengths": ["price"], "weaknesses": ["features"], "differentiation": "Cheaper"},
                ]
            )
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"recipient_name": "John Doe", "subject": "Follow up", "status": "draft"},
                ]
            )

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "meeting_prep", "prepare for my meeting"
            )

            assert "meetings" in result
            assert len(result["meetings"]) == 1
            assert result["meetings"][0]["title"] == "Demo with Acme"
            assert "signals" in result
            assert "battle_cards" in result
            assert "drafts" in result

    @pytest.mark.asyncio
    async def test_gather_calendar_query_data(self, chat_service):
        """Test that calendar_query gathers upcoming meetings."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_db.table.return_value.select.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"title": "Team Sync", "start_time": "2026-03-06T09:00:00Z", "end_time": "2026-03-06T09:30:00Z", "attendees": []},
                ]
            )

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "calendar_query", "what meetings do I have today"
            )

            assert "meetings" in result
            assert len(result["meetings"]) == 1

    @pytest.mark.asyncio
    async def test_gather_signal_review_data(self, chat_service):
        """Test that signal_review gathers market signals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"company_name": "BioTech Inc", "headline": "New drug approved", "summary": "FDA approval received", "signal_type": "regulatory", "relevance_score": 0.9, "source_url": "https://example.com", "detected_at": "2026-03-05T10:00:00Z"},
                ]
            )

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "signal_review", "show me recent signals"
            )

            assert "signals" in result
            assert len(result["signals"]) == 1
            assert result["signals"][0]["company_name"] == "BioTech Inc"

    @pytest.mark.asyncio
    async def test_gather_task_review_data(self, chat_service):
        """Test that task_review gathers active goals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"title": "Q1 Pipeline Review", "status": "in_progress", "description": "Review Q1 pipeline", "created_at": "2026-03-01T00:00:00Z"},
                ]
            )

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "task_review", "what tasks do I have"
            )

            assert "tasks" in result
            assert len(result["tasks"]) == 1

    @pytest.mark.asyncio
    async def test_gather_pipeline_review_data(self, chat_service):
        """Test that pipeline_review gathers leads and goals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            # First call for leads
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.side_effect = [
                MagicMock(data=[{"id": "lead-1", "company_name": "Acme"}]),
                MagicMock(data=[{"title": "Close Acme Deal", "status": "active"}]),
            ]

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

            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.side_effect = MagicMock(
                data=[
                    {"recipient_name": "Jane Smith", "subject": "Proposal Follow-up", "status": "draft", "created_at": "2026-03-04T00:00:00Z"},
                ]
            )

            result = await chat_service._gather_quick_action_data(
                "test-user-id", "draft_review", "any drafts waiting"
            )

            assert "drafts" in result
            assert len(result["drafts"]) == 1

    @pytest.mark.asyncio
    async def test_gather_competitive_lookup_data(self, chat_service):
        """Test that competitive_lookup gathers battle cards and signals."""
        with patch("src.services.chat.get_supabase_client") as mock_get_supabase:
            mock_db = MagicMock()
            mock_get_supabase.return_value = mock_db

            mock_db.table.return_value.select.return_value.limit.return_value.execute.side_effect = [
                MagicMock(data=[{"competitor_name": "CompetitorA", "overview": "Big competitor"}]),
                MagicMock(data=[{"company_name": "CompetitorA", "headline": "New product launch"}]),
            ]

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
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_quick_action_handlers.py -v`
Expected: All tests pass

---

## Task 6: Verify All Methods Exist

**Files:**
- Verify: `backend/src/services/chat.py`

**Step 1: Run verification command**

Run: `cd /Users/dhruv/aria/backend && python -c "
from src.services.chat import ChatService
import inspect

# Verify all methods exist
service = ChatService
methods = ['_handle_quick_action', '_gather_quick_action_data', '_build_quick_action_prompt', '_synthesize_quick_action_response']
for method in methods:
    assert hasattr(service, method), f'Method {method} not found'
    assert callable(getattr(service, method)), f'Method {method} is not callable'
print('All methods verified')
"`
Expected: `All methods verified`

---

## Task 7: Commit Changes

**Files:**
- Modify: `backend/src/services/chat.py`
- Create: `backend/tests/test_quick_action_handlers.py`

**Step 1: Stage and commit the changes**

```bash
cd /Users/dhruv/aria/backend
git add src/services/chat.py tests/test_quick_action_handlers.py
git commit -m "$(cat <<'EOF'
feat(chat): Add quick action handlers for immediate data queries

Implements three methods for handling quick actions:
- _gather_quick_action_data: Queries Supabase tables based on action_type
- _build_quick_action_prompt: Creates synthesis prompts with gathered data
- _synthesize_quick_action_response: Uses LLM to generate natural responses
- _handle_quick_action: Orchestrates the three-step pipeline

Quick actions query EXISTING data and synthesize immediate responses.
No goal creation, no execution plans, no agent spawning.

Action types supported:
- meeting_prep: Calendar + signals + battle cards + drafts
- calendar_query: Upcoming meetings
- signal_review: Market signals
- draft_review: Pending email drafts
- task_review: Active goals
- pipeline_review: Leads + goals
- competitive_lookup: Battle cards + competitor signals

Tests cover all action types and edge cases.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

**Step 2: Verify commit**

Run: `git log -1 --oneline`
Expected: Shows the new commit

---

## Summary

This plan adds four methods to ChatService:
1. `_gather_quick_action_data` - Queries Supabase for relevant data
2. `_build_quick_action_prompt` - Builds LLM prompt with data
3. `_synthesize_quick_action_response` - Generates natural response via LLM
4. `_handle_quick_action` - Orchestrates the pipeline

All methods use existing infrastructure (LLMClient, get_supabase_client, ARIA_SYSTEM_PROMPT).
Tests cover all 7 action types plus error handling.
