"""Tests for CompanionOrchestrator (US-810)."""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.companion.orchestrator import CompanionContext, CompanionOrchestrator

# ── Helpers ──────────────────────────────────────────────────────────────────


@dataclass
class _FakeMentalState:
    stress_level: str = "normal"
    confidence_level: str = "confident"
    emotional_tone: str = "neutral"
    recommended_response_style: str = "balanced"


@dataclass
class _FakeEmotionalResponse:
    context: Any = None
    acknowledgment: str = "I hear you."
    support_type: Any = None
    avoid_list: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.context is None:
            self.context = MagicMock(value="frustration")
        if self.support_type is None:
            self.support_type = MagicMock(value="empathize")


@dataclass
class _FakeKnowledgeAssessment:
    topic: str = "test"
    confidence: float = 0.3
    should_research: bool = True


@dataclass
class _FakeNarrativeState:
    trust_score: float = 0.8
    total_interactions: int = 42
    relationship_start: datetime = field(default_factory=lambda: datetime(2025, 6, 1, tzinfo=UTC))


@dataclass
class _FakePersonalityCalibration:
    tone_guidance: str = "Be direct and warm."
    example_adjustments: list[str] = field(default_factory=lambda: ["Use shorter sentences"])


@dataclass
class _FakePersonalityProfile:
    directness: int = 3
    warmth: int = 2


@dataclass
class _FakeOpinionResult:
    has_opinion: bool = True
    opinion: str = "I disagree with this approach."
    confidence: float = 0.85
    should_push_back: bool = True
    pushback_reason: str = "Evidence suggests otherwise."


@dataclass
class _FakeStrategicConcern:
    plan_id: str = "plan-1"
    plan_title: str = "Q1 Plan"
    concern_type: str = "at_risk"
    description: str = "Revenue target at risk"
    severity: str = "high"
    recommendation: str = "Increase outreach"


# ── CompanionContext Tests ───────────────────────────────────────────────────


def test_companion_context_defaults() -> None:
    """All fields default to None/empty."""
    ctx = CompanionContext()
    assert ctx.personality_profile is None
    assert ctx.mental_state is None
    assert ctx.emotional_context is None
    assert ctx.emotional_acknowledgment is None
    assert ctx.knowledge_assessments == {}
    assert ctx.uncertainty_acknowledgments == []
    assert ctx.narrative_references == []
    assert ctx.trust_score is None
    assert ctx.style_guidelines is None
    assert ctx.tone_guidance is None
    assert ctx.strategic_concerns == []
    assert ctx.improvement_focus_areas == []
    assert ctx.opinion is None
    assert ctx.pushback_text is None
    assert ctx.build_time_ms == 0.0
    assert ctx.failed_subsystems == []


def test_has_emotional_context_neutral_vs_non_neutral() -> None:
    """has_emotional_context is True when non-neutral, False otherwise."""
    ctx = CompanionContext()
    assert ctx.has_emotional_context() is False

    ctx.emotional_context = "neutral"
    assert ctx.has_emotional_context() is False

    ctx.emotional_context = "frustration"
    assert ctx.has_emotional_context() is True


def test_has_pushback_true_and_false() -> None:
    """has_pushback is True when pushback_text is set."""
    ctx = CompanionContext()
    assert ctx.has_pushback() is False

    ctx.pushback_text = "I'd push back on that..."
    assert ctx.has_pushback() is True


def test_to_system_prompt_sections_empty() -> None:
    """Empty context produces empty string."""
    ctx = CompanionContext()
    assert ctx.to_system_prompt_sections() == ""


def test_to_system_prompt_sections_populated() -> None:
    """Populated context renders expected sections."""
    ctx = CompanionContext(
        mental_state=_FakeMentalState(),
        emotional_context="frustration",
        emotional_acknowledgment="That sounds frustrating.",
        emotional_support_type="empathize",
        emotional_avoid_list=["minimizing"],
        narrative_references=["Remember our first deal with Lonza?"],
        anniversaries=[{"type": "deal_anniversary", "description": "1 year since Lonza deal"}],
        tone_guidance="Be direct and warm.",
        example_adjustments=["Use shorter sentences"],
        style_guidelines="Match user's casual tone.",
        strategic_concerns=[_FakeStrategicConcern()],
        improvement_focus_areas=["response accuracy"],
        uncertainty_acknowledgments=["Low confidence on 'pricing' (30%)"],
        pushback_text="I'd push back on that approach.",
    )

    output = ctx.to_system_prompt_sections()

    assert "## User Mental State" in output
    assert "## Emotional Context" in output
    assert "frustration" in output
    assert "## Shared History References" in output
    assert "Lonza" in output
    assert "## Relationship Anniversaries" in output
    assert "## Communication Style Calibration" in output
    assert "Be direct and warm." in output
    assert "## Writing Style Fingerprint" in output
    assert "## Strategic Concerns" in output
    assert "Revenue target at risk" in output
    assert "## Current Improvement Focus" in output
    assert "response accuracy" in output
    assert "## Knowledge Uncertainty" in output
    assert "## ARIA Pushback" in output


