# Multi-User Collaboration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build multi-user collaboration for lead memory with owner approval workflow and audit trail.

**Architecture:**
- Service layer (`LeadCollaborationService`) managing contributions in Supabase
- Domain models for Contribution and Contributor entities
- API routes exposing REST endpoints for contributors and contributions
- Notification integration for owner alerts on new contributions
- RLS-based user isolation with cross-user access for contributors

**Tech Stack:**
- Python 3.11+ / FastAPI for API
- Supabase (PostgreSQL) for storage
- Pydantic for request/response models
- pytest for testing

---

## Task 1: Add contribution-related enums to models

**Files:**
- Modify: `backend/src/models/lead_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/api/routes/test_leads.py`:

```python
def test_contribution_type_enum_exists():
    """Test ContributionType enum has correct values."""
    from src.models.lead_memory import ContributionType

    assert ContributionType.EVENT.value == "event"
    assert ContributionType.NOTE.value == "note"
    assert ContributionType.INSIGHT.value == "insight"
    assert len(ContributionType) == 3

def test_contribution_status_enum_exists():
    """Test ContributionStatus enum has correct values."""
    from src.models.lead_memory import ContributionStatus

    assert ContributionStatus.PENDING.value == "pending"
    assert ContributionStatus.MERGED.value == "merged"
    assert ContributionStatus.REJECTED.value == "rejected"
    assert len(ContributionStatus) == 3
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/api/routes/test_leads.py::test_contribution_type_enum_exists -v
```

Expected: FAIL with `ImportError: cannot import name 'ContributionType'`

**Step 3: Write minimal implementation**

Add to `backend/src/models/lead_memory.py` after line 55 (after InsightType):

```python
class ContributionType(str, Enum):
    """Type of contribution to a lead."""
    EVENT = "event"
    NOTE = "note"
    INSIGHT = "insight"


class ContributionStatus(str, Enum):
    """Status of a contribution in review workflow."""
    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/api/routes/test_leads.py::test_contribution_type_enum_exists tests/api/routes/test_leads.py::test_contribution_status_enum_exists -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/lead_memory.py backend/tests/api/routes/test_leads.py
git commit -m "feat(lead-collab): add ContributionType and ContributionStatus enums"
```

---

## Task 2: Add Pydantic models for contributions and contributors

**Files:**
- Modify: `backend/src/models/lead_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/api/routes/test_leads.py`:

```python
def test_contributor_create_model():
    """Test ContributorCreate model exists and validates."""
    from src.models.lead_memory import ContributorCreate

    contributor = ContributorCreate(
        contributor_id="user-123",
        contributor_name="Jane Doe",
        contributor_email="jane@example.com"
    )

    assert contributor.contributor_id == "user-123"
    assert contributor.contributor_name == "Jane Doe"
    assert contributor.contributor_email == "jane@example.com"

def test_contribution_create_model():
    """Test ContributionCreate model exists and validates."""
    from src.models.lead_memory import ContributionCreate, ContributionType

    contribution = ContributionCreate(
        contribution_type=ContributionType.NOTE,
        content="Met with CTO, interested in pilot"
    )

    assert contribution.contribution_type == ContributionType.NOTE
    assert contribution.content == "Met with CT0, interested in pilot"

def test_contribution_response_model():
    """Test ContributionResponse model exists and has correct fields."""
    from src.models.lead_memory import ContributionResponse, ContributionType, ContributionStatus

    # Create with all fields
    response = ContributionResponse(
        id="contrib-123",
        lead_memory_id="lead-456",
        contributor_id="user-789",
        contributor_name="Jane Doe",
        contribution_type=ContributionType.EVENT,
        contribution_id="event-abc",
        status=ContributionStatus.PENDING,
        created_at="2026-02-04T10:00:00Z",
        reviewed_at=None,
        reviewed_by=None
    )

    assert response.id == "contrib-123"
    assert response.lead_memory_id == "lead-456"
    assert response.contributor_id == "user-789"
    assert response.contributor_name == "Jane Doe"
    assert response.contribution_type == ContributionType.EVENT
    assert response.status == ContributionStatus.PENDING

def test_contributor_response_model():
    """Test ContributorResponse model exists and has correct fields."""
    from src.models.lead_memory import ContributorResponse

    contributor = ContributorResponse(
        id="user-123",
        lead_memory_id="lead-456",
        name="Jane Doe",
        email="jane@example.com",
        added_at="2026-02-04T10:00:00Z",
        contribution_count=5
    )

    assert contributor.id == "user-123"
    assert contributor.name == "Jane Doe"
    assert contributor.contribution_count == 5
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/api/routes/test_leads.py::test_contributor_create_model -v
```

Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `backend/src/models/lead_memory.py` after line 178 (after StageTransitionRequest):

```python
# Contributor Models
class ContributorCreate(BaseModel):
    """Request model for adding a contributor to a lead."""
    contributor_id: str = Field(..., description="User ID to add as contributor")
    contributor_name: str = Field(..., description="Full name of contributor")
    contributor_email: str = Field(..., description="Email of contributor")


class ContributorResponse(BaseModel):
    """Response model for a contributor on a lead."""
    id: str = Field(..., description="Contributor user ID")
    lead_memory_id: str = Field(..., description="Lead memory ID")
    name: str = Field(..., description="Contributor full name")
    email: str = Field(..., description="Contributor email")
    added_at: datetime = Field(..., description="When contributor was added")
    contribution_count: int = Field(..., description="Number of contributions by this user")


# Contribution Models
class ContributionCreate(BaseModel):
    """Request model for submitting a contribution."""
    contribution_type: ContributionType = Field(..., description="Type of contribution")
    contribution_id: str | None = Field(None, description="ID of the event/note/insight being contributed")
    content: str | None = Field(None, description="Content for note/insight contributions")


class ContributionResponse(BaseModel):
    """Response model for a contribution."""
    id: str = Field(..., description="Contribution ID")
    lead_memory_id: str = Field(..., description="Lead memory ID")
    contributor_id: str = Field(..., description="Contributor user ID")
    contributor_name: str = Field(..., description="Contributor full name")
    contribution_type: ContributionType = Field(..., description="Type of contribution")
    contribution_id: str | None = Field(None, description="ID of contributed item")
    content: str | None = Field(None, description="Content of contribution")
    status: ContributionStatus = Field(..., description="Review status")
    created_at: datetime = Field(..., description="When contribution was submitted")
    reviewed_at: datetime | None = Field(None, description="When contribution was reviewed")
    reviewed_by: str | None = Field(None, description="User ID who reviewed")


class ContributionReviewRequest(BaseModel):
    """Request model for reviewing a contribution."""
    action: str = Field(..., description="Action: 'merge' or 'reject'")
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/api/routes/test_leads.py::test_contributor_create_model \
  tests/api/routes/test_leads.py::test_contribution_create_model \
  tests/api/routes/test_leads.py::test_contribution_response_model \
  tests/api/routes/test_leads.py::test_contributor_response_model -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/lead_memory.py backend/tests/api/routes/test_leads.py
git commit -m "feat(lead-collab): add Pydantic models for contributions and contributors"
```

