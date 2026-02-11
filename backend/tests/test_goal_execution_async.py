"""Tests for async goal execution methods on GoalExecutionService."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_service():
    """Create a GoalExecutionService with mocked dependencies."""
    with patch("src.services.goal_execution.SupabaseClient") as mock_supa:
        mock_client = MagicMock()
        mock_supa.get_client.return_value = mock_client
        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        service._db = mock_client
        return service, mock_client


@pytest.mark.asyncio
async def test_propose_goals_returns_proposals():
    service, mock_db = _make_service()
    service._gather_execution_context = AsyncMock(
        return_value={
            "company_name": "Acme",
            "facts": ["Fact 1", "Fact 2"],
            "gaps": [],
            "readiness": {},
            "profile": {},
        }
    )
    service._llm = MagicMock()
    service._llm.generate_response = AsyncMock(
        return_value="""{
            "proposals": [
                {
                    "title": "Build Pipeline",
                    "description": "Find new leads",
                    "goal_type": "lead_gen",
                    "rationale": "Pipeline is empty",
                    "priority": "high",
                    "estimated_days": 7,
                    "agent_assignments": ["hunter"]
                }
            ],
            "context_summary": "Based on gaps"
        }"""
    )

    result = await service.propose_goals("user-1")
    assert len(result["proposals"]) == 1
    assert result["proposals"][0]["title"] == "Build Pipeline"
    assert result["context_summary"] == "Based on gaps"


@pytest.mark.asyncio
async def test_plan_goal_stores_plan():
    service, mock_db = _make_service()

    # Mock goal fetch
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "id": "goal-1",
        "title": "Test Goal",
        "description": "Desc",
        "config": {},
    }

    service._gather_execution_context = AsyncMock(
        return_value={
            "company_name": "Acme",
            "facts": [],
            "gaps": [],
            "readiness": {},
            "profile": {},
        }
    )
    service._llm = MagicMock()
    service._llm.generate_response = AsyncMock(
        return_value="""{
            "tasks": [
                {
                    "title": "Research Market",
                    "description": "Analyze market",
                    "agent_type": "analyst",
                    "depends_on": []
                }
            ],
            "execution_mode": "parallel",
            "reasoning": "Need market data first"
        }"""
    )

    # Mock plan storage
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "plan-1"}
    ]

    result = await service.plan_goal("goal-1", "user-1")
    assert result["goal_id"] == "goal-1"
    assert len(result["tasks"]) >= 1


@pytest.mark.asyncio
async def test_execute_goal_async_returns_immediately():
    service, mock_db = _make_service()

    # Mock goal status update
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )

    # Mock _run_goal_background to avoid actual execution
    service._run_goal_background = AsyncMock()

    result = await service.execute_goal_async("goal-1", "user-1")
    assert result["goal_id"] == "goal-1"
    assert result["status"] == "executing"


@pytest.mark.asyncio
async def test_cancel_goal():
    service, mock_db = _make_service()

    # Create a fake background task
    async def fake_bg():
        await asyncio.sleep(100)

    task = asyncio.create_task(fake_bg())
    service._active_tasks["goal-1"] = task

    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )

    result = await service.cancel_goal("goal-1", "user-1")
    assert result["status"] == "cancelled"
    # Allow cancellation to propagate
    await asyncio.sleep(0)
    assert task.cancelled()


@pytest.mark.asyncio
async def test_check_progress_returns_snapshot():
    service, mock_db = _make_service()

    # Mock goal fetch
    goal_mock = MagicMock()
    goal_mock.data = {
        "id": "goal-1",
        "title": "Test",
        "status": "active",
        "progress": 50,
    }
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = goal_mock

    # Mock plan fetch
    plan_mock = MagicMock()
    plan_mock.data = None
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = plan_mock

    # Mock executions fetch
    exec_mock = MagicMock()
    exec_mock.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = exec_mock

    result = await service.check_progress("goal-1", "user-1")
    assert result["goal_id"] == "goal-1"
    assert "progress" in result


@pytest.mark.asyncio
async def test_report_progress_returns_narrative():
    service, mock_db = _make_service()

    service.check_progress = AsyncMock(
        return_value={
            "goal_id": "goal-1",
            "title": "Test",
            "status": "active",
            "progress": 50,
            "plan": None,
            "recent_executions": [],
        }
    )
    service._llm = MagicMock()
    service._llm.generate_response = AsyncMock(
        return_value='{"summary": "Making good progress", "details": "50% complete"}'
    )

    result = await service.report_progress("goal-1", "user-1")
    assert "report" in result
    assert result["goal_id"] == "goal-1"


@pytest.mark.asyncio
async def test_complete_goal_with_retro():
    service, mock_db = _make_service()

    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )

    # Patch GoalService where it's imported (lazy import inside the method)
    with patch("src.services.goal_service.GoalService") as mock_goal_svc_cls:
        mock_goal_svc = MagicMock()
        mock_goal_svc_cls.return_value = mock_goal_svc
        mock_goal_svc.generate_retrospective = AsyncMock(
            return_value={"summary": "Good work"}
        )

        # Patch EventBus singleton
        with patch("src.core.event_bus.EventBus.get_instance") as mock_get_instance:
            mock_bus = MagicMock()
            mock_get_instance.return_value = mock_bus
            mock_bus.publish = AsyncMock()

            result = await service.complete_goal_with_retro("goal-1", "user-1")
            assert result["status"] == "complete"
            mock_bus.publish.assert_called_once()
