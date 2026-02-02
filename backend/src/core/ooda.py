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

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.memory.episodic import EpisodicMemory
    from src.memory.semantic import SemanticMemory
    from src.memory.working import WorkingMemory

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
    ) -> None:
        """Initialize OODA loop.

        Args:
            llm_client: LLM client for reasoning.
            episodic_memory: Episodic memory service.
            semantic_memory: Semantic memory service.
            working_memory: Working memory for current context.
            config: Optional configuration for budgets.
        """
        self.llm = llm_client
        self.episodic = episodic_memory
        self.semantic = semantic_memory
        self.working = working_memory
        self.config = config or OODAConfig()

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

        # Get user_id from working memory
        user_id = self.working.user_id

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

        # Log phase execution
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        state.phase_logs.append(
            OODAPhaseLogEntry(
                phase=OODAPhase.OBSERVE,
                iteration=state.iteration,
                input_summary=f"Goal: {goal.get('title', 'Unknown')}",
                output_summary=f"Gathered {len(observations)} observations",
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

        system_prompt = """You are ARIA's cognitive analysis module. Analyze the observations and produce a structured analysis.

Output ONLY valid JSON with this structure:
{
    "patterns": ["list of patterns identified"],
    "opportunities": ["list of opportunities to pursue the goal"],
    "threats": ["list of obstacles or risks"],
    "recommended_focus": "single most important area to focus on"
}"""

        user_prompt = f"""Goal: {goal.get("title", "Unknown")}
Description: {goal.get("description", "No description")}

Observations:
{observations_summary}

Analyze these observations and identify patterns, opportunities, and threats relevant to achieving the goal."""

        # Call LLM for analysis
        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                max_tokens=self.config.orient_budget,
                temperature=0.3,  # Lower temperature for more focused analysis
            )

            # Parse JSON response
            try:
                orientation = json.loads(response)
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON, using default orientation")
                orientation = {
                    "patterns": [],
                    "opportunities": [],
                    "threats": [],
                    "recommended_focus": "Unable to analyze - proceeding with default strategy",
                    "raw_response": response,
                }

        except Exception as e:
            logger.error(f"LLM call failed in orient phase: {e}")
            orientation = {
                "patterns": [],
                "opportunities": [],
                "threats": [],
                "recommended_focus": "LLM analysis failed - proceeding cautiously",
                "error": str(e),
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

        return state

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

        # Build prompt for decision
        orientation_summary = json.dumps(state.orientation, indent=2, default=str)

        system_prompt = """You are ARIA's decision module. Based on the analysis, select the best action to take.

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
    "reasoning": "why this action was chosen"
}"""

        user_prompt = f"""Goal: {goal.get('title', 'Unknown')}
Description: {goal.get('description', 'No description')}

Analysis:
{orientation_summary}

Iteration: {state.iteration + 1} of {state.max_iterations}

Previous action result: {state.action_result if state.action_result else 'No previous action'}

Select the best action to make progress toward the goal."""

        # Call LLM for decision
        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                max_tokens=self.config.decide_budget,
                temperature=0.2,  # Low temperature for more deterministic decisions
            )

            # Parse JSON response
            try:
                decision = json.loads(response)
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM decision as JSON")
                decision = {
                    "action": "blocked",
                    "agent": None,
                    "parameters": {},
                    "reasoning": "Failed to parse decision",
                    "raw_response": response,
                }

        except Exception as e:
            logger.error(f"LLM call failed in decide phase: {e}")
            decision = {
                "action": "blocked",
                "agent": None,
                "parameters": {},
                "reasoning": f"Decision failed: {e}",
                "error": str(e),
            }

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