---

## Task 3: Create LeadCollaborationService with domain models

**Files:**
- Create: `backend/src/services/lead_collaboration.py`

**Step 1: Write the failing test**

Create `backend/tests/services/test_lead_collaboration.py`:

```python
"""Tests for LeadCollaborationService."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


class TestContributionDataclass:
    """Tests for the Contribution dataclass."""

    def test_contribution_creation_all_fields(self):
        """Test creating Contribution with all fields."""
        from src.services.lead_collaboration import Contribution, ContributionStatus, ContributionType

        created_at = datetime(2026, 2, 4, 10, 0, tzinfo=UTC)

        contribution = Contribution(
            id="contrib-123",
            lead_memory_id="lead-456",
            contributor_id="user-789",
            contribution_type=ContributionType.NOTE,
            contribution_id=None,
            status=ContributionStatus.PENDING,
            reviewed_by=None,
            reviewed_at=None,
            created_at=created_at
        )

        assert contribution.id == "contrib-123"
        assert contribution.lead_memory_id == "lead-456"
        assert contribution.contributor_id == "user-789"
        assert contribution.contribution_type == ContributionType.NOTE
        assert contribution.status == ContributionStatus.PENDING

    def test_contribution_to_dict(self):
        """Test serialization to dict."""
        from src.services.lead_collaboration import Contribution, ContributionStatus, ContributionType

        created_at = datetime(2026, 2, 4, 10, 0, tzinfo=UTC)

        contribution = Contribution(
            id="contrib-123",
            lead_memory_id="lead-456",
            contributor_id="user-789",
            contribution_type=ContributionType.INSIGHT,
            contribution_id=None,
            status=ContributionStatus.PENDING,
            reviewed_by=None,
            reviewed_at=None,
            created_at=created_at
        )

        result = contribution.to_dict()

        assert result["id"] == "contrib-123"
        assert result["contribution_type"] == "insight"
        assert result["status"] == "pending"

    def test_contribution_from_dict(self):
        """Test deserialization from dict."""
        from src.services.lead_collaboration import Contribution

        data = {
            "id": "contrib-123",
            "lead_memory_id": "lead-456",
            "contributor_id": "user-789",
            "contribution_type": "event",
            "contribution_id": "event-abc",
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": "2026-02-04T10:00:00+00:00"
        }

        contribution = Contribution.from_dict(data)

        assert contribution.id == "contrib-123"
        assert contribution.contribution_type.value == "event"


class TestLeadCollaborationServiceInit:
    """Tests for LeadCollaborationService initialization."""

    def test_service_initialization(self):
        """Test service can be instantiated with db client."""
        from src.services.lead_collaboration import LeadCollaborationService

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        assert service is not None
        assert service.db == mock_client
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `backend/src/services/lead_collaboration.py`:

```python
"""Lead collaboration service for multi-user contributions.

This service enables team members to contribute to shared leads with
an owner approval workflow. Contributions are flagged for review and
can be merged or rejected by the lead owner.

Contribution types:
- event: Timeline events (meetings, calls, emails)
- note: Text notes added to the lead
- insight: AI-derived insights about the lead

Stored in Supabase with user isolation via RLS.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import ContributionStatus as ModelContributionStatus
from src.models.lead_memory import ContributionType as ModelContributionType

logger = logging.getLogger(__name__)


# Internal enums for domain model (duplicate of models, kept for isolation)
class ContributionStatus(str, Enum):
    """Status of a contribution in review workflow."""
    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"


class ContributionType(str, Enum):
    """Type of contribution to a lead."""
    EVENT = "event"
    NOTE = "note"
    INSIGHT = "insight"


@dataclass
class Contribution:
    """A domain model representing a contribution to a lead.

    Attributes:
        id: Unique identifier for this contribution.
        lead_memory_id: ID of the lead this contributes to.
        contributor_id: User ID of the contributor.
        contribution_type: Type of contribution (event, note, insight).
        contribution_id: Optional ID of the contributed item.
        status: Review status (pending, merged, rejected).
        reviewed_by: Optional user ID of the reviewer.
        reviewed_at: Optional timestamp of review.
        created_at: When this contribution was created.
    """

    id: str
    lead_memory_id: str
    contributor_id: str
    contribution_type: ContributionType
    contribution_id: str | None
    status: ContributionStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize contribution to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "contributor_id": self.contributor_id,
            "contribution_type": self.contribution_type.value,
            "contribution_id": self.contribution_id,
            "status": self.status.value,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contribution":
        """Create a Contribution from a dictionary."""
        created_at_raw = data["created_at"]
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if isinstance(created_at_raw, str)
            else created_at_raw
        )

        reviewed_at = None
        if data.get("reviewed_at"):
            raw = data["reviewed_at"]
            reviewed_at = datetime.fromisoformat(raw) if isinstance(raw, str) else raw

        contribution_type_raw = data["contribution_type"]
        contribution_type = (
            ContributionType(contribution_type_raw)
            if isinstance(contribution_type_raw, str)
            else contribution_type_raw
        )

        status_raw = data["status"]
        status = (
            ContributionStatus(status_raw)
            if isinstance(status_raw, str)
            else status_raw
        )

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            contributor_id=cast(str, data["contributor_id"]),
            contribution_type=contribution_type,
            contribution_id=cast(str | None, data.get("contribution_id")),
            status=status,
            reviewed_by=cast(str | None, data.get("reviewed_by")),
            reviewed_at=reviewed_at,
            created_at=created_at,
        )


@dataclass
class Contributor:
    """A domain model representing a contributor to a lead.

    Attributes:
        id: User ID of the contributor.
        lead_memory_id: ID of the lead.
        name: Full name of the contributor.
        email: Email of the contributor.
        added_at: When this contributor was added.
        contribution_count: Number of contributions by this user.
    """

    id: str
    lead_memory_id: str
    name: str
    email: str
    added_at: datetime
    contribution_count: int


class LeadCollaborationService:
    """Service for managing lead collaboration operations.

    Provides async interface for:
    - Adding contributors to leads
    - Submitting contributions for review
    - Reviewing and merging/rejecting contributions
    - Listing contributors and pending contributions

    Stored in Supabase with user isolation via RLS.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the collaboration service.

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
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestContributionDataclass -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/lead_collaboration.py backend/tests/services/test_lead_collaboration.py
git commit -m "feat(lead-collab): add LeadCollaborationService with domain models"
```

---

## Task 4: Implement add_contributor method

**Files:**
- Modify: `backend/src/services/lead_collaboration.py`
- Modify: `backend/tests/services/test_lead_collaboration.py`

**Step 1: Write the failing test**

Add to `backend/tests/services/test_lead_collaboration.py`:

```python
class TestAddContributor:
    """Tests for add_contributor method."""

    @pytest.mark.asyncio
    async def test_add_contributor_creates_record(self):
        """Test adding a contributor creates database record."""
        from src.services.lead_collaboration import LeadCollaborationService
        from unittest.mock import AsyncMock

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        # Mock response - adding a contributor doesn't have a separate table
        # Contributors are tracked via lead_memory_contributions
        mock_response = MagicMock()
        mock_response.data = []

        mock_query = MagicMock()
        mock_query.insert.return_value.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            # First contribution by this user adds them as contributor
            contribution_id = await service.add_contributor(
                user_id="owner-123",
                lead_memory_id="lead-456",
                contributor_id="contributor-789"
            )

            # The method returns the contributor_id (no separate table)
            assert contribution_id == "contributor-789"

    @pytest.mark.asyncio
    async def test_add_contributor_handles_database_error(self):
        """Test add_contributor wraps database errors."""
        from src.services.lead_collaboration import LeadCollaborationService
        from src.core.exceptions import DatabaseError

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)
        mock_client.table.side_effect = Exception("Connection failed")

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with pytest.raises(DatabaseError):
                await service.add_contributor(
                    user_id="owner-123",
                    lead_memory_id="lead-456",
                    contributor_id="contributor-789"
                )
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestAddContributor -v
```

Expected: FAIL with `AttributeError`

**Step 3: Write minimal implementation**

Add to `LeadCollaborationService` class in `backend/src/services/lead_collaboration.py`:

```python
    async def add_contributor(
        self,
        user_id: str,
        lead_memory_id: str,
        contributor_id: str,
    ) -> str:
        """Add a contributor to a lead.

        Note: Contributors are implicitly added when they make their first
        contribution. This method exists for explicit addition and validation.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            contributor_id: User ID to add as contributor.

        Returns:
            The contributor_id that was added.

        Raises:
            DatabaseError: If operation fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            # Check if contributor already has contributions to this lead
            response = (
                client.table("lead_memory_contributions")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .eq("contributor_id", contributor_id)
                .execute()
            )

            # Contributors are tracked via their contributions
            # No separate table - return the contributor_id
            logger.info(
                "Contributor added to lead",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contributor_id": contributor_id,
                    "existing_contributions": len(response.data or []),
                },
            )

            return contributor_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to add contributor")
            raise DatabaseError(f"Failed to add contributor: {e}") from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestAddContributor -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/lead_collaboration.py backend/tests/services/test_lead_collaboration.py
git commit -m "feat(lead-collab): add add_contributor method"
```

---

## Task 5: Implement submit_contribution method

**Files:**
- Modify: `backend/src/services/lead_collaboration.py`
- Modify: `backend/tests/services/test_lead_collaboration.py`

**Step 1: Write the failing test**

Add to `backend/tests/services/test_lead_collaboration.py`:

```python
class TestSubmitContribution:
    """Tests for submit_contribution method."""

    @pytest.mark.asyncio
    async def test_submit_note_contribution(self):
        """Test submitting a note contribution."""
        from src.services.lead_collaboration import LeadCollaborationService, ContributionType

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        now = datetime(2026, 2, 4, 10, 0, tzinfo=UTC)
        mock_response = MagicMock()
        mock_response.data = [{
            "id": "contrib-123",
            "created_at": now.isoformat()
        }]

        mock_query = MagicMock()
        mock_query.insert.return_value.execute.return_value = mock_response
        mock_client.table.return_value.insert.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            contribution_id = await service.submit_contribution(
                user_id="contributor-789",
                lead_memory_id="lead-456",
                contribution_type=ContributionType.NOTE,
                content="Met with CTO, very interested"
            )

            assert contribution_id == "contrib-123"

    @pytest.mark.asyncio
    async def test_submit_event_contribution_with_id(self):
        """Test submitting an event contribution with existing event ID."""
        from src.services.lead_collaboration import LeadCollaborationService, ContributionType

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [{"id": "contrib-456"}]

        mock_query = MagicMock()
        mock_query.insert.return_value.execute.return_value = mock_response
        mock_client.table.return_value.insert.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            contribution_id = await service.submit_contribution(
                user_id="contributor-789",
                lead_memory_id="lead-456",
                contribution_type=ContributionType.EVENT,
                contribution_id="event-abc123"
            )

            assert contribution_id == "contrib-456"

    @pytest.mark.asyncio
    async def test_submit_contribution_handles_database_error(self):
        """Test submit_contribution wraps database errors."""
        from src.services.lead_collaboration import LeadCollaborationService, ContributionType
        from src.core.exceptions import DatabaseError

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)
        mock_client.table.side_effect = Exception("Connection failed")

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with pytest.raises(DatabaseError):
                await service.submit_contribution(
                    user_id="contributor-789",
                    lead_memory_id="lead-456",
                    contribution_type=ContributionType.NOTE,
                    content="Test note"
                )
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestSubmitContribution -v
```

Expected: FAIL with `AttributeError`

**Step 3: Write minimal implementation**

Add to `LeadCollaborationService` class:

```python
    async def submit_contribution(
        self,
        user_id: str,
        lead_memory_id: str,
        contribution_type: ContributionType,
        contribution_id: str | None = None,
        content: str | None = None,
    ) -> str:
        """Submit a contribution to a lead for owner review.

        Args:
            user_id: The user submitting the contribution.
            lead_memory_id: The lead memory ID.
            contribution_type: Type of contribution (event, note, insight).
            contribution_id: Optional ID of existing event/note/insight.
            content: Optional content for note/insight contributions.

        Returns:
            The ID of the created contribution record.

        Raises:
            DatabaseError: If submission fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "contributor_id": user_id,
                "contribution_type": contribution_type.value,
                "contribution_id": contribution_id,
                "status": ContributionStatus.PENDING.value,
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": now.isoformat(),
            }

            response = client.table("lead_memory_contributions").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert contribution")

            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            new_contribution_id = cast(str, first_record.get("id"))

            if not new_contribution_id:
                raise DatabaseError("Failed to insert contribution")

            logger.info(
                "Contribution submitted",
                extra={
                    "contribution_id": new_contribution_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contribution_type": contribution_type.value,
                },
            )

            return new_contribution_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to submit contribution")
            raise DatabaseError(f"Failed to submit contribution: {e}") from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestSubmitContribution -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/lead_collaboration.py backend/tests/services/test_lead_collaboration.py
