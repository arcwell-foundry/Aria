"""Onboarding readiness score service (US-913).

Calculates and manages readiness scores across five memory domains:
- Corporate Memory (25%): Company profile completeness, document coverage, competitive intel depth
- Digital Twin (25%): Writing style confidence, communication pattern coverage, relationship graph density
- Relationship Graph (20%): Number of contacts mapped, interaction history depth, stakeholder coverage
- Integrations (15%): Connected tools count, data freshness, sync status
- Goal Clarity (15%): Goal specificity, decomposition quality, agent assignment completeness

The overall readiness score is a weighted average (0-100) that informs
confidence levels across all ARIA features.
"""

import asyncio
import logging

from pydantic import BaseModel

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


# Readiness weights must sum to 1.0
WEIGHTS: dict[str, float] = {
    "corporate_memory": 0.25,
    "digital_twin": 0.25,
    "relationship_graph": 0.20,
    "integrations": 0.15,
    "goal_clarity": 0.15,
}


class ReadinessBreakdown(BaseModel):
    """Readiness scores across all domains with overall calculation."""

    corporate_memory: float = 0.0
    digital_twin: float = 0.0
    relationship_graph: float = 0.0
    integrations: float = 0.0
    goal_clarity: float = 0.0
    overall: float = 0.0
    confidence_modifier: str = "low"  # low, moderate, high, very_high


