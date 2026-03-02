"""OODA loop cognitive processing module.

Implements the Observe-Orient-Decide-Act loop for systematic
reasoning about tasks. The OODA loop is ARIA's core cognitive
processing framework that iterates until goals are achieved.

Phases:
- Observe: Gather context from memory and environment
- Orient: Analyze situation, identify patterns
- Decide: Select best action from options
- Act: Execute chosen action

Each phase is logged for transparency and debugging.
"""

import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.exceptions import OODABlockedError, OODAMaxIterationsError
from src.core.task_types import TaskType

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.memory.episodic import EpisodicMemory
    from src.memory.semantic import SemanticMemory
    from src.memory.working import WorkingMemory
    from src.services.ooda_logger import OODALogger

logger = logging.getLogger(__name__)


class OODAPhase(Enum):
    """Phases of the OODA loop cognitive cycle."""

    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"


@dataclass
class OODAConfig:
    """Configuration for OODA loop execution.

    Controls token budgets per phase and overall constraints.
    """

    observe_budget: int = 2000  # Max tokens for observation phase
    orient_budget: int = 3000  # Max tokens for orientation phase
    decide_budget: int = 2000  # Max tokens for decision phase
    act_budget: int = 1000  # Max tokens for action phase
    max_iterations: int = 10  # Maximum OODA cycles before stopping
    total_budget: int = 50000  # Total token budget across all iterations

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "observe_budget": self.observe_budget,
            "orient_budget": self.orient_budget,
            "decide_budget": self.decide_budget,
            "act_budget": self.act_budget,
            "max_iterations": self.max_iterations,
            "total_budget": self.total_budget,
        }


@dataclass
class OODAPhaseLogEntry:
    """Log entry for a single OODA phase execution.

    Captures execution details for transparency and debugging.
    """

    phase: OODAPhase
    iteration: int
    input_summary: str
    output_summary: str
    tokens_used: int = 0
    duration_ms: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "phase": self.phase.value,
            "iteration": self.iteration,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OODAState:
    """State of an OODA loop execution.

    Tracks the current phase, observations, analysis results,
    decisions, and action outcomes across iterations.
    """

    goal_id: str
    current_phase: OODAPhase = OODAPhase.OBSERVE
    observations: list[dict[str, Any]] = field(default_factory=list)
    orientation: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] | None = None
    action_result: Any = None
    iteration: int = 0
    max_iterations: int = 10
    phase_logs: list[OODAPhaseLogEntry] = field(default_factory=list)
    is_complete: bool = False
    is_blocked: bool = False
    blocked_reason: str | None = None
    total_tokens_used: int = 0
    thinking_traces: dict[str, str] = field(default_factory=dict)
    task_characteristics: dict[str, Any] | None = None
    approval_level: str | None = None
    capability_token: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "goal_id": self.goal_id,
            "current_phase": self.current_phase.value,
            "observations": self.observations,
            "orientation": self.orientation,
            "decision": self.decision,
            "action_result": self.action_result,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "phase_logs": [log.to_dict() for log in self.phase_logs],
            "is_complete": self.is_complete,
            "is_blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
            "total_tokens_used": self.total_tokens_used,
            "thinking_traces": self.thinking_traces,
            "task_characteristics": self.task_characteristics,
            "approval_level": self.approval_level,
            "capability_token": self.capability_token,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OODAState":
        """Create OODAState from dictionary.

        Args:
            data: Dictionary containing state data.

        Returns:
            OODAState instance with restored state.
        """
        state = cls(
            goal_id=data["goal_id"],
            current_phase=OODAPhase(data["current_phase"]),
            observations=data.get("observations", []),
            orientation=data.get("orientation", {}),
            decision=data.get("decision"),
            action_result=data.get("action_result"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 10),
            is_complete=data.get("is_complete", False),
            is_blocked=data.get("is_blocked", False),
            blocked_reason=data.get("blocked_reason"),
            total_tokens_used=data.get("total_tokens_used", 0),
            thinking_traces=data.get("thinking_traces", {}),
            task_characteristics=data.get("task_characteristics"),
            approval_level=data.get("approval_level"),
            capability_token=data.get("capability_token"),
        )

        # Restore phase logs
        for log_data in data.get("phase_logs", []):
            state.phase_logs.append(
                OODAPhaseLogEntry(
                    phase=OODAPhase(log_data["phase"]),
                    iteration=log_data["iteration"],
                    input_summary=log_data["input_summary"],
                    output_summary=log_data["output_summary"],
                    tokens_used=log_data.get("tokens_used", 0),
                    duration_ms=log_data.get("duration_ms", 0),
                    timestamp=datetime.fromisoformat(log_data["timestamp"]),
                )
            )

        return state


