"""Tests for goal service."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    mock_client = MagicMock()
    return mock_client


@pytest.mark.asyncio
async def test_create_goal_stores_in_database(mock_db: MagicMock) -> None:
    """Test create_goal stores goal in database."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "goal-123",
                    "user_id": "user-456",
                    "title": "Research Acme Corp",
                    "description": "Comprehensive research on Acme Corp",
                    "goal_type": "research",
                    "status": "draft",
                    "progress": 0,
                    "config": {},
                    "strategy": None,
                    "started_at": None,
                    "completed_at": None,
                    "created_at": "2026-02-02T10:00:00Z",
                    "updated_at": "2026-02-02T10:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.goal import GoalCreate, GoalType
        from src.services.goal_service import GoalService

        service = GoalService()
        data = GoalCreate(
            title="Research Acme Corp",
            description="Comprehensive research on Acme Corp",
            goal_type=GoalType.RESEARCH,
        )

        result = await service.create_goal("user-456", data)

        assert result["id"] == "goal-123"
        assert result["title"] == "Research Acme Corp"
        assert result["goal_type"] == "research"
        assert result["status"] == "draft"
        assert result["progress"] == 0

        # Verify insert was called
        mock_db.table.assert_called_with("goals")


@pytest.mark.asyncio
async def test_get_goal_returns_goal_with_agents(mock_db: MagicMock) -> None:
    """Test get_goal returns goal with associated agents."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        expected_goal = {
            "id": "goal-123",
            "user_id": "user-456",
            "title": "Research Acme Corp",
            "goal_agents": [
                {"id": "agent-1", "agent_type": "analyst", "status": "pending"},
                {"id": "agent-2", "agent_type": "scribe", "status": "complete"},
            ],
        }
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=expected_goal
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.get_goal("user-456", "goal-123")

        assert result["id"] == "goal-123"
        assert len(result["goal_agents"]) == 2


@pytest.mark.asyncio
async def test_get_goal_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test get_goal returns None when goal not found."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock to return None
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.get_goal("user-456", "goal-999")

        assert result is None


@pytest.mark.asyncio
async def test_list_goals_returns_all_goals_by_default(mock_db: MagicMock) -> None:
    """Test list_goals returns all goals without filters."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        expected_goals = [
            {"id": "goal-1", "title": "Research Acme", "status": "draft"},
            {"id": "goal-2", "title": "Outreach to Beta", "status": "active"},
        ]
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=expected_goals
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.list_goals("user-456")

        assert len(result) == 2
        assert result == expected_goals


@pytest.mark.asyncio
async def test_list_goals_filters_by_status(mock_db: MagicMock) -> None:
    """Test list_goals filters by goal status."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "goal-1", "status": "active"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.goal import GoalStatus
        from src.services.goal_service import GoalService

        service = GoalService()
        await service.list_goals("user-456", status=GoalStatus.ACTIVE)

        # Verify eq was called with status
        mock_db.table.return_value.select.return_value.eq.assert_called()


@pytest.mark.asyncio
async def test_update_goal_modifies_specified_fields(mock_db: MagicMock) -> None:
    """Test update_goal updates only specified fields."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "goal-123",
                    "title": "Updated Title",
                    "description": "Original description",
                    "status": "active",
                    "updated_at": "2026-02-02T11:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.goal import GoalUpdate
        from src.services.goal_service import GoalService

        service = GoalService()
        data = GoalUpdate(title="Updated Title")
        result = await service.update_goal("user-456", "goal-123", data)

        assert result["title"] == "Updated Title"
        assert result["description"] == "Original description"


@pytest.mark.asyncio
async def test_update_goal_converts_enum_to_value(mock_db: MagicMock) -> None:
    """Test update_goal converts enum values to strings."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "goal-123", "status": "paused"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.goal import GoalStatus, GoalUpdate
        from src.services.goal_service import GoalService

        service = GoalService()
        data = GoalUpdate(status=GoalStatus.PAUSED)
        result = await service.update_goal("user-456", "goal-123", data)

        assert result["status"] == "paused"


@pytest.mark.asyncio
async def test_delete_goal_removes_from_database(mock_db: MagicMock) -> None:
    """Test delete_goal removes goal from database."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.delete_goal("user-456", "goal-123")

        assert result is True

        # Verify delete was called
        mock_db.table.assert_called_with("goals")