class OnboardingReadinessService:
    """Calculates and manages readiness scores for onboarding.

    The readiness score indicates how well-initialized ARIA is for a given user.
    It feeds into confidence disclaimers across features — low readiness in a domain
    results in "based on limited data" caveats for features depending on that domain.
    """

    def __init__(self) -> None:
        """Initialize readiness service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_readiness(self, user_id: str) -> ReadinessBreakdown:
        """Get current readiness scores with overall calculation.

        Reads stored scores from onboarding_state and calculates overall
        readiness as a weighted average. Determines confidence modifier
        based on overall score.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            ReadinessBreakdown with all sub-scores, overall, and confidence modifier.
        """
        # Get current onboarding state
        response = (
            self._db.table("onboarding_state")
            .select("readiness_scores")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not response or not response.data:
            # No state yet — return all zeros
            return ReadinessBreakdown()

        # Type narrowing for JSON data
        data_dict = response.data if isinstance(response.data, dict) else {}
        scores_data = data_dict.get("readiness_scores", {})
        if not isinstance(scores_data, dict):
            scores_data = {}

        scores = ReadinessBreakdown(
            corporate_memory=min(100.0, max(0.0, float(scores_data.get("corporate_memory", 0.0)))),
            digital_twin=min(100.0, max(0.0, float(scores_data.get("digital_twin", 0.0)))),
            relationship_graph=min(100.0, max(0.0, float(scores_data.get("relationship_graph", 0.0)))),
            integrations=min(100.0, max(0.0, float(scores_data.get("integrations", 0.0)))),
            goal_clarity=min(100.0, max(0.0, float(scores_data.get("goal_clarity", 0.0)))),
        )

        # Calculate weighted overall
        scores.overall = self._calculate_overall(
            scores.corporate_memory,
            scores.digital_twin,
            scores.relationship_graph,
            scores.integrations,
            scores.goal_clarity,
        )

        # Determine confidence modifier
        scores.confidence_modifier = self._get_confidence_modifier(scores.overall)

        return scores

    async def recalculate(self, user_id: str) -> ReadinessBreakdown:
        """Full recalculation from source data.

        Queries actual data state rather than relying on incremental updates:
        - corporate_memory: count facts, check enrichment quality, competitor coverage
        - digital_twin: check writing fingerprint confidence, communication patterns
        - relationship_graph: count contacts, stakeholders, interaction depth
        - integrations: count connected tools, check sync freshness
        - goal_clarity: check if goal exists, is decomposed, has agents assigned

        Args:
            user_id: The authenticated user's ID.

        Returns:
            ReadinessBreakdown with recalculated scores.
        """
        # Get current state
        state_response = (
            self._db.table("onboarding_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not state_response or not state_response.data:
            # No state — return zeros
            return ReadinessBreakdown()

        # Calculate each domain from actual data (independent queries, run concurrently)
        (
            corporate_memory,
            digital_twin,
            relationship_graph,
            integrations,
            goal_clarity,
        ) = await asyncio.gather(
            self._calculate_corporate_memory(user_id),
            self._calculate_digital_twin(user_id),
            self._calculate_relationship_graph(user_id),
            self._calculate_integrations(user_id),
            self._calculate_goal_clarity(user_id),
        )

        # Clamp to 0-100
        corporate_memory = max(0.0, min(100.0, corporate_memory))
        digital_twin = max(0.0, min(100.0, digital_twin))
        relationship_graph = max(0.0, min(100.0, relationship_graph))
        integrations = max(0.0, min(100.0, integrations))
        goal_clarity = max(0.0, min(100.0, goal_clarity))

        # Update database
        new_scores = {
            "corporate_memory": corporate_memory,
            "digital_twin": digital_twin,
            "relationship_graph": relationship_graph,
            "integrations": integrations,
            "goal_clarity": goal_clarity,
        }

        (
            self._db.table("onboarding_state")
            .update({"readiness_scores": new_scores})
            .eq("user_id", user_id)
            .execute()
        )

        # Build response
        overall = self._calculate_overall(
            corporate_memory, digital_twin, relationship_graph, integrations, goal_clarity
        )
        confidence = self._get_confidence_modifier(overall)

        return ReadinessBreakdown(
            corporate_memory=corporate_memory,
            digital_twin=digital_twin,
            relationship_graph=relationship_graph,
            integrations=integrations,
            goal_clarity=goal_clarity,
            overall=overall,
            confidence_modifier=confidence,
        )

    def _calculate_overall(
        self,
        corporate_memory: float,
        digital_twin: float,
        relationship_graph: float,
        integrations: float,
        goal_clarity: float,
    ) -> float:
        """Calculate weighted overall readiness score.

        Args:
            corporate_memory: Corporate memory sub-score (0-100).
            digital_twin: Digital twin sub-score (0-100).
            relationship_graph: Relationship graph sub-score (0-100).
            integrations: Integrations sub-score (0-100).
            goal_clarity: Goal clarity sub-score (0-100).

        Returns:
            Weighted overall score (0-100).
        """
        overall = (
            min(100.0, corporate_memory) * WEIGHTS["corporate_memory"]
            + min(100.0, digital_twin) * WEIGHTS["digital_twin"]
            + min(100.0, relationship_graph) * WEIGHTS["relationship_graph"]
            + min(100.0, integrations) * WEIGHTS["integrations"]
            + min(100.0, goal_clarity) * WEIGHTS["goal_clarity"]
        )
        return min(100.0, round(overall, 1))

    def _get_confidence_modifier(self, overall: float) -> str:
        """Map overall score to confidence modifier string.

        Args:
            overall: Overall readiness score (0-100).

        Returns:
            One of: 'low', 'moderate', 'high', 'very_high'.
        """
        if overall < 30:
            return "low"
        if overall < 60:
            return "moderate"
        if overall < 80:
            return "high"
        return "very_high"

    async def _calculate_corporate_memory(self, user_id: str) -> float:
        """Calculate corporate memory readiness from actual data.

        Score: facts (1pt each, cap 60) + documents (8pt each, cap 40).

        Args:
            user_id: The user's ID.

        Returns:
            Corporate memory score (0-100).
        """
        try:
            profile = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if not profile.data or not profile.data.get("company_id"):
                return 0.0

            company_id = profile.data["company_id"]

            facts_result = (
                self._db.table("corporate_facts")
                .select("id")
                .eq("company_id", company_id)
                .eq("is_active", True)
                .execute()
            )
            fact_score = min(len(facts_result.data or []), 60)

            docs_result = (
                self._db.table("company_documents")
                .select("id")
                .eq("company_id", company_id)
                .execute()
            )
            doc_score = min(len(docs_result.data or []) * 8, 40)

            return min(float(fact_score + doc_score), 100.0)
        except Exception as e:
            logger.warning("Corporate memory calculation failed: %s", e)
            return 0.0

    async def _calculate_digital_twin(self, user_id: str) -> float:
        """Calculate digital twin readiness from actual data.

        Score: writing style (50pt) + personality calibration (50pt).

        Args:
            user_id: The user's ID.

        Returns:
            Digital twin score (0-100).
        """
        try:
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if not result.data:
                return 0.0

            prefs = result.data.get("preferences") or {}
            dt = prefs.get("digital_twin") or {}

            score = 0.0
            if dt.get("writing_style"):
                score += 50.0
            if dt.get("personality_calibration"):
                score += 50.0

            return min(score, 100.0)
        except Exception as e:
            logger.warning("Digital twin calculation failed: %s", e)
            return 0.0

    async def _calculate_relationship_graph(self, user_id: str) -> float:
        """Calculate relationship graph readiness from actual data.

        Score: leads (10pt each, cap 50) + stakeholders (5pt each, cap 50).

        Args:
            user_id: The user's ID.

        Returns:
            Relationship graph score (0-100).
        """
        try:
            leads_result = (
                self._db.table("lead_memories")
                .select("id")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            lead_count = len(leads_result.data or [])
            lead_score = min(lead_count * 10, 50)

            stakeholder_score = 0
            if lead_count > 0:
                lead_ids = [lead["id"] for lead in leads_result.data]
                stakeholders_result = (
                    self._db.table("lead_memory_stakeholders")
                    .select("id")
                    .in_("lead_memory_id", lead_ids)
                    .execute()
                )
                stakeholder_count = len(stakeholders_result.data or [])
                stakeholder_score = min(stakeholder_count * 5, 50)

            return min(float(lead_score + stakeholder_score), 100.0)
        except Exception as e:
            logger.warning("Relationship graph calculation failed: %s", e)
            return 0.0

    async def _calculate_integrations(self, user_id: str) -> float:
        """Calculate integrations readiness from actual data.

        Score: 25 points per active integration, capped at 100.

        Args:
            user_id: The user's ID.

        Returns:
            Integrations score (0-100).
        """
        try:
            result = (
                self._db.table("user_integrations")
                .select("id")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            active_count = len(result.data or [])
            return min(active_count * 25.0, 100.0)
        except Exception as e:
            logger.warning("Integrations calculation failed: %s", e)
            return 0.0

    async def _calculate_goal_clarity(self, user_id: str) -> float:
        """Calculate goal clarity readiness from actual data.

        Score: goals (30pt each, cap 60) + agent assignments (10pt each, cap 40).

        Args:
            user_id: The user's ID.

        Returns:
            Goal clarity score (0-100).
        """
        try:
            goals_result = (
                self._db.table("goals")
                .select("id")
                .eq("user_id", user_id)
                .in_("status", ["active", "draft"])
                .execute()
            )
            goal_count = len(goals_result.data or [])
            goal_score = min(goal_count * 30, 60)

            agent_score = 0
            if goal_count > 0:
                goal_ids = [g["id"] for g in goals_result.data]
                agents_result = (
                    self._db.table("goal_agents").select("id").in_("goal_id", goal_ids).execute()
                )
                agent_count = len(agents_result.data or [])
                agent_score = min(agent_count * 10, 40)

            return min(float(goal_score + agent_score), 100.0)
        except Exception as e:
            logger.warning("Goal clarity calculation failed: %s", e)
            return 0.0
