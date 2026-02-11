"""Tests for async goal execution API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_propose_goals_endpoint():
    """POST /goals/propose should return proposals."""
    with patch("src.api.routes.goals._get_execution_service") as mock_get:
        mock_svc = MagicMock()
        mock_get.return_value = mock_svc
        mock_svc.propose_goals = AsyncMock(
            return_value={
                "proposals": [
                    {
                        "title": "Build Pipeline",
                        "description": "Find leads",
                        "goal_type": "lead_gen",
                        "rationale": "Empty pipeline",
                        "priority": "high",
                        "estimated_days": 7,
                        "agent_assignments": ["hunter"],
                    }
                ],
                "context_summary": "Based on gaps",
            }
        )

        from src.api.routes.goals import propose_goals

        # Create a mock CurrentUser
        mock_user = MagicMock()
        mock_user.id = "user-1"

        result = await propose_goals(mock_user)
        assert len(result["proposals"]) == 1
        assert result["proposals"][0]["title"] == "Build Pipeline"
        mock_svc.propose_goals.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_plan_goal_endpoint():
    """POST /goals/{id}/plan should return an execution plan."""
    with patch("src.api.routes.goals._get_execution_service") as mock_get:
        mock_svc = MagicMock()
        mock_get.return_value = mock_svc
        mock_svc.plan_goal = AsyncMock(
            return_value={
                "goal_id": "goal-1",
                "tasks": [{"title": "Research", "agent_type": "analyst"}],
                "execution_mode": "parallel",
                "reasoning": "Need data",
            }
        )

        from src.api.routes.goals import plan_goal

        mock_user = MagicMock()
        mock_user.id = "user-1"

        result = await plan_goal("goal-1", mock_user)
        assert result["goal_id"] == "goal-1"
        assert len(result["tasks"]) == 1
        mock_svc.plan_goal.assert_called_once_with("goal-1", "user-1")


@pytest.mark.asyncio
async def test_execute_goal_endpoint():
    """POST /goals/{id}/execute should return executing status."""
    with patch("src.api.routes.goals._get_execution_service") as mock_get:
        mock_svc = MagicMock()
        mock_get.return_value = mock_svc
        mock_svc.execute_goal_async = AsyncMock(
            return_value={"goal_id": "goal-1", "status": "executing"}
        )

        from src.api.routes.goals import execute_goal

        mock_user = MagicMock()
        mock_user.id = "user-1"

        result = await execute_goal("goal-1", mock_user)
        assert result["status"] == "executing"
        mock_svc.execute_goal_async.assert_called_once_with("goal-1", "user-1")


@pytest.mark.asyncio
async def test_cancel_goal_endpoint():
    """POST /goals/{id}/cancel should return cancelled status."""
    with patch("src.api.routes.goals._get_execution_service") as mock_get:
        mock_svc = MagicMock()
        mock_get.return_value = mock_svc
        mock_svc.cancel_goal = AsyncMock(
            return_value={"goal_id": "goal-1", "status": "cancelled"}
        )

        from src.api.routes.goals import cancel_goal_execution

        mock_user = MagicMock()
        mock_user.id = "user-1"

        result = await cancel_goal_execution("goal-1", mock_user)
        assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_goal_report_endpoint():
    """GET /goals/{id}/report should return a progress report."""
    with patch("src.api.routes.goals._get_execution_service") as mock_get:
        mock_svc = MagicMock()
        mock_get.return_value = mock_svc
        mock_svc.report_progress = AsyncMock(
            return_value={
                "goal_id": "goal-1",
                "report": {"summary": "On track", "details": "50% done"},
            }
        )

        from src.api.routes.goals import goal_report

        mock_user = MagicMock()
        mock_user.id = "user-1"

        result = await goal_report("goal-1", mock_user)
        assert result["goal_id"] == "goal-1"
        assert "report" in result


@pytest.mark.asyncio
async def test_goal_events_endpoint_returns_streaming_response():
    """GET /goals/{id}/events should return a StreamingResponse."""
    from src.api.routes.goals import goal_events

    mock_user = MagicMock()
    mock_user.id = "user-1"

    with patch("src.core.event_bus.EventBus.get_instance") as mock_get_instance:
        mock_bus = MagicMock()
        mock_get_instance.return_value = mock_bus
        mock_bus.subscribe = MagicMock(return_value=MagicMock())

        response = await goal_events("goal-1", mock_user)

        from fastapi.responses import StreamingResponse

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
