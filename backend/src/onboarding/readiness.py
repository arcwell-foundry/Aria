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
            corporate_memory=float(scores_data.get("corporate_memory", 0.0)),
            digital_twin=float(scores_data.get("digital_twin", 0.0)),
            relationship_graph=float(scores_data.get("relationship_graph", 0.0)),
            integrations=float(scores_data.get("integrations", 0.0)),
            goal_clarity=float(scores_data.get("goal_clarity", 0.0)),
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

        # Calculate each domain from actual data
        corporate_memory = self._calculate_corporate_memory(user_id)
        digital_twin = self._calculate_digital_twin(user_id)
        relationship_graph = self._calculate_relationship_graph(user_id)
        integrations = self._calculate_integrations(user_id)
        goal_clarity = self._calculate_goal_clarity(user_id)

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
            corporate_memory * WEIGHTS["corporate_memory"]
            + digital_twin * WEIGHTS["digital_twin"]
            + relationship_graph * WEIGHTS["relationship_graph"]
            + integrations * WEIGHTS["integrations"]
            + goal_clarity * WEIGHTS["goal_clarity"]
        )
        return round(overall, 1)

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

    def _calculate_corporate_memory(self, _user_id: str) -> float:
        """Calculate corporate memory readiness from actual data.

        Counts facts, checks enrichment quality, competitor coverage.
        This is a placeholder implementation — full implementation would
        query Graphiti and company_documents.

        Args:
            _user_id: The user's ID.

        Returns:
            Corporate memory score (0-100).
        """
        # TODO: Implement full calculation based on:
        # - Number of corporate facts in Graphiti
        # - Enrichment quality score from company profile
        # - Number of competitors identified
        # - Document count and quality scores
        # For now, return a baseline score
        return 50.0

    def _calculate_digital_twin(self, _user_id: str) -> float:
        """Calculate digital twin readiness from actual data.

        Checks writing fingerprint confidence, communication patterns.
        This is a placeholder implementation — full implementation would
        query digital_twin table and email patterns.

        Args:
            _user_id: The user's ID.

        Returns:
            Digital twin score (0-100).
        """
        # TODO: Implement full calculation based on:
        # - Writing style fingerprint confidence
        # - Number of email samples analyzed
        # - Communication pattern coverage
        # - Relationship graph density for this user
        # For now, return a baseline score
        return 50.0

    def _calculate_relationship_graph(self, _user_id: str) -> float:
        """Calculate relationship graph readiness from actual data.

        Counts contacts, stakeholders, interaction depth.
        This is a placeholder implementation — full implementation would
        query contacts and stakeholder tables.

        Args:
            _user_id: The user's ID.

        Returns:
            Relationship graph score (0-100).
        """
        # TODO: Implement full calculation based on:
        # - Number of contacts in CRM
        # - Number of stakeholders mapped
        # - Interaction history depth
        # - Stakeholder coverage
        # For now, return a baseline score
        return 50.0

    def _calculate_integrations(self, _user_id: str) -> float:
        """Calculate integrations readiness from actual data.

        Counts connected tools, checks sync freshness.
        This is a placeholder implementation — full implementation would
        query user_integrations table.

        Args:
            _user_id: The user's ID.

        Returns:
            Integrations score (0-100).
        """
        # TODO: Implement full calculation based on:
        # - Number of connected integrations
        # - Sync freshness for each integration
        # - Data quality from syncs
        # For now, return a baseline score
        return 50.0

    def _calculate_goal_clarity(self, _user_id: str) -> float:
        """Calculate goal clarity readiness from actual data.

        Checks if goals exist, are decomposed, have agents assigned.
        This is a placeholder implementation — full implementation would
        query goals table.

        Args:
            _user_id: The user's ID.

        Returns:
            Goal clarity score (0-100).
        """
        # TODO: Implement full calculation based on:
        # - Number of active goals
        # - Goal decomposition quality
        # - Agent assignment completeness
        # For now, return a baseline score
        return 50.0
