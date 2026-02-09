"""Base capability for ARIA agents.

A capability is a discrete, composable unit of functionality that an agent
can use to accomplish tasks. Capabilities are the bridge between the agent
system and the services/data layer — they encapsulate access to Supabase,
the memory system, and the knowledge graph behind a task-oriented interface.

Each capability declares:
- Which tasks it can handle (via ``can_handle``)
- What data classifications it accesses (for security auditing)
- Which agent types may invoke it
- Which OAuth scopes are required

Usage::

    class CompanyResearchCapability(BaseCapability):
        capability_name = "company_research"
        agent_types = ["hunter", "analyst"]
        oauth_scopes = ["crm:read"]

        async def can_handle(self, task):
            if task.get("type") == "company_research":
                return 0.9
            return 0.0

        async def execute(self, task, context):
            ...
            return CapabilityResult(success=True, data={...})

        def get_data_classes_accessed(self):
            return ["internal", "confidential"]
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class UserContext(BaseModel):
    """Minimal user context passed to every capability invocation."""

    user_id: str = Field(..., description="Authenticated user UUID")
    tenant_id: str | None = Field(None, description="Tenant UUID for multi-tenant isolation")
    session_id: str | None = Field(None, description="Current session identifier")


class CapabilityResult(BaseModel):
    """Structured result returned by every capability execution.

    Attributes:
        success: Whether the capability completed without error.
        data: Arbitrary output payload (JSON-serialisable).
        error: Human-readable error message when ``success`` is False.
        artifacts: Paths or URIs of files/objects produced.
        extracted_facts: Semantic facts extracted during execution,
            suitable for storage in Graphiti / pgvector.
        tokens_used: LLM tokens consumed (if applicable).
        execution_time_ms: Wall-clock execution time in milliseconds.
    """

    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    extracted_facts: list[dict[str, Any]] = Field(default_factory=list)
    tokens_used: int = 0
    execution_time_ms: int = 0


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class BaseCapability(ABC):
    """Abstract base class for agent capabilities.

    Subclasses **must** set the three class-level attributes
    (``capability_name``, ``agent_types``, ``oauth_scopes``) and implement
    the three abstract methods.

    Parameters:
        supabase_client: Supabase ``Client`` instance (from ``SupabaseClient.get_client()``).
        memory_service: Unified memory manager for six-type memory access.
        knowledge_graph: Graphiti client for Neo4j operations.
        user_context: Authenticated user metadata.
    """

    # -- Subclass must override ------------------------------------------------
    capability_name: str = ""
    """Short identifier such as ``"company_research"``."""

    agent_types: list[str] = []
    """Agent names that may invoke this capability (e.g. ``["hunter", "analyst"]``)."""

    oauth_scopes: list[str] = []
    """OAuth scopes required for this capability (e.g. ``["crm:read"]``)."""

    # --------------------------------------------------------------------------

    def __init__(
        self,
        supabase_client: Any,
        memory_service: Any,
        knowledge_graph: Any,
        user_context: UserContext,
    ) -> None:
        self._supabase = supabase_client
        self._memory = memory_service
        self._kg = knowledge_graph
        self._user_context = user_context
        self._activity_service = ActivityService()

    # -- Accessors -------------------------------------------------------------

    def get_supabase(self) -> Any:
        """Return the Supabase client."""
        return self._supabase

    def get_memory(self) -> Any:
        """Return the unified memory service."""
        return self._memory

    def get_kg(self) -> Any:
        """Return the knowledge-graph (Graphiti) client."""
        return self._kg

    # -- Abstract interface ----------------------------------------------------

    @abstractmethod
    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return a confidence score (0.0–1.0) for handling *task*.

        0.0 means "definitely cannot handle"; 1.0 means "perfect match".
        The orchestrator uses this to route tasks to the best capability.

        Args:
            task: Task specification dict (must contain at least ``"type"``).

        Returns:
            Float in [0.0, 1.0].
        """

    @abstractmethod
    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> CapabilityResult:
        """Execute the capability against *task* with additional *context*.

        Args:
            task: Task specification dict.
            context: Runtime context (memory snapshots, working-memory entries, etc.).

        Returns:
            :class:`CapabilityResult` with output data or error.
        """

    @abstractmethod
    def get_data_classes_accessed(self) -> list[str]:
        """Declare which data-classification levels this capability touches.

        Must return a subset of
        ``["public", "internal", "confidential", "restricted", "regulated"]``.

        The security layer uses this to decide whether the invoking skill's
        trust level permits calling the capability.
        """

    # -- Concrete helpers ------------------------------------------------------

    async def log_activity(
        self,
        activity_type: str,
        title: str,
        description: str,
        *,
        confidence: float = 0.5,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write an entry to the ``aria_activity`` table.

        This is a convenience wrapper around :class:`ActivityService.record`
        so capabilities can log their actions in the shared activity feed.

        Args:
            activity_type: Activity type key (e.g. ``"research_complete"``).
            title: Short human-readable title.
            description: Longer description of what happened.
            confidence: Confidence level 0-1.
            related_entity_type: Optional entity kind (lead, goal, contact, company).
            related_entity_id: Optional entity UUID.
            metadata: Arbitrary extra JSON metadata.

        Returns:
            The created activity row dict.
        """
        return await self._activity_service.record(
            user_id=self._user_context.user_id,
            agent=self.capability_name,
            activity_type=activity_type,
            title=title,
            description=description,
            confidence=confidence,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            metadata=metadata or {},
        )