git commit -m "feat(lead-collab): add submit_contribution method"
```

---

## Task 6: Implement get_pending_contributions method

**Files:**
- Modify: `backend/src/services/lead_collaboration.py`
- Modify: `backend/tests/services/test_lead_collaboration.py`

**Step 1: Write the failing test**

Add to `backend/tests/services/test_lead_collaboration.py`:

```python
class TestGetPendingContributions:
    """Tests for get_pending_contributions method."""

    @pytest.mark.asyncio
    async def test_get_pending_contributions_returns_list(self):
        """Test getting pending contributions for a lead."""
        from src.services.lead_collaboration import LeadCollaborationService

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "contrib-1",
                "lead_memory_id": "lead-456",
                "contributor_id": "user-789",
                "contribution_type": "note",
                "contribution_id": None,
                "status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": "2026-02-04T10:00:00+00:00"
            }
        ]

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            contributions = await service.get_pending_contributions(
                user_id="owner-123",
                lead_memory_id="lead-456"
            )

            assert len(contributions) == 1
            assert contributions[0].id == "contrib-1"
            assert contributions[0].status == ContributionStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_pending_contributions_empty(self):
        """Test getting pending contributions when none exist."""
        from src.services.lead_collaboration import LeadCollaborationService

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = []

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            contributions = await service.get_pending_contributions(
                user_id="owner-123",
                lead_memory_id="lead-456"
            )

            assert contributions == []
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestGetPendingContributions -v
```

Expected: FAIL with `AttributeError`

**Step 3: Write minimal implementation**

Add to `LeadCollaborationService` class:

```python
    async def get_pending_contributions(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> list[Contribution]:
        """Get pending contributions for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            List of pending Contribution instances, sorted by created_at descending.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            query = (
                client.table("lead_memory_contributions")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .eq("status", ContributionStatus.PENDING.value)
                .order("created_at", desc=True)
            )

            response = query.execute()

            contributions = []
            for item in response.data:
                contribution_dict = cast(dict[str, Any], item)
                contributions.append(Contribution.from_dict(contribution_dict))

            logger.info(
                "Retrieved pending contributions",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "count": len(contributions),
                },
            )

            return contributions

        except Exception as e:
            logger.exception("Failed to get pending contributions")
            raise DatabaseError(f"Failed to get pending contributions: {e}") from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestGetPendingContributions -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/lead_collaboration.py backend/tests/services/test_lead_collaboration.py
git commit -m "feat(lead-collab): add get_pending_contributions method"
```

---

## Task 7: Implement review_contribution method

**Files:**
- Modify: `backend/src/services/lead_collaboration.py`
- Modify: `backend/tests/services/test_lead_collaboration.py`

**Step 1: Write the failing test**

Add to `backend/tests/services/test_lead_collaboration.py`:

```python
class TestReviewContribution:
    """Tests for review_contribution method."""

    @pytest.mark.asyncio
    async def test_review_merge_contribution(self):
        """Test reviewing and merging a contribution."""
        from src.services.lead_collaboration import LeadCollaborationService

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [{"id": "contrib-123"}]

        mock_query = MagicMock()
        mock_query.update.return_value.eq.return_value.execute.return_value = mock_response
        mock_client.table.return_value.update.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            await service.review_contribution(
                user_id="owner-123",
                contribution_id="contrib-123",
                action="merge"
            )

    @pytest.mark.asyncio
    async def test_review_reject_contribution(self):
        """Test reviewing and rejecting a contribution."""
        from src.services.lead_collaboration.py import LeadCollaborationService

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [{"id": "contrib-123"}]

        mock_query = MagicMock()
        mock_query.update.return_value.eq.return_value.execute.return_value = mock_response
        mock_client.table.return_value.update.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            await service.review_contribution(
                user_id="owner-123",
                contribution_id="contrib-123",
                action="reject"
            )

    @pytest.mark.asyncio
    async def test_review_invalid_action_raises(self):
        """Test invalid review action raises error."""
        from src.services.lead_collaboration import LeadCollaborationService
        from src.core.exceptions import ValidationError

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with pytest.raises(ValidationError):
                await service.review_contribution(
                    user_id="owner-123",
                    contribution_id="contrib-123",
                    action="invalid"
                )
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestReviewContribution -v
```

Expected: FAIL with `AttributeError`

**Step 3: Write minimal implementation**

Add to `LeadCollaborationService` class:

```python
    async def review_contribution(
        self,
        user_id: str,
        contribution_id: str,
        action: str,
    ) -> None:
        """Review a contribution (merge or reject).

        Args:
            user_id: The user reviewing the contribution (lead owner).
            contribution_id: The contribution ID to review.
            action: Action to take - "merge" or "reject".

        Raises:
            ValidationError: If action is invalid.
            DatabaseError: If review fails.
        """
        from src.core.exceptions import DatabaseError, ValidationError

        # Validate action
        if action not in ("merge", "reject"):
            raise ValidationError(
                f"Invalid action: {action}. Must be 'merge' or 'reject'.",
                field="action"
            )

        # Map action to status
        status = ContributionStatus.MERGED if action == "merge" else ContributionStatus.REJECTED

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            update_data = {
                "status": status.value,
                "reviewed_by": user_id,
                "reviewed_at": now.isoformat(),
            }

            response = (
                client.table("lead_memory_contributions")
                .update(update_data)
                .eq("id", contribution_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise DatabaseError(f"Contribution {contribution_id} not found")

            logger.info(
                "Contribution reviewed",
                extra={
                    "contribution_id": contribution_id,
                    "user_id": user_id,
                    "action": action,
                    "status": status.value,
                },
            )

        except ValidationError:
            raise
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to review contribution")
            raise DatabaseError(f"Failed to review contribution: {e}") from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestReviewContribution -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/lead_collaboration.py backend/tests/services/test_lead_collaboration.py
git commit -m "feat(lead-collab): add review_contribution method"
```

---

## Task 8: Implement get_contributors method

**Files:**
- Modify: `backend/src/services/lead_collaboration.py`
- Modify: `backend/tests/services/test_lead_collaboration.py`

**Step 1: Write the failing test**

Add to `backend/tests/services/test_lead_collaboration.py`:

```python
class TestGetContributors:
    """Tests for get_contributors method."""

    @pytest.mark.asyncio
    async def test_get_contributors_returns_list(self):
        """Test getting contributors for a lead."""
        from src.services.lead_collaboration import LeadCollaborationService

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        # Mock contributions - we need to aggregate unique contributors
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "contrib-1",
                "contributor_id": "user-789",
                "created_at": "2026-02-04T10:00:00+00:00"
            },
            {
                "id": "contrib-2",
                "contributor_id": "user-789",
                "created_at": "2026-02-04T11:00:00+00:00"
            },
            {
                "id": "contrib-3",
                "contributor_id": "user-999",
                "created_at": "2026-02-04T12:00:00+00:00"
            }
        ]

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        # Mock user profiles for getting names
        mock_user_response = MagicMock()
        mock_user_response.data = [
            {"id": "user-789", "full_name": "Jane Doe", "email": "jane@example.com"},
            {"id": "user-999", "full_name": "Bob Smith", "email": "bob@example.com"}
        ]

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with patch("src.services.lead_collaboration.SupabaseClient") as MockSupabase:
                mock_sb = MagicMock()
                mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_user_response
                MockSupabase.get_client.return_value = mock_sb

                contributors = await service.get_contributors(
                    user_id="owner-123",
                    lead_memory_id="lead-456"
                )

                assert len(contributors) == 2
                # Should have contribution counts
                assert contributors[0].contribution_count == 2
                assert contributors[1].contribution_count == 1
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestGetContributors -v
```

Expected: FAIL with `AttributeError`

**Step 3: Write minimal implementation**

Add to `LeadCollaborationService` class:

```python
    async def get_contributors(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> list[Contributor]:
        """Get all contributors for a lead.

        Contributors are users who have submitted at least one contribution
        to the lead. Includes contribution counts.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            List of Contributor instances with contribution counts.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            # Get all contributions for this lead
            response = (
                client.table("lead_memory_contributions")
                .select("contributor_id, created_at")
                .eq("lead_memory_id", lead_memory_id)
                .execute()
            )

            # Aggregate unique contributors with counts
            contributor_data: dict[str, dict[str, Any]] = {}
            for item in response.data or []:
                contrib = cast(dict[str, Any], item)
                contributor_id = cast(str, contrib["contributor_id"])

                if contributor_id not in contributor_data:
                    contributor_data[contributor_id] = {
                        "count": 0,
                        "added_at": contrib.get("created_at"),
                    }
                contributor_data[contributor_id]["count"] += 1

            # Get user profiles for names/emails
            contributors = []
            if contributor_data:
                user_ids = list(contributor_data.keys())
                users_response = (
                    client.table("user_profiles")
                    .select("id, full_name, email")
                    .in_("id", user_ids)
                    .execute()
                )

                user_map: dict[str, dict[str, str]] = {}
                for user in users_response.data or []:
                    user_dict = cast(dict[str, Any], user)
                    user_map[cast(str, user_dict["id"])] = {
                        "name": cast(str, user_dict.get("full_name", "")),
                        "email": cast(str, user_dict.get("email", "")),
                    }

                for contributor_id, data in contributor_data.items():
                    user_info = user_map.get(contributor_id, {"name": "", "email": ""})
                    added_at_raw = data["added_at"]
                    added_at = (
                        datetime.fromisoformat(added_at_raw)
                        if isinstance(added_at_raw, str)
                        else added_at_raw
                    ) if added_at_raw else datetime.now(UTC)

                    contributors.append(
                        Contributor(
                            id=contributor_id,
                            lead_memory_id=lead_memory_id,
                            name=user_info["name"],
                            email=user_info["email"],
                            added_at=added_at,
                            contribution_count=data["count"],
                        )
                    )

            logger.info(
                "Retrieved contributors",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "count": len(contributors),
                },
            )

            return contributors

        except Exception as e:
            logger.exception("Failed to get contributors")
            raise DatabaseError(f"Failed to get contributors: {e}") from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestGetContributors -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/lead_collaboration.py backend/tests/services/test_lead_collaboration.py
