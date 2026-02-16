"""Companion Orchestrator — US-810.

Unifies all companion subsystems (personality, theory of mind, emotional
intelligence, metacognition, narrative identity, digital twin, strategic
planning, self-improvement) into a single parallel-gathered context that
enriches chat response generation.

Design decisions:
- All subsystems are optional and lazy-initialized via _ensure_initialized().
- build_full_context() runs 9 gatherer coroutines in parallel with a 2s timeout.
- Any subsystem failure is logged and added to failed_subsystems — never propagated.
- CompanionContext.to_system_prompt_sections() renders non-empty sections only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CompanionContext — the unified context dataclass
# ---------------------------------------------------------------------------


@dataclass
class CompanionContext:
    """All companion context gathered for a single chat turn.

    Every field defaults to None/empty so that missing subsystems
    degrade gracefully.
    """

    # Personality
    personality_profile: Any = None  # PersonalityProfile | None

    # Theory of Mind
    mental_state: Any = None  # MentalState | None

    # Emotional Intelligence
    emotional_context: str | None = None  # EmotionalContext value
    emotional_acknowledgment: str | None = None
    emotional_support_type: str | None = None
    emotional_avoid_list: list[str] = field(default_factory=list)

    # Metacognition
    knowledge_assessments: dict[str, Any] = field(default_factory=dict)
    uncertainty_acknowledgments: list[str] = field(default_factory=list)

    # Narrative Identity
    narrative_references: list[str] = field(default_factory=list)
    relationship_age_days: int | None = None
    trust_score: float | None = None
    total_interactions: int | None = None
    anniversaries: list[dict[str, Any]] = field(default_factory=list)

    # Digital Twin / Personality Calibrator
    style_guidelines: str | None = None
    tone_guidance: str | None = None
    example_adjustments: list[str] = field(default_factory=list)

    # Strategic Planning
    strategic_concerns: list[Any] = field(default_factory=list)

    # Self-Improvement
    improvement_focus_areas: list[str] = field(default_factory=list)

    # Pushback (populated via should_push_back)
    opinion: Any = None  # OpinionResult | None
    pushback_text: str | None = None

    # Timing / diagnostics
    build_time_ms: float = 0.0
    failed_subsystems: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def has_emotional_context(self) -> bool:
        """Return True when emotional context is non-neutral."""
        return self.emotional_context is not None and self.emotional_context != "neutral"

    def has_pushback(self) -> bool:
        """Return True when pushback text has been set."""
        return self.pushback_text is not None

    def to_system_prompt_sections(self) -> str:
        """Render all populated context as system-prompt sections."""
        sections: list[str] = []

        # Mental state
        if self.mental_state is not None:
            try:
                ms = self.mental_state
                sections.append(
                    "## User Mental State\n"
                    f"- Stress: {ms.stress_level.value if hasattr(ms.stress_level, 'value') else ms.stress_level}\n"
                    f"- Confidence: {ms.confidence_level.value if hasattr(ms.confidence_level, 'value') else ms.confidence_level}\n"
                    f"- Emotional tone: {ms.emotional_tone}\n"
                    f"- Recommended style: {ms.recommended_response_style}"
                )
            except Exception:
                logger.debug("Could not render mental_state section")

        # Emotional context
        if self.has_emotional_context():
            parts = [f"## Emotional Context\n- Detected: {self.emotional_context}"]
            if self.emotional_acknowledgment:
                parts.append(f"- Acknowledgment: {self.emotional_acknowledgment}")
            if self.emotional_support_type:
                parts.append(f"- Support type: {self.emotional_support_type}")
            if self.emotional_avoid_list:
                parts.append("- Avoid: " + "; ".join(self.emotional_avoid_list))
            sections.append("\n".join(parts))

        # Narrative references
        if self.narrative_references:
            refs = "\n".join(f"- {r}" for r in self.narrative_references)
            sections.append(f"## Shared History References\n{refs}")

        # Anniversaries
        if self.anniversaries:
            ann_lines = "\n".join(
                f"- {a.get('description', a.get('type', 'milestone'))}" for a in self.anniversaries
            )
            sections.append(f"## Relationship Anniversaries\n{ann_lines}")

        # Tone / personality calibration
        if self.tone_guidance:
            examples_text = ""
            if self.example_adjustments:
                examples_text = "\nExamples:\n" + "\n".join(
                    f"- {ex}" for ex in self.example_adjustments
                )
            sections.append(
                f"## Communication Style Calibration\n{self.tone_guidance}{examples_text}"
            )

        # Writing style
        if self.style_guidelines:
            sections.append(f"## Writing Style Fingerprint\n{self.style_guidelines}")

        # Strategic concerns
        if self.strategic_concerns:
            concern_lines = []
            for c in self.strategic_concerns:
                if hasattr(c, "description"):
                    concern_lines.append(f"- [{c.severity}] {c.description} (plan: {c.plan_title})")
                elif isinstance(c, dict):
                    concern_lines.append(f"- [{c.get('severity', '?')}] {c.get('description', '')}")
            if concern_lines:
                sections.append("## Strategic Concerns\n" + "\n".join(concern_lines))

        # Improvement focus
        if self.improvement_focus_areas:
            focus_lines = "\n".join(f"- {f}" for f in self.improvement_focus_areas)
            sections.append(f"## Current Improvement Focus\n{focus_lines}")

        # Uncertainty acknowledgments
        if self.uncertainty_acknowledgments:
            ack_lines = "\n".join(f"- {a}" for a in self.uncertainty_acknowledgments)
            sections.append(
                f"## Knowledge Uncertainty\n"
                f"Acknowledge low-confidence areas naturally:\n{ack_lines}"
            )

        # Pushback
        if self.has_pushback():
            sections.append(
                f"## ARIA Pushback\n"
                f"You should push back on the user's approach:\n{self.pushback_text}"
            )

        return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# CompanionOrchestrator
# ---------------------------------------------------------------------------


class CompanionOrchestrator:
    """Orchestrate all companion subsystems into a unified context.

    All subsystem parameters are optional; when not provided they are
    lazy-initialized the first time ``build_full_context`` is called.
    """

    def __init__(
        self,
        personality: Any = None,
        theory_of_mind: Any = None,
        emotional: Any = None,
        metacognition: Any = None,
        narrative: Any = None,
        digital_twin: Any = None,
        personality_calibrator: Any = None,
        strategic: Any = None,
        self_improvement: Any = None,
    ) -> None:
        self._personality = personality
        self._theory_of_mind = theory_of_mind
        self._emotional = emotional
        self._metacognition = metacognition
        self._narrative = narrative
        self._digital_twin = digital_twin
        self._personality_calibrator = personality_calibrator
        self._strategic = strategic
        self._self_improvement = self_improvement
        self._initialized = False

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Lazily create any subsystems that were not injected."""
        if self._initialized:
            return
        self._initialized = True

        try:
            if self._personality is None:
                from src.companion.personality import PersonalityService

                self._personality = PersonalityService()
        except Exception as e:
            logger.warning("Failed to init PersonalityService: %s", e)

        try:
            if self._theory_of_mind is None:
                from src.companion.theory_of_mind import TheoryOfMindModule

                self._theory_of_mind = TheoryOfMindModule()
        except Exception as e:
            logger.warning("Failed to init TheoryOfMindModule: %s", e)

        try:
            if self._emotional is None:
                from src.companion.emotional import EmotionalIntelligenceEngine

                self._emotional = EmotionalIntelligenceEngine()
        except Exception as e:
            logger.warning("Failed to init EmotionalIntelligenceEngine: %s", e)

        try:
            if self._metacognition is None:
                from src.companion.metacognition import MetacognitionService

                self._metacognition = MetacognitionService()
        except Exception as e:
            logger.warning("Failed to init MetacognitionService: %s", e)

        try:
            if self._narrative is None:
                from src.companion.narrative import NarrativeIdentityEngine

                self._narrative = NarrativeIdentityEngine()
        except Exception as e:
            logger.warning("Failed to init NarrativeIdentityEngine: %s", e)

        try:
            if self._digital_twin is None:
                from src.memory.digital_twin import DigitalTwin

                self._digital_twin = DigitalTwin()
        except Exception as e:
            logger.warning("Failed to init DigitalTwin: %s", e)

        try:
            if self._personality_calibrator is None:
                from src.onboarding.personality_calibrator import PersonalityCalibrator

                self._personality_calibrator = PersonalityCalibrator()
        except Exception as e:
            logger.warning("Failed to init PersonalityCalibrator: %s", e)

        try:
            if self._strategic is None:
                from src.companion.strategic import StrategicPlanningService

                self._strategic = StrategicPlanningService()
        except Exception as e:
            logger.warning("Failed to init StrategicPlanningService: %s", e)

        try:
            if self._self_improvement is None:
                from src.companion.self_improvement import SelfImprovementLoop

                self._self_improvement = SelfImprovementLoop()
        except Exception as e:
            logger.warning("Failed to init SelfImprovementLoop: %s", e)

    # ------------------------------------------------------------------
    # Main context builder
    # ------------------------------------------------------------------

    async def build_full_context(
        self,
        user_id: str,
        message: str,
        conversation_history: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
    ) -> CompanionContext:
        """Gather context from all subsystems in parallel.

        Args:
            user_id: The user's ID.
            message: Current user message.
            conversation_history: Recent conversation messages.
            session_id: Current session / conversation ID.

        Returns:
            Populated CompanionContext (never raises).
        """
        start = time.perf_counter()
        self._ensure_initialized()

        ctx = CompanionContext()
        history = conversation_history or []

        # Build coroutines
        coros = [
            self._gather_calibration(user_id, ctx),
            self._gather_digital_twin(user_id, ctx),
            self._gather_personality(user_id, ctx),
            self._gather_theory_of_mind(user_id, history, session_id, ctx),
            self._gather_emotional(user_id, message, history, ctx),
            self._gather_metacognition(user_id, message, ctx),
            self._gather_narrative(user_id, message, ctx),
            self._gather_strategic(user_id, ctx),
            self._gather_self_improvement(user_id, ctx),
        ]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*coros, return_exceptions=True),
                timeout=2.0,
            )
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    subsystem = [
                        "calibration",
                        "digital_twin",
                        "personality",
                        "theory_of_mind",
                        "emotional",
                        "metacognition",
                        "narrative",
                        "strategic",
                        "self_improvement",
                    ][i]
                    ctx.failed_subsystems.append(subsystem)
                    logger.warning(
                        "Companion subsystem %s failed: %s",
                        subsystem,
                        result,
                    )
        except TimeoutError:
            ctx.failed_subsystems.append("timeout")
            logger.warning("Companion context build timed out at 2s")

        ctx.build_time_ms = (time.perf_counter() - start) * 1000
        return ctx

    # ------------------------------------------------------------------
    # Individual gatherers — each wraps one subsystem
    # ------------------------------------------------------------------

    async def _gather_calibration(self, user_id: str, ctx: CompanionContext) -> None:
        if self._personality_calibrator is None:
            return
        calibration = await self._personality_calibrator.get_calibration(user_id)
        if calibration is not None:
            ctx.tone_guidance = calibration.tone_guidance
            ctx.example_adjustments = calibration.example_adjustments or []

    async def _gather_digital_twin(self, user_id: str, ctx: CompanionContext) -> None:
        if self._digital_twin is None:
            return
        fingerprint = await self._digital_twin.get_fingerprint(user_id)
        if fingerprint:
            guidelines = await self._digital_twin.get_style_guidelines(user_id)
            ctx.style_guidelines = guidelines

    async def _gather_personality(self, user_id: str, ctx: CompanionContext) -> None:
        if self._personality is None:
            return
        ctx.personality_profile = await self._personality.get_profile(user_id)

    async def _gather_theory_of_mind(
        self,
        user_id: str,
        history: list[dict[str, Any]],
        session_id: str | None,
        ctx: CompanionContext,
    ) -> None:
        if self._theory_of_mind is None:
            return
        recent = history[-5:] if history else []
        ctx.mental_state = await self._theory_of_mind.infer_state(
            user_id=user_id,
            recent_messages=recent,
            context=None,
            session_id=session_id,
        )

    async def _gather_emotional(
        self,
        user_id: str,
        message: str,
        history: list[dict[str, Any]],
        ctx: CompanionContext,
    ) -> None:
        if self._emotional is None:
            return
        response = await self._emotional.generate_emotional_response(
            user_id=user_id,
            message=message,
            context=None,
            conversation_history=history,
        )
        ctx.emotional_context = (
            response.context.value if hasattr(response.context, "value") else str(response.context)
        )
        ctx.emotional_acknowledgment = response.acknowledgment
        ctx.emotional_support_type = (
            response.support_type.value
            if hasattr(response.support_type, "value")
            else str(response.support_type)
        )
        ctx.emotional_avoid_list = response.avoid_list or []

    async def _gather_metacognition(
        self, user_id: str, message: str, ctx: CompanionContext
    ) -> None:
        if self._metacognition is None:
            return
        assessments = await self._metacognition.assess_topics(user_id, message)
        ctx.knowledge_assessments = assessments or {}

        # Build uncertainty acknowledgments for low-confidence topics
        acks: list[str] = []
        for topic, assessment in (assessments or {}).items():
            conf = assessment.confidence if hasattr(assessment, "confidence") else 0.0
            if conf < 0.5:
                acks.append(f"Low confidence on '{topic}' ({conf:.0%}) — consider researching")
        ctx.uncertainty_acknowledgments = acks

    async def _gather_narrative(self, user_id: str, message: str, ctx: CompanionContext) -> None:
        if self._narrative is None:
            return
        refs = await self._narrative.get_contextual_references(user_id, message)
        ctx.narrative_references = refs or []

        state = await self._narrative.get_narrative_state(user_id)
        if state is not None:
            ctx.trust_score = state.trust_score
            ctx.total_interactions = state.total_interactions
            if hasattr(state, "relationship_start"):
                from datetime import UTC, datetime

                delta = datetime.now(UTC) - state.relationship_start
                ctx.relationship_age_days = delta.days

        anniversaries = await self._narrative.check_anniversaries(user_id)
        ctx.anniversaries = anniversaries or []

    async def _gather_strategic(self, user_id: str, ctx: CompanionContext) -> None:
        if self._strategic is None:
            return
        concerns = await self._strategic.get_strategic_concerns(user_id)
        ctx.strategic_concerns = concerns or []

    async def _gather_self_improvement(self, user_id: str, ctx: CompanionContext) -> None:
        if self._self_improvement is None:
            return
        focus = await self._self_improvement.get_current_focus(user_id)
        ctx.improvement_focus_areas = focus or []

    # ------------------------------------------------------------------
    # Pushback evaluation
    # ------------------------------------------------------------------

    async def should_push_back(
        self,
        user_id: str,
        message: str,
        context: CompanionContext,
    ) -> CompanionContext:
        """Evaluate whether ARIA should push back on the user's message.

        Mutates and returns the context with opinion/pushback fields populated.
        """
        if self._personality is None:
            return context

        try:
            opinion = await self._personality.form_opinion(user_id, message)
            if opinion is not None:
                context.opinion = opinion
                if opinion.should_push_back:
                    pushback = await self._personality.generate_pushback(user_id, message, opinion)
                    context.pushback_text = pushback
        except Exception as e:
            logger.warning("Pushback evaluation failed: %s", e)

        return context

    # ------------------------------------------------------------------
    # Proactive trigger detection
    # ------------------------------------------------------------------

    async def check_proactive_triggers(
        self,
        user_id: str,  # noqa: ARG002
        context: CompanionContext,
    ) -> list[dict[str, Any]]:
        """Check context for proactive triggers.

        Returns a list of trigger dicts with type, description, priority.
        """
        triggers: list[dict[str, Any]] = []

        # Anniversaries
        for ann in context.anniversaries:
            triggers.append(
                {
                    "type": "anniversary",
                    "description": ann.get("description", ann.get("type", "milestone")),
                    "priority": "medium",
                }
            )

        # High/critical strategic concerns
        for concern in context.strategic_concerns:
            severity = (
                concern.severity if hasattr(concern, "severity") else concern.get("severity", "")
            )
            if severity in ("high", "critical"):
                desc = (
                    concern.description
                    if hasattr(concern, "description")
                    else concern.get("description", "")
                )
                triggers.append(
                    {
                        "type": "strategic_concern",
                        "description": desc,
                        "priority": severity,
                    }
                )

        # Low-confidence topics needing research
        for topic, assessment in context.knowledge_assessments.items():
            conf = assessment.confidence if hasattr(assessment, "confidence") else 0.0
            should_research = (
                assessment.should_research if hasattr(assessment, "should_research") else False
            )
            if should_research and conf < 0.5:
                triggers.append(
                    {
                        "type": "research_needed",
                        "description": f"Low confidence on '{topic}' — research recommended",
                        "priority": "low",
                    }
                )

        return triggers

    # ------------------------------------------------------------------
    # Post-response hooks
    # ------------------------------------------------------------------

    async def post_response_hooks(
        self,
        user_id: str,
        mental_state_dict: Any | None = None,
        session_id: str | None = None,
    ) -> None:
        """Fire-and-forget post-response hooks.

        Increments narrative interactions and stores theory-of-mind state.
        """
        coros: list[Any] = []

        if self._narrative is not None:
            coros.append(self._narrative.increment_interactions(user_id))

        if self._theory_of_mind is not None and mental_state_dict is not None:
            coros.append(self._theory_of_mind.store_state(user_id, mental_state_dict, session_id))

        if coros:
            await asyncio.gather(*coros, return_exceptions=True)
