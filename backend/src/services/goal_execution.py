"""Goal Execution Service — runs agent analyses for goals.

Supports two execution modes:
1. **Synchronous** (execute_goal_sync): Each agent runs inline, awaited in order.
   Used for activation goals during onboarding.
2. **Asynchronous** (execute_goal_async): Agents run in background via asyncio.Task.
   Emits events via EventBus for SSE streaming to the frontend.

Agent types and their analyses:
- Scout: Competitive landscape summary (top competitors, recent news, market signals)
- Analyst: Account analysis (company profile, key stakeholders, opportunities)
- Hunter: Prospect identification (3-5 companies matching user's ICP)
- Strategist: Strategic recommendations synthesis
- Scribe: Follow-up email or talking points draft
- Operator: Data quality report (what ARIA knows vs gaps)
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.core.event_bus import EventBus, GoalEvent
from src.core.llm import LLMClient
from src.core.ws import ws_manager
from src.db.supabase import SupabaseClient
from src.services.activity_service import ActivityService

try:
    from src.agents.verifier import (
        VERIFICATION_POLICIES,
        VerificationResult,
        VerifierAgent,
    )
except ImportError:
    VerifierAgent = None  # type: ignore[assignment,misc]
    VERIFICATION_POLICIES = {}  # type: ignore[assignment]
    VerificationResult = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_NOT_SET = object()  # Sentinel for lazy initialization

_AGENT_TO_CATEGORY: dict[str, str] = {
    "hunter": "lead_discovery",
    "analyst": "research",
    "strategist": "strategy",
    "scribe": "email_draft",
    "operator": "crm_action",
    "scout": "market_monitoring",
    "verifier": "verification",
    "executor": "browser_automation",
}

_AGENT_TO_VERIFICATION_POLICY: dict[str, str] = {
    "analyst": "RESEARCH_BRIEF",
    "scribe": "EMAIL_DRAFT",
    "strategist": "STRATEGY",
    "scout": "RESEARCH_BRIEF",
    "hunter": "RESEARCH_BRIEF",
    # operator, verifier, executor — no verification policy (action-based, not content-based)
}


class GoalExecutionService:
    """Executes agent goals by running LLM-powered analyses.

    Supports two execution modes:
    1. **Skill-aware**: Instantiates agent objects, calls execute_with_skills()
       which routes through skill analysis → simple/complex execution.
    2. **Prompt-based** (fallback): Builds agent-specific prompts and sends
       directly to LLM for structured analysis.
    """

    def __init__(self) -> None:
        """Initialize with database, LLM, and activity service."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._activity = ActivityService()
        self._dynamic_agents: dict[str, type] = {}
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._trust_service: Any = _NOT_SET
        self._trace_service: Any = _NOT_SET
        self._adaptive_coordinator: Any = _NOT_SET

    def _get_trust_service(self) -> Any:
        """Lazily initialize TrustCalibrationService."""
        if self._trust_service is _NOT_SET:
            try:
                from src.core.trust import get_trust_calibration_service

                self._trust_service = get_trust_calibration_service()
            except Exception as e:
                logger.warning("Failed to initialize TrustCalibrationService: %s", e)
                self._trust_service = None
        return self._trust_service

    def _get_trace_service(self) -> Any:
        """Lazily initialize DelegationTraceService."""
        if self._trace_service is _NOT_SET:
            try:
                from src.core.delegation_trace import DelegationTraceService

                self._trace_service = DelegationTraceService()
            except Exception as e:
                logger.warning("Failed to initialize DelegationTraceService: %s", e)
                self._trace_service = None
        return self._trace_service

    def _get_adaptive_coordinator(self) -> Any:
        """Lazily initialize AdaptiveCoordinator."""
        if self._adaptive_coordinator is _NOT_SET:
            try:
                from src.core.adaptive_coordinator import get_adaptive_coordinator

                self._adaptive_coordinator = get_adaptive_coordinator()
            except Exception as e:
                logger.warning("Failed to initialize AdaptiveCoordinator: %s", e)
                self._adaptive_coordinator = None
        return self._adaptive_coordinator

    async def _record_goal_update(
        self,
        goal_id: str,
        update_type: str,
        content: str,
        progress_delta: int = 0,
    ) -> None:
        """Record a goal lifecycle update in the goal_updates table.

        Args:
            goal_id: The goal ID.
            update_type: Type of update (progress, milestone, blocker, note).
            content: Description of the update.
            progress_delta: Change in progress percentage.
        """
        try:
            self._db.table("goal_updates").insert(
                {
                    "goal_id": goal_id,
                    "update_type": update_type,
                    "content": content,
                    "progress_delta": progress_delta,
                    "created_by": "aria",
                }
            ).execute()
        except Exception:
            logger.warning(
                "Failed to record goal update",
                extra={"goal_id": goal_id, "update_type": update_type},
            )

    def register_dynamic_agent(self, agent_type: str, agent_class: type) -> None:
        """Register a dynamically created agent class for task routing.

        Args:
            agent_type: The type key to use for dispatch.
            agent_class: The agent class (must extend BaseAgent).
        """
        self._dynamic_agents[agent_type] = agent_class
        logger.info(
            "Registered dynamic agent",
            extra={"agent_type": agent_type, "agent_class": agent_class.__name__},
        )

    async def execute_goal_sync(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Execute a single goal synchronously by running all assigned agents.

        This is the original synchronous execution path. For async background
        execution, use execute_goal_async() instead.

        Args:
            goal_id: The goal to execute.
            user_id: The user who owns this goal.

        Returns:
            Dict with goal_id, status, and list of agent results.
        """
        logger.info(
            "Starting goal execution",
            extra={"goal_id": goal_id, "user_id": user_id},
        )

        # Fetch the goal
        goal_result = (
            self._db.table("goals")
            .select("*, goal_agents(*)")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not goal_result.data:
            logger.warning("Goal not found", extra={"goal_id": goal_id})
            return {"goal_id": goal_id, "status": "not_found", "results": []}

        goal = goal_result.data

        # Update goal status to active
        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {"status": "active", "started_at": now, "updated_at": now}
        ).eq("id", goal_id).execute()

        await self._record_goal_update(
            goal_id, "progress", "Goal execution started", progress_delta=0
        )

        # Notify frontend that ARIA is processing
        try:
            await ws_manager.send_thinking(user_id)
        except Exception:
            logger.warning("Failed to send thinking event", extra={"user_id": user_id})

        # Gather context for agent execution
        context = await self._gather_execution_context(user_id)

        # Execute each assigned agent
        agent_type = goal.get("config", {}).get("agent_type", "")
        results: list[dict[str, Any]] = []

        if agent_type:
            # Single agent goal (activation goals have one agent_type in config)
            result = await self._execute_agent(
                user_id=user_id,
                goal=goal,
                agent_type=agent_type,
                context=context,
            )
            results.append(result)

            # Notify frontend of agent completion
            try:
                await ws_manager.send_progress_update(
                    user_id=user_id,
                    goal_id=goal_id,
                    progress=100,
                    status="active",
                    agent_name=agent_type,
                    message=f"{agent_type.title()} analysis complete",
                )
            except Exception:
                logger.warning(
                    "Failed to send progress event",
                    extra={"user_id": user_id, "goal_id": goal_id},
                )
        else:
            # Multi-agent goal: run each assigned agent
            agents_list = goal.get("goal_agents", [])
            for idx, agent in enumerate(agents_list):
                a_type = agent.get("agent_type", "")
                result = await self._execute_agent(
                    user_id=user_id,
                    goal=goal,
                    agent_type=a_type,
                    context=context,
                    goal_agent_id=agent.get("id"),
                )
                results.append(result)

                # Notify frontend of agent completion
                try:
                    pct = int(((idx + 1) / len(agents_list)) * 100)
                    await ws_manager.send_progress_update(
                        user_id=user_id,
                        goal_id=goal_id,
                        progress=pct,
                        status="active",
                        agent_name=a_type,
                        message=f"{a_type.title()} analysis complete",
                    )
                except Exception:
                    logger.warning(
                        "Failed to send progress event",
                        extra={"user_id": user_id, "goal_id": goal_id},
                    )

        # Update goal status to complete
        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {
                "status": "complete",
                "progress": 100,
                "completed_at": now,
                "updated_at": now,
            }
        ).eq("id", goal_id).execute()

        success_count = sum(1 for r in results if r.get("success"))
        await self._record_goal_update(
            goal_id,
            "milestone",
            f"Goal completed: {success_count}/{len(results)} agents succeeded",
            progress_delta=100,
        )

        # Notify frontend that goal is complete
        try:
            await ws_manager.send_aria_message(
                user_id=user_id,
                message=f'Goal "{goal.get("title", goal_id)}" complete — {success_count} of {len(results)} agents succeeded.',
                ui_commands=[
                    {"action": "navigate", "route": f"/goals/{goal_id}"},
                ],
                suggestions=["Show me the results", "What should I focus on next?"],
            )
        except Exception:
            logger.warning(
                "Failed to send goal completion message",
                extra={"user_id": user_id, "goal_id": goal_id},
            )

        logger.info(
            "Goal execution complete",
            extra={
                "goal_id": goal_id,
                "user_id": user_id,
                "agent_count": len(results),
                "success_count": sum(1 for r in results if r.get("success")),
            },
        )

        return {
            "goal_id": goal_id,
            "status": "complete",
            "results": results,
        }

    async def execute_activation_goals(self, user_id: str) -> list[dict[str, Any]]:
        """Execute all activation goals for a user.

        Queries for goals with config.source = 'onboarding_activation'
        and executes each one.

        Args:
            user_id: The user whose activation goals to execute.

        Returns:
            List of execution result dicts.
        """
        logger.info(
            "Executing activation goals",
            extra={"user_id": user_id},
        )

        # Query activation goals
        goals_result = (
            self._db.table("goals")
            .select("id, title, config")
            .eq("user_id", user_id)
            .eq("status", "draft")
            .execute()
        )

        activation_goals = [
            g
            for g in (goals_result.data or [])
            if g.get("config", {}).get("source") == "onboarding_activation"
        ]

        if not activation_goals:
            logger.info("No activation goals found", extra={"user_id": user_id})
            return []

        all_results: list[dict[str, Any]] = []

        for goal in activation_goals:
            try:
                result = await self.execute_goal_sync(goal["id"], user_id)
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "Failed to execute activation goal",
                    extra={
                        "goal_id": goal["id"],
                        "user_id": user_id,
                        "error": str(e),
                    },
                )
                all_results.append(
                    {
                        "goal_id": goal["id"],
                        "status": "failed",
                        "error": str(e),
                        "results": [],
                    }
                )

        logger.info(
            "Activation goals execution complete",
            extra={
                "user_id": user_id,
                "total": len(all_results),
                "succeeded": sum(1 for r in all_results if r.get("status") == "complete"),
            },
        )

        return all_results

    async def execute_approved_plan(
        self,
        goal_id: str,
        user_id: str,
        plan_tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute all steps of an approved plan sequentially.

        Called when user approves a goal plan via APPROVE_PLAN mode.
        Each sub-task is executed, verified, and retried if needed via
        AdaptiveCoordinator.

        Args:
            goal_id: The goal being executed.
            user_id: The user who owns this goal.
            plan_tasks: List of task dicts, each with agent_type, description, etc.

        Returns:
            Dict with goal_id, status, and list of step results.
        """
        total = len(plan_tasks)
        results: list[dict[str, Any]] = []
        context = await self._gather_execution_context(user_id)
        trust_svc = self._get_trust_service()
        adaptive = self._get_adaptive_coordinator()

        logger.info(
            "Starting approved plan execution",
            extra={"goal_id": goal_id, "user_id": user_id, "total_steps": total},
        )

        for i, task in enumerate(plan_tasks):
            step_num = i + 1
            agent_type = task.get("agent_type", "analyst")

            # Send progress WS event
            try:
                await ws_manager.send_progress_update(
                    user_id=user_id,
                    goal_id=goal_id,
                    progress=int((step_num / total) * 100),
                    status="executing",
                    agent_name=agent_type,
                    message=f"Step {step_num} of {total}: {task.get('description', '')}",
                )
            except Exception:
                logger.debug("Failed to send progress event for plan step %d", step_num)

            # Build a synthetic goal dict for agent execution
            step_goal = {
                "id": goal_id,
                "title": task.get("description", f"Step {step_num}"),
                "config": task.get("config", {}),
                "user_id": user_id,
            }

            # Execute with retry logic
            max_retries = 2
            step_result: dict[str, Any] | None = None

            for attempt in range(max_retries + 1):
                try:
                    step_result = await self._execute_agent(
                        user_id=user_id,
                        goal=step_goal,
                        agent_type=agent_type,
                        context=context,
                    )

                    if step_result.get("status") == "complete":
                        # Trust update on success
                        if trust_svc:
                            category = _AGENT_TO_CATEGORY.get(agent_type, "general")
                            try:  # noqa: SIM105
                                await trust_svc.update_on_success(user_id, category)
                            except Exception:
                                pass
                        break

                    # Step failed — try adaptive coordinator
                    if adaptive and attempt < max_retries:
                        decision = await adaptive.evaluate_failure(
                            task=task,
                            result=step_result,
                            attempt=attempt + 1,
                        )
                        if decision == "RETRY_SAME":
                            continue
                        if decision == "ESCALATE":
                            break
                    break

                except Exception as e:
                    logger.warning(
                        "Plan step %d failed (attempt %d): %s",
                        step_num,
                        attempt + 1,
                        e,
                    )
                    step_result = {
                        "agent": agent_type,
                        "status": "failed",
                        "error": str(e),
                    }
                    if attempt >= max_retries and trust_svc:
                        category = _AGENT_TO_CATEGORY.get(agent_type, "general")
                        try:  # noqa: SIM105
                            await trust_svc.update_on_failure(user_id, category)
                        except Exception:
                            pass

            results.append(step_result or {"agent": agent_type, "status": "skipped"})

            # If step failed after retries, escalate to user
            if step_result and step_result.get("status") == "failed":
                try:  # noqa: SIM105
                    await ws_manager.send_aria_message(
                        user_id=user_id,
                        message=(
                            f"Step {step_num} of your plan encountered an issue: "
                            f"{step_result.get('error', 'Unknown error')}. "
                            f"Should I continue with the remaining steps?"
                        ),
                        suggestions=["Continue", "Stop here"],
                    )
                except Exception:
                    pass
                # Don't halt — continue executing remaining steps
                # User can cancel via the goal cancellation endpoint

        # Mark goal complete
        all_succeeded = all(r.get("status") == "complete" for r in results)
        final_status = "complete" if all_succeeded else "partial"

        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {"status": final_status, "completed_at": now, "updated_at": now}
        ).eq("id", goal_id).execute()

        # Final progress event
        try:  # noqa: SIM105
            await ws_manager.send_progress_update(
                user_id=user_id,
                goal_id=goal_id,
                progress=100,
                status=final_status,
                message=f"Plan execution {final_status}: {len(results)} steps processed",
            )
        except Exception:
            pass

        logger.info(
            "Approved plan execution complete",
            extra={
                "goal_id": goal_id,
                "user_id": user_id,
                "status": final_status,
                "steps": len(results),
            },
        )

        return {
            "goal_id": goal_id,
            "status": final_status,
            "results": results,
        }

    def _create_agent_instance(
        self,
        agent_type: str,
        user_id: str,
    ) -> Any:
        """Create an agent instance for skill-aware execution.

        Args:
            agent_type: The agent type string (scout, analyst, etc.).
            user_id: The user's ID.

        Returns:
            Agent instance or None if creation fails.
        """
        try:
            from src.agents import (
                AnalystAgent,
                HunterAgent,
                OperatorAgent,
                ScoutAgent,
                ScribeAgent,
                StrategistAgent,
            )
            from src.agents.executor import ExecutorAgent
            from src.skills.index import SkillIndex
            from src.skills.orchestrator import SkillOrchestrator

            agent_classes: dict[str, type] = {
                "scout": ScoutAgent,
                "analyst": AnalystAgent,
                "hunter": HunterAgent,
                "strategist": StrategistAgent,
                "scribe": ScribeAgent,
                "operator": OperatorAgent,
                "executor": ExecutorAgent,
            }

            agent_cls = agent_classes.get(agent_type)
            if agent_cls is None:
                # Check dynamic agents
                dynamic_cls = self._dynamic_agents.get(agent_type)
                if dynamic_cls is not None:
                    return dynamic_cls(llm_client=self._llm, user_id=user_id)
                return None

            # Initialize skill infrastructure (best-effort)
            skill_orchestrator = None
            skill_index = None
            try:
                skill_index = SkillIndex()
                skill_orchestrator = SkillOrchestrator()
            except Exception as e:
                logger.debug(f"Skill infrastructure not available: {e}")

            # Initialize PersonaBuilder + ColdMemoryRetriever (best-effort)
            persona_builder = None
            cold_retriever = None
            try:
                from src.core.persona import get_persona_builder

                persona_builder = get_persona_builder()
            except Exception as e:
                logger.debug(f"PersonaBuilder not available: {e}")
            try:
                from src.db.supabase import SupabaseClient
                from src.memory.cold_retrieval import ColdMemoryRetriever

                cold_retriever = ColdMemoryRetriever(db_client=SupabaseClient.get_client())
            except Exception as e:
                logger.debug(f"ColdMemoryRetriever not available: {e}")

            # Executor extends BaseAgent (not SkillAwareAgent), separate path
            if agent_type == "executor":
                return agent_cls(
                    llm_client=self._llm,
                    user_id=user_id,
                    persona_builder=persona_builder,
                    cold_retriever=cold_retriever,
                )

            return agent_cls(
                llm_client=self._llm,
                user_id=user_id,
                skill_orchestrator=skill_orchestrator,
                skill_index=skill_index,
                persona_builder=persona_builder,
                cold_retriever=cold_retriever,
            )

        except Exception as e:
            logger.debug(f"Failed to create agent instance for {agent_type}: {e}")
            return None

    def _build_agent_task(
        self,
        agent_type: str,
        goal: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build a task dict compatible with an agent's execute() method.

        Maps goal context to each agent's expected task format.

        Args:
            agent_type: The agent type string.
            goal: The goal dict.
            context: Gathered execution context.

        Returns:
            Task dict or None if the agent type isn't supported.
        """
        config = goal.get("config", {})
        facts = context.get("facts", [])
        company_name = context.get("company_name", "")

        if agent_type == "hunter":
            return {
                "icp": {
                    "industry": config.get("industry", "Life Sciences"),
                    "size": config.get("company_size", ""),
                    "geography": config.get("geography", ""),
                },
                "target_count": config.get("target_count", 5),
                "exclusions": config.get("exclusions", []),
            }
        elif agent_type == "analyst":
            return {
                "query": goal.get("title", company_name),
                "depth": config.get("depth", "standard"),
            }
        elif agent_type == "strategist":
            return {
                "goal": {
                    "title": goal.get("title", ""),
                    "type": config.get("goal_type", "research"),
                    "target_company": company_name,
                },
                "resources": {
                    "time_horizon_days": config.get("time_horizon_days", 90),
                    "available_agents": ["Hunter", "Analyst", "Scribe", "Operator", "Scout"],
                },
                "constraints": config.get("constraints", {}),
                "context": {
                    "facts": facts[:10],
                    "company_name": company_name,
                },
            }
        elif agent_type == "scribe":
            return {
                "communication_type": config.get("communication_type", "email"),
                "goal": goal.get("title", f"Follow up for {company_name}"),
                "context": "; ".join(facts[:5]) if facts else "",
                "tone": config.get("tone", "formal"),
            }
        elif agent_type == "operator":
            return {
                "operation_type": config.get("operation_type", "crm_read"),
                "parameters": config.get("parameters", {"record_type": "accounts"}),
            }
        elif agent_type == "scout":
            entities = config.get("entities", [])
            if not entities and company_name:
                entities = [company_name]
            return {
                "entities": entities if entities else ["Unknown"],
                "signal_types": config.get("signal_types"),
            }
        elif agent_type == "executor":
            return {
                "task_description": config.get("task_description", goal.get("title", "")),
                "url": config.get("url", ""),
                "url_approved": config.get("url_approved", False),
                "steps": config.get("steps"),
            }

        return None

    async def _try_skill_execution(
        self,
        user_id: str,
        goal: dict[str, Any],
        agent_type: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Try to execute using skill-aware agent instance.

        Creates an agent instance, builds a compatible task, and calls
        execute_with_skills(). Returns the result data if skills were
        used successfully, or None to fall through to prompt-based execution.

        Args:
            user_id: The user's ID.
            goal: The goal dict.
            agent_type: The agent type string.
            context: Gathered execution context.

        Returns:
            Result data dict if skills were used, None otherwise.
        """
        try:
            agent = self._create_agent_instance(agent_type, user_id)
            if agent is None:
                return None

            task = self._build_agent_task(agent_type, goal, context)
            if task is None:
                return None

            # Only proceed with skill execution if the agent thinks skills are needed
            analysis = await agent._analyze_skill_needs(task)
            if not analysis.skills_needed:
                return None  # Let prompt-based flow handle it

            result = await agent.execute_with_skills(task)
            if result.success and result.data:
                return result.data

            return None

        except Exception as e:
            logger.debug(f"Skill execution attempt failed for {agent_type}: {e}")
            return None

    async def _verify_and_adapt(
        self,
        *,
        user_id: str,
        goal: dict[str, Any],
        agent_type: str,
        content: dict[str, Any],
        context: dict[str, Any],
        execution_mode: str,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
        """Verify agent output; retry or escalate on failure.

        Returns:
            (content, verification_result_dict, escalated)
            - content: original or retry content
            - verification_result_dict: VerificationResult.to_dict() or None
            - escalated: True if verification failed and retries exhausted
        """
        # 1. Look up policy
        policy_name = _AGENT_TO_VERIFICATION_POLICY.get(agent_type)
        if policy_name is None:
            return (content, None, False)

        if not VERIFICATION_POLICIES:
            return (content, None, False)

        policy = VERIFICATION_POLICIES.get(policy_name)
        if policy is None:
            return (content, None, False)

        # 2. Create verifier — fail-open on any error
        try:
            verifier = VerifierAgent(llm_client=self._llm, user_id=user_id)
        except Exception as e:
            logger.warning("Failed to create VerifierAgent, skipping verification: %s", e)
            return (content, None, False)

        # 3. Run verification — fail-open on error
        try:
            verification_result = await verifier.verify(content, policy)
        except Exception as e:
            logger.warning("Verification raised exception, skipping: %s", e)
            return (content, None, False)

        # 4. Check result
        if verification_result.passed:
            return (content, verification_result.to_dict(), False)

        # 5. Verification failed — try adaptive coordination
        coordinator = self._get_adaptive_coordinator()
        if coordinator is None:
            # No coordinator available, escalate with original content
            vr_dict = verification_result.to_dict()
            vr_dict["reason"] = "; ".join(verification_result.issues)
            return (content, vr_dict, True)

        # 6. Build evaluation and get decision
        try:
            from src.core.adaptive_coordinator import AgentOutputEvaluation

            vr_dict = verification_result.to_dict()
            vr_dict["reason"] = "; ".join(verification_result.issues)

            evaluation = AgentOutputEvaluation(
                agent_type=agent_type,
                goal_id=goal.get("id", ""),
                output=content,
                confidence=verification_result.confidence,
                execution_time_ms=0,
                expected_duration_ms=30000,
                verification_result=vr_dict,
            )

            decision = coordinator.evaluate_output(evaluation)
        except Exception as e:
            logger.warning("AdaptiveCoordinator evaluation failed: %s", e)
            vr_dict = verification_result.to_dict()
            vr_dict["reason"] = "; ".join(verification_result.issues)
            return (content, vr_dict, True)

        # 7. Handle decision
        from src.core.adaptive_coordinator import AdaptiveDecisionType

        if decision.decision_type == AdaptiveDecisionType.RETRY_SAME:
            # Inject verification feedback into context and retry
            retry_context = dict(context)
            retry_context["verification_feedback"] = "; ".join(verification_result.issues)
            retry_context["verification_suggestions"] = verification_result.suggestions

            retry_content = await self._retry_agent_execution(
                user_id=user_id,
                goal=goal,
                agent_type=agent_type,
                context=retry_context,
                execution_mode=execution_mode,
            )

            if retry_content is not None:
                # Re-verify the retry output
                try:
                    retry_vr = await verifier.verify(retry_content, policy)
                except Exception as e:
                    logger.warning("Retry verification raised exception: %s", e)
                    return (retry_content, None, False)

                if retry_vr.passed:
                    return (retry_content, retry_vr.to_dict(), False)

                # Retry also failed → escalate
                retry_vr_dict = retry_vr.to_dict()
                retry_vr_dict["reason"] = "; ".join(retry_vr.issues)
                return (retry_content, retry_vr_dict, True)

            # Retry returned None → escalate with original
            vr_dict = verification_result.to_dict()
            vr_dict["reason"] = "; ".join(verification_result.issues)
            return (content, vr_dict, True)

        # RE_DELEGATE, ESCALATE, or anything else → escalate
        vr_dict = verification_result.to_dict()
        vr_dict["reason"] = "; ".join(verification_result.issues)
        return (content, vr_dict, True)

    async def _retry_agent_execution(
        self,
        *,
        user_id: str,
        goal: dict[str, Any],
        agent_type: str,
        context: dict[str, Any],
        execution_mode: str,
    ) -> dict[str, Any] | None:
        """Re-run agent execution with verification feedback injected.

        Returns content dict or None on failure.
        """
        try:
            if execution_mode == "skill_aware":
                result = await self._try_skill_execution(
                    user_id=user_id,
                    goal=goal,
                    agent_type=agent_type,
                    context=context,
                )
                return result  # may be None

            # Prompt-based retry
            prompt_builder = {
                "scout": self._build_scout_prompt,
                "analyst": self._build_analyst_prompt,
                "hunter": self._build_hunter_prompt,
                "strategist": self._build_strategist_prompt,
                "scribe": self._build_scribe_prompt,
                "operator": self._build_operator_prompt,
            }

            builder = prompt_builder.get(agent_type)
            if not builder:
                return None

            prompt = builder(goal, context)

            # Append verification feedback to prompt
            feedback = context.get("verification_feedback", "")
            suggestions = context.get("verification_suggestions", [])
            if feedback:
                prompt += (
                    f"\n\n--- VERIFICATION FEEDBACK ---\n"
                    f"The previous output was rejected for: {feedback}\n"
                )
                if suggestions:
                    prompt += "Suggestions:\n" + "\n".join(
                        f"- {s}" for s in suggestions
                    )
                prompt += "\nPlease address these issues in your response.\n"

            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are ARIA, an AI Department Director for life sciences "
                    "commercial teams. Revise your analysis addressing the "
                    "verification feedback. Respond with a JSON object only."
                ),
                max_tokens=2048,
                temperature=0.3,
            )

            try:
                return json.loads(response)
            except json.JSONDecodeError:
                return {"raw_analysis": response.strip()}

        except Exception as e:
            logger.warning("Retry agent execution failed: %s", e)
            return None

    async def _execute_agent(
        self,
        user_id: str,
        goal: dict[str, Any],
        agent_type: str,
        context: dict[str, Any],
        goal_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a single agent's analysis.

        First attempts skill-aware execution via agent instances. If skills
        aren't applicable, falls back to prompt-based LLM analysis.

        Args:
            user_id: The user's ID.
            goal: The goal dict with title, description, config.
            agent_type: The agent type (scout, analyst, hunter, etc.).
            context: Gathered execution context (enrichment data, facts, etc.).
            goal_agent_id: Optional goal_agent row ID for execution tracking.

        Returns:
            Dict with agent_type, success, and content.
        """
        logger.info(
            "Executing agent analysis",
            extra={
                "user_id": user_id,
                "agent_type": agent_type,
                "goal_title": goal.get("title"),
            },
        )

        # --- Start delegation trace ---
        trace_id: str | None = None
        trace_svc = self._get_trace_service()
        if trace_svc:
            try:
                trace_id = await trace_svc.start_trace(
                    user_id=user_id,
                    goal_id=goal.get("id"),
                    delegator="goal_execution",
                    delegatee=agent_type,
                    task_description=(
                        f"{agent_type.title()} analysis for: "
                        f"{goal.get('title', '')}"
                    ),
                    inputs={
                        "goal_title": goal.get("title"),
                        "agent_type": agent_type,
                    },
                )
            except Exception as e:
                logger.warning("Failed to start delegation trace: %s", e)

        # Step 1: Try skill-aware execution
        skill_result = await self._try_skill_execution(
            user_id=user_id,
            goal=goal,
            agent_type=agent_type,
            context=context,
        )

        if skill_result is not None:
            logger.info(
                "Agent executed via skill-aware path",
                extra={"agent_type": agent_type, "user_id": user_id},
            )

            # --- Verification gate ---
            content, vr_dict, escalated = await self._verify_and_adapt(
                user_id=user_id,
                goal=goal,
                agent_type=agent_type,
                content=skill_result,
                context=context,
                execution_mode="skill_aware",
            )

            # Store execution result
            await self._store_execution(
                user_id=user_id,
                goal_id=goal["id"],
                agent_type=agent_type,
                content=content,
                goal_agent_id=goal_agent_id,
            )

            # Record goal update
            await self._record_goal_update(
                goal["id"],
                "progress",
                f"{agent_type.title()} completed analysis (skill-aware)",
            )

            # Record activity
            await self._activity.record(
                user_id=user_id,
                agent=agent_type,
                activity_type="analysis_complete",
                title=f"{agent_type.title()} completed skill-augmented analysis",
                description=content.get(
                    "summary", f"{agent_type.title()} skill execution for: {goal.get('title', '')}"
                ),
                confidence=0.85,
                related_entity_type="goal",
                related_entity_id=goal["id"],
                metadata={"execution_mode": "skill_aware"},
            )

            # Submit recommended actions to action queue (Gap #32)
            await self._submit_actions_to_queue(
                user_id=user_id,
                agent_type=agent_type,
                content=content,
                goal_id=goal["id"],
            )

            # Trust: failure if escalated, success otherwise
            trust_svc = self._get_trust_service()
            if trust_svc:
                try:
                    category = _AGENT_TO_CATEGORY.get(agent_type, "general")
                    if escalated:
                        await trust_svc.update_on_failure(user_id, category)
                    else:
                        await trust_svc.update_on_success(user_id, category)
                except Exception as te:
                    logger.warning("Trust update failed: %s", te)

            # Complete delegation trace (skill-aware path)
            if trace_svc and trace_id:
                try:
                    await trace_svc.complete_trace(
                        trace_id=trace_id,
                        outputs={"agent_type": agent_type, "success": True},
                        verification_result=vr_dict,
                        cost_usd=0.0,
                        status="completed",
                    )
                except Exception as te:
                    logger.warning("Failed to complete delegation trace: %s", te)

            result: dict[str, Any] = {
                "agent_type": agent_type,
                "success": True,
                "content": content,
                "execution_mode": "skill_aware",
                "verification_result": vr_dict,
            }
            if escalated:
                result["escalated"] = True
                result["escalation_reason"] = "Verification failed after retries"
            return result

        # Step 2: Fall back to prompt-based LLM analysis
        prompt_builder = {
            "scout": self._build_scout_prompt,
            "analyst": self._build_analyst_prompt,
            "hunter": self._build_hunter_prompt,
            "strategist": self._build_strategist_prompt,
            "scribe": self._build_scribe_prompt,
            "operator": self._build_operator_prompt,
        }

        builder = prompt_builder.get(agent_type)
        if not builder:
            logger.warning(f"Unknown agent type: {agent_type}")
            return {"agent_type": agent_type, "success": False, "error": "Unknown agent type"}

        prompt = builder(goal, context)

        try:
            # Build role context from user profile
            user_profile = context.get("user_profile", {})
            user_role = user_profile.get("role", "")
            user_title = user_profile.get("title", "")
            company_name = context.get("company_name", "")

            role_context = ""
            if user_role or user_title:
                role_context = (
                    f"\nThe user is a {user_title} in {user_role} at {company_name}. "
                    "Tailor your analysis to their perspective and priorities."
                )

            # Inject ARIA config and tone guidance (Gap #33)
            config_context = ""
            aria_config = context.get("aria_config", {})
            if aria_config:
                role_name = aria_config.get("role", "")
                domain_focus = aria_config.get("domain_focus", {})
                therapeutic_areas = domain_focus.get("therapeutic_areas", [])
                if role_name:
                    config_context += f"\nARIA role: {role_name}."
                if therapeutic_areas:
                    config_context += f"\nFocus areas: {', '.join(therapeutic_areas)}."
                competitor_watchlist = aria_config.get("competitor_watchlist", [])
                if competitor_watchlist:
                    config_context += f"\nCompetitor watchlist: {', '.join(competitor_watchlist)}."
                personality = aria_config.get("personality", {})
                if personality:
                    config_context += (
                        f"\nPersonality: assertiveness={personality.get('assertiveness', 50)}, "
                        f"verbosity={personality.get('verbosity', 50)}, "
                        f"proactiveness={personality.get('proactiveness', 50)}."
                    )

            tone_context = ""
            tone_guidance = context.get("tone_guidance", "")
            if tone_guidance:
                tone_context = f"\nCommunication style: {tone_guidance}"

            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are ARIA, an AI Department Director for life sciences "
                    "commercial teams. You are performing an initial analysis based "
                    "on onboarding data. Be specific, actionable, and concise. "
                    f"Respond with a JSON object only.{role_context}"
                    f"{config_context}{tone_context}"
                ),
                max_tokens=2048,
                temperature=0.4,
            )

            # Parse the JSON response
            try:
                content = json.loads(response)
            except json.JSONDecodeError:
                content = {"raw_analysis": response.strip()}

            # --- Verification gate ---
            content, vr_dict, escalated = await self._verify_and_adapt(
                user_id=user_id,
                goal=goal,
                agent_type=agent_type,
                content=content,
                context=context,
                execution_mode="prompt_based",
            )

            # Store execution result
            await self._store_execution(
                user_id=user_id,
                goal_id=goal["id"],
                agent_type=agent_type,
                content=content,
                goal_agent_id=goal_agent_id,
            )

            # Record goal update
            await self._record_goal_update(
                goal["id"],
                "progress",
                f"{agent_type.title()} completed analysis (prompt-based)",
            )

            # Record activity
            await self._activity.record(
                user_id=user_id,
                agent=agent_type,
                activity_type="analysis_complete",
                title=f"{agent_type.title()} completed initial analysis",
                description=content.get(
                    "summary", f"{agent_type.title()} analysis for: {goal.get('title', '')}"
                ),
                confidence=0.8,
                related_entity_type="goal",
                related_entity_id=goal["id"],
                metadata={"execution_mode": "prompt_based"},
            )

            # Submit recommended actions to action queue (Gap #32)
            await self._submit_actions_to_queue(
                user_id=user_id,
                agent_type=agent_type,
                content=content,
                goal_id=goal["id"],
            )

            # Trust: failure if escalated, success otherwise
            trust_svc = self._get_trust_service()
            if trust_svc:
                try:
                    category = _AGENT_TO_CATEGORY.get(agent_type, "general")
                    if escalated:
                        await trust_svc.update_on_failure(user_id, category)
                    else:
                        await trust_svc.update_on_success(user_id, category)
                except Exception as te:
                    logger.warning("Trust update failed: %s", te)

            # Complete delegation trace (prompt-based path)
            if trace_svc and trace_id:
                try:
                    await trace_svc.complete_trace(
                        trace_id=trace_id,
                        outputs={"agent_type": agent_type, "success": True},
                        verification_result=vr_dict,
                        cost_usd=0.0,
                        status="completed",
                    )
                except Exception as te:
                    logger.warning("Failed to complete delegation trace: %s", te)

            result = {
                "agent_type": agent_type,
                "success": True,
                "content": content,
                "execution_mode": "prompt_based",
                "verification_result": vr_dict,
            }
            if escalated:
                result["escalated"] = True
                result["escalation_reason"] = "Verification failed after retries"
            return result

        except Exception as e:
            logger.error(
                "Agent execution failed",
                extra={
                    "agent_type": agent_type,
                    "user_id": user_id,
                    "error": str(e),
                },
            )

            # Trust update on failure
            trust_svc = self._get_trust_service()
            if trust_svc:
                try:
                    category = _AGENT_TO_CATEGORY.get(agent_type, "general")
                    await trust_svc.update_on_failure(user_id, category)
                except Exception as te:
                    logger.warning("Trust update on failure failed: %s", te)

            # Fail delegation trace
            if trace_svc and trace_id:
                try:
                    await trace_svc.fail_trace(
                        trace_id=trace_id,
                        error_message=str(e)[:500],
                    )
                except Exception as te:
                    logger.warning("Failed to record trace failure: %s", te)

            return {
                "agent_type": agent_type,
                "success": False,
                "error": str(e),
            }

    async def _submit_actions_to_queue(
        self,
        user_id: str,
        agent_type: str,
        content: dict[str, Any],
        goal_id: str,
    ) -> None:
        """Submit recommended actions from agent analysis to action queue.

        Extracts actionable recommendations from the analysis content and
        submits them for user approval via the action queue workflow.
        """
        try:
            from src.models.action_queue import (
                ActionAgent,
                ActionCreate,
                ActionType,
                RiskLevel,
            )
            from src.services.action_queue_service import ActionQueueService

            # Map agent_type to ActionAgent enum
            agent_map: dict[str, ActionAgent] = {
                "scout": ActionAgent.SCOUT,
                "analyst": ActionAgent.ANALYST,
                "hunter": ActionAgent.HUNTER,
                "strategist": ActionAgent.STRATEGIST,
                "scribe": ActionAgent.SCRIBE,
                "operator": ActionAgent.OPERATOR,
            }
            agent_enum = agent_map.get(agent_type)
            if not agent_enum:
                return

            queue = ActionQueueService()
            recommendations = content.get("recommendations", content.get("next_steps", []))
            if isinstance(recommendations, list):
                for rec in recommendations[:3]:
                    action_title = rec if isinstance(rec, str) else rec.get("action", str(rec))
                    action_data = ActionCreate(
                        agent=agent_enum,
                        action_type=ActionType.RESEARCH,
                        title=action_title[:200],
                        description=f"Recommended by {agent_type.title()} agent during initial analysis.",
                        risk_level=RiskLevel.LOW,
                        payload={
                            "goal_id": goal_id,
                            "source": "activation_analysis",
                        },
                    )
                    await queue.submit_action(
                        user_id=user_id,
                        data=action_data,
                    )
        except Exception as e:
            logger.warning("Failed to submit actions to queue: %s", e)

    async def _store_execution(
        self,
        user_id: str,  # noqa: ARG002
        goal_id: str,
        agent_type: str,
        content: dict[str, Any],
        goal_agent_id: str | None = None,
    ) -> None:
        """Store agent execution result in agent_executions table.

        Args:
            user_id: The user's ID (for future audit trail use).
            goal_id: The goal ID.
            agent_type: The agent type.
            content: The execution output.
            goal_agent_id: Optional goal_agent row ID.
        """
        now = datetime.now(UTC).isoformat()

        # If no goal_agent_id, find or create one
        if not goal_agent_id:
            agent_result = (
                self._db.table("goal_agents")
                .select("id")
                .eq("goal_id", goal_id)
                .eq("agent_type", agent_type)
                .maybe_single()
                .execute()
            )
            if agent_result.data:
                goal_agent_id = agent_result.data["id"]
            else:
                # Create a goal_agents record
                insert_result = (
                    self._db.table("goal_agents")
                    .insert(
                        {
                            "goal_id": goal_id,
                            "agent_type": agent_type,
                            "agent_config": {"source": "goal_execution"},
                            "status": "complete",
                        }
                    )
                    .execute()
                )
                if insert_result.data:
                    goal_agent_id = insert_result.data[0]["id"]

        if goal_agent_id:
            # Store in agent_executions table
            self._db.table("agent_executions").insert(
                {
                    "goal_agent_id": goal_agent_id,
                    "input": {"goal_id": goal_id, "agent_type": agent_type},
                    "output": content,
                    "status": "complete",
                    "tokens_used": 0,
                    "started_at": now,
                    "completed_at": now,
                }
            ).execute()

            # Update goal_agent status
            self._db.table("goal_agents").update({"status": "complete"}).eq(
                "id", goal_agent_id
            ).execute()

        logger.info(
            "Execution stored",
            extra={
                "goal_id": goal_id,
                "agent_type": agent_type,
                "goal_agent_id": goal_agent_id,
            },
        )

    async def _gather_execution_context(self, user_id: str) -> dict[str, Any]:
        """Gather context needed for agent execution.

        Pulls enrichment data, semantic facts, user profile, company info,
        and first goal to give agents context for their analyses.

        Args:
            user_id: The user's ID.

        Returns:
            Context dict with all gathered data.
        """
        # Get user profile
        profile_result = (
            self._db.table("user_profiles").select("*").eq("id", user_id).maybe_single().execute()
        )
        profile = profile_result.data or {}

        # Get company info
        company: dict[str, Any] = {}
        if profile.get("company_id"):
            company_result = (
                self._db.table("companies")
                .select("*")
                .eq("id", profile["company_id"])
                .maybe_single()
                .execute()
            )
            company = company_result.data or {}

        # Get top semantic facts
        facts_result = (
            self._db.table("memory_semantic")
            .select("fact, confidence, source, metadata")
            .eq("user_id", user_id)
            .order("confidence", desc=True)
            .limit(30)
            .execute()
        )
        facts = facts_result.data or []

        # Get knowledge gaps
        gaps_result = (
            self._db.table("prospective_memories")
            .select("task, metadata")
            .eq("user_id", user_id)
            .execute()
        )
        gaps = [
            g
            for g in (gaps_result.data or [])
            if g.get("metadata", {}).get("type") == "knowledge_gap"
        ]

        # Get readiness scores
        state_result = (
            self._db.table("onboarding_state")
            .select("readiness_scores")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        readiness = (state_result.data or {}).get("readiness_scores", {})

        # Build enrichment summary from facts
        fact_texts = [f.get("fact", "") for f in facts[:20]]

        context = {
            "profile": profile,
            "company": company,
            "company_name": company.get("name", "the company"),
            "company_domain": company.get("domain", ""),
            "classification": company.get("settings", {}).get("classification", {}),
            "facts": fact_texts,
            "facts_full": facts,
            "gaps": [g.get("task", "") for g in gaps[:5]],
            "readiness": readiness,
        }

        # Fetch user profile for role context
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("role, title, full_name, company_id")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile_result.data:
                context["user_profile"] = profile_result.data
                company_id = profile_result.data.get("company_id")
                if company_id:
                    company_result = (
                        self._db.table("companies")
                        .select("name")
                        .eq("id", company_id)
                        .maybe_single()
                        .execute()
                    )
                    if company_result.data:
                        context["company_name"] = company_result.data.get("name", "")
        except Exception as e:
            logger.warning("Failed to fetch user profile for context: %s", e)

        # Load ARIA role configuration (Gap #33)
        try:
            settings_result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if settings_result.data:
                prefs = settings_result.data.get("preferences", {})
                aria_config = prefs.get("aria_config", {})
                if aria_config:
                    context["aria_config"] = aria_config
                # Load personality calibration for tone guidance
                dt = prefs.get("digital_twin", {})
                calibration = dt.get("personality_calibration", {})
                if calibration:
                    context["tone_guidance"] = calibration.get("tone_guidance", "")
        except Exception as e:
            logger.warning("Failed to load aria_config for context: %s", e)

        return context

    # --- Prompt Builders ---

    def _build_scout_prompt(self, goal: dict[str, Any], ctx: dict[str, Any]) -> str:
        """Build Scout agent prompt for competitive landscape analysis."""
        competitors = goal.get("config", {}).get("entities", [])
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])

        return (
            f"Analyze the competitive landscape for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"Known competitors/entities: {', '.join(str(c) for c in competitors) or 'None identified yet'}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Produce a competitive landscape analysis. Respond with JSON:\n"
            "{\n"
            '  "summary": "2-3 sentence overview",\n'
            '  "competitors": [\n'
            '    {"name": "...", "relationship": "direct|indirect|adjacent", "key_differentiator": "..."}\n'
            "  ],\n"
            '  "market_signals": ["signal 1", "signal 2"],\n'
            '  "opportunities": ["opportunity based on competitive gaps"],\n'
            '  "watch_items": ["things to monitor"]\n'
            "}"
        )

    def _build_analyst_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Analyst agent prompt for account analysis."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])

        return (
            f"Perform an account analysis for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"User role: {ctx['profile'].get('title', 'Unknown')}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Produce an account analysis. Respond with JSON:\n"
            "{\n"
            '  "summary": "2-3 sentence company profile",\n'
            '  "key_stakeholders": [\n'
            '    {"role": "...", "importance": "high|medium|low", "approach": "..."}\n'
            "  ],\n"
            '  "opportunities": ["concrete opportunity 1"],\n'
            '  "risks": ["risk or challenge"],\n'
            '  "recommended_actions": ["specific next step"]\n'
            "}"
        )

    def _build_hunter_prompt(self, goal: dict[str, Any], ctx: dict[str, Any]) -> str:
        """Build Hunter agent prompt for prospect identification."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:10])
        icp_description = goal.get("config", {}).get("icp_refinement", "")

        return (
            f"Identify potential prospect companies for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"ICP context: {icp_description}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Identify 3-5 types of prospect companies that would match the user's "
            "ideal customer profile based on what we know. Respond with JSON:\n"
            "{\n"
            '  "summary": "ICP analysis summary",\n'
            '  "icp_characteristics": ["characteristic 1", "characteristic 2"],\n'
            '  "prospect_profiles": [\n'
            '    {"company_type": "...", "why_good_fit": "...", "approach_strategy": "..."}\n'
            "  ],\n"
            '  "search_criteria": ["criteria for finding prospects"],\n'
            '  "next_steps": ["action to refine targeting"]\n'
            "}"
        )

    def _build_strategist_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Strategist agent prompt for strategic recommendations."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])
        gaps = "\n".join(f"- {g}" for g in ctx["gaps"][:5])

        return (
            f"Synthesize strategic recommendations for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"User role: {ctx['profile'].get('title', 'Unknown')}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n"
            f"Knowledge gaps:\n{gaps or 'None identified'}\n"
            f"Readiness scores: {json.dumps(ctx['readiness'])}\n\n"
            "Produce strategic recommendations. Respond with JSON:\n"
            "{\n"
            '  "summary": "Strategic assessment overview",\n'
            '  "market_position": "assessment of current position",\n'
            '  "strategic_priorities": [\n'
            '    {"priority": "...", "rationale": "...", "timeline": "short|medium|long"}\n'
            "  ],\n"
            '  "quick_wins": ["actionable item achievable this week"],\n'
            '  "key_risks": ["strategic risk to address"],\n'
            '  "recommended_focus": "top recommendation for this quarter"\n'
            "}"
        )

    def _build_scribe_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Scribe agent prompt for follow-up draft."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:10])

        return (
            f"Draft initial talking points for {ctx['company_name']}.\n\n"
            f"User: {ctx['profile'].get('full_name', 'the user')}, "
            f"{ctx['profile'].get('title', 'Sales Professional')}\n"
            f"Company: {ctx['company_name']}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Produce talking points and a sample email draft that the user "
            "could use for outreach. Respond with JSON:\n"
            "{\n"
            '  "summary": "What these talking points cover",\n'
            '  "talking_points": ["point 1", "point 2", "point 3"],\n'
            '  "email_draft": {\n'
            '    "subject": "...",\n'
            '    "body": "..."\n'
            "  },\n"
            '  "tone_notes": "guidance on delivery",\n'
            '  "personalization_hooks": ["detail to reference in conversation"]\n'
            "}"
        )

    def _build_operator_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Operator agent prompt for data quality report."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])
        gaps = "\n".join(f"- {g}" for g in ctx["gaps"][:5])

        return (
            f"Generate a data quality report for {ctx['company_name']}.\n\n"
            f"Current data:\n{facts or 'No facts available'}\n"
            f"Known gaps:\n{gaps or 'No gaps identified'}\n"
            f"Readiness scores: {json.dumps(ctx['readiness'])}\n"
            f"Total facts available: {len(ctx.get('facts_full', []))}\n\n"
            "Assess what ARIA knows vs what's missing. Respond with JSON:\n"
            "{\n"
            '  "summary": "Data quality overview",\n'
            '  "coverage": {\n'
            '    "company_intel": "strong|moderate|weak",\n'
            '    "contact_network": "strong|moderate|weak",\n'
            '    "competitive_intel": "strong|moderate|weak",\n'
            '    "pipeline_data": "strong|moderate|weak"\n'
            "  },\n"
            '  "data_quality_score": 0-100,\n'
            '  "critical_gaps": ["most important missing data"],\n'
            '  "recommended_actions": ["action to improve data quality"],\n'
            '  "integration_suggestions": ["connect X for better coverage"]\n'
            "}"
        )

    # --- Async Goal Execution Methods ---

    async def propose_goals(self, user_id: str) -> dict[str, Any]:
        """Use LLM to propose goals based on user context.

        Gathers execution context and asks the LLM to suggest goals
        the user should pursue based on pipeline gaps, market signals, etc.

        Args:
            user_id: The user to propose goals for.

        Returns:
            Dict with proposals list and context_summary.
        """
        context = await self._gather_execution_context(user_id)

        facts_text = "\n".join(f"- {f}" for f in context.get("facts", [])[:20])
        gaps_text = "\n".join(f"- {g}" for g in context.get("gaps", [])[:5])

        prompt = (
            f"Based on the following context for {context.get('company_name', 'the user')}, "
            "propose 3-4 goals that ARIA should pursue.\n\n"
            f"Key facts:\n{facts_text or 'Limited data'}\n"
            f"Knowledge gaps:\n{gaps_text or 'None identified'}\n"
            f"Readiness: {json.dumps(context.get('readiness', {}))}\n\n"
            "Respond with JSON:\n"
            "{\n"
            '  "proposals": [\n'
            '    {"title": "...", "description": "...", "goal_type": "lead_gen|research|strategy|communication|operations",\n'
            '     "rationale": "why this goal matters now", "priority": "high|medium|low",\n'
            '     "estimated_days": 7, "agent_assignments": ["hunter", "analyst"]}\n'
            "  ],\n"
            '  "context_summary": "brief summary of user context"\n'
            "}"
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are ARIA, an AI Department Director for life sciences "
                "commercial teams. Propose actionable goals. Respond with JSON only."
            ),
            max_tokens=2048,
            temperature=0.4,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"proposals": [], "context_summary": response.strip()}

    async def _gather_user_resources(self, user_id: str) -> dict[str, Any]:
        """Gather this user's integrations, trust profiles, and company facts.

        Returns a dict with keys: integrations, trust_profiles, company_facts,
        company_id.
        """
        resources: dict[str, Any] = {
            "integrations": [],
            "trust_profiles": [],
            "company_facts": [],
            "company_id": None,
        }

        # Active integrations for this user
        try:
            integ_result = (
                self._db.table("user_integrations")
                .select("integration_type, status, display_name")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            resources["integrations"] = integ_result.data or []
        except Exception as e:
            logger.warning("Failed to fetch user integrations: %s", e)

        # Trust profiles for this user
        try:
            trust_result = (
                self._db.table("user_trust_profiles")
                .select("action_category, trust_score, successful_actions, failed_actions")
                .eq("user_id", user_id)
                .execute()
            )
            resources["trust_profiles"] = trust_result.data or []
        except Exception as e:
            logger.warning("Failed to fetch trust profiles: %s", e)

        # Company facts
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            company_id = (profile_result.data or {}).get("company_id")
            resources["company_id"] = company_id
            if company_id:
                # Try corporate_facts first, fall back to memory_semantic
                try:
                    facts_result = (
                        self._db.table("corporate_facts")
                        .select("fact_type, content")
                        .eq("company_id", company_id)
                        .limit(20)
                        .execute()
                    )
                    resources["company_facts"] = facts_result.data or []
                except Exception:
                    # Table may not exist; fall back to semantic memory
                    facts_result = (
                        self._db.table("memory_semantic")
                        .select("fact, confidence")
                        .eq("user_id", user_id)
                        .order("confidence", desc=True)
                        .limit(15)
                        .execute()
                    )
                    resources["company_facts"] = [
                        {"fact_type": "semantic", "content": f.get("fact", "")}
                        for f in (facts_result.data or [])
                    ]
        except Exception as e:
            logger.warning("Failed to fetch company facts: %s", e)

        return resources

    async def plan_goal(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Resource-aware goal planning: decomposes a goal into executable tasks.

        Gathers THIS user's integrations, trust profiles, and company context,
        then calls Claude to produce a detailed execution plan showing per-task
        tools needed, risk levels, and resource availability.

        Args:
            goal_id: The goal to plan.
            user_id: The user who owns this goal.

        Returns:
            Dict with goal_id, tasks (with resource info), execution_mode,
            missing_integrations, approval_points, estimated_total_minutes,
            and reasoning.
        """
        # Fetch goal — validate ownership
        goal_result = (
            self._db.table("goals")
            .select("*")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        goal = goal_result.data
        if not goal:
            return {"goal_id": goal_id, "error": "Goal not found", "tasks": []}

        # Try procedural memory first for matching workflows
        try:
            from src.memory.procedural import ProceduralMemory

            procedural = ProceduralMemory()
            matching = await procedural.find_matching_workflow(
                user_id=user_id,
                context={
                    "goal_type": goal.get("goal_type", ""),
                    "title": goal.get("title", ""),
                },
            )
            if matching and matching.success_rate > 0.7:
                logger.info(
                    "Reusing procedural memory workflow for goal %s (success_rate=%.2f)",
                    goal_id,
                    matching.success_rate,
                )
                tasks: list[dict[str, Any]] = []
                for i, step in enumerate(matching.steps):
                    tasks.append(
                        {
                            "title": step.get("title", f"Step {i + 1}"),
                            "description": step.get("description", ""),
                            "agent": step.get("agent_type", "analyst"),
                            "dependencies": step.get("depends_on", []),
                            "tools_needed": step.get("tools_needed", []),
                            "auth_required": step.get("auth_required", []),
                            "risk_level": step.get("risk_level", "LOW"),
                            "estimated_minutes": step.get(
                                "estimated_duration_minutes", 30
                            ),
                            "auto_executable": step.get("auto_executable", True),
                        }
                    )
                plan: dict[str, Any] = {
                    "goal_id": goal_id,
                    "tasks": tasks,
                    "execution_mode": "reused_workflow",
                    "missing_integrations": [],
                    "approval_points": [],
                    "estimated_total_minutes": sum(
                        t.get("estimated_minutes", 30) for t in tasks
                    ),
                    "reasoning": (
                        f"Reused successful workflow pattern "
                        f"(success rate: {matching.success_rate:.0%})"
                    ),
                }
                self._db.table("goal_execution_plans").upsert(
                    {
                        "goal_id": goal_id,
                        "user_id": user_id,
                        "plan": json.dumps(plan),
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                ).execute()
                return plan
        except Exception as e:
            logger.debug(
                "Procedural memory lookup failed, proceeding with LLM planning: %s", e
            )

        # Gather user-specific resources and execution context
        resources = await self._gather_user_resources(user_id)
        context = await self._gather_execution_context(user_id)

        # Build integration summary for the prompt
        active_integrations = [
            i["integration_type"] for i in resources["integrations"]
        ]
        integration_summary = (
            ", ".join(active_integrations) if active_integrations else "None connected"
        )

        # Build trust summary
        trust_summary = "New user (default trust 0.3)"
        if resources["trust_profiles"]:
            trust_lines = [
                f"  {t['action_category']}: {t['trust_score']:.2f} "
                f"({t['successful_actions']} successes, {t['failed_actions']} failures)"
                for t in resources["trust_profiles"]
            ]
            trust_summary = "\n".join(trust_lines)

        # Build company facts summary
        facts_summary = "No company facts available"
        if resources["company_facts"]:
            fact_lines = [
                f"  [{f.get('fact_type', 'general')}] {f.get('content', '')}"
                for f in resources["company_facts"][:10]
            ]
            facts_summary = "\n".join(fact_lines)

        prompt = (
            f"Create a detailed execution plan for this goal.\n\n"
            f"## Goal\n"
            f"Title: {goal.get('title', '')}\n"
            f"Description: {goal.get('description', '')}\n"
            f"Type: {goal.get('goal_type', 'research')}\n\n"
            f"## User Context\n"
            f"Company: {context.get('company_name', 'Unknown')}\n"
            f"User role: {context.get('user_profile', {}).get('title', 'Unknown')}\n"
            f"Connected integrations: {integration_summary}\n\n"
            f"## Trust Levels\n{trust_summary}\n\n"
            f"## Company Knowledge\n{facts_summary}\n\n"
            f"## Available Agents & Their Tools\n"
            f"- hunter: Lead discovery (tools: exa_search, apollo_search)\n"
            f"- analyst: Scientific research (tools: pubmed_search, fda_search, "
            f"chembl_search, clinicaltrials_search)\n"
            f"- strategist: Strategic planning (tools: claude_analysis)\n"
            f"- scribe: Email/doc drafting (tools: digital_twin_style, claude_drafting)\n"
            f"- operator: CRM & calendar actions (tools: composio_crm, composio_calendar, "
            f"composio_email_send)\n"
            f"- scout: Market monitoring (tools: exa_search, news_apis)\n\n"
            f"## Instructions\n"
            f"Decompose the goal into 3-8 concrete sub-tasks. For each task, specify:\n"
            f"- Which agent handles it\n"
            f"- What tools/integrations are needed\n"
            f"- What integrations the user must have connected (auth_required)\n"
            f"- Risk level (LOW/MEDIUM/HIGH/CRITICAL)\n"
            f"- Whether it can auto-execute or needs approval\n"
            f"- Time estimate in minutes\n"
            f"- Dependencies on other tasks (by index, 0-based)\n\n"
            f"Also identify:\n"
            f"- Missing integrations the user should connect\n"
            f"- Points where ARIA needs user approval before proceeding\n\n"
            f"Respond with JSON ONLY (no markdown fences):\n"
            f'{{\n'
            f'  "tasks": [\n'
            f'    {{\n'
            f'      "title": "Task title",\n'
            f'      "agent": "hunter|analyst|strategist|scribe|operator|scout",\n'
            f'      "dependencies": [],\n'
            f'      "tools_needed": ["exa_search"],\n'
            f'      "auth_required": ["salesforce"],\n'
            f'      "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",\n'
            f'      "estimated_minutes": 15,\n'
            f'      "auto_executable": true\n'
            f'    }}\n'
            f'  ],\n'
            f'  "missing_integrations": ["salesforce"],\n'
            f'  "approval_points": ["Before sending outreach emails"],\n'
            f'  "estimated_total_minutes": 120\n'
            f'}}'
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are ARIA's resource-aware planning engine. You create detailed, "
                "actionable execution plans that account for the user's connected "
                "integrations, trust levels, and company context. "
                "Each task must have a clear agent assignment and resource requirements. "
                "Be realistic about time estimates. "
                "Respond with valid JSON only — no markdown code fences or commentary."
            ),
            max_tokens=4096,
            temperature=0.3,
            user_id=user_id,
        )

        # Strip markdown fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            plan_data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse plan JSON for goal %s, using fallback", goal_id
            )
            plan_data = {
                "tasks": [
                    {
                        "title": goal.get("title", "Execute goal"),
                        "agent": goal.get("config", {}).get("agent_type", "analyst"),
                        "dependencies": [],
                        "tools_needed": [],
                        "auth_required": [],
                        "risk_level": "LOW",
                        "estimated_minutes": 30,
                        "auto_executable": True,
                    }
                ],
                "missing_integrations": [],
                "approval_points": [],
                "estimated_total_minutes": 30,
            }

        tasks_json = plan_data.get("tasks", [])
        missing_integrations = plan_data.get("missing_integrations", [])
        approval_points = plan_data.get("approval_points", [])
        estimated_total = plan_data.get(
            "estimated_total_minutes",
            sum(t.get("estimated_minutes", 30) for t in tasks_json),
        )

        # Annotate tasks with resource availability for this user
        total_tools = 0
        connected_tools = 0
        for task in tasks_json:
            task_resources: list[dict[str, Any]] = []
            for tool in task.get("tools_needed", []):
                connected = self._check_tool_connected(tool, active_integrations)
                task_resources.append(
                    {"tool": tool, "connected": connected}
                )
                total_tools += 1
                if connected:
                    connected_tools += 1
            task["resource_status"] = task_resources

        readiness_score = (
            round((connected_tools / total_tools) * 100) if total_tools > 0 else 100
        )

        # Store plan in goal_execution_plans
        self._db.table("goal_execution_plans").insert(
            {
                "goal_id": goal_id,
                "tasks": json.dumps(tasks_json),
                "execution_mode": plan_data.get("execution_mode", "parallel"),
                "estimated_total_minutes": estimated_total,
                "reasoning": plan_data.get("reasoning", ""),
            }
        ).execute()

        # Create goal_milestones from tasks
        for i, task in enumerate(tasks_json):
            try:
                self._db.table("goal_milestones").insert(
                    {
                        "goal_id": goal_id,
                        "title": task.get("title", f"Task {i + 1}"),
                        "description": (
                            f"Agent: {task.get('agent', 'unknown')} | "
                            f"Risk: {task.get('risk_level', 'LOW')}"
                        ),
                        "status": "pending",
                        "sort_order": i,
                    }
                ).execute()
            except Exception as e:
                logger.warning("Failed to create milestone for task %d: %s", i, e)

        # Create goal_agents entries for each unique agent
        unique_agents = {task.get("agent", "analyst") for task in tasks_json}
        for agent_type in unique_agents:
            try:
                self._db.table("goal_agents").insert(
                    {
                        "goal_id": goal_id,
                        "agent_type": agent_type,
                        "agent_config": json.dumps(
                            {
                                "tasks": [
                                    t.get("title", "")
                                    for t in tasks_json
                                    if t.get("agent") == agent_type
                                ]
                            }
                        ),
                        "status": "pending",
                    }
                ).execute()
            except Exception as e:
                logger.warning(
                    "Failed to create goal_agent for %s: %s", agent_type, e
                )

        result = {
            "goal_id": goal_id,
            "tasks": tasks_json,
            "execution_mode": plan_data.get("execution_mode", "parallel"),
            "missing_integrations": missing_integrations,
            "approval_points": approval_points,
            "estimated_total_minutes": estimated_total,
            "readiness_score": readiness_score,
            "connected_integrations": active_integrations,
            "reasoning": plan_data.get("reasoning", ""),
        }

        # Emit plan via WebSocket with full resource context
        try:
            await ws_manager.send_aria_message(
                user_id=user_id,
                message=(
                    f"I've created an execution plan for **{goal.get('title', '')}** "
                    f"with {len(tasks_json)} tasks. Review it and approve when ready."
                ),
                rich_content=[
                    {
                        "type": "execution_plan",
                        "data": {
                            "goal_id": goal_id,
                            "title": goal.get("title", ""),
                            "tasks": tasks_json,
                            "missing_integrations": missing_integrations,
                            "approval_points": approval_points,
                            "estimated_total_minutes": estimated_total,
                            "readiness_score": readiness_score,
                            "connected_integrations": active_integrations,
                        },
                    }
                ],
                suggestions=[
                    "Approve the plan",
                    "What if we skip the outreach?",
                    "Can you add a research step?",
                ],
            )
        except Exception as e:
            logger.warning("Failed to send plan via WebSocket: %s", e)

        return result

    @staticmethod
    def _check_tool_connected(
        tool: str, active_integrations: list[str]
    ) -> bool:
        """Check if a tool is available given the user's active integrations.

        Args:
            tool: Tool identifier (e.g. 'exa_search', 'composio_crm').
            active_integrations: List of integration_type strings.

        Returns:
            True if the tool is available (either built-in or integration connected).
        """
        # Built-in tools that don't need user integrations
        builtin = {
            "exa_search", "pubmed_search", "fda_search", "chembl_search",
            "clinicaltrials_search", "claude_analysis", "claude_drafting",
            "digital_twin_style", "news_apis", "apollo_search",
        }
        if tool in builtin:
            return True

        # Map tools to required integration types
        tool_to_integration: dict[str, list[str]] = {
            "composio_crm": ["salesforce", "hubspot"],
            "composio_calendar": ["google_calendar", "outlook_calendar", "outlook"],
            "composio_email_send": ["gmail", "outlook", "outlook_email"],
            "salesforce": ["salesforce"],
            "hubspot": ["hubspot"],
            "google_calendar": ["google_calendar"],
            "gmail": ["gmail"],
            "outlook": ["outlook"],
        }

        required = tool_to_integration.get(tool, [])
        if not required:
            return True  # Unknown tool — assume available
        return any(i in active_integrations for i in required)

    async def execute_goal_async(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Start async background execution of a goal.

        Creates an asyncio.Task running _run_goal_background, updates
        goal status to 'active', and returns immediately.

        Args:
            goal_id: The goal to execute.
            user_id: The user who owns this goal.

        Returns:
            Dict with goal_id and status 'executing'.
        """
        # Update goal status to active
        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {"status": "active", "started_at": now, "updated_at": now}
        ).eq("id", goal_id).execute()

        # Launch background task
        task = asyncio.create_task(self._run_goal_background(goal_id, user_id))
        self._active_tasks[goal_id] = task

        # Clean up reference when done
        task.add_done_callback(lambda _t: self._active_tasks.pop(goal_id, None))

        logger.info(
            "Goal async execution started",
            extra={"goal_id": goal_id, "user_id": user_id},
        )

        return {"goal_id": goal_id, "status": "executing"}

    async def _run_goal_background(self, goal_id: str, user_id: str) -> None:
        """Background coroutine that executes a goal's plan.

        Loads or creates an execution plan, groups tasks by dependency
        order, executes each group, and publishes events via EventBus.

        Args:
            goal_id: The goal to execute.
            user_id: The user who owns this goal.
        """
        event_bus = EventBus.get_instance()

        try:
            # Load execution plan
            plan_result = (
                self._db.table("goal_execution_plans")
                .select("*")
                .eq("goal_id", goal_id)
                .order("created_at", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )

            if plan_result.data:
                tasks_raw = plan_result.data.get("tasks", "[]")
                tasks = json.loads(tasks_raw) if isinstance(tasks_raw, str) else tasks_raw
                # Extract execution_mode from stored plan or plan JSON
                execution_mode = plan_result.data.get("execution_mode", "sequential")
                if not execution_mode or execution_mode == "sequential":
                    # Check inside the plan JSON blob (reused_workflow stores it there)
                    plan_blob = plan_result.data.get("plan")
                    if plan_blob:
                        parsed = json.loads(plan_blob) if isinstance(plan_blob, str) else plan_blob
                        execution_mode = parsed.get("execution_mode", execution_mode)
            else:
                # Auto-plan if no plan exists
                plan = await self.plan_goal(goal_id, user_id)
                tasks = plan.get("tasks", [])
                execution_mode = plan.get("execution_mode", "sequential")

            if not tasks:
                await event_bus.publish(
                    GoalEvent(
                        goal_id=goal_id,
                        user_id=user_id,
                        event_type="goal.error",
                        data={"error": "No tasks in execution plan"},
                    )
                )
                return

            # Fetch goal for context
            goal_result = (
                self._db.table("goals")
                .select("*")
                .eq("id", goal_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            goal = goal_result.data or {"id": goal_id, "title": "Unknown", "config": {}}
            context = await self._gather_execution_context(user_id)

            total_tasks = len(tasks)
            completed_tasks = 0

            if execution_mode in ("parallel", "reused_workflow"):
                # Parallel execution: group tasks by dependency layers
                layers = self._build_dependency_layers(tasks)

                for layer in layers:
                    # Execute all tasks in this layer concurrently
                    layer_results = await asyncio.gather(
                        *[
                            self._execute_task_with_events(
                                task=t,
                                goal_id=goal_id,
                                user_id=user_id,
                                goal=goal,
                                context=context,
                            )
                            for t in layer
                        ],
                        return_exceptions=True,
                    )

                    # Process results from this layer
                    for lr in layer_results:
                        if isinstance(lr, BaseException):
                            logger.error(
                                "Unexpected exception in parallel task",
                                extra={"goal_id": goal_id, "error": str(lr)},
                            )
                        else:
                            completed_tasks += 1

                            progress = int((completed_tasks / total_tasks) * 100)
                            await event_bus.publish(
                                GoalEvent(
                                    goal_id=goal_id,
                                    user_id=user_id,
                                    event_type="progress.update",
                                    data={
                                        "progress": progress,
                                        "completed": completed_tasks,
                                        "total": total_tasks,
                                        "last_agent": lr.get("agent_type", ""),
                                    },
                                )
                            )

                    # Update goal progress in DB once per layer
                    layer_progress = int((completed_tasks / total_tasks) * 100)
                    self._db.table("goals").update(
                        {
                            "progress": layer_progress,
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                    ).eq("id", goal_id).execute()
            else:
                # Sequential execution: one task at a time
                for task in tasks:
                    task_result = await self._execute_task_with_events(
                        task=task,
                        goal_id=goal_id,
                        user_id=user_id,
                        goal=goal,
                        context=context,
                    )

                    completed_tasks += 1
                    progress = int((completed_tasks / total_tasks) * 100)

                    await event_bus.publish(
                        GoalEvent(
                            goal_id=goal_id,
                            user_id=user_id,
                            event_type="progress.update",
                            data={
                                "progress": progress,
                                "completed": completed_tasks,
                                "total": total_tasks,
                                "last_agent": task_result.get("agent_type", ""),
                            },
                        )
                    )

                    # Update goal progress in DB
                    self._db.table("goals").update(
                        {"progress": progress, "updated_at": datetime.now(UTC).isoformat()}
                    ).eq("id", goal_id).execute()

            # All tasks done — complete the goal
            await self.complete_goal_with_retro(goal_id, user_id)

            # Emit execution complete WS event for live frontend progress
            try:
                await ws_manager.send_execution_complete(
                    user_id=user_id,
                    goal_id=goal_id,
                    title=goal.get("title", "Unknown"),
                    success=True,
                    steps_completed=completed_tasks,
                    steps_total=total_tasks,
                )
            except Exception:
                logger.warning("Failed to send execution_complete WS event", extra={"goal_id": goal_id})

        except asyncio.CancelledError:
            logger.info("Goal background execution cancelled", extra={"goal_id": goal_id})
            raise
        except Exception as e:
            logger.error(
                "Goal background execution failed",
                extra={"goal_id": goal_id, "error": str(e)},
            )
            # Update goal status to reflect error
            self._db.table("goals").update(
                {"status": "paused", "updated_at": datetime.now(UTC).isoformat()}
            ).eq("id", goal_id).execute()

            await event_bus.publish(
                GoalEvent(
                    goal_id=goal_id,
                    user_id=user_id,
                    event_type="goal.error",
                    data={"error": str(e)},
                )
            )

            # Emit execution complete (failure) WS event
            try:
                _title = goal.get("title", "Unknown") if isinstance(goal, dict) else "Unknown"  # noqa: F841
                _completed = completed_tasks  # noqa: F841
                _total = total_tasks  # noqa: F841
            except NameError:
                _title = "Unknown"
                _completed = 0
                _total = 0
            try:
                await ws_manager.send_execution_complete(
                    user_id=user_id,
                    goal_id=goal_id,
                    title=_title,
                    success=False,
                    steps_completed=_completed,
                    steps_total=_total,
                    summary=str(e),
                )
            except Exception:
                logger.warning("Failed to send execution_complete WS event", extra={"goal_id": goal_id})

    async def _handle_agent_result(
        self,
        user_id: str,
        goal_id: str,
        agent_type: str,
        result: dict[str, Any],
        task: dict[str, Any],
    ) -> None:
        """Process an agent's execution result.

        Stores the execution, submits actions to the queue with
        appropriate risk levels, publishes completion events, and sends
        integration requests if the agent detected a missing connection.

        Args:
            user_id: The user ID.
            goal_id: The goal ID.
            agent_type: The agent type that produced the result.
            result: The agent execution result dict.
            task: The task definition dict.
        """
        event_bus = EventBus.get_instance()
        content = result.get("content", {})

        # Check for missing integration and send conversational request
        try:
            from src.services.integration_request import (
                IntegrationRequestService,
                check_agent_result_for_missing_integration,
            )

            missing = check_agent_result_for_missing_integration(result)
            if missing:
                svc = IntegrationRequestService()
                await svc.send_integration_request(
                    user_id=user_id,
                    integration_category=missing,
                    agent_name=agent_type,
                    task_description=task.get("title", "complete this task"),
                )
        except Exception:
            logger.debug("Integration request check failed", exc_info=True)

        # Publish agent completion event
        await event_bus.publish(
            GoalEvent(
                goal_id=goal_id,
                user_id=user_id,
                event_type="agent.completed",
                data={
                    "agent": agent_type,
                    "success": result.get("success", False),
                    "task_title": task.get("title", ""),
                },
            )
        )

        # Submit recommended actions to action queue
        if result.get("success") and isinstance(content, dict):
            await self._submit_actions_to_queue(
                user_id=user_id,
                agent_type=agent_type,
                content=content,
                goal_id=goal_id,
            )

    @staticmethod
    def _build_dependency_layers(tasks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group tasks into dependency layers for parallel execution.

        Uses topological sort to order tasks by dependencies:
        - Layer 0: tasks with no depends_on
        - Layer 1: tasks whose dependencies are all in layer 0
        - And so on...

        Circular dependencies are force-placed into a final layer with a
        safety cap to prevent infinite loops.

        Args:
            tasks: List of task dicts, each with "title" and optional "depends_on".

        Returns:
            List of layers, where each layer is a list of task dicts that
            can execute in parallel.
        """
        if not tasks:
            return []

        # Build lookup by title
        task_by_title: dict[str, dict[str, Any]] = {}
        for t in tasks:
            title = t.get("title", "")
            task_by_title[title] = t

        placed: set[str] = set()
        layers: list[list[dict[str, Any]]] = []
        remaining = list(tasks)

        # Safety cap: at most len(tasks) iterations to handle circular deps
        max_iterations = len(tasks)
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1
            layer: list[dict[str, Any]] = []

            for t in remaining:
                deps = t.get("depends_on", []) or []
                # A task is ready if all its dependencies are already placed
                if all(d in placed for d in deps):
                    layer.append(t)

            if not layer:
                # All remaining tasks have unresolved deps (circular).
                # Force-place them all into a final layer.
                layers.append(remaining)
                break

            layers.append(layer)
            for t in layer:
                placed.add(t.get("title", ""))
            remaining = [t for t in remaining if t.get("title", "") not in placed]

        return layers

    async def _execute_task_with_events(
        self,
        task: dict[str, Any],
        goal_id: str,
        user_id: str,
        goal: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single task and publish lifecycle events.

        Publishes agent.started before execution, calls _execute_agent and
        _handle_agent_result, and catches exceptions to publish failure events.

        Args:
            task: The task dict with title, agent_type, etc.
            goal_id: The goal ID.
            user_id: The user ID.
            goal: The full goal dict.
            context: Gathered execution context.

        Returns:
            Dict with task_title, agent_type, success, and optional error.
        """
        event_bus = EventBus.get_instance()
        agent_type = task.get("agent_type", "analyst")
        step_id = task.get("id", task.get("title", ""))

        await event_bus.publish(
            GoalEvent(
                goal_id=goal_id,
                user_id=user_id,
                event_type="agent.started",
                data={
                    "agent": agent_type,
                    "task_title": task.get("title", ""),
                },
            )
        )

        # Emit step-started WS event for live frontend progress
        try:
            await ws_manager.send_step_started(
                user_id=user_id,
                goal_id=goal_id,
                step_id=step_id,
                agent=agent_type,
                title=task.get("title", ""),
            )
        except Exception:
            logger.warning("Failed to send step_started WS event", extra={"goal_id": goal_id})

        try:
            result = await self._execute_agent(
                user_id=user_id,
                goal=goal,
                agent_type=agent_type,
                context=context,
            )

            await self._handle_agent_result(
                user_id=user_id,
                goal_id=goal_id,
                agent_type=agent_type,
                result=result,
                task=task,
            )

            # Emit step-completed WS event (success)
            try:
                await ws_manager.send_step_completed(
                    user_id=user_id,
                    goal_id=goal_id,
                    step_id=step_id,
                    agent=agent_type,
                    success=result.get("success", False),
                    result_summary=result.get("summary"),
                )
            except Exception:
                logger.warning("Failed to send step_completed WS event", extra={"goal_id": goal_id})

            return {
                "task_title": task.get("title", ""),
                "agent_type": agent_type,
                "success": result.get("success", False),
            }

        except Exception as e:
            logger.error(
                "Agent task failed in background execution",
                extra={
                    "goal_id": goal_id,
                    "agent_type": agent_type,
                    "error": str(e),
                },
            )
            await event_bus.publish(
                GoalEvent(
                    goal_id=goal_id,
                    user_id=user_id,
                    event_type="agent.completed",
                    data={
                        "agent": agent_type,
                        "success": False,
                        "error": str(e),
                    },
                )
            )

            # Emit step-completed WS event (failure)
            try:
                await ws_manager.send_step_completed(
                    user_id=user_id,
                    goal_id=goal_id,
                    step_id=step_id,
                    agent=agent_type,
                    success=False,
                    error_message=str(e),
                )
            except Exception:
                logger.warning("Failed to send step_completed WS event", extra={"goal_id": goal_id})

            return {
                "task_title": task.get("title", ""),
                "agent_type": agent_type,
                "success": False,
                "error": str(e),
            }

    async def check_progress(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Get a progress snapshot for a goal.

        Reads goal status, execution plan, and recent agent executions
        to build a comprehensive progress view.

        Args:
            goal_id: The goal to check.
            user_id: The user who owns this goal.

        Returns:
            Progress snapshot dict.
        """
        # Fetch goal
        goal_result = (
            self._db.table("goals")
            .select("id, title, status, progress, started_at, updated_at")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        goal = goal_result.data
        if not goal:
            return {"goal_id": goal_id, "error": "Goal not found"}

        # Fetch latest plan
        plan_result = (
            self._db.table("goal_execution_plans")
            .select("tasks, execution_mode, reasoning")
            .eq("goal_id", goal_id)
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        plan = plan_result.data

        # Fetch recent executions
        exec_result = (
            self._db.table("agent_executions")
            .select("goal_agent_id, status, started_at, completed_at, output")
            .eq("goal_agent_id", goal_id)
            .order("completed_at", desc=True)
            .limit(10)
            .execute()
        )
        executions = exec_result.data or []

        return {
            "goal_id": goal_id,
            "title": goal.get("title", ""),
            "status": goal.get("status", "unknown"),
            "progress": goal.get("progress", 0),
            "started_at": goal.get("started_at"),
            "updated_at": goal.get("updated_at"),
            "plan": plan,
            "recent_executions": executions,
            "is_running": goal_id in self._active_tasks,
        }

    async def report_progress(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Generate a narrative progress report for a goal.

        Uses LLM to summarize the current progress into a human-readable
        report suitable for display in the conversation.

        Args:
            goal_id: The goal to report on.
            user_id: The user who owns this goal.

        Returns:
            Dict with goal_id and report narrative.
        """
        progress = await self.check_progress(goal_id, user_id)

        prompt = (
            f"Generate a brief progress report for this goal:\n\n"
            f"Title: {progress.get('title', 'Unknown')}\n"
            f"Status: {progress.get('status', 'unknown')}\n"
            f"Progress: {progress.get('progress', 0)}%\n"
            f"Plan: {json.dumps(progress.get('plan'), default=str)}\n"
            f"Recent executions: {len(progress.get('recent_executions', []))}\n\n"
            "Respond with JSON:\n"
            '{"summary": "1-2 sentence overview", "details": "key findings", '
            '"next_steps": ["what happens next"]}'
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are ARIA reporting on goal progress. Be concise and specific. "
                "Respond with JSON only."
            ),
            max_tokens=1024,
            temperature=0.3,
        )

        try:
            report = json.loads(response)
        except json.JSONDecodeError:
            report = {"summary": response.strip(), "details": "", "next_steps": []}

        return {"goal_id": goal_id, "report": report}

    async def complete_goal_with_retro(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Mark a goal as complete and generate a retrospective.

        Updates goal status, generates a retrospective via GoalService,
        and publishes a goal.complete event.

        Args:
            goal_id: The goal to complete.
            user_id: The user who owns this goal.

        Returns:
            Dict with status and retrospective data.
        """
        from src.services.goal_service import GoalService

        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {
                "status": "complete",
                "progress": 100,
                "completed_at": now,
                "updated_at": now,
            }
        ).eq("id", goal_id).execute()

        await self._record_goal_update(
            goal_id,
            "milestone",
            "Goal marked complete with retrospective",
            progress_delta=100,
        )

        # Generate retrospective
        retro = None
        try:
            goal_service = GoalService()
            retro = await goal_service.generate_retrospective(user_id, goal_id)
        except Exception as e:
            logger.warning("Failed to generate retrospective: %s", e)

        # Store executed plan as procedural memory workflow
        try:
            import uuid as uuid_mod

            from src.memory.procedural import ProceduralMemory, Workflow

            procedural = ProceduralMemory()
            # Get the execution plan for this goal
            plan_result = (
                self._db.table("goal_execution_plans")
                .select("plan, tasks")
                .eq("goal_id", goal_id)
                .order("created_at", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if plan_result and plan_result.data:
                # Try 'plan' column first, then 'tasks' column
                plan_raw = plan_result.data.get("plan") or plan_result.data.get("tasks", "[]")
                plan_data = json.loads(plan_raw) if isinstance(plan_raw, str) else plan_raw

                # Extract tasks list — could be in plan_data.tasks or plan_data itself
                steps = (
                    plan_data.get("tasks", plan_data) if isinstance(plan_data, dict) else plan_data
                )

                # Fetch goal info for trigger conditions
                goal_result = (
                    self._db.table("goals")
                    .select("goal_type, title")
                    .eq("id", goal_id)
                    .maybe_single()
                    .execute()
                )
                goal_info = goal_result.data if goal_result and goal_result.data else {}

                workflow = Workflow(
                    id=str(uuid_mod.uuid4()),
                    user_id=user_id,
                    workflow_name=f"Workflow for goal: {goal_id}",
                    description=goal_info.get("title", ""),
                    trigger_conditions={
                        "goal_type": goal_info.get("goal_type", ""),
                    },
                    steps=steps if isinstance(steps, list) else [],
                    success_count=1,
                    failure_count=0,
                    is_shared=False,
                    version=1,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                await procedural.create_workflow(workflow)
        except Exception as e:
            logger.debug("Failed to store procedural memory: %s", e)

        # Publish completion event
        event_bus = EventBus.get_instance()
        await event_bus.publish(
            GoalEvent(
                goal_id=goal_id,
                user_id=user_id,
                event_type="goal.complete",
                data={"retrospective": retro},
            )
        )

        # Send WebSocket completion notification to user
        try:
            goal_title = ""
            try:
                goal_result = (
                    self._db.table("goals")
                    .select("title")
                    .eq("id", goal_id)
                    .maybe_single()
                    .execute()
                )
                if goal_result and goal_result.data:
                    goal_title = goal_result.data.get("title", "")
            except Exception:
                pass

            summary = (
                retro.get("summary", "") if retro else f"Goal '{goal_title}' completed."
            )
            message = (
                f"Your goal is complete: {goal_title}. {summary}"
                if goal_title
                else f"Goal completed. {summary}"
            )

            await ws_manager.send_aria_message(
                user_id=user_id,
                message=message,
                rich_content=[
                    {
                        "type": "goal_retrospective",
                        "data": {
                            "goal_id": goal_id,
                            "retrospective": retro,
                        },
                    }
                ]
                if retro
                else [],
                suggestions=["Show details", "What's next?"],
            )

            await ws_manager.send_execution_complete(
                user_id=user_id,
                goal_id=goal_id,
                title=goal_title,
                success=True,
                steps_completed=1,
                steps_total=1,
                summary=summary,
            )
        except Exception:
            logger.debug(
                "Failed to send goal completion WS notification",
                extra={"goal_id": goal_id},
                exc_info=True,
            )

        logger.info(
            "Goal completed with retrospective",
            extra={"goal_id": goal_id, "user_id": user_id},
        )

        return {"goal_id": goal_id, "status": "complete", "retrospective": retro}

    async def cancel_goal(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Cancel a running goal's background execution.

        Cancels the asyncio.Task if running, updates goal status to
        'paused', and publishes a goal.error event.

        Args:
            goal_id: The goal to cancel.
            user_id: The user who owns this goal.

        Returns:
            Dict with goal_id and status.
        """
        # Cancel background task if running
        task = self._active_tasks.pop(goal_id, None)
        if task and not task.done():
            task.cancel()

        # Update goal status
        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update({"status": "paused", "updated_at": now}).eq(
            "id", goal_id
        ).execute()

        # Publish cancellation event
        event_bus = EventBus.get_instance()
        await event_bus.publish(
            GoalEvent(
                goal_id=goal_id,
                user_id=user_id,
                event_type="goal.error",
                data={"reason": "cancelled_by_user"},
            )
        )

        logger.info("Goal cancelled", extra={"goal_id": goal_id, "user_id": user_id})

        return {"goal_id": goal_id, "status": "cancelled"}
