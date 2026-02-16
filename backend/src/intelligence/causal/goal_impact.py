"""Goal Impact Mapper for ARIA Phase 7 Jarvis Intelligence (US-706).

This module maps implications/events to user goals, providing:
- Automatic goal-impact scoring and classification
- Multi-goal implication detection and prioritization
- De-prioritization of insights with no goal relevance
- Summary views showing net pressure on each goal

Key components:
- GoalImpactMapper: Main class for mapping insights to goals
- LLM-powered impact classification (accelerates, blocks, neutral, creates_opportunity)
"""

import json
import logging
import time
from typing import Any

from src.core.llm import LLMClient
from src.intelligence.causal.models import (
    GoalImpact,
    GoalImpactSummary,
    GoalWithInsights,
    ImpactType,
    Implication,
)

logger = logging.getLogger(__name__)

# De-prioritization factor for insights with no goal relevance
NO_GOAL_PRIORITY_MULTIPLIER = 0.3

# LLM prompt template for impact scoring
IMPACT_SCORING_PROMPT = """You are analyzing how an intelligence insight affects a business goal.

Insight: {implication_content}
Goal: {goal_title} - {goal_description}

Score the impact (0.0-1.0) and classify the relationship:
- accelerates: The insight helps achieve the goal faster
- blocks: The insight creates obstacles for the goal
- neutral: No significant positive or negative impact
- creates_opportunity: The insight reveals new possibilities

Return ONLY a valid JSON object with no other text:
{{"impact_score": 0.8, "impact_type": "accelerates", "explanation": "Brief explanation here"}}"""


