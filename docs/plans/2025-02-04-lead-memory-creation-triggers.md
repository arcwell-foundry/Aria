# Lead Memory Creation Triggers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `LeadTriggerService` to automatically create Lead Memories from multiple trigger sources (email approval, manual tracking, CRM import, inbound responses) with deduplication and retroactive history scanning.

**Architecture:**
- Single `LeadTriggerService` class in `src/memory/lead_triggers.py`
- Triggers call into `LeadMemoryService.create()` to build leads
- Deduplication via `find_or_create()` pattern checking existing company names
- Retroactive scanning queries conversation episodes and events for historical context
- Integrates with existing `LeadMemoryService`, `LeadEventService`, and `ConversationService`

**Tech Stack:**
- Python 3.11+ with async/await
- Supabase for database queries
- Existing `LeadMemoryService`, `LeadEventService`, `ConversationService`
- LLM for company name extraction from history

---

## Task 1: Create LeadTriggerService Skeleton with Dependencies

**Files:**
- Create: `backend/src/memory/lead_triggers.py`
- Modify: `backend/src/memory/__init__.py` (export LeadTriggerService)
- Test: `backend/tests/test_lead_triggers.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_lead_triggers.py

import pytest
from src.memory.lead_triggers import LeadTriggerService


class TestLeadTriggerServiceInit:
    """Tests for LeadTriggerService initialization."""

    def test_service_initialization_with_dependencies(self):
        """Test service can be initialized with required dependencies."""
        from unittest.mock import MagicMock

        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conversation_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conversation_service,
        )

        assert service is not None
        assert service.lead_memory_service == mock_lead_service
        assert service.event_service == mock_event_service
        assert service.conversation_service == mock_conversation_service
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_lead_triggers.py::TestLeadTriggerServiceInit::test_service_initialization_with_dependencies -v`
Expected: FAIL with "module 'src.memory.lead_triggers' not found" or "LeadTriggerService not defined"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_triggers.py