class OODALoop:
    """OODA loop cognitive processing engine.

    Implements the Observe-Orient-Decide-Act cycle for systematic
    task reasoning. Each iteration gathers context, analyzes the
    situation, selects an action, and executes it.
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        episodic_memory: "EpisodicMemory",
        semantic_memory: "SemanticMemory",
        working_memory: "WorkingMemory",
        config: OODAConfig | None = None,
        agent_executor: Any | None = None,
        persona_builder: Any | None = None,
        hot_context_builder: Any | None = None,
        cold_memory_retriever: Any | None = None,
        cost_governor: Any | None = None,
        user_id: str | None = None,
        trust_service: Any | None = None,
        dct_minter: Any | None = None,
        ooda_logger: "OODALogger | None" = None,
    ) -> None:
        """Initialize OODA loop.

        Args:
            llm_client: LLM client for reasoning.
            episodic_memory: Episodic memory service.
            semantic_memory: Semantic memory service.
            working_memory: Working memory for current context.
            config: Optional configuration for budgets.
            agent_executor: Optional callable for dispatching agent actions.
                Signature: async (action, agent, parameters, goal) -> dict
            persona_builder: Optional PersonaBuilder for centralized prompt assembly.
            hot_context_builder: Optional HotContextBuilder for always-loaded context.
            cold_memory_retriever: Optional ColdMemoryRetriever for on-demand retrieval.
            cost_governor: Optional CostGovernor for budget-aware thinking.
            user_id: Optional user ID — enables extended thinking in orient/decide.
            trust_service: Optional TrustCalibrationService for approval level lookup.
            dct_minter: Optional DCTMinter for scoped agent permissions.
            ooda_logger: Optional OODALogger for persisting phase data to admin dashboard.
        """
        self.llm = llm_client
        self.episodic = episodic_memory
        self.semantic = semantic_memory
        self.working = working_memory
        self.config = config or OODAConfig()
        self.agent_executor = agent_executor
        self.persona_builder = persona_builder
        self._cost_governor = cost_governor
        self._user_id = user_id
        self._trust_service = trust_service
        self._dct_minter = dct_minter
        self._ooda_logger = ooda_logger

        # Auto-initialize memory builders when not provided (fail-open)
        self._hot_context_builder = hot_context_builder
        if self._hot_context_builder is None:
            try:
                from src.db.supabase import SupabaseClient
                from src.memory.hot_context import HotContextBuilder

                self._hot_context_builder = HotContextBuilder(
                    db_client=SupabaseClient.get_client()
                )
            except Exception as e:
                logger.warning("Auto-init HotContextBuilder failed (non-fatal): %s", e)

        self._cold_memory_retriever = cold_memory_retriever
        if self._cold_memory_retriever is None:
            try:
                from src.db.supabase import SupabaseClient
                from src.memory.cold_retrieval import ColdMemoryRetriever

                self._cold_memory_retriever = ColdMemoryRetriever(
                    db_client=SupabaseClient.get_client()
                )
            except Exception as e:
                logger.warning("Auto-init ColdMemoryRetriever failed (non-fatal): %s", e)

    @staticmethod
    def _agent_to_category(agent_name: str) -> str:
        """Map agent name to trust action category."""
        mapping = {
            "hunter": "lead_discovery",
            "analyst": "research",
            "strategist": "strategy",
            "scribe": "email_draft",
            "operator": "crm_action",
            "scout": "market_monitoring",
            "verifier": "verification",
            "executor": "browser_automation",
        }
        return mapping.get((agent_name or "").lower(), "general")

    async def observe(
        self,
        state: OODAState,
        goal: dict[str, Any],
    ) -> OODAState:
        """Gather relevant information from memory and context.

        Queries episodic memory for related events, semantic memory
        for relevant facts, and working memory for current context.

        Args:
            state: Current OODA state.
            goal: The goal being pursued.

        Returns:
            Updated state with observations.
        """
        start_time = time.perf_counter()
        observations: list[dict[str, Any]] = []

        # Build search query from goal
        search_query = f"{goal.get('title', '')} {goal.get('description', '')}"

        # Get user_id from working memory (or constructor override)
        user_id = self._user_id or self.working.user_id

        # --- Hot/Cold memory path (preferred) ---
        if self._hot_context_builder is not None:
            try:
                hot = await self._hot_context_builder.build(
                    user_id, working_memory=self.working, active_goal=goal
                )
                observations.append(
                    {
                        "source": "hot_context",
                        "type": "hot",
                        "data": hot.formatted if hasattr(hot, "formatted") else str(hot),
                    }
                )
            except Exception as e:
                logger.warning("Failed to build hot context: %s", e)

        if self._cold_memory_retriever is not None:
            try:
                cold_results = await self._cold_memory_retriever.retrieve(
                    user_id, query=search_query, limit=10
                )
                for result in cold_results:
                    observations.append(
                        {
                            "source": result.source.value if hasattr(result, "source") else "cold",
                            "type": "cold",
                            "data": result.to_dict() if hasattr(result, "to_dict") else str(result),
                        }
                    )
            except Exception as e:
                logger.warning("Failed to retrieve cold memory: %s", e)

        # --- Legacy episodic/semantic path (when Hot/Cold not provided) ---
        if self._hot_context_builder is None and self._cold_memory_retriever is None:
            # Query episodic memory for related events
            try:
                episodes = await self.episodic.semantic_search(
                    user_id=user_id,
                    query=search_query,
                    limit=5,
                )
                for episode in episodes:
                    observations.append(
                        {
                            "source": "episodic",
                            "type": "episode",
                            "data": episode.to_dict() if hasattr(episode, "to_dict") else str(episode),
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to query episodic memory: {e}")

            # Query semantic memory for relevant facts
            try:
                facts = await self.semantic.search_facts(
                    user_id=user_id,
                    query=search_query,
                    limit=10,
                )
                for fact in facts:
                    observations.append(
                        {
                            "source": "semantic",
                            "type": "fact",
                            "data": fact.to_dict() if hasattr(fact, "to_dict") else str(fact),
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to query semantic memory: {e}")

        # Get current working memory context
        try:
            context = self.working.get_context_for_llm()
            observations.append(
                {
                    "source": "working",
                    "type": "conversation",
                    "data": context,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to get working memory context: {e}")

        # Update state
        state.observations = observations
        state.current_phase = OODAPhase.ORIENT

        # Estimate tokens used based on observations data size
        # Rough estimate: 4 characters per token
        import json as json_module

        observations_str = json_module.dumps(observations, default=str)
        estimated_tokens = len(observations_str) // 4

        # Log phase execution
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        state.phase_logs.append(
            OODAPhaseLogEntry(
                phase=OODAPhase.OBSERVE,
                iteration=state.iteration,
                input_summary=f"Goal: {goal.get('title', 'Unknown')}",
                output_summary=f"Gathered {len(observations)} observations",
                tokens_used=estimated_tokens,
                duration_ms=duration_ms,
            )
        )

        logger.info(
            "OODA observe phase complete",
            extra={
                "goal_id": state.goal_id,
                "iteration": state.iteration,
                "observation_count": len(observations),
                "duration_ms": duration_ms,
            },
        )

        return state

    async def orient(
        self,
        state: OODAState,
        goal: dict[str, Any],
    ) -> OODAState:
        """Analyze observations and identify patterns.

        Uses LLM to synthesize observations, identify threats and
        opportunities, and map to available agent capabilities.

        Args:
            state: Current OODA state with observations.
            goal: The goal being pursued.

        Returns:
            Updated state with orientation analysis.
        """
        import json

        start_time = time.perf_counter()

        # Build prompt for LLM analysis
        observations_summary = json.dumps(state.observations, indent=2, default=str)

        # --- Graph context enrichment ---
        graph_context_str = ""
        if self._cold_memory_retriever is not None:
            try:
                user_id_for_graph = self._user_id or self.working.user_id
                graph_context_str = await self._get_graph_context_for_orient(
                    state.observations, user_id_for_graph
                )
            except Exception as e:
                logger.warning("Graph context retrieval failed in orient: %s", e)

        orient_task_instructions = """Analyze the observations and produce a structured analysis.

