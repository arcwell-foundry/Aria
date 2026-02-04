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
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from src.core.exceptions import LeadMemoryError
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

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
