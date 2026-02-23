"""Cold memory retrieval for on-demand deep memory search.

Provides parallel search across episodic, semantic, and lead memory
sources with relevance scoring and deduplication.

Used by agents when they need context beyond what hot context provides.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MemorySource(str, Enum):
    """Memory source type for cold retrieval."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    LEAD = "lead"


@dataclass
class ColdMemoryResult:
    """A single result from cold memory retrieval.

    Combines content from any memory source with a unified
    relevance score for ranking.
    """

    source: MemorySource
    content: str
    relevance_score: float  # 0.0-1.0
    data: dict[str, Any] = field(default_factory=dict)
    memory_id: str = ""
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source": self.source.value,
            "content": self.content,
            "relevance_score": self.relevance_score,
            "data": self.data,
            "memory_id": self.memory_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class EntityContext:
    """Aggregated context for a specific entity.

    Groups cold memory results into categories for
    entity-centric retrieval (e.g., "tell me about BioGenix").
    """

    entity_id: str
    direct_facts: list[ColdMemoryResult] = field(default_factory=list)
    relationships: list[ColdMemoryResult] = field(default_factory=list)
    recent_interactions: list[ColdMemoryResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "entity_id": self.entity_id,
            "direct_facts": [r.to_dict() for r in self.direct_facts],
            "relationships": [r.to_dict() for r in self.relationships],
            "recent_interactions": [r.to_dict() for r in self.recent_interactions],
        }