When Knowledge Graph Context is provided, look for non-obvious connections between entities.
If Company A just lost a key executive AND Company B is expanding in that space AND
we have an active opportunity with Company A — that's an implication chain the user needs to know about.

Output ONLY valid JSON with this structure:
{
    "patterns": ["list of patterns identified"],
    "opportunities": ["list of opportunities to pursue the goal"],
    "threats": ["list of obstacles or risks"],
    "recommended_focus": "single most important area to focus on",
    "implication_chains": [
        {
            "signal": "what triggered this chain",
            "chain": "A → B → C causal connection",
            "implication": "what this means for the user",
            "urgency": "high | medium | low"
        }
    ]
}

The implication_chains array can be empty if no multi-hop connections are found."""

        # Use PersonaBuilder as primary, fall back to task instructions only
        system_prompt: str | None = None
        if self.persona_builder is not None:
            try:
                from src.core.persona import PersonaRequest

                user_id = self.working.user_id
                request = PersonaRequest(
                    user_id=user_id,
                    agent_name="ooda_orient",
                    agent_role_description="ARIA's cognitive analysis module",
                    task_description=f"Analyze observations for goal: {goal.get('title', 'Unknown')[:80]}",
                    output_format="json",
                )
                ctx = await self.persona_builder.build(request)
                system_prompt = ctx.to_system_prompt() + "\n\n" + orient_task_instructions
            except Exception as e:
                logger.warning("PersonaBuilder failed in orient, using fallback: %s", e)

        if system_prompt is None:
            system_prompt = orient_task_instructions

        user_prompt = f"""Goal: {goal.get("title", "Unknown")}
Description: {goal.get("description", "No description")}

Observations:
{observations_summary}
"""
        if graph_context_str:
            user_prompt += f"""
Knowledge Graph Context (entity relationships and history):
{graph_context_str}
"""
        user_prompt += """
