"""Tests for CRM sync domain models."""

import pytest
from datetime import datetime, UTC


class TestCRMProviderEnum:
    """Tests for CRMProvider enum."""

    def test_crm_provider_values(self) -> None:
        """Test CRMProvider enum has correct values."""
        from src.services.crm_sync_models import CRMProvider

        assert CRMProvider.SALESFORCE.value == "salesforce"
        assert CRMProvider.HUBSPOT.value == "hubspot"


class TestSyncStatusEnum:
    """Tests for SyncStatus enum."""

    def test_sync_status_values(self) -> None:
        """Test SyncStatus enum has correct state machine values."""
        from src.services.crm_sync_models import SyncStatus

        assert SyncStatus.SYNCED.value == "synced"
        assert SyncStatus.PENDING.value == "pending"
        assert SyncStatus.CONFLICT.value == "conflict"
        assert SyncStatus.ERROR.value == "error"


class TestSyncDirectionEnum:
    """Tests for SyncDirection enum."""

    def test_sync_direction_values(self) -> None:
        """Test SyncDirection enum has correct values."""
        from src.services.crm_sync_models import SyncDirection

        assert SyncDirection.PUSH.value == "push"
        assert SyncDirection.PULL.value == "pull"
        assert SyncDirection.BIDIRECTIONAL.value == "bidirectional"


class TestConflictResolutionEnum:
    """Tests for ConflictResolution enum."""

    def test_conflict_resolution_values(self) -> None:
        """Test ConflictResolution enum has correct values."""
        from src.services.crm_sync_models import ConflictResolution

        assert ConflictResolution.CRM_WINS.value == "crm_wins"
        assert ConflictResolution.ARIA_WINS.value == "aria_wins"
        assert ConflictResolution.MERGE.value == "merge"
        assert ConflictResolution.MANUAL.value == "manual"


