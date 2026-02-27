"""Continuous self-improvement loop for ARIA (US-809).

This module enables ARIA to continuously improve by:
- Running periodic improvement cycles that analyze daily reflections
- Detecting performance regressions across time windows
- Tracking current focus areas for response calibration
- Recording and applying learnings from interactions
- Generating weekly improvement reports with trend analysis
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from pydantic import BaseModel, Field

from src.core.task_types import TaskType

logger = logging.getLogger(__name__)


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class ImprovementArea:
    """An identified area for improvement with gap analysis."""

    area: str
    current_performance: float
    target_performance: float
    gap: float
    improvement_actions: list[str] = field(default_factory=list)
    priority: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage/transmission."""
        return {
            "area": self.area,
            "current_performance": self.current_performance,
            "target_performance": self.target_performance,
            "gap": self.gap,
            "improvement_actions": self.improvement_actions,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImprovementArea:
        """Deserialize from dictionary."""
        return cls(
            area=data.get("area", ""),
            current_performance=float(data.get("current_performance", 0.0)),
            target_performance=float(data.get("target_performance", 1.0)),
            gap=float(data.get("gap", 0.0)),
            improvement_actions=data.get("improvement_actions", []),
            priority=int(data.get("priority", 1)),
        )


# ── Pydantic Response Models ────────────────────────────────────────────────


class ImprovementCycleResponse(BaseModel):
    """Response model for an improvement cycle run."""

    areas: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Identified improvement areas with gap analysis",
    )
    action_plan: list[str] = Field(
        default_factory=list,
        description="Generated action items for improvement",
    )
    performance_trend: dict[str, Any] = Field(
        default_factory=dict,
        description="Performance trend metrics over time",
    )


class WeeklyReportResponse(BaseModel):
    """Response model for a weekly improvement report."""

    summary: str = Field(default="", description="Executive summary of the week")
    interaction_count: int = Field(default=0, description="Total interactions this week")
    improvement_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Quantitative improvement metrics",
    )
    wins: list[str] = Field(
        default_factory=list,
        description="Notable wins and achievements this week",
    )
    areas_to_work_on: list[str] = Field(
        default_factory=list,
        description="Areas that need continued focus",
    )
    week_over_week: dict[str, Any] = Field(
        default_factory=dict,
        description="Comparison with previous week",
    )


# ── Service ──────────────────────────────────────────────────────────────────


