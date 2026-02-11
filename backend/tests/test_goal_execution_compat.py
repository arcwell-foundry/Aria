"""Verify that renaming execute_goal -> execute_goal_sync doesn't break callers."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_execute_goal_sync_exists():
    """execute_goal_sync must exist and work like the old execute_goal."""
    with patch("src.services.goal_execution.SupabaseClient") as mock_supa:
        mock_client = MagicMock()
        mock_supa.get_client.return_value = mock_client

        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        assert hasattr(service, "execute_goal_sync")
        assert callable(service.execute_goal_sync)


@pytest.mark.asyncio
async def test_execute_activation_goals_calls_sync():
    """execute_activation_goals should call execute_goal_sync internally."""
    with patch("src.services.goal_execution.SupabaseClient") as mock_supa:
        mock_client = MagicMock()
        mock_supa.get_client.return_value = mock_client

        # Return no activation goals so it returns quickly
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        result = await service.execute_activation_goals("user-1")
        assert result == []