class TestCRMSyncStateDataclass:
    """Tests for CRMSyncState dataclass."""

    def test_sync_state_initialization(self) -> None:
        """Test CRMSyncState initializes correctly."""
        from src.services.crm_sync_models import CRMSyncState, SyncStatus

        now = datetime.now(UTC)
        state = CRMSyncState(
            id="sync-123",
            lead_memory_id="lead-456",
            status=SyncStatus.SYNCED,
            last_sync_at=now,
            created_at=now,
            updated_at=now,
        )

        assert state.id == "sync-123"
        assert state.lead_memory_id == "lead-456"
        assert state.status == SyncStatus.SYNCED

    def test_sync_state_to_dict(self) -> None:
        """Test CRMSyncState.to_dict serializes correctly."""
        from src.services.crm_sync_models import CRMSyncState, SyncStatus

        now = datetime.now(UTC)
        state = CRMSyncState(
            id="sync-123",
            lead_memory_id="lead-456",
            status=SyncStatus.PENDING,
            last_sync_at=now,
            pending_changes=[{"field": "stage", "value": "opportunity"}],
            created_at=now,
            updated_at=now,
        )

        data = state.to_dict()

        assert data["id"] == "sync-123"
        assert data["status"] == "pending"
        assert len(data["pending_changes"]) == 1

    def test_sync_state_from_dict_roundtrip(self) -> None:
        """Test CRMSyncState.from_dict and to_dict roundtrip."""
        from src.services.crm_sync_models import (
            CRMSyncState,
            SyncStatus,
            SyncDirection,
        )

        now = datetime.now(UTC)
        original = CRMSyncState(
            id="sync-123",
            lead_memory_id="lead-456",
            status=SyncStatus.PENDING,
            sync_direction=SyncDirection.PUSH,
            last_sync_at=now,
            last_push_at=now,
            last_pull_at=None,
            pending_changes=[{"field": "stage", "value": "opportunity"}],
            conflict_log=[{"field": "amount", "resolution": "crm_wins"}],
            error_message="Test error",
            retry_count=3,
            created_at=now,
            updated_at=now,
        )

        # Serialize to dict
        data = original.to_dict()

        # Deserialize back
        restored = CRMSyncState.from_dict(data)

        # Verify all fields match
        assert restored.id == original.id
        assert restored.lead_memory_id == original.lead_memory_id
        assert restored.status == original.status
        assert restored.sync_direction == original.sync_direction
        assert restored.last_sync_at == original.last_sync_at
        assert restored.last_push_at == original.last_push_at
        assert restored.last_pull_at == original.last_pull_at
        assert restored.pending_changes == original.pending_changes
        assert restored.conflict_log == original.conflict_log
        assert restored.error_message == original.error_message
        assert restored.retry_count == original.retry_count
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at

    def test_sync_state_from_dict_with_datetime_objects(self) -> None:
        """Test CRMSyncState.from_dict handles datetime objects directly."""
        from src.services.crm_sync_models import CRMSyncState, SyncStatus

        now = datetime.now(UTC)
        data = {
            "id": "sync-123",
            "lead_memory_id": "lead-456",
            "status": "synced",
            "last_sync_at": now,  # datetime object, not string
            "last_push_at": now,
            "last_pull_at": now,
            "created_at": now,
            "updated_at": now,
        }

        state = CRMSyncState.from_dict(data)

        assert state.last_sync_at == now
        assert state.last_push_at == now
        assert state.last_pull_at == now
        assert state.created_at == now
        assert state.updated_at == now

    def test_sync_state_from_dict_missing_required_fields(self) -> None:
        """Test CRMSyncState.from_dict raises error for missing required fields."""
        from src.services.crm_sync_models import CRMSyncState, CRMSyncModelError

        # Missing id
        with pytest.raises(CRMSyncModelError) as exc_info:
            CRMSyncState.from_dict(
                {
                    "lead_memory_id": "lead-456",
                    "status": "synced",
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
        assert "id" in str(exc_info.value)

        # Missing multiple fields
        with pytest.raises(CRMSyncModelError) as exc_info:
            CRMSyncState.from_dict({"status": "synced"})
        assert "id" in str(exc_info.value)
        assert "lead_memory_id" in str(exc_info.value)

    def test_sync_state_from_dict_invalid_status(self) -> None:
        """Test CRMSyncState.from_dict raises error for invalid status."""
        from src.services.crm_sync_models import CRMSyncState, CRMSyncModelError

        now = datetime.now(UTC)
        with pytest.raises(CRMSyncModelError) as exc_info:
            CRMSyncState.from_dict(
                {
                    "id": "sync-123",
                    "lead_memory_id": "lead-456",
                    "status": "invalid_status",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )
        assert "Invalid field value" in str(exc_info.value)

    def test_sync_state_negative_retry_count_raises_error(self) -> None:
        """Test CRMSyncState raises error for negative retry_count."""
        from src.services.crm_sync_models import CRMSyncState, SyncStatus, CRMSyncModelError

        now = datetime.now(UTC)
        with pytest.raises(CRMSyncModelError) as exc_info:
            CRMSyncState(
                id="sync-123",
                lead_memory_id="lead-456",
                status=SyncStatus.SYNCED,
                last_sync_at=now,
                created_at=now,
                updated_at=now,
                retry_count=-1,
            )
        assert "retry_count must be non-negative" in str(exc_info.value)

    def test_sync_state_zero_retry_count_valid(self) -> None:
        """Test CRMSyncState accepts zero retry_count."""
        from src.services.crm_sync_models import CRMSyncState, SyncStatus

        now = datetime.now(UTC)
        state = CRMSyncState(
            id="sync-123",
            lead_memory_id="lead-456",
            status=SyncStatus.SYNCED,
            last_sync_at=now,
            created_at=now,
            updated_at=now,
            retry_count=0,
        )
        assert state.retry_count == 0


class TestSyncConflictDataclass:
    """Tests for SyncConflict dataclass."""

    def test_conflict_initialization(self) -> None:
        """Test SyncConflict initializes correctly."""
        from src.services.crm_sync_models import SyncConflict, ConflictResolution

        now = datetime.now(UTC)
        conflict = SyncConflict(
            field="lifecycle_stage",
            aria_value="opportunity",
            crm_value="prospect",
            resolution=ConflictResolution.CRM_WINS,
            resolved_value="prospect",
            detected_at=now,
        )

        assert conflict.field == "lifecycle_stage"
        assert conflict.resolution == ConflictResolution.CRM_WINS

    def test_conflict_to_dict(self) -> None:
        """Test SyncConflict.to_dict serializes correctly."""
        from src.services.crm_sync_models import SyncConflict, ConflictResolution

        detected = datetime.now(UTC)
        resolved = datetime.now(UTC)
        conflict = SyncConflict(
            field="amount",
            aria_value=100000.0,
            crm_value=150000.0,
            resolution=ConflictResolution.CRM_WINS,
            resolved_value=150000.0,
            detected_at=detected,
            resolved_at=resolved,
        )

        data = conflict.to_dict()

        assert data["field"] == "amount"
        assert data["aria_value"] == 100000.0
        assert data["crm_value"] == 150000.0
        assert data["resolution"] == "crm_wins"
        assert data["resolved_value"] == 150000.0
        assert data["detected_at"] == detected.isoformat()
        assert data["resolved_at"] == resolved.isoformat()

    def test_conflict_to_dict_with_none_resolved_at(self) -> None:
        """Test SyncConflict.to_dict handles None resolved_at."""
        from src.services.crm_sync_models import SyncConflict, ConflictResolution

        now = datetime.now(UTC)
        conflict = SyncConflict(
            field="stage",
            aria_value="negotiation",
            crm_value="proposal",
            resolution=ConflictResolution.MANUAL,
            resolved_value=None,
            detected_at=now,
            resolved_at=None,
        )

        data = conflict.to_dict()

        assert data["resolved_at"] is None
        assert data["resolution"] == "manual"


class TestCRMRecordDataclass:
    """Tests for CRMRecord dataclass."""

    def test_crm_record_initialization(self) -> None:
        """Test CRMRecord initializes correctly."""
        from src.services.crm_sync_models import CRMRecord, CRMProvider

        record = CRMRecord(
            crm_id="sf-opp-123",
            provider=CRMProvider.SALESFORCE,
            name="Acme Corp",
            stage="Proposal",
            amount=250000.0,
            close_date="2026-06-30",
            notes=["[ARIA] Previous meeting went well"],
        )

        assert record.crm_id == "sf-opp-123"
        assert record.provider == CRMProvider.SALESFORCE
        assert "[ARIA]" in record.notes[0]

    def test_crm_record_to_dict(self) -> None:
        """Test CRMRecord.to_dict serializes correctly."""
        from src.services.crm_sync_models import CRMRecord, CRMProvider

        record = CRMRecord(
            crm_id="sf-opp-456",
            provider=CRMProvider.HUBSPOT,
            name="TechCorp Inc",
            stage="Qualified",
            amount=500000.0,
            close_date="2026-12-31",
            notes=["Initial call completed", "[ARIA] Follow up scheduled"],
            activities=[{"type": "call", "date": "2026-01-15"}],
            contacts=[{"name": "Jane Doe", "role": "CTO"}],
            metadata={"source": "inbound", "campaign": "Q1-2026"},
        )

        data = record.to_dict()

        assert data["crm_id"] == "sf-opp-456"
        assert data["provider"] == "hubspot"
        assert data["name"] == "TechCorp Inc"
        assert data["stage"] == "Qualified"
        assert data["amount"] == 500000.0
        assert data["close_date"] == "2026-12-31"
        assert len(data["notes"]) == 2
        assert data["activities"] == [{"type": "call", "date": "2026-01-15"}]
        assert data["contacts"] == [{"name": "Jane Doe", "role": "CTO"}]
        assert data["metadata"] == {"source": "inbound", "campaign": "Q1-2026"}

    def test_crm_record_to_dict_with_defaults(self) -> None:
        """Test CRMRecord.to_dict with default values."""
        from src.services.crm_sync_models import CRMRecord, CRMProvider

        record = CRMRecord(
            crm_id="sf-opp-789",
            provider=CRMProvider.SALESFORCE,
            name="MinimalCorp",
        )

        data = record.to_dict()

        assert data["crm_id"] == "sf-opp-789"
        assert data["provider"] == "salesforce"
        assert data["name"] == "MinimalCorp"
        assert data["stage"] is None
        assert data["amount"] is None
        assert data["close_date"] is None
        assert data["notes"] == []
        assert data["activities"] == []
        assert data["contacts"] == []
        assert data["metadata"] == {}