class SelfImprovementLoop:
    """Continuous self-improvement loop for ARIA.

    Analyzes daily reflections to identify capability gaps,
    detect regressions, and generate actionable improvement plans.
    """

    def __init__(
        self,
        db_client: Any = None,
        llm_client: Any = None,
        self_reflection_service: Any = None,
        prediction_service: Any = None,
    ) -> None:
        """Initialize the Self-Improvement Loop.

        Args:
            db_client: Optional Supabase client (will create if not provided).
            llm_client: Optional LLM client (will create if not provided).
            self_reflection_service: Optional SelfReflectionService instance.
            prediction_service: Optional PredictionService instance.
        """
        if db_client is None:
            from src.db.supabase import SupabaseClient

            self._db = SupabaseClient.get_client()
        else:
            self._db = db_client

        if llm_client is None:
            from src.core.llm import LLMClient

            self._llm = LLMClient()
        else:
            self._llm = llm_client

        self._reflection_service = self_reflection_service
        self._prediction_service = prediction_service

    async def run_improvement_cycle(self, user_id: str) -> dict[str, Any]:
        """Run an improvement cycle analyzing recent reflections.

        Queries the last 7 daily reflections, aggregates outcomes,
        uses LLM to identify capability gaps, and generates an action plan.

        Args:
            user_id: User identifier.

        Returns:
            Dict with top_improvement_areas, action_plan, and performance_trend.
        """
        # Get last 7 daily reflections
        reflections = self._get_recent_reflections(user_id, days=7)

        if not reflections:
            return {
                "top_improvement_areas": [],
                "action_plan": [],
                "performance_trend": {"status": "no_data"},
            }

        # Aggregate outcomes
        total_positive = 0
        total_negative = 0
        all_patterns: list[str] = []
        all_opportunities: list[dict[str, Any]] = []

        for r in reflections:
            total_positive += len(r.get("positive_outcomes", []))
            total_negative += len(r.get("negative_outcomes", []))
            all_patterns.extend(r.get("patterns_detected", []))
            all_opportunities.extend(r.get("improvement_opportunities", []))

        # Use LLM to analyze and identify gaps
        areas = await self._analyze_gaps(
            total_positive=total_positive,
            total_negative=total_negative,
            patterns=all_patterns,
            opportunities=all_opportunities,
        )

        # Build performance trend
        performance_trend = {
            "total_reflections": len(reflections),
            "total_positive": total_positive,
            "total_negative": total_negative,
            "positive_ratio": (
                total_positive / (total_positive + total_negative)
                if (total_positive + total_negative) > 0
                else 0.0
            ),
        }

        # Generate action plan from areas
        action_plan = []
        for area in areas:
            for action in area.improvement_actions:
                action_plan.append(action)

        # Store cycle result
        self._store_improvement_cycle(
            user_id=user_id,
            areas=areas,
            performance_trend=performance_trend,
            action_plan=action_plan,
        )

        return {
            "top_improvement_areas": [a.to_dict() for a in areas],
            "action_plan": action_plan,
            "performance_trend": performance_trend,
        }

    async def detect_regression(self, user_id: str) -> list[str]:
        """Detect performance regressions by comparing recent vs baseline.

        Splits last 14 reflections into recent (7) and baseline (7),
        compares positive/negative ratios to flag declines.

        Args:
            user_id: User identifier.

        Returns:
            List of regression description strings.
        """
        reflections = self._get_recent_reflections(user_id, days=14)

        if len(reflections) < 4:
            return []

        mid = len(reflections) // 2
        # Reflections are ordered desc, so first half is recent
        recent = reflections[:mid]
        baseline = reflections[mid:]

        recent_positive = sum(len(r.get("positive_outcomes", [])) for r in recent)
        recent_negative = sum(len(r.get("negative_outcomes", [])) for r in recent)
        baseline_positive = sum(len(r.get("positive_outcomes", [])) for r in baseline)
        baseline_negative = sum(len(r.get("negative_outcomes", [])) for r in baseline)

        regressions: list[str] = []

        # Compare positive ratios
        recent_total = recent_positive + recent_negative
        baseline_total = baseline_positive + baseline_negative

        if recent_total > 0 and baseline_total > 0:
            recent_ratio = recent_positive / recent_total
            baseline_ratio = baseline_positive / baseline_total

            if recent_ratio < baseline_ratio - 0.1:
                regressions.append(
                    f"Overall positive outcome ratio declined from "
                    f"{baseline_ratio:.0%} to {recent_ratio:.0%}"
                )

        # Check for increase in negative outcomes
        if baseline_negative > 0 and recent_negative > baseline_negative * 1.5:
            regressions.append(
                f"Negative outcomes increased from {baseline_negative} to {recent_negative} "
                f"({((recent_negative - baseline_negative) / baseline_negative):.0%} increase)"
            )

        # Check for decrease in positive outcomes
        if baseline_positive > 0 and recent_positive < baseline_positive * 0.7:
            regressions.append(
                f"Positive outcomes decreased from {baseline_positive} to {recent_positive} "
                f"({((baseline_positive - recent_positive) / baseline_positive):.0%} decrease)"
            )

        return regressions

    async def get_current_focus(self, user_id: str) -> list[str]:
        """Get the top 3 current improvement focus areas.

        Queries the latest improvement cycle and returns the
        highest-priority area names for orchestrator use.

        Args:
            user_id: User identifier.

        Returns:
            List of up to 3 focus area name strings.
        """
        try:
            result = (
                self._db.table("companion_improvement_cycles")
                .select("improvement_areas")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if not result.data:
                return []

            areas_data = result.data[0].get("improvement_areas", [])
            if not areas_data:
                return []

            # Sort by priority and return top 3 names
            areas = [ImprovementArea.from_dict(a) for a in areas_data]
            areas.sort(key=lambda a: a.priority)
            return [a.area for a in areas[:3]]

        except Exception as e:
            logger.warning(
                "Failed to get current focus areas",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def apply_learning(
        self,
        user_id: str,
        area: str,
        learning_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Record and apply a learning from interactions.

        Stores the learning in companion_learnings and optionally
        triggers personality adjustments if learning_data indicates.

        Args:
            user_id: User identifier.
            area: The improvement area this learning relates to.
            learning_data: Details of what was learned.

        Returns:
            Confirmation dict with learning_id and applied status.
        """
        learning_id = str(uuid.uuid4())

        applied_changes: dict[str, Any] = {}

        # Check if learning includes personality adjustment
        if "personality_adjustment" in learning_data:
            try:
                adjustment = learning_data["personality_adjustment"]
                applied_changes["personality_adjustment"] = adjustment
                logger.info(
                    "Applied personality adjustment from learning",
                    extra={"user_id": user_id, "area": area, "adjustment": adjustment},
                )
            except Exception as e:
                logger.warning(
                    "Failed to apply personality adjustment",
                    extra={"user_id": user_id, "error": str(e)},
                )

        # Store learning
        try:
            self._db.table("companion_learnings").insert(
                {
                    "id": learning_id,
                    "user_id": user_id,
                    "area": area,
                    "learning_data": learning_data,
                    "applied_changes": applied_changes,
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "Failed to store learning",
                extra={"user_id": user_id, "error": str(e)},
            )

        return {
            "learning_id": learning_id,
            "area": area,
            "applied": True,
            "applied_changes": applied_changes,
        }

    async def generate_weekly_report(self, user_id: str) -> dict[str, Any]:
        """Generate a weekly improvement report with trend analysis.

        Compares this week's reflections with the previous week,
        queries improvement cycles for trend, and uses LLM to generate
        a summary with wins and areas to work on.

        Args:
            user_id: User identifier.

        Returns:
            Dict with summary, interaction_count, improvement_metrics,
            wins, areas_to_work_on, and week_over_week comparison.
        """
        now = datetime.now(UTC)
        week_start = now - timedelta(days=7)
        prev_week_start = now - timedelta(days=14)

        # Get this week and previous week reflections
        this_week = self._get_reflections_in_range(user_id, week_start, now)
        prev_week = self._get_reflections_in_range(user_id, prev_week_start, week_start)

        # Aggregate metrics
        this_positive = sum(len(r.get("positive_outcomes", [])) for r in this_week)
        this_negative = sum(len(r.get("negative_outcomes", [])) for r in this_week)
        prev_positive = sum(len(r.get("positive_outcomes", [])) for r in prev_week)
        prev_negative = sum(len(r.get("negative_outcomes", [])) for r in prev_week)

        this_interactions = sum(r.get("total_interactions", 0) for r in this_week)
        prev_interactions = sum(r.get("total_interactions", 0) for r in prev_week)

        # Build week-over-week comparison
        week_over_week: dict[str, Any] = {
            "interactions_change": this_interactions - prev_interactions,
            "positive_change": this_positive - prev_positive,
            "negative_change": this_negative - prev_negative,
        }

        improvement_metrics: dict[str, Any] = {
            "total_positive": this_positive,
            "total_negative": this_negative,
            "positive_ratio": (
                this_positive / (this_positive + this_negative)
                if (this_positive + this_negative) > 0
                else 0.0
            ),
            "reflection_count": len(this_week),
        }

        # Use LLM to generate summary
        report = await self._generate_report_summary(
            this_week=this_week,
            prev_week=prev_week,
            this_positive=this_positive,
            this_negative=this_negative,
            prev_positive=prev_positive,
            prev_negative=prev_negative,
        )

        return {
            "summary": report.get("summary", "No report data available."),
            "interaction_count": this_interactions,
            "improvement_metrics": improvement_metrics,
            "wins": report.get("wins", []),
            "areas_to_work_on": report.get("areas_to_work_on", []),
            "week_over_week": week_over_week,
        }

    # ── Private Methods ──────────────────────────────────────────────────────

    def _get_recent_reflections(
        self,
        user_id: str,
        days: int,
    ) -> list[dict[str, Any]]:
        """Get recent daily reflections for a user."""
        try:
            since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            result = (
                self._db.table("daily_reflections")
                .select("*")
                .eq("user_id", user_id)
                .gte("reflection_date", since)
                .order("reflection_date", desc=True)
                .execute()
            )
            return cast(list[dict[str, Any]], result.data or [])
        except Exception as e:
            logger.warning(
                "Failed to get recent reflections",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    def _get_reflections_in_range(
        self,
        user_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Get daily reflections within a date range."""
        try:
            result = (
                self._db.table("daily_reflections")
                .select("*")
                .eq("user_id", user_id)
                .gte("reflection_date", start.isoformat())
                .lte("reflection_date", end.isoformat())
                .order("reflection_date", desc=True)
                .execute()
            )
            return cast(list[dict[str, Any]], result.data or [])
        except Exception as e:
            logger.warning(
                "Failed to get reflections in range",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    def _store_improvement_cycle(
        self,
        user_id: str,
        areas: list[ImprovementArea],
        performance_trend: dict[str, Any],
        action_plan: list[str],
    ) -> None:
        """Store an improvement cycle result."""
        try:
            self._db.table("companion_improvement_cycles").insert(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "improvement_areas": [a.to_dict() for a in areas],
                    "performance_trend": performance_trend,
                    "action_plan": action_plan,
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "Failed to store improvement cycle",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def _analyze_gaps(
        self,
        total_positive: int,
        total_negative: int,
        patterns: list[str],
        opportunities: list[dict[str, Any]],
    ) -> list[ImprovementArea]:
        """Use LLM to analyze performance gaps and generate improvement areas."""
        prompt = f"""Analyze ARIA's performance over the past week and identify improvement areas.

DATA:
- Positive outcomes: {total_positive}
- Negative outcomes: {total_negative}
- Patterns detected: {patterns[:10]}
- Improvement opportunities: {json.dumps(opportunities[:10])}

Identify 3-5 specific capability gaps with priorities. Output ONLY valid JSON:
{{
    "areas": [
        {{
            "area": "specific capability area",
            "current_performance": 0.6,
            "target_performance": 0.85,
            "gap": 0.25,
            "improvement_actions": ["specific action 1", "specific action 2"],
            "priority": 1
        }}
    ]
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                task=TaskType.GENERAL,
            )

            content = self._extract_json(response)
            data = json.loads(content)
            return [ImprovementArea.from_dict(a) for a in data.get("areas", [])]

        except Exception as e:
            logger.warning(
                "Failed to analyze gaps via LLM",
                extra={"error": str(e)},
            )
            return []

    async def _generate_report_summary(
        self,
        this_week: list[dict[str, Any]],
        prev_week: list[dict[str, Any]],
        this_positive: int,
        this_negative: int,
        prev_positive: int,
        prev_negative: int,
    ) -> dict[str, Any]:
        """Use LLM to generate a weekly report summary."""
        prompt = f"""Generate a weekly improvement report for ARIA.

THIS WEEK:
- Reflections: {len(this_week)}
- Positive outcomes: {this_positive}
- Negative outcomes: {this_negative}

PREVIOUS WEEK:
- Reflections: {len(prev_week)}
- Positive outcomes: {prev_positive}
- Negative outcomes: {prev_negative}

Generate a concise report. Output ONLY valid JSON:
{{
    "summary": "One paragraph executive summary of the week's performance",
    "wins": ["notable win 1", "notable win 2"],
    "areas_to_work_on": ["area needing focus 1", "area needing focus 2"]
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                task=TaskType.GENERAL,
            )

            content = self._extract_json(response)
            return cast(dict[str, Any], json.loads(content))

        except Exception as e:
            logger.warning(
                "Failed to generate weekly report summary",
                extra={"error": str(e)},
            )
            return {
                "summary": "Weekly report generation unavailable.",
                "wins": [],
                "areas_to_work_on": [],
            }

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks."""
        content = text.strip()

        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        return content