Analyze these observations and identify patterns, opportunities, and threats relevant to achieving the goal.
If graph context is available, identify implication chains — non-obvious multi-hop connections between entities."""

        # Call LLM for analysis — use extended thinking when user_id is set
        estimated_tokens = 0
        orientation = None  # sentinel: set to dict on error, parsed from response otherwise
        response: str | None = None

        use_thinking = bool(self._user_id)
        if use_thinking and self._cost_governor:
            try:
                budget = await self._cost_governor.check_budget(self._user_id)
                if not budget.can_proceed:
                    use_thinking = False
            except Exception:
                use_thinking = False

        if use_thinking:
            try:
                effort = "complex"
                if self._cost_governor:
                    budget = await self._cost_governor.check_budget(self._user_id)  # type: ignore[arg-type]
                    effort = self._cost_governor.get_thinking_budget(budget, effort)

                llm_response = await self.llm.generate_response_with_thinking(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=self.config.orient_budget,
                    thinking_effort=effort,
                    user_id=self._user_id,
                    task=TaskType.OODA_ORIENT,
                    agent_id="ooda",
                )
                response = llm_response.text
                if llm_response.thinking:
                    state.thinking_traces["orient"] = llm_response.thinking
                if llm_response.usage:
                    estimated_tokens = llm_response.usage.total_tokens
                else:
                    estimated_tokens = (len(system_prompt) + len(user_prompt) + len(response)) // 4
            except Exception as e:
                logger.error("Extended thinking failed in orient, falling back: %s", e)
                use_thinking = False  # fall through to standard path

        if not use_thinking and response is None and orientation is None:
            try:
                response = await self.llm.generate_response(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=self.config.orient_budget,
                    temperature=0.3,
                    task=TaskType.OODA_ORIENT,
                    agent_id="ooda",
                )
                input_chars = len(system_prompt) + len(user_prompt)
                output_chars = len(response)
                estimated_tokens = (input_chars + output_chars) // 4
            except Exception as e:
                logger.error(f"LLM call failed in orient phase: {e}")
                orientation = {
                    "patterns": [],
                    "opportunities": [],
                    "threats": [],
                    "recommended_focus": "LLM analysis failed - proceeding cautiously",
                    "error": str(e),
                }

        # Parse JSON response (when we got one and no error orientation was set)
        if response is not None and orientation is None:
            try:
                orientation = json.loads(response)
            except json.JSONDecodeError:
                # Try extracting JSON from markdown code fences
                import re

                json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
                if json_match:
                    try:
                        orientation = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass
                if orientation is None:
                    brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)
                    if brace_match:
                        try:
                            orientation = json.loads(brace_match.group(0))
                        except json.JSONDecodeError:
                            pass
                if orientation is None:
                    logger.warning("Failed to parse LLM response as JSON, using default orientation")
                    orientation = {
                        "patterns": [],
                        "opportunities": [],
                        "threats": [],
                        "recommended_focus": "Unable to analyze - proceeding with default strategy",
                        "raw_response": response[:500],
                    }

        if orientation is None:
            orientation = {
                "patterns": [],
                "opportunities": [],
                "threats": [],
                "recommended_focus": "No analysis available",
            }

        # Update state
        state.orientation = orientation
        state.current_phase = OODAPhase.DECIDE

        # Log phase execution
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        state.phase_logs.append(
            OODAPhaseLogEntry(
                phase=OODAPhase.ORIENT,
                iteration=state.iteration,
                input_summary=f"Analyzed {len(state.observations)} observations",
                output_summary=f"Focus: {orientation.get('recommended_focus', 'Unknown')}",
                tokens_used=estimated_tokens,
                duration_ms=duration_ms,
            )
        )

        logger.info(
            "OODA orient phase complete",
            extra={
                "goal_id": state.goal_id,
                "iteration": state.iteration,
                "patterns_found": len(orientation.get("patterns", [])),
                "duration_ms": duration_ms,
            },
        )

        # --- Connection awareness: detect newly connected tools ---
        if self._user_id:
            try:
                orientation = await self._orient_with_connections(
                    goal_id=state.goal_id,
                    user_id=self._user_id,
                    existing_orientation=orientation,
                )
            except Exception as e:
                logger.warning("Connection awareness check failed (non-fatal): %s", e)

        # Evaluate high-urgency implication chains for proactive goal proposals
        if self._user_id and orientation:
            try:
                from src.services.proactive_goal_proposer import (
                    ProactiveGoalProposer,
                    _MAX_PROPOSALS_PER_ORIENT,
                )

                proposer = ProactiveGoalProposer()
                chains = [
                    t for t in orientation.get("threats", [])
                    if isinstance(t, dict) and t.get("urgency") == "high"
                ] + [
                    o for o in orientation.get("opportunities", [])
                    if isinstance(o, dict) and o.get("urgency") == "high"
                ]
                proposals_sent = 0
                for chain in chains[:_MAX_PROPOSALS_PER_ORIENT]:
                    with contextlib.suppress(Exception):
                        sent = await proposer.evaluate_implication_chain(
                            user_id=self._user_id,
                            goal_id=state.goal_id,
                            chain=chain,
                        )
                        if sent:
                            proposals_sent += 1
                if proposals_sent:
                    logger.debug(
                        "Proactive proposals from orient: %d", proposals_sent,
                        extra={"user_id": self._user_id, "goal_id": state.goal_id},
                    )
            except Exception:
                pass  # Best-effort — never break OODA for proposals

        return state

    async def _get_graph_context_for_orient(
        self,
        observations: list[dict[str, Any]],
        user_id: str,
    ) -> str:
        """Extract entities from observations and retrieve graph context.

        Args:
            observations: OODA observations from Observe phase.
            user_id: User ID for scoped graph queries.

        Returns:
            Formatted string of graph context for the Orient prompt.
        """
        if self._cold_memory_retriever is None:
            return ""

        import asyncio

        from src.core.entity_extractor import extract_entities_from_observations

        entities = extract_entities_from_observations(observations, max_entities=5)
        if not entities:
            return ""

        # Query graph for each entity in parallel
        tasks = [
            self._cold_memory_retriever.retrieve_for_entity(
                user_id=user_id,
                entity_id=entity,
                hops=3,
            )
            for entity in entities
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results
        parts: list[str] = []
        for entity, result in zip(entities, results, strict=False):
            if isinstance(result, BaseException):
                logger.warning("Graph retrieval failed for %s: %s", entity, result)
                continue

            section_lines: list[str] = [f"### {entity}"]
            if result.direct_facts:
                section_lines.append("Facts:")
                for fact in result.direct_facts[:3]:
                    section_lines.append(f"  - {fact.content}")
            if result.relationships:
                section_lines.append("Relationships:")
                for rel in result.relationships[:3]:
                    section_lines.append(f"  - {rel.content}")
            if result.recent_interactions:
                section_lines.append("Recent Interactions:")
                for interaction in result.recent_interactions[:3]:
                    section_lines.append(f"  - {interaction.content}")

            if len(section_lines) > 1:  # More than just the header
                parts.append("\n".join(section_lines))

        return "\n\n".join(parts) if parts else ""

    async def _orient_with_connections(
        self,
        goal_id: str,
        user_id: str,
        existing_orientation: dict[str, Any],
    ) -> dict[str, Any]:
        """Enhance orientation with connection awareness.

        Checks if any tools were connected since the goal was planned
        that could resolve capability gaps on blocked tasks.

        Args:
            goal_id: The active goal being monitored.
            user_id: Goal owner.
            existing_orientation: The orientation dict from the standard Orient phase.

        Returns:
            Enhanced orientation dict with connection_changes field.
        """
        from src.integrations.connection_registry import get_connection_registry

        registry = get_connection_registry()

        connection_changes: dict[str, Any] = {
            "new_connections_detected": False,
            "resolved_gaps": [],
            "still_blocked": [],
            "recommendation": None,
        }

        try:
            client = __import__("src.db.supabase", fromlist=["SupabaseClient"]).SupabaseClient.get_client()

            goal_result = (
                client.table("goals")
                .select("config, status")
                .eq("id", goal_id)
                .maybe_single()
                .execute()
            )
            if not goal_result.data:
                return {**existing_orientation, "connection_changes": connection_changes}

            goal_config = goal_result.data.get("config", {}) or {}
            capability_gaps = goal_config.get("capability_gaps", [])
            assessed_at = goal_config.get("capability_assessed_at")

            if not capability_gaps:
                return {**existing_orientation, "connection_changes": connection_changes}

            # Check for connections added since the assessment
            if assessed_at:
                assessed_dt = datetime.fromisoformat(assessed_at)
                hours_since = (datetime.now(UTC) - assessed_dt).total_seconds() / 3600
                recent = await registry.get_recently_added_connections(
                    user_id, hours=max(int(hours_since) + 1, 1)
                )
            else:
                recent = await registry.get_recently_added_connections(user_id, hours=24)

            if not recent:
                connection_changes["still_blocked"] = [
                    g["capability"] if isinstance(g, dict) else g
                    for g in capability_gaps
                    if (isinstance(g, dict) and g.get("severity") == "blocking") or isinstance(g, str)
                ]
                return {**existing_orientation, "connection_changes": connection_changes}

            # Check which gaps are now resolved via CapabilityGraphService
            from src.db.supabase import SupabaseClient as SBClient
            from src.services.capability_provisioning import CapabilityGraphService

            graph = CapabilityGraphService(SBClient.get_client())

            blocked_capabilities = [
                g["capability"] if isinstance(g, dict) else g
                for g in capability_gaps
                if (isinstance(g, dict) and g.get("severity") == "blocking") or isinstance(g, str)
            ]

            resolved_gaps: list[str] = []
            still_blocked: list[str] = []
            for cap_name in blocked_capabilities:
                best = await graph.get_best_available(cap_name, user_id)
                if best is not None:
                    resolved_gaps.append(cap_name)
                else:
                    still_blocked.append(cap_name)

            connection_changes["new_connections_detected"] = True
            connection_changes["resolved_gaps"] = resolved_gaps
            connection_changes["still_blocked"] = still_blocked

            if resolved_gaps:
                connection_changes["recommendation"] = "resume_blocked_tasks"
                logger.info(
                    "OODA Orient: Goal %s has %d resolved gaps — recommending task resumption",
                    goal_id,
                    len(resolved_gaps),
                )

        except Exception as e:
            logger.warning("OODA Orient connection check failed for goal %s: %s", goal_id, e)

        return {**existing_orientation, "connection_changes": connection_changes}

    async def decide(
        self,
        state: OODAState,
        goal: dict[str, Any],
    ) -> OODAState:
        """Select the best action to take.

        Uses LLM to generate action options, evaluate them against
        the goal, and select the highest-value action.

        Args:
            state: Current OODA state with orientation.
            goal: The goal being pursued.

        Returns:
            Updated state with decision.
        """
        import json

        start_time = time.perf_counter()

        # --- Pre-LLM check: auto-resume blocked tasks if Orient detected resolved gaps ---
        connection_changes = state.orientation.get("connection_changes", {})
        if connection_changes.get("recommendation") == "resume_blocked_tasks":
            resolved_gaps = connection_changes.get("resolved_gaps", [])
            if resolved_gaps:
                logger.info(
                    "OODA Decide: Auto-selecting resume_blocked_tasks for goal %s, "
                    "resolved: %s",
                    state.goal_id,
                    resolved_gaps,
                )
                decision: dict[str, Any] = {
                    "action": "resume_blocked_tasks",
                    "agent": None,
                    "parameters": {},
                    "reasoning": (
                        f"New tool connections detected. Previously blocked capabilities "
                        f"now available: {', '.join(resolved_gaps)}"
                    ),
                    "resolved_capabilities": resolved_gaps,
                    "confidence": 0.95,
                }
                state.decision = decision
                state.current_phase = OODAPhase.ACT

                duration_ms = int((time.perf_counter() - start_time) * 1000)
                state.phase_logs.append(
                    OODAPhaseLogEntry(
                        phase=OODAPhase.DECIDE,
                        iteration=state.iteration,
                        input_summary=f"Connection changes detected: {len(resolved_gaps)} resolved",
                        output_summary="Decision: resume_blocked_tasks (deterministic)",
                        tokens_used=0,
                        duration_ms=duration_ms,
                    )
                )
                return state

        # Build prompt for decision
        orientation_summary = json.dumps(state.orientation, indent=2, default=str)

        decide_task_instructions = """Based on the analysis, select the best action to take.

