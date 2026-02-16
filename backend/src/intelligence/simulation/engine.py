"""Mental Simulation Engine for ARIA Phase 7 Jarvis Intelligence.

This engine powers "what if" scenario analysis, enabling ARIA to:
- Simulate multiple outcomes from a scenario
- Traverse causal chains to identify downstream effects
- Generate recommendations based on expected value analysis
- Calculate sensitivity of outcomes to key variables

The engine integrates with the CausalChainEngine for chain traversal
and uses LLM for scenario parsing and outcome generation.
"""

import json
import logging
import time
import uuid
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import get_supabase_client
from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.simulation.models import (
    OutcomeClassification,
    QuickSimulationResponse,
    SimulationContext,
    SimulationOutcome,
    SimulationRequest,
    SimulationResult,
    SimulationScenario,
)

logger = logging.getLogger(__name__)


class MentalSimulationEngine:
    """Engine for running mental simulations of "what if" scenarios.

    Uses a hybrid approach combining:
    1. CausalChainEngine for traversing causal relationships
    2. LLM for scenario parsing, outcome generation, and reasoning

    Attributes:
        MAX_OUTCOMES: Maximum number of outcomes per simulation (5)
        MAX_HOPS: Maximum causal chain depth (5)
        MIN_CONFIDENCE: Minimum confidence threshold (0.3)
    """

    MAX_OUTCOMES: int = 5
    MAX_HOPS: int = 5
    MIN_CONFIDENCE: float = 0.3

    def __init__(
        self,
        causal_engine: CausalChainEngine | None = None,
        llm_client: LLMClient | None = None,
        db_client: Any = None,
    ) -> None:
        """Initialize the mental simulation engine.

        Args:
            causal_engine: CausalChainEngine for chain traversal
            llm_client: LLM client for generation
            db_client: Supabase client for context and persistence
        """
        self._causal = causal_engine
        self._llm = llm_client or LLMClient()
        self._db = db_client or get_supabase_client()

    async def simulate(
        self,
        user_id: str,
        request: SimulationRequest,
    ) -> SimulationResult:
        """Run a full mental simulation of a scenario.

        Main entry point for scenario analysis. Parses the scenario,
        traverses causal chains, generates outcomes, and provides
        a recommendation.

        Args:
            user_id: User ID for context scoping
            request: Simulation request with scenario and parameters

        Returns:
            SimulationResult with outcomes and recommendation
        """
        start_time = time.monotonic()

        # Clamp parameters
        max_outcomes = min(request.max_outcomes, self.MAX_OUTCOMES)
        max_hops = min(request.max_hops, self.MAX_HOPS)

        logger.info(
            "Starting mental simulation",
            extra={
                "user_id": user_id,
                "scenario_length": len(request.scenario),
                "max_outcomes": max_outcomes,
                "max_hops": max_hops,
            },
        )

        # Step 1: Gather context for the simulation
        context = await self._gather_context(
            user_id=user_id,
            request=request,
        )

        # Step 2: Parse scenario into key variables using LLM
        variables = request.variables or await self._extract_variables(
            scenario=request.scenario,
            context=context,
        )

        # Step 3: Generate scenario variations
        scenarios = await self._generate_scenarios(
            base_scenario=request.scenario,
            variables=variables,
            max_scenarios=max_outcomes,
            context=context,
        )

        # Step 4: Traverse causal chains and generate outcomes
        outcomes: list[SimulationOutcome] = []
        for scenario in scenarios:
            outcome = await self._simulate_scenario(
                user_id=user_id,
                scenario=scenario,
                context=context,
                max_hops=max_hops,
            )
            if outcome:
                outcomes.append(outcome)

        # Step 5: Generate overall recommendation
        recommended_path, reasoning = await self._generate_recommendation(
            scenario=request.scenario,
            outcomes=outcomes,
            context=context,
        )

        # Step 6: Calculate sensitivity analysis
        sensitivity = self._calculate_sensitivity(
            outcomes=outcomes,
            variables=variables,
        )

        # Step 7: Extract key insights
        key_insights = self._extract_key_insights(outcomes)

        # Calculate overall confidence
        confidence = self._calculate_confidence(outcomes)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Mental simulation completed",
            extra={
                "user_id": user_id,
                "outcomes_generated": len(outcomes),
                "confidence": confidence,
                "processing_time_ms": elapsed_ms,
            },
        )

        return SimulationResult(
            scenario=request.scenario,
            scenario_type=request.scenario_type,
            outcomes=outcomes,
            recommended_path=recommended_path,
            reasoning=reasoning,
            sensitivity=sensitivity,
            confidence=confidence,
            key_insights=key_insights,
            processing_time_ms=elapsed_ms,
        )

    async def quick_simulate(
        self,
        user_id: str,
        question: str,
    ) -> QuickSimulationResponse:
        """Run a lightweight simulation for chat "what if" questions.

        Uses LLM with user context without full causal chain traversal.
        Returns a natural language answer suitable for chat responses.

        Args:
            user_id: User ID for context
            question: The "what if" question to answer

        Returns:
            QuickSimulationResponse with natural language answer
        """
        start_time = time.monotonic()

        # Gather minimal context
        context = await self._gather_minimal_context(user_id)

        system_prompt = f"""You are ARIA, an AI assistant helping a life sciences professional think through scenarios.

User context:
{self._format_context_for_llm(context)}

When answering "what if" questions:
1. Be direct and practical
2. Consider 2-3 likely outcomes
3. Highlight key uncertainties
4. Provide a clear recommendation
5. Keep the answer concise (2-3 paragraphs max)

Format your response as JSON:
{{
  "answer": "Your natural language answer here",
  "key_points": ["point 1", "point 2", "point 3"],
  "confidence": 0.0-1.0
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": question}],
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=500,
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

            elapsed_ms = (time.monotonic() - start_time) * 1000

            return QuickSimulationResponse(
                answer=data.get("answer", "I couldn't analyze this scenario."),
                key_points=data.get("key_points", []),
                confidence=float(data.get("confidence", 0.5)),
                processing_time_ms=elapsed_ms,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse quick simulation response: {e}")
            elapsed_ms = (time.monotonic() - start_time) * 1000
            return QuickSimulationResponse(
                answer="I encountered an issue analyzing this scenario. Please try rephrasing.",
                key_points=[],
                confidence=0.3,
                processing_time_ms=elapsed_ms,
            )
        except Exception as e:
            logger.exception(f"Quick simulation failed: {e}")
            elapsed_ms = (time.monotonic() - start_time) * 1000
            return QuickSimulationResponse(
                answer="I couldn't analyze this scenario right now. Please try again.",
                key_points=[],
                confidence=0.2,
                processing_time_ms=elapsed_ms,
            )

    async def save_simulation(
        self,
        user_id: str,
        result: SimulationResult,
    ) -> uuid.UUID:
        """Save a simulation result to the jarvis_insights table.

        Args:
            user_id: User ID
            result: Simulation result to save

        Returns:
            UUID of the saved simulation
        """
        simulation_id = uuid.uuid4()

        # Determine classification from outcomes
        classification = self._determine_classification(result.outcomes)

        # Calculate scores
        avg_probability = (
            sum(o.probability for o in result.outcomes) / len(result.outcomes)
            if result.outcomes
            else 0.5
        )

        # Extract recommended actions from recommended path
        recommended_actions = [result.recommended_path[:500]] if result.recommended_path else []

        # Prepare causal chain (outcomes as JSONB)
        causal_chain = [o.model_dump() for o in result.outcomes]

        # Extract affected goals
        affected_goals: list[str] = []
        for outcome in result.outcomes:
            affected_goals.extend(outcome.affected_goals)
        affected_goals = list(set(affected_goals))

        insight_data: dict[str, Any] = {
            "id": str(simulation_id),
            "user_id": user_id,
            "insight_type": "simulation_result",
            "trigger_event": result.scenario[:2000],
            "content": f"{result.recommended_path}\n\nReasoning: {result.reasoning}",
            "classification": classification,
            "impact_score": avg_probability,
            "confidence": result.confidence,
            "urgency": 0.5,
            "combined_score": result.confidence * 0.7 + avg_probability * 0.3,
            "causal_chain": causal_chain,
            "affected_goals": affected_goals,
            "recommended_actions": recommended_actions,
            "time_horizon": "short_term",
            "status": "new",
        }

        try:
            self._db.table("jarvis_insights").insert(insight_data).execute()
            logger.info(
                "Simulation saved",
                extra={
                    "user_id": user_id,
                    "simulation_id": str(simulation_id),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to save simulation: {e}")

        return simulation_id

    async def _gather_context(
        self,
        user_id: str,
        request: SimulationRequest,
    ) -> SimulationContext:
        """Gather context for simulation analysis.

        Args:
            user_id: User ID
            request: Simulation request

        Returns:
            SimulationContext with relevant data
        """
        context = SimulationContext()

        try:
            # Get active goals
            goals_result = (
                self._db.table("goals")
                .select("id, title, status, priority")
                .eq("user_id", user_id)
                .eq("status", "active")
                .order("priority", desc=True)
                .limit(5)
                .execute()
            )
            if goals_result.data:
                context.active_goals = list(goals_result.data)  # type: ignore[arg-type]
        except Exception:
            pass

        try:
            # Get recent market signals
            signals_result = (
                self._db.table("market_signals")
                .select("signal_type, summary, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            if signals_result.data:
                context.recent_events = list(signals_result.data)  # type: ignore[arg-type]
        except Exception:
            pass

        # Add related lead if specified
        if request.related_lead_id:
            try:
                lead_result = (
                    self._db.table("leads")
                    .select("id, company_name, lifecycle_stage")
                    .eq("id", str(request.related_lead_id))
                    .eq("user_id", user_id)
                    .single()
                    .execute()
                )
                if lead_result.data:
                    context.related_leads = [dict(lead_result.data)]  # type: ignore[arg-type]
            except Exception:
                pass

        # Add related goal if specified
        if request.related_goal_id:
            try:
                goal_result = (
                    self._db.table("goals")
                    .select("id, title, status, description")
                    .eq("id", str(request.related_goal_id))
                    .eq("user_id", user_id)
                    .single()
                    .execute()
                )
                if goal_result.data:
                    # Prepend to active goals
                    goal_dict = dict(goal_result.data)  # type: ignore[arg-type]
                    if goal_dict not in context.active_goals:
                        context.active_goals.insert(0, goal_dict)
            except Exception:
                pass

        return context

    async def _gather_minimal_context(self, user_id: str) -> dict[str, Any]:
        """Gather minimal context for quick simulation.

        Args:
            user_id: User ID

        Returns:
            Dictionary with minimal context
        """
        context: dict[str, Any] = {"goals": [], "recent_activity": []}

        try:
            # Get top 3 active goals
            goals_result = (
                self._db.table("goals")
                .select("title, status")
                .eq("user_id", user_id)
                .eq("status", "active")
                .limit(3)
                .execute()
            )
            if goals_result.data:
                goals_list = list(goals_result.data)
                context["goals"] = [str(g.get("title", "")) for g in goals_list]
        except Exception:
            pass

        return context

    async def _extract_variables(
        self,
        scenario: str,
        context: SimulationContext,
    ) -> list[str]:
        """Extract key variables from the scenario using LLM.

        Args:
            scenario: The scenario text
            context: Simulation context

        Returns:
            List of key variable names
        """
        system_prompt = f"""You are an expert at identifying key variables in business scenarios.