# ── CompanionOrchestrator Tests ──────────────────────────────────────────────


def _build_mocked_orchestrator() -> CompanionOrchestrator:
    """Create orchestrator with fully mocked subsystems."""
    personality = AsyncMock()
    personality.get_profile.return_value = _FakePersonalityProfile()
    personality.form_opinion.return_value = _FakeOpinionResult()
    personality.generate_pushback.return_value = "I'd push back on that."

    theory_of_mind = AsyncMock()
    theory_of_mind.infer_state.return_value = _FakeMentalState()
    theory_of_mind.store_state.return_value = "state-id-123"

    emotional = AsyncMock()
    emotional.generate_emotional_response.return_value = _FakeEmotionalResponse()

    metacognition = AsyncMock()
    metacognition.assess_topics.return_value = {
        "pricing": _FakeKnowledgeAssessment(topic="pricing"),
    }

    narrative = AsyncMock()
    narrative.get_contextual_references.return_value = ["We dealt with this in Q3"]
    narrative.get_narrative_state.return_value = _FakeNarrativeState()
    narrative.check_anniversaries.return_value = [
        {"type": "deal_anniversary", "description": "1yr Lonza"}
    ]
    narrative.increment_interactions.return_value = 43

    digital_twin = AsyncMock()
    digital_twin.get_fingerprint.return_value = MagicMock()  # truthy
    digital_twin.get_style_guidelines.return_value = "Match casual tone."

    personality_calibrator = AsyncMock()
    personality_calibrator.get_calibration.return_value = _FakePersonalityCalibration()

    strategic = AsyncMock()
    strategic.get_strategic_concerns.return_value = [_FakeStrategicConcern()]

    self_improvement = AsyncMock()
    self_improvement.get_current_focus.return_value = ["accuracy", "empathy"]

    orch = CompanionOrchestrator(
        personality=personality,
        theory_of_mind=theory_of_mind,
        emotional=emotional,
        metacognition=metacognition,
        narrative=narrative,
        digital_twin=digital_twin,
        personality_calibrator=personality_calibrator,
        strategic=strategic,
        self_improvement=self_improvement,
    )
    return orch


@pytest.mark.asyncio
async def test_build_full_context_all_subsystems_none() -> None:
    """Orchestrator with all None subsystems degrades gracefully."""
    orch = CompanionOrchestrator()
    # Prevent lazy init from creating real subsystems
    orch._initialized = True

    ctx = await orch.build_full_context(
        user_id="user-1",
        message="Hello",
    )

    assert isinstance(ctx, CompanionContext)
    assert ctx.personality_profile is None
    assert ctx.mental_state is None
    assert ctx.emotional_context is None
    assert ctx.failed_subsystems == []
    assert ctx.build_time_ms > 0


@pytest.mark.asyncio
async def test_build_full_context_with_mocked_subsystems() -> None:
    """Orchestrator correctly populates context from all subsystems."""
    orch = _build_mocked_orchestrator()

    ctx = await orch.build_full_context(
        user_id="user-1",
        message="How's the Lonza deal looking?",
        conversation_history=[
            {"role": "user", "content": "Tell me about Lonza"},
            {"role": "assistant", "content": "Here's what I know..."},
        ],
        session_id="session-abc",
    )

    # Personality
    assert ctx.personality_profile is not None
    assert ctx.personality_profile.directness == 3

    # Theory of Mind
    assert ctx.mental_state is not None
    assert ctx.mental_state.stress_level == "normal"

    # Emotional
    assert ctx.emotional_context == "frustration"
    assert ctx.emotional_acknowledgment == "I hear you."

    # Metacognition
    assert "pricing" in ctx.knowledge_assessments
    assert len(ctx.uncertainty_acknowledgments) == 1

    # Narrative
    assert len(ctx.narrative_references) == 1
    assert ctx.trust_score == 0.8
    assert ctx.total_interactions == 42
    assert ctx.relationship_age_days is not None
    assert len(ctx.anniversaries) == 1

    # Digital Twin
    assert ctx.style_guidelines == "Match casual tone."

    # Calibration
    assert ctx.tone_guidance == "Be direct and warm."

    # Strategic
    assert len(ctx.strategic_concerns) == 1

    # Self-improvement
    assert ctx.improvement_focus_areas == ["accuracy", "empathy"]

    # No failures
    assert ctx.failed_subsystems == []
    assert ctx.build_time_ms > 0


