"""Multi-Scale Temporal Reasoner for JARVIS Intelligence.

This module enables ARIA to simultaneously reason across different time
horizons (immediate, tactical, strategic, visionary), detect cross-scale
conflicts, and generate time-appropriate recommendations.

Key features:
- Context gathering at each time scale (today, this week, this quarter, this year)
- Cross-scale impact analysis (how immediate decisions affect long-term goals)
- Conflict detection (short-term gain vs long-term pain)
- Reconciliation advice for detected conflicts
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import get_supabase_client
from src.intelligence.temporal.models import (
    CrossScaleImpact,
    ScaleContext,
    ScaleRecommendation,
    TemporalAnalysis,
    TemporalAnalysisRequest,
    TemporalConflict,
    TimeScale,
)

logger = logging.getLogger(__name__)

# Time scale configuration
TIME_SCALE_CONFIG = {
    TimeScale.IMMEDIATE: {
        "days": 1,
        "description": "today and next 24 hours",
        "context_sources": ["calendar_today", "pending_tasks", "urgent_items"],
    },
    TimeScale.TACTICAL: {
        "days": 7,
        "description": "this week",
        "context_sources": ["weekly_goals", "upcoming_meetings", "near_term_deadlines"],
    },
    TimeScale.STRATEGIC: {
        "days": 90,
        "description": "this quarter",
        "context_sources": ["quarterly_targets", "pipeline_stage", "key_milestones"],
    },
    TimeScale.VISIONARY: {
        "days": 365,
        "description": "this year and beyond",
        "context_sources": ["annual_strategy", "market_trends", "long_term_goals"],
    },
}

# Decision indicators for detecting time scale
SCALE_INDICATORS = {
    TimeScale.IMMEDIATE: [
        "today",
        "now",
        "immediately",
        "right now",
        "this hour",
        "urgent",
        "asap",
        "by end of day",
        "tonight",
    ],
    TimeScale.TACTICAL: [
        "this week",
        "next week",
        "by friday",
        "in a few days",
        "coming days",
        "weekly",
        "before the meeting",
    ],
    TimeScale.STRATEGIC: [
        "this quarter",
        "next quarter",
        "q1",
        "q2",
        "q3",
        "q4",
        "by end of quarter",
        "quarterly",
        "90 days",
        "pipeline",
    ],
    TimeScale.VISIONARY: [
        "this year",
        "next year",
        "annual",
        "long term",
        "eventually",
        "in the future",
        "strategic",
        "vision",
        "12 months",
        "market trends",
    ],
}


class MultiScaleTemporalReasoner:
    """Analyzer for reasoning across multiple time scales.

    Enables ARIA to understand how decisions at one time horizon
    affect outcomes at other time horizons, detect conflicts between
    short-term and long-term goals, and provide reconciled recommendations.

    Attributes:
        TIME_SCALE_CONFIG: Configuration for each time scale
        SCALE_INDICATORS: Keywords that indicate a time scale
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        db_client: Any | None = None,
    ) -> None:
        """Initialize the multi-scale temporal reasoner.

        Args:
            llm_client: LLM client for analysis (optional, created if not provided)
            db_client: Database client for context gathering (optional)
        """
        self._llm = llm_client or LLMClient()
        self._db = db_client

    def _get_db(self) -> Any:
        """Get or create the database client."""
        if self._db is None:
            self._db = get_supabase_client()
        return self._db

    async def analyze_decision(
        self,
        user_id: str,
        decision: str,
        request: TemporalAnalysisRequest | None = None,
    ) -> TemporalAnalysis:
        """Analyze a decision across all time scales.

        Main entry point for multi-scale temporal reasoning. Analyzes how
        a decision affects goals and outcomes at each time scale.

        Args:
            user_id: User ID for context gathering
            decision: The decision to analyze
            request: Optional request with additional parameters

        Returns:
            TemporalAnalysis with cross-scale impacts, conflicts, and recommendations
        """
        start_time = time.monotonic()

        logger.info(
            "Starting multi-scale temporal analysis",
            extra={
                "user_id": user_id,
                "decision_preview": decision[:100],
            },
        )

        # 1. Determine primary time scale of the decision
        primary_scale = await self._determine_primary_scale(decision)
        logger.debug(
            "Primary scale determined",
            extra={"primary_scale": primary_scale.value},
        )

        # 2. Gather context at each time scale in parallel
        scale_contexts = await self._gather_scale_contexts(user_id)

        # 3. Analyze impact of decision at EACH scale
        cross_scale_impacts = await self._analyze_cross_scale_impacts(
            decision=decision,
            primary_scale=primary_scale,
            contexts=scale_contexts,
            context_hint=request.context_hint if request else None,
        )

        # 4. Detect conflicts (good for short-term, bad for long-term)
        conflicts = self._detect_conflicts(cross_scale_impacts)

        # 5. Generate recommendations per scale
        recommendations = await self._generate_scale_recommendations(
            decision=decision,
            contexts=scale_contexts,
            impacts=cross_scale_impacts,
            conflicts=conflicts,
        )

        # 6. Generate reconciliation advice if conflicts exist
        reconciliation = None
        include_reconciliation = request.include_reconciliation if request else True
        if conflicts and include_reconciliation:
            reconciliation = await self._generate_reconciliation(decision, conflicts)

        # Determine overall alignment
        overall_alignment = self._determine_alignment(conflicts)

        # Calculate confidence
        confidence = self._calculate_confidence(
            scale_contexts=scale_contexts,
            impacts=cross_scale_impacts,
            conflicts=conflicts,
        )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Multi-scale temporal analysis complete",
            extra={
                "user_id": user_id,
                "primary_scale": primary_scale.value,
                "conflicts_found": len(conflicts),
                "overall_alignment": overall_alignment,
                "processing_time_ms": elapsed_ms,
            },
        )

        return TemporalAnalysis(
            decision=decision,
            primary_scale=primary_scale,
            scale_contexts={scale.value: ctx for scale, ctx in scale_contexts.items()},
            cross_scale_impacts=cross_scale_impacts,
            conflicts=conflicts,
            recommendations={scale.value: rec for scale, rec in recommendations.items()},
            reconciliation_advice=reconciliation,
            overall_alignment=overall_alignment,
            confidence=confidence,
            processing_time_ms=elapsed_ms,
        )

    async def analyze_with_metadata(
        self,
        user_id: str,
        request: TemporalAnalysisRequest,
    ) -> TemporalAnalysis:
        """Analyze a decision with full request metadata.

        Args:
            user_id: User ID for context gathering
            request: Full request with all parameters

        Returns:
            TemporalAnalysis with complete results
        """
        return await self.analyze_decision(
            user_id=user_id,
            decision=request.decision,
            request=request,
        )

    async def _determine_primary_scale(self, decision: str) -> TimeScale:
        """Determine the primary time scale of a decision.

        Uses pattern matching first, then LLM for ambiguous cases.

        Args:
            decision: The decision text to analyze

        Returns:
            TimeScale enum value for the primary scale
        """
        decision_lower = decision.lower()

        # Pattern matching for explicit scale indicators
        for scale, indicators in SCALE_INDICATORS.items():
            for indicator in indicators:
                if indicator in decision_lower:
                    return scale

        # LLM fallback for ambiguous decisions
        try:
            prompt = f"""Determine the primary time scale of this decision.
Decision: "{decision}"

Time scales:
- immediate: hours/today (operational)
- tactical: days/this week (weekly planning)
- strategic: weeks/quarter (quarterly objectives)
- visionary: months+/year (annual vision)

Return ONLY a JSON object: {{"scale": "immediate|tactical|strategic|visionary", "confidence": 0.0-1.0}}"""

            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You classify decisions by time scale. Output ONLY valid JSON.",
                temperature=0.0,
                max_tokens=100,
            )

            data = json.loads(response.strip())
            scale_str = data.get("scale", "tactical")
            return TimeScale(scale_str)

        except Exception as e:
            logger.warning(
                "Failed to determine scale via LLM, defaulting to tactical",
                extra={"error": str(e)},
            )
            return TimeScale.TACTICAL

    async def _gather_scale_contexts(self, user_id: str) -> dict[TimeScale, ScaleContext]:
        """Gather context for each time scale in parallel.

        Args:
            user_id: User ID for context queries

        Returns:
            Dict mapping TimeScale to ScaleContext
        """
        # Gather all contexts in parallel
        tasks = {
            TimeScale.IMMEDIATE: self._gather_immediate_context(user_id),
            TimeScale.TACTICAL: self._gather_tactical_context(user_id),
            TimeScale.STRATEGIC: self._gather_strategic_context(user_id),
            TimeScale.VISIONARY: self._gather_visionary_context(user_id),
        }

        results = await asyncio.gather(*tasks.values())

        return dict(zip(tasks.keys(), results, strict=True))

    async def _gather_immediate_context(self, user_id: str) -> ScaleContext:
        """Gather context for immediate time scale (today).

        Includes:
        - Today's calendar events
        - Pending/urgent tasks
        - Items requiring immediate attention

        Args:
            user_id: User ID for queries

        Returns:
            ScaleContext for immediate scale
        """
        db = self._get_db()
        now = datetime.now(UTC)
        end_of_day = now.replace(hour=23, minute=59, second=59)

        active_concerns: list[str] = []
        decisions_pending: list[str] = []
        goals: list[str] = []
        constraints: list[str] = []
        calendar_events: list[dict[str, Any]] = []

        try:
            # Get today's calendar events
            events_result = (
                db.table("calendar_events")
                .select("id, title, start_time, end_time, status")
                .eq("user_id", user_id)
                .gte("start_time", now.isoformat())
                .lte("start_time", end_of_day.isoformat())
                .order("start_time")
                .limit(10)
                .execute()
            )

            if events_result.data:
                calendar_events = events_result.data
                active_concerns.extend(
                    [f"Meeting: {e.get('title', 'Untitled')}" for e in events_result.data[:5]]
                )

        except Exception as e:
            logger.warning(
                "Failed to gather immediate calendar context",
                extra={"user_id": user_id, "error": str(e)},
            )

        try:
            # Get urgent/high-priority tasks
            tasks_result = (
                db.table("tasks")
                .select("id, title, priority, due_date")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .gte("priority", 0.7)
                .limit(5)
                .execute()
            )

            if tasks_result.data:
                active_concerns.extend(
                    [f"Task: {t.get('title', 'Untitled')}" for t in tasks_result.data]
                )
                constraints.append(f"{len(tasks_result.data)} high-priority tasks pending")

        except Exception as e:
            logger.debug(
                "Tasks query failed in immediate context",
                extra={"user_id": user_id, "error": str(e)},
            )

        try:
            # Get active goals with immediate deadlines
            goals_result = (
                db.table("goals")
                .select("id, title, target_date")
                .eq("user_id", user_id)
                .eq("status", "active")
                .lte("target_date", end_of_day.isoformat())
                .limit(5)
                .execute()
            )

            if goals_result.data:
                goals.extend([g.get("title", "Untitled goal") for g in goals_result.data])
                decisions_pending.append("Goals due today need attention")

        except Exception as e:
            logger.debug(
                "Goals query failed in immediate context",
                extra={"user_id": user_id, "error": str(e)},
            )

        return ScaleContext(
            scale=TimeScale.IMMEDIATE,
            active_concerns=active_concerns,
            decisions_pending=decisions_pending,
            goals=goals,
            constraints=constraints,
            calendar_events=calendar_events,
        )

    async def _gather_tactical_context(self, user_id: str) -> ScaleContext:
        """Gather context for tactical time scale (this week).

        Includes:
        - This week's goals and targets
        - Upcoming meetings
        - Near-term deadlines

        Args:
            user_id: User ID for queries

        Returns:
            ScaleContext for tactical scale
        """
        db = self._get_db()
        now = datetime.now(UTC)
        end_of_week = now + timedelta(days=7)

        active_concerns: list[str] = []
        decisions_pending: list[str] = []
        goals: list[str] = []
        constraints: list[str] = []
        calendar_events: list[dict[str, Any]] = []

        try:
            # Get this week's calendar events
            events_result = (
                db.table("calendar_events")
                .select("id, title, start_time")
                .eq("user_id", user_id)
                .gte("start_time", now.isoformat())
                .lte("start_time", end_of_week.isoformat())
                .order("start_time")
                .limit(20)
                .execute()
            )

            if events_result.data:
                calendar_events = events_result.data
                # Count meetings by day for context
                active_concerns.append(f"{len(events_result.data)} events this week")

        except Exception as e:
            logger.warning(
                "Failed to gather tactical calendar context",
                extra={"user_id": user_id, "error": str(e)},
            )

        try:
            # Get active goals with weekly scope
            goals_result = (
                db.table("goals")
                .select("id, title, target_date, status")
                .eq("user_id", user_id)
                .eq("status", "active")
                .lte("target_date", end_of_week.isoformat())
                .limit(10)
                .execute()
            )

            if goals_result.data:
                goals.extend([g.get("title", "Untitled goal") for g in goals_result.data])
                decisions_pending.append(f"{len(goals_result.data)} goals due this week")

        except Exception as e:
            logger.debug(
                "Goals query failed in tactical context",
                extra={"user_id": user_id, "error": str(e)},
            )

        try:
            # Get pending tasks for the week
            tasks_result = (
                db.table("tasks")
                .select("id, title, due_date")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .lte("due_date", end_of_week.isoformat())
                .limit(10)
                .execute()
            )

            if tasks_result.data:
                active_concerns.append(f"{len(tasks_result.data)} tasks due this week")
                constraints.append("Weekly task capacity is limited")

        except Exception as e:
            logger.debug(
                "Tasks query failed in tactical context",
                extra={"user_id": user_id, "error": str(e)},
            )

        return ScaleContext(
            scale=TimeScale.TACTICAL,
            active_concerns=active_concerns,
            decisions_pending=decisions_pending,
            goals=goals,
            constraints=constraints,
            calendar_events=calendar_events,
        )

    async def _gather_strategic_context(self, user_id: str) -> ScaleContext:
        """Gather context for strategic time scale (this quarter).

        Includes:
        - Quarterly targets and OKRs
        - Pipeline stage and forecast
        - Key milestones and dependencies

        Args:
            user_id: User ID for queries

        Returns:
            ScaleContext for strategic scale
        """
        db = self._get_db()
        now = datetime.now(UTC)
        end_of_quarter = now + timedelta(days=90)

        active_concerns: list[str] = []
        decisions_pending: list[str] = []
        goals: list[str] = []
        constraints: list[str] = []

        try:
            # Get quarterly goals
            goals_result = (
                db.table("goals")
                .select("id, title, target_date, priority")
                .eq("user_id", user_id)
                .eq("status", "active")
                .lte("target_date", end_of_quarter.isoformat())
                .order("priority", desc=True)
                .limit(10)
                .execute()
            )

            if goals_result.data:
                goals.extend([g.get("title", "Untitled goal") for g in goals_result.data])
                active_concerns.append(f"{len(goals_result.data)} active quarterly goals")

        except Exception as e:
            logger.debug(
                "Goals query failed in strategic context",
                extra={"user_id": user_id, "error": str(e)},
            )

        try:
            # Get pipeline/opportunity data
            pipeline_result = (
                db.table("leads")
                .select("id, company_name, lifecycle_stage, value")
                .eq("user_id", user_id)
                .in_(
                    "lifecycle_stage",
                    ["qualified", "proposal", "negotiation"],
                )
                .limit(10)
                .execute()
            )

            if pipeline_result.data:
                active_concerns.append(
                    f"{len(pipeline_result.data)} active opportunities in pipeline"
                )
                constraints.append("Pipeline capacity and resource allocation")

        except Exception as e:
            logger.debug(
                "Pipeline query failed in strategic context",
                extra={"user_id": user_id, "error": str(e)},
            )

        try:
            # Check for key milestones
            milestones_result = (
                db.table("goals")
                .select("id, title, target_date")
                .eq("user_id", user_id)
                .eq("status", "active")
                .gte("priority", 0.8)
                .lte("target_date", end_of_quarter.isoformat())
                .execute()
            )

            if milestones_result.data:
                decisions_pending.append(
                    f"{len(milestones_result.data)} high-priority milestones this quarter"
                )

        except Exception as e:
            logger.debug(
                "Milestones query failed in strategic context",
                extra={"user_id": user_id, "error": str(e)},
            )

        return ScaleContext(
            scale=TimeScale.STRATEGIC,
            active_concerns=active_concerns,
            decisions_pending=decisions_pending,
            goals=goals,
            constraints=constraints,
            calendar_events=None,
        )

    async def _gather_visionary_context(self, user_id: str) -> ScaleContext:
        """Gather context for visionary time scale (annual/long-term).

        Includes:
        - Annual strategy and objectives
        - Market trends and industry context
        - Long-term goals and vision

        Args:
            user_id: User ID for queries

        Returns:
            ScaleContext for visionary scale
        """
        db = self._get_db()
        now = datetime.now(UTC)
        end_of_year = now + timedelta(days=365)

        active_concerns: list[str] = []
        decisions_pending: list[str] = []
        goals: list[str] = []
        constraints: list[str] = []

        try:
            # Get annual/long-term goals
            goals_result = (
                db.table("goals")
                .select("id, title, target_date, description")
                .eq("user_id", user_id)
                .eq("status", "active")
                .gte("target_date", end_of_year - timedelta(days=275))
                .order("target_date")
                .limit(10)
                .execute()
            )

            if goals_result.data:
                goals.extend([g.get("title", "Untitled goal") for g in goals_result.data])
                active_concerns.append(f"{len(goals_result.data)} long-term objectives")

        except Exception as e:
            logger.debug(
                "Goals query failed in visionary context",
                extra={"user_id": user_id, "error": str(e)},
            )

        try:
            # Get market signals for trend context
            signals_result = (
                db.table("market_signals")
                .select("id, signal_type, summary")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )

            if signals_result.data:
                active_concerns.append("Market intelligence available")
                constraints.append("Industry trends and market conditions")

        except Exception as e:
            logger.debug(
                "Market signals query failed in visionary context",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Add general visionary constraints
        constraints.extend(
            [
                "Resource capacity over time",
                "Market evolution and competition",
                "Technology and capability development",
            ]
        )

        return ScaleContext(
            scale=TimeScale.VISIONARY,
            active_concerns=active_concerns,
            decisions_pending=decisions_pending,
            goals=goals,
            constraints=constraints,
            calendar_events=None,
        )

    async def _analyze_cross_scale_impacts(
        self,
        decision: str,
        primary_scale: TimeScale,
        contexts: dict[TimeScale, ScaleContext],
        context_hint: str | None = None,
    ) -> list[CrossScaleImpact]:
        """Analyze how a decision impacts each time scale.

        Uses LLM to reason about cross-scale relationships.

        Args:
            decision: The decision being analyzed
            primary_scale: The primary time scale of the decision
            contexts: Context at each time scale
            context_hint: Optional additional context

        Returns:
            List of CrossScaleImpact for each scale combination
        """
        impacts: list[CrossScaleImpact] = []

        # Build context summary for LLM
        context_summary = self._build_context_summary(contexts)

        prompt = f"""Analyze how this decision impacts outcomes at different time scales.

Decision: "{decision}"
Primary Time Scale: {primary_scale.value}

Context at each scale:
{context_summary}

{f"Additional context: {context_hint}" if context_hint else ""}

For each time scale (immediate, tactical, strategic, visionary), analyze:
1. How does this decision impact goals/concerns at that scale?
2. Is the impact supportive, conflicting, or neutral?
3. What is your confidence in this assessment?

Return ONLY a JSON array:
[
  {{
    "target_scale": "immediate|tactical|strategic|visionary",
    "impact_description": "description of impact",
    "alignment": "supports|conflicts|neutral",
    "explanation": "detailed explanation",
    "confidence": 0.0-1.0
  }}
]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You analyze cross-scale decision impacts. "
                    "Output ONLY valid JSON array, no markdown."
                ),
                temperature=0.2,
                max_tokens=1000,
            )

            # Clean response
            response_text = response.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [line for line in lines if not line.startswith("```")]
                response_text = "\n".join(lines).strip()

            data = json.loads(response_text)

            for item in data:
                try:
                    target_scale = TimeScale(item.get("target_scale", "tactical"))
                    impacts.append(
                        CrossScaleImpact(
                            source_scale=primary_scale,
                            target_scale=target_scale,
                            source_decision=decision,
                            impact_on_target=item.get("impact_description", ""),
                            alignment=item.get("alignment", "neutral"),
                            explanation=item.get("explanation", ""),
                            confidence=item.get("confidence", 0.7),
                        )
                    )
                except (ValueError, KeyError) as e:
                    logger.warning(
                        "Failed to parse impact item",
                        extra={"item": item, "error": str(e)},
                    )

        except Exception as e:
            logger.warning(
                "Cross-scale impact analysis failed",
                extra={"error": str(e)},
            )
            # Generate default impacts if LLM fails
            for scale in TimeScale:
                impacts.append(
                    CrossScaleImpact(
                        source_scale=primary_scale,
                        target_scale=scale,
                        source_decision=decision,
                        impact_on_target="Unable to analyze impact",
                        alignment="neutral",
                        explanation="Analysis unavailable due to processing error",
                        confidence=0.3,
                    )
                )

        return impacts

    def _build_context_summary(self, contexts: dict[TimeScale, ScaleContext]) -> str:
        """Build a summary of contexts for LLM prompt.

        Args:
            contexts: Dict mapping TimeScale to ScaleContext

        Returns:
            Formatted string summary
        """
        lines = []

        for scale in TimeScale:
            ctx = contexts.get(scale)
            if ctx:
                lines.append(f"\n{scale.value.upper()}:")
                if ctx.active_concerns:
                    lines.append(f"  Concerns: {', '.join(ctx.active_concerns[:3])}")
                if ctx.goals:
                    lines.append(f"  Goals: {', '.join(ctx.goals[:3])}")
                if ctx.constraints:
                    lines.append(f"  Constraints: {', '.join(ctx.constraints[:2])}")

        return "\n".join(lines)

    def _detect_conflicts(self, impacts: list[CrossScaleImpact]) -> list[TemporalConflict]:
        """Detect conflicts between time scales.

        Identifies when a decision supports one scale but conflicts with another.

        Args:
            impacts: List of cross-scale impacts

        Returns:
            List of detected TemporalConflicts
        """
        conflicts: list[TemporalConflict] = []

        # Group impacts by alignment
        supporting = [i for i in impacts if i.alignment == "supports"]
        conflicting = [i for i in impacts if i.alignment == "conflicts"]

        # Check for short-term gain, long-term pain pattern
        immediate_support = any(
            i for i in supporting if i.target_scale in [TimeScale.IMMEDIATE, TimeScale.TACTICAL]
        )
        long_term_conflict = any(
            i for i in conflicting if i.target_scale in [TimeScale.STRATEGIC, TimeScale.VISIONARY]
        )

        if immediate_support and long_term_conflict:
            conflict_scales = [TimeScale.IMMEDIATE, TimeScale.VISIONARY]
            conflict_scales.extend(
                [i.target_scale for i in supporting if i.target_scale not in conflict_scales]
            )
            conflict_scales.extend(
                [i.target_scale for i in conflicting if i.target_scale not in conflict_scales]
            )

            conflicts.append(
                TemporalConflict(
                    conflict_type="short_vs_long",
                    scales_involved=list(set(conflict_scales)),
                    description=(
                        "Decision provides short-term benefits but may conflict "
                        "with long-term strategic objectives"
                    ),
                    severity=0.7,
                    potential_resolutions=[
                        "Consider phased approach that addresses immediate needs while preserving long-term options",
                        "Identify modifications that align short-term actions with long-term goals",
                        "Evaluate if short-term gains justify potential long-term tradeoffs",
                    ],
                )
            )

        # Check for resource contention
        if len(conflicting) >= 2:
            conflict_scales = [i.target_scale for i in conflicting]
            conflicts.append(
                TemporalConflict(
                    conflict_type="resource_contention",
                    scales_involved=conflict_scales,
                    description=(
                        f"Decision creates resource contention across {len(conflicting)} time scales"
                    ),
                    severity=0.5,
                    potential_resolutions=[
                        "Prioritize which time scale is most critical",
                        "Look for creative solutions that serve multiple scales",
                        "Defer some commitments to reduce contention",
                    ],
                )
            )

        return conflicts

    async def _generate_scale_recommendations(
        self,
        decision: str,
        contexts: dict[TimeScale, ScaleContext],  # noqa: ARG002 - Reserved for future context-aware recommendations
        impacts: list[CrossScaleImpact],
        conflicts: list[TemporalConflict],
    ) -> dict[TimeScale, ScaleRecommendation]:
        """Generate recommendations for each time scale.

        Args:
            decision: The decision being analyzed
            contexts: Context at each scale
            impacts: Cross-scale impacts
            conflicts: Detected conflicts

        Returns:
            Dict mapping TimeScale to ScaleRecommendation
        """
        recommendations: dict[TimeScale, ScaleRecommendation] = {}

        # Build impact summary
        impact_summary = "\n".join(
            [
                f"- {i.target_scale.value}: {i.alignment} - {i.impact_on_target[:100]}"
                for i in impacts
            ]
        )

        conflict_summary = ""
        if conflicts:
            conflict_summary = "\n\nDetected Conflicts:\n" + "\n".join(
                [f"- {c.description}" for c in conflicts]
            )

        prompt = f"""Generate time-appropriate recommendations for this decision.

Decision: "{decision}"

Cross-Scale Impacts:
{impact_summary}
{conflict_summary}

For each time scale, provide one specific, actionable recommendation.

Return ONLY a JSON object:
{{
  "immediate": {{
    "recommendation": "specific action for today",
    "rationale": "why this makes sense now",
    "priority": 0.0-1.0
  }},
  "tactical": {{
    "recommendation": "action for this week",
    "rationale": "why this makes sense for weekly planning",
    "priority": 0.0-1.0
  }},
  "strategic": {{
    "recommendation": "action for this quarter",
    "rationale": "why this aligns with quarterly objectives",
    "priority": 0.0-1.0
  }},
  "visionary": {{
    "recommendation": "action for long-term",
    "rationale": "why this serves annual/vision goals",
    "priority": 0.0-1.0
  }}
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You generate time-scale-appropriate recommendations. "
                    "Output ONLY valid JSON, no markdown."
                ),
                temperature=0.3,
                max_tokens=800,
            )

            # Clean response
            response_text = response.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [line for line in lines if not line.startswith("```")]
                response_text = "\n".join(lines).strip()

            data = json.loads(response_text)

            for scale in TimeScale:
                scale_data = data.get(scale.value, {})
                recommendations[scale] = ScaleRecommendation(
                    scale=scale,
                    recommendation=scale_data.get("recommendation", "No specific recommendation"),
                    rationale=scale_data.get("rationale", ""),
                    priority=scale_data.get("priority", 0.5),
                )

        except Exception as e:
            logger.warning(
                "Recommendation generation failed",
                extra={"error": str(e)},
            )
            # Generate default recommendations
            for scale in TimeScale:
                recommendations[scale] = ScaleRecommendation(
                    scale=scale,
                    recommendation="Consider implications at this time scale",
                    rationale=f"Analysis for {scale.value} scale",
                    priority=0.5,
                )

        return recommendations

    async def _generate_reconciliation(
        self,
        decision: str,
        conflicts: list[TemporalConflict],
    ) -> str:
        """Generate reconciliation advice for detected conflicts.

        Args:
            decision: The decision being analyzed
            conflicts: List of detected conflicts

        Returns:
            Reconciliation advice string
        """
        conflict_descriptions = "\n".join([f"- {c.description}" for c in conflicts])
        potential_resolutions = []
        for c in conflicts:
            potential_resolutions.extend(c.potential_resolutions)

        prompt = f"""Provide reconciliation advice for a decision with cross-scale conflicts.

Decision: "{decision}"

Detected Conflicts:
{conflict_descriptions}

Potential Resolutions Suggested:
{chr(10).join(f"- {r}" for r in potential_resolutions[:5])}

Provide a concise (2-3 sentences) recommendation for how to reconcile these conflicts
and make a decision that balances short-term and long-term considerations.

Return ONLY the reconciliation advice text, no JSON or formatting."""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You provide practical reconciliation advice for conflicting priorities.",
                temperature=0.4,
                max_tokens=200,
            )

            return response.strip()

        except Exception as e:
            logger.warning(
                "Reconciliation generation failed",
                extra={"error": str(e)},
            )
            return (
                "Consider a phased approach that addresses immediate needs "
                "while preserving options for long-term objectives. "
                "Review tradeoffs with stakeholders before proceeding."
            )

    def _determine_alignment(self, conflicts: list[TemporalConflict]) -> str:
        """Determine overall alignment status.

        Args:
            conflicts: List of detected conflicts

        Returns:
            Alignment status string
        """
        if not conflicts:
            return "aligned"

        # Check severity
        max_severity = max(c.severity for c in conflicts)

        if max_severity >= 0.7:
            return "conflicted"
        else:
            return "needs_reconciliation"

    def _calculate_confidence(
        self,
        scale_contexts: dict[TimeScale, ScaleContext],
        impacts: list[CrossScaleImpact],
        conflicts: list[TemporalConflict],
    ) -> float:
        """Calculate overall confidence in the analysis.

        Args:
            scale_contexts: Context at each scale
            impacts: Cross-scale impacts
            conflicts: Detected conflicts

        Returns:
            Confidence score between 0 and 1
        """
        # Base confidence
        confidence = 0.7

        # Adjust for context quality
        for _scale, ctx in scale_contexts.items():
            if ctx.active_concerns or ctx.goals:
                confidence += 0.02
            else:
                confidence -= 0.03

        # Adjust for impact confidence
        if impacts:
            avg_impact_confidence = sum(i.confidence for i in impacts) / len(impacts)
            confidence = (confidence + avg_impact_confidence) / 2

        # Adjust for conflict severity
        if conflicts:
            max_severity = max(c.severity for c in conflicts)
            confidence -= max_severity * 0.1

        return max(0.3, min(1.0, confidence))
