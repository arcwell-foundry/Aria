"""Tests for GoalExecutionService WebSocket integration.

Verifies that real-time WebSocket events are sent at the right points
during goal execution: thinking on start, progress after agents complete,
and aria.message when the goal finishes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock Supabase client with chained query support."""
    client = MagicMock()

    # Default: chained calls return an execute() with empty data
    def _chain(*_args, **_kwargs):
        return client

    client.table.return_value = client
    client.select.return_value = client
    client.insert.return_value = client
    client.update.return_value = client
    client.eq.return_value = client
    client.order.return_value = client
    client.limit.return_value = client
    client.maybe_single.return_value = client
    client.execute.return_value = MagicMock(data=[])
    return client


@pytest.fixture
def _patch_deps(mock_db: MagicMock):
    """Patch external dependencies so GoalExecutionService can be instantiated."""
    with (
        patch("src.services.goal_execution.SupabaseClient") as mock_supa,
        patch("src.services.goal_execution.LLMClient") as mock_llm_cls,
        patch("src.services.goal_execution.ActivityService"),
    ):
        mock_supa.get_client.return_value = mock_db
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"summary": "Test analysis result"}'
        )
        mock_llm_cls.return_value = mock_llm
        yield


def _build_goal_data(goal_id: str = "goal-1", agent_type: str = "scout") -> dict:
    """Build a minimal goal row dict for testing."""
    return {
        "id": goal_id,
        "title": "Analyze competitors",
        "description": "Competitive landscape",
        "status": "draft",
        "config": {"source": "onboarding_activation", "agent_type": agent_type},
        "goal_agents": [],
    }


def _configure_db_for_single_agent(mock_db: MagicMock, goal_id: str = "goal-1") -> None:
    """Configure mock_db to return a goal with a single agent on the first query."""
    goal_data = _build_goal_data(goal_id=goal_id)

    call_count = 0

    def _smart_execute():
        nonlocal call_count
        call_count += 1
        # First execute call is the goal fetch (select with maybe_single)
        if call_count == 1:
            return MagicMock(data=goal_data)
        # All other calls return default empty data
        return MagicMock(data=[])

    mock_db.execute = _smart_execute


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_deps")
async def test_execute_goal_sends_thinking_on_start(mock_db: MagicMock) -> None:
    """execute_goal() sends send_thinking(user_id) after setting goal to active."""
    _configure_db_for_single_agent(mock_db)

    with patch("src.services.goal_execution.ws_manager") as mock_ws:
        mock_ws.send_thinking = AsyncMock()
        mock_ws.send_progress_update = AsyncMock()
        mock_ws.send_aria_message = AsyncMock()

        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        # Patch _execute_agent to avoid deep LLM/skill calls
        service._execute_agent = AsyncMock(
            return_value={"agent_type": "scout", "success": True, "content": {}}
        )

        await service.execute_goal_sync("goal-1", "user-1")

        mock_ws.send_thinking.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_deps")
async def test_execute_goal_sends_progress_after_agent(mock_db: MagicMock) -> None:
    """execute_goal() sends progress update after each agent completes."""
    _configure_db_for_single_agent(mock_db)

    with patch("src.services.goal_execution.ws_manager") as mock_ws:
        mock_ws.send_thinking = AsyncMock()
        mock_ws.send_progress_update = AsyncMock()
        mock_ws.send_aria_message = AsyncMock()

        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        service._execute_agent = AsyncMock(
            return_value={"agent_type": "scout", "success": True, "content": {}}
        )

        await service.execute_goal_sync("goal-1", "user-1")

        mock_ws.send_progress_update.assert_awaited_once()
        call_kwargs = mock_ws.send_progress_update.call_args.kwargs
        assert call_kwargs["user_id"] == "user-1"
        assert call_kwargs["goal_id"] == "goal-1"
        assert call_kwargs["status"] == "active"
        assert "agent_name" in call_kwargs


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_deps")
async def test_execute_goal_sends_aria_message_on_complete(mock_db: MagicMock) -> None:
    """execute_goal() sends aria message when goal finishes."""
    _configure_db_for_single_agent(mock_db)

    with patch("src.services.goal_execution.ws_manager") as mock_ws:
        mock_ws.send_thinking = AsyncMock()
        mock_ws.send_progress_update = AsyncMock()
        mock_ws.send_aria_message = AsyncMock()

        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        service._execute_agent = AsyncMock(
            return_value={"agent_type": "scout", "success": True, "content": {}}
        )

        await service.execute_goal_sync("goal-1", "user-1")

        assert mock_ws.send_aria_message.await_count >= 1
        call_kwargs = mock_ws.send_aria_message.call_args.kwargs
        assert call_kwargs["user_id"] == "user-1"
        assert "message" in call_kwargs
        assert "ui_commands" in call_kwargs
        assert "suggestions" in call_kwargs


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_deps")
async def test_execute_goal_sends_progress_per_agent_in_multi(mock_db: MagicMock) -> None:
    """execute_goal() sends a progress update for each agent in a multi-agent goal."""
    # Multi-agent goal: no agent_type in config, agents in goal_agents list
    multi_goal = {
        "id": "goal-m",
        "title": "Full research",
        "description": "Multi-agent research",
        "status": "draft",
        "config": {"source": "onboarding_activation"},
        "goal_agents": [
            {"id": "ga-1", "agent_type": "scout"},
            {"id": "ga-2", "agent_type": "analyst"},
        ],
    }

    call_count = 0

    def _smart_execute():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(data=multi_goal)
        return MagicMock(data=[])

    mock_db.execute = _smart_execute

    with patch("src.services.goal_execution.ws_manager") as mock_ws:
        mock_ws.send_thinking = AsyncMock()
        mock_ws.send_progress_update = AsyncMock()
        mock_ws.send_aria_message = AsyncMock()

        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        service._execute_agent = AsyncMock(
            return_value={"agent_type": "scout", "success": True, "content": {}}
        )

        await service.execute_goal_sync("goal-m", "user-1")

        assert mock_ws.send_progress_update.await_count == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_deps")
async def test_ws_failure_does_not_break_goal_execution(mock_db: MagicMock) -> None:
    """WebSocket errors must not prevent goal execution from completing."""
    _configure_db_for_single_agent(mock_db)

    with patch("src.services.goal_execution.ws_manager") as mock_ws:
        mock_ws.send_thinking = AsyncMock(side_effect=RuntimeError("ws down"))
        mock_ws.send_progress_update = AsyncMock(side_effect=RuntimeError("ws down"))
        mock_ws.send_aria_message = AsyncMock(side_effect=RuntimeError("ws down"))

        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        service._execute_agent = AsyncMock(
            return_value={"agent_type": "scout", "success": True, "content": {}}
        )

        # Should NOT raise even though ws_manager calls fail
        result = await service.execute_goal_sync("goal-1", "user-1")

        assert result["status"] == "complete"
        assert result["goal_id"] == "goal-1"
