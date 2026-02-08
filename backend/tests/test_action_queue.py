"""Tests for action queue API routes (US-937).

Covers: GET /actions, POST /actions, GET /actions/{id},
POST /actions/{id}/approve, POST /actions/{id}/reject,
POST /actions/batch-approve, GET /actions/pending-count,
POST /actions/{id}/execute.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.api.routes.action_queue import router

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
def mock_service() -> MagicMock:
    """Mock ActionQueueService via the _get_service helper."""
    with patch("src.api.routes.action_queue._get_service") as mock_factory:
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


# Sample data factory
def _sample_action(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "act-1",
        "user_id": "user-123",
        "agent": "scout",
        "action_type": "research",
        "title": "Research competitor X",
        "description": "Gather market intelligence",
        "risk_level": "low",
        "status": "pending",
        "payload": {},
        "reasoning": "Competitor launched new product",
        "result": {},
        "approved_at": None,
        "completed_at": None,
        "created_at": "2026-02-08T00:00:00Z",
        "updated_at": "2026-02-08T00:00:00Z",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /actions
# ---------------------------------------------------------------------------


class TestListActions:
    """Tests for GET /actions."""

    def test_returns_list_of_actions(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """GET /actions returns a list of actions."""
        mock_service.get_queue = AsyncMock(
            return_value=[
                _sample_action(id="act-1"),
                _sample_action(id="act-2", status="completed"),
            ]
        )

        response = client.get(
            "/api/v1/actions",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_filters_by_status(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """GET /actions?status=pending returns filtered actions."""
        mock_service.get_queue = AsyncMock(return_value=[_sample_action()])

        response = client.get(
            "/api/v1/actions?status=pending",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        mock_service.get_queue.assert_called_once_with("user-123", "pending", 50)


# ---------------------------------------------------------------------------
# POST /actions
# ---------------------------------------------------------------------------


class TestSubmitAction:
    """Tests for POST /actions."""

    def test_submits_low_risk_auto_approved(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions with low risk auto-approves."""
        mock_service.submit_action = AsyncMock(return_value=_sample_action(status="auto_approved"))

        response = client.post(
            "/api/v1/actions",
            json={
                "agent": "scout",
                "action_type": "research",
                "title": "Quick research",
                "risk_level": "low",
            },
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "auto_approved"

    def test_submits_high_risk_pending(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions with high risk stays pending."""
        mock_service.submit_action = AsyncMock(
            return_value=_sample_action(status="pending", risk_level="high")
        )

        response = client.post(
            "/api/v1/actions",
            json={
                "agent": "operator",
                "action_type": "crm_update",
                "title": "Update CRM record",
                "risk_level": "high",
                "reasoning": "New contact info from meeting",
            },
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"

    def test_submits_critical_risk_pending(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions with critical risk stays pending."""
        mock_service.submit_action = AsyncMock(
            return_value=_sample_action(status="pending", risk_level="critical")
        )

        response = client.post(
            "/api/v1/actions",
            json={
                "agent": "scribe",
                "action_type": "email_draft",
                "title": "Send email to prospect",
                "risk_level": "critical",
            },
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"


# ---------------------------------------------------------------------------
# GET /actions/{action_id}
# ---------------------------------------------------------------------------


class TestGetAction:
    """Tests for GET /actions/{action_id}."""

    def test_returns_action_detail(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """GET /actions/{id} returns action with reasoning."""
        mock_service.get_action = AsyncMock(
            return_value=_sample_action(reasoning="Competitor launched new product")
        )

        response = client.get(
            "/api/v1/actions/act-1",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reasoning"] == "Competitor launched new product"

    def test_returns_404_if_not_found(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """GET /actions/{id} returns 404 if not found."""
        mock_service.get_action = AsyncMock(return_value=None)

        response = client.get(
            "/api/v1/actions/act-missing",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Action not found"


# ---------------------------------------------------------------------------
# POST /actions/{action_id}/approve
# ---------------------------------------------------------------------------


class TestApproveAction:
    """Tests for POST /actions/{action_id}/approve."""

    def test_approves_pending_action(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/{id}/approve approves a pending action."""
        mock_service.approve_action = AsyncMock(
            return_value=_sample_action(
                status="approved",
                approved_at="2026-02-08T01:00:00Z",
            )
        )

        response = client.post(
            "/api/v1/actions/act-1/approve",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["approved_at"] is not None

    def test_returns_404_if_not_pending(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/{id}/approve returns 404 if not pending."""
        mock_service.approve_action = AsyncMock(return_value=None)

        response = client.post(
            "/api/v1/actions/act-already-done/approve",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /actions/{action_id}/reject
# ---------------------------------------------------------------------------


class TestRejectAction:
    """Tests for POST /actions/{action_id}/reject."""

    def test_rejects_pending_action(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/{id}/reject rejects a pending action."""
        mock_service.reject_action = AsyncMock(
            return_value=_sample_action(
                status="rejected",
                result={"rejection_reason": "Not needed"},
            )
        )

        response = client.post(
            "/api/v1/actions/act-1/reject",
            json={"reason": "Not needed"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert data["result"]["rejection_reason"] == "Not needed"

    def test_rejects_without_reason(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/{id}/reject works without a reason."""
        mock_service.reject_action = AsyncMock(return_value=_sample_action(status="rejected"))

        response = client.post(
            "/api/v1/actions/act-1/reject",
            json={},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "rejected"

    def test_returns_404_if_not_pending(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/{id}/reject returns 404 if not pending."""
        mock_service.reject_action = AsyncMock(return_value=None)

        response = client.post(
            "/api/v1/actions/act-done/reject",
            json={"reason": "Too late"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /actions/batch-approve
# ---------------------------------------------------------------------------


class TestBatchApprove:
    """Tests for POST /actions/batch-approve."""

    def test_approves_multiple_actions(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/batch-approve approves multiple actions."""
        mock_service.batch_approve = AsyncMock(
            return_value=[
                _sample_action(id="act-1", status="approved"),
                _sample_action(id="act-2", status="approved"),
            ]
        )

        response = client.post(
            "/api/v1/actions/batch-approve",
            json={"action_ids": ["act-1", "act-2"]},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["approved"]) == 2

    def test_partial_batch_approve(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/batch-approve handles partial success."""
        mock_service.batch_approve = AsyncMock(
            return_value=[_sample_action(id="act-1", status="approved")]
        )

        response = client.post(
            "/api/v1/actions/batch-approve",
            json={"action_ids": ["act-1", "act-already-done"]},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1


# ---------------------------------------------------------------------------
# GET /actions/pending-count
# ---------------------------------------------------------------------------


class TestPendingCount:
    """Tests for GET /actions/pending-count."""

    def test_returns_count(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """GET /actions/pending-count returns pending count."""
        mock_service.get_pending_count = AsyncMock(return_value=5)

        response = client.get(
            "/api/v1/actions/pending-count",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5


# ---------------------------------------------------------------------------
# POST /actions/{action_id}/execute
# ---------------------------------------------------------------------------


class TestExecuteAction:
    """Tests for POST /actions/{action_id}/execute."""

    def test_executes_approved_action(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/{id}/execute executes an approved action."""
        mock_service.execute_action = AsyncMock(
            return_value=_sample_action(
                status="completed",
                completed_at="2026-02-08T02:00:00Z",
                result={"executed": True},
            )
        )

        response = client.post(
            "/api/v1/actions/act-1/execute",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"]["executed"] is True

    def test_returns_404_if_not_approved(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """POST /actions/{id}/execute returns 404 if not approved."""
        mock_service.execute_action = AsyncMock(return_value=None)

        response = client.post(
            "/api/v1/actions/act-pending/execute",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 404
