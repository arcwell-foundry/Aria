"""Tests for goal plan generation error handling."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def goal_exec_service():
    """Create a GoalExecutionService with mocked dependencies."""
    with patch("src.services.goal_execution.SupabaseClient") as mock_sb:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        from src.services.goal_execution import GoalExecutionService
        svc = GoalExecutionService()
        svc._db = mock_client
        svc._llm = AsyncMock()
        svc._activity = AsyncMock()
        return svc, mock_client


@pytest.mark.asyncio
async def test_plan_goal_llm_failure_marks_plan_failed(goal_exec_service):
    """When the LLM call fails, plan_goal should mark goal as plan_failed and re-raise."""
    svc, mock_client = goal_exec_service

    # Mock goal lookup to return a draft goal
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.maybe_single.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = MagicMock(
        data={"id": "goal-1", "title": "Find leads", "config": {}, "user_id": "user-1", "status": "draft"}
    )
    mock_table.update.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.upsert.return_value = mock_table

    # Mock LLM to raise exception
    svc._llm.generate_response = AsyncMock(side_effect=Exception("API rate limit exceeded"))

    # Mock internal methods that run between goal fetch and LLM call
    svc._gather_user_resources = AsyncMock(return_value={
        "integrations": [],
        "trust_profiles": [],
        "company_facts": [],
        "company_id": None,
    })
    svc._gather_execution_context = AsyncMock(return_value={
        "company_name": "Test Co",
        "company_domain": "test.com",
        "classification": {},
        "facts": [],
        "gaps": [],
        "readiness": {},
        "profile": {},
    })
    svc._get_tool_discovery = MagicMock(return_value=None)
    svc._get_causal_engine = MagicMock(return_value=None)

    # plan_goal should re-raise after marking plan_failed
    with pytest.raises(Exception, match="API rate limit exceeded"):
        await svc.plan_goal("goal-1", "user-1")

    # Verify that a status update to plan_failed was attempted
    update_calls = mock_table.update.call_args_list
    status_updates = [
        call for call in update_calls
        if isinstance(call[0][0], dict) and call[0][0].get("status") == "plan_failed"
    ]
    assert len(status_updates) >= 1, f"Expected plan_failed status update, got updates: {update_calls}"
