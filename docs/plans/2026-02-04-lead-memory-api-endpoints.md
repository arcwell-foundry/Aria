# Lead Memory API Endpoints Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Lead Memory REST API with 6 missing endpoints for CRUD operations, event tracking, stakeholder management, AI insights, and lifecycle stage transitions.

**Architecture:**
- Routes use FastAPI with Pydantic request/response models
- Service layer (`LeadMemoryService`, `LeadEventService`) handles business logic
- User isolation enforced via `CurrentUser` dependency
- RLS policies on Supabase tables enforce data access
- New services needed: `LeadStakeholderService`, `LeadInsightsService` (placeholder for US-515)

**Tech Stack:**
- Python 3.11+, FastAPI, Pydantic v2
- Supabase PostgreSQL client
- Existing models in `src/models/lead_memory.py`
- Existing services in `src/memory/lead_memory.py`, `src/memory/lead_memory_events.py`
- Test framework: pytest + TestClient

**File Structure:**
```
backend/src/
├── api/routes/leads.py          # MODIFY: Add 6 new endpoints
├── models/lead_memory.py         # EXISTS: All schemas already defined
├── memory/
│   ├── lead_memory.py            # EXISTS: LeadMemoryService
│   ├── lead_memory_events.py     # EXISTS: LeadEventService
│   ├── lead_stakeholders.py      # CREATE: New stakeholder service
│   └── lead_insights.py          # CREATE: New insights service (placeholder)
└── core/exceptions.py            # EXISTS: All exceptions defined

backend/tests/api/test_leads_route.py  # MODIFY: Add integration tests
```

---

## Task 1: POST /api/v1/leads - Create Lead

**Files:**
- Modify: `backend/src/api/routes/leads.py:68-193` (add after get_lead, before add_note)
- Test: `backend/tests/api/test_leads_route.py:96-` (append to file)

**Step 1: Write the failing test**

Open `backend/tests/api/test_leads_route.py`. Add this test class after `TestListLeads`:

```python
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
        from unittest.mock import patch
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
            mock_instance.create.return_value = mock_lead

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
        from unittest.mock import patch
        from src.memory.lead_memory import LeadMemory, TriggerType, LifecycleStage, LeadStatus
        from datetime import datetime, UTC, date

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
            mock_instance.create.return_value = mock_lead

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestCreateLead::test_create_lead_requires_auth -v`

