"""Tests for goal lifecycle API routes (US-936).

Covers: GET /goals/dashboard, POST /goals/create-with-aria,
GET /goals/templates, GET /goals/{id}/detail,
POST /goals/{id}/milestone, POST /goals/{id}/retrospective.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.api.routes.goals import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Mock authenticated user."""
    user = MagicMock()
    user.id = "user-123"
    return user


@pytest.fixture
def mock_goal_service() -> MagicMock:
    """Mock GoalService via the _get_service helper."""
    with patch("src.api.routes.goals._get_service") as mock_factory:
        service_instance = MagicMock()
        mock_factory.return_value = service_instance
        yield service_instance


@pytest.fixture
def client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked auth."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /goals/dashboard
# ---------------------------------------------------------------------------


class TestGetDashboard:
    """Tests for GET /goals/dashboard."""

    def test_returns_list_of_goals(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """GET /goals/dashboard returns a list of goals with milestone counts."""
        mock_goal_service.get_dashboard = AsyncMock(
            return_value=[
                {
                    "id": "g1",
                    "title": "Goal A",
                    "milestone_total": 3,
                    "milestone_complete": 1,
                },
                {
                    "id": "g2",
                    "title": "Goal B",
                    "milestone_total": 0,
                    "milestone_complete": 0,
                },
            ]
        )

        response = client.get(
            "/api/v1/goals/dashboard",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["milestone_total"] == 3
        assert data[1]["milestone_complete"] == 0


# ---------------------------------------------------------------------------
# POST /goals/create-with-aria
# ---------------------------------------------------------------------------


class TestCreateWithARIA:
    """Tests for POST /goals/create-with-aria."""

    def test_returns_suggestion_dict(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """POST /goals/create-with-aria returns ARIA suggestion dict."""
        expected: dict[str, Any] = {
            "refined_title": "Refined Goal",
            "refined_description": "SMART description",
            "smart_score": 85,
            "sub_tasks": [{"title": "Step 1", "description": "Do thing"}],
            "agent_assignments": ["analyst", "hunter"],
            "suggested_timeline_days": 7,
            "reasoning": "Well-scoped goal.",
        }
        mock_goal_service.create_with_aria = AsyncMock(return_value=expected)

        response = client.post(
            "/api/v1/goals/create-with-aria",
            json={"title": "My goal", "description": "Details"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["refined_title"] == "Refined Goal"
        assert data["smart_score"] == 85
        assert data["agent_assignments"] == ["analyst", "hunter"]


# ---------------------------------------------------------------------------
# GET /goals/templates
# ---------------------------------------------------------------------------


class TestGetTemplates:
    """Tests for GET /goals/templates."""

    def test_returns_list(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """GET /goals/templates returns a list of templates."""
        mock_goal_service.get_templates = AsyncMock(
            return_value=[
                {
                    "title": "Pipeline Generation",
                    "description": "Generate new pipeline",
                    "applicable_roles": ["sales", "marketing"],
                    "goal_type": "lead_gen",
                },
                {
                    "title": "Competitive Intel",
                    "description": "Research competitors",
                    "applicable_roles": ["sales"],
                    "goal_type": "competitive_intel",
                },
            ]
        )

        response = client.get(
            "/api/v1/goals/templates",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_filters_by_role(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """GET /goals/templates?role=sales returns filtered templates."""
        mock_goal_service.get_templates = AsyncMock(
            return_value=[
                {
                    "title": "Competitive Intel",
                    "description": "Research competitors",
                    "applicable_roles": ["sales"],
                    "goal_type": "competitive_intel",
                },
            ]
        )

        response = client.get(
            "/api/v1/goals/templates?role=sales",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        # Verify service was called with role arg
        mock_goal_service.get_templates.assert_called_once_with("sales")


# ---------------------------------------------------------------------------
# GET /goals/{goal_id}/detail
# ---------------------------------------------------------------------------


class TestGetGoalDetail:
    """Tests for GET /goals/{goal_id}/detail."""

    def test_returns_goal_with_milestones_and_retrospective(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """GET /goals/{id}/detail returns goal with milestones and retrospective."""
        mock_goal_service.get_goal_detail = AsyncMock(
            return_value={
                "id": "g1",
                "title": "Detailed Goal",
                "milestones": [
                    {"id": "m1", "title": "MS 1", "sort_order": 1},
                    {"id": "m2", "title": "MS 2", "sort_order": 2},
                ],
                "retrospective": {
                    "id": "retro-1",
                    "summary": "Good progress",
                },
            }
        )

        response = client.get(
            "/api/v1/goals/g1/detail",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Detailed Goal"
        assert len(data["milestones"]) == 2
        assert data["retrospective"]["summary"] == "Good progress"

    def test_returns_404_if_not_found(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """GET /goals/{id}/detail returns 404 if goal not found."""
        mock_goal_service.get_goal_detail = AsyncMock(return_value=None)

        response = client.get(
            "/api/v1/goals/g-missing/detail",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Goal not found"


# ---------------------------------------------------------------------------
# POST /goals/{goal_id}/milestone
# ---------------------------------------------------------------------------


class TestAddMilestone:
    """Tests for POST /goals/{goal_id}/milestone."""

    def test_creates_milestone(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """POST /goals/{id}/milestone creates a new milestone."""
        mock_goal_service.add_milestone = AsyncMock(
            return_value={
                "id": "ms-new",
                "goal_id": "g1",
                "title": "New Milestone",
                "description": "Milestone desc",
                "status": "pending",
                "sort_order": 1,
            }
        )

        response = client.post(
            "/api/v1/goals/g1/milestone",
            json={
                "title": "New Milestone",
                "description": "Milestone desc",
            },
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ms-new"
        assert data["title"] == "New Milestone"
        assert data["sort_order"] == 1

    def test_returns_404_if_goal_not_found(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """POST /goals/{id}/milestone returns 404 if goal not found."""
        mock_goal_service.add_milestone = AsyncMock(return_value=None)

        response = client.post(
            "/api/v1/goals/g-missing/milestone",
            json={"title": "Won't work"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Goal not found"


# ---------------------------------------------------------------------------
# POST /goals/{goal_id}/retrospective
# ---------------------------------------------------------------------------


class TestGenerateRetrospective:
    """Tests for POST /goals/{goal_id}/retrospective."""

    def test_returns_retrospective(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """POST /goals/{id}/retrospective returns a retrospective."""
        mock_goal_service.generate_retrospective = AsyncMock(
            return_value={
                "id": "retro-1",
                "goal_id": "g1",
                "summary": "Good progress overall",
                "what_worked": ["Communication"],
                "what_didnt": ["Timing"],
                "time_analysis": {"total_days": 10},
                "agent_effectiveness": {},
                "learnings": ["Start earlier"],
            }
        )

        response = client.post(
            "/api/v1/goals/g1/retrospective",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "Good progress overall"
        assert data["what_worked"] == ["Communication"]
        assert data["learnings"] == ["Start earlier"]

    def test_returns_404_if_goal_not_found(
        self,
        client: TestClient,
        mock_goal_service: MagicMock,
    ) -> None:
        """POST /goals/{id}/retrospective returns 404 if goal not found."""
        mock_goal_service.generate_retrospective = AsyncMock(return_value=None)

        response = client.post(
            "/api/v1/goals/g-missing/retrospective",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Goal not found"
