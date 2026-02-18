"""Tests for CognitiveFrictionEngine — ARIA's pushback mechanism.

Covers FrictionDecision dataclass, fast-path comply, LLM evaluation,
persona builder usage, error handling, and the singleton accessor.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.cognitive_friction import (
    FAST_PATH_THRESHOLD,
    FRICTION_CHALLENGE,
    FRICTION_COMPLY,
    FRICTION_FLAG,
    FRICTION_REFUSE,
    CognitiveFrictionEngine,
    FrictionDecision,
    get_cognitive_friction_engine,
)
from src.core.task_characteristics import TaskCharacteristics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_json(level: str, reasoning: str = "test", user_message: str | None = None) -> str:
    """Return a raw JSON string mimicking LLM output."""
    return json.dumps({
        "level": level,
        "reasoning": reasoning,
        "user_message": user_message,
    })


def _mock_llm(return_text: str = "") -> MagicMock:
    """Create a mock LLMClient that returns *return_text*."""
    mock = MagicMock()

    # generate_response returns a string
    mock.generate_response = AsyncMock(return_value=return_text)

    # generate_response_with_thinking returns an LLMResponse-like object
    resp = MagicMock()
    resp.text = return_text
    mock.generate_response_with_thinking = AsyncMock(return_value=resp)

    return mock


def _mock_persona_builder() -> MagicMock:
    """Create a mock PersonaBuilder whose ``build()`` returns a PersonaContext stub."""
    ctx = MagicMock()
    ctx.to_system_prompt.return_value = "You are ARIA."

    builder = MagicMock()
    builder.build = AsyncMock(return_value=ctx)
    return builder


def _tc(risk_score_approx: float) -> TaskCharacteristics:
    """Create a TaskCharacteristics with a risk_score near *risk_score_approx*.

    The formula: risk = criticality*0.3 + (1-reversibility)*0.25 + uncertainty*0.2
                        + complexity*0.15 + contextuality*0.1
    Setting all dims equal to *v* gives: 0.3v + 0.25(1-v) + 0.2v + 0.15v + 0.1v
    = 0.3v + 0.25 - 0.25v + 0.2v + 0.15v + 0.1v = 0.5v + 0.25
    So v = (risk - 0.25) / 0.5.
    """
    v = max(0.0, min(1.0, (risk_score_approx - 0.25) / 0.5))
    return TaskCharacteristics(
        complexity=v,
        criticality=v,
        uncertainty=v,
        reversibility=v,
        verifiability=v,
        subjectivity=v,
        contextuality=v,
    )


# ---------------------------------------------------------------------------
# TestFrictionDecision
# ---------------------------------------------------------------------------

class TestFrictionDecision:
    def test_comply_decision(self):
        d = FrictionDecision(
            level=FRICTION_COMPLY,
            reasoning="No concern",
            user_message=None,
            proceed_if_confirmed=True,
        )
        assert d.user_message is None
        assert d.proceed_if_confirmed is True

    def test_refuse_decision(self):
        d = FrictionDecision(
            level=FRICTION_REFUSE,
            reasoning="Compliance violation",
            user_message="I can't do that.",
            proceed_if_confirmed=False,
        )
        assert d.proceed_if_confirmed is False

    def test_challenge_decision(self):
        d = FrictionDecision(
            level=FRICTION_CHALLENGE,
            reasoning="CFO expects ROI",
            user_message="I'd push back — the CFO explicitly asked for ROI numbers.",
            proceed_if_confirmed=True,
        )
        assert d.user_message is not None
        assert d.proceed_if_confirmed is True


# ---------------------------------------------------------------------------
# TestFastPathComply
# ---------------------------------------------------------------------------

class TestFastPathComply:
    @pytest.mark.asyncio
    async def test_low_risk_fast_path(self):
        """risk_score < 0.15 should return COMPLY without calling LLM."""
        llm = _mock_llm()
        engine = CognitiveFrictionEngine(llm_client=llm)

        # risk_score ~0.10 (very low)
        tc = TaskCharacteristics(
            complexity=0.0, criticality=0.0, uncertainty=0.0,
            reversibility=1.0, verifiability=1.0, subjectivity=0.0,
            contextuality=0.0,
        )
        assert tc.risk_score < FAST_PATH_THRESHOLD

        result = await engine.evaluate("u1", "search for X", tc)

        assert result.level == FRICTION_COMPLY
        llm.generate_response.assert_not_called()
        llm.generate_response_with_thinking.assert_not_called()

    @pytest.mark.asyncio
    async def test_moderate_risk_calls_llm(self):
        """risk_score = 0.3 should trigger an LLM call."""
        llm = _mock_llm(_make_llm_json("comply"))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        tc = _tc(0.3)
        assert tc.risk_score >= FAST_PATH_THRESHOLD

        result = await engine.evaluate("u1", "draft email", tc)

        assert result.level == FRICTION_COMPLY
        # 0.3 < 0.4 → generate_response (no thinking)
        llm.generate_response.assert_called_once()
        llm.generate_response_with_thinking.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_characteristics_defaults(self):
        """task_characteristics=None defaults to 0.5 risk → LLM called."""
        llm = _mock_llm(_make_llm_json("comply"))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "send proposal", None)

        # Default TC has risk_score ~0.5, which is >= 0.4 → thinking used
        assert result.level == FRICTION_COMPLY
        llm.generate_response_with_thinking.assert_called_once()


# ---------------------------------------------------------------------------
# TestLLMEvaluation
# ---------------------------------------------------------------------------

class TestLLMEvaluation:
    @pytest.mark.asyncio
    async def test_comply_from_llm(self):
        llm = _mock_llm(_make_llm_json("comply", "No issues found"))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "search PubMed", _tc(0.3))

        assert result.level == FRICTION_COMPLY
        assert result.user_message is None
        assert result.proceed_if_confirmed is True

    @pytest.mark.asyncio
    async def test_challenge_from_llm(self):
        msg = "I'd push back — the CFO explicitly asked for ROI numbers."
        llm = _mock_llm(_make_llm_json("challenge", "CFO wants ROI", msg))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "send proposal without ROI", _tc(0.5))

        assert result.level == FRICTION_CHALLENGE
        assert result.user_message == msg
        assert result.proceed_if_confirmed is True

    @pytest.mark.asyncio
    async def test_refuse_from_llm(self):
        msg = "I can't send that — it violates pharma compliance rules."
        llm = _mock_llm(_make_llm_json("refuse", "Compliance issue", msg))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "send unapproved claims", _tc(0.5))

        assert result.level == FRICTION_REFUSE
        assert result.user_message == msg
        assert result.proceed_if_confirmed is False

    @pytest.mark.asyncio
    async def test_flag_from_llm(self):
        msg = "Worth noting: this conflicts with last week's strategy."
        llm = _mock_llm(_make_llm_json("flag", "Minor concern", msg))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "pivot strategy", _tc(0.3))

        assert result.level == FRICTION_FLAG
        assert result.user_message == msg
        assert result.proceed_if_confirmed is True

    @pytest.mark.asyncio
    async def test_high_risk_uses_thinking(self):
        """risk_score >= 0.4 should call generate_response_with_thinking."""
        llm = _mock_llm(_make_llm_json("comply"))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        tc = _tc(0.5)
        assert tc.risk_score >= 0.4

        await engine.evaluate("u1", "send email to all contacts", tc)

        llm.generate_response_with_thinking.assert_called_once()
        llm.generate_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_medium_risk_uses_plain_response(self):
        """risk_score between 0.15 and 0.4 should call generate_response."""
        llm = _mock_llm(_make_llm_json("comply"))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        tc = _tc(0.3)
        assert FAST_PATH_THRESHOLD <= tc.risk_score < 0.4

        await engine.evaluate("u1", "draft a message", tc)

        llm.generate_response.assert_called_once()
        llm.generate_response_with_thinking.assert_not_called()


# ---------------------------------------------------------------------------
# TestPersonaBuilderUsage
# ---------------------------------------------------------------------------

class TestPersonaBuilderUsage:
    @pytest.mark.asyncio
    async def test_persona_builder_called_with_cognitive_friction(self):
        llm = _mock_llm(_make_llm_json("comply"))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        await engine.evaluate("u1", "do something", _tc(0.3))

        pb.build.assert_called_once()
        call_args = pb.build.call_args
        request = call_args[0][0]
        assert request.agent_name == "cognitive_friction"

    @pytest.mark.asyncio
    async def test_persona_builder_failure_falls_back(self):
        """If PersonaBuilder.build() raises, the engine should still work."""
        llm = _mock_llm(_make_llm_json("comply"))
        pb = MagicMock()
        pb.build = AsyncMock(side_effect=RuntimeError("DB unavailable"))
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "do something", _tc(0.3))

        assert result.level == FRICTION_COMPLY
        # Verify LLM was still called (with fallback prompt)
        llm.generate_response.assert_called_once()


# ---------------------------------------------------------------------------
# TestErrorHandling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_llm_exception_returns_comply(self):
        """LLM raising an exception should fail-open to comply."""
        llm = MagicMock()
        llm.generate_response = AsyncMock(side_effect=RuntimeError("API down"))
        llm.generate_response_with_thinking = AsyncMock(side_effect=RuntimeError("API down"))
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "something", _tc(0.3))

        assert result.level == FRICTION_COMPLY
        assert result.proceed_if_confirmed is True

    @pytest.mark.asyncio
    async def test_malformed_response_returns_comply(self):
        """Non-JSON LLM output should fail-open to comply."""
        llm = _mock_llm("This is not JSON at all, just some text.")
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "something", _tc(0.3))

        assert result.level == FRICTION_COMPLY

    @pytest.mark.asyncio
    async def test_json_in_code_fences_parsed(self):
        """JSON wrapped in markdown code fences should be correctly parsed."""
        fenced = '```json\n' + _make_llm_json("challenge", "reason", "push back msg") + '\n```'
        llm = _mock_llm(fenced)
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "something", _tc(0.3))

        assert result.level == FRICTION_CHALLENGE
        assert result.user_message == "push back msg"

    @pytest.mark.asyncio
    async def test_invalid_level_defaults_to_comply(self):
        """An unrecognised level value in the JSON should default to comply."""
        bad_json = json.dumps({"level": "banana", "reasoning": "oops", "user_message": None})
        llm = _mock_llm(bad_json)
        pb = _mock_persona_builder()
        engine = CognitiveFrictionEngine(llm_client=llm, persona_builder=pb)

        result = await engine.evaluate("u1", "something", _tc(0.3))

        assert result.level == FRICTION_COMPLY


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_cognitive_friction_engine_returns_same_instance(self):
        # Reset module-level singleton for test isolation
        import src.core.cognitive_friction as mod
        mod._engine = None

        a = get_cognitive_friction_engine()
        b = get_cognitive_friction_engine()
        assert a is b

        # Clean up
        mod._engine = None
