"""Skill-aware agent base class for ARIA.

Extends BaseAgent with skills.sh integration, enabling agents to
discover and execute skills as part of their OODA ACT phase.
"""

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class SkillAnalysis:
    """Result of analyzing whether skills are needed for a task.

    Attributes:
        skills_needed: Whether any skills should be invoked.
        recommended_skills: List of skill paths to use.
        reasoning: LLM explanation of the decision.
    """

    skills_needed: bool
    recommended_skills: list[str]
    reasoning: str


# Maps agent_id to the skill paths that agent is authorized to use.
AGENT_SKILLS: dict[str, list[str]] = {
    "hunter": [
        "competitor-analysis",
        "lead-research",
        "company-profiling",
    ],
    "analyst": [
        "clinical-trial-analysis",
        "pubmed-research",
        "data-visualization",
    ],
    "strategist": [
        "market-analysis",
        "competitive-positioning",
        "pricing-strategy",
    ],
    "scribe": [
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "email-sequence",
    ],
    "operator": [
        "calendar-management",
        "crm-operations",
        "workflow-automation",
    ],
    "scout": [
        "regulatory-monitor",
        "news-aggregation",
        "signal-detection",
    ],
}


class SkillAwareAgent(BaseAgent):
    """Base class for agents that can discover and execute skills.

    Extends BaseAgent with:
    - A SkillOrchestrator for multi-skill execution
    - A SkillIndex for skill discovery
    - An agent_id that maps to AGENT_SKILLS for skill authorization
    - LLM-based skill need analysis
    - execute_with_skills() for skill-augmented task execution

    Subclasses must set the `agent_id` class attribute to one of the
    keys in AGENT_SKILLS.
    """

    agent_id: str

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        """Initialize the skill-aware agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
        """
        self.skill_orchestrator = skill_orchestrator
        self.skill_index = skill_index
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _get_available_skills(self) -> list[str]:
        """Get the list of skills this agent is authorized to use.

        Returns:
            List of skill path strings from AGENT_SKILLS, or empty list
            if the agent_id is not in the mapping.
        """
        return AGENT_SKILLS.get(self.agent_id, [])

    async def _analyze_skill_needs(self, task: dict[str, Any]) -> SkillAnalysis:
        """Use LLM to determine if skills would help with a task.

        Sends the task description and available skills to the LLM,
        which returns a JSON response indicating whether skills are needed.

        Args:
            task: Task specification to analyze.

        Returns:
            SkillAnalysis with skills_needed, recommended_skills, reasoning.
            On error, returns SkillAnalysis with skills_needed=False.
        """
        available_skills = self._get_available_skills()

        if not available_skills:
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning="No skills available for this agent",
            )

        prompt = (
            "You are analyzing whether external skills should be used for a task.\n\n"
            f"Agent: {self.name} ({self.description})\n"
            f"Available skills: {', '.join(available_skills)}\n\n"
            f"Task: {json.dumps(task, default=str)}\n\n"
            "Respond with JSON only:\n"
            '{"skills_needed": bool, "recommended_skills": ["skill-name", ...], '
            '"reasoning": "explanation"}\n\n'
            "Only recommend skills from the available list. "
            "Set skills_needed to false if the agent's built-in tools suffice."
        )

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.0,
            )

            parsed = json.loads(response)

            # Filter recommended skills to only those available
            recommended = [
                s for s in parsed.get("recommended_skills", []) if s in available_skills
            ]

            # If filtering removed all skills, mark as not needed
            skills_needed = parsed.get("skills_needed", False) and len(recommended) > 0

            return SkillAnalysis(
                skills_needed=skills_needed,
                recommended_skills=recommended,
                reasoning=parsed.get("reasoning", ""),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse skill analysis response: {e}")
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning=f"Failed to parse LLM response: {e}",
            )
        except Exception as e:
            logger.error(f"Skill analysis failed: {e}")
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning=f"Skill analysis error: {e}",
            )

    async def execute_with_skills(self, task: dict[str, Any]) -> AgentResult:
        """Execute a task, using skills if beneficial.

        This is the OODA ACT phase integration point. Analyzes whether
        skills would help, and if so, delegates to the SkillOrchestrator.
        Falls back to the agent's native execute() if skills aren't needed
        or aren't available.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with execution outcome.
        """
        # Step 1: Analyze if skills would help
        analysis = await self._analyze_skill_needs(task)

        if not analysis.skills_needed:
            logger.info(
                f"Agent {self.name}: no skills needed, using native execution",
                extra={"agent_id": self.agent_id, "reasoning": analysis.reasoning},
            )
            return await self.execute(task)

        # Step 2: Check if orchestrator is available
        if self.skill_orchestrator is None or self.skill_index is None:
            logger.warning(
                f"Agent {self.name}: skills recommended but no orchestrator available, "
                "falling back to native execution",
                extra={
                    "agent_id": self.agent_id,
                    "recommended_skills": analysis.recommended_skills,
                },
            )
            return await self.execute(task)

        # Step 3: Find skill metadata from index
        try:
            available_skill_entries = await self.skill_index.search(
                query=" ".join(analysis.recommended_skills),
            )

            # Build task description for orchestrator
            task_description = json.dumps(task, default=str)

            # Step 4: Create execution plan
            plan = await self.skill_orchestrator.create_execution_plan(
                task=task_description,
                available_skills=available_skill_entries,
            )

            logger.info(
                f"Agent {self.name}: executing skill plan with {len(plan.steps)} steps",
                extra={
                    "agent_id": self.agent_id,
                    "plan_id": plan.plan_id,
                    "step_count": len(plan.steps),
                },
            )

            # Step 5: Execute the plan
            working_memory = await self.skill_orchestrator.execute_plan(
                user_id=self.user_id,
                plan=plan,
            )

            # Step 6: Build result from working memory
            skill_outputs = []
            all_succeeded = True
            for entry in working_memory:
                skill_outputs.append({
                    "step": entry.step_number,
                    "skill_id": entry.skill_id,
                    "status": entry.status,
                    "summary": entry.summary,
                    "artifacts": entry.artifacts,
                })
                if entry.status != "completed":
                    all_succeeded = False

            return AgentResult(
                success=all_succeeded,
                data={
                    "skill_execution": True,
                    "plan_id": plan.plan_id,
                    "steps": skill_outputs,
                },
                error=None if all_succeeded else "One or more skill steps failed",
            )

        except Exception as e:
            logger.error(
                f"Agent {self.name}: skill execution failed: {e}",
                extra={"agent_id": self.agent_id, "error": str(e)},
            )
            return AgentResult(
                success=False,
                data=None,
                error=f"Skill execution failed: {e}",
            )
