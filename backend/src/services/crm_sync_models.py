"""Domain models for CRM synchronization."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CRMSyncModelError(Exception):
    """Error raised when CRM sync model validation fails."""

    pass


class CRMProvider(str, Enum):
    """Supported CRM providers."""

    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"


class SyncStatus(str, Enum):
    """Sync state machine states.

    State transitions:
    - synced -> pending (on local change)
    - pending -> synced (on successful sync)
    - pending -> conflict (on conflicting remote change)
    - pending -> error (on sync failure)
    - conflict -> synced (on resolution)
    - error -> pending (on retry)
    """

    SYNCED = "synced"
    PENDING = "pending"
    CONFLICT = "conflict"
    ERROR = "error"


class SyncDirection(str, Enum):
    """Direction of sync operation."""

    PUSH = "push"  # ARIA -> CRM
    PULL = "pull"  # CRM -> ARIA
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(str, Enum):
    """How to resolve sync conflicts."""

    CRM_WINS = "crm_wins"  # CRM value takes precedence
    ARIA_WINS = "aria_wins"  # ARIA value takes precedence
    MERGE = "merge"  # Merge both values (for notes)
    MANUAL = "manual"  # Requires user intervention


@dataclass
class SyncConflict:
    """A sync conflict between ARIA and CRM."""

    field: str
    aria_value: Any
    crm_value: Any
    resolution: ConflictResolution
    resolved_value: Any
    detected_at: datetime
    resolved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize conflict to dictionary."""
        return {
            "field": self.field,
            "aria_value": self.aria_value,
            "crm_value": self.crm_value,
            "resolution": self.resolution.value,
            "resolved_value": self.resolved_value,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse a datetime value from string or datetime object.

    Args:
        value: Either an ISO format string, datetime object, or None.

    Returns:
        Parsed datetime or None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


@dataclass
class CRMSyncState:
    """Sync state for a lead memory record."""

    id: str
    lead_memory_id: str
    status: SyncStatus
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime
    sync_direction: SyncDirection | None = None
    last_push_at: datetime | None = None
    last_pull_at: datetime | None = None
    pending_changes: list[dict[str, Any]] = field(default_factory=list)
    conflict_log: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    retry_count: int = 0

    def __post_init__(self) -> None:
        """Validate the dataclass after initialization."""
        if self.retry_count < 0:
            raise CRMSyncModelError(f"retry_count must be non-negative, got {self.retry_count}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize sync state to dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "status": self.status.value,
            "sync_direction": self.sync_direction.value if self.sync_direction else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_push_at": self.last_push_at.isoformat() if self.last_push_at else None,
            "last_pull_at": self.last_pull_at.isoformat() if self.last_pull_at else None,
            "pending_changes": self.pending_changes,
            "conflict_log": self.conflict_log,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CRMSyncState":
        """Create CRMSyncState from dictionary.

        Args:
            data: Dictionary containing CRMSyncState fields.

        Returns:
            CRMSyncState instance.

        Raises:
            CRMSyncModelError: If required fields are missing or invalid.
        """
        required_fields = ["id", "lead_memory_id", "status", "created_at", "updated_at"]
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            raise CRMSyncModelError(f"Missing required fields: {', '.join(missing_fields)}")

        try:
            return cls(
                id=data["id"],
                lead_memory_id=data["lead_memory_id"],
                status=SyncStatus(data["status"]),
                sync_direction=SyncDirection(data["sync_direction"])
                if data.get("sync_direction")
                else None,
                last_sync_at=_parse_datetime(data.get("last_sync_at")),
                last_push_at=_parse_datetime(data.get("last_push_at")),
                last_pull_at=_parse_datetime(data.get("last_pull_at")),
                pending_changes=data.get("pending_changes") or [],
                conflict_log=data.get("conflict_log") or [],
                error_message=data.get("error_message"),
                retry_count=data.get("retry_count", 0),
                created_at=_parse_datetime(data["created_at"]),  # type: ignore[arg-type]
                updated_at=_parse_datetime(data["updated_at"]),  # type: ignore[arg-type]
            )
        except ValueError as e:
            raise CRMSyncModelError(f"Invalid field value: {e}") from e


@dataclass
class CRMRecord:
    """A record from a CRM system."""

    crm_id: str
    provider: CRMProvider
    name: str
    stage: str | None = None
    amount: float | None = None
    close_date: str | None = None
    notes: list[str] = field(default_factory=list)
    activities: list[dict[str, Any]] = field(default_factory=list)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize CRM record to dictionary."""
        return {
            "crm_id": self.crm_id,
            "provider": self.provider.value,
            "name": self.name,
            "stage": self.stage,
            "amount": self.amount,
            "close_date": self.close_date,
            "notes": self.notes,
            "activities": self.activities,
            "contacts": self.contacts,
            "metadata": self.metadata,
        }