@pytest.mark.asyncio
async def test_start_goal_transitions_to_active(mock_db: MagicMock) -> None:
    """Test start_goal sets status to active and sets started_at."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "goal-123",
                    "status": "active",
                    "started_at": "2026-02-02T10:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.start_goal("user-456", "goal-123")

        assert result["status"] == "active"
        assert result["started_at"] is not None


@pytest.mark.asyncio
async def test_pause_goal_transitions_to_paused(mock_db: MagicMock) -> None:
    """Test pause_goal sets status to paused."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "goal-123",
                    "status": "paused",
                    "updated_at": "2026-02-02T10:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.pause_goal("user-456", "goal-123")

        assert result["status"] == "paused"


@pytest.mark.asyncio
async def test_complete_goal_transitions_to_complete(mock_db: MagicMock) -> None:
    """Test complete_goal sets status to complete, progress to 100, and sets completed_at."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        goal_data = {
            "id": "goal-123",
            "status": "active",
            "progress": 75,
            "completed_at": None,
            "goal_agents": [],
        }
        # Mock select chain for get_goal
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=goal_data
        )
        # Mock update chain
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "goal-123",
                    "status": "complete",
                    "progress": 100,
                    "completed_at": "2026-02-02T10:00:00Z",
                }
            ]
        )
        # Mock order chain for milestones query in generate_retrospective
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.complete_goal("user-456", "goal-123")

        assert result["status"] == "complete"
        assert "retrospective" in result


@pytest.mark.asyncio
async def test_update_progress_clamps_to_0_100(mock_db: MagicMock) -> None:
    """Test update_progress clamps values between 0 and 100."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Test value above 100
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "goal-123", "progress": 100}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.update_progress("user-456", "goal-123", 150)

        assert result["progress"] == 100

        # Test value below 0
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "goal-123", "progress": 0}]
        )
        result = await service.update_progress("user-456", "goal-123", -10)

        assert result["progress"] == 0


@pytest.mark.asyncio
async def test_get_goal_progress_includes_recent_executions(mock_db: MagicMock) -> None:
    """Test get_goal_progress includes recent agent executions."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        goal_data = {
            "id": "goal-123",
            "title": "Research Acme",
            "goal_agents": [
                {"id": "agent-1"},
            ],
        }
        executions_data = [
            {"id": "exec-1", "status": "complete"},
            {"id": "exec-2", "status": "running"},
        ]

        # Setup DB mock for executions query
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=executions_data
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        # Mock get_goal to return the test data (async wrapper)
        async def mock_get_goal(user_id: str, goal_id: str) -> dict[str, Any]:
            return goal_data

        service.get_goal = mock_get_goal  # type: ignore[method-assign]

        result = await service.get_goal_progress("user-456", "goal-123")

        assert result["id"] == "goal-123"
        assert "recent_executions" in result
        assert len(result["recent_executions"]) == 2


@pytest.mark.asyncio
async def test_get_goal_progress_returns_none_for_not_found(mock_db: MagicMock) -> None:
    """Test get_goal_progress returns None when goal not found."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock to return None
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.get_goal_progress("user-456", "goal-999")

        assert result is None


@pytest.mark.asyncio
async def test_update_goal_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test update_goal returns None when goal not found."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock to return empty data
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.goal import GoalUpdate
        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.update_goal("user-456", "goal-999", GoalUpdate(title="New Title"))

        assert result is None


@pytest.mark.asyncio
async def test_start_goal_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test start_goal returns None when goal not found."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock to return empty data
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.start_goal("user-456", "goal-999")

        assert result is None


@pytest.mark.asyncio
async def test_pause_goal_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test pause_goal returns None when goal not found."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock to return empty data
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.pause_goal("user-456", "goal-999")

        assert result is None


@pytest.mark.asyncio
async def test_complete_goal_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test complete_goal returns None when goal not found."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Mock get_goal's select chain to return None (goal not found)
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.complete_goal("user-456", "goal-999")

        assert result is None


@pytest.mark.asyncio
async def test_update_progress_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test update_progress returns None when goal not found."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock to return empty data
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.update_progress("user-456", "goal-999", 50)

        assert result is None
