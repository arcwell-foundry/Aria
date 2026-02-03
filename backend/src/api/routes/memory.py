"""Memory API routes for unified memory querying."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import AdminUser, CurrentUser
from src.core.exceptions import (
    CorporateFactNotFoundError,
    CorporateMemoryError,
    DigitalTwinError,
    EpisodicMemoryError,
    NotFoundError,
    ProceduralMemoryError,
    ProspectiveMemoryError,
    SemanticMemoryError,
)
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryAuditLogger, MemoryOperation, MemoryType
from src.memory.conversation import ConversationService
from src.memory.corporate import (
    CORPORATE_SOURCE_CONFIDENCE,
    CorporateFact,
    CorporateFactSource,
    CorporateMemory,
)
from src.memory.digital_twin import DigitalTwin
from src.memory.episodic import Episode, EpisodicMemory
from src.memory.priming import ConversationPrimingService
from src.memory.procedural import ProceduralMemory, Workflow
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from src.memory.salience import SalienceService
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


class CreateWorkflowRequest(BaseModel):
    """Request body for creating a new procedural workflow."""

    workflow_name: str = Field(..., min_length=1, description="Name of the workflow")
    description: str = Field(..., min_length=1, description="Description of what the workflow does")
    trigger_conditions: dict[str, Any] = Field(
        default_factory=dict, description="Conditions that trigger this workflow"
    )
    steps: list[dict[str, Any]] = Field(
        ..., min_length=1, description="Ordered list of workflow steps"
    )
    is_shared: bool = Field(False, description="Whether workflow is available to other users")


class CreateWorkflowResponse(BaseModel):
    """Response body for workflow creation."""

    id: str
    message: str = "Workflow created successfully"


# Digital Twin Models
class FingerprintResponse(BaseModel):
    """Response body for fingerprint retrieval."""

    id: str
    user_id: str
    average_sentence_length: float
    vocabulary_level: str
    formality_score: float = Field(..., ge=0.0, le=1.0)
    common_phrases: list[str]
    greeting_style: str
    sign_off_style: str
    emoji_usage: bool
    punctuation_patterns: dict[str, float]
    samples_analyzed: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime


class AnalyzeSampleRequest(BaseModel):
    """Request body for analyzing a text sample."""

    text: str = Field(..., min_length=10, description="Text sample to analyze")
    text_type: Literal["email", "message", "document"] = Field("email", description="Type of text")


class AnalyzeSampleResponse(BaseModel):
    """Response body for sample analysis."""

    message: str = "Sample analyzed successfully"


class StyleGuidelinesResponse(BaseModel):
    """Response body for style guidelines."""

    guidelines: str


class ScoreStyleMatchRequest(BaseModel):
    """Request body for scoring style match."""

    text: str = Field(..., min_length=1, description="Text to score")


class ScoreStyleMatchResponse(BaseModel):
    """Response body for style match score."""

    score: float = Field(..., ge=0.0, le=1.0)


# Audit Log Models
class AuditLogEntry(BaseModel):
    """A single audit log entry."""

    id: str
    user_id: str
    operation: str
    memory_type: str
    memory_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogResponse(BaseModel):
    """Paginated response for audit log queries."""

    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    has_more: bool


# Corporate Memory Models
class CreateCorporateFactRequest(BaseModel):
    """Request body for creating a new corporate fact."""

    subject: str = Field(..., min_length=1, description="Entity the fact is about")
    predicate: str = Field(..., min_length=1, description="Relationship type")
    object: str = Field(..., min_length=1, description="Value or related entity")
    source: Literal["extracted", "aggregated", "admin_stated"] | None = Field(
        None, description="Source of the fact"
    )
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Confidence score")


class CreateCorporateFactResponse(BaseModel):
    """Response body for corporate fact creation."""

    id: str
    message: str = "Corporate fact created successfully"


class CorporateFactResponse(BaseModel):
    """Response body for a single corporate fact."""

    id: str
    company_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None


class CorporateFactsResponse(BaseModel):
    """Paginated response for corporate facts queries."""

    items: list[CorporateFactResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class InvalidateCorporateFactRequest(BaseModel):
    """Request body for invalidating a corporate fact."""

    reason: str = Field(..., min_length=1, description="Reason for invalidation")


class PrimeConversationResponse(BaseModel):
    """Response for conversation priming endpoint."""

    recent_context: list[dict[str, Any]] = Field(
        default_factory=list, description="Recent conversation episodes"
    )
    open_threads: list[dict[str, Any]] = Field(
        default_factory=list, description="Unresolved topics from past conversations"
    )
    salient_facts: list[dict[str, Any]] = Field(
        default_factory=list, description="High-salience facts about entities"
    )
    formatted_context: str = Field(..., description="Pre-formatted context for LLM consumption")


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
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query episodic memory.

        Note: _start_date and _end_date are accepted for API consistency but
        date filtering is not yet implemented in EpisodicMemory.semantic_search().

        Args:
            user_id: The user ID to query memories for.
            query: The search query string.
            _start_date: Reserved for future date filtering.
            _end_date: Reserved for future date filtering.
            limit: Maximum results to return.
            as_of: Point in time filter. Only includes episodes recorded on or before this date.
        """
        # TODO: Add date filtering when EpisodicMemory.semantic_search supports it
        from src.memory.episodic import EpisodicMemory

        # Note: Creating memory instance per request is acceptable - classes are
        # lightweight and stateless. Could optimize with DI if needed in future.
        memory = EpisodicMemory()
        episodes = await memory.semantic_search(user_id, query, limit=limit, as_of=as_of)

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
    min_confidence: float | None = Query(
        None, ge=0.0, le=1.0, description="Minimum confidence threshold for semantic results"
    ),
    as_of: datetime | None = Query(
        None,
        description="Point in time for temporal query. Returns memories as known at this date.",
    ),
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
        as_of: Point in time for temporal query. Returns memories as known at this date.
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
        min_confidence=min_confidence,
        limit=page_size + 1,  # Get one extra to check has_more
        offset=offset,
        as_of=as_of,
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


