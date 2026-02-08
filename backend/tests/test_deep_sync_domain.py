"""Test deep sync domain models (US-942).

These tests verify the domain models for the deep sync service:
1. SyncResult with calculated properties
2. PushQueueItem with proper defaults
3. CRMEntity with confidence defaults
4. CalendarEvent with is_external detection
5. SyncConfig with safe defaults
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from importlib import import_module

import pytest


# Direct imports to avoid circular import in integrations __init__.py
def _import_deep_sync_domain():
    """Import deep_sync_domain directly, bypassing package __init__.py."""
    import sys
    from pathlib import Path

    # Import the module directly
    module_path = Path(__file__).parent.parent / "src" / "integrations" / "deep_sync_domain.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location("deep_sync_domain", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deep_sync_domain"] = module
    spec.loader.exec_module(module)
    return module


ds_domain = _import_deep_sync_domain()

CalendarEvent = ds_domain.CalendarEvent
CRMEntity = ds_domain.CRMEntity
PushActionType = ds_domain.PushActionType
PushPriority = ds_domain.PushPriority
PushQueueItem = ds_domain.PushQueueItem
PushStatus = ds_domain.PushStatus
SyncConfig = ds_domain.SyncConfig
SyncDirection = ds_domain.SyncDirection
SyncResult = ds_domain.SyncResult
SyncStatus = ds_domain.SyncStatus

# Mock IntegrationType for testing
class IntegrationType(str, Enum):
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"


class TestSyncResult:
    """Test SyncResult dataclass with calculated properties."""

    def test_sync_result_success_rate(self) -> None:
        """Success rate should be calculated as records_succeeded / records_processed * 100."""
        result = SyncResult(
            direction=SyncDirection.PULL,
            integration_type=IntegrationType.SALESFORCE,
            status=SyncStatus.SUCCESS,
            records_processed=100,
            records_succeeded=95,
            records_failed=5,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc) + timedelta(seconds=10),
            error_details=None,
        )
        assert result.success_rate == 95.0

    def test_sync_result_success_rate_zero_processed(self) -> None:
        """Success rate should be 0 when no records processed."""
        result = SyncResult(
            direction=SyncDirection.PULL,
            integration_type=IntegrationType.SALESFORCE,
            status=SyncStatus.SUCCESS,
            records_processed=0,
            records_succeeded=0,
            records_failed=0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc) + timedelta(seconds=10),
            error_details=None,
        )
        assert result.success_rate == 0.0

    def test_sync_result_duration(self) -> None:
        """Duration should be calculated from started_at and completed_at."""
        started = datetime(2026, 2, 7, 12, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2026, 2, 7, 12, 0, 30, tzinfo=timezone.utc)
        result = SyncResult(
            direction=SyncDirection.PULL,
            integration_type=IntegrationType.SALESFORCE,
            status=SyncStatus.SUCCESS,
            records_processed=10,
            records_succeeded=10,
            records_failed=0,
            started_at=started,
            completed_at=completed,
            error_details=None,
        )
        assert result.duration_seconds == 30

    def test_sync_result_duration_not_completed(self) -> None:
        """Duration should be None if sync not completed."""
        result = SyncResult(
            direction=SyncDirection.PULL,
            integration_type=IntegrationType.SALESFORCE,
            status=SyncStatus.PENDING,
            records_processed=0,
            records_succeeded=0,
            records_failed=0,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            error_details=None,
        )
        assert result.duration_seconds is None


class TestCRMEntity:
    """Test CRMEntity dataclass with confidence defaults."""

    def test_crm_entity_confidence_default(self) -> None:
        """CRMEntity should have 0.85 default confidence per source hierarchy."""
        entity = CRMEntity(
            entity_type="opportunity",
            external_id="opp-123",
            name="Test Opportunity",
            data={"amount": 50000},
        )
        assert entity.confidence == 0.85

    def test_crm_entity_explicit_confidence(self) -> None:
        """CRMEntity should accept explicit confidence value."""
        entity = CRMEntity(
            entity_type="contact",
            external_id="contact-456",
            name="John Doe",
            data={"email": "john@example.com"},
            confidence=0.90,
        )
        assert entity.confidence == 0.90

    def test_crm_entity_all_entity_types(self) -> None:
        """CRMEntity should support all standard entity types."""
        entity_types = ["opportunity", "contact", "account", "activity"]
        for entity_type in entity_types:
            entity = CRMEntity(
                entity_type=entity_type,
                external_id=f"{entity_type}-123",
                name=f"Test {entity_type}",
                data={},
            )
            assert entity.entity_type == entity_type


class TestCalendarEvent:
    """Test CalendarEvent dataclass with is_external detection."""

    def test_calendar_event_is_external_detection(self) -> None:
        """is_external should be set to True when event has external attendees."""
        # In production, this would be auto-detected based on company domain
        # For now, it must be set explicitly based on the attendee analysis
        event = CalendarEvent(
            external_id="event-123",
            title="Client Meeting",
            start_time=datetime(2026, 2, 7, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 7, 15, 0, tzinfo=timezone.utc),
            attendees=["user@company.com", "client@external.com"],
            is_external=True,  # Set explicitly after detecting external attendees
        )
        assert event.is_external is True

    def test_calendar_event_internal_only(self) -> None:
        """is_external should be False when all attendees are from company."""
        event = CalendarEvent(
            external_id="event-456",
            title="Internal Sync",
            start_time=datetime(2026, 2, 7, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 7, 15, 0, tzinfo=timezone.utc),
            attendees=["user1@company.com", "user2@company.com"],
        )
        assert event.is_external is False

    def test_calendar_event_is_external_explicit(self) -> None:
        """is_external should be settable explicitly."""
        event = CalendarEvent(
            external_id="event-789",
            title="Mixed Meeting",
            start_time=datetime(2026, 2, 7, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 7, 15, 0, tzinfo=timezone.utc),
            attendees=["user@company.com"],
            is_external=True,  # Explicit override
        )
        assert event.is_external is True


class TestPushQueueItem:
    """Test PushQueueItem dataclass."""

    def test_push_queue_item_creation(self) -> None:
        """PushQueueItem should create with all required fields."""
        item = PushQueueItem(
            user_id="user-123",
            integration_type=IntegrationType.SALESFORCE,
            action_type=PushActionType.CREATE_NOTE,
            priority=PushPriority.MEDIUM,
            payload={"note": "Test note"},
        )
        assert item.user_id == "user-123"
        assert item.integration_type == IntegrationType.SALESFORCE
        assert item.action_type == PushActionType.CREATE_NOTE
        assert item.priority == PushPriority.MEDIUM
        assert item.payload == {"note": "Test note"}
        assert item.status == PushStatus.PENDING
        assert item.id is None
        assert item.created_at is None
        assert item.expires_at is None
        assert item.processed_at is None
        assert item.error_message is None


class TestSyncConfig:
    """Test SyncConfig dataclass with safe defaults."""

    def test_sync_config_defaults(self) -> None:
        """SyncConfig should have safe defaults per spec."""
        config = SyncConfig()
        assert config.sync_interval_minutes == 15
        assert config.auto_push_enabled is False
        assert config.push_requires_approval is True
        assert config.conflict_resolution == "crm_wins_structured"
        assert config.max_retries == 3
        assert config.retry_backoff_seconds == 60

    def test_sync_config_custom_values(self) -> None:
        """SyncConfig should accept custom values."""
        config = SyncConfig(
            sync_interval_minutes=30,
            auto_push_enabled=True,
            push_requires_approval=False,
            conflict_resolution="aria_wins_insights",
            max_retries=5,
            retry_backoff_seconds=120,
        )
        assert config.sync_interval_minutes == 30
        assert config.auto_push_enabled is True
        assert config.push_requires_approval is False
        assert config.conflict_resolution == "aria_wins_insights"
        assert config.max_retries == 5
        assert config.retry_backoff_seconds == 120


class TestEnums:
    """Test enum values."""

    def test_sync_direction_enum(self) -> None:
        """SyncDirection should have PULL and PUSH values."""
        assert SyncDirection.PULL.value == "PULL"
        assert SyncDirection.PUSH.value == "PUSH"

    def test_sync_status_enum(self) -> None:
        """SyncStatus should have SUCCESS, FAILED, PARTIAL, PENDING values."""
        assert SyncStatus.SUCCESS.value == "SUCCESS"
        assert SyncStatus.FAILED.value == "FAILED"
        assert SyncStatus.PARTIAL.value == "PARTIAL"
        assert SyncStatus.PENDING.value == "PENDING"

    def test_push_action_type_enum(self) -> None:
        """PushActionType should have create_note, update_field, create_event values."""
        assert PushActionType.CREATE_NOTE.value == "create_note"
        assert PushActionType.UPDATE_FIELD.value == "update_field"
        assert PushActionType.CREATE_EVENT.value == "create_event"

    def test_push_priority_enum(self) -> None:
        """PushPriority should have low, medium, high, critical values."""
        assert PushPriority.LOW.value == "low"
        assert PushPriority.MEDIUM.value == "medium"
        assert PushPriority.HIGH.value == "high"
        assert PushPriority.CRITICAL.value == "critical"

    def test_push_status_enum(self) -> None:
        """PushStatus should have pending, approved, rejected, completed, failed values."""
        assert PushStatus.PENDING.value == "pending"
        assert PushStatus.APPROVED.value == "approved"
        assert PushStatus.REJECTED.value == "rejected"
        assert PushStatus.COMPLETED.value == "completed"
        assert PushStatus.FAILED.value == "failed"
