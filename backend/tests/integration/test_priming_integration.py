"""Integration tests for conversation priming flow."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestPrimingIntegration:
    """Integration tests for the full priming flow."""

    @pytest.fixture
    def mock_db_with_data(self) -> MagicMock:
        """Create mock DB with episodes and facts."""
        mock = MagicMock()
        now = datetime.now(UTC)

        # Mock conversation_episodes table
        episodes_data = [
            {
                "id": "ep-1",
                "user_id": "user-test",
                "conversation_id": "conv-1",
                "summary": "Discussed Q1 sales targets with John",
                "key_topics": ["sales", "Q1", "targets"],
                "entities_discussed": ["John Doe", "Acme Corp"],
                "user_state": {"mood": "focused"},
                "outcomes": [{"type": "decision", "content": "Increase Q1 target by 10%"}],
                "open_threads": [
                    {"topic": "pricing review", "status": "pending", "context": "Awaiting CFO"}
                ],
                "message_count": 15,
                "duration_minutes": 20,
                "started_at": (now - timedelta(hours=2)).isoformat(),
                "ended_at": (now - timedelta(hours=1, minutes=40)).isoformat(),
                "current_salience": 0.95,
                "last_accessed_at": now.isoformat(),
                "access_count": 3,
            },
            {
                "id": "ep-2",
                "user_id": "user-test",
                "conversation_id": "conv-2",
                "summary": "Quick sync about contract status",
                "key_topics": ["contract", "legal"],
                "entities_discussed": ["Legal Team"],
                "user_state": {"mood": "neutral"},
                "outcomes": [],
                "open_threads": [
                    {"topic": "contract review", "status": "awaiting_response", "context": "Legal reviewing"}
                ],
                "message_count": 5,
                "duration_minutes": 8,
                "started_at": (now - timedelta(days=1)).isoformat(),
                "ended_at": (now - timedelta(days=1) + timedelta(minutes=8)).isoformat(),
                "current_salience": 0.75,
                "last_accessed_at": (now - timedelta(hours=12)).isoformat(),
                "access_count": 1,
            },
        ]

        # Mock semantic_fact_salience table
        salience_data = [
            {"graphiti_episode_id": "fact-1", "current_salience": 0.90, "access_count": 5},
            {"graphiti_episode_id": "fact-2", "current_salience": 0.65, "access_count": 2},
        ]

        # Mock semantic_facts table
        facts_data = [
            {
                "id": "fact-1",
                "subject": "John Doe",
                "predicate": "works_at",
                "object": "Acme Corp",
                "confidence": 0.95,
            },
            {
                "id": "fact-2",
                "subject": "Acme Corp",
                "predicate": "industry",
                "object": "Technology",
                "confidence": 0.88,
            },
        ]

        def table_mock(table_name: str) -> MagicMock:
            """Return appropriate mock based on table name."""
            table = MagicMock()

            if table_name == "conversation_episodes":
                # For get_recent_episodes
                table.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=episodes_data
                )
                # For get_open_threads
                table.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=episodes_data
                )
            elif table_name == "semantic_fact_salience":
                table.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=salience_data
                )
            elif table_name == "memory_semantic":
                # _fetch_fact_details now queries memory_semantic with .eq().order().limit()
                table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[
                        {"id": "fact-1", "fact": "John Doe works_at Acme Corp", "confidence": 0.95},
                    ]
                )
            elif table_name == "semantic_facts":
                # _fetch_fact_details now queries semantic_facts with .eq().order().limit()
                table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[
                        {
                            "id": "fact-2",
                            "subject": "Acme Corp",
                            "predicate": "industry",
                            "object": "Technology",
                            "confidence": 0.88,
                        },
                    ]
                )

            return table

        mock.table = table_mock
        return mock

    @pytest.mark.asyncio
    async def test_full_priming_flow(self, mock_db_with_data: MagicMock) -> None:
        """Test the full priming flow from service to formatted output."""
        from src.memory.conversation import ConversationService
        from src.memory.priming import ConversationPrimingService
        from src.memory.salience import SalienceService

        mock_llm = MagicMock()

        conversation_service = ConversationService(
            db_client=mock_db_with_data,
            llm_client=mock_llm,
        )
        salience_service = SalienceService(db_client=mock_db_with_data)

        priming_service = ConversationPrimingService(
            conversation_service=conversation_service,
            salience_service=salience_service,
            db_client=mock_db_with_data,
        )

        context = await priming_service.prime_conversation(user_id="user-test")

        # Verify episodes were fetched
        assert len(context.recent_episodes) == 2
        assert context.recent_episodes[0]["summary"] == "Discussed Q1 sales targets with John"

        # Verify open threads were aggregated
        assert len(context.open_threads) >= 1

        # Verify facts were fetched
        assert len(context.salient_facts) == 2

        # Verify formatted context includes all sections
        assert "## Recent Conversations" in context.formatted_context
        assert "Discussed Q1 sales targets" in context.formatted_context
        assert "Increase Q1 target by 10%" in context.formatted_context  # Outcome
        assert "## Open Threads" in context.formatted_context
        assert "## Key Facts I Remember" in context.formatted_context
        # Facts come from memory_semantic (subject=fact text) and semantic_facts
        assert "John Doe works_at Acme Corp" in context.formatted_context

    @pytest.mark.asyncio
    async def test_priming_performance_parallel_fetch(self) -> None:
        """Verify priming uses parallel fetching."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        # Track call times
        call_times: list[tuple[str, float]] = []

        async def mock_get_episodes(*_args: object, **_kwargs: object) -> list[object]:
            call_times.append(("episodes", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.05)  # 50ms
            return []

        async def mock_get_threads(*_args: object, **_kwargs: object) -> list[object]:
            call_times.append(("threads", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.05)  # 50ms
            return []

        async def mock_get_salience(*_args: object, **_kwargs: object) -> list[object]:
            call_times.append(("salience", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.05)  # 50ms
            return []

        mock_conversation_service.get_recent_episodes = mock_get_episodes
        mock_conversation_service.get_open_threads = mock_get_threads
        mock_salience_service.get_by_salience = mock_get_salience

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        start = asyncio.get_event_loop().time()
        await service.prime_conversation(user_id="user-test")
        elapsed = asyncio.get_event_loop().time() - start

        # If parallel, should take ~50ms, not ~150ms
        # Allow some margin for test overhead
        assert elapsed < 0.15, f"Priming took {elapsed:.3f}s, expected parallel execution"

        # All calls should start at approximately the same time
        times = [t for _, t in call_times]
        max_diff = max(times) - min(times)
        assert max_diff < 0.02, f"Calls not parallel: time diff {max_diff:.3f}s"

    @pytest.mark.asyncio
    async def test_priming_handles_empty_data(self) -> None:
        """Priming should handle users with no history gracefully."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_conversation_service.get_recent_episodes = AsyncMock(return_value=[])
        mock_conversation_service.get_open_threads = AsyncMock(return_value=[])

        mock_salience_service = MagicMock()
        mock_salience_service.get_by_salience = AsyncMock(return_value=[])

        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        context = await service.prime_conversation(user_id="new-user")

        assert context.recent_episodes == []
        assert context.open_threads == []
        assert context.salient_facts == []
        assert context.formatted_context == "No prior context available."
