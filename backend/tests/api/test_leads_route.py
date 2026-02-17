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
            patch(
                "src.memory.lead_stakeholders.LeadStakeholderService"
            ) as mock_stakeholder_service,
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


class TestGetInsights:
    """Tests for GET /api/v1/leads/{lead_id}/insights endpoint."""

    def test_get_insights_requires_auth(self) -> None:
        """Test that getting insights requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads/some-lead-id/insights")
        assert response.status_code == 401

    def test_get_insights_success(self, test_client: TestClient) -> None:
        """Test successfully getting insights."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.memory.lead_insights import LeadInsight
        from src.models.lead_memory import InsightType

        mock_insights = [
            LeadInsight(
                id="insight-1",
                lead_memory_id="lead-456",
                insight_type=InsightType.BUYING_SIGNAL,
                content="Decision maker expressed interest in timeline",
                confidence=0.85,
                source_event_id="event-123",
                detected_at=datetime.now(UTC),
                addressed_at=None,
            ),
            LeadInsight(
                id="insight-2",
                lead_memory_id="lead-456",
                insight_type=InsightType.RISK,
                content="No budget confirmation received",
                confidence=0.70,
                source_event_id=None,
                detected_at=datetime.now(UTC),
                addressed_at=None,
            ),
        ]

        # Mock the LeadInsightsService where it's imported (inside the function)
        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.memory.lead_insights.LeadInsightsService") as mock_insights_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock SupabaseClient.get_client()
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_insights_instance = mock_insights_service.return_value
            mock_insights_instance.get_insights = AsyncMock(return_value=mock_insights)

            response = test_client.get("/api/v1/leads/lead-456/insights")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["insight_type"] == "buying_signal"
            assert data[1]["insight_type"] == "risk"

    def test_get_insights_not_found(self, test_client: TestClient) -> None:
        """Test getting insights for non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("lead-999"))

            response = test_client.get("/api/v1/leads/lead-999/insights")

            assert response.status_code == 404


class TestContributionTypeEnum:
    """Tests for ContributionType enum."""

    def test_contribution_type_enum_exists(self) -> None:
        """Test that ContributionType enum has all required values."""
        from src.models.lead_memory import ContributionType

        assert hasattr(ContributionType, "EVENT")
        assert ContributionType.EVENT.value == "event"
        assert hasattr(ContributionType, "NOTE")
        assert ContributionType.NOTE.value == "note"
        assert hasattr(ContributionType, "INSIGHT")
        assert ContributionType.INSIGHT.value == "insight"


class TestContributionStatusEnum:
    """Tests for ContributionStatus enum."""

    def test_contribution_status_enum_exists(self) -> None:
        """Test that ContributionStatus enum has all required values."""
        from src.models.lead_memory import ContributionStatus

        assert hasattr(ContributionStatus, "PENDING")
        assert ContributionStatus.PENDING.value == "pending"
        assert hasattr(ContributionStatus, "MERGED")
        assert ContributionStatus.MERGED.value == "merged"
        assert hasattr(ContributionStatus, "REJECTED")
        assert ContributionStatus.REJECTED.value == "rejected"


class TestTransitionStage:
    """Tests for POST /api/v1/leads/{lead_id}/transition endpoint."""

    def test_transition_stage_requires_auth(self) -> None:
        """Test that transitioning stage requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/some-lead-id/transition",
            json={"stage": "opportunity"},
        )
        assert response.status_code == 401

    def test_transition_stage_success(self, test_client: TestClient) -> None:
        """Test successfully transitioning lead stage."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

        updated_lead = LeadMemory(
            id="lead-123",
            user_id="test-user-123",
            company_name="Test Company",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
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
            mock_instance.get_by_id = AsyncMock(return_value=updated_lead)
            mock_instance.transition_stage = AsyncMock()

            response = test_client.post(
                "/api/v1/leads/lead-123/transition",
                json={"stage": "opportunity"},
            )

            assert response.status_code == 200
            mock_instance.transition_stage.assert_called_once()

    def test_transition_stage_invalid(self, test_client: TestClient) -> None:
        """Test invalid transition returns 400."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import InvalidStageTransitionError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.transition_stage = AsyncMock(
                side_effect=InvalidStageTransitionError("account", "lead")
            )

            response = test_client.post(
                "/api/v1/leads/lead-123/transition",
                json={"stage": "lead"},
            )

            assert response.status_code == 400

    def test_transition_stage_validation_error(self, test_client: TestClient) -> None:
        """Test validation with invalid stage value."""
        response = test_client.post(
            "/api/v1/leads/lead-123/transition",
            json={"stage": "invalid_stage"},
        )
        assert response.status_code == 422


