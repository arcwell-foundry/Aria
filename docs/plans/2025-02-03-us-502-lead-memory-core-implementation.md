# Lead Memory Core Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `LeadMemoryService` in `src/memory/lead_memory.py` to track sales pursuits with lifecycle stages, status management, and filtering capabilities.

**Architecture:** Lead Memory uses Supabase (PostgreSQL) for structured storage via the `lead_memories` table created in US-501. The service follows existing memory service patterns (like `ProceduralMemory`), using dataclasses for models, enums for type safety, and the Supabase client singleton pattern. All operations log to the audit trail.

**Tech Stack:** Python 3.11+ / Supabase / Pydantic-style dataclasses / Async/await

---

## Task 1: Create Lead Memory Exceptions

**Files:**
- Modify: `backend/src/core/exceptions.py` (add after line 402, following CorporateFactNotFoundError)

**Step 1: Write the failing test**

Create: `backend/tests/test_lead_memory_exceptions.py`

```python
"""Tests for Lead Memory exceptions."""


def test_lead_memory_error_initialization() -> None:
    """Test LeadMemoryError initializes with correct attributes."""
    from src.core.exceptions import LeadMemoryError

    error = LeadMemoryError("Database connection failed")

    assert error.message == "Lead memory error: Database connection failed"
    assert error.code == "LEAD_MEMORY_ERROR"
    assert error.status_code == 500


def test_lead_not_found_error_initialization() -> None:
    """Test LeadNotFoundError initializes with correct attributes."""
    from src.core.exceptions import LeadNotFoundError

    error = LeadNotFoundError("lead-123")

    assert "lead-123" in error.message
    assert error.code == "NOT_FOUND"
    assert error.status_code == 404


def test_invalid_stage_transition_error() -> None:
    """Test InvalidStageTransitionError initializes with correct attributes."""
    from src.core.exceptions import InvalidStageTransitionError

    error = InvalidStageTransitionError("lead", "account")

    assert "lead" in error.message
    assert "account" in error.message
    assert error.code == "INVALID_STAGE_TRANSITION"
    assert error.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory_exceptions.py -v`
Expected: FAIL with "cannot import name 'LeadMemoryError' from 'src.core.exceptions'"

**Step 3: Write minimal implementation**

Add to `backend/src/core/exceptions.py` after `CorporateFactNotFoundError` (around line 402):

```python
class LeadMemoryError(ARIAException):
    """Lead memory operation error (500).

    Used for failures in lead memory operations.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize lead memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Lead memory error: {message}",
            code="LEAD_MEMORY_ERROR",
            status_code=500,
        )


class LeadNotFoundError(NotFoundError):
    """Lead not found error (404)."""

    def __init__(self, lead_id: str) -> None:
        """Initialize lead not found error.

        Args:
            lead_id: The ID of the lead that was not found.
        """
        super().__init__(resource="Lead", resource_id=lead_id)


class InvalidStageTransitionError(ARIAException):
    """Invalid lifecycle stage transition error (400).

    Raised when attempting an invalid stage transition
    (e.g., account -> lead).
    """

    def __init__(self, current_stage: str, target_stage: str) -> None:
        """Initialize invalid stage transition error.

        Args:
            current_stage: The current lifecycle stage.
            target_stage: The attempted target stage.
        """
        super().__init__(
            message=f"Cannot transition from '{current_stage}' to '{target_stage}'",
            code="INVALID_STAGE_TRANSITION",
            status_code=400,
            details={"current_stage": current_stage, "target_stage": target_stage},
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory_exceptions.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/core/exceptions.py backend/tests/test_lead_memory_exceptions.py
git commit -m "feat(lead-memory): add LeadMemoryError, LeadNotFoundError, InvalidStageTransitionError exceptions"
```

---

## Task 2: Add LEAD to MemoryType Enum

**Files:**
- Modify: `backend/src/memory/audit.py` (line 31-38)

**Step 1: Write the failing test**

Create: `backend/tests/test_lead_memory_audit_enum.py`

```python
"""Tests for Lead Memory audit enum."""


def test_memory_type_includes_lead() -> None:
    """Test MemoryType enum includes LEAD variant."""
    from src.memory.audit import MemoryType

    assert hasattr(MemoryType, "LEAD")
    assert MemoryType.LEAD.value == "lead"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory_audit_enum.py -v`
Expected: FAIL with "AttributeError: LEAD"

**Step 3: Write minimal implementation**

Edit `backend/src/memory/audit.py`, modify the `MemoryType` enum (around line 31-38):

```python
class MemoryType(Enum):
    """Types of memory that can be audited."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PROSPECTIVE = "prospective"
    LEAD = "lead"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory_audit_enum.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/audit.py backend/tests/test_lead_memory_audit_enum.py
git commit -m "feat(lead-memory): add LEAD to MemoryType audit enum"
```

---

## Task 3: Create LeadMemory Enums and Dataclass

**Files:**
- Create: `backend/src/memory/lead_memory.py`
- Create: `backend/tests/test_lead_memory.py`

**Step 1: Write the failing test for enums**

Create: `backend/tests/test_lead_memory.py`

