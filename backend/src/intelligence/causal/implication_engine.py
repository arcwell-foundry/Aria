"""Implication Reasoning Engine for ARIA Phase 7 Jarvis Intelligence.

This engine transforms raw causal chains into actionable insights by connecting
causal chain endpoints to the user's active goals and deals.

Key features:
- Analyze events through causal chain traversal
- Match chain endpoints against user's active goals
- Classify implications as opportunities, threats, or neutral
- Score via multi-factor algorithm (impact, confidence, urgency)
- Generate natural language explanations and recommendations via LLM
- Categorize by time horizon for prioritized action planning
- Persist top insights to jarvis_insights table for UI consumption
"""

import json
import logging
import re
import time
from typing import Any
from uuid import UUID

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.causal.models import (
    CausalChain,
    Implication,
    ImplicationRequest,
    ImplicationResponse,
    ImplicationType,
)
from src.intelligence.temporal import TimeHorizonAnalyzer

logger = logging.getLogger(__name__)

# Scoring weights for combined score calculation
IMPACT_WEIGHT = 0.40
CONFIDENCE_WEIGHT = 0.35
URGENCY_WEIGHT = 0.25


class ImplicationEngine:
    """Engine for deriving actionable implications from causal chain analysis.

    Connects causal chain endpoints to user goals to surface proactive
    intelligence as opportunities or threats.

    Attributes:
        DEFAULT_MAX_HOPS: Default maximum causal hops to traverse (4)
        DEFAULT_MIN_SCORE: Minimum combined score threshold (0.3)
    """

    DEFAULT_MAX_HOPS: int = 4
    DEFAULT_MIN_SCORE: float = 0.3

    def __init__(
        self,
        causal_engine: CausalChainEngine,
        db_client: Any,
        llm_client: LLMClient,
        time_horizon_analyzer: TimeHorizonAnalyzer | None = None,
    ) -> None:
        """Initialize the implication engine.

        Args:
            causal_engine: Causal chain traversal engine
            db_client: Supabase client for goal queries and insight persistence
            llm_client: LLM client for explanation and recommendation generation
            time_horizon_analyzer: Optional time horizon analyzer for temporal categorization
        """
        self._causal_engine = causal_engine
        self._db = db_client
        self._llm = llm_client
        self._time_horizon_analyzer = time_horizon_analyzer or TimeHorizonAnalyzer(llm_client)

    async def analyze_event(
        self,
        user_id: str,
        event: str,
        max_hops: int = DEFAULT_MAX_HOPS,
        include_neutral: bool = False,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> list[Implication]:
        """Analyze an event for implications affecting user's goals.

        Main entry point for implication analysis. Traverses causal chains
        from the event, matches endpoints to goals, and generates insights.

        Args:
            user_id: User ID for goal context
            event: Description of the event to analyze
            max_hops: Maximum causal hops to traverse (1-6)
            include_neutral: Include neutral implications (default False)
            min_score: Minimum combined score threshold (0-1)

        Returns:
            List of implications sorted by combined_score descending
        """
        start_time = time.monotonic()

        logger.info(
            "Starting implication analysis",
            extra={
                "user_id": user_id,
                "event_length": len(event),
                "max_hops": max_hops,
                "include_neutral": include_neutral,
            },
        )

        # Step 1: Traverse causal chains from the event
        chains = await self._causal_engine.traverse(
            user_id=user_id,
            trigger_event=event,
            max_hops=max_hops,
            min_confidence=0.2,  # Lower threshold to get more chains for analysis
        )

        if not chains:
            logger.info("No causal chains found for event")
            return []

        logger.info(f"Found {len(chains)} causal chains to analyze")

        # Step 2: Get user's active goals
        goals = await self._get_active_goals(user_id)

        if not goals:
            logger.info("No active goals found for user")
            return []

        logger.info(f"Found {len(goals)} active goals")

        # Step 3: Analyze each chain for implications
        implications: list[Implication] = []

        for chain in chains:
            chain_implications = await self._analyze_chain(
                chain=chain,
                goals=goals,
                include_neutral=include_neutral,
            )
            implications.extend(chain_implications)

        # Step 4: Filter by minimum score and sort
        filtered_implications = [impl for impl in implications if impl.combined_score >= min_score]

        # Sort by combined score descending
        sorted_implications = sorted(
            filtered_implications,
            key=lambda i: -i.combined_score,
        )

        # Step 5: Enrich with time horizon categorization
        if sorted_implications and self._time_horizon_analyzer:
            sorted_implications = await self._enrich_with_time_horizons(sorted_implications)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "Implication analysis complete",
            extra={
                "user_id": user_id,
                "total_implications": len(implications),
                "filtered_implications": len(sorted_implications),
                "elapsed_ms": elapsed_ms,
            },
        )

        return sorted_implications

    async def analyze_with_metadata(
        self,
        user_id: str,
        request: ImplicationRequest,
    ) -> ImplicationResponse:
        """Analyze an event and return full response with metadata.

        Args:
            user_id: User ID for context
            request: Implication request with parameters

        Returns:
            Full response with implications and processing metadata
        """
        start_time = time.monotonic()

        implications = await self.analyze_event(
            user_id=user_id,
            event=request.event,
            max_hops=request.max_hops,
            include_neutral=request.include_neutral,
            min_score=request.min_score,
        )

        # Count chains and goals for metadata
        chains = await self._causal_engine.traverse(
            user_id=user_id,
            trigger_event=request.event,
            max_hops=request.max_hops,
        )
        goals = await self._get_active_goals(user_id)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return ImplicationResponse(
            implications=implications,
            processing_time_ms=elapsed_ms,
            chains_analyzed=len(chains),
            goals_considered=len(goals),
        )

    async def save_insight(
        self,
        user_id: str,
        implication: Implication,
    ) -> UUID | None:
        """Persist an implication to the jarvis_insights table.

        Args:
            user_id: User ID
            implication: Implication to save

        Returns:
            UUID of saved insight, or None if save failed
        """
        try:
            data = {
                "user_id": user_id,
                "insight_type": "implication",
                "trigger_event": implication.trigger_event,
                "content": implication.content,
                "classification": implication.type.value,
                "impact_score": implication.impact_score,
                "confidence": implication.confidence,
                "urgency": implication.urgency,
                "combined_score": implication.combined_score,
                "causal_chain": implication.causal_chain,
                "affected_goals": implication.affected_goals,
                "recommended_actions": implication.recommended_actions,
                "time_horizon": implication.time_horizon,
                "time_to_impact": implication.time_to_impact,
                "status": "new",
            }

            result = self._db.table("jarvis_insights").insert(data).execute()

            if result.data and len(result.data) > 0:
                insight_id = UUID(result.data[0]["id"])
                logger.info(
                    "Saved insight to database",
                    extra={
                        "insight_id": str(insight_id),
                        "user_id": user_id,
                        "classification": implication.type.value,
                    },
                )
                return insight_id

            return None

        except Exception:
            logger.exception(
                "Failed to save insight",
                extra={"user_id": user_id},
            )
            return None

    async def _get_active_goals(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch user's active goals from database.

        Args:
            user_id: User ID

        Returns:
            List of active goal dictionaries
        """
        try:
            result = (
                self._db.table("goals")
                .select("id, title, description, priority, status, category")
                .eq("user_id", user_id)
                .eq("status", "active")
                .order("priority", desc=True)
                .limit(20)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.warning(f"Failed to fetch goals: {e}")
            return []

    async def _analyze_chain(
        self,
        chain: CausalChain,
        goals: list[dict[str, Any]],
        include_neutral: bool,
    ) -> list[Implication]:
        """Analyze a single causal chain for goal implications.

        Args:
            chain: Causal chain to analyze
            goals: List of user's active goals
            include_neutral: Whether to include neutral implications

        Returns:
            List of implications derived from this chain
        """
        if not chain.hops:
            return []

        # Get the final target of the chain
        final_target = chain.hops[-1].target_entity

        # Find affected goals
        affected_goals = await self._find_affected_goals(final_target, goals)

        if not affected_goals and not include_neutral:
            return []

        # Classify the implication
        impl_type = await self._classify_implication(chain, affected_goals)

        # Skip neutral if not included
        if impl_type == ImplicationType.NEUTRAL and not include_neutral:
            return []

        # Calculate scores
        impact_score = self._calculate_impact(chain, affected_goals)
        urgency = self._calculate_urgency(chain)
        confidence = chain.final_confidence
        combined_score = (
            impact_score * IMPACT_WEIGHT + confidence * CONFIDENCE_WEIGHT + urgency * URGENCY_WEIGHT
        )

        # Generate explanation
        explanation = await self._generate_explanation(
            event=chain.trigger_event,
            chain=chain,
            affected_goals=affected_goals,
            impl_type=impl_type,
        )

        # Generate recommendations
        recommendations = await self._generate_recommendations(
            chain=chain,
            impl_type=impl_type,
        )

        # Serialize causal chain
        causal_chain_data = [
            {
                "source_entity": hop.source_entity,
                "target_entity": hop.target_entity,
                "relationship": hop.relationship,
                "confidence": hop.confidence,
                "explanation": hop.explanation,
            }
            for hop in chain.hops
        ]

        implication = Implication(
            id=None,
            trigger_event=chain.trigger_event,
            content=explanation,
            type=impl_type,
            impact_score=impact_score,
            confidence=confidence,
            urgency=urgency,
            combined_score=combined_score,
            causal_chain=causal_chain_data,
            affected_goals=[str(g["id"]) for g in affected_goals],
            recommended_actions=recommendations,
            time_horizon=None,
            time_to_impact=chain.time_to_impact,
            created_at=None,
        )

        return [implication]

    async def _find_affected_goals(
        self,
        chain_endpoint: str,
        goals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Find goals affected by a causal chain endpoint.

        Uses keyword matching and semantic similarity to identify
        which goals are relevant to the chain's final impact.

        Args:
            chain_endpoint: Final target entity of the causal chain
            goals: List of user's active goals

        Returns:
            List of goals affected by this chain endpoint
        """
        affected: list[dict[str, Any]] = []

        # Keywords that indicate relevance
        endpoint_lower = chain_endpoint.lower()
        endpoint_keywords = set(re.findall(r"\b\w{3,}\b", endpoint_lower))

        for goal in goals:
            # Combine goal fields for matching
            goal_text = f"{goal.get('title', '')} {goal.get('description', '')}".lower()
            goal_keywords = set(re.findall(r"\b\w{3,}\b", goal_text))

            # Calculate keyword overlap
            overlap = endpoint_keywords & goal_keywords

            # Check for direct substring match
            if any(kw in goal_text for kw in endpoint_keywords if len(kw) > 4):
                affected.append(goal)
                continue

            # Check for significant keyword overlap
            if len(overlap) >= 2:
                affected.append(goal)
                continue

            # Check for related concepts using LLM if no keyword match
            # This is more expensive, so only do it for high-priority goals
            if goal.get("priority", 0) >= 3:
                is_relevant = await self._check_goal_relevance_llm(chain_endpoint, goal)
                if is_relevant:
                    affected.append(goal)

        return affected

    async def _check_goal_relevance_llm(
        self,
        chain_endpoint: str,
        goal: dict[str, Any],
    ) -> bool:
        """Use LLM to check if a goal is relevant to a chain endpoint.

        Args:
            chain_endpoint: Final target of causal chain
            goal: Goal to check for relevance

        Returns:
            True if goal is relevant to the endpoint
        """
        try:
            system_prompt = """You are analyzing whether a business goal is affected by an event.
Respond with only "yes" or "no" - no other text.

Consider the goal relevant if:
- The event directly impacts the goal's target company, market, or outcome
- The event creates an opportunity or risk for achieving the goal
- There's a logical connection between the event and the goal's domain"""

            response = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"""Goal: {goal.get("title", "")} - {goal.get("description", "")}

Event impact: {chain_endpoint}

Is this goal affected by or relevant to this event impact?""",
                    }
                ],
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=10,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="implication_engine",
            )

            return "yes" in response.lower()

        except Exception as e:
            logger.warning(f"LLM relevance check failed: {e}")
            return False

    async def _classify_implication(
        self,
        chain: CausalChain,
        affected_goals: list[dict[str, Any]],
    ) -> ImplicationType:
        """Classify an implication as opportunity, threat, or neutral.

        Uses the relationship types in the causal chain and LLM analysis
        to determine whether the implication helps or hinders goals.

        Args:
            chain: Causal chain to classify
            affected_goals: Goals affected by this chain

        Returns:
            ImplicationType classification
        """
        if not affected_goals:
            return ImplicationType.NEUTRAL

        # Check relationship types in the chain
        threat_keywords = {"threatens", "risks", "hinders", "blocks", "delays"}
        opportunity_keywords = {"enables", "accelerates", "supports", "improves"}

        for hop in chain.hops:
            rel_lower = hop.relationship.lower()
            if any(kw in rel_lower for kw in threat_keywords):
                return ImplicationType.THREAT
            if any(kw in rel_lower for kw in opportunity_keywords):
                return ImplicationType.OPPORTUNITY

        # Use LLM for nuanced classification
        try:
            system_prompt = """Classify the business impact of an event on a user's goals.
Respond with only one word: "opportunity", "threat", or "neutral" - no other text.

Opportunity: The event helps achieve the goals
Threat: The event hinders or risks the goals
Neutral: No clear positive or negative impact"""

            goal_summaries = [f"- {g.get('title', 'Unknown goal')}" for g in affected_goals[:3]]

            chain_summary = " → ".join(
                f"{h.source_entity} [{h.relationship}] {h.target_entity}" for h in chain.hops
            )

            response = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"""User's goals:
{chr(10).join(goal_summaries)}

Causal chain:
{chain_summary}

How does this chain affect the user's goals?""",
                    }
                ],
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=20,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="implication_engine",
            )

            response_lower = response.lower().strip()

            if "opportunity" in response_lower:
                return ImplicationType.OPPORTUNITY
            elif "threat" in response_lower:
                return ImplicationType.THREAT
            else:
                return ImplicationType.NEUTRAL

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
            return ImplicationType.NEUTRAL

    def _calculate_impact(
        self,
        chain: CausalChain,
        affected_goals: list[dict[str, Any]],
    ) -> float:
        """Calculate impact score based on goal importance and count.

        Higher impact = more goals affected + higher priority goals.

        Args:
            chain: Causal chain
            affected_goals: Goals affected by this chain

        Returns:
            Impact score (0-1)
        """
        if not affected_goals:
            return 0.0

        # Base impact from number of goals affected
        count_factor = min(len(affected_goals) / 3.0, 1.0)  # Cap at 3 goals

        # Priority factor (average of goal priorities, normalized)
        priorities = [g.get("priority", 1) for g in affected_goals]
        avg_priority = sum(priorities) / len(priorities) if priorities else 1
        priority_factor = min(avg_priority / 5.0, 1.0)  # Assume max priority is 5

        # Confidence factor from chain
        confidence_factor = chain.final_confidence

        # Combined impact score
        impact = (count_factor * 0.4) + (priority_factor * 0.4) + (confidence_factor * 0.2)

        return min(impact, 1.0)

    def _calculate_urgency(self, chain: CausalChain) -> float:
        """Calculate urgency score based on time-to-impact.

        Parses time_to_impact string and converts to urgency score.

        Args:
            chain: Causal chain with optional time_to_impact

        Returns:
            Urgency score (0-1)
        """
        time_to_impact = chain.time_to_impact

        if not time_to_impact:
            # Default to medium urgency if no time specified
            return 0.5

        time_lower = time_to_impact.lower()

        # Immediate/urgent keywords
        if any(kw in time_lower for kw in ["immediate", "urgent", "now", "critical"]):
            return 0.9

        # Parse time expressions
        # Days
        days_match = re.search(r"(\d+)\s*day", time_lower)
        if days_match:
            days = int(days_match.group(1))
            if days <= 3:
                return 0.8
            elif days <= 7:
                return 0.6
            elif days <= 14:
                return 0.4
            else:
                return 0.3

        # Weeks
        weeks_match = re.search(r"(\d+)\s*week", time_lower)
        if weeks_match:
            weeks = int(weeks_match.group(1))
            if weeks <= 1:
                return 0.7
            elif weeks <= 2:
                return 0.5
            elif weeks <= 4:
                return 0.3
            else:
                return 0.2

        # Months
        months_match = re.search(r"(\d+)\s*month", time_lower)
        if months_match:
            months = int(months_match.group(1))
            if months <= 1:
                return 0.4
            elif months <= 3:
                return 0.3
            else:
                return 0.2

        # Default based on common phrases
        if any(kw in time_lower for kw in ["soon", "near", "short"]):
            return 0.7
        if any(kw in time_lower for kw in ["long", "future", "eventual"]):
            return 0.2

        return 0.5

    async def _generate_explanation(
        self,
        event: str,
        chain: CausalChain,
        affected_goals: list[dict[str, Any]],
        impl_type: ImplicationType,
    ) -> str:
        """Generate natural language explanation of the implication.

        Uses LLM to create a clear, actionable explanation.

        Args:
            event: Original trigger event
            chain: Causal chain leading to implication
            affected_goals: Goals affected
            impl_type: Classification type

        Returns:
            Natural language explanation
        """
        try:
            type_desc = {
                ImplicationType.OPPORTUNITY: "an opportunity",
                ImplicationType.THREAT: "a potential threat",
                ImplicationType.NEUTRAL: "a development",
            }

            system_prompt = """You are a business analyst explaining market implications.
Write a clear, concise explanation (2-3 sentences) of why an event matters.
Focus on actionable insights, not generic observations.
Be specific about the causal connection."""

            chain_summary = " → ".join(
                f"{h.source_entity} {h.relationship} {h.target_entity}" for h in chain.hops
            )

            goal_titles = [g.get("title", "goal") for g in affected_goals[:2]]

            response = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"""Event: {event}

Causal chain: {chain_summary}

This represents {type_desc[impl_type]} for these goals: {", ".join(goal_titles)}

Explain this implication in 2-3 sentences:""",
                    }
                ],
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=200,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="implication_engine",
            )

            return response.strip()

        except Exception as e:
            logger.warning(f"Explanation generation failed: {e}")
            # Fallback explanation
            final_target = chain.hops[-1].target_entity if chain.hops else "unknown"
            return f"This event may affect {final_target} and relates to your active goals."

    async def _generate_recommendations(
        self,
        chain: CausalChain,
        impl_type: ImplicationType,
    ) -> list[str]:
        """Generate actionable recommendations based on the implication.

        Uses LLM to suggest 1-3 specific actions the user can take.

        Args:
            chain: Causal chain
            impl_type: Implication type

        Returns:
            List of 1-3 recommendation strings
        """
        try:
            type_guidance = {
                ImplicationType.OPPORTUNITY: "actions to capitalize on this opportunity",
                ImplicationType.THREAT: "actions to mitigate this risk",
                ImplicationType.NEUTRAL: "actions to monitor or prepare",
            }

            system_prompt = f"""You are a strategic advisor suggesting specific, actionable next steps.
Generate 1-3 concrete recommendations for {type_guidance[impl_type]}.
Each recommendation should be specific and actionable.

Return ONLY a valid JSON array of strings, no other text:
["recommendation 1", "recommendation 2"]"""

            chain_summary = " → ".join(
                f"{h.source_entity} {h.relationship} {h.target_entity}" for h in chain.hops
            )

            response = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"""Event: {chain.trigger_event}

Causal chain: {chain_summary}

Implication type: {impl_type.value}

Generate 1-3 specific recommendations:""",
                    }
                ],
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=300,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="implication_engine",
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

            recommendations = json.loads(response)

            # Validate and limit
            if isinstance(recommendations, list):
                return [str(r) for r in recommendations[:3] if isinstance(r, str)]

            return []

        except Exception as e:
            logger.warning(f"Recommendation generation failed: {e}")
            return []

    async def _enrich_with_time_horizons(
        self,
        implications: list[Implication],
    ) -> list[Implication]:
        """Enrich implications with time horizon categorization.

        Uses the TimeHorizonAnalyzer to categorize each implication
        by when it will materialize.

        Args:
            implications: Implications to enrich

        Returns:
            Implications with time_horizon and time_to_impact fields populated
        """
        if not self._time_horizon_analyzer:
            return implications

        # Convert to dicts for analyzer
        impl_dicts = [
            {
                "content": impl.content,
                "trigger_event": impl.trigger_event,
                "causal_chain": impl.causal_chain,
            }
            for impl in implications
        ]

        try:
            # Categorize all implications
            categorized = await self._time_horizon_analyzer.categorize(impl_dicts)

            # Build a lookup by content (simple matching)
            horizon_lookup: dict[str, tuple[str | None, str | None]] = {}
            for horizon, impls in categorized.items():
                for impl_dict in impls:
                    content = impl_dict.get("content", "")
                    time_to_impact = impl_dict.get("time_to_impact")
                    horizon_lookup[content] = (horizon.value, time_to_impact)

            # Enrich original implications
            enriched: list[Implication] = []
            for impl in implications:
                content = impl.content
                horizon_data = horizon_lookup.get(content)
                if horizon_data:
                    enriched.append(
                        Implication(
                            **{
                                **impl.model_dump(),
                                "time_horizon": horizon_data[0],
                                "time_to_impact": horizon_data[1],
                            }
                        )
                    )
                else:
                    enriched.append(impl)

            return enriched

        except Exception as e:
            logger.warning(f"Time horizon enrichment failed: {e}")
            return implications