class GoalImpactMapper:
    """Maps intelligence insights to user goals with impact classification.

    This class analyzes implications and maps them to the user's goals,
    providing scored and classified impact relationships. It also
    identifies multi-goal implications and de-prioritizes insights
    with no goal relevance.

    Attributes:
        NO_GOAL_PRIORITY_MULTIPLIER: Factor to reduce priority for no-goal insights (0.3)
    """

    def __init__(
        self,
        db_client: Any,
        llm_client: LLMClient,
    ) -> None:
        """Initialize the goal impact mapper.

        Args:
            db_client: Supabase client for goal and insight queries
            llm_client: LLM client for impact classification
        """
        self._db = db_client
        self._llm = llm_client

    async def map_impact(
        self,
        user_id: str,
        implications: list[Implication],
        include_draft_goals: bool = True,
    ) -> list[GoalImpact]:
        """Map implications to goals with impact scores and classifications.

        For each implication, identifies which goals it affects and how.
        Updates affected_goals field on implications and de-prioritizes
        those with no goal relevance.

        Args:
            user_id: User ID to fetch goals for
            implications: List of implications to map to goals
            include_draft_goals: Whether to include draft goals in analysis

        Returns:
            List of GoalImpact objects for all implication-goal pairs
        """
        start_time = time.monotonic()

        if not implications:
            return []

        # Fetch active goals (and optionally draft goals)
        goals = await self._get_goals(user_id, include_draft_goals)

        if not goals:
            logger.info("No goals found for user, skipping impact mapping")
            return []

        logger.info(
            "Mapping implications to goals",
            extra={
                "user_id": user_id,
                "implication_count": len(implications),
                "goal_count": len(goals),
            },
        )

        # Track all impacts
        all_impacts: list[GoalImpact] = []

        # Track which implications affect which goals
        implication_goal_map: dict[str, list[str]] = {}

        # Analyze each implication against each goal
        for implication in implications:
            impl_id = str(implication.id) if implication.id else implication.content[:50]
            implication_goal_map[impl_id] = []

            for goal in goals:
                goal_id = str(goal["id"])

                # Use LLM to score and classify impact
                impact = await self._analyze_impact(implication, goal)

                if impact and impact.impact_type != ImpactType.NEUTRAL:
                    all_impacts.append(impact)
                    implication_goal_map[impl_id].append(goal_id)

        # Identify multi-goal implications (affect 2+ goals)
        multi_goal_count = sum(
            1 for goals_affected in implication_goal_map.values() if len(goals_affected) >= 2
        )

        # De-prioritize implications with no goal impact
        for implication in implications:
            impl_id = str(implication.id) if implication.id else implication.content[:50]
            affected = implication_goal_map.get(impl_id, [])

            if not affected:
                # De-prioritize by reducing combined_score
                implication.combined_score *= NO_GOAL_PRIORITY_MULTIPLIER
                logger.debug(
                    "De-prioritized implication with no goal impact",
                    extra={"implication": impl_id, "new_score": implication.combined_score},
                )
            else:
                # Update affected_goals on the implication
                implication.affected_goals = affected

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "Impact mapping complete",
            extra={
                "user_id": user_id,
                "total_impacts": len(all_impacts),
                "multi_goal_implications": multi_goal_count,
                "elapsed_ms": elapsed_ms,
            },
        )

        return all_impacts

    async def get_goal_impact_summary(
        self,
        user_id: str,
        include_draft_goals: bool = True,
        days_back: int = 30,
    ) -> GoalImpactSummary:
        """Get summary of goal impacts across all active goals.

        Aggregates insights by goal and calculates net pressure
        (opportunities vs threats) for each goal.

        Args:
            user_id: User ID to fetch goals and insights for
            include_draft_goals: Whether to include draft goals
            days_back: Number of days to look back for insights

        Returns:
            GoalImpactSummary with all goals and their insights
        """
        start_time = time.monotonic()

        # Fetch goals
        goals = await self._get_goals(user_id, include_draft_goals)

        # Fetch recent insights from jarvis_insights
        insights = await self._get_recent_insights(user_id, days_back)

        # Group insights by goal
        goals_with_insights: list[GoalWithInsights] = []
        total_insights = 0
        multi_goal_count = 0

        for goal in goals:
            goal_id = str(goal["id"])
            goal_insights: list[dict[str, Any]] = []
            opportunity_count = 0
            threat_count = 0

            for insight in insights:
                affected_goals = insight.get("affected_goals") or []
                if goal_id in affected_goals:
                    insight_ref = {
                        "id": str(insight.get("id")),
                        "content": insight.get("content", "")[:200],
                        "classification": insight.get("classification"),
                        "combined_score": insight.get("combined_score", 0),
                        "impact_type": self._classify_impact_type(insight),
                        "created_at": insight.get("created_at"),
                    }
                    goal_insights.append(insight_ref)
                    total_insights += 1

                    # Track if this insight affects multiple goals
                    if len(affected_goals) >= 2:
                        multi_goal_count += 1

                    # Count opportunities vs threats
                    if insight.get("classification") == "opportunity":
                        opportunity_count += 1
                    elif insight.get("classification") == "threat":
                        threat_count += 1

            # Calculate net pressure (opportunities help, threats hinder)
            net_pressure = (opportunity_count * 0.5) - (threat_count * 0.5)

            goals_with_insights.append(
                GoalWithInsights(
                    goal_id=goal_id,
                    goal_title=goal.get("title", "Unknown Goal"),
                    goal_status=goal.get("status", "unknown"),
                    insights=goal_insights,
                    net_pressure=net_pressure,
                    opportunity_count=opportunity_count,
                    threat_count=threat_count,
                )
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return GoalImpactSummary(
            goals=goals_with_insights,
            total_insights_analyzed=total_insights,
            multi_goal_implications=multi_goal_count,
            processing_time_ms=elapsed_ms,
        )

    async def get_goal_insights(
        self,
        user_id: str,
        goal_id: str,
        limit: int = 20,
    ) -> GoalWithInsights:
        """Get insights affecting a specific goal.

        Args:
            user_id: User ID for authentication
            goal_id: Goal ID to get insights for
            limit: Maximum number of insights to return

        Returns:
            GoalWithInsights for the specified goal
        """
        # Fetch goal details
        goal = await self._get_goal_by_id(user_id, goal_id)

        if not goal:
            raise ValueError(f"Goal {goal_id} not found for user {user_id}")

        # Fetch insights affecting this goal
        insights = await self._get_insights_for_goal(user_id, goal_id, limit)

        # Classify and count
        goal_insights: list[dict[str, Any]] = []
        opportunity_count = 0
        threat_count = 0

        for insight in insights:
            insight_ref = {
                "id": str(insight.get("id")),
                "content": insight.get("content", "")[:200],
                "classification": insight.get("classification"),
                "combined_score": insight.get("combined_score", 0),
                "impact_type": self._classify_impact_type(insight),
                "created_at": insight.get("created_at"),
            }
            goal_insights.append(insight_ref)

            if insight.get("classification") == "opportunity":
                opportunity_count += 1
            elif insight.get("classification") == "threat":
                threat_count += 1

        net_pressure = (opportunity_count * 0.5) - (threat_count * 0.5)

        return GoalWithInsights(
            goal_id=goal_id,
            goal_title=goal.get("title", "Unknown Goal"),
            goal_status=goal.get("status", "unknown"),
            insights=goal_insights,
            net_pressure=net_pressure,
            opportunity_count=opportunity_count,
            threat_count=threat_count,
        )

    async def _get_goals(
        self,
        user_id: str,
        include_draft: bool,
    ) -> list[dict[str, Any]]:
        """Fetch user's goals from database.

        Args:
            user_id: User ID
            include_draft: Whether to include draft goals

        Returns:
            List of goal dictionaries
        """
        try:
            query = (
                self._db.table("goals")
                .select("id, title, description, status, priority, category")
                .eq("user_id", user_id)
            )

            if include_draft:
                # Use .in_() for multiple statuses
                query = query.in_("status", ["active", "draft"])
            else:
                query = query.eq("status", "active")

            result = query.order("priority", desc=True).limit(50).execute()

            return result.data or []

        except Exception as e:
            logger.warning(f"Failed to fetch goals: {e}")
            return []

    async def _get_goal_by_id(
        self,
        user_id: str,
        goal_id: str,
    ) -> dict[str, Any] | None:
        """Fetch a single goal by ID.

        Args:
            user_id: User ID for ownership check
            goal_id: Goal ID to fetch

        Returns:
            Goal dictionary or None if not found
        """
        try:
            result = (
                self._db.table("goals")
                .select("id, title, description, status, priority, category")
                .eq("id", goal_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            # Explicit cast for mypy strict - result.data is Any from Supabase
            data: dict[str, Any] | None = result.data
            return data

        except Exception as e:
            logger.warning(f"Failed to fetch goal {goal_id}: {e}")
            return None

    async def _get_recent_insights(
        self,
        user_id: str,
        days_back: int,
    ) -> list[dict[str, Any]]:
        """Fetch recent insights from jarvis_insights.

        Args:
            user_id: User ID
            days_back: Number of days to look back

        Returns:
            List of insight dictionaries
        """
        try:
            # Calculate date threshold
            from datetime import UTC, datetime, timedelta

            threshold = (datetime.now(UTC) - timedelta(days=days_back)).isoformat()

            result = (
                self._db.table("jarvis_insights")
                .select("id, content, classification, combined_score, affected_goals, created_at")
                .eq("user_id", user_id)
                .gte("created_at", threshold)
                .order("combined_score", desc=True)
                .limit(100)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.warning(f"Failed to fetch recent insights: {e}")
            return []

    async def _get_insights_for_goal(
        self,
        user_id: str,
        goal_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch insights that affect a specific goal.

        Args:
            user_id: User ID
            goal_id: Goal ID to filter by
            limit: Maximum insights to return

        Returns:
            List of insight dictionaries
        """
        try:
            # Query insights where goal_id is in affected_goals array
            result = (
                self._db.table("jarvis_insights")
                .select("id, content, classification, combined_score, affected_goals, created_at")
                .eq("user_id", user_id)
                .contains("affected_goals", [goal_id])
                .order("combined_score", desc=True)
                .limit(limit)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.warning(f"Failed to fetch insights for goal {goal_id}: {e}")
            return []

    async def _analyze_impact(
        self,
        implication: Implication,
        goal: dict[str, Any],
    ) -> GoalImpact | None:
        """Analyze the impact of an implication on a goal using LLM.

        Args:
            implication: Implication to analyze
            goal: Goal to check impact against

        Returns:
            GoalImpact object or None if analysis fails
        """
        try:
            prompt = IMPACT_SCORING_PROMPT.format(
                implication_content=implication.content,
                goal_title=goal.get("title", ""),
                goal_description=goal.get("description", ""),
            )

            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200,
            )

            # Parse JSON response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            data = json.loads(response)

            # Validate and map impact type
            impact_type_str = data.get("impact_type", "neutral").lower()
            try:
                impact_type = ImpactType(impact_type_str)
            except ValueError:
                impact_type = ImpactType.NEUTRAL

            return GoalImpact(
                goal_id=str(goal["id"]),
                goal_title=goal.get("title", "Unknown Goal"),
                impact_score=min(1.0, max(0.0, float(data.get("impact_score", 0.5)))),
                impact_type=impact_type,
                explanation=data.get("explanation", "Impact analysis not available"),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse impact response: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to analyze impact: {e}")
            return None

    def _classify_impact_type(self, insight: dict[str, Any]) -> str:
        """Classify the impact type of an insight based on its properties.

        Args:
            insight: Insight dictionary

        Returns:
            Impact type string
        """
        classification = insight.get("classification", "neutral")

        # Map classification to impact type
        if classification == "opportunity":
            return "accelerates"
        elif classification == "threat":
            return "blocks"
        else:
            return "neutral"