```python
"""Tests for Lead Memory module."""

from datetime import UTC, datetime
from decimal import Decimal


class TestLifecycleStageEnum:
    """Tests for LifecycleStage enum."""

    def test_lifecycle_stage_values(self) -> None:
        """Test LifecycleStage enum has correct values."""
        from src.memory.lead_memory import LifecycleStage

        assert LifecycleStage.LEAD.value == "lead"
        assert LifecycleStage.OPPORTUNITY.value == "opportunity"
        assert LifecycleStage.ACCOUNT.value == "account"

    def test_lifecycle_stage_ordering(self) -> None:
        """Test lifecycle stages can be compared for progression."""
        from src.memory.lead_memory import LifecycleStage

        # Stages should be orderable via their natural progression
        stages = [LifecycleStage.LEAD, LifecycleStage.OPPORTUNITY, LifecycleStage.ACCOUNT]
        assert stages == sorted(stages, key=lambda s: list(LifecycleStage).index(s))


class TestLeadStatusEnum:
    """Tests for LeadStatus enum."""

    def test_lead_status_values(self) -> None:
        """Test LeadStatus enum has correct values."""
        from src.memory.lead_memory import LeadStatus

        assert LeadStatus.ACTIVE.value == "active"
        assert LeadStatus.WON.value == "won"
        assert LeadStatus.LOST.value == "lost"
        assert LeadStatus.DORMANT.value == "dormant"


class TestTriggerTypeEnum:
    """Tests for TriggerType enum."""

    def test_trigger_type_values(self) -> None:
        """Test TriggerType enum has correct values."""
        from src.memory.lead_memory import TriggerType

        assert TriggerType.EMAIL_APPROVED.value == "email_approved"
        assert TriggerType.MANUAL.value == "manual"
        assert TriggerType.CRM_IMPORT.value == "crm_import"
        assert TriggerType.INBOUND.value == "inbound"


class TestLeadMemoryDataclass:
    """Tests for LeadMemory dataclass."""

    def test_lead_memory_initialization(self) -> None:
        """Test LeadMemory initializes with required fields."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        lead = LeadMemory(
            id="lead-123",
            user_id="user-456",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=75,
            trigger=TriggerType.MANUAL,
            first_touch_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )

        assert lead.id == "lead-123"
        assert lead.user_id == "user-456"
        assert lead.company_name == "Acme Corp"
        assert lead.lifecycle_stage == LifecycleStage.LEAD
        assert lead.status == LeadStatus.ACTIVE
        assert lead.health_score == 75
        assert lead.trigger == TriggerType.MANUAL

    def test_lead_memory_optional_fields(self) -> None:
        """Test LeadMemory optional fields default correctly."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        lead = LeadMemory(
            id="lead-123",
            user_id="user-456",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )

        assert lead.company_id is None
        assert lead.crm_id is None
        assert lead.crm_provider is None
        assert lead.expected_close_date is None
        assert lead.expected_value is None
        assert lead.tags == []
        assert lead.metadata == {}

    def test_lead_memory_to_dict(self) -> None:
        """Test LeadMemory.to_dict serializes correctly."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        lead = LeadMemory(
            id="lead-123",
            user_id="user-456",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.ACTIVE,
            health_score=80,
            trigger=TriggerType.CRM_IMPORT,
            first_touch_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
            tags=["enterprise", "healthcare"],
            expected_value=Decimal("100000.00"),
        )

        data = lead.to_dict()

        assert data["id"] == "lead-123"
        assert data["lifecycle_stage"] == "opportunity"
        assert data["status"] == "active"
        assert data["tags"] == ["enterprise", "healthcare"]
        assert data["expected_value"] == "100000.00"

    def test_lead_memory_from_dict(self) -> None:
        """Test LeadMemory.from_dict deserializes correctly."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        data = {
            "id": "lead-123",
            "user_id": "user-456",
            "company_id": None,
            "company_name": "Acme Corp",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 80,
            "trigger": "crm_import",
            "crm_id": "sf-opp-123",
            "crm_provider": "salesforce",
            "first_touch_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "expected_close_date": None,
            "expected_value": "100000.00",
            "tags": ["enterprise"],
            "metadata": {"source": "website"},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        lead = LeadMemory.from_dict(data)

        assert lead.id == "lead-123"
        assert lead.lifecycle_stage == LifecycleStage.OPPORTUNITY
        assert lead.status == LeadStatus.ACTIVE
        assert lead.trigger == TriggerType.CRM_IMPORT
        assert lead.crm_id == "sf-opp-123"
        assert lead.expected_value == Decimal("100000.00")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.memory.lead_memory'"

**Step 3: Write minimal implementation**

Create: `backend/src/memory/lead_memory.py`

```python
"""Lead memory module for tracking sales pursuits.

Lead memory stores sales pursuit information with:
- Lifecycle stage progression (lead → opportunity → account)
- Status tracking (active, won, lost, dormant)
- Health score calculation (0-100)
- Trigger source tracking for lead creation
- Optional CRM integration fields

Leads are stored in Supabase for structured querying
and integration with the CRM sync system.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, date
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LifecycleStage(Enum):
    """Lifecycle stages for lead progression.

    Stages progress in order: lead → opportunity → account.
    History is preserved on transition.
    """

    LEAD = "lead"
    OPPORTUNITY = "opportunity"
    ACCOUNT = "account"


class LeadStatus(Enum):
    """Status of a lead within its lifecycle stage."""

    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    DORMANT = "dormant"


class TriggerType(Enum):
    """Source that triggered lead creation."""

    EMAIL_APPROVED = "email_approved"
    MANUAL = "manual"
    CRM_IMPORT = "crm_import"
    INBOUND = "inbound"


@dataclass
class LeadMemory:
    """A lead memory record representing a sales pursuit.

    Tracks the full lifecycle of a sales pursuit from initial
    lead through opportunity to closed account.
    """

    id: str
    user_id: str
    company_name: str
    lifecycle_stage: LifecycleStage
    status: LeadStatus
    health_score: int  # 0-100
    trigger: TriggerType
    first_touch_at: datetime
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime
    company_id: str | None = None
    crm_id: str | None = None
    crm_provider: str | None = None  # salesforce, hubspot
    expected_close_date: date | None = None
    expected_value: Decimal | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize lead to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "lifecycle_stage": self.lifecycle_stage.value,
            "status": self.status.value,
            "health_score": self.health_score,
            "trigger": self.trigger.value,
            "crm_id": self.crm_id,
            "crm_provider": self.crm_provider,
            "first_touch_at": self.first_touch_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "expected_close_date": self.expected_close_date.isoformat()
            if self.expected_close_date
            else None,
            "expected_value": str(self.expected_value) if self.expected_value else None,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeadMemory":
        """Create a LeadMemory instance from a dictionary.

        Args:
            data: Dictionary containing lead data.

        Returns:
            LeadMemory instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            company_id=data.get("company_id"),
            company_name=data["company_name"],
            lifecycle_stage=LifecycleStage(data["lifecycle_stage"]),
            status=LeadStatus(data["status"]),
            health_score=data["health_score"],
            trigger=TriggerType(data["trigger"]) if data.get("trigger") else TriggerType.MANUAL,
            crm_id=data.get("crm_id"),
            crm_provider=data.get("crm_provider"),
            first_touch_at=datetime.fromisoformat(data["first_touch_at"])
            if isinstance(data["first_touch_at"], str)
            else data["first_touch_at"],
            last_activity_at=datetime.fromisoformat(data["last_activity_at"])
            if isinstance(data["last_activity_at"], str)
            else data["last_activity_at"],
            expected_close_date=date.fromisoformat(data["expected_close_date"])
            if data.get("expected_close_date")
            else None,
            expected_value=Decimal(data["expected_value"])
            if data.get("expected_value")
            else None,
            tags=data.get("tags") or [],
            metadata=data.get("metadata") or {},
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data["created_at"], str)
            else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"])
            if isinstance(data["updated_at"], str)
            else data["updated_at"],
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory.py -v`
Expected: PASS (9 tests)

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory.py backend/tests/test_lead_memory.py
git commit -m "feat(lead-memory): add LifecycleStage, LeadStatus, TriggerType enums and LeadMemory dataclass"
```

