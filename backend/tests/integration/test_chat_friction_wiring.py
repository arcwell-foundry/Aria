"""Tests for Cognitive Friction wiring in ChatService."""

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch


@dataclass
class FakeFrictionDecision:
    """Minimal stand-in for FrictionDecision to avoid importing real module."""

    level: str
    reasoning: str
    user_message: str | None
    proceed_if_confirmed: bool


def _make_chat_service():
    """Build a ChatService with all dependencies mocked out."""
    from src.services.chat import ChatService

    svc = ChatService.__new__(ChatService)
    svc._llm_client = MagicMock()
    svc._llm_client.generate_response = AsyncMock(return_value="Sure, I'll do that.")
    svc._working_memory_manager = MagicMock()
    svc._working_memory_manager.get_or_create = AsyncMock(
        return_value=MagicMock(
            add_message=MagicMock(),
            get_context_for_llm=MagicMock(return_value=[]),
        )
    )
    svc._memory_service = MagicMock()
    svc._memory_service.query = AsyncMock(return_value=[])
    svc._cognitive_monitor = MagicMock()
    svc._cognitive_monitor.estimate_load = AsyncMock(
        return_value=MagicMock(
            level=MagicMock(value="low"),
            score=0.1,
            recommendation="",
        )
    )
    svc._web_grounding = MagicMock()
    svc._web_grounding.detect_and_ground = AsyncMock(return_value=None)
    svc._email_check = MagicMock()
    svc._email_check.detect_email_check_request = MagicMock(return_value=False)
    svc._proactive_service = MagicMock()
    svc._proactive_service.get_insights = AsyncMock(return_value=[])
    svc._companion_orchestrator = None
    svc._personality_calibrator = MagicMock()
    svc._personality_calibrator.get_calibration = AsyncMock(return_value=None)
    svc._digital_twin = MagicMock()
    svc._digital_twin.get_style_guidelines = AsyncMock(return_value=None)
    svc._priming_service = MagicMock()
    svc._priming_service.get_priming_context = AsyncMock(return_value=None)
    svc._episodic_memory = MagicMock()
    svc._episodic_memory.store_episode = AsyncMock()
    svc._extraction_service = MagicMock()
    svc._extraction_service.extract_and_store = AsyncMock()
    svc._use_persona_builder = False
    svc._persona_builder = None
    svc._skill_registry = None
    svc._skill_orchestrator = None
    svc._skill_registry_initialized = True
    svc._friction_engine = None
    svc._trust_service = None
    svc.persist_turn = AsyncMock()
    svc._ensure_conversation_record = AsyncMock()
    return svc


class TestChatFrictionWiring:
    """Verify CognitiveFriction is called before skill routing."""

    @pytest.mark.asyncio
    async def test_challenge_returns_early_with_pushback(self):
        """When friction returns 'challenge', process_message returns pushback."""
        svc = _make_chat_service()

        challenge_decision = FakeFrictionDecision(
            level="challenge",
            reasoning="Risk detected",
            user_message="I'd push back on that -- the CFO asked for ROI data.",
            proceed_if_confirmed=True,
        )

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(return_value=challenge_decision)
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message(
                "user-1", "conv-1", "Send proposal without ROI section"
            )

        assert result["message"] == challenge_decision.user_message
        assert result["rich_content"][0]["type"] == "friction_decision"
        assert result["rich_content"][0]["data"]["level"] == "challenge"
        assert result["rich_content"][0]["data"]["proceed_if_confirmed"] is True
        # LLM should NOT have been called
        svc._llm_client.generate_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_refuse_returns_early(self):
        """When friction returns 'refuse', process_message returns pushback."""
        svc = _make_chat_service()

        refuse_decision = FakeFrictionDecision(
            level="refuse",
            reasoning="Cannot comply",
            user_message="I can't do that -- it violates compliance policy.",
            proceed_if_confirmed=False,
        )

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(return_value=refuse_decision)
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message("user-1", "conv-1", "Bypass approval")

        assert result["message"] == refuse_decision.user_message
        assert result["rich_content"][0]["data"]["level"] == "refuse"
        assert result["rich_content"][0]["data"]["proceed_if_confirmed"] is False
        svc._llm_client.generate_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_comply_proceeds_to_llm(self):
        """When friction returns 'comply', normal LLM flow runs."""
        svc = _make_chat_service()

        comply_decision = FakeFrictionDecision(
            level="comply",
            reasoning="No concerns",
            user_message=None,
            proceed_if_confirmed=True,
        )

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(return_value=comply_decision)
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message(
                "user-1", "conv-1", "Research BioGenix pipeline"
            )

        # LLM should have been called
        svc._llm_client.generate_response.assert_called_once()
        assert "message" in result

    @pytest.mark.asyncio
    async def test_friction_error_fails_open(self):
        """When friction engine raises, flow continues as if 'comply'."""
        svc = _make_chat_service()

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message(
                "user-1", "conv-1", "Send proposal without ROI"
            )

        # Should proceed to LLM despite friction error
        svc._llm_client.generate_response.assert_called_once()
        assert "message" in result

    @pytest.mark.asyncio
    async def test_flag_injects_note_into_system_prompt(self):
        """When friction returns 'flag', a note is appended to system prompt."""
        svc = _make_chat_service()

        flag_decision = FakeFrictionDecision(
            level="flag",
            reasoning="Minor risk",
            user_message="The recipient hasn't responded to the last 2 emails.",
            proceed_if_confirmed=True,
        )

        captured_prompts = []
        original_generate = svc._llm_client.generate_response

        async def capture_prompt(*args, **kwargs):
            captured_prompts.append(kwargs.get("system_prompt", ""))
            return "Here's my response, noting the concern."

        svc._llm_client.generate_response = AsyncMock(side_effect=capture_prompt)

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(return_value=flag_decision)
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message(
                "user-1", "conv-1", "Send follow-up email to Dr. Smith"
            )

        # LLM should have been called
        assert svc._llm_client.generate_response.called
        # The flag note should be in the system prompt
        assert len(captured_prompts) == 1
        assert "Cognitive Friction Note" in captured_prompts[0]
        assert flag_decision.user_message in captured_prompts[0]