Expected: FAIL or SKIP (endpoint doesn't exist yet)

**Step 3: Write minimal implementation**

Open `backend/src/api/routes/leads.py`. Add this endpoint after `get_lead` (around line 192):

```python
@router.post("", response_model=LeadMemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_data: LeadMemoryCreate,
    current_user: CurrentUser,
) -> LeadMemoryResponse:
    """Create a new lead.

    Args:
        lead_data: The lead data to create.
        current_user: Current authenticated user.

    Returns:
        The created lead.

    Raises:
        HTTPException: 500 if creation fails.
    """
    from decimal import Decimal
    from src.memory.lead_memory import TriggerType

    try:
        service = LeadMemoryService()

        # Convert expected_value to Decimal if provided
        expected_value = (
            Decimal(str(lead_data.expected_value)) if lead_data.expected_value else None
        )

        lead = await service.create(
            user_id=current_user.id,
            company_name=lead_data.company_name,
            trigger=TriggerType.MANUAL,
            company_id=lead_data.company_id,
            expected_close_date=lead_data.expected_close_date,
            expected_value=expected_value,
            tags=lead_data.tags,
            metadata=lead_data.metadata,
        )

        return _lead_to_response(lead)

    except LeadMemoryError as e:
        logger.exception("Failed to create lead")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

Also add the import at the top of the file (around line 25, add to the existing import):

```python
from src.models.lead_memory import (
    LeadEventCreate,
    LeadEventResponse,
    LeadMemoryCreate,  # ADD THIS
    LeadMemoryResponse,
)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestCreateLead -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/test_leads_route.py
git commit -m "feat(lead-api): add POST /leads endpoint for creating leads"
```

---

## Task 2: PATCH /api/v1/leads/{id} - Update Lead

**Files:**
- Modify: `backend/src/api/routes/leads.py:193-` (add after create_lead)
- Test: `backend/tests/api/test_leads_route.py` (append)

**Step 1: Write the failing test**

Open `backend/tests/api/test_leads_route.py`. Add this test class:

```python
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
        from unittest.mock import AsyncMock, patch
        from src.memory.lead_memory import LeadMemory, LifecycleStage, LeadStatus
        from datetime import datetime, UTC

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

        with patch("src.api.routes.leads.LeadMemoryService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.get_by_id = AsyncMock(return_value=existing_lead)
            mock_instance.update = AsyncMock()
            mock_instance.get_by_id.return_value = LeadMemory(
                id="test-lead-123",
                user_id="test-user-123",
                company_name="Updated Name",
                lifecycle_stage=LifecycleStage.LEAD,
                status=LeadStatus.ACTIVE,
                health_score=75,
                trigger=TriggerType.MANUAL,
                first_touch_at=datetime.now(UTC),
                last_activity_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestUpdateLead::test_update_lead_requires_auth -v`

Expected: FAIL (endpoint doesn't exist)

**Step 3: Write minimal implementation**

Open `backend/src/api/routes/leads.py`. Add this endpoint after `create_lead`:

```python
@router.patch("/{lead_id}", response_model=LeadMemoryResponse)
async def update_lead(
    lead_id: str,
    lead_data: LeadMemoryUpdate,
    current_user: CurrentUser,
) -> LeadMemoryResponse:
    """Update an existing lead.

    Only provided fields will be updated. None values are ignored.

    Args:
        lead_id: The lead ID to update.
        lead_data: The fields to update.
        current_user: Current authenticated user.

    Returns:
        The updated lead.

    Raises:
        HTTPException: 404 if lead not found, 500 if update fails.
    """
    from decimal import Decimal

    try:
        service = LeadMemoryService()

        # Verify lead exists
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Convert expected_value to Decimal if provided
        expected_value = (
            Decimal(str(lead_data.expected_value)) if lead_data.expected_value else None
        )

        # Perform update
        await service.update(
            user_id=current_user.id,
            lead_id=lead_id,
            company_name=lead_data.company_name,
            health_score=lead_data.health_score,
            expected_close_date=lead_data.expected_close_date,
            expected_value=expected_value,
            tags=lead_data.tags,
        )

        # Fetch and return updated lead
        updated_lead = await service.get_by_id(user_id=current_user.id, lead_id=lead_id)
        return _lead_to_response(updated_lead)

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to update lead")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

Add the import:

```python
from src.models.lead_memory import (
    LeadEventCreate,
    LeadEventResponse,
    LeadMemoryCreate,
    LeadMemoryUpdate,  # ADD THIS
    LeadMemoryResponse,
)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestUpdateLead -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/test_leads_route.py
git commit -m "feat(lead-api): add PATCH /leads/{id} endpoint for updating leads"
```

---

## Task 3: POST /api/v1/leads/{id}/events - Add Event

**Files:**
- Modify: `backend/src/api/routes/leads.py` (endpoint already exists, verify and improve if needed)
- Test: `backend/tests/api/test_leads_route.py` (already has auth test, add more)

**Step 1: Add more comprehensive tests**

Open `backend/tests/api/test_leads_route.py`. Update `TestAddNote` class (rename to `TestAddEvent`):

```python
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
        from unittest.mock import AsyncMock, patch
        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import EventType, Direction
        from datetime import datetime, UTC

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

        with patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service, \
             patch("src.api.routes.leads.SupabaseClient") as mock_sb_client, \
             patch("src.api.routes.leads.LeadEventService") as mock_event_service:

            # Mock lead verification
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

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
```

**Step 2: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestAddEvent -v`

Expected: PASS (endpoint already exists)

**Step 3: Commit**

```bash
git add backend/tests/api/test_leads_route.py
git commit -m "test(lead-api): add comprehensive tests for POST /leads/{id}/events"
```

---

## Task 4: POST /api/v1/leads/{id}/stakeholders - Add Stakeholder

**Files:**
- Create: `backend/src/memory/lead_stakeholders.py` (new service)
- Modify: `backend/src/api/routes/leads.py` (add endpoint)
- Test: `backend/tests/api/test_leads_route.py` (add tests)

**Step 1: Write the failing test**

Open `backend/tests/api/test_leads_route.py`. Add this test class:

```python
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
        from unittest.mock import AsyncMock, patch

        with patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service, \
             patch("src.api.routes.leads.SupabaseClient") as mock_sb_client, \
             patch("src.api.routes.leads.LeadStakeholderService") as mock_stakeholder_service:

            # Mock lead verification
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock stakeholder creation
            mock_stakeholder_instance = mock_stakeholder_service.return_value
            mock_stakeholder_instance.add_stakeholder = AsyncMock(return_value="stakeholder-123")

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestAddStakeholder::test_add_stakeholder_requires_auth -v`

Expected: FAIL (endpoint doesn't exist)

**Step 3: Create stakeholder service**

Create file `backend/src/memory/lead_stakeholders.py`:

```python
"""Lead stakeholder tracking for contact mapping.

Stakeholders track individual contacts at a lead company including:
- Contact information (email, name, title)
- Role classification (decision maker, influencer, champion, blocker, user)
- Influence level (1-10)
- Sentiment tracking
- Last contact timestamp

Stored in Supabase with user isolation via RLS.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import Sentiment, StakeholderRole

logger = logging.getLogger(__name__)


@dataclass
class LeadStakeholder:
    """A domain model representing a stakeholder at a lead company.

    Attributes:
        id: Unique identifier for this stakeholder.
        lead_memory_id: ID of the lead memory this stakeholder belongs to.
        contact_email: Primary contact email (unique per lead).
        contact_name: Optional full name.
        title: Optional job title.
        role: Optional role classification.
        influence_level: Influence level 1-10 (default 5).
        sentiment: Current sentiment (default neutral).
        last_contacted_at: Optional timestamp of last contact.
        notes: Optional additional notes.
        created_at: When this stakeholder was created.
    """

    id: str
    lead_memory_id: str
    contact_email: str
    contact_name: str | None
    title: str | None
    role: StakeholderRole | None
    influence_level: int
    sentiment: Sentiment
    last_contacted_at: datetime | None
    notes: str | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize stakeholder to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "contact_email": self.contact_email,
            "contact_name": self.contact_name,
            "title": self.title,
            "role": self.role.value if self.role else None,
            "influence_level": self.influence_level,
            "sentiment": self.sentiment.value,
            "last_contacted_at": self.last_contacted_at.isoformat() if self.last_contacted_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeadStakeholder:
        """Create a LeadStakeholder from a dictionary."""
        # Parse datetime fields
        last_contacted_at = None
        if data.get("last_contacted_at"):
            raw = data["last_contacted_at"]
            last_contacted_at = (
                datetime.fromisoformat(raw) if isinstance(raw, str) else raw
            )

        created_at_raw = data["created_at"]
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if isinstance(created_at_raw, str)
            else created_at_raw
        )

        # Parse enums
        role = None
        if data.get("role"):
            role_raw = data["role"]
            role = (
                StakeholderRole(role_raw)
                if isinstance(role_raw, str)
                else role_raw
            )

        sentiment_raw = data["sentiment"]
        sentiment = (
            Sentiment(sentiment_raw)
            if isinstance(sentiment_raw, str)
            else sentiment_raw
        )

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            contact_email=cast(str, data["contact_email"]),
            contact_name=cast(str | None, data.get("contact_name")),
            title=cast(str | None, data.get("title")),
            role=role,
            influence_level=cast(int, data["influence_level"]),
            sentiment=sentiment,
            last_contacted_at=last_contacted_at,
            notes=cast(str | None, data.get("notes")),
            created_at=created_at,
        )


class LeadStakeholderService:
    """Service for managing lead stakeholder operations.

    Provides async interface for storing, retrieving, and querying
    lead stakeholders. Stored in Supabase with user isolation via RLS.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the stakeholder service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    def _get_supabase_client(self) -> Client:
        """Get the Supabase client instance."""
        from src.core.exceptions import DatabaseError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def add_stakeholder(
        self,
        user_id: str,
        lead_memory_id: str,
        contact_email: str,
        contact_name: str | None = None,
        title: str | None = None,
        role: StakeholderRole | None = None,
        influence_level: int = 5,
        sentiment: Sentiment = Sentiment.NEUTRAL,
        notes: str | None = None,
    ) -> str:
        """Add a new stakeholder to a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            contact_email: Contact email address.
            contact_name: Optional full name.
            title: Optional job title.
            role: Optional role classification.
            influence_level: Influence level 1-10.
            sentiment: Current sentiment.
            notes: Optional additional notes.

        Returns:
            The ID of the created stakeholder.

        Raises:
            DatabaseError: If storage fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "contact_email": contact_email,
                "contact_name": contact_name,
                "title": title,
                "role": role.value if role else None,
                "influence_level": influence_level,
                "sentiment": sentiment.value,
                "last_contacted_at": None,
                "notes": notes,
                "created_at": now.isoformat(),
            }

            response = client.table("lead_stakeholders").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert stakeholder")

            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            stakeholder_id = cast(str, first_record.get("id"))

            if not stakeholder_id:
                raise DatabaseError("Failed to insert stakeholder")

            logger.info(
                "Added lead stakeholder",
                extra={
                    "stakeholder_id": stakeholder_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contact_email": contact_email,
                },
            )

            return stakeholder_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to add lead stakeholder")
            raise DatabaseError(f"Failed to add lead stakeholder: {e}") from e

    async def list_by_lead(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> list[LeadStakeholder]:
        """List all stakeholders for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            List of LeadStakeholder instances.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("lead_stakeholders")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .order("influence_level", desc=True)
                .execute()
            )

            stakeholders = []
            for item in response.data:
                stakeholder_dict = cast(dict[str, Any], item)
                stakeholders.append(LeadStakeholder.from_dict(stakeholder_dict))

            logger.info(
                "Listed lead stakeholders",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "count": len(stakeholders),
                },
            )

            return stakeholders

        except Exception as e:
            logger.exception("Failed to list lead stakeholders")
            raise DatabaseError(f"Failed to list lead stakeholders: {e}") from e
```

**Step 4: Add endpoint to routes**

Open `backend/src/api/routes/leads.py`. Add this endpoint after `add_note`:

```python
@router.post("/{lead_id}/stakeholders", response_model=StakeholderResponse, status_code=status.HTTP_201_CREATED)
async def add_stakeholder(
    lead_id: str,
    stakeholder_data: StakeholderCreate,
    current_user: CurrentUser,
) -> StakeholderResponse:
    """Add a stakeholder to a lead.

    Args:
        lead_id: The lead ID to add stakeholder to.
        stakeholder_data: The stakeholder data.
        current_user: Current authenticated user.

    Returns:
        The created stakeholder.

    Raises:
        HTTPException: 404 if lead not found, 500 if creation fails.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_stakeholders import LeadStakeholderService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Create stakeholder
        client = SupabaseClient.get_client()
        stakeholder_service = LeadStakeholderService(db_client=client)

        stakeholder_id = await stakeholder_service.add_stakeholder(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            contact_email=stakeholder_data.contact_email,
            contact_name=stakeholder_data.contact_name,
            title=stakeholder_data.title,
            role=stakeholder_data.role,
            influence_level=stakeholder_data.influence_level,
            sentiment=stakeholder_data.sentiment,
            notes=stakeholder_data.notes,
        )

        # Retrieve the created stakeholder
        stakeholders = await stakeholder_service.list_by_lead(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        # Find the stakeholder we just created
        created_stakeholder = next((s for s in stakeholders if s.id == stakeholder_id), None)

        if created_stakeholder is None:
            raise LeadMemoryError("Failed to retrieve created stakeholder")

        return StakeholderResponse(
            id=created_stakeholder.id,
            lead_memory_id=created_stakeholder.lead_memory_id,
            contact_email=created_stakeholder.contact_email,
            contact_name=created_stakeholder.contact_name,
            title=created_stakeholder.title,
            role=created_stakeholder.role,
            influence_level=created_stakeholder.influence_level,
            sentiment=created_stakeholder.sentiment,
            last_contacted_at=created_stakeholder.last_contacted_at,
            notes=created_stakeholder.notes,
            created_at=created_stakeholder.created_at,
        )

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to add stakeholder")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

Add imports:

```python
from src.models.lead_memory import (
    LeadEventCreate,
    LeadEventResponse,
    LeadMemoryCreate,
    LeadMemoryUpdate,
    LeadMemoryResponse,
    StakeholderCreate,  # ADD THIS
    StakeholderResponse,  # ADD THIS
)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestAddStakeholder -v`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/memory/lead_stakeholders.py backend/src/api/routes/leads.py backend/tests/api/test_leads_route.py
git commit -m "feat(lead-api): add POST /leads/{id}/stakeholders endpoint with service"
```

---

## Task 5: GET /api/v1/leads/{id}/insights - Get AI Insights

**Files:**
- Create: `backend/src/memory/lead_insights.py` (placeholder service)
- Modify: `backend/src/api/routes/leads.py` (add endpoint)
- Test: `backend/tests/api/test_leads_route.py` (add tests)

**Step 1: Write the failing test**

Open `backend/tests/api/test_leads_route.py`. Add this test class:

```python
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
        from unittest.mock import AsyncMock, patch
        from src.memory.lead_insights import LeadInsight
        from src.models.lead_memory import InsightType
        from datetime import datetime, UTC

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

        with patch("src.api.routes.leads.LeadMemoryService") as mock_lead_service, \
             patch("src.api.routes.leads.SupabaseClient") as mock_sb_client, \
             patch("src.api.routes.leads.LeadInsightsService") as mock_insights_service:

            # Mock lead verification
            mock_lead_instance = mock_lead_service.return_value
            mock_lead_instance.get_by_id = AsyncMock()

            # Mock insights retrieval
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestGetInsights::test_get_insights_requires_auth -v`

Expected: FAIL (endpoint doesn't exist)

**Step 3: Create insights service (placeholder)**

Create file `backend/src/memory/lead_insights.py`:

```python
"""Lead insights for AI-generated observations.

Insights track AI-detected patterns including:
- Buying signals (positive indicators)
- Objections (concerns raised)
- Commitments (promises made)
- Risks (potential deal blockers)
- Opportunities (upsell/cross-sell)

This is a placeholder implementation. Full AI insight generation
will be implemented in US-515.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import InsightType

logger = logging.getLogger(__name__)


@dataclass
class LeadInsight:
    """A domain model representing an AI-generated insight.

    Attributes:
        id: Unique identifier for this insight.
        lead_memory_id: ID of the lead memory this insight belongs to.
        insight_type: Type of insight (buying_signal, objection, etc.).
        content: The insight text.
        confidence: Confidence score 0-1.
        source_event_id: Optional ID of the event that triggered this insight.
        detected_at: When this insight was detected.
        addressed_at: Optional timestamp when this insight was addressed.
    """

    id: str
    lead_memory_id: str
    insight_type: InsightType
    content: str
    confidence: float
    source_event_id: str | None
    detected_at: datetime
    addressed_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize insight to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "insight_type": self.insight_type.value,
            "content": self.content,
            "confidence": self.confidence,
            "source_event_id": self.source_event_id,
            "detected_at": self.detected_at.isoformat(),
            "addressed_at": self.addressed_at.isoformat() if self.addressed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeadInsight:
        """Create a LeadInsight from a dictionary."""
        # Parse datetime fields
        detected_at_raw = data["detected_at"]
        detected_at = (
            datetime.fromisoformat(detected_at_raw)
            if isinstance(detected_at_raw, str)
            else detected_at_raw
        )

        addressed_at = None
        if data.get("addressed_at"):
            addressed_at_raw = data["addressed_at"]
            addressed_at = (
                datetime.fromisoformat(addressed_at_raw)
                if isinstance(addressed_at_raw, str)
                else addressed_at_raw
            )

        # Parse insight_type
        insight_type_raw = data["insight_type"]
        insight_type = (
            InsightType(insight_type_raw)
            if isinstance(insight_type_raw, str)
            else insight_type_raw
        )

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            insight_type=insight_type,
            content=cast(str, data["content"]),
            confidence=cast(float, data["confidence"]),
            source_event_id=cast(str | None, data.get("source_event_id")),
            detected_at=detected_at,
            addressed_at=addressed_at,
        )