class TestAddContributor:
    """Tests for POST /api/v1/leads/{lead_id}/contributors endpoint."""

    def test_add_contributor_requires_auth(self) -> None:
        """Test that adding a contributor requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/some-lead-id/contributors",
            json={
                "contributor_id": "contributor-123",
                "contributor_name": "Jane Smith",
                "contributor_email": "jane@example.com",
            },
        )
        assert response.status_code == 401

    def test_add_contributor_success(self, test_client: TestClient) -> None:
        """Test successfully adding a contributor."""
        from unittest.mock import AsyncMock, MagicMock, patch

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            # Mock lead verification
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock SupabaseClient.get_client()
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            # Mock collaboration service
            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.add_contributor = AsyncMock(return_value="contributor-123")

            response = test_client.post(
                "/api/v1/leads/lead-456/contributors",
                json={
                    "contributor_id": "contributor-123",
                    "contributor_name": "Jane Smith",
                    "contributor_email": "jane@example.com",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["contributor_id"] == "contributor-123"

    def test_add_contributor_lead_not_found(self, test_client: TestClient) -> None:
        """Test adding contributor to non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("lead-999"))

            response = test_client.post(
                "/api/v1/leads/lead-999/contributors",
                json={
                    "contributor_id": "contributor-123",
                    "contributor_name": "Jane Smith",
                    "contributor_email": "jane@example.com",
                },
            )

            assert response.status_code == 404