Available actions:
- "research": Use Analyst agent to gather information
- "search": Use Hunter agent to find leads/companies
- "communicate": Use Scribe agent to draft communications
- "schedule": Use Operator agent for calendar/CRM operations
- "monitor": Use Scout agent for intelligence gathering
- "plan": Use Strategist agent for planning
- "complete": Goal has been achieved
- "blocked": Cannot proceed without user intervention

Output ONLY valid JSON with this structure:
{
    "action": "action_name",
    "agent": "agent_type or null",
    "parameters": {"key": "value"},
    "reasoning": "why this action was chosen",
    "task_characteristics": {
        "complexity": 0.0-1.0,
        "criticality": 0.0-1.0,
        "uncertainty": 0.0-1.0,
        "reversibility": 0.0-1.0,
        "verifiability": 0.0-1.0,
        "subjectivity": 0.0-1.0,
        "contextuality": 0.0-1.0
    }
}

Task characteristics guide:
- complexity: How many steps / sub-tasks are involved (1.0 = very complex)
- criticality: Business impact if this goes wrong (1.0 = severe consequences)
- uncertainty: How much is unknown about the right approach (1.0 = highly uncertain)
- reversibility: Can the action be undone? (1.0 = fully reversible like research, 0.0 = irreversible like sending email)
- verifiability: Can the outcome be objectively checked? (1.0 = fully verifiable)
- subjectivity: Does the task depend on personal judgment? (1.0 = very subjective)
- contextuality: How much does success depend on user-specific context? (1.0 = highly contextual)"""

        # Use PersonaBuilder as primary, fall back to task instructions only
        system_prompt: str | None = None
        if self.persona_builder is not None:
            try:
                from src.core.persona import PersonaRequest

                user_id = self.working.user_id
                request = PersonaRequest(
                    user_id=user_id,
                    agent_name="ooda_decide",
                    agent_role_description="ARIA's decision module",
                    task_description=f"Select action for goal: {goal.get('title', 'Unknown')[:80]}",
                    output_format="json",
                )
                ctx = await self.persona_builder.build(request)
                system_prompt = ctx.to_system_prompt() + "\n\n" + decide_task_instructions
            except Exception as e:
                logger.warning("PersonaBuilder failed in decide, using fallback: %s", e)

        if system_prompt is None:
            system_prompt = decide_task_instructions

        user_prompt = f"""Goal: {goal.get("title", "Unknown")}
Description: {goal.get("description", "No description")}

Analysis:
{orientation_summary}

Iteration: {state.iteration + 1} of {state.max_iterations}

Previous action result: {state.action_result if state.action_result else "No previous action"}