class ColdMemoryRetriever:
    """Retrieves memories from episodic, semantic, and lead sources.

    Searches all sources in parallel, scores results by a weighted
    combination of semantic similarity, recency, and salience, then
    deduplicates and ranks.
    """

    SEMANTIC_WEIGHT = 0.5
    RECENCY_WEIGHT = 0.3
    SALIENCE_WEIGHT = 0.2
    RECENCY_HALF_LIFE_DAYS = 14.0

    def __init__(
        self,
        db_client: Any,
        graphiti_client: Any | None = None,
    ) -> None:
        """Initialize the retriever.

        Args:
            db_client: Supabase client for database queries.
            graphiti_client: Optional Graphiti client for graph-based search.
        """
        self.db = db_client
        self.graphiti = graphiti_client

    async def retrieve(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        sources: list[MemorySource] | None = None,
        min_confidence: float = 0.3,
    ) -> list[ColdMemoryResult]:
        """Search across memory sources and return ranked results.

        Dispatches searches to all requested sources in parallel,
        scores and deduplicates results, then returns the top `limit`.

        Args:
            user_id: The user whose memories to search.
            query: Natural language search query.
            limit: Maximum results to return.
            sources: Which sources to search (default: all).
            min_confidence: Minimum confidence for semantic facts.

        Returns:
            Ranked list of ColdMemoryResult, best first.
        """
        active_sources = sources or list(MemorySource)

        tasks: list[asyncio.Task[list[ColdMemoryResult]]] = []

        if MemorySource.EPISODIC in active_sources:
            tasks.append(
                asyncio.ensure_future(
                    self._search_episodic(user_id, query, limit)
                )
            )

        if MemorySource.SEMANTIC in active_sources:
            tasks.append(
                asyncio.ensure_future(
                    self._search_semantic(user_id, query, min_confidence, limit)
                )
            )

        if MemorySource.LEAD in active_sources:
            tasks.append(
                asyncio.ensure_future(
                    self._search_lead(user_id, query, limit)
                )
            )

        if not tasks:
            return []

        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[ColdMemoryResult] = []
        for result in results_lists:
            if isinstance(result, BaseException):
                logger.warning("Cold memory source search failed: %s", result)
                continue
            all_results.extend(result)

        return self._merge_and_rank(all_results, limit)

    async def retrieve_for_entity(
        self,
        user_id: str,
        entity_id: str,
        hops: int = 2,
    ) -> EntityContext:
        """Retrieve context about a specific entity.

        Uses Graphiti for graph neighborhood traversal when available,
        falling back to Supabase text search.

        Args:
            user_id: The user whose memories to search.
            entity_id: The entity to retrieve context for.
            hops: Graph traversal depth (Graphiti only).

        Returns:
            EntityContext with categorized results.
        """
        ctx = EntityContext(entity_id=entity_id)

        # Try Graphiti for graph-based entity context
        if self.graphiti is not None:
            try:
                results = await self.graphiti.search(
                    f"entity {entity_id}",
                )
                for edge in results[:hops * 5]:
                    fact = getattr(edge, "fact", "")
                    edge_uuid = getattr(edge, "uuid", "")
                    created_at = getattr(edge, "created_at", None)
                    if isinstance(created_at, str):
                        from datetime import datetime as dt
                        created_at = dt.fromisoformat(created_at)

                    result = ColdMemoryResult(
                        source=MemorySource.SEMANTIC,
                        content=fact,
                        relevance_score=0.8,
                        data={"edge_uuid": edge_uuid},
                        memory_id=edge_uuid,
                        created_at=created_at,
                    )

                    # Categorize based on content
                    content_lower = fact.lower()
                    if any(kw in content_lower for kw in ["meeting", "call", "email", "discussed"]):
                        ctx.recent_interactions.append(result)
                    elif any(kw in content_lower for kw in ["works_at", "reports_to", "knows"]):
                        ctx.relationships.append(result)
                    else:
                        ctx.direct_facts.append(result)

                return ctx
            except Exception as e:
                logger.warning("Graphiti entity search failed, falling back: %s", e)

        # Fallback: Supabase text search across memory_semantic
        try:
            result = (
                self.db.table("memory_semantic")
                .select("id, fact, confidence, metadata, created_at")
                .eq("user_id", user_id)
                .ilike("fact", f"%{entity_id}%")
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            )
            rows = result.data if result else []
            for row in rows:
                cold_result = ColdMemoryResult(
                    source=MemorySource.SEMANTIC,
                    content=row.get("fact", ""),
                    relevance_score=row.get("confidence", 0.5),
                    data=row.get("metadata", {}),
                    memory_id=row.get("id", ""),
                    created_at=_parse_datetime(row.get("created_at")),
                )
                ctx.direct_facts.append(cold_result)
        except Exception as e:
            logger.warning("Supabase entity search failed: %s", e)

        return ctx

    async def _search_episodic(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[ColdMemoryResult]:
        """Search episodic memories."""
        try:
            from src.memory.episodic import EpisodicMemory

            episodic = EpisodicMemory()
            episodes = await episodic.semantic_search(user_id, query, limit=limit)

            results: list[ColdMemoryResult] = []
            for ep in episodes:
                relevance = self._compute_relevance(
                    semantic_score=0.7,  # Returned by search, assume decent match
                    created_at=ep.occurred_at,
                    salience=None,
                )
                results.append(
                    ColdMemoryResult(
                        source=MemorySource.EPISODIC,
                        content=ep.content,
                        relevance_score=relevance,
                        data=ep.to_dict(),
                        memory_id=ep.id,
                        created_at=ep.occurred_at,
                    )
                )
            return results
        except Exception as e:
            logger.warning("Episodic search failed: %s", e)
            return []

    async def _search_semantic(
        self,
        user_id: str,
        query: str,
        min_confidence: float,
        limit: int,
    ) -> list[ColdMemoryResult]:
        """Search semantic facts."""
        try:
            from src.memory.semantic import SemanticMemory

            semantic = SemanticMemory()
            facts = await semantic.search_facts(
                user_id, query, min_confidence=min_confidence, limit=limit
            )

            results: list[ColdMemoryResult] = []
            for fact in facts:
                relevance = self._compute_relevance(
                    semantic_score=fact.confidence,
                    created_at=fact.valid_from,
                    salience=None,
                )
                results.append(
                    ColdMemoryResult(
                        source=MemorySource.SEMANTIC,
                        content=f"{fact.subject} {fact.predicate} {fact.object}",
                        relevance_score=relevance,
                        data=fact.to_dict(),
                        memory_id=fact.id,
                        created_at=fact.valid_from,
                    )
                )
            return results
        except Exception as e:
            logger.warning("Semantic search failed: %s", e)
            return []

    async def _search_lead(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[ColdMemoryResult]:
        """Search lead memories via Supabase."""
        try:
            result = (
                self.db.table("lead_memories")
                .select("id, company_name, lifecycle_stage, status, metadata, created_at")
                .eq("user_id", user_id)
                .ilike("company_name", f"%{query}%")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            rows = result.data if result else []

            results: list[ColdMemoryResult] = []
            for row in rows:
                created_at = _parse_datetime(row.get("created_at"))
                relevance = self._compute_relevance(
                    semantic_score=0.6,
                    created_at=created_at,
                    salience=None,
                )
                content = f"{row.get('company_name', '')} - {row.get('lifecycle_stage', '')} ({row.get('status', '')})"
                results.append(
                    ColdMemoryResult(
                        source=MemorySource.LEAD,
                        content=content,
                        relevance_score=relevance,
                        data=row,
                        memory_id=row.get("id", ""),
                        created_at=created_at,
                    )
                )
            return results
        except Exception as e:
            logger.warning("Lead search failed: %s", e)
            return []

    def _compute_relevance(
        self,
        semantic_score: float,
        created_at: datetime | None,
        salience: float | None,
    ) -> float:
        """Compute a combined relevance score.

        Formula: 0.5*semantic + 0.3*recency + 0.2*salience

        Args:
            semantic_score: Similarity or confidence score (0-1).
            created_at: When the memory was created.
            salience: Access-based salience (0-1), or None.

        Returns:
            Combined relevance score (0-1).
        """
        recency = self._recency_score(created_at) if created_at else 0.5
        sal = salience if salience is not None else 0.5

        score = (
            self.SEMANTIC_WEIGHT * semantic_score
            + self.RECENCY_WEIGHT * recency
            + self.SALIENCE_WEIGHT * sal
        )
        return max(0.0, min(1.0, score))

    def _recency_score(self, created_at: datetime) -> float:
        """Compute recency score using exponential decay.

        Args:
            created_at: When the memory was created.

        Returns:
            Score between 0 and 1 (1 = just now, decays with half-life).
        """
        now = datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        days_ago = (now - created_at).total_seconds() / 86400
        if days_ago <= 0:
            return 1.0
        return math.pow(0.5, days_ago / self.RECENCY_HALF_LIFE_DAYS)

    def _merge_and_rank(
        self,
        results: list[ColdMemoryResult],
        limit: int,
    ) -> list[ColdMemoryResult]:
        """Deduplicate, sort by relevance, and limit results.

        Args:
            results: All results from all sources.
            limit: Maximum results to return.

        Returns:
            Deduplicated, sorted results.
        """
        # Deduplicate by memory_id (keep highest relevance)
        seen: dict[str, ColdMemoryResult] = {}
        for r in results:
            key = r.memory_id if r.memory_id else id(r)
            str_key = str(key)
            if str_key not in seen or r.relevance_score > seen[str_key].relevance_score:
                seen[str_key] = r

        deduped = list(seen.values())
        deduped.sort(key=lambda r: r.relevance_score, reverse=True)
        return deduped[:limit]


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse a datetime from a string or return as-is."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