---

## Task 4: Implement LeadMemoryService.create()

**Files:**
- Modify: `backend/src/memory/lead_memory.py`
- Modify: `backend/tests/test_lead_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory.py`:

```python
from unittest.mock import MagicMock, patch
import pytest


class TestLeadMemoryServiceCreate:
    """Tests for LeadMemoryService.create()."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "generated-uuid"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        return mock_client

    @pytest.mark.asyncio
    async def test_create_lead_with_minimal_fields(self, mock_supabase: MagicMock) -> None:
        """Test creating a lead with only required fields."""
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Acme Corp",
                    trigger=TriggerType.MANUAL,
                )

        assert lead.user_id == "user-123"
        assert lead.company_name == "Acme Corp"
        assert lead.trigger == TriggerType.MANUAL
        assert lead.lifecycle_stage.value == "lead"
        assert lead.status.value == "active"
        assert lead.health_score == 50  # Default health score

    @pytest.mark.asyncio
    async def test_create_lead_with_all_fields(self, mock_supabase: MagicMock) -> None:
        """Test creating a lead with all optional fields."""
        from datetime import date
        from decimal import Decimal
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Enterprise Inc",
                    trigger=TriggerType.CRM_IMPORT,
                    company_id="company-456",
                    crm_id="sf-lead-789",
                    crm_provider="salesforce",
                    expected_close_date=date(2025, 6, 30),
                    expected_value=Decimal("250000.00"),
                    tags=["enterprise", "healthcare"],
                    metadata={"source": "conference"},
                )

        assert lead.company_name == "Enterprise Inc"
        assert lead.trigger == TriggerType.CRM_IMPORT
        assert lead.company_id == "company-456"
        assert lead.crm_id == "sf-lead-789"
        assert lead.crm_provider == "salesforce"
        assert lead.expected_value == Decimal("250000.00")
        assert "enterprise" in lead.tags

    @pytest.mark.asyncio
    async def test_create_lead_sets_timestamps(self, mock_supabase: MagicMock) -> None:
        """Test that create sets first_touch_at and last_activity_at."""
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Test Corp",
                    trigger=TriggerType.INBOUND,
                )

        assert lead.first_touch_at is not None
        assert lead.last_activity_at is not None
        assert lead.created_at is not None
        assert lead.first_touch_at == lead.last_activity_at

    @pytest.mark.asyncio
    async def test_create_lead_logs_audit(self, mock_supabase: MagicMock) -> None:
        """Test that create logs to audit trail."""
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation") as mock_audit:
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Test Corp",
                    trigger=TriggerType.MANUAL,
                )

                mock_audit.assert_called_once()
                call_kwargs = mock_audit.call_args.kwargs
                assert call_kwargs["user_id"] == "user-123"
                assert call_kwargs["memory_id"] == lead.id
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceCreate -v`
Expected: FAIL with "cannot import name 'LeadMemoryService'"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/lead_memory.py`:

```python
import uuid
from typing import Any

from src.core.exceptions import LeadMemoryError
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation


