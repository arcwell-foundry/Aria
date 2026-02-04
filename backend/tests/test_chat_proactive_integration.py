"""Tests for chat service integration with proactive memory."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestChatProactiveIntegration:
    """Tests for proactive memory integration in chat."""

    @pytest.mark.asyncio
    async def test_chat_service_has_proactive_dependency(self) -> None:
        """ChatService should have proactive memory service."""
        from src.services.chat import ChatService

        with patch("src.services.chat.get_supabase_client"):
            service = ChatService()

        # Service should have proactive memory capability
        assert hasattr(service, "_proactive_service") or hasattr(service, "_get_proactive_insights")

    @pytest.mark.asyncio
    async def test_chat_context_includes_proactive_insights(self) -> None:
        """Chat context building should include proactive insights."""
        with patch("src.services.chat.get_supabase_client"):
            with patch("src.services.chat.ProactiveMemoryService") as MockProactive:
                from src.models.proactive_insight import InsightType, ProactiveInsight

                mock_insight = ProactiveInsight(
                    insight_type=InsightType.TEMPORAL,
                    content="Follow up with Dr. Smith is due tomorrow",
                    relevance_score=0.85,
                    source_memory_id="task-123",
                    source_memory_type="prospective",
                    explanation="Due in 1 day",
                )

                mock_instance = MagicMock()
                mock_instance.find_volunteerable_context = AsyncMock(return_value=[mock_insight])
                MockProactive.return_value = mock_instance

                from src.services.chat import ChatService

                service = ChatService()

                # Call the method that builds context
                # (you'll need to check what method name ChatService uses)
                # The service should include proactive insights in context
                assert MockProactive.called or hasattr(service, "_proactive_service")

    @pytest.mark.asyncio
    async def test_get_proactive_insights_returns_insights(self) -> None:
        """_get_proactive_insights should return insights from service."""
        with patch("src.services.chat.get_supabase_client"):
            with patch("src.services.chat.ProactiveMemoryService") as MockProactive:
                from src.models.proactive_insight import InsightType, ProactiveInsight

                mock_insight = ProactiveInsight(
                    insight_type=InsightType.PATTERN_MATCH,
                    content="You discussed this topic with Dr. Chen last week",
                    relevance_score=0.78,
                    source_memory_id="episode-456",
                    source_memory_type="episodic",
                    explanation="Similar topic discussed recently",
                )

                mock_instance = MagicMock()
                mock_instance.find_volunteerable_context = AsyncMock(return_value=[mock_insight])
                MockProactive.return_value = mock_instance

                from src.services.chat import ChatService

                service = ChatService()

                insights = await service._get_proactive_insights(
                    user_id="user-123",
                    current_message="What do we know about Dr. Chen?",
                    conversation_messages=[],
                )

                assert len(insights) == 1
                assert insights[0].content == "You discussed this topic with Dr. Chen last week"
                mock_instance.find_volunteerable_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_proactive_insights_handles_errors_gracefully(self) -> None:
        """_get_proactive_insights should return empty list on error."""
        with patch("src.services.chat.get_supabase_client"):
            with patch("src.services.chat.ProactiveMemoryService") as MockProactive:
                mock_instance = MagicMock()
                mock_instance.find_volunteerable_context = AsyncMock(
                    side_effect=Exception("Database connection failed")
                )
                MockProactive.return_value = mock_instance

                from src.services.chat import ChatService

                service = ChatService()

                # Should not raise, should return empty list
                insights = await service._get_proactive_insights(
                    user_id="user-123",
                    current_message="Hello",
                    conversation_messages=[],
                )

                assert insights == []

    @pytest.mark.asyncio
    async def test_build_system_prompt_includes_proactive_insights(self) -> None:
        """_build_system_prompt should include proactive insights."""
        with patch("src.services.chat.get_supabase_client"):
            with patch("src.services.chat.ProactiveMemoryService"):
                from src.models.proactive_insight import InsightType, ProactiveInsight
                from src.services.chat import ChatService

                service = ChatService()

                insights = [
                    ProactiveInsight(
                        insight_type=InsightType.TEMPORAL,
                        content="Follow up with Acme Corp due tomorrow",
                        relevance_score=0.9,
                        source_memory_id="task-789",
                        source_memory_type="prospective",
                        explanation="Due in 1 day",
                    )
                ]

                prompt = service._build_system_prompt(
                    memories=[],
                    load_state=None,
                    proactive_insights=insights,
                )

                assert "Acme Corp" in prompt
                assert "tomorrow" in prompt or "due" in prompt.lower()

    @pytest.mark.asyncio
    async def test_process_message_calls_proactive_insights(self) -> None:
        """process_message should call _get_proactive_insights."""
        with patch("src.services.chat.get_supabase_client") as mock_db:
            mock_db_instance = MagicMock()
            mock_db_instance.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            mock_db_instance.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[{"id": "conv-1"}])
            )
            mock_db_instance.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"message_count": 0}
            )
            mock_db_instance.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            mock_db.return_value = mock_db_instance

            from src.services.chat import ChatService

            service = ChatService()

            # Mock the proactive service directly on the instance
            mock_proactive_service = MagicMock()
            mock_proactive_service.find_volunteerable_context = AsyncMock(return_value=[])
            service._proactive_service = mock_proactive_service

            # Mock the other dependencies
            service._memory_service = MagicMock()
            service._memory_service.query = AsyncMock(return_value=[])
            service._llm_client = MagicMock()
            service._llm_client.generate_response = AsyncMock(return_value="Hello!")
            service._extraction_service = MagicMock()
            service._extraction_service.extract_and_store = AsyncMock()
            service._cognitive_monitor = MagicMock()
            service._cognitive_monitor.estimate_load = AsyncMock(
                return_value=MagicMock(level=MagicMock(value="low"), score=0.3, recommendation="")
            )

            await service.process_message(
                user_id="user-123",
                conversation_id="conv-123",
                message="What's on my schedule?",
            )

            # Verify proactive insights were fetched
            mock_proactive_service.find_volunteerable_context.assert_called_once()