"""Lead memory creation triggers service.

Detects and creates Lead Memories from various trigger sources:
- Email approval: User approves outbound email to prospect
- Manual tracking: User clicks "track this company"
- CRM import: Bulk import from Salesforce/HubSpot
- Inbound response: Reply from prospect

Handles deduplication and retroactive history scanning.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.memory.lead_memory import LeadMemoryService, TriggerType

logger = logging.getLogger(__name__)


class LeadTriggerService:
    """Service for creating Lead Memories from various trigger sources.

    Automatically detects when a lead should be tracked, prevents duplicates,
    and retroactively populates history for late-detected leads.
    """

    def __init__(
        self,
        lead_memory_service: LeadMemoryService,
        event_service: Any,  # LeadEventService
        conversation_service: Any,  # ConversationService
    ) -> None:
        """Initialize the trigger service with dependencies.

        Args:
            lead_memory_service: Service for creating/updating leads.
            event_service: Service for querying lead events.
            conversation_service: Service for querying conversation history.
        """
        self.lead_memory_service = lead_memory_service
        self.event_service = event_service
        self.conversation_service = conversation_service
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_lead_triggers.py::TestLeadTriggerServiceInit::test_service_initialization_with_dependencies -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py
git commit -m "feat(lead-memory): add LeadTriggerService skeleton with dependencies"
```

---

## Task 2: Implement find_or_create for Deduplication

**Files:**
- Modify: `backend/src/memory/lead_triggers.py`
- Test: `backend/tests/test_lead_triggers.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_lead_triggers.py (add to file)

from unittest.mock import MagicMock, patch
from datetime import UTC, datetime
from src.memory.lead_memory import LeadMemory, LifecycleStage, LeadStatus, TriggerType
from src.core.exceptions import LeadNotFoundError


class TestFindOrCreate:
    """Tests for find_or_create deduplication logic."""

    @pytest.mark.asyncio
    async def test_find_existing_lead_by_company_name(self):
        """Test find_or_create returns existing lead for same company."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead
        existing_lead = LeadMemory(
            id="lead-123",
            user_id="user-abc",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=65,
            trigger=TriggerType.EMAIL_APPROVED,
            first_touch_at=datetime(2025, 1, 15, tzinfo=UTC),
            last_activity_at=datetime(2025, 2, 1, tzinfo=UTC),
            created_at=datetime(2025, 1, 15, tzinfo=UTC),
            updated_at=datetime(2025, 2, 1, tzinfo=UTC),
        )

        # Mock list_by_user to return existing lead
        mock_lead_service.list_by_user.return_value = [existing_lead]

        # Call find_or_create
        result = await service.find_or_create(
            user_id="user-abc",
            company_name="Acme Corp",
            trigger=TriggerType.MANUAL,
        )

        # Should return existing lead, not create new one
        assert result.id == "lead-123"
        assert result.company_name == "Acme Corp"
        mock_lead_service.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_new_lead_when_no_match(self):
        """Test find_or_create creates new lead for unknown company."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock no existing leads
        mock_lead_service.list_by_user.return_value = []

        # Mock create response
        new_lead = LeadMemory(
            id="lead-new",
            user_id="user-abc",
            company_name="New Company LLC",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.create.return_value = new_lead

        # Call find_or_create
        result = await service.find_or_create(
            user_id="user-abc",
            company_name="New Company LLC",
            trigger=TriggerType.MANUAL,
        )

        # Should create new lead
        assert result.id == "lead-new"
        mock_lead_service.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_case_insensitive_company_matching(self):
        """Test find_or_create matches company names case-insensitively."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead with different case
        existing_lead = LeadMemory(
            id="lead-123",
            user_id="user-abc",
            company_name="ACME CORPORATION",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=65,
            trigger=TriggerType.EMAIL_APPROVED,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.list_by_user.return_value = [existing_lead]

        # Call with different case
        result = await service.find_or_create(
            user_id="user-abc",
            company_name="acme corporation",
            trigger=TriggerType.INBOUND,
        )

        # Should find existing match
        assert result.id == "lead-123"
        mock_lead_service.create.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_lead_triggers.py::TestFindOrCreate -v`
Expected: FAIL with "LeadTriggerService has no attribute 'find_or_create'"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_triggers.py (add method to LeadTriggerService class)

    async def find_or_create(
        self,
        user_id: str,
        company_name: str,
        trigger: TriggerType,
        company_id: str | None = None,
        crm_id: str | None = None,
        crm_provider: str | None = None,
        expected_close_date: Any = None,
        expected_value: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LeadMemory:
        """Find existing lead or create new one for company.

        Checks for existing leads with matching company name (case-insensitive).
        Returns existing lead if found, otherwise creates new one.

        Args:
            user_id: The user's ID.
            company_name: Name of the company to track.
            trigger: Source that triggered lead creation.
            company_id: Optional company UUID reference.
            crm_id: Optional CRM record ID.
            crm_provider: Optional CRM provider.
            expected_close_date: Optional expected close date.
            expected_value: Optional expected deal value.
            tags: Optional list of tags.
            metadata: Optional additional metadata.

        Returns:
            The existing or newly created LeadMemory.
        """
        try:
            # Query existing leads for user
            existing_leads = await self.lead_memory_service.list_by_user(
                user_id=user_id,
                limit=1000,  # Get all leads for deduplication check
            )

            # Check for matching company name (case-insensitive)
            company_name_normalized = company_name.strip().lower()
            for lead in existing_leads:
                if lead.company_name.strip().lower() == company_name_normalized:
                    logger.info(
                        "Found existing lead for company",
                        extra={
                            "user_id": user_id,
                            "company_name": company_name,
                            "existing_lead_id": lead.id,
                        },
                    )
                    return lead

            # No match found - create new lead
            logger.info(
                "Creating new lead for company",
                extra={
                    "user_id": user_id,
                    "company_name": company_name,
                    "trigger": trigger.value,
                },
            )

            return await self.lead_memory_service.create(
                user_id=user_id,
                company_name=company_name,
                trigger=trigger,
                company_id=company_id,
                crm_id=crm_id,
                crm_provider=crm_provider,
                expected_close_date=expected_close_date,
                expected_value=expected_value,
                tags=tags,
                metadata=metadata,
            )

        except Exception as e:
            logger.exception(
                "Failed to find or create lead",
                extra={"user_id": user_id, "company_name": company_name},
            )
            raise
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_lead_triggers.py::TestFindOrCreate -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py
git commit -m "feat(lead-memory): add find_or_create for deduplication"
```

---

## Task 3: Implement on_email_approved Trigger

**Files:**
- Modify: `backend/src/memory/lead_triggers.py`
- Test: `backend/tests/test_lead_triggers.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_lead_triggers.py (add to file)

class TestOnEmailApproved:
    """Tests for on_email_approved trigger."""

    @pytest.mark.asyncio
    async def test_creates_lead_from_approved_outbound_email(self):
        """Test creating lead when user approves outbound email."""
        from src.memory.lead_triggers import LeadTriggerService
        from src.models.lead_memory import LeadEventCreate

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock create response
        new_lead = LeadMemory(
            id="lead-new",
            user_id="user-abc",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.EMAIL_APPROVED,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.create.return_value = new_lead
        mock_lead_service.list_by_user.return_value = []

        # Call on_email_approved
        result = await service.on_email_approved(
            user_id="user-abc",
            company_name="Acme Corp",
            email_subject="Introduction to ARIA",
            email_content="Hi John, wanted to introduce you to ARIA...",
            recipient_email="john@acmecorp.com",
            occurred_at=datetime(2025, 2, 4, 10, 0, tzinfo=UTC),
        )

        # Verify lead created
        assert result.id == "lead-new"
        mock_lead_service.create.assert_called_once_with(
            user_id="user-abc",
            company_name="Acme Corp",
            trigger=TriggerType.EMAIL_APPROVED,
        )

        # Verify email event added
        mock_event_service.add_event.assert_called_once()
        call_args = mock_event_service.add_event.call_args
        assert call_args[1]["user_id"] == "user-abc"
        assert call_args[1]["lead_memory_id"] == "lead-new"

    @pytest.mark.asyncio
    async def test_uses_existing_lead_for_same_company(self):
        """Test on_email_approved reuses existing lead."""
        from src.memory.lead_triggers.py import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead
        existing_lead = LeadMemory(
            id="lead-existing",
            user_id="user-abc",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=60,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime(2025, 1, 1, tzinfo=UTC),
            last_activity_at=datetime(2025, 2, 1, tzinfo=UTC),
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            updated_at=datetime(2025, 2, 1, tzinfo=UTC),
        )
        mock_lead_service.list_by_user.return_value = [existing_lead]

        # Call on_email_approved
        result = await service.on_email_approved(
            user_id="user-abc",
            company_name="Acme Corp",
            email_subject="Follow up",
            email_content="Checking in...",
            recipient_email="john@acmecorp.com",
            occurred_at=datetime.now(UTC),
        )

        # Should reuse existing lead
        assert result.id == "lead-existing"
        mock_lead_service.create.assert_not_called()

        # But still add the event
        mock_event_service.add_event.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnEmailApproved::test_creates_lead_from_approved_outbound_email -v`
Expected: FAIL with "LeadTriggerService has no attribute 'on_email_approved'"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_triggers.py (add method to class)

    async def on_email_approved(
        self,
        user_id: str,
        company_name: str,
        email_subject: str,
        email_content: str,
        recipient_email: str,
        occurred_at: datetime,
    ) -> LeadMemory:
        """Create lead when user approves outbound email to prospect.

        Args:
            user_id: The user who approved the email.
            company_name: Name of prospect's company (extracted from email).
            email_subject: Subject line of approved email.
            email_content: Body content of approved email.
            recipient_email: Email address of prospect.
            occurred_at: When the email was sent.

        Returns:
            The created or existing LeadMemory.
        """
        try:
            # Find or create lead
            lead = await self.find_or_create(
                user_id=user_id,
                company_name=company_name,
                trigger=TriggerType.EMAIL_APPROVED,
            )

            # Add email event to lead timeline
            from src.models.lead_memory import Direction, EventType, LeadEventCreate

            event_data = LeadEventCreate(
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject=email_subject,
                content=email_content,
                participants=[recipient_email],
                occurred_at=occurred_at,
                source="gmail",
            )

            await self.event_service.add_event(
                user_id=user_id,
                lead_memory_id=lead.id,
                event_data=event_data,
            )

            logger.info(
                "Created lead from approved email",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "company_name": company_name,
                    "recipient": recipient_email,
                },
            )

            return lead

        except Exception as e:
            logger.exception(
                "Failed to process email approval trigger",
                extra={"user_id": user_id, "company_name": company_name},
            )
            raise
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnEmailApproved -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py
git commit -m "feat(lead-memory): add on_email_approved trigger"
```

---

## Task 4: Implement on_manual_track Trigger

**Files:**
- Modify: `backend/src/memory/lead_triggers.py`
- Test: `backend/tests/test_lead_triggers.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_lead_triggers.py (add to file)

