"""Tests for leads API routes."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import leads


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(leads.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""
    from src.api.deps import get_current_user

    app = create_test_app()

    def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestListLeads:
    """Tests for GET /api/v1/leads endpoint."""

    def test_list_leads_requires_auth(self) -> None:
        """Test that listing leads requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads")
        assert response.status_code == 401


class TestGetLead:
    """Tests for GET /api/v1/leads/{lead_id} endpoint."""

    def test_get_lead_requires_auth(self) -> None:
        """Test that getting a lead requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads/some-lead-id")
        assert response.status_code == 401


class TestAddNote:
    """Tests for POST /api/v1/leads/{lead_id}/notes endpoint."""

    def test_add_note_requires_auth(self) -> None:
        """Test that adding a note requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/some-lead-id/notes",
            json={
                "event_type": "note",
                "content": "Test note",
                "occurred_at": "2025-01-01T00:00:00Z",
            },
        )
        assert response.status_code == 401


class TestExportLeads:
    """Tests for POST /api/v1/leads/export endpoint."""

    def test_export_leads_requires_auth(self) -> None:
        """Test that exporting leads requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/export",
            json=["lead-1", "lead-2"],
        )
        assert response.status_code == 401


class TestCreateLead:
    """Tests for POST /api/v1/leads endpoint."""

    def test_create_lead_requires_auth(self) -> None:
        """Test that creating a lead requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads",
            json={
                "company_name": "Test Company",
                "lifecycle_stage": "lead",
            },
        )
        assert response.status_code == 401

    def test_create_lead_with_minimal_data(self, test_client: TestClient) -> None:
        """Test creating a lead with minimal required fields."""
        from unittest.mock import AsyncMock, patch
        from src.memory.lead_memory import LeadMemory, TriggerType, LifecycleStage, LeadStatus
        from datetime import datetime, UTC

        mock_lead = LeadMemory(
            id="test-lead-123",
            user_id="test-user-123",
            company_name="Test Company",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.create = AsyncMock(return_value=mock_lead)

            response = test_client.post(
                "/api/v1/leads",
                json={"company_name": "Test Company"},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "test-lead-123"
            assert data["company_name"] == "Test Company"
            assert data["lifecycle_stage"] == "lead"
            assert data["status"] == "active"

    def test_create_lead_with_all_fields(self, test_client: TestClient) -> None:
        """Test creating a lead with all optional fields."""
        from unittest.mock import AsyncMock, patch
        from src.memory.lead_memory import LeadMemory, TriggerType, LifecycleStage, LeadStatus
        from datetime import datetime, UTC, date
        from decimal import Decimal

        mock_lead = LeadMemory(
            id="test-lead-456",
            user_id="test-user-123",
            company_name="Full Test Company",
            company_id="company-uuid",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            expected_close_date=date(2025, 6, 30),
            expected_value=Decimal("100000.00"),
            tags=["enterprise", "healthcare"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.create = AsyncMock(return_value=mock_lead)

            response = test_client.post(
                "/api/v1/leads",
                json={
                    "company_name": "Full Test Company",
                    "company_id": "company-uuid",
                    "lifecycle_stage": "opportunity",
                    "expected_close_date": "2025-06-30",
                    "expected_value": 100000.00,
                    "tags": ["enterprise", "healthcare"],
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["company_name"] == "Full Test Company"
            assert data["lifecycle_stage"] == "opportunity"
            assert data["tags"] == ["enterprise", "healthcare"]

    def test_create_lead_validation_error(self, test_client: TestClient) -> None:
        """Test validation when missing required field."""
        response = test_client.post("/api/v1/leads", json={})
        assert response.status_code == 422  # Pydantic validation error