Scenario: {scenario}

Context:
- Active goals: {[g.get("title", "") for g in context.active_goals]}
- Recent events: {[e.get("summary", "")[:100] for e in context.recent_events]}

Identify the 3-5 most important variables that could change the outcome.
A variable is something that could vary and affect the result.

Return ONLY a JSON array of variable names, no other text:
["variable1", "variable2", "variable3"]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": "What are the key variables?"}],
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=200,
            )

            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            variables = json.loads(response)
            return [str(v) for v in variables[:5] if v]

        except Exception as e:
            logger.warning(f"Variable extraction failed: {e}")
            return ["timing", "market_response", "competition"]

    async def _generate_scenarios(
        self,
        base_scenario: str,
        variables: list[str],
        max_scenarios: int,
        context: SimulationContext,
    ) -> list[SimulationScenario]:
        """Generate scenario variations based on key variables.

        Args:
            base_scenario: The base scenario text
            variables: Key variables to vary
            max_scenarios: Maximum scenarios to generate
            context: Simulation context

        Returns:
            List of scenario variations
        """
        system_prompt = f"""You are an expert at generating scenario variations for analysis.

Base scenario: {base_scenario}

Key variables: {variables}

Context:
- Active goals: {[g.get("title", "") for g in context.active_goals]}

Generate {max_scenarios} variations of this scenario, each emphasizing different outcomes.
Each variation should represent a plausible path the scenario could take.

Return ONLY a JSON array, no other text:
[
  {{
    "description": "Description of this scenario variation",
    "probability": 0.0-1.0,
    "variables": {{"variable_name": "value"}},
    "expected_outcome": "What likely happens"
  }}
]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": "Generate scenario variations"}],
                system_prompt=system_prompt,
                temperature=0.6,
                max_tokens=1000,
            )

            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            scenarios_data = json.loads(response)

            scenarios = []
            for s in scenarios_data[:max_scenarios]:
                scenarios.append(
                    SimulationScenario(
                        description=str(s.get("description", "")),
                        probability=float(s.get("probability", 0.5)),
                        variables=s.get("variables", {}),
                        expected_outcome=s.get("expected_outcome"),
                    )
                )

            return scenarios

        except Exception as e:
            logger.warning(f"Scenario generation failed: {e}")
            # Return a single base scenario as fallback
            return [
                SimulationScenario(
                    description=base_scenario,
                    probability=0.5,
                    variables=dict.fromkeys(variables[:3], "unknown"),
                    expected_outcome=None,
                )
            ]

    async def _simulate_scenario(
        self,
        user_id: str,
        scenario: SimulationScenario,
        context: SimulationContext,
        max_hops: int,
    ) -> SimulationOutcome | None:
        """Simulate a single scenario variation.

        Args:
            user_id: User ID
            scenario: Scenario to simulate
            context: Simulation context
            max_hops: Maximum causal chain depth

        Returns:
            SimulationOutcome or None if simulation fails
        """
        # Traverse causal chains if causal engine is available
        causal_chain: list[dict[str, Any]] = []
        if self._causal:
            try:
                chains = await self._causal.traverse(
                    user_id=user_id,
                    trigger_event=scenario.description,
                    max_hops=max_hops,
                    min_confidence=self.MIN_CONFIDENCE,
                )
                if chains:
                    # Take the highest-confidence chain
                    best_chain = max(chains, key=lambda c: c.final_confidence)
                    causal_chain = [hop.model_dump() for hop in best_chain.hops]
            except Exception as e:
                logger.warning(f"Causal traversal failed: {e}")

        # Generate outcome using LLM
        outcome = await self._generate_outcome(
            scenario=scenario,
            context=context,
            causal_chain=causal_chain,
        )

        return outcome

    async def _generate_outcome(
        self,
        scenario: SimulationScenario,
        context: SimulationContext,
        causal_chain: list[dict[str, Any]],
    ) -> SimulationOutcome | None:
        """Generate an outcome for a scenario using LLM.

        Args:
            scenario: Scenario to analyze
            context: Simulation context
            causal_chain: Causal chain data (if available)

        Returns:
            SimulationOutcome or None
        """
        causal_summary = ""
        if causal_chain:
            causal_summary = "Causal chain: " + " -> ".join(
                [hop.get("target_entity", "?") for hop in causal_chain[:3]]
            )

        system_prompt = f"""You are an expert at analyzing business scenario outcomes.