class LeadInsightsService:
    """Service for managing lead insights.

    This is a placeholder implementation. Full AI insight generation
    will be implemented in US-515 (AI-Powered Health Scoring).

    For now, returns empty list and provides structure for future implementation.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the insights service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    def _get_supabase_client(self) -> Client:
        """Get the Supabase client instance."""
        from src.core.exceptions import DatabaseError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def get_insights(
        self,
        user_id: str,
        lead_memory_id: str,
        insight_type: InsightType | None = None,
        include_addressed: bool = False,
    ) -> list[LeadInsight]:
        """Get insights for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            insight_type: Optional filter by insight type.
            include_addressed: Whether to include addressed insights.

        Returns:
            List of LeadInsight instances ordered by detected_at descending.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            query = (
                client.table("lead_insights")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
            )

            if insight_type:
                query = query.eq("insight_type", insight_type.value)

            if not include_addressed:
                query = query.is_("addressed_at", "null")

            query = query.order("detected_at", desc=True)

            response = query.execute()

            insights = []
            for item in response.data:
                insight_dict = cast(dict[str, Any], item)
                insights.append(LeadInsight.from_dict(insight_dict))

            logger.info(
                "Retrieved lead insights",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "count": len(insights),
                },
            )

            return insights

        except Exception as e:
            logger.exception("Failed to get lead insights")
            raise DatabaseError(f"Failed to get lead insights: {e}") from e

    async def create_insight(
        self,
        user_id: str,
        lead_memory_id: str,
        insight_type: InsightType,
        content: str,
        confidence: float = 0.7,
        source_event_id: str | None = None,
    ) -> str:
        """Create a new insight.

        TODO: Implement in US-515 with AI-powered insight generation.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            insight_type: Type of insight.
            content: The insight text.
            confidence: Confidence score 0-1.
            source_event_id: Optional source event ID.

        Returns:
            The ID of the created insight.

        Raises:
            DatabaseError: If creation fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "insight_type": insight_type.value,
                "content": content,
                "confidence": confidence,
                "source_event_id": source_event_id,
                "detected_at": now.isoformat(),
                "addressed_at": None,
            }

            response = client.table("lead_insights").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert insight")

            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            insight_id = cast(str, first_record.get("id"))

            logger.info(
                "Created lead insight",
                extra={
                    "insight_id": insight_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "insight_type": insight_type.value,
                },
            )

            return insight_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to create lead insight")
            raise DatabaseError(f"Failed to create lead insight: {e}") from e
```

**Step 4: Add endpoint to routes**

Open `backend/src/api/routes/leads.py`. Add this endpoint after `add_stakeholder`:

```python
@router.get("/{lead_id}/insights", response_model=list[InsightResponse])
async def get_insights(
    lead_id: str,
    current_user: CurrentUser,
    insight_type: str | None = Query(None, description="Filter by insight type"),
    include_addressed: bool = Query(False, description="Include addressed insights"),
) -> list[InsightResponse]:
    """Get AI insights for a lead.

    Args:
        lead_id: The lead ID to get insights for.
        current_user: Current authenticated user.
        insight_type: Optional filter by insight type.
        include_addressed: Whether to include addressed insights.

    Returns:
        List of insights for the lead.

    Raises:
        HTTPException: 404 if lead not found, 500 if retrieval fails.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_insights import LeadInsightsService
    from src.models.lead_memory import InsightType

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Parse insight type filter
        insight_type_filter = None
        if insight_type:
            try:
                insight_type_filter = InsightType(insight_type)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid insight type: {insight_type}",
                ) from e

        # Get insights
        client = SupabaseClient.get_client()
        insights_service = LeadInsightsService(db_client=client)

        insights = await insights_service.get_insights(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            insight_type=insight_type_filter,
            include_addressed=include_addressed,
        )

        return [
            InsightResponse(
                id=insight.id,
                lead_memory_id=insight.lead_memory_id,
                insight_type=insight.insight_type,
                content=insight.content,
                confidence=insight.confidence,
                source_event_id=insight.source_event_id,
                detected_at=insight.detected_at,
                addressed_at=insight.addressed_at,
            )
            for insight in insights
        ]

    except HTTPException:
        raise
    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to get insights")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

