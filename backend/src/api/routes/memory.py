"""Memory API routes for unified memory querying."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# Response Models
class MemoryQueryResult(BaseModel):
    """A single result from unified memory query.

    Represents a memory item retrieved from any of the four memory types:
    - episodic: Past events, interactions, meetings
    - semantic: Facts with confidence scores
    - procedural: Learned workflows and patterns
    - prospective: Future tasks, reminders, follow-ups
    """

    id: str
    memory_type: Literal["episodic", "semantic", "procedural", "prospective"]
    content: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    timestamp: datetime


class MemoryQueryResponse(BaseModel):
    """Paginated response for memory queries.

    Provides a unified response format for querying across all memory types
    with standard pagination fields.
    """

    items: list[MemoryQueryResult]
    total: int
    page: int
    page_size: int
    has_more: bool


class MemoryQueryService:
    """Service for querying across all memory types."""

    async def query(
        self,
        user_id: str,
        query: str,
        memory_types: list[str],
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """Query across specified memory types.

        Args:
            user_id: The user ID to query memories for.
            query: The search query string.
            memory_types: List of memory types to search.
            start_date: Optional start of time range filter.
            end_date: Optional end of time range filter.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of memory results sorted by relevance.
        """
        tasks = []

        if "episodic" in memory_types:
            tasks.append(self._query_episodic(user_id, query, start_date, end_date, limit))
        if "semantic" in memory_types:
            tasks.append(self._query_semantic(user_id, query, limit))
        if "procedural" in memory_types:
            tasks.append(self._query_procedural(user_id, query, limit))
        if "prospective" in memory_types:
            tasks.append(self._query_prospective(user_id, query, limit))

        # Execute all queries in parallel
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results, filtering out exceptions
        all_results: list[dict[str, Any]] = []
        for result in results_lists:
            if isinstance(result, Exception):
                logger.warning("Memory query failed: %s", result)
                continue
            all_results.extend(result)

        # Sort by relevance score descending
        all_results.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Apply offset and limit
        return all_results[offset : offset + limit]

    async def _query_episodic(
        self,
        user_id: str,
        query: str,
        _start_date: datetime | None,
        _end_date: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query episodic memory.

        Note: _start_date and _end_date are accepted for API consistency but
        date filtering is not yet implemented in EpisodicMemory.semantic_search().
        """
        # TODO: Add date filtering when EpisodicMemory.semantic_search supports it
        from src.memory.episodic import EpisodicMemory

        # Note: Creating memory instance per request is acceptable - classes are
        # lightweight and stateless. Could optimize with DI if needed in future.
        memory = EpisodicMemory()
        episodes = await memory.semantic_search(user_id, query, limit=limit)

        results = []
        for episode in episodes:
            relevance = self._calculate_text_relevance(query, episode.content)
            results.append({
                "id": episode.id,
                "memory_type": "episodic",
                "content": f"[{episode.event_type}] {episode.content}",
                "relevance_score": relevance,
                "confidence": None,
                "timestamp": episode.occurred_at,
            })

        return results

    async def _query_semantic(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query semantic memory."""
        from src.memory.semantic import SemanticMemory

        memory = SemanticMemory()
        facts = await memory.search_facts(user_id, query, min_confidence=0.0, limit=limit)

        results = []
        for fact in facts:
            relevance = self._calculate_text_relevance(
                query, f"{fact.subject} {fact.predicate} {fact.object}"
            )
            results.append({
                "id": fact.id,
                "memory_type": "semantic",
                "content": f"{fact.subject} {fact.predicate} {fact.object}",
                "relevance_score": relevance,
                "confidence": fact.confidence,
                "timestamp": fact.valid_from,
            })

        return results

    async def _query_procedural(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query procedural memory."""
        from src.memory.procedural import ProceduralMemory

        memory = ProceduralMemory()
        workflows = await memory.list_workflows(user_id, include_shared=True)

        results = []
        query_lower = query.lower()
        for workflow in workflows:
            text = f"{workflow.workflow_name} {workflow.description}"
            if query_lower in text.lower():
                relevance = self._calculate_text_relevance(query, text)
                results.append({
                    "id": workflow.id,
                    "memory_type": "procedural",
                    "content": f"{workflow.workflow_name}: {workflow.description}",
                    "relevance_score": relevance,
                    "confidence": workflow.success_rate,
                    "timestamp": workflow.created_at,
                })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:limit]

    async def _query_prospective(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query prospective memory."""
        from src.memory.prospective import ProspectiveMemory

        memory = ProspectiveMemory()
        # Fetch extra to allow for filtering (query matching reduces result count)
        upcoming = await memory.get_upcoming_tasks(user_id, limit=limit * 2)

        results = []
        query_lower = query.lower()
        for task in upcoming:
            text = f"{task.task} {task.description or ''}"
            if query_lower in text.lower():
                relevance = self._calculate_text_relevance(query, text)
                results.append({
                    "id": task.id,
                    "memory_type": "prospective",
                    "content": f"[{task.status.value}] {task.task}",
                    "relevance_score": relevance,
                    "confidence": None,
                    "timestamp": task.created_at,
                })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:limit]

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


@router.get("/query", response_model=MemoryQueryResponse)
async def query_memory(
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Search query string"),
    types: list[str] = Query(
        default=["episodic", "semantic"],
        description="Memory types to search",
    ),
    start_date: datetime | None = Query(None, description="Start of time range filter"),
    end_date: datetime | None = Query(None, description="End of time range filter"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
) -> MemoryQueryResponse:
    """Query across multiple memory types.

    Searches episodic, semantic, procedural, and/or prospective memories
    based on the provided query string. Returns ranked results sorted by
    relevance score.

    Args:
        current_user: Authenticated user.
        q: Search query string.
        types: List of memory types to search.
        start_date: Optional start of time range filter.
        end_date: Optional end of time range filter.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        Paginated memory query results.
    """
    # Validate and filter memory types
    valid_types = {"episodic", "semantic", "procedural", "prospective"}
    invalid_types = [t for t in types if t not in valid_types]
    if invalid_types:
        logger.warning(
            "Invalid memory types ignored in query",
            extra={"invalid_types": invalid_types, "user_id": current_user.id},
        )
    requested_types = [t for t in types if t in valid_types]

    if not requested_types:
        requested_types = ["episodic", "semantic"]

    # Calculate offset
    offset = (page - 1) * page_size

    # Query memories
    service = MemoryQueryService()
    # Request extra to determine has_more
    results = await service.query(
        user_id=current_user.id,
        query=q,
        memory_types=requested_types,
        start_date=start_date,
        end_date=end_date,
        limit=page_size + 1,  # Get one extra to check has_more
        offset=offset,
    )

    # Check if there are more results
    has_more = len(results) > page_size
    results = results[:page_size]

    # Convert to response models
    items = [
        MemoryQueryResult(
            id=r["id"],
            memory_type=r["memory_type"],
            content=r["content"],
            relevance_score=r["relevance_score"],
            confidence=r["confidence"],
            timestamp=r["timestamp"],
        )
        for r in results
    ]

    logger.info(
        "Memory query executed",
        extra={
            "user_id": current_user.id,
            "query": q,
            "types": requested_types,
            "results_count": len(items),
        },
    )

    return MemoryQueryResponse(
        items=items,
        total=len(items),  # Count of items in current page (not total across all pages)
        page=page,
        page_size=page_size,
        has_more=has_more,
    )
