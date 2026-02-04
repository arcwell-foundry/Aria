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


class TestAddEvent:
    """Tests for POST /api/v1/leads/{lead_id}/notes endpoint."""

    def test_add_event_requires_auth(self) -> None:
        """Test that adding an event requires authentication."""
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

    def test_add_event_success(self, test_client: TestClient) -> None:
        """Test successfully adding an event."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import EventType

        mock_event = LeadEvent(
            id="event-123",
            lead_memory_id="lead-456",
            event_type=EventType.NOTE,
            direction=None,
            subject=None,
            content="Test note content",
            participants=[],
            occurred_at=datetime.now(UTC),
            source="manual",
            source_id=None,
            created_at=datetime.now(UTC),
        )

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch("src.memory.lead_memory_events.LeadEventService") as mock_event_service,
        ):
            # Mock lead verification
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock SupabaseClient.get_client()
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            # Mock event creation
            mock_event_instance = mock_event_service.return_value
            mock_event_instance.add_event = AsyncMock(return_value="event-123")
            mock_event_instance.get_timeline = AsyncMock(return_value=[mock_event])

            response = test_client.post(
                "/api/v1/leads/lead-456/notes",
                json={
                    "event_type": "note",
                    "content": "Test note content",
                    "occurred_at": "2025-01-01T00:00:00Z",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "event-123"
            assert data["content"] == "Test note content"

    def test_add_event_lead_not_found(self, test_client: TestClient) -> None:
        """Test adding event to non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("lead-999"))

            response = test_client.post(
                "/api/v1/leads/lead-999/notes",
                json={
                    "event_type": "note",
                    "content": "Test",
                    "occurred_at": "2025-01-01T00:00:00Z",
                },
            )

            assert response.status_code == 404

    def test_add_event_with_email_sent(self, test_client: TestClient) -> None:
        """Test adding an email_sent event with all fields."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import Direction, EventType

        mock_event = LeadEvent(
            id="event-456",
            lead_memory_id="lead-789",
            event_type=EventType.EMAIL_SENT,
            direction=Direction.OUTBOUND,
            subject="Follow up on proposal",
            content="Hi John, checking in on the proposal...",
            participants=["john@example.com", "jane@example.com"],
            occurred_at=datetime.now(UTC),
            source="gmail",
            source_id="gmail-msg-123",
            created_at=datetime.now(UTC),
        )

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch("src.memory.lead_memory_events.LeadEventService") as mock_event_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock SupabaseClient.get_client()
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_event_instance = mock_event_service.return_value
            mock_event_instance.add_event = AsyncMock(return_value="event-456")
            mock_event_instance.get_timeline = AsyncMock(return_value=[mock_event])

            response = test_client.post(
                "/api/v1/leads/lead-789/notes",
                json={
                    "event_type": "email_sent",
                    "direction": "outbound",
                    "subject": "Follow up on proposal",
                    "content": "Hi John, checking in on the proposal...",
                    "participants": ["john@example.com", "jane@example.com"],
                    "occurred_at": "2025-01-15T10:30:00Z",
                    "source": "gmail",
                    "source_id": "gmail-msg-123",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "event-456"
            assert data["event_type"] == "email_sent"
            assert data["direction"] == "outbound"
            assert data["subject"] == "Follow up on proposal"
            assert len(data["participants"]) == 2

    def test_add_event_with_meeting(self, test_client: TestClient) -> None:
        """Test adding a meeting event."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import EventType

        mock_event = LeadEvent(
            id="event-789",
            lead_memory_id="lead-101",
            event_type=EventType.MEETING,
            direction=None,
            subject="Product Demo",
            content="Discussed key features and pricing",
            participants=["cto@example.com", "ceo@example.com"],
            occurred_at=datetime.now(UTC),
            source="calendar",
            source_id="cal-event-456",
            created_at=datetime.now(UTC),
        )

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch("src.memory.lead_memory_events.LeadEventService") as mock_event_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock SupabaseClient.get_client()
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_event_instance = mock_event_service.return_value
            mock_event_instance.add_event = AsyncMock(return_value="event-789")
            mock_event_instance.get_timeline = AsyncMock(return_value=[mock_event])

            response = test_client.post(
                "/api/v1/leads/lead-101/notes",
                json={
                    "event_type": "meeting",
                    "subject": "Product Demo",
                    "content": "Discussed key features and pricing",
                    "participants": ["cto@example.com", "ceo@example.com"],
                    "occurred_at": "2025-01-20T14:00:00Z",
                    "source": "calendar",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "event-789"
            assert data["event_type"] == "meeting"
            assert data["subject"] == "Product Demo"

    def test_add_event_validation_error(self, test_client: TestClient) -> None:
        """Test validation error when required fields are missing."""
        response = test_client.post(
            "/api/v1/leads/lead-123/notes",
            json={
                "event_type": "note",
                # Missing occurred_at which is required
            },
        )
        assert response.status_code == 422

    def test_add_event_invalid_event_type(self, test_client: TestClient) -> None:
        """Test validation error with invalid event type."""
        response = test_client.post(
            "/api/v1/leads/lead-123/notes",
            json={
                "event_type": "invalid_type",
                "content": "Test",
                "occurred_at": "2025-01-01T00:00:00Z",
            },
        )
        assert response.status_code == 422


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
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

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
        from datetime import UTC, date, datetime
        from decimal import Decimal
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

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


class TestUpdateLead:
    """Tests for PATCH /api/v1/leads/{lead_id} endpoint."""

    def test_update_lead_requires_auth(self) -> None:
        """Test that updating a lead requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.patch(
            "/api/v1/leads/some-lead-id",
            json={"company_name": "Updated Name"},
        )
        assert response.status_code == 401

    def test_update_lead_partial(self, test_client: TestClient) -> None:
        """Test updating a lead with partial data."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

        existing_lead = LeadMemory(
            id="test-lead-123",
            user_id="test-user-123",
            company_name="Original Name",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        updated_lead = LeadMemory(
            id="test-lead-123",
            user_id="test-user-123",
            company_name="Original Name",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=75,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=[existing_lead, updated_lead])
            mock_instance.update = AsyncMock()

            response = test_client.patch(
                "/api/v1/leads/test-lead-123",
                json={"health_score": 75},
            )

            assert response.status_code == 200
            mock_instance.update.assert_called_once()

    def test_update_lead_not_found(self, test_client: TestClient) -> None:
        """Test updating a non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("test-lead-999"))

            response = test_client.patch(
                "/api/v1/leads/test-lead-999",
                json={"company_name": "New Name"},
            )

            assert response.status_code == 404

    def test_update_lead_with_lifecycle_stage_and_status(self, test_client: TestClient) -> None:
        """Test updating lifecycle_stage and status fields."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        existing_lead = LeadMemory(
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

        updated_lead = LeadMemory(
            id="test-lead-123",
            user_id="test-user-123",
            company_name="Test Company",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.WON,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=[existing_lead, updated_lead])
            mock_instance.update = AsyncMock()

            response = test_client.patch(
                "/api/v1/leads/test-lead-123",
                json={
                    "lifecycle_stage": "opportunity",
                    "status": "won",
                },
            )

            # Verify the update was called with the correct arguments
            mock_instance.update.assert_called_once()
            call_kwargs = mock_instance.update.call_args.kwargs

            assert call_kwargs["lifecycle_stage"] == LifecycleStage.OPPORTUNITY
            assert call_kwargs["status"] == LeadStatus.WON
            assert response.status_code == 200
            data = response.json()
            assert data["lifecycle_stage"] == "opportunity"
            assert data["status"] == "won"


class TestAddStakeholder:
    """Tests for POST /api/v1/leads/{lead_id}/stakeholders endpoint."""

    def test_add_stakeholder_requires_auth(self) -> None:
        """Test that adding a stakeholder requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/some-lead-id/stakeholders",
            json={
                "contact_email": "john@example.com",
                "contact_name": "John Doe",
                "role": "decision_maker",
            },
        )
        assert response.status_code == 401

    def test_add_stakeholder_success(self, test_client: TestClient) -> None:
        """Test successfully adding a stakeholder."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.memory.lead_stakeholders import LeadStakeholder
        from src.models.lead_memory import Sentiment, StakeholderRole

        mock_stakeholder = LeadStakeholder(
            id="stakeholder-123",
            lead_memory_id="lead-456",
            contact_email="john@example.com",
            contact_name="John Doe",
            title="CTO",
            role=StakeholderRole.DECISION_MAKER,
            influence_level=8,
            sentiment=Sentiment.POSITIVE,
            last_contacted_at=None,
            notes=None,
            created_at=datetime.now(UTC),
        )

        # Patch SupabaseClient at the source - both the route and service import from here
        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch("src.memory.lead_stakeholders.LeadStakeholderService") as mock_stakeholder_service,
        ):
            # Mock lead verification
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock SupabaseClient.get_client() for both import locations
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            # Mock stakeholder creation
            mock_stakeholder_instance = mock_stakeholder_service.return_value
            mock_stakeholder_instance.add_stakeholder = AsyncMock(return_value="stakeholder-123")
            mock_stakeholder_instance.list_by_lead = AsyncMock(return_value=[mock_stakeholder])

            response = test_client.post(
                "/api/v1/leads/lead-456/stakeholders",
                json={
                    "contact_email": "john@example.com",
                    "contact_name": "John Doe",
                    "title": "CTO",
                    "role": "decision_maker",
                    "influence_level": 8,
                    "sentiment": "positive",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "stakeholder-123"
            assert data["contact_email"] == "john@example.com"

    def test_add_stakeholder_validation_error(self, test_client: TestClient) -> None:
        """Test validation when missing required field."""
        response = test_client.post(
            "/api/v1/leads/lead-456/stakeholders",
            json={"contact_name": "John Doe"},  # Missing contact_email
        )
        assert response.status_code == 422