Add imports:

```python
from src.models.lead_memory import (
    # ... existing imports ...
    InsightCreate,  # ADD THIS
    InsightResponse,  # ADD THIS
    InsightType,  # ADD THIS
)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestGetInsights -v`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/memory/lead_insights.py backend/src/api/routes/leads.py backend/tests/api/test_leads_route.py
git commit -m "feat(lead-api): add GET /leads/{id}/insights endpoint with placeholder service"
```

---

## Task 6: POST /api/v1/leads/{id}/transition - Change Lifecycle Stage

**Files:**
- Modify: `backend/src/api/routes/leads.py` (add endpoint)
- Test: `backend/tests/api/test_leads_route.py` (add tests)

**Step 1: Write the failing test**

Open `backend/tests/api/test_leads_route.py`. Add this test class:

```python
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
        from unittest.mock import AsyncMock, patch
        from src.memory.lead_memory import LeadMemory, LifecycleStage, LeadStatus
        from datetime import datetime, UTC

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestTransitionStage::test_transition_stage_requires_auth -v`

Expected: FAIL (endpoint doesn't exist)

**Step 3: Create schema for transition request**

Open `backend/src/models/lead_memory.py`. Add this at the end of the file (before existing schemas):

```python
# Transition Request
class StageTransitionRequest(BaseModel):
    stage: LifecycleStage = Field(..., description="Target lifecycle stage")
