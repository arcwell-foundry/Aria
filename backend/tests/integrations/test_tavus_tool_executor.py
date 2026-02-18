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
