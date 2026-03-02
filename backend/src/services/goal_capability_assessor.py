"""Goal Capability Assessor — thin facade over existing provisioning services.

Wraps GapDetectionService, CapabilityGraphService, ResolutionEngine,
and ProvisioningConversation to annotate goal plan tasks with
capability_status (ready/degraded/blocked) at planning time.
"""

from __future__ import annotations

import logging
from typing import Any

from src.models.capability import CapabilityGap, TaskCapabilityReport
from src.services.capability_provisioning import (
    CapabilityGraphService,
    GapDetectionService,
    ProvisioningConversation,
    ResolutionEngine,
)

logger = logging.getLogger(__name__)


class GoalCapabilityAssessor:
    """Assesses capability readiness for each task in a goal plan.

    Delegates all heavy lifting to existing provisioning services:
    - GapDetectionService.analyze_capabilities_for_plan() for LLM inference + graph lookup
    - CapabilityGraphService.get_best_available() for provider resolution
    - ResolutionEngine.generate_strategies() for resolution options
    - ProvisioningConversation.format_gap_message() for natural language messages
    """

    def __init__(self, db_client: Any) -> None:
        self._db = db_client
        self._graph = CapabilityGraphService(db_client)
        self._resolution = ResolutionEngine(db_client, self._graph)
        self._detector = GapDetectionService(db_client, self._graph, self._resolution)
        self._conversation = ProvisioningConversation()

    async def assess_plan(
        self,
        tasks: list[dict[str, Any]],
        user_id: str,
        goal_title: str,
    ) -> dict[str, Any]:
        """Assess capability readiness for each task in a plan.

        Args:
            tasks: List of task dicts from the goal plan (each has title, agent_type, etc.)
            user_id: The user's ID for checking integrations.
            goal_title: Goal title for message formatting.

        Returns:
            Dict with keys: task_reports, has_blocking, has_degraded, all_gaps, gap_message.
        """
        task_reports: list[TaskCapabilityReport] = []
        all_gaps: list[CapabilityGap] = []

        for task in tasks:
            task_title = task.get("title", task.get("description", "Unknown task"))
            step_desc = task.get("description", task_title)

            # Wrap single task as a mini-plan for GapDetectionService
            mini_plan = {"steps": [{"description": step_desc}]}

            try:
                gaps = await self._detector.analyze_capabilities_for_plan(
                    mini_plan, user_id
                )
            except Exception:
                logger.warning(
                    "Capability assessment failed for task, defaulting to ready",
                    extra={"task_title": task_title, "user_id": user_id},
                )
                task_reports.append(
                    TaskCapabilityReport(
                        task_title=task_title,
                        capability_status="ready",
                    )
                )
                continue

            blocking = [g for g in gaps if g.severity == "blocking"]
            degraded = [g for g in gaps if g.severity == "degraded"]
            all_gaps.extend(gaps)

            if blocking:
                task_reports.append(
                    TaskCapabilityReport(
                        task_title=task_title,
                        capability_status="blocked",
                        gaps=gaps,
                        blocking_capabilities=[g.capability for g in blocking],
                    )
                )
            elif degraded:
                notes = []
                for g in degraded:
                    provider = g.current_provider or "fallback"
                    quality_pct = int(g.current_quality * 100)
                    notes.append(
                        f"{g.capability}: using {provider} (~{quality_pct}% accuracy)"
                    )
                task_reports.append(
                    TaskCapabilityReport(
                        task_title=task_title,
                        capability_status="degraded",
                        gaps=gaps,
                        degradation_notes=notes,
                    )
                )
            else:
                task_reports.append(
                    TaskCapabilityReport(
                        task_title=task_title,
                        capability_status="ready",
                    )
                )

        has_blocking = any(r.capability_status == "blocked" for r in task_reports)
        has_degraded = any(r.capability_status == "degraded" for r in task_reports)

        # Generate natural language gap message if there are gaps
        gap_message = ""
        if all_gaps:
            try:
                gap_message = await self._conversation.format_gap_message(
                    all_gaps, goal_title
                )
            except Exception:
                logger.warning("Failed to format gap message", exc_info=True)

        return {
            "task_reports": task_reports,
            "has_blocking": has_blocking,
            "has_degraded": has_degraded,
            "all_gaps": all_gaps,
            "gap_message": gap_message,
        }

    async def check_gaps_resolved(
        self,
        blocked_tasks: list[dict[str, Any]],
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Re-assess previously blocked tasks to see if gaps are now resolved.

        Args:
            blocked_tasks: List of task dicts that were previously blocked.
            user_id: The user's ID.

        Returns:
            List of task dicts that are now unblocked (capability_status changed from blocked).
        """
        unblocked: list[dict[str, Any]] = []

        for task in blocked_tasks:
            blocking_caps = task.get("blocking_capabilities", [])
            still_blocked = False

            for cap_name in blocking_caps:
                best = await self._graph.get_best_available(cap_name, user_id)
                if best is None:
                    still_blocked = True
                    break

            if not still_blocked:
                unblocked.append(task)

        return unblocked