```

**Step 4: Add endpoint to routes**

Open `backend/src/api/routes/leads.py`. Add this endpoint after `get_insights`:

```python
@router.post("/{lead_id}/transition", response_model=LeadMemoryResponse)
async def transition_stage(
    lead_id: str,
    transition: StageTransitionRequest,
    current_user: CurrentUser,
) -> LeadMemoryResponse:
    """Transition a lead to a new lifecycle stage.

    Stages can only progress forward: lead -> opportunity -> account.

    Args:
        lead_id: The lead ID to transition.
        transition: The transition request with target stage.
        current_user: Current authenticated user.

    Returns:
        The updated lead.

    Raises:
        HTTPException: 400 if invalid transition, 404 if lead not found,
                      500 if transition fails.
    """
    from src.models.lead_memory import StageTransitionRequest

    try:
        service = LeadMemoryService()

        # Perform transition
        await service.transition_stage(
            user_id=current_user.id,
            lead_id=lead_id,
            new_stage=transition.stage,
        )

        # Fetch and return updated lead
        updated_lead = await service.get_by_id(user_id=current_user.id, lead_id=lead_id)
        return _lead_to_response(updated_lead)

    except InvalidStageTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to transition stage")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

Add imports:

```python
from src.core.exceptions import (
    LeadMemoryError,
    LeadNotFoundError,
    InvalidStageTransitionError,  # ADD THIS
)
```