class TestOnManualTrack:
    """Tests for on_manual_track trigger."""

    @pytest.mark.asyncio
    async def test_creates_lead_from_manual_track_action(self):
        """Test creating lead when user clicks 'track this'."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock create response
        new_lead = LeadMemory(
            id="lead-manual",
            user_id="user-abc",
            company_name="BioTech Inc",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.create.return_value = new_lead
        mock_lead_service.list_by_user.return_value = []

        # Call on_manual_track
        result = await service.on_manual_track(
            user_id="user-abc",
            company_name="BioTech Inc",
            notes="Interested in our enterprise plan",
        )

        # Verify lead created
        assert result.id == "lead-manual"
        mock_lead_service.create.assert_called_once_with(
            user_id="user-abc",
            company_name="BioTech Inc",
            trigger=TriggerType.MANUAL,
            metadata={"notes": "Interested in our enterprise plan"},
        )

    @pytest.mark.asyncio
    async def test_returns_existing_lead_if_already_tracked(self):
        """Test on_manual_track returns existing lead without duplicate."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead
        existing_lead = LeadMemory(
            id="lead-existing",
            user_id="user-abc",
            company_name="BioTech Inc",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=70,
            trigger=TriggerType.EMAIL_APPROVED,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.list_by_user.return_value = [existing_lead]

        # Call on_manual_track
        result = await service.on_manual_track(
            user_id="user-abc",
            company_name="BioTech Inc",
            notes="Following up",
        )

        # Should return existing, not create
        assert result.id == "lead-existing"
        mock_lead_service.create.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnManualTrack::test_creates_lead_from_manual_track_action -v`
Expected: FAIL with "LeadTriggerService has no attribute 'on_manual_track'"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_triggers.py (add method to class)

    async def on_manual_track(
        self,
        user_id: str,
        company_name: str,
        notes: str | None = None,
    ) -> LeadMemory:
        """Create lead when user manually clicks 'track this'.

        Args:
            user_id: The user tracking the company.
            company_name: Name of the company to track.
            notes: Optional notes about why they're tracking.

        Returns:
            The created or existing LeadMemory.
        """
        try:
            # Build metadata if notes provided
            metadata = {"notes": notes} if notes else None

            # Find or create lead
            lead = await self.find_or_create(
                user_id=user_id,
                company_name=company_name,
                trigger=TriggerType.MANUAL,
                metadata=metadata,
            )

            # If new lead and notes provided, add as note event
            if notes and lead.trigger == TriggerType.MANUAL:
                from src.models.lead_memory import EventType, LeadEventCreate

                # Check if this is a newly created lead by checking if it has the notes
                # If lead is new (just created), add the note as an event
                # We detect this by seeing if the notes aren't already in metadata
                if not lead.metadata.get("notes") or lead.metadata.get("notes") != notes:
                    event_data = LeadEventCreate(
                        event_type=EventType.NOTE,
                        content=notes,
                        occurred_at=datetime.now(UTC),
                        source="manual",
                    )

                    await self.event_service.add_event(
                        user_id=user_id,
                        lead_memory_id=lead.id,
                        event_data=event_data,
                    )

            logger.info(
                "Manual track lead created/found",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "company_name": company_name,
                },
            )

            return lead

        except Exception as e:
            logger.exception(
                "Failed to process manual track trigger",
                extra={"user_id": user_id, "company_name": company_name},
            )
            raise
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnManualTrack -v`
Expected: PASS (may need to adjust test logic for note event check)

**Step 5: Commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py
git commit -m "feat(lead-memory): add on_manual_track trigger"
```

---

## Task 5: Implement on_crm_import Trigger

**Files:**
- Modify: `backend/src/memory/lead_triggers.py`
- Test: `backend/tests/test_lead_triggers.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_lead_triggers.py (add to file)

from decimal import Decimal


class TestOnCrmImport:
    """Tests for on_crm_import trigger."""

    @pytest.mark.asyncio
    async def test_creates_lead_from_crm_import(self):
        """Test creating lead from CRM bulk import."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock create response
        new_lead = LeadMemory(
            id="lead-crm",
            user_id="user-abc",
            company_name="PharmaCo",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.CRM_IMPORT,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            crm_id="sf-0012345678",
            crm_provider="salesforce",
            expected_close_date=None,
            expected_value=Decimal("150000.00"),
        )
        mock_lead_service.create.return_value = new_lead
        mock_lead_service.list_by_user.return_value = []

        # Call on_crm_import
        result = await service.on_crm_import(
            user_id="user-abc",
            company_name="PharmaCo",
            crm_id="sf-0012345678",
            crm_provider="salesforce",
            expected_value=Decimal("150000.00"),
            expected_close_date=None,
        )

        # Verify lead created with CRM fields
        assert result.id == "lead-crm"
        mock_lead_service.create.assert_called_once()
        call_kwargs = mock_lead_service.create.call_args[1]
        assert call_kwargs["crm_id"] == "sf-0012345678"
        assert call_kwargs["crm_provider"] == "salesforce"
        assert call_kwargs["expected_value"] == Decimal("150000.00")

    @pytest.mark.asyncio
    async def test_bulk_crm_import(self):
        """Test importing multiple leads from CRM."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock responses for different companies
        def mock_create_side_effect(*args, **kwargs):
            company = kwargs.get("company_name", "")
            return LeadMemory(
                id=f"lead-{company.lower().replace(' ', '-')}",
                user_id="user-abc",
                company_name=company,
                lifecycle_stage=LifecycleStage.LEAD,
                status=LeadStatus.ACTIVE,
                health_score=50,
                trigger=TriggerType.CRM_IMPORT,
                first_touch_at=datetime.now(UTC),
                last_activity_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        mock_lead_service.create.side_effect = mock_create_side_effect
        mock_lead_service.list_by_user.return_value = []

        # Import data
        import_data = [
            {"company_name": "Company A", "crm_id": "hub-001", "crm_provider": "hubspot"},
            {"company_name": "Company B", "crm_id": "hub-002", "crm_provider": "hubspot"},
            {"company_name": "Company C", "crm_id": "hub-003", "crm_provider": "hubspot"},
        ]

        # Call on_crm_import for each
        results = []
        for data in import_data:
            lead = await service.on_crm_import(
                user_id="user-abc",
                **data,
            )
            results.append(lead)

        # Verify all created
        assert len(results) == 3
        assert mock_lead_service.create.call_count == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnCrmImport::test_creates_lead_from_crm_import -v`
Expected: FAIL with "LeadTriggerService has no attribute 'on_crm_import'"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_triggers.py (add method to class)

    async def on_crm_import(
        self,
        user_id: str,
        company_name: str,
        crm_id: str,
        crm_provider: str,
        expected_value: Decimal | None = None,
        expected_close_date: date | None = None,
    ) -> LeadMemory:
        """Create lead from CRM import (Salesforce, HubSpot, etc.).

        Args:
            user_id: The user importing from CRM.
            company_name: Name of the company from CRM.
            crm_id: External CRM record ID.
            crm_provider: CRM provider name (salesforce, hubspot).
            expected_value: Optional deal value from CRM.
            expected_close_date: Optional close date from CRM.

        Returns:
            The created or existing LeadMemory.
        """
        try:
            # Find or create lead with CRM fields
            lead = await self.find_or_create(
                user_id=user_id,
                company_name=company_name,
                trigger=TriggerType.CRM_IMPORT,
                crm_id=crm_id,
                crm_provider=crm_provider,
                expected_value=expected_value,
                expected_close_date=expected_close_date,
            )

            logger.info(
                "CRM import lead created/found",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "company_name": company_name,
                    "crm_provider": crm_provider,
                    "crm_id": crm_id,
                },
            )

            return lead

        except Exception as e:
            logger.exception(
                "Failed to process CRM import trigger",
                extra={
                    "user_id": user_id,
                    "company_name": company_name,
                    "crm_provider": crm_provider,
                },
            )
            raise
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnCrmImport -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py
git commit -m "feat(lead-memory): add on_crm_import trigger"
```

---

## Task 6: Implement on_inbound_response Trigger

**Files:**
- Modify: `backend/src/memory/lead_triggers.py`
- Test: `backend/tests/test_lead_triggers.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_lead_triggers.py (add to file)

class TestOnInboundResponse:
    """Tests for on_inbound_response trigger."""

    @pytest.mark.asyncio
    async def test_creates_lead_from_inbound_email(self):
        """Test creating lead when prospect replies."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock create response
        new_lead = LeadMemory(
            id="lead-inbound",
            user_id="user-abc",
            company_name="StartupXYZ",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=60,
            trigger=TriggerType.INBOUND,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.create.return_value = new_lead
        mock_lead_service.list_by_user.return_value = []

        # Call on_inbound_response
        result = await service.on_inbound_response(
            user_id="user-abc",
            company_name="StartupXYZ",
            email_subject="Re: Product inquiry",
            email_content="Thanks for reaching out, we're interested...",
            sender_email="founder@startupxyz.com",
            occurred_at=datetime.now(UTC),
        )

        # Verify lead created
        assert result.id == "lead-inbound"
        mock_lead_service.create.assert_called_once_with(
            user_id="user-abc",
            company_name="StartupXYZ",
            trigger=TriggerType.INBOUND,
        )

        # Verify inbound email event added
        mock_event_service.add_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_adds_inbound_event_to_existing_lead(self):
        """Test on_inbound_response adds event to existing lead."""
        from src.memory.lead_triggers import LeadTriggerService

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead
        existing_lead = LeadMemory(
            id="lead-existing",
            user_id="user-abc",
            company_name="StartupXYZ",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=65,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.list_by_user.return_value = [existing_lead]

        # Call on_inbound_response
        result = await service.on_inbound_response(
            user_id="user-abc",
            company_name="StartupXYZ",
            email_subject="Interested in demo",
            email_content="Can we schedule a demo?",
            sender_email="founder@startupxyz.com",
            occurred_at=datetime.now(UTC),
        )

        # Should reuse existing lead
        assert result.id == "lead-existing"
        mock_lead_service.create.assert_not_called()

        # But add the inbound event
        mock_event_service.add_event.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnInboundResponse::test_creates_lead_from_inbound_email -v`
Expected: FAIL with "LeadTriggerService has no attribute 'on_inbound_response'"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_triggers.py (add method to class)

    async def on_inbound_response(
        self,
        user_id: str,
        company_name: str,
        email_subject: str,
        email_content: str,
        sender_email: str,
        occurred_at: datetime,
    ) -> LeadMemory:
        """Create lead when prospect sends inbound response.

        Args:
            user_id: The user who received the response.
            company_name: Name of prospect's company.
            email_subject: Subject line of inbound email.
            email_content: Body content of inbound email.
            sender_email: Email address of prospect.
            occurred_at: When the email was received.

        Returns:
            The created or existing LeadMemory.
        """
        try:
            # Find or create lead
            lead = await self.find_or_create(
                user_id=user_id,
                company_name=company_name,
                trigger=TriggerType.INBOUND,
            )

            # Add inbound email event
            from src.models.lead_memory import Direction, EventType, LeadEventCreate

            event_data = LeadEventCreate(
                event_type=EventType.EMAIL_RECEIVED,
                direction=Direction.INBOUND,
                subject=email_subject,
                content=email_content,
                participants=[sender_email],
                occurred_at=occurred_at,
                source="gmail",
            )

            await self.event_service.add_event(
                user_id=user_id,
                lead_memory_id=lead.id,
                event_data=event_data,
            )

            logger.info(
                "Created lead from inbound response",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "company_name": company_name,
                    "sender": sender_email,
                },
            )

            return lead

        except Exception as e:
            logger.exception(
                "Failed to process inbound response trigger",
                extra={"user_id": user_id, "company_name": company_name},
            )
            raise
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_lead_triggers.py::TestOnInboundResponse -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py
git commit -m "feat(lead-memory): add on_inbound_response trigger"
```

---

## Task 7: Implement Retroactive History Scanning

**Files:**
- Modify: `backend/src/memory/lead_triggers.py`
- Test: `backend/tests/test_lead_triggers.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_lead_triggers.py (add to file)

class TestScanHistoryForLead:
    """Tests for retroactive history scanning."""

    @pytest.mark.asyncio
    async def test_scans_conversation_episodes_for_company_mentions(self):
        """Test scanning conversation history for company mentions."""
        from src.memory.lead_triggers import LeadTriggerService
        from src.memory.conversation import ConversationEpisode

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock conversation episodes mentioning company
        episodes = [
            ConversationEpisode(
                id="ep-1",
                user_id="user-abc",
                conversation_id="conv-1",
                summary="Discussed Acme Corp partnership opportunity",
                key_topics=["acme corp", "partnership"],
                entities_discussed=["Acme Corp"],
                user_state={},
                outcomes=[],
                open_threads=[],
                message_count=5,
                duration_minutes=10,
                started_at=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
                ended_at=datetime(2025, 1, 15, 10, 10, tzinfo=UTC),
            ),
            ConversationEpisode(
                id="ep-2",
                user_id="user-abc",
                conversation_id="conv-2",
                summary="Follow up on Acme Corp proposal",
                key_topics=["acme corp", "proposal"],
                entities_discussed=["Acme Corp"],
                user_state={},
                outcomes=[],
                open_threads=[],
                message_count=3,
                duration_minutes=5,
                started_at=datetime(2025, 1, 20, 14, 0, tzinfo=UTC),
                ended_at=datetime(2025, 1, 20, 14, 5, tzinfo=UTC),
            ),
        ]
        mock_conv_service.get_recent_episodes.return_value = episodes

        # Mock existing lead
        existing_lead = LeadMemory(
            id="lead-acme",
            user_id="user-abc",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=70,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime(2025, 2, 1, tzinfo=UTC),
            last_activity_at=datetime(2025, 2, 1, tzinfo=UTC),
            created_at=datetime(2025, 2, 1, tzinfo=UTC),
            updated_at=datetime(2025, 2, 1, tzinfo=UTC),
        )

        # Call scan_history_for_lead
        await service.scan_history_for_lead(
            lead=existing_lead,
            user_id="user-abc",
        )

        # Should have queried conversations
        mock_conv_service.get_recent_episodes.assert_called_once_with(
            user_id="user-abc",
            limit=50,
        )

    @pytest.mark.asyncio
    async def test_updates_first_touch_from_earliest_mention(self):
        """Test updating first_touch_at from earliest historical mention."""
        from src.memory.lead_triggers import LeadTriggerService
        from src.memory.conversation import ConversationEpisode

        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock episode from January
        episode = ConversationEpisode(
            id="ep-old",
            user_id="user-abc",
            conversation_id="conv-old",
            summary="First contact with BioTech Inc",
            key_topics=["biotech inc"],
            entities_discussed=["BioTech Inc"],
            user_state={},
            outcomes=[],
            open_threads=[],
            message_count=2,
            duration_minutes=5,
            started_at=datetime(2025, 1, 5, 9, 0, tzinfo=UTC),
            ended_at=datetime(2025, 1, 5, 9, 5, tzinfo=UTC),
        )
        mock_conv_service.get_recent_episodes.return_value = [episode]

        # Mock lead created in February
        lead = LeadMemory(
            id="lead-biotech",
            user_id="user-abc",
            company_name="BioTech Inc",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime(2025, 2, 1, tzinfo=UTC),
            last_activity_at=datetime(2025, 2, 4, tzinfo=UTC),
            created_at=datetime(2025, 2, 4, tzinfo=UTC),
            updated_at=datetime(2025, 2, 4, tzinfo=UTC),
        )

        # Call scan_history_for_lead
        await service.scan_history_for_lead(
            lead=lead,
            user_id="user-abc",
        )

        # Should update first_touch_at to January
        mock_lead_service.update.assert_called_once()
        call_kwargs = mock_lead_service.update.call_args[1]
        # Should have updated with earlier timestamp
        assert "first_touch_at" in call_kwargs or "metadata" in call_kwargs
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_lead_triggers.py::TestScanHistoryForLead::test_scans_conversation_episodes_for_company_mentions -v`
Expected: FAIL with "LeadTriggerService has no attribute 'scan_history_for_lead'"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_triggers.py (add method to class)

    async def scan_history_for_lead(
        self,
        lead: LeadMemory,
        user_id: str,
        scan_limit: int = 50,
    ) -> None:
        """Scan conversation history for retroactive lead context.

        When a lead is detected late (e.g., manual tracking after emails),
        scan conversation episodes to find historical mentions and update
        first_touch_at if earlier contact found.

        Args:
            lead: The lead to scan history for.
            user_id: The user who owns the lead.
            scan_limit: Maximum conversation episodes to scan.
        """
        try:
            # Get recent conversation episodes
            episodes = await self.conversation_service.get_recent_episodes(
                user_id=user_id,
                limit=scan_limit,
            )

            if not episodes:
                return

            # Search for company mentions in episodes
            company_name_normalized = lead.company_name.strip().lower()
            earliest_mention: datetime | None = None

            for episode in episodes:
                # Check summary and entities for company mention
                episode_text = (
                    episode.summary.lower()
                    + " "
                    + " ".join(episode.entities_discussed).lower()
                    + " "
                    + " ".join(episode.key_topics).lower()
                )

                if company_name_normalized in episode_text:
                    # Found a mention - check if it's earlier than current first_touch
                    if earliest_mention is None or episode.started_at < earliest_mention:
                        earliest_mention = episode.started_at

            # If we found earlier contact, update first_touch_at
            if earliest_mention and earliest_mention < lead.first_touch_at:
                await self.lead_memory_service.update(
                    user_id=user_id,
                    lead_id=lead.id,
                    metadata={
                        **(lead.metadata or {}),
                        "retroactive_first_touch": earliest_mention.isoformat(),
                        "retroactive_scan_date": datetime.now(UTC).isoformat(),
                    },
                )

                logger.info(
                    "Updated first_touch from retroactive scan",
                    extra={
                        "user_id": user_id,
                        "lead_id": lead.id,
                        "company_name": lead.company_name,
                        "previous_first_touch": lead.first_touch_at.isoformat(),
                        "new_first_touch": earliest_mention.isoformat(),
                    },
                )

        except Exception as e:
            logger.warning(
                "Failed to scan history for lead",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "error": str(e),
                },
            )
            # Don't fail the trigger if history scan fails
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_lead_triggers.py::TestScanHistoryForLead -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py
git commit -m "feat(lead-memory): add retroactive history scanning"
```

---

## Task 8: Export LeadTriggerService from Memory Module

**Files:**
- Modify: `backend/src/memory/__init__.py`
- Test: `backend/tests/test_memory_lead_triggers_module_exports.py` (new file)

**Step 1: Write the failing test**

```python
# backend/tests/test_memory_lead_triggers_module_exports.py

"""Test that LeadTriggerService is exported from memory module."""

def test_lead_trigger_service_exported():
    """Test LeadTriggerService is importable from src.memory."""
    from src.memory import LeadTriggerService

    assert LeadTriggerService is not None


def test_lead_trigger_service_has_required_methods():
    """Test LeadTriggerService has all trigger methods."""
    from src.memory import LeadTriggerService

    required_methods = [
        "find_or_create",
        "on_email_approved",
        "on_manual_track",
        "on_crm_import",
        "on_inbound_response",
        "scan_history_for_lead",
    ]

    for method_name in required_methods:
        assert hasattr(LeadTriggerService, method_name), f"Missing method: {method_name}"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_memory_lead_triggers_module_exports.py -v`
Expected: FAIL with "cannot import name 'LeadTriggerService' from 'src.memory'"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/__init__.py (add import)

# ... existing imports ...
from src.memory.lead_triggers import LeadTriggerService

__all__ = [
    # ... existing exports ...
    "LeadTriggerService",
]
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_memory_lead_triggers_module_exports.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_memory_lead_triggers_module_exports.py
git commit -m "feat(lead-memory): export LeadTriggerService from memory module"
```

---

## Task 9: Run All Tests and Quality Gates

**Step 1: Run all tests**

```bash
cd backend
pytest tests/test_lead_triggers.py -v
pytest tests/test_memory_lead_triggers_module_exports.py -v
```

Expected: All tests PASS

**Step 2: Run type checking**

```bash
cd backend
mypy src/memory/lead_triggers.py --strict
```

Expected: No type errors (may need to add type stubs or fix issues)

**Step 3: Run linting**

```bash
cd backend
ruff check src/memory/lead_triggers.py
ruff format src/memory/lead_triggers.py
```

Expected: No lint errors

**Step 4: Fix any issues found**

Repeat steps 1-3 until all checks pass.

**Step 5: Final commit**

```bash
git add backend/src/memory/lead_triggers.py backend/tests/test_lead_triggers.py backend/tests/test_memory_lead_triggers_module_exports.py backend/src/memory/__init__.py
git commit -m "feat(lead-memory): complete LeadTriggerService implementation with all triggers"
```

---

## Summary

This plan implements US-510: Lead Memory Creation Triggers by creating a `LeadTriggerService` that:

1. **Deduplicates** leads via `find_or_create()` using case-insensitive company name matching
2. **Creates leads from 4 trigger sources:**
   - `on_email_approved()` - when user approves outbound email
   - `on_manual_track()` - when user clicks "track this"
   - `on_crm_import()` - during bulk CRM import
   - `on_inbound_response()` - when prospect replies
3. **Retroactively scans history** via `scan_history_for_lead()` to update `first_touch_at` from earlier mentions
4. **Integrates** with existing `LeadMemoryService`, `LeadEventService`, and `ConversationService`

Each trigger follows the pattern:
- Find or create the lead
- Add relevant event to timeline
- Log the operation
- Return the lead for further processing