Select the best action to make progress toward the goal."""

        # Call LLM for decision — use extended thinking when user_id is set
        estimated_tokens = 0
        decision: dict[str, Any] | None = None
        response: str | None = None

        # Determine thinking effort dynamically: upgrade if orient found threats
        use_thinking = bool(self._user_id)
        decide_effort = "routine"
        threats = state.orientation.get("threats", [])
        if threats:
            decide_effort = "complex"

        if use_thinking and self._cost_governor:
            try:
                budget = await self._cost_governor.check_budget(self._user_id)  # type: ignore[arg-type]
                if not budget.can_proceed:
                    use_thinking = False
                else:
                    decide_effort = self._cost_governor.get_thinking_budget(budget, decide_effort)
            except Exception:
                use_thinking = False

        if use_thinking:
            try:
                llm_response = await self.llm.generate_response_with_thinking(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=self.config.decide_budget,
                    thinking_effort=decide_effort,
                    user_id=self._user_id,
                    task=TaskType.OODA_DECIDE,
                    agent_id="ooda",
                )
                response = llm_response.text
                if llm_response.thinking:
                    state.thinking_traces["decide"] = llm_response.thinking
                if llm_response.usage:
                    estimated_tokens = llm_response.usage.total_tokens
                else:
                    estimated_tokens = (len(system_prompt) + len(user_prompt) + len(response)) // 4
            except Exception as e:
                logger.error("Extended thinking failed in decide, falling back: %s", e)
                use_thinking = False

        if not use_thinking and response is None and decision is None:
            try:
                response = await self.llm.generate_response(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=self.config.decide_budget,
                    temperature=0.2,
                    task=TaskType.OODA_DECIDE,
                    agent_id="ooda",
                )
                input_chars = len(system_prompt) + len(user_prompt)
                output_chars = len(response)
                estimated_tokens = (input_chars + output_chars) // 4
            except Exception as e:
                logger.error(f"LLM call failed in decide phase: {e}")
                decision = {
                    "action": "blocked",
                    "agent": None,
                    "parameters": {},
                    "reasoning": f"Decision failed: {e}",
                    "error": str(e),
                }

        # Parse JSON response — try raw first, then extract from markdown fences
        if response is not None and decision is None:
            try:
                decision = json.loads(response)
            except json.JSONDecodeError:
                # Try extracting JSON from markdown code fences
                import re

                json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
                if json_match:
                    try:
                        decision = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass
                if decision is None:
                    # Try finding a JSON object in the response
                    brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)
                    if brace_match:
                        try:
                            decision = json.loads(brace_match.group(0))
                        except json.JSONDecodeError:
                            pass
                if decision is None:
                    logger.warning("Failed to parse LLM decision as JSON")
                    decision = {
                        "action": "blocked",
                        "agent": None,
                        "parameters": {},
                        "reasoning": "Failed to parse decision",
                        "raw_response": response[:500],
                    }

        if decision is None:
            decision = {
                "action": "blocked",
                "agent": None,
                "parameters": {},
                "reasoning": "No decision produced",
            }

        # Extract and apply TaskCharacteristics
        from src.core.task_characteristics import TaskCharacteristics

        raw_chars = decision.get("task_characteristics", {})
        if raw_chars and isinstance(raw_chars, dict):
            try:
                chars = TaskCharacteristics.from_dict(raw_chars)
            except Exception:
                action_name = decision.get("action", "research")
                chars = TaskCharacteristics.default_for_action(action_name)
        else:
            action_name = decision.get("action", "research")
            chars = TaskCharacteristics.default_for_action(action_name)

        state.task_characteristics = chars.to_dict()
        decision["risk_level"] = chars.risk_level
        decision["risk_score"] = chars.risk_score

        # --- Wave 2: Trust-aware approval level ---
        if self._trust_service and self._user_id:
            try:
                agent_name = decision.get("agent", "")
                action_category = self._agent_to_category(agent_name)
                approval_level_str = await self._trust_service.get_approval_level(
                    user_id=self._user_id,
                    action_category=action_category,
                    risk_score=chars.risk_score,
                )
                decision["approval_level"] = approval_level_str
                state.approval_level = approval_level_str
            except Exception as e:
                logger.warning("Trust lookup failed in decide (using risk-only): %s", e)
                decision["approval_level"] = chars.approval_level
                state.approval_level = chars.approval_level
        else:
            decision["approval_level"] = chars.approval_level
            state.approval_level = chars.approval_level

        # --- Wave 2: Mint DCT for the delegatee agent ---
        if self._dct_minter and decision.get("agent"):
            try:
                dct = self._dct_minter.mint(
                    delegatee=decision["agent"],
                    goal_id=state.goal_id,
                    time_limit=300,
                )
                dct_dict = dct.to_dict()
                decision["capability_token"] = dct_dict
                state.capability_token = dct_dict
            except Exception as e:
                logger.warning(
                    "DCT minting failed for agent %s: %s", decision.get("agent"), e
                )

        # Update state based on decision
        state.decision = decision

        if decision.get("action") == "complete":
            state.is_complete = True
        elif decision.get("action") == "blocked":
            state.is_blocked = True
            state.blocked_reason = decision.get("reasoning", "Unknown reason")
        else:
            state.current_phase = OODAPhase.ACT

        # Log phase execution
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        state.phase_logs.append(
            OODAPhaseLogEntry(
                phase=OODAPhase.DECIDE,
                iteration=state.iteration,
                input_summary=f"Focus: {state.orientation.get('recommended_focus', 'Unknown')}",
                output_summary=f"Decision: {decision.get('action', 'Unknown')}",
                tokens_used=estimated_tokens,
                duration_ms=duration_ms,
            )
        )

        logger.info(
            "OODA decide phase complete",
            extra={
                "goal_id": state.goal_id,
                "iteration": state.iteration,
                "action": decision.get("action"),
                "agent": decision.get("agent"),
                "duration_ms": duration_ms,
            },
        )

        return state

    async def act(
        self,
        state: OODAState,
        goal: dict[str, Any],
    ) -> OODAState:
        """Execute the decided action.

        Dispatches to the appropriate agent and records the result.
        Increments iteration and loops back to observe phase.

        Args:
            state: Current OODA state with decision.
            goal: The goal being pursued.

        Returns:
            Updated state with action result.
        """
        start_time = time.perf_counter()

        # Skip execution if goal is complete or blocked
        if state.is_complete or state.is_blocked:
            logger.info(
                "OODA act phase skipped",
                extra={
                    "goal_id": state.goal_id,
                    "is_complete": state.is_complete,
                    "is_blocked": state.is_blocked,
                },
            )
            return state

        decision = state.decision or {}
        action = decision.get("action", "unknown")
        agent = decision.get("agent")
        parameters = decision.get("parameters", {})

        # Handle resume_blocked_tasks action (from connection-aware Decide)
        if action == "resume_blocked_tasks":
            try:
                result = await self._resume_blocked_tasks(
                    goal_id=state.goal_id,
                    user_id=self._user_id or self.working.user_id,
                    resolved_capabilities=decision.get("resolved_capabilities", []),
                )
                state.action_result = result
            except Exception as e:
                logger.error("Failed to resume blocked tasks: %s", e)
                state.action_result = {"success": False, "error": str(e)}

            state.current_phase = OODAPhase.OBSERVE
            state.iteration += 1

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            state.phase_logs.append(
                OODAPhaseLogEntry(
                    phase=OODAPhase.ACT,
                    iteration=state.iteration - 1,
                    input_summary=f"Action: resume_blocked_tasks, resolved: {decision.get('resolved_capabilities', [])}",
                    output_summary=f"Resumed: {state.action_result.get('resumed_count', 0) if isinstance(state.action_result, dict) else 0}",
                    tokens_used=0,
                    duration_ms=duration_ms,
                )
            )
            return state

        # Execute action via agent executor
        try:
            if hasattr(self, "agent_executor") and self.agent_executor:
                result = await self.agent_executor(
                    action=action,
                    agent=agent,
                    parameters=parameters,
                    goal=goal,
                    capability_token=state.capability_token,
                    approval_level=state.approval_level,
                )
                state.action_result = result
            else:
                # No agent executor configured - record as pending
                state.action_result = {
                    "success": False,
                    "pending": True,
                    "message": "Agent executor not configured",
                    "action": action,
                    "agent": agent,
                }

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            state.action_result = {
                "success": False,
                "error": str(e),
                "action": action,
                "agent": agent,
            }

        # Loop back to observe phase and increment iteration
        state.current_phase = OODAPhase.OBSERVE
        state.iteration += 1

        # Estimate tokens based on action result size
        # Rough estimate: 4 characters per token
        result_str = str(state.action_result) if state.action_result else ""
        estimated_tokens = len(result_str) // 4

        # Log phase execution
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        success = state.action_result.get("success", False) if state.action_result else False
        state.phase_logs.append(
            OODAPhaseLogEntry(
                phase=OODAPhase.ACT,
                iteration=state.iteration - 1,  # Log for previous iteration
                input_summary=f"Action: {action}, Agent: {agent}",
                output_summary=f"Success: {success}",
                tokens_used=estimated_tokens,
                duration_ms=duration_ms,
            )
        )

        logger.info(
            "OODA act phase complete",
            extra={
                "goal_id": state.goal_id,
                "iteration": state.iteration,
                "action": action,
                "agent": agent,
                "success": success,
                "duration_ms": duration_ms,
            },
        )

        return state

    async def _resume_blocked_tasks(
        self,
        goal_id: str,
        user_id: str,
        resolved_capabilities: list[str],
    ) -> dict[str, Any]:
        """Resume tasks that were blocked by missing tool connections.

        Finds blocked goal_agents for this goal, updates their status,
        triggers re-execution via GoalExecutionService, updates the goal
        config to remove resolved gaps, and notifies the user.

        Args:
            goal_id: Goal with blocked tasks.
            user_id: Goal owner.
            resolved_capabilities: Capabilities that are now available.

        Returns:
            Act result dict with status and resumed_count.
        """
        from src.db.supabase import SupabaseClient

        try:
            client = SupabaseClient.get_client()

            # Find blocked goal_agents for this goal
            blocked_agents = (
                client.table("goal_agents")
                .select("id, agent_type, agent_config")
                .eq("goal_id", goal_id)
                .eq("status", "blocked")
                .execute()
            )

            blocked_for_goal = blocked_agents.data or []

            if not blocked_for_goal:
                logger.info("OODA Act: No blocked tasks found for goal %s", goal_id)
                return {"status": "no_blocked_tasks", "resumed_count": 0}

            # Resume blocked tasks whose blocking capability is now resolved
            resumed_count = 0
            for agent_row in blocked_for_goal:
                agent_config = agent_row.get("agent_config", {}) or {}
                blocked_by = agent_config.get("blocked_by")

                # If blocked_by is specified, check if it's in resolved list
                if blocked_by and blocked_by not in resolved_capabilities:
                    continue

                # Update status to 'running'
                client.table("goal_agents").update({
                    "status": "running",
                }).eq("id", agent_row["id"]).execute()

                resumed_count += 1

            # Trigger re-execution through GoalExecutionService
            if resumed_count > 0:
                try:
                    from src.services.goal_execution import GoalExecutionService

                    execution_service = GoalExecutionService()
                    await execution_service.resume_blocked_tasks(
                        goal_id=goal_id,
                        user_id=user_id,
                        resolved_capabilities=resolved_capabilities,
                    )
                except Exception as e:
                    logger.warning(
                        "GoalExecutionService.resume_blocked_tasks failed: %s", e
                    )

            # Update goal config — remove resolved gaps
            try:
                goal_result = (
                    client.table("goals")
                    .select("config")
                    .eq("id", goal_id)
                    .maybe_single()
                    .execute()
                )
                if goal_result.data:
                    config = goal_result.data.get("config", {}) or {}
                    gaps = config.get("capability_gaps", [])
                    updated_gaps = [
                        g for g in gaps
                        if (isinstance(g, dict) and g.get("capability") not in resolved_capabilities)
                        or (isinstance(g, str) and g not in resolved_capabilities)
                    ]
                    config["capability_gaps"] = updated_gaps
                    config["last_gap_resolution"] = datetime.now(UTC).isoformat()
                    client.table("goals").update({"config": config}).eq("id", goal_id).execute()
            except Exception as e:
                logger.warning("Failed to update goal gaps: %s", e)

            # Notify user via WebSocket
            try:
                from src.core.ws import ws_manager

                await ws_manager.send_to_user(user_id, {
                    "type": "goal.tasks_resumed",
                    "goal_id": goal_id,
                    "resumed_count": resumed_count,
                    "resolved_capabilities": resolved_capabilities,
                    "message": (
                        f"Great news! {resumed_count} previously blocked task(s) "
                        f"can now proceed with your new tool connections."
                    ),
                })
            except Exception:
                pass  # User may not be connected

            logger.info(
                "OODA Act: Resumed %d blocked tasks for goal %s. "
                "Resolved capabilities: %s",
                resumed_count, goal_id, resolved_capabilities,
            )

            return {
                "status": "tasks_resumed",
                "resumed_count": resumed_count,
                "resolved_capabilities": resolved_capabilities,
            }

        except Exception as e:
            logger.error("Failed to resume blocked tasks for goal %s: %s", goal_id, e)
            return {"status": "error", "message": str(e), "resumed_count": 0}

    async def run(self, goal: str) -> OODAState:
        """Execute OODA loop until goal achieved, blocked, or limit exceeded.

        Runs full OODA cycles (observe -> orient -> decide -> act) until:
        - Goal is complete (state.is_complete is True)
        - Goal is blocked (raises OODABlockedError)
        - Max iterations exceeded (raises OODAMaxIterationsError)
        - Token budget exceeded (raises OODAMaxIterationsError)

        Args:
            goal: The goal description to achieve.

        Returns:
            Final OODAState on successful completion.

        Raises:
            OODABlockedError: When the loop cannot proceed.
            OODAMaxIterationsError: When iterations or token budget exceeded.
        """
        # Generate a unique goal ID for this run
        goal_id = str(uuid.uuid4())
        cycle_id = uuid.uuid4()

        # Create initial state
        state = OODAState(
            goal_id=goal_id,
            max_iterations=self.config.max_iterations,
        )

        # Build goal dict for phase methods
        goal_dict = {"id": goal_id, "title": goal, "description": goal}

        logger.info(
            "OODA loop starting",
            extra={
                "goal_id": goal_id,
                "cycle_id": str(cycle_id),
                "goal": goal,
                "max_iterations": self.config.max_iterations,
                "total_budget": self.config.total_budget,
            },
        )

        while True:
            # Check iteration limit before starting cycle
            if state.iteration >= self.config.max_iterations:
                logger.warning(
                    "OODA loop max iterations exceeded",
                    extra={
                        "goal_id": goal_id,
                        "iterations": state.iteration,
                    },
                )
                if self._ooda_logger:
                    with contextlib.suppress(Exception):
                        await self._ooda_logger.mark_cycle_complete(cycle_id=cycle_id)
                raise OODAMaxIterationsError(
                    goal_id=goal_id,
                    iterations=state.iteration,
                )

            # Check token budget
            if state.total_tokens_used >= self.config.total_budget:
                logger.warning(
                    "OODA loop token budget exceeded",
                    extra={
                        "goal_id": goal_id,
                        "tokens_used": state.total_tokens_used,
                        "budget": self.config.total_budget,
                    },
                )
                if self._ooda_logger:
                    with contextlib.suppress(Exception):
                        await self._ooda_logger.mark_cycle_complete(cycle_id=cycle_id)
                raise OODAMaxIterationsError(
                    goal_id=goal_id,
                    iterations=state.iteration,
                )

            logger.info(
                "OODA loop iteration starting",
                extra={
                    "goal_id": goal_id,
                    "iteration": state.iteration,
                    "tokens_used": state.total_tokens_used,
                },
            )

            # Execute OODA cycle: observe -> orient -> decide -> act
            state = await self.observe(state, goal_dict)
            self._update_token_count(state)
            await self._log_phase(cycle_id, state, "observe")

            state = await self.orient(state, goal_dict)
            self._update_token_count(state)
            await self._log_phase(cycle_id, state, "orient")

            state = await self.decide(state, goal_dict)
            self._update_token_count(state)
            await self._log_phase(cycle_id, state, "decide")

            # Check if blocked after decide
            if state.is_blocked:
                logger.warning(
                    "OODA loop blocked",
                    extra={
                        "goal_id": goal_id,
                        "reason": state.blocked_reason,
                    },
                )
                if self._ooda_logger:
                    with contextlib.suppress(Exception):
                        await self._ooda_logger.mark_cycle_complete(cycle_id=cycle_id)
                raise OODABlockedError(
                    goal_id=goal_id,
                    reason=state.blocked_reason or "Unknown reason",
                )

            # Check if complete after decide
            if state.is_complete:
                logger.info(
                    "OODA loop completed successfully",
                    extra={
                        "goal_id": goal_id,
                        "iterations": state.iteration,
                        "tokens_used": state.total_tokens_used,
                    },
                )
                if self._ooda_logger:
                    with contextlib.suppress(Exception):
                        await self._ooda_logger.mark_cycle_complete(cycle_id=cycle_id)
                return state

            # Execute action (only if not complete/blocked)
            state = await self.act(state, goal_dict)
            self._update_token_count(state)
            await self._log_phase(cycle_id, state, "act")

            logger.info(
                "OODA loop iteration complete",
                extra={
                    "goal_id": goal_id,
                    "iteration": state.iteration,
                    "tokens_used": state.total_tokens_used,
                },
            )

    async def run_single_iteration(
        self,
        state: OODAState,
        goal: dict[str, Any],
    ) -> OODAState:
        """Run exactly one OODA cycle (observe → orient → decide → act).

        Used by the scheduler to monitor goals at intervals without
        running the full loop. Returns updated state for the caller
        to interpret and act upon.

        Args:
            state: Current OODA state (may be from a previous iteration).
            goal: The goal dict being monitored.

        Returns:
            Updated OODAState after one full cycle.
        """
        cycle_id = uuid.uuid4()
        logger.info(
            "OODA single iteration starting",
            extra={
                "goal_id": state.goal_id,
                "iteration": state.iteration,
                "cycle_id": str(cycle_id),
            },
        )

        state = await self.observe(state, goal)
        self._update_token_count(state)
        await self._log_phase(cycle_id, state, "observe")

        state = await self.orient(state, goal)
        self._update_token_count(state)
        await self._log_phase(cycle_id, state, "orient")

        state = await self.decide(state, goal)
        self._update_token_count(state)
        await self._log_phase(cycle_id, state, "decide")

        # Only act if not complete/blocked
        if not state.is_complete and not state.is_blocked:
            state = await self.act(state, goal)
            self._update_token_count(state)
            await self._log_phase(cycle_id, state, "act")

        # Mark cycle complete
        if self._ooda_logger:
            with contextlib.suppress(Exception):
                await self._ooda_logger.mark_cycle_complete(cycle_id=cycle_id)

        logger.info(
            "OODA single iteration complete",
            extra={
                "goal_id": state.goal_id,
                "iteration": state.iteration,
                "is_complete": state.is_complete,
                "is_blocked": state.is_blocked,
                "decision": state.decision.get("action") if state.decision else None,
            },
        )

        return state

    def _update_token_count(self, state: OODAState) -> None:
        """Update total token count from phase logs.

        Args:
            state: The current OODA state.
        """
        state.total_tokens_used = sum(log.tokens_used for log in state.phase_logs)

    async def _log_phase(
        self,
        cycle_id: uuid.UUID,
        state: OODAState,
        phase: str,
    ) -> None:
        """Persist the latest phase log entry via OODALogger (fail-open).

        Args:
            cycle_id: UUID grouping this OODA run.
            state: Current OODA state (reads the last phase_log entry).
            phase: Phase name (observe/orient/decide/act).
        """
        if not self._ooda_logger:
            return
        try:
            log_entry = state.phase_logs[-1] if state.phase_logs else None
            agents: list[str] | None = None
            if phase == "act" and state.decision:
                agent = state.decision.get("agent")
                if agent:
                    agents = [agent]

            await self._ooda_logger.log_phase(
                cycle_id=cycle_id,
                goal_id=state.goal_id,
                user_id=self._user_id or "",
                phase=phase,
                iteration=state.iteration,
                input_summary=log_entry.input_summary if log_entry else "",
                output_summary=log_entry.output_summary if log_entry else "",
                tokens_used=log_entry.tokens_used if log_entry else 0,
                duration_ms=log_entry.duration_ms if log_entry else 0,
                thinking_effort=self._get_thinking_effort(phase, state),
                agents_dispatched=agents,
            )
        except Exception:
            logger.warning("Failed to persist OODA phase %s", phase, exc_info=True)

    def _get_thinking_effort(self, phase: str, state: OODAState) -> str | None:
        """Determine thinking effort used for a phase.

        Args:
            phase: The OODA phase name.
            state: Current state with task characteristics.

        Returns:
            Thinking effort level or None if not applicable.
        """
        if phase == "orient":
            return "complex"
        if phase == "decide" and state.task_characteristics:
            risk = state.task_characteristics.get("risk_score", 0)
            if risk > 0.7:
                return "critical"
            if risk > 0.4:
                return "complex"
            return "routine"
        return None
