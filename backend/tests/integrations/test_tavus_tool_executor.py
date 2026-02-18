"""Tests for VideoToolExecutor — Scribe Digital Twin integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_draft_email_loads_digital_twin_style():
    """draft_email should load Digital Twin fingerprint and pass style to ScribeAgent."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")

    # Mock LLM
    executor._llm = MagicMock()

    # Mock DB for recipient profile lookup
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    executor._db = mock_db

    # Mock DigitalTwin.get_fingerprint
    mock_fingerprint = MagicMock()
    mock_fingerprint.greeting_style = "Hi"
    mock_fingerprint.sign_off_style = "Best"
    mock_fingerprint.formality_score = 0.8

    with patch("src.memory.digital_twin.DigitalTwin") as MockDT:
        mock_dt_instance = AsyncMock()
        mock_dt_instance.get_fingerprint.return_value = mock_fingerprint
        MockDT.return_value = mock_dt_instance

        with patch("src.agents.ScribeAgent") as MockScribe:
            mock_agent = AsyncMock()
            mock_agent._call_tool.return_value = {
                "subject": "Follow up",
                "body": "Hi there...",
                "word_count": 42,
            }
            MockScribe.return_value = mock_agent

            result = await executor._handle_draft_email({
                "to": "jane@lonza.com",
                "subject_context": "follow up on bioreactor demo",
                "tone": "formal",
            })

            # Verify Digital Twin was queried
            mock_dt_instance.get_fingerprint.assert_called_once_with("user-123")

            # Verify style was passed to ScribeAgent._call_tool
            call_kwargs = mock_agent._call_tool.call_args
            assert "style" in call_kwargs.kwargs or (len(call_kwargs.args) > 4)
            # Check style has Digital Twin values
            style_arg = call_kwargs.kwargs.get("style", {})
            assert style_arg.get("preferred_greeting") == "Hi"
            assert style_arg.get("signature") == "Best"

            assert result.spoken_text  # Should have content


@pytest.mark.asyncio
async def test_draft_email_recipient_profile_overrides_digital_twin():
    """Per-recipient writing profile should override Digital Twin defaults."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-456")
    executor._llm = MagicMock()

    # DB returns a per-recipient profile
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "greeting_style": "Dear",
            "signoff_style": "Kind regards",
            "formality_level": 0.9,
            "tone": "warm",
        }]
    )
    executor._db = mock_db

    mock_fingerprint = MagicMock()
    mock_fingerprint.greeting_style = "Hi"
    mock_fingerprint.sign_off_style = "Best"
    mock_fingerprint.formality_score = 0.5

    with patch("src.memory.digital_twin.DigitalTwin") as MockDT:
        mock_dt_instance = AsyncMock()
        mock_dt_instance.get_fingerprint.return_value = mock_fingerprint
        MockDT.return_value = mock_dt_instance

        with patch("src.agents.ScribeAgent") as MockScribe:
            mock_agent = AsyncMock()
            mock_agent._call_tool.return_value = {
                "subject": "Quarterly review",
                "body": "Dear Dr. Smith...",
                "word_count": 88,
            }
            MockScribe.return_value = mock_agent

            result = await executor._handle_draft_email({
                "to": "smith@pharma.com",
                "subject_context": "quarterly review follow-up",
                "tone": "formal",
            })

            call_kwargs = mock_agent._call_tool.call_args
            style_arg = call_kwargs.kwargs.get("style", {})
            # Recipient profile should override Digital Twin
            assert style_arg.get("preferred_greeting") == "Dear"
            assert style_arg.get("signature") == "Kind regards"
            assert style_arg.get("formality") == "formal"

            # Tone from recipient profile should override default
            assert call_kwargs.kwargs.get("tone") == "warm"

            assert result.spoken_text


@pytest.mark.asyncio
async def test_draft_email_graceful_fallback_on_digital_twin_failure():
    """If DigitalTwin raises, draft_email should still work with empty style."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-789")
    executor._llm = MagicMock()
    executor._db = MagicMock()

    with patch("src.memory.digital_twin.DigitalTwin") as MockDT:
        mock_dt_instance = AsyncMock()
        mock_dt_instance.get_fingerprint.side_effect = Exception("Graphiti down")
        MockDT.return_value = mock_dt_instance

        with patch("src.agents.ScribeAgent") as MockScribe:
            mock_agent = AsyncMock()
            mock_agent._call_tool.return_value = {
                "subject": "Quick note",
                "body": "Hello...",
                "word_count": 20,
            }
            MockScribe.return_value = mock_agent

            result = await executor._handle_draft_email({
                "to": "bob@example.com",
                "subject_context": "quick check-in",
            })

            # Should still produce a result even if DT failed
            assert result.spoken_text
            assert "bob@example.com" in result.spoken_text

            # Style should be empty dict (fallback)
            call_kwargs = mock_agent._call_tool.call_args
            style_arg = call_kwargs.kwargs.get("style", {})
            assert style_arg == {}


