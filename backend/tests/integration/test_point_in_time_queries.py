"""Integration tests for point-in-time memory queries.

Tests the full flow of temporal queries across episodic and semantic memory
to verify US-214 acceptance criteria.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.episodic import Episode, EpisodicMemory
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory


class TestPointInTimeEpisodic:
    """Integration tests for episodic memory point-in-time queries."""

    @pytest.mark.asyncio
    async def test_query_returns_only_episodes_known_at_as_of_date(self) -> None:
        """Test that point-in-time query excludes episodes recorded after as_of."""
        memory = EpisodicMemory()
        mock_client = MagicMock()

        now = datetime.now(UTC)

        # Create three episodes with different recording times
        episodes_data = [
            {
                "occurred": now - timedelta(days=60),
                "recorded": now - timedelta(days=60),  # Known 60 days ago
                "content": "Old meeting",
                "uuid": "ep-old",
            },
            {
                "occurred": now - timedelta(days=40),
                "recorded": now - timedelta(days=20),  # Known 20 days ago
                "content": "Backdated meeting",
                "uuid": "ep-backdated",
            },
            {
                "occurred": now - timedelta(days=30),
                "recorded": now - timedelta(days=5),  # Known 5 days ago
                "content": "Recent recording",
                "uuid": "ep-recent",
            },
        ]

        mock_edges = []
        for ep in episodes_data:
            edge = MagicMock()
            edge.fact = (
                f"Event Type: meeting\n"
                f"Content: {ep['content']}\n"
                f"Occurred At: {ep['occurred'].isoformat()}\n"
                f"Recorded At: {ep['recorded'].isoformat()}"
            )
            edge.created_at = ep["occurred"]
            edge.uuid = ep["uuid"]
            mock_edges.append(edge)

        mock_client.search = AsyncMock(return_value=mock_edges)

        with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client

            # Query as of 30 days ago - should only include the first episode
            as_of_date = now - timedelta(days=30)
            results = await memory.semantic_search(
                user_id="user-123",
                query="meeting",
                as_of=as_of_date,
            )

            # Only "Old meeting" was recorded by 30 days ago
            assert len(results) == 1
            assert results[0].content == "Old meeting"


class TestPointInTimeSemantic:
    """Integration tests for semantic memory point-in-time queries."""

    @pytest.mark.asyncio
    async def test_query_returns_facts_valid_at_as_of_date(self) -> None:
        """Test that point-in-time query respects fact validity windows."""
        memory = SemanticMemory()
        mock_client = MagicMock()

        now = datetime.now(UTC)

        # Create facts with different validity periods
        facts_data = [
            {
                "subject": "John",
                "predicate": "works_at",
                "object": "CompanyA",
                "valid_from": now - timedelta(days=365),
                "valid_to": now - timedelta(days=100),  # Expired 100 days ago
                "uuid": "fact-expired",
            },
            {
                "subject": "John",
                "predicate": "works_at",
                "object": "CompanyB",
                "valid_from": now - timedelta(days=100),
                "valid_to": None,  # Still valid
                "uuid": "fact-current",
            },
        ]

        mock_edges = []
        for fact in facts_data:
            edge = MagicMock()
            valid_to_str = (
                f"\nValid To: {fact['valid_to'].isoformat()}" if fact["valid_to"] else ""
            )
            edge.fact = (
                f"Subject: {fact['subject']}\n"
                f"Predicate: {fact['predicate']}\n"
                f"Object: {fact['object']}\n"
                f"Confidence: 0.90\n"
                f"Source: user_stated\n"
                f"Valid From: {fact['valid_from'].isoformat()}"
                f"{valid_to_str}"
            )
            edge.created_at = fact["valid_from"]
            edge.uuid = fact["uuid"]
            mock_edges.append(edge)

        mock_client.search = AsyncMock(return_value=mock_edges)

        with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client

            # Query as of 150 days ago - only CompanyA should be valid
            as_of_date = now - timedelta(days=150)
            results = await memory.search_facts(
                user_id="user-123",
                query="where does John work",
                as_of=as_of_date,
            )

            assert len(results) == 1
            assert results[0].object == "CompanyA"

            # Query as of today - only CompanyB should be valid
            results_now = await memory.search_facts(
                user_id="user-123",
                query="where does John work",
                as_of=now,
            )

            assert len(results_now) == 1
            assert results_now[0].object == "CompanyB"


class TestPointInTimeConfidence:
    """Integration tests for confidence scoring at point in time."""

    def test_effective_confidence_at_past_date(self) -> None:
        """Test confidence calculation uses correct decay for as_of date."""
        now = datetime.now(UTC)

        # Fact created 90 days ago, never confirmed
        fact = SemanticFact(
            id="fact-confidence",
            user_id="user-123",
            subject="Market",
            predicate="size",
            object="$1B",
            confidence=0.80,
            source=FactSource.WEB_RESEARCH,
            valid_from=now - timedelta(days=90),
            last_confirmed_at=None,
            corroborating_sources=[],
        )

        memory = SemanticMemory()

        # Confidence at creation (no decay yet - within 7 day window)
        creation_plus_3 = now - timedelta(days=87)
        conf_at_creation = memory.get_effective_confidence(fact, as_of=creation_plus_3)
        assert conf_at_creation == 0.80  # No decay within refresh window

        # Confidence now (should have decayed)
        conf_now = memory.get_effective_confidence(fact, as_of=now)
        # 0.80 - ((90-7) * 0.05/30) = 0.80 - 0.138 = 0.662
        assert conf_now < 0.80
        assert conf_now > 0.60  # Should still be above floor

        # Confidence at 30 days ago
        conf_30_ago = memory.get_effective_confidence(fact, as_of=now - timedelta(days=30))
        # Should be between creation and now
        assert conf_at_creation >= conf_30_ago >= conf_now


class TestPointInTimeInvalidatedFacts:
    """Integration tests for handling invalidated facts."""

    def test_is_valid_returns_false_regardless_of_as_of_when_invalidated(self) -> None:
        """Test invalidated facts are never valid, even at past dates."""
        now = datetime.now(UTC)

        fact = SemanticFact(
            id="fact-invalidated",
            user_id="user-123",
            subject="Data",
            predicate="status",
            object="Active",
            confidence=0.90,
            source=FactSource.USER_STATED,
            valid_from=now - timedelta(days=60),
            invalidated_at=now - timedelta(days=10),
            invalidation_reason="superseded",
        )

        # Even checking validity at 30 days ago (before invalidation),
        # the fact should be invalid because invalidated_at is set
        assert fact.is_valid(as_of=now - timedelta(days=30)) is False
        assert fact.is_valid(as_of=now) is False

    @pytest.mark.asyncio
    async def test_get_facts_about_respects_include_invalidated_with_as_of(self) -> None:
        """Test that include_invalidated works with as_of parameter."""
        memory = SemanticMemory()
        mock_client = MagicMock()

        now = datetime.now(UTC)

        # Fact that is not explicitly invalidated
        mock_edge = MagicMock()
        mock_edge.fact = (
            f"Subject: Account\n"
            f"Predicate: status\n"
            f"Object: Active\n"
            f"Confidence: 0.90\n"
            f"Source: user_stated\n"
            f"Valid From: {(now - timedelta(days=60)).isoformat()}"
        )
        mock_edge.created_at = now - timedelta(days=60)
        mock_edge.uuid = "fact-inv"

        mock_client.search = AsyncMock(return_value=[mock_edge])

        with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client

            # Without include_invalidated, should respect validity
            results = await memory.get_facts_about(
                user_id="user-123",
                subject="Account",
                as_of=now - timedelta(days=30),
                include_invalidated=False,
            )

            # The mock fact is valid (not explicitly invalidated)
            assert len(results) == 1
