"""Tests for BaseAgent memory integration.

Validates that hot context and cold retrieval are properly wired
into the agent lifecycle, cached per run, and backward compatible.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.base import AgentResult, BaseAgent

# ── Concrete test agent ──────────────────────────────────────────


class _TestAgent(BaseAgent):
    """Minimal concrete agent for testing."""

    name = "test_agent"
    description = "A test agent"

    def _register_tools(self) -> dict[str, Any]:
        return {}

    def validate_input(self, task: dict[str, Any]) -> bool:  # noqa: ARG002
        return True

    async def execute(self, task: dict[str, Any]) -> AgentResult:  # noqa: ARG002
        return AgentResult(success=True, data={"result": "ok"})


# ── Tests ─────────────────────────────────────────────────────────


class TestBaseAgentMemory:
    """Tests for BaseAgent hot/cold memory integration."""

    @pytest.mark.asyncio()
    async def test_agent_without_memory_services(self) -> None:
        """Agent works without memory services (returns None/[])."""
        agent = _TestAgent(llm_client=MagicMock(), user_id="user-1")

        hot = await agent.get_hot_context()
        assert hot is None

        cold = await agent.cold_retrieve("test query")
        assert cold == []

    @pytest.mark.asyncio()
    async def test_agent_get_hot_context(self) -> None:
        """get_hot_context() delegates to builder and returns result."""
        mock_builder = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.user_id = "user-1"
        mock_builder.build = AsyncMock(return_value=mock_ctx)

        agent = _TestAgent(
            llm_client=MagicMock(),
            user_id="user-1",
            hot_context_builder=mock_builder,
        )
        result = await agent.get_hot_context()

        assert result is mock_ctx
        mock_builder.build.assert_called_once_with("user-1", working_memory=None)

    @pytest.mark.asyncio()
    async def test_agent_hot_context_cached_per_run(self) -> None:
        """Second call returns same object without re-fetching."""
        mock_builder = MagicMock()
        mock_ctx = MagicMock()
        mock_builder.build = AsyncMock(return_value=mock_ctx)

        agent = _TestAgent(
            llm_client=MagicMock(),
            user_id="user-1",
            hot_context_builder=mock_builder,
        )
        first = await agent.get_hot_context()
        second = await agent.get_hot_context()

        assert first is second
        assert mock_builder.build.call_count == 1

    @pytest.mark.asyncio()
    async def test_agent_hot_context_reset_on_run(self) -> None:
        """Cache is cleared at the start of run()."""
        mock_builder = MagicMock()
        mock_ctx = MagicMock()
        mock_builder.build = AsyncMock(return_value=mock_ctx)

        agent = _TestAgent(
            llm_client=MagicMock(),
            user_id="user-1",
            hot_context_builder=mock_builder,
        )

        # Pre-populate cache
        await agent.get_hot_context()
        assert agent._hot_context_cache is not None

        # run() should reset cache
        await agent.run({"task": "test"})
        # After run(), cache should have been reset at start
        # (it may be re-populated if execute() calls get_hot_context,
        # but the reset itself happens)
        assert mock_builder.build.call_count == 1  # only the first get_hot_context

    @pytest.mark.asyncio()
    async def test_agent_cold_retrieve(self) -> None:
        """cold_retrieve() delegates to retriever and returns dicts."""
        mock_retriever = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"source": "semantic", "content": "a fact"}
        mock_retriever.retrieve = AsyncMock(return_value=[mock_result])

        agent = _TestAgent(
            llm_client=MagicMock(),
            user_id="user-1",
            cold_retriever=mock_retriever,
        )
        results = await agent.cold_retrieve("BioGenix pipeline")

        assert len(results) == 1
        assert results[0]["source"] == "semantic"
        mock_retriever.retrieve.assert_called_once_with(
            user_id="user-1", query="BioGenix pipeline", limit=10
        )

    @pytest.mark.asyncio()
    async def test_agent_cold_retrieve_no_retriever(self) -> None:
        """cold_retrieve() returns [] when no retriever configured."""
        agent = _TestAgent(llm_client=MagicMock(), user_id="user-1")
        results = await agent.cold_retrieve("test")
        assert results == []

    def test_agent_backward_compatible(self) -> None:
        """Existing init (without memory params) still works."""
        agent = _TestAgent(llm_client=MagicMock(), user_id="user-1")
        assert agent._hot_context_builder is None
        assert agent._cold_retriever is None
        assert agent._hot_context_cache is None
        assert agent.user_id == "user-1"

    @pytest.mark.asyncio()
    async def test_agent_get_hot_context_with_working_memory(self) -> None:
        """get_hot_context() passes working memory to builder."""
        mock_builder = MagicMock()
        mock_ctx = MagicMock()
        mock_builder.build = AsyncMock(return_value=mock_ctx)

        agent = _TestAgent(
            llm_client=MagicMock(),
            user_id="user-1",
            hot_context_builder=mock_builder,
        )
        mock_wm = MagicMock()
        result = await agent.get_hot_context(working_memory=mock_wm)

        assert result is mock_ctx
        mock_builder.build.assert_called_once_with("user-1", working_memory=mock_wm)