@pytest.mark.asyncio
async def test_get_battle_card_generates_via_strategist_when_not_in_db():
    """When no battle card exists in DB, Strategist should generate one."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")
    executor._llm = MagicMock()

    # Mock DB — battle_cards returns empty, then insert succeeds
    mock_db = MagicMock()
    # First call: battle_cards select returns empty
    mock_select = MagicMock()
    mock_select.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_select
    # Insert call
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "card-1"}])
    executor._db = mock_db

    with patch("src.agents.StrategistAgent") as MockStrat:
        mock_agent = AsyncMock()
        mock_agent._call_tool.return_value = {
            "target_company": "Catalent",
            "opportunities": ["Strong mAb portfolio"],
            "challenges": ["High pricing"],
            "recommendation": "Lead with cost efficiency",
            "competitive_analysis": {
                "competitors": [{"name": "Catalent", "strengths": ["Scale"], "weaknesses": ["Slow"]}],
            },
        }
        MockStrat.return_value = mock_agent

        result = await executor._handle_get_battle_card({"competitor_name": "Catalent"})

        # Strategist should have been invoked
        mock_agent._call_tool.assert_called_once()
        assert "Catalent" in result.spoken_text
        assert result.rich_content is not None
        assert result.rich_content["type"] == "battle_card"


@pytest.mark.asyncio
async def test_execute_stores_episodic_memory_on_success():
    """Successful tool execution should store an episodic memory."""
    from src.integrations.tavus_tool_executor import ToolResult, VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")
    executor._llm = MagicMock()
    executor._db = MagicMock()

    # Stub a handler that returns successfully
    async def mock_handler(_args):
        return ToolResult(spoken_text="Found 3 articles on CAR-T therapy.")

    with (
        patch.object(executor, "_handle_search_pubmed", mock_handler),
        patch.object(executor, "_log_activity", new_callable=AsyncMock),
        patch.object(executor, "_store_episodic", new_callable=AsyncMock) as mock_store,
    ):
        await executor.execute("search_pubmed", {"query": "CAR-T"})

        mock_store.assert_called_once()
        call_args = mock_store.call_args
        assert call_args[0][0] == "search_pubmed"  # tool_name
        assert call_args[0][1] == {"query": "CAR-T"}  # arguments
        assert call_args[0][2].spoken_text == "Found 3 articles on CAR-T therapy."


@pytest.mark.asyncio
async def test_trigger_goal_action_runs_ooda_cycle():
    """trigger_goal_action should find a matching goal and run one OODA iteration."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")
    executor._llm = MagicMock()

    # Mock DB — goals table returns a matching goal
    mock_db = MagicMock()
    mock_goals_result = MagicMock()
    mock_goals_result.data = [
        {
            "id": "goal-1",
            "title": "Expand into cell therapy market",
            "description": "Target cell therapy CDMOs",
            "goal_type": "research",
            "config": {},
            "progress": 25,
            "status": "active",
        }
    ]
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_goals_result
    executor._db = mock_db

    with patch("src.core.ooda.OODALoop") as MockOODA:
        mock_ooda = AsyncMock()
        mock_state = MagicMock()
        mock_state.is_complete = False
        mock_state.is_blocked = False
        mock_state.decision = {"action": "research", "agent": "analyst", "reasoning": "Need more data"}
        mock_state.action_result = {"summary": "Found 5 cell therapy CDMOs"}
        mock_ooda.run_single_iteration.return_value = mock_state
        MockOODA.return_value = mock_ooda

        with (
            patch("src.memory.episodic.EpisodicMemory"),
            patch("src.memory.semantic.SemanticMemory"),
            patch("src.memory.working.WorkingMemory"),
        ):
            result = await executor._handle_trigger_goal_action({
                "goal_description": "cell therapy"
            })

        assert "cell therapy" in result.spoken_text.lower() or "research" in result.spoken_text.lower()
        mock_ooda.run_single_iteration.assert_called_once()
