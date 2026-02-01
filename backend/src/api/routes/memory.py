"""Memory API routes for unified memory querying."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import EpisodicMemoryError, ProspectiveMemoryError, SemanticMemoryError
from src.memory.episodic import Episode, EpisodicMemory
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from src.memory.semantic import SOURCE_CONFIDENCE, FactSource, SemanticFact, SemanticMemory

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


# Request Models for Store Endpoints
class CreateEpisodeRequest(BaseModel):
    """Request body for creating a new episodic memory."""

    event_type: str = Field(
        ..., min_length=1, description="Type of event (meeting, call, email, etc.)"
    )
    content: str = Field(..., min_length=1, description="Event content/description")
    participants: list[str] = Field(
        default_factory=list, description="People involved in the event"
    )
    occurred_at: datetime | None = Field(
        None, description="When the event occurred (defaults to now)"
    )
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")


class CreateEpisodeResponse(BaseModel):
    """Response body for episode creation."""

    id: str
    message: str = "Episode created successfully"


class CreateFactRequest(BaseModel):
    """Request body for creating a new semantic fact."""

    subject: str = Field(..., min_length=1, description="Entity the fact is about")
    predicate: str = Field(..., min_length=1, description="Relationship type")
    object: str = Field(..., min_length=1, description="Value or related entity")
    source: Literal["user_stated", "extracted", "inferred", "crm_import", "web_research"] | None = (
        Field(None, description="Source of the fact")
    )
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Confidence score")
    valid_from: datetime | None = Field(None, description="When the fact became valid")
    valid_to: datetime | None = Field(None, description="When the fact expires")


class CreateFactResponse(BaseModel):
    """Response body for fact creation."""

    id: str
    message: str = "Fact created successfully"


class CreateTaskRequest(BaseModel):
    """Request body for creating a new prospective task."""

    task: str = Field(..., min_length=1, description="Short task description")
    description: str | None = Field(None, description="Detailed description")
    trigger_type: Literal["time", "event", "condition"] = Field(..., description="Type of trigger")
    trigger_config: dict[str, Any] = Field(..., description="Trigger-specific configuration")
    priority: Literal["low", "medium", "high", "urgent"] = Field(
        "medium", description="Task priority"
    )
    related_goal_id: str | None = Field(None, description="Optional linked goal ID")
    related_lead_id: str | None = Field(None, description="Optional linked lead ID")


class CreateTaskResponse(BaseModel):
    """Response body for task creation."""

    id: str
    message: str = "Task created successfully"


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
            results.append(
                {
                    "id": fact.id,
                    "memory_type": "semantic",
                    "content": f"{fact.subject} {fact.predicate} {fact.object}",
                    "relevance_score": relevance,
                    "confidence": fact.confidence,
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
                results.append(
                    {
                        "id": workflow.id,
                        "memory_type": "procedural",
                        "content": f"{workflow.workflow_name}: {workflow.description}",
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
                results.append(
                    {
                        "id": task.id,
                        "memory_type": "prospective",
                        "content": f"[{task.status.value}] {task.task}",
                        "relevance_score": relevance,
                        "confidence": None,
                        "timestamp": task.created_at,
                    }
                )

        results.sort(key=lambda x: cast(float, x["relevance_score"]), reverse=True)
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


@router.post("/episode", response_model=CreateEpisodeResponse, status_code=201)
async def store_episode(
    current_user: CurrentUser,
    request: CreateEpisodeRequest,
) -> CreateEpisodeResponse:
    """Store a new episodic memory.

    Creates an episode representing a past event or interaction.
    Episodes are stored in Graphiti for temporal querying.

    Args:
        current_user: Authenticated user.
        request: Episode creation request body.

    Returns:
        Created episode with ID.
    """
    # Build episode from request
    now = datetime.now(UTC)
    episode = Episode(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        event_type=request.event_type,
        content=request.content,
        participants=request.participants,
        occurred_at=request.occurred_at or now,
        recorded_at=now,
        context=request.context,
    )

    # Store episode
    memory = EpisodicMemory()
    try:
        episode_id = await memory.store_episode(episode)
    except EpisodicMemoryError as e:
        logger.error(
            "Failed to store episode",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Memory storage unavailable") from None

    logger.info(
        "Stored episode via API",
        extra={
            "episode_id": episode_id,
            "user_id": current_user.id,
            "event_type": request.event_type,
        },
    )

    return CreateEpisodeResponse(id=episode_id)


@router.post("/fact", response_model=CreateFactResponse, status_code=201)
async def store_fact(
    current_user: CurrentUser,
    request: CreateFactRequest,
) -> CreateFactResponse:
    """Store a new semantic fact.

    Creates a fact representing knowledge about an entity as a
    subject-predicate-object triple. Facts are stored in Graphiti
    for semantic search and temporal querying. Contradiction detection
    is automatically performed.

    Args:
        current_user: Authenticated user.
        request: Fact creation request body.

    Returns:
        Created fact with ID.
    """
    # Determine source and confidence
    source = FactSource(request.source) if request.source else FactSource.USER_STATED
    confidence = request.confidence if request.confidence is not None else SOURCE_CONFIDENCE[source]

    # Build fact from request
    now = datetime.now(UTC)
    fact = SemanticFact(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        subject=request.subject,
        predicate=request.predicate,
        object=request.object,
        confidence=confidence,
        source=source,
        valid_from=request.valid_from or now,
        valid_to=request.valid_to,
    )

    # Store fact with error handling
    memory = SemanticMemory()
    try:
        fact_id = await memory.add_fact(fact)
    except SemanticMemoryError as e:
        logger.error(
            "Failed to store fact",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Memory storage unavailable") from None

    logger.info(
        "Stored fact via API",
        extra={
            "fact_id": fact_id,
            "user_id": current_user.id,
            "subject": request.subject,
            "predicate": request.predicate,
        },
    )

    return CreateFactResponse(id=fact_id)


@router.post("/task", response_model=CreateTaskResponse, status_code=201)
async def store_task(
    current_user: CurrentUser,
    request: CreateTaskRequest,
) -> CreateTaskResponse:
    """Store a new prospective task.

    Creates a task representing a future action to be completed.
    Tasks are stored in Supabase with trigger-based scheduling.

    Args:
        current_user: Authenticated user.
        request: Task creation request body.

    Returns:
        Created task with ID.
    """
    # Build task from request
    now = datetime.now(UTC)
    task = ProspectiveTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task=request.task,
        description=request.description,
        trigger_type=TriggerType(request.trigger_type),
        trigger_config=request.trigger_config,
        status=TaskStatus.PENDING,
        priority=TaskPriority(request.priority),
        related_goal_id=request.related_goal_id,
        related_lead_id=request.related_lead_id,
        completed_at=None,
        created_at=now,
    )

    # Store task with error handling
    memory = ProspectiveMemory()
    try:
        task_id = await memory.create_task(task)
    except ProspectiveMemoryError as e:
        logger.error(
            "Failed to store task",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Memory storage unavailable") from None

    logger.info(
        "Stored task via API",
        extra={
            "task_id": task_id,
            "user_id": current_user.id,
            "task": request.task,
            "trigger_type": request.trigger_type,
        },
    )

    return CreateTaskResponse(id=task_id)