class TestListContributors:
    """Tests for GET /api/v1/leads/{lead_id}/contributors endpoint."""

    def test_list_contributors_requires_auth(self) -> None:
        """Test that listing contributors requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads/some-lead-id/contributors")
        assert response.status_code == 401

    def test_list_contributors_success(self, test_client: TestClient) -> None:
        """Test successfully listing contributors."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.services.lead_collaboration import Contributor

        mock_contributors = [
            Contributor(
                id="contributor-1",
                lead_memory_id="lead-456",
                name="Jane Smith",
                email="jane@example.com",
                added_at=datetime.now(UTC),
                contribution_count=3,
            ),
            Contributor(
                id="contributor-2",
                lead_memory_id="lead-456",
                name="Bob Jones",
                email="bob@example.com",
                added_at=datetime.now(UTC),
                contribution_count=1,
            ),
        ]

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.get_contributors = AsyncMock(return_value=mock_contributors)

            response = test_client.get("/api/v1/leads/lead-456/contributors")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "Jane Smith"
            assert data[0]["contribution_count"] == 3
            assert data[1]["name"] == "Bob Jones"

    def test_list_contributors_lead_not_found(self, test_client: TestClient) -> None:
        """Test listing contributors for non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("lead-999"))

            response = test_client.get("/api/v1/leads/lead-999/contributors")

            assert response.status_code == 404


class TestSubmitContribution:
    """Tests for POST /api/v1/leads/{lead_id}/contributions endpoint."""

    def test_submit_contribution_requires_auth(self) -> None:
        """Test that submitting a contribution requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/some-lead-id/contributions",
            json={
                "contribution_type": "note",
                "content": "This is a note contribution",
            },
        )
        assert response.status_code == 401

    def test_submit_contribution_success(self, test_client: TestClient) -> None:
        """Test successfully submitting a contribution."""
        from unittest.mock import AsyncMock, MagicMock, patch

        with (
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.submit_contribution = AsyncMock(return_value="contribution-123")

            response = test_client.post(
                "/api/v1/leads/lead-456/contributions",
                json={
                    "contribution_type": "note",
                    "content": "This is a note contribution",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "contribution-123"

    def test_submit_contribution_validation_error(self, test_client: TestClient) -> None:
        """Test validation when missing required field."""
        response = test_client.post(
            "/api/v1/leads/lead-456/contributions",
            json={},
        )
        assert response.status_code == 422

    def test_submit_contribution_with_event_type(self, test_client: TestClient) -> None:
        """Test submitting an event contribution."""
        from unittest.mock import AsyncMock, MagicMock, patch

        with (
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.submit_contribution = AsyncMock(return_value="contribution-456")

            response = test_client.post(
                "/api/v1/leads/lead-456/contributions",
                json={
                    "contribution_type": "event",
                    "contribution_id": "event-789",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "contribution-456"


class TestListContributions:
    """Tests for GET /api/v1/leads/{lead_id}/contributions endpoint."""

    def test_list_contributions_requires_auth(self) -> None:
        """Test that listing contributions requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads/some-lead-id/contributions")
        assert response.status_code == 401

    def test_list_contributions_success(self, test_client: TestClient) -> None:
        """Test successfully listing contributions."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.services.lead_collaboration import Contribution, ContributionType, ContributionStatus

        mock_contributions = [
            Contribution(
                id="contribution-1",
                lead_memory_id="lead-456",
                contributor_id="contributor-1",
                contribution_type=ContributionType.NOTE,
                contribution_id=None,
                status=ContributionStatus.PENDING,
                reviewed_by=None,
                reviewed_at=None,
                created_at=datetime.now(UTC),
            ),
            Contribution(
                id="contribution-2",
                lead_memory_id="lead-456",
                contributor_id="contributor-2",
                contribution_type=ContributionType.EVENT,
                contribution_id="event-123",
                status=ContributionStatus.PENDING,
                reviewed_by=None,
                reviewed_at=None,
                created_at=datetime.now(UTC),
            ),
        ]

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.get_pending_contributions = AsyncMock(return_value=mock_contributions)

            response = test_client.get("/api/v1/leads/lead-456/contributions")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["id"] == "contribution-1"
            assert data[0]["contribution_type"] == "note"
            assert data[1]["contribution_type"] == "event"

    def test_list_contributions_lead_not_found(self, test_client: TestClient) -> None:
        """Test listing contributions for non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("lead-999"))

            response = test_client.get("/api/v1/leads/lead-999/contributions")

            assert response.status_code == 404


class TestReviewContribution:
    """Tests for POST /api/v1/leads/{lead_id}/contributions/{contribution_id}/review endpoint."""

    def test_review_contribution_requires_auth(self) -> None:
        """Test that reviewing a contribution requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/some-lead-id/contributions/contribution-123/review",
            json={"action": "merge"},
        )
        assert response.status_code == 401

    def test_review_contribution_merge_success(self, test_client: TestClient) -> None:
        """Test successfully merging a contribution."""
        from unittest.mock import AsyncMock, MagicMock, patch

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.review_contribution = AsyncMock()

            response = test_client.post(
                "/api/v1/leads/lead-456/contributions/contribution-123/review",
                json={"action": "merge"},
            )

            assert response.status_code == 204
            assert response.content == b""

    def test_review_contribution_reject_success(self, test_client: TestClient) -> None:
        """Test successfully rejecting a contribution."""
        from unittest.mock import AsyncMock, MagicMock, patch

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.review_contribution = AsyncMock()

            response = test_client.post(
                "/api/v1/leads/lead-456/contributions/contribution-123/review",
                json={"action": "reject"},
            )

            assert response.status_code == 204

    def test_review_contribution_invalid_action(self, test_client: TestClient) -> None:
        """Test reviewing with invalid action returns 400."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.core.exceptions import ValidationError

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
            patch(
                "src.services.lead_collaboration.LeadCollaborationService"
            ) as mock_collab_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            mock_sb_client.get_client = MagicMock(return_value=MagicMock())

            mock_collab_instance = mock_collab_service.return_value
            mock_collab_instance.review_contribution = AsyncMock(
                side_effect=ValidationError("Invalid action", field="action")
            )

            response = test_client.post(
                "/api/v1/leads/lead-456/contributions/contribution-123/review",
                json={"action": "merge"},  # Valid Pydantic value, but service will reject
            )

            assert response.status_code == 400

    def test_review_contribution_lead_not_found(self, test_client: TestClient) -> None:
        """Test reviewing contribution for non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("lead-999"))

            response = test_client.post(
                "/api/v1/leads/lead-999/contributions/contribution-123/review",
                json={"action": "merge"},
            )

            assert response.status_code == 404

    def test_review_contribution_validation_error(self, test_client: TestClient) -> None:
        """Test validation when action is missing."""
        response = test_client.post(
            "/api/v1/leads/lead-456/contributions/contribution-123/review",
            json={},
        )
        assert response.status_code == 422


class TestBatchScoreLeads:
    """Tests for POST /api/v1/leads/batch-score endpoint."""

    def test_batch_score_requires_auth(self) -> None:
        """Test that batch scoring requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post("/api/v1/leads/batch-score")
        assert response.status_code == 401

    def test_batch_score_success(self, test_client: TestClient) -> None:
        """Test successfully batch scoring leads."""
        from unittest.mock import AsyncMock, patch

        from src.services.conversion_scoring import BatchScoreResult

        mock_result = BatchScoreResult(
            scored=10,
            errors=[],
            duration_seconds=2.5,
        )

        with patch(
            "src.services.conversion_scoring.ConversionScoringService"
        ) as mock_scoring_service:
            mock_instance = mock_scoring_service.return_value
            mock_instance.batch_score_all_leads = AsyncMock(return_value=mock_result)

            response = test_client.post("/api/v1/leads/batch-score")

            assert response.status_code == 200
            data = response.json()
            assert data["scored"] == 10
            assert data["errors"] == []
            assert data["duration_seconds"] == 2.5

    def test_batch_score_with_errors(self, test_client: TestClient) -> None:
        """Test batch scoring with some errors."""
        from unittest.mock import AsyncMock, patch

        from src.services.conversion_scoring import BatchScoreResult

        mock_result = BatchScoreResult(
            scored=8,
            errors=[
                {"lead_id": "lead-1", "error": "Scoring failed"},
                {"lead_id": "lead-2", "error": "Missing data"},
            ],
            duration_seconds=3.0,
        )

        with patch(
            "src.services.conversion_scoring.ConversionScoringService"
        ) as mock_scoring_service:
            mock_instance = mock_scoring_service.return_value
            mock_instance.batch_score_all_leads = AsyncMock(return_value=mock_result)

            response = test_client.post("/api/v1/leads/batch-score")

            assert response.status_code == 200
            data = response.json()
            assert data["scored"] == 8
            assert len(data["errors"]) == 2


class TestConversionRankings:
    """Tests for GET /api/v1/leads/conversion-rankings endpoint."""

    def test_rankings_requires_auth(self) -> None:
        """Test that getting rankings requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads/conversion-rankings")
        assert response.status_code == 401

    def test_rankings_success(self, test_client: TestClient) -> None:
        """Test successfully getting conversion rankings."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.data = [
            {
                "id": "lead-1",
                "company_name": "Acme Corp",
                "lifecycle_stage": "opportunity",
                "metadata": {
                    "conversion_score": {
                        "conversion_probability": 75.0,
                        "confidence": 0.85,
                    }
                },
                "health_score": 80,
                "expected_value": 100000,
            },
            {
                "id": "lead-2",
                "company_name": "Beta Inc",
                "lifecycle_stage": "lead",
                "metadata": {
                    "conversion_score": {
                        "conversion_probability": 45.0,
                        "confidence": 0.65,
                    }
                },
                "health_score": 60,
                "expected_value": 50000,
            },
        ]

        with patch("src.db.supabase.SupabaseClient") as mock_sb_client:
            mock_db = MagicMock()
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.is_.return_value.execute.return_value = mock_result
            mock_sb_client.get_client = MagicMock(return_value=mock_db)

            response = test_client.get("/api/v1/leads/conversion-rankings")

            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 2
            assert len(data["rankings"]) == 2
            # Should be sorted by probability descending
            assert data["rankings"][0]["conversion_probability"] == 75.0
            assert data["rankings"][1]["conversion_probability"] == 45.0

    def test_rankings_with_min_probability_filter(self, test_client: TestClient) -> None:
        """Test rankings with minimum probability filter."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.data = [
            {
                "id": "lead-1",
                "company_name": "Acme Corp",
                "lifecycle_stage": "opportunity",
                "metadata": {
                    "conversion_score": {
                        "conversion_probability": 75.0,
                        "confidence": 0.85,
                    }
                },
                "health_score": 80,
                "expected_value": 100000,
            },
            {
                "id": "lead-2",
                "company_name": "Low Score Inc",
                "lifecycle_stage": "lead",
                "metadata": {
                    "conversion_score": {
                        "conversion_probability": 25.0,
                        "confidence": 0.65,
                    }
                },
                "health_score": 40,
                "expected_value": 10000,
            },
        ]

        with patch("src.db.supabase.SupabaseClient") as mock_sb_client:
            mock_db = MagicMock()
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.is_.return_value.execute.return_value = mock_result
            mock_sb_client.get_client = MagicMock(return_value=mock_db)

            response = test_client.get("/api/v1/leads/conversion-rankings?min_probability=50")

            assert response.status_code == 200
            data = response.json()
            # Only lead with 75% should be included
            assert data["total_count"] == 1
            assert data["rankings"][0]["conversion_probability"] == 75.0

    def test_rankings_with_limit(self, test_client: TestClient) -> None:
        """Test rankings with limit parameter."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.data = [
            {
                "id": f"lead-{i}",
                "company_name": f"Company {i}",
                "lifecycle_stage": "opportunity",
                "metadata": {
                    "conversion_score": {
                        "conversion_probability": 80.0 - i * 10,
                        "confidence": 0.8,
                    }
                },
                "health_score": 70,
                "expected_value": 50000,
            }
            for i in range(5)
        ]

        with patch("src.db.supabase.SupabaseClient") as mock_sb_client:
            mock_db = MagicMock()
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.not_.is_.return_value.execute.return_value = mock_result
            mock_sb_client.get_client = MagicMock(return_value=mock_db)

            response = test_client.get("/api/v1/leads/conversion-rankings?limit=3")

            assert response.status_code == 200
            data = response.json()
            assert len(data["rankings"]) == 3


class TestGetConversionScore:
    """Tests for GET /api/v1/leads/{lead_id}/conversion-score endpoint."""

    def test_conversion_score_requires_auth(self) -> None:
        """Test that getting conversion score requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads/some-lead-id/conversion-score")
        assert response.status_code == 401

    def test_conversion_score_success(self, test_client: TestClient) -> None:
        """Test successfully getting conversion score."""
        from datetime import UTC, datetime
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch

        from src.services.conversion_scoring import ConversionScore, ScoreExplanation, FeatureDriver

        lead_id = str(uuid4())
        mock_score = ConversionScore(
            lead_memory_id=uuid4(),
            conversion_probability=72.5,
            confidence=0.85,
            feature_values={"engagement_frequency": 0.8, "stakeholder_depth": 0.6},
            feature_importance={"engagement_frequency": 0.144, "stakeholder_depth": 0.072},
            calculated_at=datetime.now(UTC),
        )

        mock_explanation = ScoreExplanation(
            lead_memory_id=uuid4(),
            conversion_probability=72.5,
            summary="Acme Corp has a 73% conversion probability. Key strengths: strong engagement.",
            key_drivers=[
                FeatureDriver(
                    name="engagement_frequency",
                    value=0.8,
                    contribution=0.144,
                    description="16 interactions this month",
                )
            ],
            key_risks=[
                FeatureDriver(
                    name="stakeholder_depth",
                    value=0.4,
                    contribution=0.048,
                    description="limited stakeholder mapping",
                )
            ],
            recommendation="Map additional stakeholders and expand relationships.",
        )

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch(
                "src.services.conversion_scoring.ConversionScoringService"
            ) as mock_scoring_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            mock_scoring_instance = mock_scoring_service.return_value
            mock_scoring_instance.calculate_conversion_score = AsyncMock(return_value=mock_score)
            mock_scoring_instance.explain_score = AsyncMock(return_value=mock_explanation)

            response = test_client.get(f"/api/v1/leads/{lead_id}/conversion-score")

            assert response.status_code == 200
            data = response.json()
            assert data["conversion_probability"] == 72.5
            assert data["confidence"] == 0.85
            assert "summary" in data
            assert len(data["key_drivers"]) == 1
            assert len(data["key_risks"]) == 1
            assert "recommendation" in data

    def test_conversion_score_lead_not_found(self, test_client: TestClient) -> None:
        """Test getting conversion score for non-existent lead returns 404."""
        from unittest.mock import AsyncMock, patch

        from src.core.exceptions import LeadNotFoundError

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=LeadNotFoundError("lead-999"))

            response = test_client.get("/api/v1/leads/lead-999/conversion-score")

            assert response.status_code == 404

    def test_conversion_score_with_force_refresh(self, test_client: TestClient) -> None:
        """Test force refresh parameter is passed to scoring service."""
        from datetime import UTC, datetime
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch, call

        from src.services.conversion_scoring import ConversionScore, ScoreExplanation

        mock_score = ConversionScore(
            lead_memory_id=uuid4(),
            conversion_probability=65.0,
            confidence=0.75,
            feature_values={},
            feature_importance={},
            calculated_at=datetime.now(UTC),
        )

        mock_explanation = ScoreExplanation(
            lead_memory_id=uuid4(),
            conversion_probability=65.0,
            summary="Test summary",
            key_drivers=[],
            key_risks=[],
            recommendation="Test recommendation",
        )

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service,
            patch(
                "src.services.conversion_scoring.ConversionScoringService"
            ) as mock_scoring_service,
        ):
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            mock_scoring_instance = mock_scoring_service.return_value
            mock_scoring_instance.calculate_conversion_score = AsyncMock(return_value=mock_score)
            mock_scoring_instance.explain_score = AsyncMock(return_value=mock_explanation)

            response = test_client.get("/api/v1/leads/lead-123/conversion-score?force_refresh=true")

            assert response.status_code == 200
            # Verify force_refresh was passed
            mock_scoring_instance.calculate_conversion_score.assert_called_once_with(
                "lead-123", force_refresh=True
            )


class TestUpdateLeadPredictionValidation:
    """Tests for prediction validation when lead status changes to won/lost."""

    def test_update_to_won_validates_prediction(self, test_client: TestClient) -> None:
        """Test that updating status to won triggers prediction validation."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

        existing_lead = LeadMemory(
            id="test-lead-123",
            user_id="test-user-123",
            company_name="Test Company",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.ACTIVE,  # Previous status
            health_score=75,
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
            status=LeadStatus.WON,  # New status
            health_score=75,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_prediction_result = MagicMock()
        mock_prediction_result.data = [
            {
                "id": "prediction-123",
                "predicted_outcome": "won",
                "confidence": 0.85,
            }
        ]

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
        ):
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=[existing_lead, updated_lead])
            mock_instance.update = AsyncMock()

            mock_db = MagicMock()
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_prediction_result
            mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            mock_db.rpc.return_value.execute.return_value = MagicMock()
            mock_sb_client.get_client = MagicMock(return_value=mock_db)

            response = test_client.patch(
                "/api/v1/leads/test-lead-123",
                json={"status": "won"},
            )

            assert response.status_code == 200
            # Verify prediction validation was called
            mock_db.table.assert_called()

    def test_update_to_lost_validates_prediction(self, test_client: TestClient) -> None:
        """Test that updating status to lost triggers prediction validation."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

        existing_lead = LeadMemory(
            id="test-lead-456",
            user_id="test-user-123",
            company_name="Lost Company",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=30,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        updated_lead = LeadMemory(
            id="test-lead-456",
            user_id="test-user-123",
            company_name="Lost Company",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.LOST,
            health_score=30,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_prediction_result = MagicMock()
        mock_prediction_result.data = []  # No prediction found

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
        ):
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=[existing_lead, updated_lead])
            mock_instance.update = AsyncMock()

            mock_db = MagicMock()
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_prediction_result
            mock_sb_client.get_client = MagicMock(return_value=mock_db)

            response = test_client.patch(
                "/api/v1/leads/test-lead-456",
                json={"status": "lost"},
            )

            assert response.status_code == 200

    def test_update_active_to_active_no_validation(self, test_client: TestClient) -> None:
        """Test that updating active to active doesn't trigger validation."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

        existing_lead = LeadMemory(
            id="test-lead-789",
            user_id="test-user-123",
            company_name="Active Company",
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
            id="test-lead-789",
            user_id="test-user-123",
            company_name="Active Company Updated",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=60,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with (
            patch("src.api.routes.leads.LeadMemoryService") as mock_service,
            patch("src.db.supabase.SupabaseClient") as mock_sb_client,
        ):
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(side_effect=[existing_lead, updated_lead])
            mock_instance.update = AsyncMock()

            mock_db = MagicMock()
            mock_sb_client.get_client = MagicMock(return_value=mock_db)

            response = test_client.patch(
                "/api/v1/leads/test-lead-789",
                json={"health_score": 60, "company_name": "Active Company Updated"},
            )

            assert response.status_code == 200
            # Supabase should not be called for prediction validation
            # since status didn't change to won/lost
            mock_db.table.assert_not_called()


class TestLeadMemoryResponseWithConversionScore:
    """Tests for LeadMemoryResponse with conversion_score field."""

    def test_response_includes_conversion_score(self, test_client: TestClient) -> None:
        """Test that lead response includes conversion score when available."""
        from datetime import UTC, datetime
        from decimal import Decimal
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

        mock_lead = LeadMemory(
            id="test-lead-123",
            user_id="test-user-123",
            company_name="Scored Company",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.ACTIVE,
            health_score=75,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            expected_value=Decimal("100000"),
            tags=["enterprise"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        # Add metadata with conversion score
        mock_lead.metadata = {
            "conversion_score": {
                "conversion_probability": 72.5,
                "confidence": 0.85,
                "calculated_at": datetime.now(UTC).isoformat(),
            }
        }

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(return_value=mock_lead)

            response = test_client.get("/api/v1/leads/test-lead-123")

            assert response.status_code == 200
            data = response.json()
            assert "conversion_score" in data
            assert data["conversion_score"]["probability"] == 72.5
            assert data["conversion_score"]["confidence"] == 0.85

    def test_response_without_conversion_score(self, test_client: TestClient) -> None:
        """Test that lead response handles missing conversion score."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType

        mock_lead = LeadMemory(
            id="test-lead-456",
            user_id="test-user-123",
            company_name="Unscored Company",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            tags=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead.metadata = {}  # No conversion score

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(return_value=mock_lead)

            response = test_client.get("/api/v1/leads/test-lead-456")

            assert response.status_code == 200
            data = response.json()
            assert data["conversion_score"] is None