Scenario: {scenario.description}
Probability: {scenario.probability}
Variables: {scenario.variables}
Expected outcome: {scenario.expected_outcome or "Unknown"}

{causal_summary}

User's goals: {[g.get("title", "") for g in context.active_goals]}

Analyze this scenario and predict the outcome. Be balanced and realistic.

Return ONLY a JSON object, no other text:
{{
  "positive_outcomes": ["positive effect 1", "positive effect 2"],
  "negative_outcomes": ["negative effect 1", "negative effect 2"],
  "key_uncertainties": ["uncertainty 1", "uncertainty 2"],
  "recommended": true/false,
  "reasoning": "Why this path is or isn't recommended",
  "classification": "positive/negative/mixed/neutral",
  "time_to_impact": "2-4 weeks",
  "affected_goals": ["goal_id_1", "goal_id_2"]
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": "Analyze this scenario"}],
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=500,
            )

            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            data = json.loads(response)

            # Parse classification
            classification_str = data.get("classification", "mixed").lower()
            try:
                classification = OutcomeClassification(classification_str)
            except ValueError:
                classification = OutcomeClassification.MIXED

            return SimulationOutcome(
                scenario=scenario.description,
                probability=scenario.probability,
                classification=classification,
                positive_outcomes=data.get("positive_outcomes", []),
                negative_outcomes=data.get("negative_outcomes", []),
                key_uncertainties=data.get("key_uncertainties", []),
                recommended=bool(data.get("recommended", False)),
                reasoning=data.get("reasoning", ""),
                causal_chain=causal_chain,
                time_to_impact=data.get("time_to_impact"),
                affected_goals=data.get("affected_goals", []),
            )

        except Exception as e:
            logger.warning(f"Outcome generation failed: {e}")
            return None

    async def _generate_recommendation(
        self,
        scenario: str,  # noqa: ARG002
        outcomes: list[SimulationOutcome],
        context: SimulationContext,  # noqa: ARG002
    ) -> tuple[str, str]:
        """Generate overall recommendation from outcomes.

        Args:
            scenario: Original scenario
            outcomes: All generated outcomes
            context: Simulation context

        Returns:
            Tuple of (recommended_path, reasoning)
        """
        if not outcomes:
            return (
                "Unable to generate a recommendation due to insufficient analysis.",
                "No outcomes were successfully generated.",
            )

        # Find recommended outcomes
        recommended = [o for o in outcomes if o.recommended]

        if recommended:
            # Use the highest probability recommended outcome
            best = max(recommended, key=lambda o: o.probability)
            return (
                best.scenario,
                f"Based on {len(outcomes)} outcomes analyzed, this path offers the best balance of probability ({best.probability:.0%}) and positive impact. {best.reasoning}",
            )

        # No recommended outcomes - pick the least bad
        least_negative = min(outcomes, key=lambda o: len(o.negative_outcomes))
        return (
            "Consider alternative approaches not covered by this simulation.",
            f"All {len(outcomes)} analyzed paths have significant risks. "
            f"The least risky option has {len(least_negative.negative_outcomes)} negative outcomes. "
            "Consider gathering more information or exploring alternatives.",
        )

    def _calculate_sensitivity(
        self,
        outcomes: list[SimulationOutcome],
        variables: list[str],
    ) -> dict[str, float]:
        """Calculate sensitivity of outcomes to variables.

        Args:
            outcomes: Generated outcomes
            variables: Key variables

        Returns:
            Dictionary mapping variable names to impact scores
        """
        sensitivity: dict[str, float] = {}

        for var in variables:
            # Simple heuristic: count how often variable appears in outcomes
            count = sum(
                1
                for o in outcomes
                if var.lower() in o.reasoning.lower()
                or any(var.lower() in p.lower() for p in o.positive_outcomes)
                or any(var.lower() in n.lower() for n in o.negative_outcomes)
            )
            sensitivity[var] = count / len(outcomes) if outcomes else 0.0

        return sensitivity

    def _extract_key_insights(
        self,
        outcomes: list[SimulationOutcome],
    ) -> list[str]:
        """Extract key insights from outcomes.

        Args:
            outcomes: Generated outcomes

        Returns:
            List of key insight strings
        """
        insights: list[str] = []

        if not outcomes:
            return ["No outcomes were generated for analysis."]

        # Most common positive outcomes
        all_positives = []
        for o in outcomes:
            all_positives.extend(o.positive_outcomes)
        if all_positives:
            insights.append(f"Key opportunity: {all_positives[0]}")

        # Most common negative outcomes
        all_negatives = []
        for o in outcomes:
            all_negatives.extend(o.negative_outcomes)
        if all_negatives:
            insights.append(f"Key risk: {all_negatives[0]}")

        # Key uncertainties
        all_uncertainties = []
        for o in outcomes:
            all_uncertainties.extend(o.key_uncertainties)
        if all_uncertainties:
            insights.append(f"Key uncertainty: {all_uncertainties[0]}")

        # Recommendation rate
        recommended_count = sum(1 for o in outcomes if o.recommended)
        rate = recommended_count / len(outcomes)
        if rate >= 0.5:
            insights.append(f"{rate:.0%} of scenarios analyzed are favorable")
        else:
            insights.append(f"Only {rate:.0%} of scenarios analyzed are favorable")

        return insights[:4]

    def _calculate_confidence(
        self,
        outcomes: list[SimulationOutcome],
    ) -> float:
        """Calculate overall confidence in the simulation.

        Args:
            outcomes: Generated outcomes

        Returns:
            Confidence score (0-1)
        """
        if not outcomes:
            return 0.3

        # Base confidence on number of outcomes and their probabilities
        avg_probability = sum(o.probability for o in outcomes) / len(outcomes)

        # More outcomes = higher confidence (up to a point)
        coverage_bonus = min(len(outcomes) / 3.0, 0.2)

        # Consistency bonus: if outcomes agree on recommendation
        recommended = [o for o in outcomes if o.recommended]
        if recommended:
            agreement_rate = len(recommended) / len(outcomes)
            consistency_bonus = 0.1 if agreement_rate >= 0.5 else 0.0
        else:
            consistency_bonus = 0.0

        confidence = min(avg_probability * 0.6 + coverage_bonus + consistency_bonus, 1.0)
        return round(confidence, 2)

    def _determine_classification(
        self,
        outcomes: list[SimulationOutcome],
    ) -> str:
        """Determine overall classification from outcomes.

        Args:
            outcomes: Generated outcomes

        Returns:
            Classification string for jarvis_insights
        """
        if not outcomes:
            return "neutral"

        # Count by classification
        positive = sum(1 for o in outcomes if o.classification == OutcomeClassification.POSITIVE)
        negative = sum(1 for o in outcomes if o.classification == OutcomeClassification.NEGATIVE)

        if positive > negative:
            return "opportunity"
        elif negative > positive:
            return "threat"
        else:
            return "neutral"

    def _format_context_for_llm(self, context: dict[str, Any]) -> str:
        """Format context dictionary for LLM prompt.

        Args:
            context: Context dictionary

        Returns:
            Formatted string
        """
        parts = []
        if context.get("goals"):
            parts.append(f"Active goals: {', '.join(context['goals'])}")
        if context.get("recent_activity"):
            parts.append(f"Recent activity: {context['recent_activity'][:200]}")
        return "\n".join(parts) if parts else "No specific context available."
