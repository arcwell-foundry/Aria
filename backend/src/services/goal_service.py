"""Goal service for ARIA.

This service handles:
- Creating and querying goals
- Managing goal lifecycle (start, pause, complete)
- Tracking goal progress and agent executions
- Dashboard views, milestones, retrospectives, and ARIA collaboration
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.models.goal import GoalCreate, GoalStatus, GoalUpdate

logger = logging.getLogger(__name__)


class GoalService:
    """Service for goal management and execution."""

    def __init__(self) -> None:
        """Initialize goal service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def create_goal(self, user_id: str, data: GoalCreate) -> dict[str, Any]:
        """Create a new goal.

        Args:
            user_id: The user's ID.
            data: Goal creation data.

        Returns:
            Created goal dict.
        """
        logger.info(
            "Creating goal",
            extra={
                "user_id": user_id,
                "title": data.title,
                "goal_type": data.goal_type.value,
            },
        )

        result = (
            self._db.table("goals")
            .insert(
                {
                    "user_id": user_id,
                    "title": data.title,
                    "description": data.description,
                    "goal_type": data.goal_type.value,
                    "config": data.config,
                    "status": GoalStatus.DRAFT.value,
                    "progress": 0,
                }
            )
            .execute()
        )

        goal = cast(dict[str, Any], result.data[0])
        logger.info("Goal created", extra={"goal_id": goal["id"]})
        return goal

    async def get_goal(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Get a goal by ID with its agents.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Goal dict with agents, or None if not found.
        """
        result = (
            self._db.table("goals")
            .select("*, goal_agents(*)")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if result.data is None:
            logger.warning("Goal not found", extra={"user_id": user_id, "goal_id": goal_id})
            return None

        logger.info("Goal retrieved", extra={"goal_id": goal_id})
        return cast(dict[str, Any], result.data)

    async def list_goals(
        self,
        user_id: str,
        status: GoalStatus | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List user's goals.

        Args:
            user_id: The user's ID.
            status: Optional filter by goal status.
            limit: Maximum number of goals to return.

        Returns:
            List of goal dicts.
        """
        query = self._db.table("goals").select("*").eq("user_id", user_id)

        if status:
            query = query.eq("status", status.value)

        result = query.order("created_at", desc=True).limit(limit).execute()

        logger.info(
            "Goals listed",
            extra={"user_id": user_id, "count": len(result.data)},
        )

        return cast(list[dict[str, Any]], result.data)

    async def update_goal(
        self,
        user_id: str,
        goal_id: str,
        data: GoalUpdate,
    ) -> dict[str, Any] | None:
        """Update a goal.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.
            data: Goal update data.

        Returns:
            Updated goal dict, or None if not found.
        """
        # Build update dict, converting enums to values
        update_data: dict[str, Any] = {
            k: v.value if hasattr(v, "value") else v
            for k, v in data.model_dump(exclude_unset=True).items()
        }
        update_data["updated_at"] = datetime.now(UTC).isoformat()

        result = (
            self._db.table("goals")
            .update(update_data)
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Goal updated", extra={"goal_id": goal_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for update", extra={"goal_id": goal_id})
        return None

    async def delete_goal(self, user_id: str, goal_id: str) -> bool:
        """Delete a goal.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            True if successful.
        """
        self._db.table("goals").delete().eq("id", goal_id).eq("user_id", user_id).execute()

        logger.info("Goal deleted", extra={"goal_id": goal_id})
        return True

    async def start_goal(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Start goal execution.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Updated goal dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("goals")
            .update(
                {
                    "status": GoalStatus.ACTIVE.value,
                    "started_at": now,
                    "updated_at": now,
                }
            )
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Goal started", extra={"goal_id": goal_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for start", extra={"goal_id": goal_id})
        return None

    async def pause_goal(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Pause goal execution.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Updated goal dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("goals")
            .update(
                {
                    "status": GoalStatus.PAUSED.value,
                    "updated_at": now,
                }
            )
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Goal paused", extra={"goal_id": goal_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for pause", extra={"goal_id": goal_id})
        return None

    async def complete_goal(
        self,
        user_id: str,
        goal_id: str,
    ) -> dict[str, Any] | None:
        """Complete a goal: update status, generate retrospective, update readiness."""
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {
                "status": "complete",
                "progress": 100,
                "completed_at": now,
                "updated_at": now,
            }
        ).eq("id", goal_id).eq("user_id", user_id).execute()

        # Generate retrospective
        retro = await self.generate_retrospective(user_id, goal_id)

        # Update readiness — goal_clarity domain
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(user_id, {"goal_clarity": 10.0})
        except Exception as e:
            logger.warning("Failed to update readiness on goal completion: %s", e)

        logger.info(
            "Goal completed",
            extra={"goal_id": goal_id, "user_id": user_id},
        )

        return {**goal, "status": "complete", "retrospective": retro}

    async def update_progress(
        self,
        user_id: str,
        goal_id: str,
        progress: int,
    ) -> dict[str, Any] | None:
        """Update goal progress.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.
            progress: Progress value (0-100, will be clamped).

        Returns:
            Updated goal dict, or None if not found.
        """
        clamped_progress = max(0, min(100, progress))
        now = datetime.now(UTC).isoformat()

        result = (
            self._db.table("goals")
            .update(
                {
                    "progress": clamped_progress,
                    "updated_at": now,
                }
            )
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info(
                "Goal progress updated",
                extra={"goal_id": goal_id, "progress": clamped_progress},
            )
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for progress update", extra={"goal_id": goal_id})
        return None

    async def get_goal_progress(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Get goal with execution progress.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Goal dict with recent executions, or None if not found.
        """
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        # Get agent executions for each agent
        agents = goal.get("goal_agents", [])
        executions: list[dict[str, Any]] = []

        for agent in agents:
            exec_result = (
                self._db.table("agent_executions")
                .select("*")
                .eq("goal_agent_id", agent["id"])
                .order("started_at", desc=True)
                .limit(5)
                .execute()
            )
            executions.extend(cast(list[dict[str, Any]], exec_result.data))

        logger.info(
            "Goal progress retrieved",
            extra={"goal_id": goal_id, "execution_count": len(executions)},
        )

        return {
            **goal,
            "recent_executions": executions,
        }

    # ------------------------------------------------------------------ #
    # Lifecycle methods (US-936)                                          #
    # ------------------------------------------------------------------ #

    async def get_dashboard(self, user_id: str) -> list[dict[str, Any]]:
        """Get dashboard view of goals with milestone counts.

        Queries goals with joined goal_agents and goal_milestones, computes
        milestone_total and milestone_complete per goal.

        Args:
            user_id: The user's ID.

        Returns:
            List of goal dicts ordered by created_at desc, each with
            milestone_total and milestone_complete keys.
        """
        result = (
            self._db.table("goals")
            .select("*, goal_agents(*), goal_milestones(*)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        goals = cast(list[dict[str, Any]], result.data)

        for goal in goals:
            milestones = goal.get("goal_milestones") or []
            goal["milestone_total"] = len(milestones)
            goal["milestone_complete"] = sum(1 for m in milestones if m.get("status") == "complete")

        logger.info(
            "Dashboard retrieved",
            extra={"user_id": user_id, "goal_count": len(goals)},
        )
        return goals

    async def create_with_aria(
        self,
        user_id: str,
        title: str,
        description: str | None,
    ) -> dict[str, Any]:
        """Create a goal collaboratively with ARIA using LLM refinement.

        Sends the user's goal idea to Claude for SMART refinement and returns
        suggestions including refined title/description, sub-tasks, agent
        assignments, and a suggested timeline.

        Args:
            user_id: The user's ID.
            title: Raw goal title from user.
            description: Optional raw goal description.

        Returns:
            Dict with ARIA's SMART refinement suggestions.
        """
        prompt = (
            "You are ARIA, an AI sales assistant. A user wants to create a goal.\n\n"
            f"Title: {title}\n"
            f"Description: {description or 'N/A'}\n\n"
            "Refine this into a SMART goal and respond with ONLY a JSON object:\n"
            "{\n"
            '  "refined_title": "...",\n'
            '  "refined_description": "...",\n'
            '  "smart_score": 0-100,\n'
            '  "sub_tasks": [{"title": "...", "description": "..."}],\n'
            '  "agent_assignments": ["hunter"|"analyst"|"strategist"|"scribe"'
            '|"operator"|"scout"],\n'
            '  "suggested_timeline_days": N,\n'
            '  "reasoning": "..."\n'
            "}"
        )

        llm = LLMClient()
        try:
            raw = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.4,
            )
            suggestion = json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("ARIA goal refinement parse failed: %s", exc)
            suggestion = {
                "refined_title": title,
                "refined_description": description or "",
                "smart_score": 50,
                "sub_tasks": [],
                "agent_assignments": ["analyst"],
                "suggested_timeline_days": 14,
                "reasoning": "Unable to refine automatically; defaults applied.",
            }

        logger.info(
            "ARIA goal collaboration completed",
            extra={"user_id": user_id, "smart_score": suggestion.get("smart_score")},
        )
        return cast(dict[str, Any], suggestion)

    async def get_templates(
        self,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get goal templates, optionally filtered by role.

        Uses FirstGoalService.TEMPLATES as the canonical source and flattens
        them into a list.

        Args:
            role: Optional role to filter templates by.

        Returns:
            List of template dicts.
        """
        from src.onboarding.first_goal import FirstGoalService

        svc = FirstGoalService.__new__(FirstGoalService)
        all_templates: list[dict[str, Any]] = []

        for templates in svc.TEMPLATES.values():
            for tpl in templates:
                if role and not any(role.lower() in r.lower() for r in tpl.applicable_roles):
                    continue
                all_templates.append(tpl.model_dump())

        logger.info(
            "Templates retrieved",
            extra={"role": role, "count": len(all_templates)},
        )
        return all_templates

    async def add_milestone(
        self,
        user_id: str,
        goal_id: str,
        title: str,
        description: str | None = None,
        due_date: str | None = None,
    ) -> dict[str, Any] | None:
        """Add a milestone to a goal.

        Verifies goal ownership, determines sort_order, then inserts into
        the goal_milestones table.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.
            title: Milestone title.
            description: Optional milestone description.
            due_date: Optional due date (ISO string).

        Returns:
            Created milestone dict, or None if goal not found.
        """
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        # Determine next sort_order
        existing = (
            self._db.table("goal_milestones")
            .select("sort_order")
            .eq("goal_id", goal_id)
            .order("sort_order", desc=True)
            .limit(1)
            .execute()
        )

        max_order: int = 0
        if existing.data:
            row = cast(dict[str, Any], existing.data[0])
            max_order = int(row.get("sort_order", 0))

        insert_data: dict[str, Any] = {
            "goal_id": goal_id,
            "title": title,
            "description": description,
            "status": "pending",
            "sort_order": max_order + 1,
        }
        if due_date:
            insert_data["due_date"] = due_date

        result = self._db.table("goal_milestones").insert(insert_data).execute()

        milestone = cast(dict[str, Any], result.data[0])
        logger.info(
            "Milestone added",
            extra={"goal_id": goal_id, "milestone_id": milestone["id"]},
        )
        return milestone

    async def complete_milestone(
        self,
        user_id: str,
        goal_id: str,
        milestone_id: str,
    ) -> dict[str, Any] | None:
        """Mark a milestone as complete.

        Verifies goal ownership before updating the milestone status.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.
            milestone_id: The milestone ID.

        Returns:
            Updated milestone dict, or None if goal not found.
        """
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("goal_milestones")
            .update({"status": "complete", "completed_at": now})
            .eq("id", milestone_id)
            .eq("goal_id", goal_id)
            .execute()
        )

        if result.data:
            logger.info(
                "Milestone completed",
                extra={
                    "goal_id": goal_id,
                    "milestone_id": milestone_id,
                },
            )

            # Check if all milestones done → auto-complete goal
            all_ms = (
                self._db.table("goal_milestones").select("status").eq("goal_id", goal_id).execute()
            )
            all_statuses = [m.get("status") for m in (all_ms.data or [])]
            if all_statuses and all(s in ("complete", "skipped") for s in all_statuses):
                await self.complete_goal(user_id, goal_id)

            return cast(dict[str, Any], result.data[0])

        logger.warning(
            "Milestone not found for completion",
            extra={"milestone_id": milestone_id},
        )
        return None

    async def generate_retrospective(
        self,
        user_id: str,
        goal_id: str,
    ) -> dict[str, Any] | None:
        """Generate an AI-powered retrospective for a goal.

        Gathers goal data, milestones, and agent executions, then asks the
        LLM to produce a structured retrospective which is upserted into
        the goal_retrospectives table.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Retrospective dict, or None if goal not found.
        """
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        # Gather milestones
        ms_result = (
            self._db.table("goal_milestones")
            .select("*")
            .eq("goal_id", goal_id)
            .order("sort_order")
            .execute()
        )
        milestones = cast(list[dict[str, Any]], ms_result.data)

        # Gather agent executions
        agents = goal.get("goal_agents") or []
        executions: list[dict[str, Any]] = []
        for agent in agents:
            exec_result = (
                self._db.table("agent_executions")
                .select("*")
                .eq("goal_agent_id", agent["id"])
                .order("started_at", desc=True)
                .limit(20)
                .execute()
            )
            executions.extend(cast(list[dict[str, Any]], exec_result.data))

        prompt = (
            "You are ARIA. Analyze this goal and produce a retrospective.\n\n"
            f"Goal: {json.dumps(goal, default=str)}\n"
            f"Milestones: {json.dumps(milestones, default=str)}\n"
            f"Executions: {json.dumps(executions, default=str)}\n\n"
            "Respond with ONLY a JSON object:\n"
            "{\n"
            '  "summary": "...",\n'
            '  "what_worked": ["..."],\n'
            '  "what_didnt": ["..."],\n'
            '  "time_analysis": {"total_days": N, "active_days": N},\n'
            '  "agent_effectiveness": {"agent_type": {"tasks": N, "success_rate": 0.0}},\n'
            '  "learnings": ["..."]\n'
            "}"
        )

        llm = LLMClient()
        try:
            raw = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
            )
            retro_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Retrospective parse failed: %s", exc)
            retro_data = {
                "summary": "Retrospective generation failed.",
                "what_worked": [],
                "what_didnt": [],
                "time_analysis": {},
                "agent_effectiveness": {},
                "learnings": [],
            }

        now = datetime.now(UTC).isoformat()
        upsert_payload: dict[str, Any] = {
            "goal_id": goal_id,
            "summary": retro_data.get("summary", ""),
            "what_worked": retro_data.get("what_worked", []),
            "what_didnt": retro_data.get("what_didnt", []),
            "time_analysis": retro_data.get("time_analysis", {}),
            "agent_effectiveness": retro_data.get("agent_effectiveness", {}),
            "learnings": retro_data.get("learnings", []),
            "updated_at": now,
        }

        result = (
            self._db.table("goal_retrospectives")
            .upsert(upsert_payload, on_conflict="goal_id")
            .execute()
        )

        retro = cast(dict[str, Any], result.data[0])
        logger.info(
            "Retrospective generated",
            extra={"goal_id": goal_id, "retro_id": retro.get("id")},
        )
        return retro

    async def get_goal_detail(
        self,
        user_id: str,
        goal_id: str,
    ) -> dict[str, Any] | None:
        """Get full goal detail including milestones and retrospective.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Goal dict with milestones and retrospective keys,
            or None if goal not found.
        """
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        # Get milestones ordered by sort_order
        ms_result = (
            self._db.table("goal_milestones")
            .select("*")
            .eq("goal_id", goal_id)
            .order("sort_order")
            .execute()
        )
        milestones = cast(list[dict[str, Any]], ms_result.data)

        # Get retrospective (may not exist)
        retro_result = (
            self._db.table("goal_retrospectives")
            .select("*")
            .eq("goal_id", goal_id)
            .maybe_single()
            .execute()
        )
        retrospective: dict[str, Any] | None = None
        if retro_result is not None:
            retrospective = cast(dict[str, Any] | None, retro_result.data)

        logger.info(
            "Goal detail retrieved",
            extra={
                "goal_id": goal_id,
                "milestone_count": len(milestones),
                "has_retro": retrospective is not None,
            },
        )

        return {
            **goal,
            "milestones": milestones,
            "retrospective": retrospective,
        }
