"""Self-reflection and self-correction service for ARIA.

This module enables ARIA to honestly assess her own performance,
acknowledge mistakes without excuses, and continuously improve.

Key features:
- DailyReflection: Captures daily interaction outcomes and patterns
- SelfAssessment: Weekly/periodic assessment of ARIA's capabilities
- SelfReflectionService: Generates reflections, assessments, and acknowledgments
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, cast

from pydantic import BaseModel, Field

from src.core.task_types import TaskType

logger = logging.getLogger(__name__)


class Trend(str, Enum):
    """Trend direction for self-assessment scores."""

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class DailyReflection:
    """A daily reflection on ARIA's performance."""

    id: str
    user_id: str
    reflection_date: datetime
    total_interactions: int
    positive_outcomes: list[dict[str, Any]] = field(default_factory=list)
    negative_outcomes: list[dict[str, Any]] = field(default_factory=list)
    patterns_detected: list[str] = field(default_factory=list)
    improvement_opportunities: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage/transmission."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "reflection_date": self.reflection_date.isoformat(),
            "total_interactions": self.total_interactions,
            "positive_outcomes": self.positive_outcomes,
            "negative_outcomes": self.negative_outcomes,
            "patterns_detected": self.patterns_detected,
            "improvement_opportunities": self.improvement_opportunities,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyReflection:
        """Deserialize from dictionary."""
        reflection_date = data.get("reflection_date")
        if isinstance(reflection_date, str):
            reflection_date = datetime.fromisoformat(reflection_date.replace("Z", "+00:00"))
        elif reflection_date is None:
            reflection_date = datetime.now(UTC)

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif created_at is None:
            created_at = datetime.now(UTC)

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", ""),
            reflection_date=reflection_date,
            total_interactions=data.get("total_interactions", 0),
            positive_outcomes=data.get("positive_outcomes", []),
            negative_outcomes=data.get("negative_outcomes", []),
            patterns_detected=data.get("patterns_detected", []),
            improvement_opportunities=data.get("improvement_opportunities", []),
            created_at=created_at,
        )


@dataclass
class SelfAssessment:
    """A periodic self-assessment of ARIA's capabilities."""

    id: str
    user_id: str
    assessment_period: str  # 'daily', 'weekly', 'monthly'
    overall_score: float  # 0.0 to 1.0
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    mistakes_acknowledged: list[dict[str, Any]] = field(default_factory=list)
    improvement_plan: list[dict[str, Any]] = field(default_factory=list)
    trend: Trend = Trend.STABLE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage/transmission."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "assessment_period": self.assessment_period,
            "overall_score": round(self.overall_score, 3),
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "mistakes_acknowledged": self.mistakes_acknowledged,
            "improvement_plan": self.improvement_plan,
            "trend": self.trend.value,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelfAssessment:
        """Deserialize from dictionary."""
        trend_str = data.get("trend", "stable")
        trend = Trend(trend_str) if trend_str in [e.value for e in Trend] else Trend.STABLE

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif created_at is None:
            created_at = datetime.now(UTC)

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", ""),
            assessment_period=data.get("assessment_period", "weekly"),
            overall_score=float(data.get("overall_score", 0.5)),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            mistakes_acknowledged=data.get("mistakes_acknowledged", []),
            improvement_plan=data.get("improvement_plan", []),
            trend=trend,
            created_at=created_at,
        )


# Pydantic models for API


class ReflectRequest(BaseModel):
    """Request model for triggering a reflection."""

    period: str = Field(
        default="daily",
        description="Reflection period: daily, weekly, monthly",
    )


class DailyReflectionResponse(BaseModel):
    """Response model for daily reflection."""

    id: str
    reflection_date: str
    total_interactions: int
    positive_outcomes: list[dict[str, Any]]
    negative_outcomes: list[dict[str, Any]]
    patterns_detected: list[str]
    improvement_opportunities: list[dict[str, Any]]


class SelfAssessmentResponse(BaseModel):
    """Response model for self-assessment."""

    id: str
    assessment_period: str
    overall_score: float
    strengths: list[str]
    weaknesses: list[str]
    mistakes_acknowledged: list[dict[str, Any]]
    improvement_plan: list[dict[str, Any]]
    trend: str