@router.post("/workflow", response_model=CreateWorkflowResponse, status_code=201)
async def store_workflow(
    current_user: CurrentUser,
    request: CreateWorkflowRequest,
) -> CreateWorkflowResponse:
    """Store a new procedural workflow.

    Creates a workflow representing a repeatable sequence of actions.
    Workflows are stored in Supabase with trigger-based matching and
    success rate tracking for continuous improvement.

    Args:
        current_user: Authenticated user.
        request: Workflow creation request body.

    Returns:
        Created workflow with ID.
    """
    # Build workflow from request
    now = datetime.now(UTC)
    workflow = Workflow(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        workflow_name=request.workflow_name,
        description=request.description,
        trigger_conditions=request.trigger_conditions,
        steps=request.steps,
        success_count=0,
        failure_count=0,
        is_shared=request.is_shared,
        version=1,
        created_at=now,
        updated_at=now,
    )

    # Store workflow with error handling
    memory = ProceduralMemory()
    try:
        workflow_id = await memory.create_workflow(workflow)
    except ProceduralMemoryError as e:
        logger.error(
            "Failed to store workflow",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Memory storage unavailable") from None

    logger.info(
        "Stored workflow via API",
        extra={
            "workflow_id": workflow_id,
            "user_id": current_user.id,
            "workflow_name": request.workflow_name,
        },
    )

    return CreateWorkflowResponse(id=workflow_id)


# Digital Twin Endpoints


@router.get("/fingerprint", response_model=FingerprintResponse)
async def get_fingerprint(
    current_user: CurrentUser,
) -> FingerprintResponse:
    """Get the user's writing style fingerprint.

    Retrieves the accumulated writing style fingerprint for the current user,
    built from analyzed text samples.

    Args:
        current_user: Authenticated user.

    Returns:
        User's writing style fingerprint.

    Raises:
        HTTPException: 404 if no fingerprint exists.
    """
    twin = DigitalTwin()
    try:
        fingerprint = await twin.get_fingerprint(user_id=current_user.id)
    except DigitalTwinError as e:
        logger.error(
            "Failed to get fingerprint",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    if fingerprint is None:
        raise HTTPException(status_code=404, detail="No fingerprint found for user")

    return FingerprintResponse(
        id=fingerprint.id,
        user_id=fingerprint.user_id,
        average_sentence_length=fingerprint.average_sentence_length,
        vocabulary_level=fingerprint.vocabulary_level,
        formality_score=fingerprint.formality_score,
        common_phrases=fingerprint.common_phrases,
        greeting_style=fingerprint.greeting_style,
        sign_off_style=fingerprint.sign_off_style,
        emoji_usage=fingerprint.emoji_usage,
        punctuation_patterns=fingerprint.punctuation_patterns,
        samples_analyzed=fingerprint.samples_analyzed,
        confidence=fingerprint.confidence,
        created_at=fingerprint.created_at,
        updated_at=fingerprint.updated_at,
    )


@router.post("/fingerprint/analyze", response_model=AnalyzeSampleResponse)
async def analyze_sample(
    current_user: CurrentUser,
    request: AnalyzeSampleRequest,
) -> AnalyzeSampleResponse:
    """Analyze a text sample to update the user's writing style fingerprint.

    Extracts writing style features from the provided text and updates
    the user's fingerprint with an incremental weighted average.

    Args:
        current_user: Authenticated user.
        request: Analysis request with text sample.

    Returns:
        Success confirmation.
    """
    twin = DigitalTwin()
    try:
        await twin.analyze_sample(
            user_id=current_user.id,
            text=request.text,
            text_type=request.text_type,
        )
    except DigitalTwinError as e:
        logger.error(
            "Failed to analyze sample",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    logger.info(
        "Analyzed text sample",
        extra={
            "user_id": current_user.id,
            "text_type": request.text_type,
            "text_length": len(request.text),
        },
    )

    return AnalyzeSampleResponse()


@router.get("/fingerprint/guidelines", response_model=StyleGuidelinesResponse)
async def get_style_guidelines(
    current_user: CurrentUser,
) -> StyleGuidelinesResponse:
    """Get style guidelines for generating text in the user's voice.

    Returns prompt-ready instructions that can be used with an LLM
    to generate text matching the user's writing style.

    Args:
        current_user: Authenticated user.

    Returns:
        Style guidelines string.
    """
    twin = DigitalTwin()
    try:
        guidelines = await twin.get_style_guidelines(user_id=current_user.id)
    except DigitalTwinError as e:
        logger.error(
            "Failed to get style guidelines",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    return StyleGuidelinesResponse(guidelines=guidelines)


@router.post("/fingerprint/score", response_model=ScoreStyleMatchResponse)
async def score_style_match(
    current_user: CurrentUser,
    request: ScoreStyleMatchRequest,
) -> ScoreStyleMatchResponse:
    """Score how well text matches the user's writing style.

    Compares the provided text against the user's fingerprint and
    returns a similarity score from 0.0 to 1.0.

    Args:
        current_user: Authenticated user.
        request: Score request with text to evaluate.

    Returns:
        Style match score.
    """
    twin = DigitalTwin()
    try:
        score = await twin.score_style_match(
            user_id=current_user.id,
            generated_text=request.text,
        )
    except DigitalTwinError as e:
        logger.error(
            "Failed to score style match",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    return ScoreStyleMatchResponse(score=score)


# Audit Log Endpoints


@router.get("/audit", response_model=AuditLogResponse)
async def query_audit_log(
    current_user: CurrentUser,
    operation: Literal["create", "update", "delete", "query", "invalidate"] | None = Query(
        None, description="Filter by operation type"
    ),
    memory_type: Literal["episodic", "semantic", "procedural", "prospective"] | None = Query(
        None, description="Filter by memory type"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Results per page"),
) -> AuditLogResponse:
    """Query the memory audit log.

    Returns audit log entries for the current user. Admins can see
    all entries via the admin audit endpoint.

    Args:
        current_user: Authenticated user.
        operation: Optional filter by operation type.
        memory_type: Optional filter by memory type.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        Paginated audit log entries.
    """
    offset = (page - 1) * page_size

    audit_logger = MemoryAuditLogger()

    # Convert string filters to enums
    op_filter = MemoryOperation(operation) if operation else None
    mt_filter = MemoryType(memory_type) if memory_type else None

    # Query with one extra to determine has_more
    results = await audit_logger.query(
        user_id=current_user.id,
        operation=op_filter,
        memory_type=mt_filter,
        limit=page_size + 1,
        offset=offset,
    )

    has_more = len(results) > page_size
    results = results[:page_size]

    items = [
        AuditLogEntry(
            id=r["id"],
            user_id=r["user_id"],
            operation=r["operation"],
            memory_type=r["memory_type"],
            memory_id=r.get("memory_id"),
            metadata=r.get("metadata") or {},
            created_at=datetime.fromisoformat(r["created_at"]),
        )
        for r in results
    ]

    logger.info(
        "Audit log queried",
        extra={
            "user_id": current_user.id,
            "operation_filter": operation,
            "memory_type_filter": memory_type,
            "results_count": len(items),
        },
    )

    return AuditLogResponse(
        items=items,
        total=len(items),
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


# Corporate Memory Endpoints


async def _get_user_company_id(user_id: str) -> str:
    """Get the user's company_id from their profile.

    Args:
        user_id: The user's UUID.

    Returns:
        The company_id from the user's profile.

    Raises:
        HTTPException: If user profile not found or no company_id.
    """
    try:
        profile = await SupabaseClient.get_user_by_id(user_id)
        company_id = profile.get("company_id")
        if not company_id:
            raise HTTPException(
                status_code=400,
                detail="User must be associated with a company to access corporate memory",
            )
        return cast(str, company_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User profile not found") from None


async def _check_user_is_admin(user_id: str) -> bool:
    """Check if user has admin role.

    Args:
        user_id: The user's UUID.

    Returns:
        True if user has admin role, False otherwise.
    """
    try:
        profile = await SupabaseClient.get_user_by_id(user_id)
        return profile.get("role") == "admin"
    except NotFoundError:
        return False


@router.post("/corporate/fact", response_model=CreateCorporateFactResponse, status_code=201)
async def create_corporate_fact(
    admin_user: AdminUser,
    request: CreateCorporateFactRequest,
) -> CreateCorporateFactResponse:
    """Create a new corporate fact (admin only).

    Creates a company-level fact that is shared across all users in the company.
    Only admins can create corporate facts.

    Args:
        admin_user: Authenticated admin user.
        request: Corporate fact creation request body.

    Returns:
        Created corporate fact with ID.
    """
    company_id = await _get_user_company_id(admin_user.id)

    # Determine source and confidence
    source = (
        CorporateFactSource(request.source) if request.source else CorporateFactSource.ADMIN_STATED
    )
    confidence = (
        request.confidence
        if request.confidence is not None
        else CORPORATE_SOURCE_CONFIDENCE[source]
    )

    # Build fact from request
    now = datetime.now(UTC)
    fact = CorporateFact(
        id=str(uuid.uuid4()),
        company_id=company_id,
        subject=request.subject,
        predicate=request.predicate,
        object=request.object,
        confidence=confidence,
        source=source,
        is_active=True,
        created_at=now,
        updated_at=now,
        created_by=admin_user.id,
    )

    # Store fact
    memory = CorporateMemory()
    try:
        fact_id = await memory.add_fact(fact)
    except CorporateMemoryError as e:
        logger.error(
            "Failed to store corporate fact",
            extra={"error": str(e), "user_id": admin_user.id, "company_id": company_id},
        )
        raise HTTPException(
            status_code=503, detail="Corporate memory storage unavailable"
        ) from None

    logger.info(
        "Stored corporate fact via API",
        extra={
            "fact_id": fact_id,
            "user_id": admin_user.id,
            "company_id": company_id,
            "subject": request.subject,
            "predicate": request.predicate,
        },
    )

    return CreateCorporateFactResponse(id=fact_id)


@router.get("/corporate/facts", response_model=CorporateFactsResponse)
async def list_corporate_facts(
    current_user: CurrentUser,
    subject: str | None = Query(None, description="Filter by subject entity"),
    predicate: str | None = Query(None, description="Filter by predicate type"),
    include_inactive: bool = Query(False, description="Include invalidated facts"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
) -> CorporateFactsResponse:
    """List corporate facts for the user's company.

    Returns company-level facts shared across all users.
    All authenticated users can read their company's facts.

    Args:
        current_user: Authenticated user.
        subject: Optional filter by subject entity.
        predicate: Optional filter by predicate type.
        include_inactive: Whether to include invalidated facts.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        Paginated corporate facts.
    """
    company_id = await _get_user_company_id(current_user.id)

    memory = CorporateMemory()
    try:
        # Get extra to determine has_more
        facts = await memory.get_facts_for_company(
            company_id=company_id,
            subject=subject,
            predicate=predicate,
            active_only=not include_inactive,
            limit=page_size + 1,
        )
    except CorporateMemoryError as e:
        logger.error(
            "Failed to list corporate facts",
            extra={"error": str(e), "user_id": current_user.id, "company_id": company_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    has_more = len(facts) > page_size
    facts = facts[:page_size]

    items = [
        CorporateFactResponse(
            id=f.id,
            company_id=f.company_id,
            subject=f.subject,
            predicate=f.predicate,
            object=f.object,
            confidence=f.confidence,
            source=f.source.value,
            is_active=f.is_active,
            created_at=f.created_at,
            updated_at=f.updated_at,
            created_by=f.created_by,
            invalidated_at=f.invalidated_at,
            invalidation_reason=f.invalidation_reason,
        )
        for f in facts
    ]

    logger.info(
        "Listed corporate facts",
        extra={
            "user_id": current_user.id,
            "company_id": company_id,
            "results_count": len(items),
        },
    )

    return CorporateFactsResponse(
        items=items,
        total=len(items),
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/corporate/facts/{fact_id}", response_model=CorporateFactResponse)
async def get_corporate_fact(
    current_user: CurrentUser,
    fact_id: str,
) -> CorporateFactResponse:
    """Get a specific corporate fact.

    Retrieves a single corporate fact by ID. All authenticated users
    can read their company's facts.

    Args:
        current_user: Authenticated user.
        fact_id: The ID of the fact to retrieve.

    Returns:
        The requested corporate fact.

    Raises:
        HTTPException: 404 if fact not found.
    """
    company_id = await _get_user_company_id(current_user.id)

    memory = CorporateMemory()
    try:
        fact = await memory.get_fact(company_id=company_id, fact_id=fact_id)
    except CorporateFactNotFoundError:
        raise HTTPException(status_code=404, detail=f"Corporate fact {fact_id} not found") from None
    except CorporateMemoryError as e:
        logger.error(
            "Failed to get corporate fact",
            extra={"error": str(e), "user_id": current_user.id, "fact_id": fact_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    return CorporateFactResponse(
        id=fact.id,
        company_id=fact.company_id,
        subject=fact.subject,
        predicate=fact.predicate,
        object=fact.object,
        confidence=fact.confidence,
        source=fact.source.value,
        is_active=fact.is_active,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        created_by=fact.created_by,
        invalidated_at=fact.invalidated_at,
        invalidation_reason=fact.invalidation_reason,
    )


@router.post("/corporate/facts/{fact_id}/invalidate", status_code=204)
async def invalidate_corporate_fact(
    admin_user: AdminUser,
    fact_id: str,
    request: InvalidateCorporateFactRequest,
) -> None:
    """Invalidate a corporate fact (admin only).

    Soft deletes a corporate fact by marking it as inactive.
    The fact remains in the database but won't appear in queries
    unless include_inactive=True is specified.

    Args:
        admin_user: Authenticated admin user.
        fact_id: The ID of the fact to invalidate.
        request: Invalidation request with reason.

    Raises:
        HTTPException: 404 if fact not found, 403 if not admin.
    """
    company_id = await _get_user_company_id(admin_user.id)

    memory = CorporateMemory()
    try:
        await memory.invalidate_fact(
            company_id=company_id,
            fact_id=fact_id,
            reason=request.reason,
            invalidated_by=admin_user.id,
        )
    except CorporateFactNotFoundError:
        raise HTTPException(status_code=404, detail=f"Corporate fact {fact_id} not found") from None
    except CorporateMemoryError as e:
        logger.error(
            "Failed to invalidate corporate fact",
            extra={"error": str(e), "user_id": admin_user.id, "fact_id": fact_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    logger.info(
        "Invalidated corporate fact",
        extra={
            "fact_id": fact_id,
            "user_id": admin_user.id,
            "company_id": company_id,
            "reason": request.reason,
        },
    )


@router.delete("/corporate/facts/{fact_id}", status_code=204)
async def delete_corporate_fact(
    admin_user: AdminUser,
    fact_id: str,
) -> None:
    """Permanently delete a corporate fact (admin only).

    Hard deletes a corporate fact from both Supabase and Graphiti.
    This action cannot be undone. Use invalidate for soft delete.

    Args:
        admin_user: Authenticated admin user.
        fact_id: The ID of the fact to delete.

    Raises:
        HTTPException: 404 if fact not found, 403 if not admin.
    """
    company_id = await _get_user_company_id(admin_user.id)

    memory = CorporateMemory()
    try:
        await memory.delete_fact(company_id=company_id, fact_id=fact_id)
    except CorporateFactNotFoundError:
        raise HTTPException(status_code=404, detail=f"Corporate fact {fact_id} not found") from None
    except CorporateMemoryError as e:
        logger.error(
            "Failed to delete corporate fact",
            extra={"error": str(e), "user_id": admin_user.id, "fact_id": fact_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    logger.info(
        "Deleted corporate fact",
        extra={
            "fact_id": fact_id,
            "user_id": admin_user.id,
            "company_id": company_id,
        },
    )


@router.get("/corporate/search", response_model=CorporateFactsResponse)
async def search_corporate_facts(
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Search query string"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
) -> CorporateFactsResponse:
    """Search corporate facts using semantic search.

    Searches company-level facts using Graphiti semantic search.
    All authenticated users can search their company's facts.

    Args:
        current_user: Authenticated user.
        q: Search query string.
        min_confidence: Minimum confidence threshold.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        Paginated search results.
    """
    company_id = await _get_user_company_id(current_user.id)

    memory = CorporateMemory()
    try:
        # Get extra to determine has_more
        facts = await memory.search_facts(
            company_id=company_id,
            query=q,
            min_confidence=min_confidence,
            limit=page_size + 1,
        )
    except CorporateMemoryError as e:
        logger.error(
            "Failed to search corporate facts",
            extra={"error": str(e), "user_id": current_user.id, "company_id": company_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory search unavailable") from None

    has_more = len(facts) > page_size
    facts = facts[:page_size]

    items = [
        CorporateFactResponse(
            id=f.id,
            company_id=f.company_id,
            subject=f.subject,
            predicate=f.predicate,
            object=f.object,
            confidence=f.confidence,
            source=f.source.value,
            is_active=f.is_active,
            created_at=f.created_at,
            updated_at=f.updated_at,
            created_by=f.created_by,
            invalidated_at=f.invalidated_at,
            invalidation_reason=f.invalidation_reason,
        )
        for f in facts
    ]

    logger.info(
        "Searched corporate facts",
        extra={
            "user_id": current_user.id,
            "company_id": company_id,
            "query": q,
            "results_count": len(items),
        },
    )

    return CorporateFactsResponse(
        items=items,
        total=len(items),
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


# Conversation Priming Endpoints


@router.get("/prime", response_model=PrimeConversationResponse)
async def prime_conversation(
    current_user: CurrentUser,
    initial_message: str | None = Query(None, description="Initial message for entity lookup"),
) -> PrimeConversationResponse:
    """Get context for starting a new conversation.

    Gathers recent episodes, open threads, and high-salience facts
    to prime ARIA with relevant context from past interactions.

    Args:
        current_user: The authenticated user.
        initial_message: Optional first message to find relevant entities.

    Returns:
        PrimeConversationResponse with context for LLM.
    """
    try:
        # Initialize services
        db_client = SupabaseClient.get_client()
        llm_client = LLMClient()

        conversation_service = ConversationService(
            db_client=db_client,
            llm_client=llm_client,
        )
        salience_service = SalienceService(db_client=db_client)

        priming_service = ConversationPrimingService(
            conversation_service=conversation_service,
            salience_service=salience_service,
            db_client=db_client,
        )

        context = await priming_service.prime_conversation(
            user_id=current_user.id,
            initial_message=initial_message,
        )

        return PrimeConversationResponse(
            recent_context=context.recent_episodes,
            open_threads=context.open_threads,
            salient_facts=context.salient_facts,
            formatted_context=context.formatted_context,
        )

    except Exception as e:
        logger.error(
            "Failed to prime conversation",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to gather conversation context",
        ) from None
