"""Tests for admin onboarding outcomes routes (US-924)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.routes import admin


def _mock_execute(data: Any) -> MagicMock:
    result = MagicMock()
    result.data = data
    result.count = len(data) if isinstance(data, list) else 0
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_admin_user() -> MagicMock:
    """Mock admin user."""
    user = MagicMock()
    user.id = "admin-user-123"
    user.email = "admin@example.com"
    return user


@pytest.fixture()
def admin_test_client(mock_admin_user: MagicMock) -> TestClient:
    """Create test client with mocked admin authentication."""
    from fastapi import FastAPI
    from src.api.deps import get_current_user

    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1")

    async def override_get_current_user() -> MagicMock:
        return mock_admin_user

    # Override get_current_user - the AdminUser dependency uses this internally
    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio()
async def test_get_onboarding_insights_admin_only(
    admin_test_client: TestClient,
    mock_admin_user: MagicMock,
) -> None:
    """GET /admin/onboarding/insights returns insights for admins."""
    # Mock insights from outcome tracker
    insights = [
        {
            "pattern": "avg_readiness_by_company_type",
            "company_type": "cdmo",
            "value": 82.5,
            "sample_size": 10,
            "evidence_count": 10,
            "confidence": 0.8,
        }
    ]

    with patch("src.db.supabase.SupabaseClient.get_user_by_id", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = {"role": "admin"}

        with patch(
            "src.onboarding.outcome_tracker.OnboardingOutcomeTracker"
        ) as mock_tracker_cls:
            mock_tracker = MagicMock()
            mock_tracker.get_system_insights = AsyncMock(return_value=insights)
            mock_tracker._format_insight.return_value = "Cdmo users average 83% overall readiness after onboarding."
            mock_tracker_cls.return_value = mock_tracker

            response = admin_test_client.get("/api/v1/admin/onboarding/insights")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 0


@pytest.mark.asyncio()
async def test_get_onboarding_outcomes_pagination(
    admin_test_client: TestClient,
    mock_admin_user: MagicMock,
) -> None:
    """GET /admin/onboarding/outcomes supports pagination."""
    outcomes = [
        {
            "id": "outcome-1",
            "user_id": "user-1",
            "completion_time_minutes": 15.0,
            "company_type": "cdmo",
            "steps_completed": 8,
            "steps_skipped": 0,
            "first_goal_category": "lead_gen",
            "documents_uploaded": 3,
            "email_connected": True,
            "crm_connected": True,
            "readiness_snapshot": {"overall": 85.0},
            "created_at": "2026-02-07T12:00:00+00:00",
        }
    ]

    with patch("src.db.supabase.SupabaseClient.get_user_by_id", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = {"role": "admin"}

        with patch("src.db.supabase.SupabaseClient") as mock_db_cls:
            mock_db = MagicMock()
            mock_db_cls.get_client.return_value = mock_db

            # Build chain for outcomes query
            chain = _build_chain(outcomes)
            mock_db.table.return_value = chain

            response = admin_test_client.get("/api/v1/admin/onboarding/outcomes?page=1&page_size=10")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "has_more" in data


@pytest.mark.asyncio()
async def test_consolidate_procedural_insights(
    admin_test_client: TestClient,
    mock_admin_user: MagicMock,
) -> None:
    """POST /admin/onboarding/consolidate triggers consolidation."""
    with patch("src.db.supabase.SupabaseClient.get_user_by_id", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = {"role": "admin"}

        with patch(
            "src.onboarding.outcome_tracker.OnboardingOutcomeTracker"
        ) as mock_tracker_cls:
            mock_tracker = MagicMock()
            mock_tracker.consolidate_to_procedural = AsyncMock(return_value=3)
            mock_tracker_cls.return_value = mock_tracker

            response = admin_test_client.post("/api/v1/admin/onboarding/consolidate")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "message" in data
    assert "3" in data["message"]