Also add the schema import:

```python
from src.models.lead_memory import (
    # ... existing imports ...
    StageTransitionRequest,  # ADD THIS
)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_leads_route.py::TestTransitionStage -v`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/models/lead_memory.py backend/src/api/routes/leads.py backend/tests/api/test_leads_route.py
git commit -m "feat(lead-api): add POST /leads/{id}/transition endpoint for stage changes"
```

---

## Final Verification

**Step 1: Run all tests**

Run: `cd backend && pytest tests/api/test_leads_route.py -v`

Expected: All tests PASS

**Step 2: Run type checks**

Run: `cd backend && mypy src/api/routes/leads.py --strict`

Expected: No errors

**Step 3: Run linter**

Run: `cd backend && ruff check src/api/routes/leads.py`

Expected: No errors

**Step 4: Final commit if all checks pass**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/test_leads_route.py
git commit -m "test(lead-api): ensure all lead API endpoints pass quality gates"
```

---

## Summary of New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/leads` | Create new lead |
| PATCH | `/api/v1/leads/{id}` | Update lead fields |
| POST | `/api/v1/leads/{id}/events` | Add event to timeline (already existed as /notes) |
| POST | `/api/v1/leads/{id}/stakeholders` | Add stakeholder to lead |
| GET | `/api/v1/leads/{id}/insights` | Get AI insights for lead |
| POST | `/api/v1/leads/{id}/transition` | Change lifecycle stage |

## New Services Created

1. `LeadStakeholderService` in `src/memory/lead_stakeholders.py`
2. `LeadInsightsService` in `src/memory/lead_insights.py` (placeholder for US-515)

## Database Tables Required (must exist via migrations)

- `lead_stakeholders` - Stakeholder records
- `lead_insights` - AI-generated insights

If these tables don't exist, create migrations:
```bash
supabase migration new create_lead_stakeholders_and_insights
```