@pytest.mark.asyncio
async def test_build_full_context_subsystem_failure_degrades() -> None:
    """One failing subsystem doesn't affect the rest."""
    orch = _build_mocked_orchestrator()

    # Make emotional subsystem raise
    orch._emotional.generate_emotional_response.side_effect = RuntimeError("LLM down")

    ctx = await orch.build_full_context(
        user_id="user-1",
        message="Hello",
    )

    # Emotional failed
    assert "emotional" in ctx.failed_subsystems

    # Other subsystems still populated
    assert ctx.personality_profile is not None
    assert ctx.mental_state is not None
    assert len(ctx.narrative_references) == 1
    assert ctx.style_guidelines == "Match casual tone."


@pytest.mark.asyncio
async def test_build_full_context_performance_under_2_seconds() -> None:
    """build_full_context completes well under 2s with fast subsystems."""
    orch = _build_mocked_orchestrator()

    start = time.perf_counter()
    ctx = await orch.build_full_context(
        user_id="user-1",
        message="Test",
    )
    elapsed = (time.perf_counter() - start) * 1000

    assert elapsed < 2000
    assert ctx.build_time_ms < 2000


@pytest.mark.asyncio
async def test_post_response_hooks_increments_and_stores() -> None:
    """post_response_hooks calls narrative.increment and tom.store_state."""
    orch = _build_mocked_orchestrator()

    mental_state = _FakeMentalState()
    await orch.post_response_hooks(
        user_id="user-1",
        mental_state_dict=mental_state,
        session_id="session-abc",
    )

    orch._narrative.increment_interactions.assert_awaited_once_with("user-1")
    orch._theory_of_mind.store_state.assert_awaited_once_with("user-1", mental_state, "session-abc")


@pytest.mark.asyncio
async def test_should_push_back_with_opinion() -> None:
    """should_push_back populates opinion and pushback_text."""
    orch = _build_mocked_orchestrator()
    ctx = CompanionContext()

    result = await orch.should_push_back("user-1", "I think we should cut prices", ctx)

    assert result.opinion is not None
    assert result.opinion.should_push_back is True
    assert result.pushback_text == "I'd push back on that."


@pytest.mark.asyncio
async def test_should_push_back_no_opinion() -> None:
    """should_push_back does nothing when opinion is None."""
    orch = _build_mocked_orchestrator()
    orch._personality.form_opinion.return_value = None
    ctx = CompanionContext()

    result = await orch.should_push_back("user-1", "Hello", ctx)

    assert result.opinion is None
    assert result.pushback_text is None


@pytest.mark.asyncio
async def test_check_proactive_triggers() -> None:
    """check_proactive_triggers finds anniversaries, concerns, and research needs."""
    orch = _build_mocked_orchestrator()
    ctx = CompanionContext(
        anniversaries=[{"type": "deal_anniversary", "description": "1yr Lonza"}],
        strategic_concerns=[_FakeStrategicConcern()],
        knowledge_assessments={
            "pricing": _FakeKnowledgeAssessment(topic="pricing"),
        },
    )

    triggers = await orch.check_proactive_triggers("user-1", ctx)

    types = [t["type"] for t in triggers]
    assert "anniversary" in types
    assert "strategic_concern" in types
    assert "research_needed" in types
    assert len(triggers) == 3


@pytest.mark.asyncio
async def test_check_proactive_triggers_empty() -> None:
    """check_proactive_triggers returns empty for empty context."""
    orch = _build_mocked_orchestrator()
    ctx = CompanionContext()

    triggers = await orch.check_proactive_triggers("user-1", ctx)
    assert triggers == []
