"""Tests for cold memory retrieval.

Validates ColdMemoryRetriever searches multiple sources in parallel,
ranks results, deduplicates, handles errors gracefully, and supports
entity-level context retrieval.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.cold_retrieval import (
    ColdMemoryResult,
    ColdMemoryRetriever,
    EntityContext,
    MemorySource,
    _parse_datetime,
)

# ── Helpers ──────────────────────────────────────────────────────


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    """Build a fluent Supabase query chain."""
    chain = MagicMock()
    for method in (
        "select", "eq", "gte", "lte", "in_", "ilike",
        "order", "limit", "maybe_single", "single",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


def _make_episode(
    episode_id: str = "ep-1",
    content: str = "Meeting with BioGenix team",
    occurred_at: datetime | None = None,
) -> MagicMock:
    """Create a mock Episode."""
    ep = MagicMock()
    ep.id = episode_id
    ep.content = content
    ep.occurred_at = occurred_at or datetime.now(UTC)
    ep.to_dict.return_value = {
        "id": episode_id,
        "content": content,
        "occurred_at": ep.occurred_at.isoformat(),
    }
    return ep


def _make_fact(
    fact_id: str = "fact-1",
    subject: str = "BioGenix",
    predicate: str = "has_pipeline",
    obj: str = "Phase 3 oncology",
    confidence: float = 0.85,
    valid_from: datetime | None = None,
) -> MagicMock:
    """Create a mock SemanticFact."""
    fact = MagicMock()
    fact.id = fact_id
    fact.subject = subject
    fact.predicate = predicate
    fact.object = obj
    fact.confidence = confidence
    fact.valid_from = valid_from or datetime.now(UTC)
    fact.to_dict.return_value = {
        "id": fact_id,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "confidence": confidence,
    }
    return fact


# ── ColdMemoryResult tests ──────────────────────────────────────


class TestColdMemoryResult:
    """Tests for ColdMemoryResult dataclass."""

    def test_to_dict_serialization(self) -> None:
        """to_dict produces expected structure."""
        now = datetime.now(UTC)
        result = ColdMemoryResult(
            source=MemorySource.EPISODIC,
            content="Meeting notes",
            relevance_score=0.85,
            data={"key": "value"},
            memory_id="mem-1",
            created_at=now,
        )
        d = result.to_dict()
        assert d["source"] == "episodic"
        assert d["relevance_score"] == 0.85
        assert d["memory_id"] == "mem-1"
        assert d["created_at"] == now.isoformat()

    def test_to_dict_with_none_created_at(self) -> None:
        """to_dict handles None created_at."""
        result = ColdMemoryResult(
            source=MemorySource.SEMANTIC,
            content="A fact",
            relevance_score=0.5,
        )
        d = result.to_dict()
        assert d["created_at"] is None

    def test_memory_source_enum_values(self) -> None:
        """MemorySource enum has expected values."""
        assert MemorySource.EPISODIC.value == "episodic"
        assert MemorySource.SEMANTIC.value == "semantic"
        assert MemorySource.LEAD.value == "lead"


# ── EntityContext tests ──────────────────────────────────────────


class TestEntityContext:
    """Tests for EntityContext dataclass."""

    def test_to_dict_serialization(self) -> None:
        """to_dict produces categorized structure."""
        ctx = EntityContext(
            entity_id="bioGenix",
            direct_facts=[
                ColdMemoryResult(
                    source=MemorySource.SEMANTIC,
                    content="BioGenix has Phase 3",
                    relevance_score=0.9,
                )
            ],
        )
        d = ctx.to_dict()
        assert d["entity_id"] == "bioGenix"
        assert len(d["direct_facts"]) == 1
        assert len(d["relationships"]) == 0
        assert len(d["recent_interactions"]) == 0

    def test_empty_entity_context(self) -> None:
        """Empty EntityContext serializes correctly."""
        ctx = EntityContext(entity_id="unknown")
        d = ctx.to_dict()
        assert d["entity_id"] == "unknown"
        assert d["direct_facts"] == []


# ── ColdMemoryRetriever.retrieve tests ───────────────────────────


class TestColdRetrieve:
    """Tests for ColdMemoryRetriever.retrieve()."""

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture()
    def retriever(self, mock_db: MagicMock) -> ColdMemoryRetriever:
        return ColdMemoryRetriever(db_client=mock_db)

    @pytest.mark.asyncio()
    async def test_retrieve_searches_all_sources(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock
    ) -> None:
        """retrieve() dispatches to episodic, semantic, and lead."""
        mock_db.table.side_effect = lambda _name: _build_chain([])

        with (
            patch(
                "src.memory.episodic.EpisodicMemory"
            ) as mock_ep_cls,
            patch(
                "src.memory.semantic.SemanticMemory"
            ) as mock_sem_cls,
        ):
            mock_ep = mock_ep_cls.return_value
            mock_ep.semantic_search = AsyncMock(return_value=[_make_episode()])

            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(return_value=[_make_fact()])

            results = await retriever.retrieve("user-1", "BioGenix")

        assert len(results) >= 2  # At least episodic + semantic
        sources = {r.source for r in results}
        assert MemorySource.EPISODIC in sources
        assert MemorySource.SEMANTIC in sources

    @pytest.mark.asyncio()
    async def test_retrieve_filters_by_source(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock  # noqa: ARG002
    ) -> None:
        """Only specified sources are searched."""
        with patch(
            "src.memory.semantic.SemanticMemory"
        ) as mock_sem_cls:
            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(return_value=[_make_fact()])

            results = await retriever.retrieve(
                "user-1", "test", sources=[MemorySource.SEMANTIC]
            )

        assert all(r.source == MemorySource.SEMANTIC for r in results)

    @pytest.mark.asyncio()
    async def test_retrieve_returns_ranked_results(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock
    ) -> None:
        """Results are sorted by relevance descending."""
        mock_db.table.side_effect = lambda _name: _build_chain([])

        with (
            patch(
                "src.memory.episodic.EpisodicMemory"
            ) as mock_ep_cls,
            patch(
                "src.memory.semantic.SemanticMemory"
            ) as mock_sem_cls,
        ):
            mock_ep = mock_ep_cls.return_value
            mock_ep.semantic_search = AsyncMock(
                return_value=[_make_episode("ep-1", "Old meeting")]
            )

            # High-confidence fact should rank higher
            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(
                return_value=[_make_fact("f-1", confidence=0.95)]
            )

            results = await retriever.retrieve("user-1", "test")

        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i].relevance_score >= results[i + 1].relevance_score

    @pytest.mark.asyncio()
    async def test_retrieve_limits_results(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock  # noqa: ARG002
    ) -> None:
        """Respects the limit parameter."""
        with patch(
            "src.memory.semantic.SemanticMemory"
        ) as mock_sem_cls:
            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(
                return_value=[
                    _make_fact(f"f-{i}") for i in range(20)
                ]
            )

            results = await retriever.retrieve(
                "user-1", "test", limit=3, sources=[MemorySource.SEMANTIC]
            )

        assert len(results) <= 3

    @pytest.mark.asyncio()
    async def test_retrieve_deduplicates(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock  # noqa: ARG002
    ) -> None:
        """Duplicate memory_ids are deduplicated (keep best score)."""
        with patch(
            "src.memory.semantic.SemanticMemory"
        ) as mock_sem_cls:
            # Two facts with same ID but different confidence
            fact_a = _make_fact("same-id", confidence=0.6)
            fact_b = _make_fact("same-id", confidence=0.9)
            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(return_value=[fact_a, fact_b])

            results = await retriever.retrieve(
                "user-1", "test", sources=[MemorySource.SEMANTIC]
            )

        # Should only have one result for "same-id"
        ids = [r.memory_id for r in results]
        assert ids.count("same-id") == 1

    @pytest.mark.asyncio()
    async def test_retrieve_handles_source_failure(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock
    ) -> None:
        """Returns results from healthy sources when one fails."""
        mock_db.table.side_effect = Exception("Lead DB down")

        with (
            patch(
                "src.memory.episodic.EpisodicMemory"
            ) as mock_ep_cls,
            patch(
                "src.memory.semantic.SemanticMemory"
            ) as mock_sem_cls,
        ):
            mock_ep = mock_ep_cls.return_value
            mock_ep.semantic_search = AsyncMock(return_value=[_make_episode()])

            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(return_value=[_make_fact()])

            results = await retriever.retrieve("user-1", "test")

        # Lead failed but episodic + semantic should still work
        assert len(results) >= 1

    @pytest.mark.asyncio()
    async def test_retrieve_handles_all_failures(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock
    ) -> None:
        """Returns empty list when all sources fail."""
        mock_db.table.side_effect = Exception("DB down")

        with (
            patch(
                "src.memory.episodic.EpisodicMemory"
            ) as mock_ep_cls,
            patch(
                "src.memory.semantic.SemanticMemory"
            ) as mock_sem_cls,
        ):
            mock_ep = mock_ep_cls.return_value
            mock_ep.semantic_search = AsyncMock(side_effect=Exception("Graphiti down"))

            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(side_effect=Exception("Semantic down"))

            results = await retriever.retrieve("user-1", "test")

        assert results == []

    @pytest.mark.asyncio()
    async def test_retrieve_respects_min_confidence(
        self, retriever: ColdMemoryRetriever, mock_db: MagicMock  # noqa: ARG002
    ) -> None:
        """min_confidence is passed to semantic search."""
        with patch(
            "src.memory.semantic.SemanticMemory"
        ) as mock_sem_cls:
            mock_sem = mock_sem_cls.return_value
            mock_sem.search_facts = AsyncMock(return_value=[])

            await retriever.retrieve(
                "user-1",
                "test",
                sources=[MemorySource.SEMANTIC],
                min_confidence=0.8,
            )

            mock_sem.search_facts.assert_called_once_with(
                "user-1", "test", min_confidence=0.8, limit=10
            )


# ── Entity retrieval tests ───────────────────────────────────────


class TestRetrieveForEntity:
    """Tests for ColdMemoryRetriever.retrieve_for_entity()."""

    @pytest.mark.asyncio()
    async def test_entity_graphiti_search(self) -> None:
        """Uses Graphiti when available."""
        mock_graphiti = AsyncMock()
        edge = MagicMock()
        edge.fact = "BioGenix has Phase 3 pipeline"
        edge.uuid = "edge-1"
        edge.created_at = datetime.now(UTC)
        mock_graphiti.search = AsyncMock(return_value=[edge])

        retriever = ColdMemoryRetriever(
            db_client=MagicMock(), graphiti_client=mock_graphiti
        )
        ctx = await retriever.retrieve_for_entity("user-1", "BioGenix")

        assert isinstance(ctx, EntityContext)
        assert ctx.entity_id == "BioGenix"
        assert len(ctx.direct_facts) + len(ctx.relationships) + len(ctx.recent_interactions) > 0

    @pytest.mark.asyncio()
    async def test_entity_fallback_to_supabase(self) -> None:
        """Falls back to Supabase when no Graphiti."""
        mock_db = MagicMock()
        mock_db.table.return_value = _build_chain([
            {"id": "f1", "fact": "BioGenix pipeline", "confidence": 0.8, "metadata": {}, "created_at": "2026-01-15T00:00:00+00:00"},
        ])

        retriever = ColdMemoryRetriever(db_client=mock_db, graphiti_client=None)
        ctx = await retriever.retrieve_for_entity("user-1", "BioGenix")

        assert len(ctx.direct_facts) == 1
        assert "pipeline" in ctx.direct_facts[0].content


# ── Relevance scoring tests ──────────────────────────────────────


class TestRelevanceScoring:
    """Tests for relevance score computation."""

    def test_score_bounds(self) -> None:
        """Score is always between 0 and 1."""
        retriever = ColdMemoryRetriever(db_client=MagicMock())

        # High semantic, recent
        score = retriever._compute_relevance(1.0, datetime.now(UTC), 1.0)
        assert 0.0 <= score <= 1.0

        # Low everything
        old = datetime.now(UTC) - timedelta(days=365)
        score = retriever._compute_relevance(0.0, old, 0.0)
        assert 0.0 <= score <= 1.0

    def test_recent_scores_higher(self) -> None:
        """Recent memories score higher than old ones."""
        retriever = ColdMemoryRetriever(db_client=MagicMock())
        now = datetime.now(UTC)
        old = now - timedelta(days=60)

        recent_score = retriever._compute_relevance(0.7, now, 0.5)
        old_score = retriever._compute_relevance(0.7, old, 0.5)
        assert recent_score > old_score

    def test_higher_semantic_scores_higher(self) -> None:
        """Higher semantic similarity produces higher score."""
        retriever = ColdMemoryRetriever(db_client=MagicMock())
        now = datetime.now(UTC)

        high_score = retriever._compute_relevance(0.9, now, 0.5)
        low_score = retriever._compute_relevance(0.3, now, 0.5)
        assert high_score > low_score

    def test_none_created_at_uses_default(self) -> None:
        """None created_at uses 0.5 as recency score."""
        retriever = ColdMemoryRetriever(db_client=MagicMock())
        score = retriever._compute_relevance(0.7, None, 0.5)
        assert 0.0 <= score <= 1.0


# ── Merge and rank tests ─────────────────────────────────────────


class TestMergeAndRank:
    """Tests for the merge, sort, deduplicate, limit pipeline."""

    def test_deduplicates_by_memory_id(self) -> None:
        """Same memory_id keeps only the highest-scoring version."""
        retriever = ColdMemoryRetriever(db_client=MagicMock())
        results = [
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content="low",
                relevance_score=0.3,
                memory_id="dup",
            ),
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content="high",
                relevance_score=0.9,
                memory_id="dup",
            ),
        ]
        merged = retriever._merge_and_rank(results, limit=10)
        assert len(merged) == 1
        assert merged[0].content == "high"

    def test_sorts_descending(self) -> None:
        """Results are sorted by relevance descending."""
        retriever = ColdMemoryRetriever(db_client=MagicMock())
        results = [
            ColdMemoryResult(source=MemorySource.EPISODIC, content="low", relevance_score=0.2, memory_id="a"),
            ColdMemoryResult(source=MemorySource.SEMANTIC, content="high", relevance_score=0.9, memory_id="b"),
            ColdMemoryResult(source=MemorySource.LEAD, content="mid", relevance_score=0.5, memory_id="c"),
        ]
        merged = retriever._merge_and_rank(results, limit=10)
        assert merged[0].relevance_score == 0.9
        assert merged[1].relevance_score == 0.5
        assert merged[2].relevance_score == 0.2

    def test_respects_limit(self) -> None:
        """Output is truncated to limit."""
        retriever = ColdMemoryRetriever(db_client=MagicMock())
        results = [
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content=f"item-{i}",
                relevance_score=i / 10,
                memory_id=f"id-{i}",
            )
            for i in range(10)
        ]
        merged = retriever._merge_and_rank(results, limit=3)
        assert len(merged) == 3


# ── Parse datetime helper tests ──────────────────────────────────


class TestParseDatetime:
    """Tests for the _parse_datetime helper."""

    def test_parse_none(self) -> None:
        assert _parse_datetime(None) is None

    def test_parse_datetime_passthrough(self) -> None:
        now = datetime.now(UTC)
        assert _parse_datetime(now) is now

    def test_parse_iso_string(self) -> None:
        result = _parse_datetime("2026-01-15T10:00:00+00:00")
        assert isinstance(result, datetime)

    def test_parse_invalid_string(self) -> None:
        assert _parse_datetime("not-a-date") is None
