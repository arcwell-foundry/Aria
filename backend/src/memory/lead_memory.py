"""Lead memory module for tracking sales pursuits.

Lead memory stores sales pursuit information with:
- Lifecycle stage progression (lead -> opportunity -> account)
- Status tracking (active, won, lost, dormant)
- Health score calculation (0-100)
- Trigger source tracking for lead creation
- Optional CRM integration fields

Leads are stored in Supabase for structured querying
and integration with the CRM sync system.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LifecycleStage(Enum):
    """Lifecycle stages for lead progression.

    Stages progress in order: lead -> opportunity -> account.
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
            expected_value=Decimal(data["expected_value"]) if data.get("expected_value") else None,
            tags=data.get("tags") or [],
            metadata=data.get("metadata") or {},
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data["created_at"], str)
            else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"])
            if isinstance(data["updated_at"], str)
            else data["updated_at"],
        )