class ImprovementPlanResponse(BaseModel):
    """Response model for improvement plan."""

    areas: list[dict[str, Any]]
    last_updated: str
    progress_indicators: dict[str, Any]


class AcknowledgeMistakeRequest(BaseModel):
    """Request model for acknowledging a mistake."""

    mistake_description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Description of the mistake to acknowledge",
    )


class AcknowledgeMistakeResponse(BaseModel):
    """Response model for mistake acknowledgment."""

    acknowledgment: str
    recorded: bool


class SelfReflectionService:
    """
    Service for self-reflection and self-correction capabilities.

    This service enables ARIA to:
    - Run daily reflections on interactions and outcomes
    - Generate periodic self-assessments with trend detection
    - Get improvement plans with prioritized actions
    - Acknowledge mistakes honestly without excuses
    """

    def __init__(
        self,
        db_client: Any = None,
        llm_client: Any = None,
        personality_service: Any = None,
    ) -> None:
        """
        Initialize the Self-Reflection service.

        Args:
            db_client: Optional Supabase client (will create if not provided).
            llm_client: Optional LLM client (will create if not provided).
            personality_service: Optional PersonalityService for tone calibration.
        """
        # Lazy imports to avoid circular dependencies
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

        self._personality = personality_service

    async def run_daily_reflection(self, user_id: str) -> dict[str, Any]:
        """
        Run a daily reflection on ARIA's performance for a user.

        Steps:
        1. Query conversations + messages for today's user interactions
        2. Query feedback for today's ratings (up/down counts)
        3. Query aria_activity for today's actions
        4. Use LLM to classify outcomes as positive/negative
        5. Use LLM to detect patterns across outcomes
        6. Use LLM to identify improvement opportunities
        7. Store in daily_reflections table
        8. Return reflection data

        Args:
            user_id: User identifier.

        Returns:
            Dict with reflection data including outcomes, patterns, and opportunities.
        """
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Gather data sources
        conversation_summary = await self._get_today_conversations(user_id, today_start)
        feedback_summary = await self._get_today_feedback(user_id, today_start)
        action_summary = await self._get_today_actions(user_id, today_start)

        total_interactions = (
            conversation_summary.get("count", 0)
            + feedback_summary.get("count", 0)
            + action_summary.get("count", 0)
        )

        # If no interactions, return empty reflection
        if total_interactions == 0:
            return self._create_empty_reflection(user_id, now)

        # Generate reflection via LLM
        reflection_data = await self._generate_reflection_analysis(
            conversation_summary=conversation_summary,
            feedback_summary=feedback_summary,
            action_summary=action_summary,
        )

        # Build reflection object
        reflection = DailyReflection(
            id=str(uuid.uuid4()),
            user_id=user_id,
            reflection_date=now,
            total_interactions=total_interactions,
            positive_outcomes=reflection_data.get("positive_outcomes", []),
            negative_outcomes=reflection_data.get("negative_outcomes", []),
            patterns_detected=reflection_data.get("patterns_detected", []),
            improvement_opportunities=reflection_data.get("improvement_opportunities", []),
        )

        # Store in database
        await self._store_reflection(reflection)

        logger.info(
            "Completed daily reflection",
            extra={
                "user_id": user_id,
                "reflection_id": reflection.id,
                "total_interactions": total_interactions,
            },
        )

        return reflection.to_dict()

    async def generate_self_assessment(
        self,
        user_id: str,
        period: str = "weekly",
    ) -> dict[str, Any]:
        """
        Generate a periodic self-assessment of ARIA's capabilities.

        Steps:
        1. Aggregate daily_reflections for the period (7 days for weekly)
        2. Calculate overall score from positive/negative ratio
        3. Use LLM to identify strengths (consistent positives)
        4. Use LLM to identify weaknesses (consistent negatives)
        5. Generate specific mistake acknowledgments
        6. Generate improvement plan with prioritized actions
        7. Determine trend by comparing to previous period
        8. Store in companion_self_assessments
        9. Return assessment data

        Args:
            user_id: User identifier.
            period: Assessment period ('daily', 'weekly', 'monthly').

        Returns:
            Dict with assessment data including score, strengths, weaknesses, and plan.
        """
        now = datetime.now(UTC)

        # Determine period length
        period_days = {
            "daily": 1,
            "weekly": 7,
            "monthly": 30,
        }.get(period, 7)

        period_start = now - timedelta(days=period_days)

        # Get reflections for the period
        reflections = await self._get_reflections_for_period(user_id, period_start)

        # Calculate score from reflections
        overall_score = self._calculate_score_from_reflections(reflections)

        # Generate assessment via LLM
        assessment_data = await self._generate_assessment_analysis(
            reflections=reflections,
            period=period,
        )

        # Get previous assessment for trend calculation
        previous_assessment = await self._get_previous_assessment(user_id, period)
        trend = self._calculate_trend(
            current_score=overall_score,
            previous_assessment=previous_assessment,
        )

        # Build assessment object
        assessment = SelfAssessment(
            id=str(uuid.uuid4()),
            user_id=user_id,
            assessment_period=period,
            overall_score=overall_score,
            strengths=assessment_data.get("strengths", []),
            weaknesses=assessment_data.get("weaknesses", []),
            mistakes_acknowledged=assessment_data.get("mistakes_acknowledged", []),
            improvement_plan=assessment_data.get("improvement_plan", []),
            trend=trend,
        )

        # Store in database
        await self._store_assessment(assessment)

        logger.info(
            "Generated self-assessment",
            extra={
                "user_id": user_id,
                "assessment_id": assessment.id,
                "period": period,
                "score": overall_score,
                "trend": trend.value,
            },
        )

        return assessment.to_dict()

    async def get_improvement_plan(self, user_id: str) -> dict[str, Any]:
        """
        Get the current improvement plan for a user.

        Args:
            user_id: User identifier.

        Returns:
            Dict with prioritized improvement areas and actions.
        """
        # Get latest assessment
        assessment = await self._get_latest_assessment(user_id)

        if assessment is None:
            # Return default structure if no assessment exists
            return {
                "areas": [],
                "last_updated": datetime.now(UTC).isoformat(),
                "progress_indicators": {
                    "has_assessment": False,
                    "message": "No assessment available yet. Run a self-assessment first.",
                },
            }

        # Sort improvement plan by priority
        areas = sorted(
            assessment.improvement_plan,
            key=lambda x: x.get("priority", 999),
        )

        return {
            "areas": areas,
            "last_updated": assessment.created_at.isoformat(),
            "progress_indicators": {
                "has_assessment": True,
                "overall_score": assessment.overall_score,
                "trend": assessment.trend.value,
                "strengths_count": len(assessment.strengths),
                "weaknesses_count": len(assessment.weaknesses),
            },
        }

    async def acknowledge_mistake(
        self,
        user_id: str,
        mistake_description: str,
    ) -> str:
        """
        Generate an honest acknowledgment of a mistake.

        Key: NO EXCUSES - use "I" statements, accept full responsibility.

        Args:
            user_id: User identifier.
            mistake_description: Description of the mistake.

        Returns:
            Honest acknowledgment text.
        """
        # Get personality directness for tone calibration
        directness = await self._get_personality_directness(user_id)

        prompt = f"""Generate an honest acknowledgment of this mistake. Rules:
- Use "I" statements, accept full responsibility
- NO excuses or explanations that deflect blame
- NO "but" clauses that minimize the mistake
- Be specific about what went wrong
- Commit to improvement

Mistake: {mistake_description}

Output ONLY the acknowledgment text (2-3 sentences). Be {self._get_tone_description(directness)}."""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=150,
                task=TaskType.GENERAL,
                agent_id="self_reflection",
            )
            acknowledgment = response.strip().strip('"')

            # Record acknowledgment for future reference
            await self._record_mistake_acknowledgment(
                user_id=user_id,
                mistake_description=mistake_description,
                acknowledgment=acknowledgment,
            )

            return acknowledgment

        except Exception as e:
            logger.error(
                "Failed to generate mistake acknowledgment",
                extra={"user_id": user_id, "error": str(e)},
            )
            # Fallback acknowledgment
            return (
                "I made a mistake here, and I take responsibility for it. I will work to do better."
            )

    # ── Private Methods ─────────────────────────────────────────────────────

    async def _get_today_conversations(
        self,
        user_id: str,
        today_start: datetime,
    ) -> dict[str, Any]:
        """Get summary of today's conversations for a user."""
        try:
            # Query conversations from today
            result = (
                self._db.table("conversations")
                .select("id, messages")
                .eq("user_id", user_id)
                .gte("created_at", today_start.isoformat())
                .execute()
            )

            conversations = result.data or []
            total_messages = sum(len(c.get("messages", [])) for c in conversations)

            return {
                "count": len(conversations),
                "message_count": total_messages,
                "summary": f"{len(conversations)} conversations with {total_messages} messages",
            }

        except Exception as e:
            logger.warning(
                "Failed to get today's conversations",
                extra={"user_id": user_id, "error": str(e)},
            )
            return {"count": 0, "message_count": 0, "summary": "No conversation data available"}

    async def _get_today_feedback(
        self,
        user_id: str,
        today_start: datetime,
    ) -> dict[str, Any]:
        """Get summary of today's feedback for a user."""
        try:
            # Query feedback from today
            result = (
                self._db.table("feedback")
                .select("rating")
                .eq("user_id", user_id)
                .gte("created_at", today_start.isoformat())
                .execute()
            )

            feedback = result.data or []
            up_count = sum(1 for f in feedback if f.get("rating") == "up")
            down_count = sum(1 for f in feedback if f.get("rating") == "down")

            return {
                "count": len(feedback),
                "up_count": up_count,
                "down_count": down_count,
                "summary": f"{up_count} positive, {down_count} negative ratings",
            }

        except Exception as e:
            logger.warning(
                "Failed to get today's feedback",
                extra={"user_id": user_id, "error": str(e)},
            )
            return {
                "count": 0,
                "up_count": 0,
                "down_count": 0,
                "summary": "No feedback data available",
            }

    async def _get_today_actions(
        self,
        user_id: str,
        today_start: datetime,
    ) -> dict[str, Any]:
        """Get summary of today's ARIA actions for a user."""
        try:
            # Query aria_activity from today
            result = (
                self._db.table("aria_activity")
                .select("action_type, status")
                .eq("user_id", user_id)
                .gte("created_at", today_start.isoformat())
                .execute()
            )

            actions = result.data or []
            completed = sum(1 for a in actions if a.get("status") == "completed")
            pending = sum(1 for a in actions if a.get("status") == "pending")
            failed = sum(1 for a in actions if a.get("status") == "failed")

            return {
                "count": len(actions),
                "completed": completed,
                "pending": pending,
                "failed": failed,
                "summary": f"{completed} completed, {pending} pending, {failed} failed",
            }

        except Exception as e:
            logger.warning(
                "Failed to get today's actions",
                extra={"user_id": user_id, "error": str(e)},
            )
            return {
                "count": 0,
                "completed": 0,
                "pending": 0,
                "failed": 0,
                "summary": "No action data available",
            }

    async def _generate_reflection_analysis(
        self,
        conversation_summary: dict[str, Any],
        feedback_summary: dict[str, Any],
        action_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate reflection analysis via LLM."""
        prompt = f"""Analyze ARIA's performance for today based on this activity data:

CONVERSATIONS: {conversation_summary.get("summary", "No data")}
FEEDBACK RATINGS: {feedback_summary.get("summary", "No data")} (thumbs up: {feedback_summary.get("up_count", 0)}, down: {feedback_summary.get("down_count", 0)})
ACTIONS TAKEN: {action_summary.get("summary", "No data")}

Classify outcomes and identify patterns. Output ONLY valid JSON:
{{
    "positive_outcomes": [{{"description": "what went well", "evidence": "specific evidence"}}],
    "negative_outcomes": [{{"description": "what didn't go well", "evidence": "specific evidence"}}],
    "patterns_detected": ["observed pattern 1", "observed pattern 2"],
    "improvement_opportunities": [{{"area": "area for improvement", "action": "specific action to take"}}]
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                task=TaskType.GENERAL,
                agent_id="self_reflection",
            )

            content = self._extract_json(response)
            return cast(dict[str, Any], json.loads(content))

        except Exception as e:
            logger.warning(
                "Failed to generate reflection analysis",
                extra={"error": str(e)},
            )
            return {
                "positive_outcomes": [],
                "negative_outcomes": [],
                "patterns_detected": [],
                "improvement_opportunities": [],
            }

    async def _generate_assessment_analysis(
        self,
        reflections: list[DailyReflection],
        period: str,
    ) -> dict[str, Any]:
        """Generate assessment analysis via LLM."""
        # Build summary of reflections
        total_positive = sum(len(r.positive_outcomes) for r in reflections)
        total_negative = sum(len(r.negative_outcomes) for r in reflections)
        all_patterns = []
        for r in reflections:
            all_patterns.extend(r.patterns_detected)

        reflection_summary = f"""Over {len(reflections)} days:
- Total positive outcomes: {total_positive}
- Total negative outcomes: {total_negative}
- Patterns detected: {len(set(all_patterns))}
- Top patterns: {list(set(all_patterns))[:5]}"""

        prompt = f"""Generate a {period} self-assessment for ARIA based on daily reflections:

{reflection_summary}

Identify strengths, weaknesses, and create an improvement plan. Output ONLY valid JSON:
{{
    "strengths": ["consistent positive capability 1", "consistent positive capability 2"],
    "weaknesses": ["area needing improvement 1", "area needing improvement 2"],
    "mistakes_acknowledged": [{{"mistake": "specific mistake", "learning": "what was learned"}}],
    "improvement_plan": [{{"area": "improvement area", "priority": 1, "actions": ["action 1", "action 2"]}}]
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                task=TaskType.GENERAL,
                agent_id="self_reflection",
            )

            content = self._extract_json(response)
            return cast(dict[str, Any], json.loads(content))

        except Exception as e:
            logger.warning(
                "Failed to generate assessment analysis",
                extra={"error": str(e)},
            )
            return {
                "strengths": [],
                "weaknesses": [],
                "mistakes_acknowledged": [],
                "improvement_plan": [],
            }

    def _calculate_score_from_reflections(
        self,
        reflections: list[DailyReflection],
    ) -> float:
        """Calculate overall score from daily reflections."""
        if not reflections:
            return 0.5  # Default neutral score

        total_positive = sum(len(r.positive_outcomes) for r in reflections)
        total_negative = sum(len(r.negative_outcomes) for r in reflections)
        total = total_positive + total_negative

        if total == 0:
            return 0.5

        # Score based on positive ratio, clamped to 0-1
        score = total_positive / total
        return max(0.0, min(1.0, score))

    def _calculate_trend(
        self,
        current_score: float,
        previous_assessment: SelfAssessment | None,
    ) -> Trend:
        """Calculate trend based on score comparison."""
        if previous_assessment is None:
            return Trend.STABLE

        previous_score = previous_assessment.overall_score
        threshold = 0.05  # 5% change threshold

        if current_score > previous_score + threshold:
            return Trend.IMPROVING
        elif current_score < previous_score - threshold:
            return Trend.DECLINING
        else:
            return Trend.STABLE

    async def _get_reflections_for_period(
        self,
        user_id: str,
        period_start: datetime,
    ) -> list[DailyReflection]:
        """Get daily reflections for a period."""
        try:
            result = (
                self._db.table("daily_reflections")
                .select("*")
                .eq("user_id", user_id)
                .gte("reflection_date", period_start.isoformat())
                .order("reflection_date", desc=True)
                .execute()
            )

            if not result.data:
                return []

            return [DailyReflection.from_dict(cast(dict[str, Any], row)) for row in result.data]

        except Exception as e:
            logger.warning(
                "Failed to get reflections for period",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_previous_assessment(
        self,
        user_id: str,
        period: str,
    ) -> SelfAssessment | None:
        """Get the previous assessment for trend calculation."""
        try:
            result = (
                self._db.table("companion_self_assessments")
                .select("*")
                .eq("user_id", user_id)
                .eq("assessment_period", period)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if not result.data:
                return None

            return SelfAssessment.from_dict(cast(dict[str, Any], result.data[0]))

        except Exception as e:
            logger.warning(
                "Failed to get previous assessment",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_latest_assessment(self, user_id: str) -> SelfAssessment | None:
        """Get the latest assessment for a user."""
        try:
            result = (
                self._db.table("companion_self_assessments")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if not result.data:
                return None

            return SelfAssessment.from_dict(cast(dict[str, Any], result.data[0]))

        except Exception as e:
            logger.warning(
                "Failed to get latest assessment",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _store_reflection(self, reflection: DailyReflection) -> None:
        """Store a daily reflection in the database."""
        try:
            self._db.table("daily_reflections").insert(
                {
                    "id": reflection.id,
                    "user_id": reflection.user_id,
                    "reflection_date": reflection.reflection_date.isoformat(),
                    "total_interactions": reflection.total_interactions,
                    "positive_outcomes": reflection.positive_outcomes,
                    "negative_outcomes": reflection.negative_outcomes,
                    "patterns_detected": reflection.patterns_detected,
                    "improvement_opportunities": reflection.improvement_opportunities,
                    "created_at": reflection.created_at.isoformat(),
                }
            ).execute()

        except Exception:
            logger.exception(
                "Failed to store reflection",
                extra={"reflection_id": reflection.id, "user_id": reflection.user_id},
            )
            raise

    async def _store_assessment(self, assessment: SelfAssessment) -> None:
        """Store a self-assessment in the database."""
        try:
            self._db.table("companion_self_assessments").insert(
                {
                    "id": assessment.id,
                    "user_id": assessment.user_id,
                    "assessment_period": assessment.assessment_period,
                    "overall_score": assessment.overall_score,
                    "strengths": assessment.strengths,
                    "weaknesses": assessment.weaknesses,
                    "mistakes_acknowledged": assessment.mistakes_acknowledged,
                    "improvement_plan": assessment.improvement_plan,
                    "trend": assessment.trend.value,
                    "created_at": assessment.created_at.isoformat(),
                }
            ).execute()

        except Exception:
            logger.exception(
                "Failed to store assessment",
                extra={"assessment_id": assessment.id, "user_id": assessment.user_id},
            )
            raise

    async def _record_mistake_acknowledgment(
        self,
        user_id: str,
        mistake_description: str,
        acknowledgment: str,
    ) -> None:
        """Record a mistake acknowledgment for future reference."""
        try:
            self._db.table("companion_mistake_acknowledgments").insert(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "mistake_description": mistake_description,
                    "acknowledgment": acknowledgment,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ).execute()

        except Exception as e:
            # Non-critical - just log the error
            logger.warning(
                "Failed to record mistake acknowledgment",
                extra={"user_id": user_id, "error": str(e)},
            )

    def _create_empty_reflection(self, user_id: str, now: datetime) -> dict[str, Any]:
        """Create an empty reflection for days with no interactions."""
        reflection = DailyReflection(
            id=str(uuid.uuid4()),
            user_id=user_id,
            reflection_date=now,
            total_interactions=0,
            positive_outcomes=[],
            negative_outcomes=[],
            patterns_detected=["No interactions today"],
            improvement_opportunities=[],
        )
        return reflection.to_dict()

    async def _get_personality_directness(self, user_id: str) -> int:
        """Get personality directness level for a user."""
        if self._personality is None:
            try:
                from src.companion.personality import PersonalityService

                self._personality = PersonalityService()
            except Exception:
                return 3  # Default to high directness

        try:
            profile = await self._personality.get_profile(user_id)
            return int(profile.directness)
        except Exception:
            return 3

    def _get_tone_description(self, directness: int) -> str:
        """Get tone description based on directness level."""
        descriptions = {
            1: "gentle and supportive while still taking full responsibility",
            2: "direct but caring, acknowledging the impact",
            3: "direct and candid, no softening",
        }
        return descriptions.get(directness, descriptions[3])

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks."""
        content = text.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line if it's a code block start
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last line if it's a code block end
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        return content