class TestAutonomyUpgradeRequest:
    """Verify autonomy upgrade request is surfaced after successful skill execution."""

    @pytest.mark.asyncio
    async def test_autonomy_request_included_when_eligible(self):
        """After skill execution, if trust is high enough, include autonomy request."""
        svc = _make_chat_service()

        # Mock skill routing to return a completed skill result
        svc._detect_plan_extension = AsyncMock(return_value=None)
        svc._detect_skill_match = AsyncMock(return_value=(True, [], 0.9))
        svc._route_through_skill = AsyncMock(
            return_value={
                "status": "completed",
                "agent_type": "analyst",
                "plan_id": "plan-1",
                "steps_completed": 2,
                "steps_failed": 0,
            }
        )

        mock_trust = MagicMock()
        mock_trust.can_request_autonomy_upgrade = AsyncMock(return_value=True)
        mock_trust.format_autonomy_request = AsyncMock(
            return_value="I've completed 15 research tasks with 100% accuracy. Can I run these automatically?"
        )
        svc._trust_service = mock_trust

        result = await svc.process_message("user-1", "conv-1", "Research BioGenix pipeline")

        assert "autonomy_request" in result
        assert "15 research tasks" in result["autonomy_request"]
        mock_trust.can_request_autonomy_upgrade.assert_called_once()
        mock_trust.format_autonomy_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_autonomy_request_when_not_eligible(self):
        """If trust is not high enough, no autonomy request included."""
        svc = _make_chat_service()

        mock_trust = MagicMock()
        mock_trust.can_request_autonomy_upgrade = AsyncMock(return_value=False)
        svc._trust_service = mock_trust

        result = await svc.process_message("user-1", "conv-1", "Research BioGenix pipeline")

        assert "autonomy_request" not in result

    @pytest.mark.asyncio
    async def test_autonomy_check_error_fails_open(self):
        """If trust check raises, no autonomy request but response proceeds."""
        svc = _make_chat_service()

        # Mock skill routing to return a completed skill result
        svc._detect_plan_extension = AsyncMock(return_value=None)
        svc._detect_skill_match = AsyncMock(return_value=(True, [], 0.9))
        svc._route_through_skill = AsyncMock(
            return_value={
                "status": "completed",
                "agent_type": "scout",
                "plan_id": "plan-2",
                "steps_completed": 1,
                "steps_failed": 0,
            }
        )

        mock_trust = MagicMock()
        mock_trust.can_request_autonomy_upgrade = AsyncMock(
            side_effect=RuntimeError("db error")
        )
        svc._trust_service = mock_trust

        result = await svc.process_message("user-1", "conv-1", "Monitor BioGenix news")

        # Should still succeed despite autonomy check failure
        assert "message" in result
        assert "autonomy_request" not in result
