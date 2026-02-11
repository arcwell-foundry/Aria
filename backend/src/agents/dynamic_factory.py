"""Dynamic agent factory for creating agents at runtime.

Creates SkillAwareAgent subclasses on-the-fly from goal context,
required capabilities, and task descriptions. Used when the 6 core
agents don't cover a specialized need (e.g., BoardPrepAgent,
DueDiligenceAgent, EventPlanningAgent).
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import AGENT_SKILLS, SkillAwareAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class DynamicAgentSpec:
    """Specification for creating a dynamic agent.

    Attributes:
        name: Agent class name (e.g., "BoardPrepAgent").
        description: What this agent does.
        goal_context: The goal it's working toward.
        required_capabilities: Capability tags (e.g., ["research", "document_generation"]).
        task_description: Specific task description.
        skill_access: Skill paths this agent is authorized to use.
    """

    name: str
    description: str
    goal_context: str
    required_capabilities: list[str] = field(default_factory=list)
    task_description: str = ""
    skill_access: list[str] = field(default_factory=list)


class DynamicAgentFactory:
    """Creates SkillAwareAgent subclasses at runtime.

    Given a DynamicAgentSpec, produces a new class extending
    SkillAwareAgent with a generated system prompt and configured
    skill access. Agents can be instantiated and used with the
    existing AgentOrchestrator.
    """

    def _build_system_prompt(self, spec: DynamicAgentSpec) -> str:
        """Build a focused system prompt for the dynamic agent.

        Args:
            spec: The agent specification.

        Returns:
            System prompt string for the agent's LLM calls.
        """
        return (
            f"You are {spec.name}, a specialized ARIA agent.\n\n"
            f"Role: {spec.description}\n\n"
            f"Current Goal: {spec.goal_context}\n\n"
            f"Capabilities: {', '.join(spec.required_capabilities)}\n\n"
            "You are part of ARIA, an AI Department Director for life sciences "
            "commercial teams. Be specific, actionable, and data-driven. "
            "Structure your output as JSON when possible."
        )

    def create_agent_class(self, spec: DynamicAgentSpec) -> type[SkillAwareAgent]:
        """Create a new SkillAwareAgent subclass from a spec.

        Dynamically constructs a class using Python's type() with the
        correct class attributes and method overrides.

        Args:
            spec: The agent specification.

        Returns:
            A new class that extends SkillAwareAgent.
        """
        agent_id = f"dynamic_{spec.name}"
        system_prompt = self._build_system_prompt(spec)

        # Register skill access for this dynamic agent
        AGENT_SKILLS[agent_id] = list(spec.skill_access)

        def _register_tools(self: Any) -> dict[str, Callable[..., Any]]:  # noqa: ARG001
            return {}

        async def execute(self: Any, task: dict[str, Any]) -> AgentResult:
            """Execute task using LLM with the generated system prompt."""
            task_str = json.dumps(task, default=str)
            prompt = (
                f"Task: {spec.task_description}\n\n"
                f"Input: {task_str}\n\n"
                "Analyze the input and produce a structured response. "
                "Respond with JSON."
            )
            try:
                response = await self.llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=system_prompt,
                    max_tokens=2048,
                    temperature=0.3,
                )
                try:
                    data = json.loads(response)
                except json.JSONDecodeError:
                    data = {"raw_response": response.strip()}

                return AgentResult(success=True, data=data)
            except Exception as e:
                logger.error(
                    "Dynamic agent execution failed",
                    extra={"agent": spec.name, "error": str(e)},
                )
                return AgentResult(success=False, data=None, error=str(e))

        # Create the class dynamically
        agent_cls = type(
            spec.name,
            (SkillAwareAgent,),
            {
                "name": spec.name,
                "description": spec.description,
                "agent_id": agent_id,
                "_register_tools": _register_tools,
                "execute": execute,
            },
        )

        logger.info(
            "Created dynamic agent class",
            extra={
                "agent_name": spec.name,
                "agent_id": agent_id,
                "capabilities": spec.required_capabilities,
                "skill_access": spec.skill_access,
            },
        )

        return agent_cls

    def create_agent(
        self,
        spec: DynamicAgentSpec,
        llm_client: "LLMClient",
        user_id: str,
    ) -> SkillAwareAgent:
        """Create and instantiate a dynamic agent from a spec.

        Args:
            spec: The agent specification.
            llm_client: LLM client for agent reasoning.
            user_id: ID of the user this agent works for.

        Returns:
            Instantiated SkillAwareAgent subclass.
        """
        agent_cls = self.create_agent_class(spec)
        return agent_cls(llm_client=llm_client, user_id=user_id)

    async def log_to_procedural_memory(
        self,
        spec: DynamicAgentSpec,
        user_id: str,
    ) -> None:
        """Log the dynamic agent pattern to procedural memory for reuse.

        Stores the agent spec so future similar goals can reuse the
        same agent configuration.

        Args:
            spec: The agent specification to log.
            user_id: The user who triggered creation.
        """
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
            db.table("procedural_memories").insert(
                {
                    "user_id": user_id,
                    "procedure_type": "dynamic_agent",
                    "trigger_pattern": spec.goal_context,
                    "procedure": {
                        "name": spec.name,
                        "description": spec.description,
                        "capabilities": spec.required_capabilities,
                        "skill_access": spec.skill_access,
                        "task_description": spec.task_description,
                    },
                    "success_count": 1,
                    "source": "dynamic_agent_factory",
                }
            ).execute()
            logger.info(
                "Logged dynamic agent to procedural memory",
                extra={"agent_name": spec.name, "user_id": user_id},
            )
        except Exception as e:
            logger.warning("Failed to log dynamic agent to procedural memory: %s", e)
