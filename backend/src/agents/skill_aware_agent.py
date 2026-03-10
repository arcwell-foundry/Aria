"""Skill-aware agent base class for ARIA.

Extends BaseAgent with skills integration, enabling agents to
discover and execute skills as part of their OODA ACT phase.

Enhancement 5 (Conversational Invocation): Detects if a task is simple
(single service call → bypass orchestrator) vs complex (needs multi-skill
orchestration). Simple tasks execute directly; complex tasks use the full
SkillOrchestrator DAG pipeline.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.core.task_types import TaskType

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.core.persona import PersonaBuilder
    from src.memory.cold_retrieval import ColdMemoryRetriever
    from src.memory.hot_context import HotContextBuilder
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
        is_simple: True if 0-1 skills (bypass orchestrator), False if multi-skill.
    """

    skills_needed: bool
    recommended_skills: list[str]
    reasoning: str
    is_simple: bool = True


# Maps agent_id to the skill paths that agent is authorized to use.
# These MUST match skill_path values in the skills_index table.
AGENT_SKILLS: dict[str, list[str]] = {
    "hunter": [
        "aria:capability/contact-enricher",
        "aria:capability/linkedin-intelligence",
    ],
    "analyst": [
        "aria:skill_definition/financial-intel",
        "aria:skill_definition/insight-visualizer",
        "aria:skill_definition/kol-mapper",
        "aria:skill_definition/trial-radar",
        "aria:capability/mcp-evaluator",
    ],
    "strategist": [
        "aria:skill_definition/battle-card-generator",
        "aria:skill_definition/roi-calculator",
        "aria:skill_definition/territory-planner",
    ],
    "scribe": [
        "aria:skill_definition/document-forge",
        "aria:skill_definition/deck-builder",
        "aria:skill_definition/compliance-guardian",
        "aria:skill_definition/email-sequence-builder",
        "aria:capability/email-intelligence",
        "aria:capability/compliance",
    ],
    "operator": [
        "aria:capability/calendar-intelligence",
        "aria:capability/crm-deep-sync",
        "aria:capability/meeting-intelligence",
        "aria:capability/team-messenger",
    ],
    "scout": [
        "aria:capability/web-intelligence",
        "aria:capability/signal-radar",
        "aria:capability/mcp-discovery",
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

    Enhancement 5 (Conversational Invocation):
    - Simple tasks (0-1 skills) bypass the orchestrator
    - Complex tasks (2+ skills) use full DAG orchestration
    - All skill decisions are logged to aria_activity

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
        persona_builder: "PersonaBuilder | None" = None,
        hot_context_builder: "HotContextBuilder | None" = None,
        cold_retriever: "ColdMemoryRetriever | None" = None,
    ) -> None:
        """Initialize the skill-aware agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
            persona_builder: Optional PersonaBuilder for centralized prompt assembly.
            hot_context_builder: Optional builder for always-loaded context.
            cold_retriever: Optional retriever for on-demand deep memory search.
        """
        self.skill_orchestrator = skill_orchestrator
        self.skill_index = skill_index
        self._last_skill_analysis: SkillAnalysis | None = None
        self._core_skills_installed: bool = False
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            persona_builder=persona_builder,
            hot_context_builder=hot_context_builder,
            cold_retriever=cold_retriever,
        )

    def _get_available_skills(self) -> list[str]:
        """Get the list of skills this agent is authorized to use.

        Returns:
            List of skill path strings from AGENT_SKILLS, or empty list
            if the agent_id is not in the mapping.
        """
        return AGENT_SKILLS.get(self.agent_id, [])

    async def _ensure_core_skills_installed(self) -> None:
        """Auto-install all core trust_level skills for the current user.

        Called once per agent lifetime (cached via _core_skills_installed flag).
        Populates the user_skills table so skill execution tracking works.
        """
        if self._core_skills_installed:
            return
        self._core_skills_installed = True

        if self.skill_index is None:
            return

        try:
            from src.security.trust_levels import SkillTrustLevel
            from src.skills.installer import SkillInstaller

            installer = SkillInstaller()

            # Find all core-trust skills in the index
            core_skills = await self.skill_index.search(
                query="",
                trust_level=SkillTrustLevel.CORE,
                limit=100,
            )

            if not core_skills:
                return

            installed_count = 0
            for skill in core_skills:
                already = await installer.is_installed(self.user_id, skill.id)
                if not already:
                    try:
                        await installer.install(
                            user_id=self.user_id,
                            skill_id=skill.id,
                            auto_installed=True,
                        )
                        installed_count += 1
                    except Exception as e:
                        logger.debug(
                            "Failed to auto-install skill %s: %s",
                            skill.skill_path, e,
                        )

            if installed_count > 0:
                logger.info(
                    "Auto-installed %d core skills for user %s",
                    installed_count, self.user_id,
                )
        except Exception as e:
            logger.warning("Core skills auto-install failed (non-fatal): %s", e)

    async def _analyze_skill_needs(self, task: dict[str, Any]) -> SkillAnalysis:
        """Use LLM to determine if skills would help with a task.

        Sends the task description and available skills to the LLM,
        which returns a JSON response indicating whether skills are needed.

        Args:
            task: Task specification to analyze.

        Returns:
            SkillAnalysis with skills_needed, recommended_skills, reasoning,
            and is_simple classification.
            On error, returns SkillAnalysis with skills_needed=False.
        """
        available_skills = self._get_available_skills()

        if not available_skills:
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning="No skills available for this agent",
                is_simple=True,
            )

        prompt = (
            "You are analyzing whether external skills should be used for a task.\n\n"
            f"Agent: {self.name} ({self.description})\n"
            f"Available skills: {', '.join(available_skills)}\n\n"
            f"Task: {json.dumps(task, default=str)}\n\n"
            "Only recommend skills from the available list. "
            "Set skills_needed to false if the agent's built-in tools suffice.\n\n"
            "Respond with ONLY valid JSON, no markdown, no explanation:\n"
            '{"skills_needed": true, "recommended_skills": ["skill-name"], "reasoning": "why"}'
        )

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.0,
                task=TaskType.SKILL_EXECUTE,
                agent_id="skill_aware_agent",
            )

            # Guard against empty/None responses
            if not response or not response.strip():
                logger.warning(
                    "Skill analysis returned empty response, defaulting to native execution"
                )
                return SkillAnalysis(
                    skills_needed=False,
                    recommended_skills=[],
                    reasoning="LLM returned empty response, defaulting to native",
                    is_simple=True,
                )

            # Strip markdown code fences if present (```json ... ```)
            cleaned = response.strip()
            fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
            fence_match = re.search(fence_pattern, cleaned, re.DOTALL)
            if fence_match:
                cleaned = fence_match.group(1).strip()

            parsed = json.loads(cleaned)

            # Filter recommended skills to only those available
            recommended = [s for s in parsed.get("recommended_skills", []) if s in available_skills]

            # If filtering removed all skills, mark as not needed
            skills_needed = parsed.get("skills_needed", False) and len(recommended) > 0
            is_simple = len(recommended) <= 1

            return SkillAnalysis(
                skills_needed=skills_needed,
                recommended_skills=recommended,
                reasoning=parsed.get("reasoning", ""),
                is_simple=is_simple,
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Log the actual raw response so we can diagnose the format issue
            raw_preview = (response or "")[:500]
            logger.warning(
                "Failed to parse skill analysis response: %s | raw response: %s",
                e,
                raw_preview,
            )
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning=f"Failed to parse LLM response: {e}",
                is_simple=True,
            )
        except Exception as e:
            logger.error(f"Skill analysis failed: {e}")
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning=f"Skill analysis error: {e}",
                is_simple=True,
            )

    async def _log_skill_decision(
        self,
        task: dict[str, Any],
        analysis: SkillAnalysis,
        execution_path: str,
    ) -> None:
        """Log skill routing decision to aria_activity.

        Records the skill analysis result and chosen execution path
        for audit trail and transparency.

        Args:
            task: The task that was analyzed.
            analysis: The skill analysis result.
            execution_path: Which path was chosen (native, simple_skill, orchestrator).
        """
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            await activity.record(
                user_id=self.user_id,
                agent=self.agent_id,
                activity_type="skill_decision",
                title=f"{self.name} evaluated skill routing",
                description=(
                    f"Skills needed: {analysis.skills_needed}. "
                    f"Recommended: {', '.join(analysis.recommended_skills) or 'none'}. "
                    f"Path: {execution_path}. "
                    f"Reasoning: {analysis.reasoning}"
                ),
                confidence=0.9,
                metadata={
                    "skills_needed": analysis.skills_needed,
                    "recommended_skills": analysis.recommended_skills,
                    "is_simple": analysis.is_simple,
                    "execution_path": execution_path,
                    "task_keys": list(task.keys()),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log skill decision to aria_activity: {e}")

    async def _log_skill_consideration(self) -> None:
        """Log that this agent considered skills before native execution.

        Called at the start of execute() to record the OODA ACT phase
        skill evaluation in aria_activity. Reads the cached analysis
        from _last_skill_analysis set by execute_with_skills().

        If called outside the execute_with_skills() flow (i.e., execute()
        called directly), this is a no-op.
        """
        if self._last_skill_analysis is None:
            return

        analysis = self._last_skill_analysis
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            await activity.record(
                user_id=self.user_id,
                agent=self.agent_id,
                activity_type="skill_consideration",
                title=f"{self.name} proceeding with native execution",
                description=(
                    f"Available skills: {', '.join(self._get_available_skills()) or 'none'}. "
                    f"Decision: {'skill knowledge injected into context' if analysis.skills_needed else 'native execution preferred'}. "
                    f"Reasoning: {analysis.reasoning}"
                ),
                confidence=0.85,
                metadata={
                    "available_skills": self._get_available_skills(),
                    "skills_needed": analysis.skills_needed,
                    "recommended_skills": analysis.recommended_skills,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log skill consideration: {e}")

    async def _record_capability_execution(
        self,
        skill_entry: "SkillIndexEntry",
        result: AgentResult,
    ) -> None:
        """Record a capability execution to tracking tables.

        Writes to skill_execution_plans, skill_working_memory,
        skill_audit_log, and records usage in user_skills.

        Args:
            skill_entry: The skill that was executed.
            result: The execution result.
        """
        try:
            import uuid as _uuid
            from datetime import UTC, datetime

            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
            plan_id = str(_uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            exec_ms = result.execution_time_ms or 0

            # 1. skill_execution_plans — create a completed plan record
            try:
                db.table("skill_execution_plans").insert({
                    "id": plan_id,
                    "user_id": self.user_id,
                    "task_description": f"Direct capability: {skill_entry.skill_path}",
                    "plan_dag": json.dumps({
                        "steps": [{
                            "step_number": 1,
                            "skill_id": skill_entry.id,
                            "skill_path": skill_entry.skill_path,
                            "depends_on": [],
                            "input_data": {},
                        }],
                        "parallel_groups": [[1]],
                    }),
                    "status": "completed" if result.success else "failed",
                    "risk_level": "low",
                    "reasoning": "Direct capability dispatch — no LLM planning needed",
                    "estimated_seconds": 0,
                    "actual_seconds": exec_ms // 1000,
                    "completed_at": now,
                }).execute()
            except Exception as e:
                logger.debug("Failed to write skill_execution_plans: %s", e)

            # 2. skill_working_memory — record the step result
            try:
                db.table("skill_working_memory").insert({
                    "plan_id": plan_id,
                    "step_number": 1,
                    "skill_id": skill_entry.id,
                    "input_summary": None,
                    "output_summary": f"Capability {skill_entry.skill_path} {'succeeded' if result.success else 'failed'}",
                    "artifacts": json.dumps([]),
                    "extracted_facts": json.dumps({}),
                    "next_step_hints": json.dumps([]),
                    "status": "completed" if result.success else "failed",
                    "execution_time_ms": exec_ms,
                }).execute()
            except Exception as e:
                logger.debug("Failed to write skill_working_memory: %s", e)

            # 3. skill_audit_log
            try:
                db.table("skill_audit_log").insert({
                    "user_id": self.user_id,
                    "skill_id": skill_entry.id,
                    "skill_path": skill_entry.skill_path,
                    "action": "execute",
                    "success": result.success,
                    "execution_time_ms": exec_ms,
                    "error_message": result.error,
                    "metadata": json.dumps({
                        "agent_id": self.agent_id,
                        "execution_mode": "capability_direct",
                        "plan_id": plan_id,
                    }),
                    "timestamp": now,
                }).execute()
            except Exception as e:
                logger.debug("Failed to write skill_audit_log: %s", e)

            # 4. user_skills usage tracking
            try:
                from src.skills.installer import SkillInstaller

                installer = SkillInstaller()
                await installer.record_usage(
                    self.user_id,
                    skill_entry.id,
                    success=result.success,
                )
            except Exception as e:
                logger.debug("Failed to record skill usage: %s", e)

        except Exception as e:
            logger.warning(
                "Failed to record capability execution for %s: %s",
                skill_entry.skill_path, e,
            )

    async def _execute_simple_skill(
        self,
        task: dict[str, Any],
        skill_path: str,
    ) -> AgentResult:
        """Execute a single skill directly, bypassing full DAG orchestration.

        Execution paths (tried in order):
        1. Capability dispatch — if a handler exists in capability_handlers,
           call the real Python capability directly (no LLM sandbox).
        2. Orchestrator pipeline — create a 1-step plan via LLM and execute
           through the sandbox executor.
        3. Knowledge injection fallback — inject skill YAML into task context
           and use native execute().

        Args:
            task: Task specification with parameters.
            skill_path: The skill path to execute.

        Returns:
            AgentResult with execution outcome.
        """
        if self.skill_index is None:
            logger.warning(
                f"Agent {self.name}: skill index unavailable for simple execution, "
                "falling back to native execution",
            )
            return await self.execute(task)

        try:
            # Look up skill by path (exact match), fall back to search
            skill_entry = await self.skill_index.get_by_path(skill_path)
            if skill_entry is None:
                # Try fuzzy search as fallback
                search_results = await self.skill_index.search(
                    skill_path.split("/")[-1],
                    limit=1,
                )
                skill_entry = search_results[0] if search_results else None

            if skill_entry is None:
                logger.warning(
                    f"Agent {self.name}: skill '{skill_path}' not found in index, "
                    "falling back to native execution",
                )
                return await self.execute(task)

            # --- Path 1: Capability dispatch (real Python code, no sandbox) ---
            from src.skills.capability_handlers import get_capability_handler

            handler = get_capability_handler(skill_path)
            if handler is not None:
                logger.info(
                    f"Agent {self.name}: dispatching capability '{skill_path}' directly",
                    extra={"agent_id": self.agent_id, "skill_path": skill_path},
                )
                result = await handler(self.user_id, task, skill_entry)
                await self._record_capability_execution(skill_entry, result)
                return result

            # --- Path 2: Orchestrator pipeline (LLM sandbox) ---
            if self.skill_orchestrator is not None:
                task_description = json.dumps(task, default=str)
                plan = await self.skill_orchestrator.create_execution_plan(
                    task=task_description,
                    available_skills=[skill_entry],
                    user_id=self.user_id,
                )

                plan_result = await self.skill_orchestrator.execute_plan(
                    user_id=self.user_id,
                    plan=plan,
                )

                if plan_result.working_memory:
                    entry = plan_result.working_memory[0]
                    return AgentResult(
                        success=entry.status == "completed",
                        data={
                            "skill_execution": True,
                            "execution_mode": "simple",
                            "skill_path": skill_path,
                            "plan_id": plan_result.plan_id,
                            "summary": entry.summary,
                            "artifacts": entry.artifacts,
                        },
                        error=(
                            None
                            if entry.status == "completed"
                            else f"Skill step failed: {entry.status}"
                        ),
                    )

            # --- Path 3: Knowledge injection fallback ---
            # Inject skill definition content into task context for native execute()
            if skill_entry.full_content:
                logger.info(
                    f"Agent {self.name}: injecting skill knowledge for '{skill_path}'",
                    extra={"agent_id": self.agent_id, "skill_path": skill_path},
                )
                task = {**task, "skill_knowledge": skill_entry.full_content}

            return await self.execute(task)

        except Exception as e:
            logger.error(
                f"Agent {self.name}: simple skill execution failed for '{skill_path}': {e}",
                extra={"agent_id": self.agent_id, "skill_path": skill_path, "error": str(e)},
            )
            return await self.execute(task)

    async def execute_with_skills(self, task: dict[str, Any]) -> AgentResult:
        """Execute a task, using skills if beneficial.

        This is the OODA ACT phase integration point. Routes tasks through
        three execution paths based on skill analysis:

        1. **Native** (0 skills needed): Direct agent execute()
        2. **Simple** (1 skill needed): Single-skill execution, bypasses
           full DAG orchestration overhead
        3. **Orchestrator** (2+ skills needed): Full multi-skill DAG
           execution with working memory and parallel steps

        All routing decisions are logged to aria_activity for transparency.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with execution outcome.
        """
        # Step 0: Ensure core skills are installed for this user (once per agent)
        await self._ensure_core_skills_installed()

        # Step 1: Analyze if skills would help
        analysis = await self._analyze_skill_needs(task)
        self._last_skill_analysis = analysis

        if not analysis.skills_needed:
            await self._log_skill_decision(task, analysis, "native")
            logger.info(
                f"Agent {self.name}: no skills needed, using native execution",
                extra={"agent_id": self.agent_id, "reasoning": analysis.reasoning},
            )
            return await self.execute(task)

        # Step 2: Simple path - single skill, bypass full orchestration
        if analysis.is_simple and len(analysis.recommended_skills) == 1:
            skill_path = analysis.recommended_skills[0]
            await self._log_skill_decision(task, analysis, f"simple_skill:{skill_path}")
            logger.info(
                f"Agent {self.name}: simple task, executing skill '{skill_path}' directly",
                extra={"agent_id": self.agent_id, "skill": skill_path},
            )
            return await self._execute_simple_skill(task, skill_path)

        # Step 3: Complex path - multi-skill orchestration
        await self._log_skill_decision(task, analysis, "orchestrator")

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

        try:
            available_skill_entries = await self.skill_index.search(
                query=" ".join(analysis.recommended_skills),
            )

            task_description = json.dumps(task, default=str)

            plan = await self.skill_orchestrator.create_execution_plan(
                task=task_description,
                available_skills=available_skill_entries,
                user_id=self.user_id,
            )

            logger.info(
                f"Agent {self.name}: executing multi-skill plan with {len(plan.steps)} steps",
                extra={
                    "agent_id": self.agent_id,
                    "plan_id": plan.plan_id,
                    "step_count": len(plan.steps),
                },
            )

            plan_result = await self.skill_orchestrator.execute_plan(
                user_id=self.user_id,
                plan=plan,
            )

            skill_outputs = []
            all_succeeded = True
            for entry in plan_result.working_memory:
                skill_outputs.append(
                    {
                        "step": entry.step_number,
                        "skill_id": entry.skill_id,
                        "status": entry.status,
                        "summary": entry.summary,
                        "artifacts": entry.artifacts,
                    }
                )
                if entry.status != "completed":
                    all_succeeded = False

            return AgentResult(
                success=all_succeeded,
                data={
                    "skill_execution": True,
                    "execution_mode": "orchestrator",
                    "plan_id": plan_result.plan_id,
                    "steps": skill_outputs,
                },
                error=None if all_succeeded else "One or more skill steps failed",
            )

        except Exception as e:
            logger.error(
                f"Agent {self.name}: multi-skill execution failed: {e}",
                extra={"agent_id": self.agent_id, "error": str(e)},
            )
            return AgentResult(
                success=False,
                data=None,
                error=f"Skill execution failed: {e}",
            )

    async def run(self, task: dict[str, Any]) -> AgentResult:
        """Run the agent with skill-aware lifecycle management.

        Overrides BaseAgent.run() to route through execute_with_skills()
        instead of execute(), enabling automatic skill consideration
        for every task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with execution outcome.
        """
        start_time = time.perf_counter()
        self.status = AgentStatus.RUNNING

        logger.info(
            f"Agent {self.name} starting skill-aware execution",
            extra={
                "agent": self.name,
                "user_id": self.user_id,
                "task_keys": list(task.keys()),
            },
        )

        try:
            # Validate input
            if not self.validate_input(task):
                self.status = AgentStatus.FAILED
                return AgentResult(
                    success=False,
                    data=None,
                    error="Input validation failed",
                )

            # Route through skill-aware execution
            result = await self.execute_with_skills(task)

            # Format output
            result.data = self.format_output(result.data)

            # Calculate execution time
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            result.execution_time_ms = elapsed_ms

            # Accumulate token usage
            self.total_tokens_used += result.tokens_used

            self.status = AgentStatus.COMPLETE if result.success else AgentStatus.FAILED

            logger.info(
                f"Agent {self.name} skill-aware execution complete",
                extra={
                    "agent": self.name,
                    "user_id": self.user_id,
                    "success": result.success,
                    "execution_time_ms": elapsed_ms,
                    "tokens_used": result.tokens_used,
                },
            )

            return result

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self.status = AgentStatus.FAILED

            logger.error(
                f"Agent {self.name} skill-aware execution failed: {e}",
                extra={
                    "agent": self.name,
                    "user_id": self.user_id,
                    "error": str(e),
                    "execution_time_ms": elapsed_ms,
                },
            )

            return AgentResult(
                success=False,
                data=None,
                error=str(e),
                execution_time_ms=elapsed_ms,
            )