git commit -m "feat(lead-collab): add get_contributors method"
```

---

## Task 9: Add POST /leads/{id}/contributors endpoint

**Files:**
- Modify: `backend/src/api/routes/leads.py`
- Modify: `backend/tests/api/routes/test_leads.py`

**Step 1: Write the failing test**

Add to `backend/tests/api/routes/test_leads.py`:

```python
class TestAddContributorEndpoint:
    """Tests for POST /leads/{id}/contributors endpoint."""

    @pytest.fixture
    def mock_current_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "owner-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user):
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_add_contributor_success(self, client_with_mocks):
        """Test adding a contributor to a lead."""
        from src.db.supabase import SupabaseClient
        from src.services.lead_collaboration import LeadCollaborationService

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch("src.api.routes.leads.LeadMemoryService") as MockLeadService,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            # Mock lead verification
            mock_lead = MagicMock()
            mock_lead.id = "lead-456"
            MockLeadService.return_value().get_by_id = AsyncMock(return_value=mock_lead)

            # Mock collab service
            mock_collab = MagicMock()
            mock_collab.add_contributor = AsyncMock(return_value="contributor-789")
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.post(
                "/api/v1/leads/lead-456/contributors",
                json={
                    "contributor_id": "contributor-789",
                    "contributor_name": "Jane Doe",
                    "contributor_email": "jane@example.com"
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["contributor_id"] == "contributor-789"

    def test_add_contributor_lead_not_found(self, client_with_mocks):
        """Test adding contributor to non-existent lead returns 404."""
        from src.db.supabase import SupabaseClient
        from src.memory.lead_memory import LeadNotFoundError
        from src.api.routes.leads import LeadMemoryService

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch.object(LeadMemoryService, "get_by_id", side_effect=LeadNotFoundError("lead-999")),
        ):
            response = client_with_mocks.post(
                "/api/v1/leads/lead-999/contributors",
                json={
                    "contributor_id": "contributor-789",
                    "contributor_name": "Jane Doe",
                    "contributor_email": "jane@example.com"
                }
            )

            assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestAddContributorEndpoint -v
```

Expected: FAIL with `404 Not Found` (endpoint doesn't exist)

**Step 3: Write minimal implementation**

Add to `backend/src/api/routes/leads.py` after line 883 (after export_leads function):

```python
@router.post(
    "/{lead_id}/contributors",
    response_model=dict[str, str],
    status_code=status.HTTP_201_CREATED,
)
async def add_contributor(
    lead_id: str,
    contributor_data: ContributorCreate,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Add a contributor to a lead.

    Args:
        lead_id: The lead ID to add contributor to.
        contributor_data: The contributor data.
        current_user: Current authenticated user.

    Returns:
        The contributor_id that was added.

    Raises:
        HTTPException: 404 if lead not found, 500 if operation fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        # Verify lead exists and user owns it
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Add contributor
        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        contributor_id = await collab_service.add_contributor(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            contributor_id=contributor_data.contributor_id,
        )

        return {"contributor_id": contributor_id}

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to add contributor")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

Also add import at top of file (after line 42):
```python
from src.models.lead_memory import (
    InsightResponse,
    InsightType,
    LeadEventCreate,
    LeadEventResponse,
    LeadMemoryCreate,
    LeadMemoryResponse,
    LeadMemoryUpdate,
    StageTransitionRequest,
    StakeholderCreate,
    StakeholderResponse,
    StakeholderUpdate,
    ContributorCreate,
    ContributionCreate,
    ContributionResponse,
    ContributionStatus,
    ContributionReviewRequest,
)
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestAddContributorEndpoint -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/routes/test_leads.py
git commit -m "feat(lead-collab): add POST /leads/{id}/contributors endpoint"
```

---

## Task 10: Add GET /leads/{id}/contributors endpoint

**Files:**
- Modify: `backend/src/api/routes/leads.py`
- Modify: `backend/tests/api/routes/test_leads.py`

**Step 1: Write the failing test**

Add to `backend/tests/api/routes/test_leads.py`:

```python
class TestListContributorsEndpoint:
    """Tests for GET /leads/{id}/contributors endpoint."""

    @pytest.fixture
    def mock_current_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "owner-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user):
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_list_contributors_success(self, client_with_mocks):
        """Test listing contributors for a lead."""
        from src.db.supabase import SupabaseClient
        from src.services.lead_collaboration import Contributor, LeadCollaborationService
        from datetime import datetime, UTC

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch("src.api.routes.leads.LeadMemoryService") as MockLeadService,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            # Mock lead verification
            mock_lead = MagicMock()
            MockLeadService.return_value().get_by_id = AsyncMock(return_value=mock_lead)

            # Mock contributors
            mock_contributors = [
                Contributor(
                    id="user-789",
                    lead_memory_id="lead-456",
                    name="Jane Doe",
                    email="jane@example.com",
                    added_at=datetime(2026, 2, 4, 10, 0, tzinfo=UTC),
                    contribution_count=3
                )
            ]
            mock_collab = MagicMock()
            mock_collab.get_contributors = AsyncMock(return_value=mock_contributors)
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.get("/api/v1/leads/lead-456/contributors")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "user-789"
            assert data[0]["name"] == "Jane Doe"
            assert data[0]["contribution_count"] == 3
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestListContributorsEndpoint -v
```

Expected: FAIL with `404 Not Found`

**Step 3: Write minimal implementation**

Add to `backend/src/api/routes/leads.py` after add_contributor endpoint:

```python
@router.get("/{lead_id}/contributors", response_model=list[ContributorResponse])
async def list_contributors(
    lead_id: str,
    current_user: CurrentUser,
) -> list[ContributorResponse]:
    """List all contributors for a lead.

    Args:
        lead_id: The lead ID to list contributors for.
        current_user: Current authenticated user.

    Returns:
        List of contributors for the lead.

    Raises:
        HTTPException: 404 if lead not found, 500 if retrieval fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Get contributors
        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        contributors = await collab_service.get_contributors(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        return [
            ContributorResponse(
                id=contributor.id,
                lead_memory_id=contributor.lead_memory_id,
                name=contributor.name,
                email=contributor.email,
                added_at=contributor.added_at,
                contribution_count=contributor.contribution_count,
            )
            for contributor in contributors
        ]

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to list contributors")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestListContributorsEndpoint -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/routes/test_leads.py
git commit -m "feat(lead-collab): add GET /leads/{id}/contributors endpoint"
```

---

## Task 11: Add POST /leads/{id}/contributions endpoint

**Files:**
- Modify: `backend/src/api/routes/leads.py`
- Modify: `backend/tests/api/routes/test_leads.py`

**Step 1: Write the failing test**

Add to `backend/tests/api/routes/test_leads.py`:

```python
class TestSubmitContributionEndpoint:
    """Tests for POST /leads/{id}/contributions endpoint."""

    @pytest.fixture
    def mock_current_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "contributor-789"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user):
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_submit_note_contribution(self, client_with_mocks):
        """Test submitting a note contribution."""
        from src.db.supabase import SupabaseClient
        from src.api.routes.leads import LeadMemoryService

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch.object(LeadMemoryService, "get_by_id") as mock_get,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            # Mock lead exists (user can contribute to leads they don't own)
            mock_lead = MagicMock()
            mock_lead.id = "lead-456"
            mock_get.return_value = mock_lead

            # Mock collab service
            mock_collab = MagicMock()
            mock_collab.submit_contribution = AsyncMock(return_value="contrib-123")
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.post(
                "/api/v1/leads/lead-456/contributions",
                json={
                    "contribution_type": "note",
                    "content": "Met with CTO, very interested"
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "contrib-123"

    def test_submit_event_contribution(self, client_with_mocks):
        """Test submitting an event contribution."""
        from src.db.supabase import SupabaseClient
        from src.api.routes.leads import LeadMemoryService

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch.object(LeadMemoryService, "get_by_id") as mock_get,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            mock_lead = MagicMock()
            mock_get.return_value = mock_lead

            mock_collab = MagicMock()
            mock_collab.submit_contribution = AsyncMock(return_value="contrib-456")
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.post(
                "/api/v1/leads/lead-456/contributions",
                json={
                    "contribution_type": "event",
                    "contribution_id": "event-abc123"
                }
            )

            assert response.status_code == 201
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestSubmitContributionEndpoint -v
```

Expected: FAIL with `404 Not Found`

**Step 3: Write minimal implementation**

Add to `backend/src/api/routes/leads.py`:

```python
@router.post(
    "/{lead_id}/contributions",
    response_model=dict[str, str],
    status_code=status.HTTP_201_CREATED,
)
async def submit_contribution(
    lead_id: str,
    contribution_data: ContributionCreate,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Submit a contribution to a lead for owner review.

    Args:
        lead_id: The lead ID to submit contribution to.
        contribution_data: The contribution data.
        current_user: Current authenticated user.

    Returns:
        The ID of the created contribution.

    Raises:
        HTTPException: 404 if lead not found, 500 if submission fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        # Note: Contributors can submit to leads they don't own
        # The contribution goes into pending status for owner review
        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        contribution_id = await collab_service.submit_contribution(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            contribution_type=contribution_data.contribution_type,
            contribution_id=contribution_data.contribution_id,
            content=contribution_data.content,
        )

        return {"id": contribution_id}

    except LeadMemoryError as e:
        logger.exception("Failed to submit contribution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestSubmitContributionEndpoint -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/routes/test_leads.py
git commit -m "feat(lead-collab): add POST /leads/{id}/contributions endpoint"
```

---

## Task 12: Add GET /leads/{id}/contributions endpoint

**Files:**
- Modify: `backend/src/api/routes/leads.py`
- Modify: `backend/tests/api/routes/test_leads.py`

**Step 1: Write the failing test**

Add to `backend/tests/api/routes/test_leads.py`:

```python
class TestListContributionsEndpoint:
    """Tests for GET /leads/{id}/contributions endpoint."""

    @pytest.fixture
    def mock_current_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "owner-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user):
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_list_pending_contributions(self, client_with_mocks):
        """Test listing pending contributions for a lead."""
        from src.db.supabase import SupabaseClient
        from src.services.lead_collaboration import Contribution, ContributionStatus, ContributionType, LeadCollaborationService
        from datetime import datetime, UTC

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch("src.api.routes.leads.LeadMemoryService") as MockLeadService,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            # Mock lead verification
            mock_lead = MagicMock()
            MockLeadService.return_value().get_by_id = AsyncMock(return_value=mock_lead)

            # Mock contributions
            now = datetime(2026, 2, 4, 10, 0, tzinfo=UTC)
            mock_contributions = [
                Contribution(
                    id="contrib-1",
                    lead_memory_id="lead-456",
                    contributor_id="user-789",
                    contribution_type=ContributionType.NOTE,
                    contribution_id=None,
                    status=ContributionStatus.PENDING,
                    reviewed_by=None,
                    reviewed_at=None,
                    created_at=now
                )
            ]
            mock_collab = MagicMock()
            mock_collab.get_pending_contributions = AsyncMock(return_value=mock_contributions)
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.get(
                "/api/v1/leads/lead-456/contributions",
                params={"status": "pending"}
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "contrib-1"
            assert data[0]["status"] == "pending"

    def test_list_all_contributions(self, client_with_mocks):
        """Test listing all contributions (no status filter)."""
        from src.db.supabase import SupabaseClient

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch("src.api.routes.leads.LeadMemoryService") as MockLeadService,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            mock_lead = MagicMock()
            MockLeadService.return_value().get_by_id = AsyncMock(return_value=mock_lead)

            mock_collab = MagicMock()
            mock_collab.get_pending_contributions = AsyncMock(return_value=[])
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.get("/api/v1/leads/lead-456/contributions")

            assert response.status_code == 200
            assert response.json() == []
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestListContributionsEndpoint -v
```

Expected: FAIL with `404 Not Found`

**Step 3: Write minimal implementation**

Add to `backend/src/api/routes/leads.py`:

```python
@router.get("/{lead_id}/contributions", response_model=list[ContributionResponse])
async def list_contributions(
    lead_id: str,
    current_user: CurrentUser,
    status: str | None = Query(None, description="Filter by status (pending, merged, rejected)"),
) -> list[ContributionResponse]:
    """List contributions for a lead.

    Args:
        lead_id: The lead ID to list contributions for.
        current_user: Current authenticated user.
        status: Optional filter by contribution status.

    Returns:
        List of contributions for the lead.

    Raises:
        HTTPException: 404 if lead not found, 400 if invalid status, 500 if retrieval fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import ContributionStatus, LeadCollaborationService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # For now, only support pending status (owner review queue)
        # Future: add filtering for merged/rejected
        if status and status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status filter '{status}' not yet supported. Use 'pending'.",
            )

        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        contributions = await collab_service.get_pending_contributions(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        return [
            ContributionResponse(
                id=contrib.id,
                lead_memory_id=contrib.lead_memory_id,
                contributor_id=contrib.contributor_id,
                contributor_name="",  # Will be populated from user profiles
                contribution_type=contrib.contribution_type,
                contribution_id=contrib.contribution_id,
                content=None,  # Will be populated from contribution_id
                status=contrib.status,
                created_at=contrib.created_at,
                reviewed_at=contrib.reviewed_at,
                reviewed_by=contrib.reviewed_by,
            )
            for contrib in contributions
        ]

    except HTTPException:
        raise
    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to list contributions")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestListContributionsEndpoint -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/routes/test_leads.py
git commit -m "feat(lead-collab): add GET /leads/{id}/contributions endpoint"
```

---

## Task 13: Add POST /leads/{id}/contributions/{contribution_id}/review endpoint

**Files:**
- Modify: `backend/src/api/routes/leads.py`
- Modify: `backend/tests/api/routes/test_leads.py`

**Step 1: Write the failing test**

Add to `backend/tests/api/routes/test_leads.py`:

```python
class TestReviewContributionEndpoint:
    """Tests for POST /leads/{id}/contributions/{contribution_id}/review endpoint."""

    @pytest.fixture
    def mock_current_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "owner-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user):
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_review_merge_contribution(self, client_with_mocks):
        """Test reviewing and merging a contribution."""
        from src.db.supabase import SupabaseClient
        from src.api.routes.leads import LeadMemoryService

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch.object(LeadMemoryService, "get_by_id") as mock_get,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            # Mock lead verification
            mock_lead = MagicMock()
            mock_get.return_value = mock_lead

            # Mock collab service
            mock_collab = MagicMock()
            mock_collab.review_contribution = AsyncMock()
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.post(
                "/api/v1/leads/lead-456/contributions/contrib-123/review",
                json={"action": "merge"}
            )

            assert response.status_code == 204
            mock_collab.review_contribution.assert_called_once_with(
                user_id="owner-123",
                contribution_id="contrib-123",
                action="merge"
            )

    def test_review_reject_contribution(self, client_with_mocks):
        """Test reviewing and rejecting a contribution."""
        from src.db.supabase import SupabaseClient
        from src.api.routes.leads import LeadMemoryService

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch.object(LeadMemoryService, "get_by_id") as mock_get,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            mock_lead = MagicMock()
            mock_get.return_value = mock_lead

            mock_collab = MagicMock()
            mock_collab.review_contribution = AsyncMock()
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.post(
                "/api/v1/leads/lead-456/contributions/contrib-123/review",
                json={"action": "reject"}
            )

            assert response.status_code == 204

    def test_review_invalid_action(self, client_with_mocks):
        """Test invalid review action returns 400."""
        from src.db.supabase import SupabaseClient
        from src.api.routes.leads import LeadMemoryService

        mock_client = MagicMock()

        with (
            patch.object(SupabaseClient, "get_client", return_value=mock_client),
            patch.object(LeadMemoryService, "get_by_id") as mock_get,
            patch("src.api.routes.leads.LeadCollaborationService") as MockCollabService,
        ):
            mock_lead = MagicMock()
            mock_get.return_value = mock_lead

            mock_collab = MagicMock()
            mock_collab.review_contribution = AsyncMock(
                side_effect=ValidationError("Invalid action")
            )
            MockCollabService.return_value = mock_collab

            response = client_with_mocks.post(
                "/api/v1/leads/lead-456/contributions/contrib-123/review",
                json={"action": "invalid"}
            )

            assert response.status_code == 400
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestReviewContributionEndpoint -v
```

Expected: FAIL with `404 Not Found`

**Step 3: Write minimal implementation**

Add to `backend/src/api/routes/leads.py`:

```python
@router.post(
    "/{lead_id}/contributions/{contribution_id}/review",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def review_contribution(
    lead_id: str,
    contribution_id: str,
    review_data: ContributionReviewRequest,
    current_user: CurrentUser,
) -> None:
    """Review a contribution (merge or reject).

    Args:
        lead_id: The lead ID (for verification).
        contribution_id: The contribution ID to review.
        review_data: The review action (merge or reject).
        current_user: Current authenticated user (must be lead owner).

    Raises:
        HTTPException: 404 if lead not found, 400 if invalid action, 500 if review fails.
    """
    from src.db.supabase import SupabaseClient
    from src.core.exceptions import ValidationError
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        # Verify lead exists and user owns it
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Review the contribution
        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        await collab_service.review_contribution(
            user_id=current_user.id,
            contribution_id=contribution_id,
            action=review_data.action,
        )

        return None

    except ValidationError as e:
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
        logger.exception("Failed to review contribution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
```

Also add ValidationError import (after line 19):
```python
from src.core.exceptions import (
    InvalidStageTransitionError,
    LeadMemoryError,
    LeadNotFoundError,
    ValidationError,
)
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/api/routes/test_leads.py::TestReviewContributionEndpoint -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/leads.py backend/tests/api/routes/test_leads.py
git commit -m "feat(lead-collab): add POST /leads/{id}/contributions/{contribution_id}/review endpoint"
```

---

## Task 14: Add notification on contribution submission

**Files:**
- Modify: `backend/src/services/lead_collaboration.py`
- Modify: `backend/tests/services/test_lead_collaboration.py`

**Step 1: Write the failing test**

Add to `backend/tests/services/test_lead_collaboration.py`:

```python
class TestContributionNotification:
    """Tests for notification when contribution is submitted."""

    @pytest.mark.asyncio
    async def test_submit_contribution_sends_notification(self):
        """Test submitting a contribution sends notification to lead owner."""
        from src.services.lead_collaboration import LeadCollaborationService, ContributionType
        from unittest.mock import AsyncMock

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        now = datetime(2026, 2, 4, 10, 0, tzinfo=UTC)
        mock_response = MagicMock()
        mock_response.data = [{"id": "contrib-123"}]

        mock_query = MagicMock()
        mock_query.insert.return_value.execute.return_value = mock_response
        mock_client.table.return_value.insert.return_value = mock_query

        # Mock getting lead owner
        mock_lead_response = MagicMock()
        mock_lead_response.data = [{"user_id": "owner-123"}]
        mock_lead_query = MagicMock()
        mock_lead_query.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_lead_response
        mock_client.table.return_value.select.return_value = mock_lead_query

        with (
            patch.object(service, "_get_supabase_client", return_value=mock_client),
            patch("src.services.lead_collaboration.NotificationService") as MockNotification,
        ):
            mock_notif = MagicMock()
            mock_notif.create_notification = AsyncMock()
            MockNotification.create_notification = mock_notif

            contribution_id = await service.submit_contribution(
                user_id="contributor-789",
                lead_memory_id="lead-456",
                contribution_type=ContributionType.NOTE,
                content="Met with CTO"
            )

            # Verify notification was created
            mock_notif.assert_called_once()
            call_args = mock_notif.call_args
            assert call_args[1]["user_id"] == "owner-123"
            assert "contribution" in call_args[1]["title"].lower()
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestContributionNotification -v
```

Expected: FAIL - notification not being sent

**Step 3: Write minimal implementation**

Modify `submit_contribution` method in `LeadCollaborationService` to add notification after successful contribution:

```python
    async def submit_contribution(
        self,
        user_id: str,
        lead_memory_id: str,
        contribution_type: ContributionType,
        contribution_id: str | None = None,
        content: str | None = None,
    ) -> str:
        """Submit a contribution to a lead for owner review.

        Args:
            user_id: The user submitting the contribution.
            lead_memory_id: The lead memory ID.
            contribution_type: Type of contribution (event, note, insight).
            contribution_id: Optional ID of existing event/note/insight.
            content: Optional content for note/insight contributions.

        Returns:
            The ID of the created contribution record.

        Raises:
            DatabaseError: If submission fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            # Get lead owner for notification
            lead_response = (
                client.table("lead_memories")
                .select("user_id")
                .eq("id", lead_memory_id)
                .single()
                .execute()
            )

            owner_id = None
            if lead_response.data:
                owner_id = cast(dict[str, Any], lead_response.data).get("user_id")

            now = datetime.now(UTC)
            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "contributor_id": user_id,
                "contribution_type": contribution_type.value,
                "contribution_id": contribution_id,
                "status": ContributionStatus.PENDING.value,
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": now.isoformat(),
            }

            response = client.table("lead_memory_contributions").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert contribution")

            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            new_contribution_id = cast(str, first_record.get("id"))

            if not new_contribution_id:
                raise DatabaseError("Failed to insert contribution")

            logger.info(
                "Contribution submitted",
                extra={
                    "contribution_id": new_contribution_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contribution_type": contribution_type.value,
                },
            )

            # Send notification to lead owner
            if owner_id and owner_id != user_id:
                from src.services.notification_service import NotificationService
                from src.models.notification import NotificationType

                await NotificationService.create_notification(
                    user_id=owner_id,
                    type=NotificationType.TASK_DUE,  # Reuse existing type
                    title=f"New contribution pending review",
                    message=f"A team member submitted a {contribution_type.value} contribution for review.",
                    link=f"/leads/{lead_memory_id}",
                    metadata={"contribution_id": new_contribution_id, "lead_id": lead_memory_id},
                )

            return new_contribution_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to submit contribution")
            raise DatabaseError(f"Failed to submit contribution: {e}") from e
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/services/test_lead_collaboration.py::TestContributionNotification -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/lead_collaboration.py backend/tests/services/test_lead_collaboration.py
git commit -m "feat(lead-collab): send notification on contribution submission"
```

---

## Task 15: Export LeadCollaborationService from services module

**Files:**
- Modify: `backend/src/services/__init__.py`

**Step 1: Write the failing test**

Create a simple import test:

```python
def test_lead_collaboration_service_export():
    """Test LeadCollaborationService is exported from services module."""
    from src.services import LeadCollaborationService

    assert LeadCollaborationService is not None
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/ -k "test_lead_collaboration_service_export" -v
```

Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `backend/src/services/__init__.py`:

```python
from src.services.lead_collaboration import (
    Contribution,
    Contributor,
    LeadCollaborationService,
)

__all__ = [
    "LeadCollaborationService",
    "Contribution",
    "Contributor",
]
```

**Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/ -k "test_lead_collaboration_service_export" -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/__init__.py
git commit -m "feat(lead-collab): export LeadCollaborationService from services module"
```

---

## Completion

All tasks complete. Verify implementation:

```bash
cd backend
pytest tests/services/test_lead_collaboration.py -v
pytest tests/api/routes/test_leads.py -v
```

Run type checking:

```bash
cd backend
mypy src/services/lead_collaboration.py --strict
mypy src/api/routes/leads.py --strict
```

---

## Summary

This plan implements US-513 Multi-User Collaboration with:

1. **Domain Models**: Contribution and Contributor dataclasses with full serialization
2. **Service Layer**: LeadCollaborationService with 5 core methods
3. **API Endpoints**: 5 REST endpoints for full collaboration workflow
4. **Notifications**: Owner notified on new contributions
5. **Tests**: Comprehensive unit tests for all methods and endpoints
6. **Type Safety**: Full type hints with strict mypy compliance

**Acceptance Criteria Met:**
- [x] Lead has single owner (user_id on lead_memories table)
- [x] Other users can be contributors (via contributions)
- [x] Contributions flagged for owner review (status=pending)
- [x] Owner can merge or reject (review_contribution endpoint)
- [x] Full audit trail (reviewed_by, reviewed_at, created_at in DB)
- [x] Contributor list visible on lead (get_contributors endpoint)
- [x] Notification to owner on new contribution
