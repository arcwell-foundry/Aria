"""Unified memory query service.

Queries across all memory types (episodic, semantic, procedural, prospective,
lead) in parallel and returns results ranked by relevance.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, cast

logger = logging.getLogger(__name__)


class MemoryQueryService:
    """Service for querying across all memory types."""

    async def query(
        self,
        user_id: str,
        query: str,
        memory_types: list[str],
        start_date: datetime | None,
        end_date: datetime | None,
        min_confidence: float | None,
        limit: int,
        offset: int,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query across specified memory types.

        Args:
            user_id: The user ID to query memories for.
            query: The search query string.
            memory_types: List of memory types to search.
            start_date: Optional start of time range filter.
            end_date: Optional end of time range filter.
            min_confidence: Minimum confidence threshold for semantic results.
            limit: Maximum results to return.
            offset: Number of results to skip.
            as_of: Point in time for temporal query. Returns memories as known at this date.

        Returns:
            List of memory results sorted by relevance.
        """
        tasks = []

        if "episodic" in memory_types:
            tasks.append(self._query_episodic(user_id, query, start_date, end_date, limit, as_of))
        if "semantic" in memory_types:
            tasks.append(self._query_semantic(user_id, query, limit, min_confidence, as_of))
        if "procedural" in memory_types:
            tasks.append(self._query_procedural(user_id, query, limit))
        if "prospective" in memory_types:
            tasks.append(self._query_prospective(user_id, query, limit))
        if "lead" in memory_types:
            tasks.append(self._query_lead(user_id, query, limit))

        # Execute all queries in parallel
        results_lists: list[list[dict[str, Any]] | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        # Flatten results, filtering out exceptions
        all_results: list[dict[str, Any]] = []
        for result in results_lists:
            if isinstance(result, BaseException):
                logger.warning("Memory query failed: %s", result)
                continue
            all_results.extend(result)

        # Sort by relevance score descending
        all_results.sort(key=lambda x: float(x.get("relevance_score", 0.0)), reverse=True)

        # Apply offset and limit
        return all_results[offset : offset + limit]

    async def _query_episodic(
        self,
        user_id: str,
        query: str,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query episodic memory.

        Args:
            user_id: The user ID to query memories for.
            query: The search query string.
            start_date: If provided, only episodes on or after this date.
            end_date: If provided, only episodes on or before this date.
            limit: Maximum results to return.
            as_of: Point in time filter. Only includes episodes recorded on or before this date.
        """
        from src.memory.episodic import EpisodicMemory

        # Note: Creating memory instance per request is acceptable - classes are
        # lightweight and stateless. Could optimize with DI if needed in future.
        memory = EpisodicMemory()
        episodes = await memory.semantic_search(
            user_id, query, limit=limit, as_of=as_of,
            start_date=start_date, end_date=end_date,
        )

        results = []
        for episode in episodes:
            relevance = self._calculate_text_relevance(query, episode.content)
            results.append(
                {
                    "id": episode.id,
                    "memory_type": "episodic",
                    "content": f"[{episode.event_type}] {episode.content}",
                    "relevance_score": relevance,
                    "confidence": None,
                    "timestamp": episode.occurred_at,
                }
            )

        return results

    async def _query_semantic(
        self,
        user_id: str,
        query: str,
        limit: int,
        min_confidence: float | None = None,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query semantic memory.

        Args:
            user_id: The user ID to query memories for.
            query: The search query string.
            limit: Maximum results to return.
            min_confidence: Minimum confidence threshold for filtering.
            as_of: Point in time for temporal validity and confidence calculation.
        """
        from src.memory.semantic import SemanticMemory

        memory = SemanticMemory()
        facts = await memory.search_facts(
            user_id, query, min_confidence=0.0, limit=limit, as_of=as_of
        )

        results = []
        for fact in facts:
            # Calculate effective confidence with decay and boosts at the as_of time
            effective_confidence = memory.get_effective_confidence(fact, as_of=as_of)

            # Filter by minimum confidence threshold
            if min_confidence is not None and effective_confidence < min_confidence:
                continue

            relevance = self._calculate_text_relevance(
                query, f"{fact.subject} {fact.predicate} {fact.object}"
            )
            results.append(
                {
                    "id": fact.id,
                    "memory_type": "semantic",
                    "content": f"{fact.subject} {fact.predicate} {fact.object}",
                    "relevance_score": relevance,
                    "confidence": effective_confidence,
                    "timestamp": fact.valid_from,
                }
            )

        return results

    async def _query_procedural(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query procedural memory.

        Returns all workflows for the user, scored by text relevance.
        Workflows are typically few and always useful as context, so we
        include all of them with at least a baseline relevance score.
        """
        from src.memory.procedural import ProceduralMemory

        memory = ProceduralMemory()
        workflows = await memory.list_workflows(user_id, include_shared=True)

        results = []
        for workflow in workflows:
            text = f"{workflow.workflow_name} {workflow.description}"
            relevance = self._calculate_text_relevance(query, text)
            # Always include workflows as context, with a minimum relevance floor
            relevance = max(relevance, 0.3)
            steps_summary = ", ".join(
                s.get("action", s.get("name", "step")) for s in workflow.steps[:5]
            )
            results.append(
                {
                    "id": workflow.id,
                    "memory_type": "procedural",
                    "content": (
                        f"Workflow: {workflow.workflow_name} — {workflow.description}"
                        f" | Steps: {steps_summary}"
                        f" | Success rate: {workflow.success_rate:.0%}"
                    ),
                    "relevance_score": relevance,
                    "confidence": workflow.success_rate,
                    "timestamp": workflow.created_at,
                }
            )

        results.sort(key=lambda x: cast(float, x["relevance_score"]), reverse=True)
        return results[:limit]

    async def _query_prospective(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query prospective memory.

        Fetches both upcoming and overdue tasks so ARIA is aware of
        what's pending and what's past due. All pending/overdue tasks
        are included with a relevance floor so they always surface.
        """
        from src.memory.prospective import ProspectiveMemory

        memory = ProspectiveMemory()
        # Fetch upcoming time-based tasks and overdue tasks in parallel
        upcoming_tasks, overdue_tasks = await asyncio.gather(
            memory.get_upcoming_tasks(user_id, limit=limit * 2),
            memory.get_overdue_tasks(user_id),
            return_exceptions=True,
        )

        # Handle exceptions gracefully
        if isinstance(upcoming_tasks, BaseException):
            logger.warning("Failed to get upcoming tasks: %s", upcoming_tasks)
            upcoming_tasks = []
        if isinstance(overdue_tasks, BaseException):
            logger.warning("Failed to get overdue tasks: %s", overdue_tasks)
            overdue_tasks = []

        # Combine and deduplicate by ID
        seen_ids: set[str] = set()
        all_tasks = []
        # Overdue first (higher urgency)
        for task in [*overdue_tasks, *upcoming_tasks]:
            if task.id not in seen_ids:
                seen_ids.add(task.id)
                all_tasks.append(task)

        results = []
        for task in all_tasks:
            text = f"{task.task} {task.description or ''}"
            relevance = self._calculate_text_relevance(query, text)
            # Overdue tasks get high relevance; pending tasks get a floor
            if task.status.value == "overdue":
                relevance = max(relevance, 0.7)
            else:
                relevance = max(relevance, 0.4)

            due_info = ""
            due_at = task.trigger_config.get("due_at")
            if due_at:
                due_info = f" | Due: {due_at}"

            results.append(
                {
                    "id": task.id,
                    "memory_type": "prospective",
                    "content": (
                        f"[{task.status.value}] [{task.priority.value}] {task.task}{due_info}"
                    ),
                    "relevance_score": relevance,
                    "confidence": None,
                    "timestamp": task.created_at,
                }
            )

        results.sort(key=lambda x: cast(float, x["relevance_score"]), reverse=True)
        return results[:limit]

    async def _query_lead(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query lead memory for relevant leads.

        Returns leads whose company or contact name appears in the query,
        or top active leads as general context when no name match is found.
        """
        from src.memory.lead_memory import LeadMemoryService

        service = LeadMemoryService()
        try:
            leads = await service.list_by_user(user_id=user_id, limit=limit * 2)
        except Exception:
            return []

        query_lower = query.lower()
        relevant: list[dict[str, Any]] = []

        for lead in leads:
            company_lower = lead.company_name.lower()
            if company_lower in query_lower or query_lower in company_lower:
                relevant.append(
                    {
                        "id": lead.id,
                        "memory_type": "lead",
                        "content": self._format_lead_content(lead, prefix="Lead"),
                        "relevance_score": 0.9,
                        "confidence": None,
                        "timestamp": lead.updated_at,
                    }
                )

        # If no name match, return top active leads as general context
        if not relevant and leads:
            for lead in leads[:3]:
                relevant.append(
                    {
                        "id": lead.id,
                        "memory_type": "lead",
                        "content": self._format_lead_content(lead, prefix="Active lead"),
                        "relevance_score": 0.5,
                        "confidence": None,
                        "timestamp": lead.updated_at,
                    }
                )

        return relevant[:limit]

    def _calculate_text_relevance(self, query: str, text: str) -> float:
        """Calculate simple text relevance score.

        Uses word overlap ratio as a simple relevance metric.

        Args:
            query: The search query.
            text: The text to score.

        Returns:
            Relevance score between 0.0 and 1.0.
        """
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())

        if not query_words:
            return 0.0

        overlap = len(query_words & text_words)
        return min(1.0, overlap / len(query_words))

    @staticmethod
    def _format_lead_content(lead: Any, prefix: str = "Lead") -> str:
        """Format a lead into a readable content string for the LLM.

        Args:
            lead: A LeadMemory instance.
            prefix: Label prefix (e.g. "Lead" or "Active lead").

        Returns:
            Formatted lead summary string.
        """
        parts = [
            f"{prefix}: {lead.company_name}",
            f"Stage: {lead.lifecycle_stage.value}",
            f"Status: {lead.status.value}",
            f"Health: {lead.health_score}/100",
        ]
        if lead.expected_value:
            parts.append(f"Value: ${lead.expected_value:,.0f}")
        if lead.expected_close_date:
            parts.append(f"Expected close: {lead.expected_close_date}")
        if lead.last_activity_at:
            parts.append(f"Last activity: {lead.last_activity_at.strftime('%Y-%m-%d')}")
        return " | ".join(parts)