class LeadMemoryService:
    """Service class for lead memory operations.

    Provides async interface for storing, retrieving, and managing
    lead memories. Uses Supabase as the underlying storage for
    structured querying and CRM integration.
    """

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            LeadMemoryError: If client initialization fails.
        """
        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise LeadMemoryError(f"Failed to get Supabase client: {e}") from e

    async def create(
        self,
        user_id: str,
        company_name: str,
        trigger: TriggerType,
        company_id: str | None = None,
        crm_id: str | None = None,
        crm_provider: str | None = None,
        expected_close_date: date | None = None,
        expected_value: Decimal | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LeadMemory:
        """Create a new lead in memory.

        Args:
            user_id: The user creating the lead.
            company_name: Name of the company/lead.
            trigger: Source that triggered lead creation.
            company_id: Optional company UUID reference.
            crm_id: Optional external CRM record ID.
            crm_provider: Optional CRM provider (salesforce, hubspot).
            expected_close_date: Optional expected close date.
            expected_value: Optional expected deal value.
            tags: Optional list of tags.
            metadata: Optional additional metadata.

        Returns:
            The created LeadMemory instance.

        Raises:
            LeadMemoryError: If creation fails.
        """
        try:
            lead_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            # Create lead with defaults
            lead = LeadMemory(
                id=lead_id,
                user_id=user_id,
                company_id=company_id,
                company_name=company_name,
                lifecycle_stage=LifecycleStage.LEAD,
                status=LeadStatus.ACTIVE,
                health_score=50,  # Default health score
                trigger=trigger,
                crm_id=crm_id,
                crm_provider=crm_provider,
                first_touch_at=now,
                last_activity_at=now,
                expected_close_date=expected_close_date,
                expected_value=expected_value,
                tags=tags or [],
                metadata=metadata or {},
                created_at=now,
                updated_at=now,
            )

            # Prepare data for database
            data = {
                "id": lead.id,
                "user_id": lead.user_id,
                "company_id": lead.company_id,
                "company_name": lead.company_name,
                "lifecycle_stage": lead.lifecycle_stage.value,
                "status": lead.status.value,
                "health_score": lead.health_score,
                "crm_id": lead.crm_id,
                "crm_provider": lead.crm_provider,
                "first_touch_at": lead.first_touch_at.isoformat(),
                "last_activity_at": lead.last_activity_at.isoformat(),
                "expected_close_date": lead.expected_close_date.isoformat()
                if lead.expected_close_date
                else None,
                "expected_value": float(lead.expected_value) if lead.expected_value else None,
                "tags": lead.tags,
                "metadata": {
                    **lead.metadata,
                    "trigger": trigger.value,
                },
            }

            client = self._get_supabase_client()
            response = client.table("lead_memories").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise LeadMemoryError("Failed to insert lead")

            logger.info(
                "Created lead",
                extra={
                    "lead_id": lead_id,
                    "user_id": user_id,
                    "company_name": company_name,
                    "trigger": trigger.value,
                },
            )

            # Audit log the creation
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={"company_name": company_name, "trigger": trigger.value},
                suppress_errors=True,
            )

            return lead

        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to create lead")
            raise LeadMemoryError(f"Failed to create lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceCreate -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory.py backend/tests/test_lead_memory.py
git commit -m "feat(lead-memory): implement LeadMemoryService.create() with trigger tracking"
```

---

## Task 5: Implement LeadMemoryService.get_by_id()

**Files:**
- Modify: `backend/src/memory/lead_memory.py`
- Modify: `backend/tests/test_lead_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory.py`:

```python
class TestLeadMemoryServiceGetById:
    """Tests for LeadMemoryService.get_by_id()."""

    @pytest.fixture
    def mock_supabase_with_lead(self) -> MagicMock:
        """Create a mocked Supabase client with lead data."""
        mock_client = MagicMock()
        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = {
            "id": "lead-123",
            "user_id": "user-456",
            "company_id": None,
            "company_name": "Acme Corp",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 75,
            "crm_id": None,
            "crm_provider": None,
            "first_touch_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "expected_close_date": None,
            "expected_value": None,
            "tags": ["enterprise"],
            "metadata": {"trigger": "manual"},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
        return mock_client

    @pytest.mark.asyncio
    async def test_get_by_id_returns_lead(self, mock_supabase_with_lead: MagicMock) -> None:
        """Test get_by_id returns the correct lead."""
        from src.memory.lead_memory import LeadMemoryService, LifecycleStage

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_with_lead):
            service = LeadMemoryService()
            lead = await service.get_by_id(user_id="user-456", lead_id="lead-123")

        assert lead.id == "lead-123"
        assert lead.company_name == "Acme Corp"
        assert lead.lifecycle_stage == LifecycleStage.LEAD

    @pytest.mark.asyncio
    async def test_get_by_id_not_found_raises_error(self) -> None:
        """Test get_by_id raises LeadNotFoundError when lead doesn't exist."""
        from src.core.exceptions import LeadNotFoundError
        from src.memory.lead_memory import LeadMemoryService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = None
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_client):
            service = LeadMemoryService()
            with pytest.raises(LeadNotFoundError) as exc_info:
                await service.get_by_id(user_id="user-456", lead_id="nonexistent")

            assert "nonexistent" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceGetById -v`
Expected: FAIL with "AttributeError: 'LeadMemoryService' object has no attribute 'get_by_id'"

**Step 3: Write minimal implementation**

Add to `LeadMemoryService` class in `backend/src/memory/lead_memory.py`:

```python
    async def get_by_id(self, user_id: str, lead_id: str) -> LeadMemory:
        """Retrieve a specific lead by ID.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID.

        Returns:
            The requested LeadMemory.

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            LeadMemoryError: If retrieval fails.
        """
        from src.core.exceptions import LeadNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("lead_memories")
                .select("*")
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise LeadNotFoundError(lead_id)

            # Extract trigger from metadata if present
            data = response.data
            if "trigger" not in data and data.get("metadata", {}).get("trigger"):
                data["trigger"] = data["metadata"]["trigger"]
            elif "trigger" not in data:
                data["trigger"] = "manual"

            return LeadMemory.from_dict(data)

        except LeadNotFoundError:
            raise
        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get lead", extra={"lead_id": lead_id})
            raise LeadMemoryError(f"Failed to get lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceGetById -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory.py backend/tests/test_lead_memory.py
git commit -m "feat(lead-memory): implement LeadMemoryService.get_by_id()"
```

---

## Task 6: Implement LeadMemoryService.update()

**Files:**
- Modify: `backend/src/memory/lead_memory.py`
- Modify: `backend/tests/test_lead_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory.py`:

```python
class TestLeadMemoryServiceUpdate:
    """Tests for LeadMemoryService.update()."""

    @pytest.fixture
    def mock_supabase_update(self) -> MagicMock:
        """Create a mocked Supabase client for updates."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "lead-123"}]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_response
        return mock_client

    @pytest.mark.asyncio
    async def test_update_lead_fields(self, mock_supabase_update: MagicMock) -> None:
        """Test updating lead fields."""
        from src.memory.lead_memory import LeadMemoryService

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_update):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                await service.update(
                    user_id="user-456",
                    lead_id="lead-123",
                    company_name="Acme Corp Updated",
                    health_score=85,
                    tags=["enterprise", "priority"],
                )

        # Verify update was called with correct data
        update_call = mock_supabase_update.table.return_value.update
        update_call.assert_called_once()
        update_data = update_call.call_args[0][0]
        assert update_data["company_name"] == "Acme Corp Updated"
        assert update_data["health_score"] == 85
        assert update_data["tags"] == ["enterprise", "priority"]

    @pytest.mark.asyncio
    async def test_update_lead_updates_last_activity(self, mock_supabase_update: MagicMock) -> None:
        """Test that update sets last_activity_at."""
        from src.memory.lead_memory import LeadMemoryService

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_update):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                await service.update(
                    user_id="user-456",
                    lead_id="lead-123",
                    company_name="New Name",
                )

        update_data = mock_supabase_update.table.return_value.update.call_args[0][0]
        assert "last_activity_at" in update_data
        assert "updated_at" in update_data

    @pytest.mark.asyncio
    async def test_update_lead_not_found_raises_error(self) -> None:
        """Test update raises LeadNotFoundError when lead doesn't exist."""
        from src.core.exceptions import LeadNotFoundError
        from src.memory.lead_memory import LeadMemoryService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_response

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_client):
            service = LeadMemoryService()
            with pytest.raises(LeadNotFoundError):
                await service.update(
                    user_id="user-456",
                    lead_id="nonexistent",
                    company_name="New Name",
                )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceUpdate -v`
Expected: FAIL with "AttributeError: 'LeadMemoryService' object has no attribute 'update'"

**Step 3: Write minimal implementation**

Add to `LeadMemoryService` class:

```python
    async def update(
        self,
        user_id: str,
        lead_id: str,
        company_name: str | None = None,
        health_score: int | None = None,
        crm_id: str | None = None,
        crm_provider: str | None = None,
        expected_close_date: date | None = None,
        expected_value: Decimal | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update an existing lead.

        Only provided fields will be updated. None values are ignored.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID to update.
            company_name: Optional new company name.
            health_score: Optional new health score (0-100).
            crm_id: Optional CRM record ID.
            crm_provider: Optional CRM provider.
            expected_close_date: Optional expected close date.
            expected_value: Optional expected deal value.
            tags: Optional new tags list.
            metadata: Optional metadata to merge.

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            LeadMemoryError: If update fails.
        """
        from src.core.exceptions import LeadNotFoundError

        try:
            client = self._get_supabase_client()
            now = datetime.now(UTC)

            # Build update data from provided fields
            data: dict[str, Any] = {
                "last_activity_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            if company_name is not None:
                data["company_name"] = company_name
            if health_score is not None:
                data["health_score"] = health_score
            if crm_id is not None:
                data["crm_id"] = crm_id
            if crm_provider is not None:
                data["crm_provider"] = crm_provider
            if expected_close_date is not None:
                data["expected_close_date"] = expected_close_date.isoformat()
            if expected_value is not None:
                data["expected_value"] = float(expected_value)
            if tags is not None:
                data["tags"] = tags
            if metadata is not None:
                data["metadata"] = metadata

            response = (
                client.table("lead_memories")
                .update(data)
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise LeadNotFoundError(lead_id)

            logger.info(
                "Updated lead",
                extra={
                    "lead_id": lead_id,
                    "user_id": user_id,
                    "updated_fields": list(data.keys()),
                },
            )

            # Audit log the update
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.UPDATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={"updated_fields": list(data.keys())},
                suppress_errors=True,
            )

        except LeadNotFoundError:
            raise
        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to update lead", extra={"lead_id": lead_id})
            raise LeadMemoryError(f"Failed to update lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceUpdate -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory.py backend/tests/test_lead_memory.py
git commit -m "feat(lead-memory): implement LeadMemoryService.update()"
```

---

## Task 7: Implement LeadMemoryService.list_by_user() with Filters

**Files:**
- Modify: `backend/src/memory/lead_memory.py`
- Modify: `backend/tests/test_lead_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory.py`:

```python
class TestLeadMemoryServiceListByUser:
    """Tests for LeadMemoryService.list_by_user()."""

    @pytest.fixture
    def mock_supabase_list(self) -> MagicMock:
        """Create a mocked Supabase client with multiple leads."""
        mock_client = MagicMock()
        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "lead-1",
                "user_id": "user-456",
                "company_id": None,
                "company_name": "Acme Corp",
                "lifecycle_stage": "lead",
                "status": "active",
                "health_score": 75,
                "crm_id": None,
                "crm_provider": None,
                "first_touch_at": now.isoformat(),
                "last_activity_at": now.isoformat(),
                "expected_close_date": None,
                "expected_value": None,
                "tags": ["enterprise"],
                "metadata": {"trigger": "manual"},
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
            {
                "id": "lead-2",
                "user_id": "user-456",
                "company_id": None,
                "company_name": "Beta Inc",
                "lifecycle_stage": "opportunity",
                "status": "active",
                "health_score": 90,
                "crm_id": None,
                "crm_provider": None,
                "first_touch_at": now.isoformat(),
                "last_activity_at": now.isoformat(),
                "expected_close_date": None,
                "expected_value": "50000",
                "tags": ["smb"],
                "metadata": {"trigger": "inbound"},
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        ]

        # Create a proper chain mock
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_order = MagicMock()
        mock_limit = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.eq.return_value = mock_eq
        mock_eq.gte.return_value = mock_eq
        mock_eq.lte.return_value = mock_eq
        mock_eq.order.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.execute.return_value = mock_response

        return mock_client

    @pytest.mark.asyncio
    async def test_list_by_user_returns_all_leads(self, mock_supabase_list: MagicMock) -> None:
        """Test list_by_user returns all leads for a user."""
        from src.memory.lead_memory import LeadMemoryService

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_list):
            service = LeadMemoryService()
            leads = await service.list_by_user(user_id="user-456")

        assert len(leads) == 2
        assert leads[0].id == "lead-1"
        assert leads[1].id == "lead-2"

    @pytest.mark.asyncio
    async def test_list_by_user_with_status_filter(self, mock_supabase_list: MagicMock) -> None:
        """Test list_by_user filters by status."""
        from src.memory.lead_memory import LeadMemoryService, LeadStatus

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_list):
            service = LeadMemoryService()
            leads = await service.list_by_user(
                user_id="user-456",
                status=LeadStatus.ACTIVE,
            )

        # Verify the eq filter was called with status
        calls = mock_supabase_list.table.return_value.select.return_value.eq.call_args_list
        status_call = [c for c in calls if c[0][0] == "status"]
        assert len(status_call) == 1
        assert status_call[0][0][1] == "active"

    @pytest.mark.asyncio
    async def test_list_by_user_with_stage_filter(self, mock_supabase_list: MagicMock) -> None:
        """Test list_by_user filters by lifecycle stage."""
        from src.memory.lead_memory import LeadMemoryService, LifecycleStage

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_list):
            service = LeadMemoryService()
            leads = await service.list_by_user(
                user_id="user-456",
                lifecycle_stage=LifecycleStage.OPPORTUNITY,
            )

        calls = mock_supabase_list.table.return_value.select.return_value.eq.call_args_list
        stage_call = [c for c in calls if c[0][0] == "lifecycle_stage"]
        assert len(stage_call) == 1
        assert stage_call[0][0][1] == "opportunity"

    @pytest.mark.asyncio
    async def test_list_by_user_with_health_range(self, mock_supabase_list: MagicMock) -> None:
        """Test list_by_user filters by health score range."""
        from src.memory.lead_memory import LeadMemoryService

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_list):
            service = LeadMemoryService()
            leads = await service.list_by_user(
                user_id="user-456",
                min_health_score=70,
                max_health_score=95,
            )

        # The mock should have been called with gte and lte
        mock_query = mock_supabase_list.table.return_value.select.return_value.eq.return_value
        mock_query.gte.assert_called()
        mock_query.lte.assert_called()

    @pytest.mark.asyncio
    async def test_list_by_user_with_limit(self, mock_supabase_list: MagicMock) -> None:
        """Test list_by_user respects limit parameter."""
        from src.memory.lead_memory import LeadMemoryService

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_list):
            service = LeadMemoryService()
            leads = await service.list_by_user(user_id="user-456", limit=10)

        mock_supabase_list.table.return_value.select.return_value.eq.return_value.order.return_value.limit.assert_called_with(10)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceListByUser -v`
Expected: FAIL with "AttributeError: 'LeadMemoryService' object has no attribute 'list_by_user'"

**Step 3: Write minimal implementation**

Add to `LeadMemoryService` class:

```python
    async def list_by_user(
        self,
        user_id: str,
        status: LeadStatus | None = None,
        lifecycle_stage: LifecycleStage | None = None,
        min_health_score: int | None = None,
        max_health_score: int | None = None,
        limit: int = 50,
    ) -> list[LeadMemory]:
        """List all leads for a user with optional filters.

        Args:
            user_id: The user to list leads for.
            status: Optional filter by lead status.
            lifecycle_stage: Optional filter by lifecycle stage.
            min_health_score: Optional minimum health score.
            max_health_score: Optional maximum health score.
            limit: Maximum number of leads to return.

        Returns:
            List of LeadMemory instances matching the filters.

        Raises:
            LeadMemoryError: If the query fails.
        """
        try:
            client = self._get_supabase_client()

            query = client.table("lead_memories").select("*").eq("user_id", user_id)

            if status is not None:
                query = query.eq("status", status.value)

            if lifecycle_stage is not None:
                query = query.eq("lifecycle_stage", lifecycle_stage.value)

            if min_health_score is not None:
                query = query.gte("health_score", min_health_score)

            if max_health_score is not None:
                query = query.lte("health_score", max_health_score)

            response = query.order("last_activity_at", desc=True).limit(limit).execute()

            if not response.data:
                return []

            leads = []
            for row in response.data:
                # Extract trigger from metadata if not present
                if "trigger" not in row and row.get("metadata", {}).get("trigger"):
                    row["trigger"] = row["metadata"]["trigger"]
                elif "trigger" not in row:
                    row["trigger"] = "manual"
                leads.append(LeadMemory.from_dict(row))

            logger.info(
                "Listed leads",
                extra={
                    "user_id": user_id,
                    "count": len(leads),
                    "filters": {
                        "status": status.value if status else None,
                        "lifecycle_stage": lifecycle_stage.value if lifecycle_stage else None,
                        "min_health_score": min_health_score,
                        "max_health_score": max_health_score,
                    },
                },
            )

            return leads

        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to list leads")
            raise LeadMemoryError(f"Failed to list leads: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceListByUser -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory.py backend/tests/test_lead_memory.py
git commit -m "feat(lead-memory): implement LeadMemoryService.list_by_user() with filters"
```

---

## Task 8: Implement LeadMemoryService.transition_stage()

**Files:**
- Modify: `backend/src/memory/lead_memory.py`
- Modify: `backend/tests/test_lead_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory.py`:

```python
class TestLeadMemoryServiceTransitionStage:
    """Tests for LeadMemoryService.transition_stage()."""

    @pytest.fixture
    def mock_supabase_transition(self) -> MagicMock:
        """Create a mocked Supabase client for stage transitions."""
        mock_client = MagicMock()
        now = datetime.now(UTC)

        # Mock for get_by_id (select)
        mock_get_response = MagicMock()
        mock_get_response.data = {
            "id": "lead-123",
            "user_id": "user-456",
            "company_id": None,
            "company_name": "Acme Corp",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 75,
            "crm_id": None,
            "crm_provider": None,
            "first_touch_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "expected_close_date": None,
            "expected_value": None,
            "tags": [],
            "metadata": {"trigger": "manual", "stage_history": []},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # Mock for update
        mock_update_response = MagicMock()
        mock_update_response.data = [{"id": "lead-123"}]

        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        # Set up select chain
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_get_response

        # Set up update chain
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value.eq.return_value.execute.return_value = mock_update_response

        return mock_client

    @pytest.mark.asyncio
    async def test_transition_lead_to_opportunity(self, mock_supabase_transition: MagicMock) -> None:
        """Test transitioning from lead to opportunity."""
        from src.memory.lead_memory import LeadMemoryService, LifecycleStage

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_transition):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                await service.transition_stage(
                    user_id="user-456",
                    lead_id="lead-123",
                    new_stage=LifecycleStage.OPPORTUNITY,
                )

        # Verify update was called with new stage
        update_call = mock_supabase_transition.table.return_value.update
        update_call.assert_called_once()
        update_data = update_call.call_args[0][0]
        assert update_data["lifecycle_stage"] == "opportunity"

    @pytest.mark.asyncio
    async def test_transition_preserves_history(self, mock_supabase_transition: MagicMock) -> None:
        """Test that stage transition preserves history in metadata."""
        from src.memory.lead_memory import LeadMemoryService, LifecycleStage

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_transition):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                await service.transition_stage(
                    user_id="user-456",
                    lead_id="lead-123",
                    new_stage=LifecycleStage.OPPORTUNITY,
                )

        update_data = mock_supabase_transition.table.return_value.update.call_args[0][0]
        metadata = update_data["metadata"]
        assert "stage_history" in metadata
        assert len(metadata["stage_history"]) == 1
        assert metadata["stage_history"][0]["from_stage"] == "lead"
        assert metadata["stage_history"][0]["to_stage"] == "opportunity"

    @pytest.mark.asyncio
    async def test_transition_invalid_backward_raises_error(self) -> None:
        """Test that invalid backward transition raises error."""
        from src.core.exceptions import InvalidStageTransitionError
        from src.memory.lead_memory import LeadMemoryService, LifecycleStage

        mock_client = MagicMock()
        now = datetime.now(UTC)

        # Lead is already at opportunity stage
        mock_get_response = MagicMock()
        mock_get_response.data = {
            "id": "lead-123",
            "user_id": "user-456",
            "company_id": None,
            "company_name": "Acme Corp",
            "lifecycle_stage": "opportunity",  # Current stage
            "status": "active",
            "health_score": 75,
            "crm_id": None,
            "crm_provider": None,
            "first_touch_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "expected_close_date": None,
            "expected_value": None,
            "tags": [],
            "metadata": {"trigger": "manual"},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_get_response

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_client):
            service = LeadMemoryService()
            with pytest.raises(InvalidStageTransitionError) as exc_info:
                await service.transition_stage(
                    user_id="user-456",
                    lead_id="lead-123",
                    new_stage=LifecycleStage.LEAD,  # Trying to go backward
                )

            assert "opportunity" in str(exc_info.value)
            assert "lead" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transition_same_stage_is_noop(self, mock_supabase_transition: MagicMock) -> None:
        """Test transitioning to same stage does nothing."""
        from src.memory.lead_memory import LeadMemoryService, LifecycleStage

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_transition):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                await service.transition_stage(
                    user_id="user-456",
                    lead_id="lead-123",
                    new_stage=LifecycleStage.LEAD,  # Same as current
                )

        # Update should not be called for same stage
        mock_supabase_transition.table.return_value.update.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceTransitionStage -v`
Expected: FAIL with "AttributeError: 'LeadMemoryService' object has no attribute 'transition_stage'"

**Step 3: Write minimal implementation**

Add to `LeadMemoryService` class:

```python
    # Class-level constant for valid stage transitions
    _STAGE_ORDER = [LifecycleStage.LEAD, LifecycleStage.OPPORTUNITY, LifecycleStage.ACCOUNT]

    async def transition_stage(
        self,
        user_id: str,
        lead_id: str,
        new_stage: LifecycleStage,
    ) -> None:
        """Transition a lead to a new lifecycle stage.

        Stages can only progress forward: lead → opportunity → account.
        History is preserved in metadata.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID to transition.
            new_stage: The target lifecycle stage.

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            InvalidStageTransitionError: If transition is not allowed.
            LeadMemoryError: If transition fails.
        """
        from src.core.exceptions import InvalidStageTransitionError

        try:
            # Get current lead
            lead = await self.get_by_id(user_id, lead_id)

            # No-op if same stage
            if lead.lifecycle_stage == new_stage:
                logger.info(
                    "Stage transition is no-op (same stage)",
                    extra={"lead_id": lead_id, "stage": new_stage.value},
                )
                return

            # Validate forward-only progression
            current_index = self._STAGE_ORDER.index(lead.lifecycle_stage)
            target_index = self._STAGE_ORDER.index(new_stage)

            if target_index <= current_index:
                raise InvalidStageTransitionError(
                    current_stage=lead.lifecycle_stage.value,
                    target_stage=new_stage.value,
                )

            # Build stage history entry
            now = datetime.now(UTC)
            history_entry = {
                "from_stage": lead.lifecycle_stage.value,
                "to_stage": new_stage.value,
                "transitioned_at": now.isoformat(),
            }

            # Get existing history or create new
            existing_metadata = lead.metadata or {}
            stage_history = existing_metadata.get("stage_history", [])
            stage_history.append(history_entry)

            # Update metadata with preserved history
            updated_metadata = {
                **existing_metadata,
                "stage_history": stage_history,
            }

            # Perform update
            client = self._get_supabase_client()
            data = {
                "lifecycle_stage": new_stage.value,
                "metadata": updated_metadata,
                "last_activity_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            response = (
                client.table("lead_memories")
                .update(data)
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                from src.core.exceptions import LeadNotFoundError
                raise LeadNotFoundError(lead_id)

            logger.info(
                "Transitioned lead stage",
                extra={
                    "lead_id": lead_id,
                    "user_id": user_id,
                    "from_stage": lead.lifecycle_stage.value,
                    "to_stage": new_stage.value,
                },
            )

            # Audit log the transition
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.UPDATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={
                    "action": "stage_transition",
                    "from_stage": lead.lifecycle_stage.value,
                    "to_stage": new_stage.value,
                },
                suppress_errors=True,
            )

        except (InvalidStageTransitionError, LeadMemoryError):
            raise
        except Exception as e:
            logger.exception("Failed to transition stage", extra={"lead_id": lead_id})
            raise LeadMemoryError(f"Failed to transition stage: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryServiceTransitionStage -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory.py backend/tests/test_lead_memory.py
git commit -m "feat(lead-memory): implement LeadMemoryService.transition_stage() preserving history"
```

---

## Task 9: Export Lead Memory from Module

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory.py`:

```python
class TestLeadMemoryModuleExports:
    """Tests for lead memory module exports."""

    def test_lead_memory_exported_from_memory_module(self) -> None:
        """Test LeadMemory classes are exported from memory module."""
        from src.memory import (
            LeadMemory,
            LeadMemoryService,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        assert LeadMemory is not None
        assert LeadMemoryService is not None
        assert LeadStatus is not None
        assert LifecycleStage is not None
        assert TriggerType is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryModuleExports -v`
Expected: FAIL with "cannot import name 'LeadMemory' from 'src.memory'"

**Step 3: Write minimal implementation**

Edit `backend/src/memory/__init__.py`, add imports and exports:

After the existing imports (around line 45), add:

```python
from src.memory.lead_memory import (
    LeadMemory,
    LeadMemoryService,
    LeadStatus,
    LifecycleStage,
    TriggerType,
)
```

In the `__all__` list, add after the "Corporate Memory" section:

```python
    # Lead Memory
    "LeadMemory",
    "LeadMemoryService",
    "LeadStatus",
    "LifecycleStage",
    "TriggerType",
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory.py::TestLeadMemoryModuleExports -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_lead_memory.py
git commit -m "feat(lead-memory): export LeadMemory classes from memory module"
```

---

## Task 10: Run Full Test Suite and Verify

**Files:**
- All lead memory files

**Step 1: Run all lead memory tests**

Run: `cd backend && pytest tests/test_lead_memory.py tests/test_lead_memory_exceptions.py tests/test_lead_memory_audit_enum.py -v`
Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd backend && mypy src/memory/lead_memory.py --strict`
Expected: No errors (or only minor type issues to fix)

**Step 3: Run linting**

Run: `cd backend && ruff check src/memory/lead_memory.py`
Expected: No errors (or fix any issues)

**Step 4: Run formatting**

Run: `cd backend && ruff format src/memory/lead_memory.py`
Expected: Files formatted

**Step 5: Run full backend tests**

Run: `cd backend && pytest tests/ -v --ignore=tests/integration`
Expected: All existing tests still pass

**Step 6: Final commit**

```bash
git add .
git commit -m "chore(lead-memory): complete US-502 Lead Memory Core Implementation"
```

---

## Acceptance Criteria Verification

After completing all tasks, verify:

- [x] `src/memory/lead_memory.py` created
- [x] `LifecycleStage` enum (lead, opportunity, account)
- [x] `LeadStatus` enum (active, won, lost, dormant)
- [x] `TriggerType` enum (email_approved, manual, crm_import, inbound)
- [x] `LeadMemory` dataclass with all fields
- [x] `LeadMemoryService.create()` with trigger tracking
- [x] `LeadMemoryService.update()` for field updates
- [x] `LeadMemoryService.get_by_id()`
- [x] `LeadMemoryService.list_by_user()` with filters
- [x] `LeadMemoryService.transition_stage()` preserving history
- [x] Unit tests for all operations
- [x] Exported from `src/memory/__init__.py`

---

## Notes

- **DRY**: Follows existing memory service patterns from ProceduralMemory
- **YAGNI**: Only implements methods specified in acceptance criteria
- **TDD**: Each task starts with failing test, then implementation
- **Frequent commits**: One logical change per commit
- **Forward-only transitions**: Stages can only progress lead → opportunity → account
- **History preservation**: Stage transitions are recorded in metadata

---

## Next Steps

After this plan completes:
1. Proceed to US-503: Lead Memory Event Tracking
2. Implement `LeadEvent` and `add_event()` method
3. Create API endpoints in US-507
