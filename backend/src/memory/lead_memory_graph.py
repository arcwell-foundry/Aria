"""Lead memory graph module for knowledge graph operations.

Stores lead memories as first-class nodes in Graphiti with typed relationships:
- OWNED_BY: Lead owned by a user
- CONTRIBUTED_BY: Users who contributed to the lead
- ABOUT_COMPANY: Links to company entity
- HAS_CONTACT: Stakeholder contacts
- HAS_COMMUNICATION: Email/meeting/call events
- HAS_SIGNAL: Market signals and insights
- SYNCED_TO: CRM synchronization link

Enables cross-lead queries and pattern detection.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LeadRelationshipType(Enum):
    """Types of relationships between lead memory nodes."""

    OWNED_BY = "OWNED_BY"  # Lead -> User (owner)
    CONTRIBUTED_BY = "CONTRIBUTED_BY"  # Lead -> User (contributor)
    ABOUT_COMPANY = "ABOUT_COMPANY"  # Lead -> Company
    HAS_CONTACT = "HAS_CONTACT"  # Lead -> Contact/Stakeholder
    HAS_COMMUNICATION = "HAS_COMMUNICATION"  # Lead -> Event (email/meeting/call)
    HAS_SIGNAL = "HAS_SIGNAL"  # Lead -> Signal/Insight
    SYNCED_TO = "SYNCED_TO"  # Lead -> CRM Record


@dataclass
class LeadMemoryNode:
    """A lead memory node for the knowledge graph.

    Represents a sales lead/opportunity/account with all its metadata.
    Stored in both Supabase (structured data) and Graphiti (relationships).
    """

    id: str
    user_id: str
    company_name: str
    lifecycle_stage: str  # lead, opportunity, account
    status: str  # active, won, lost, dormant
    health_score: int
    created_at: datetime
    company_id: str | None = None
    crm_id: str | None = None
    crm_provider: str | None = None
    first_touch_at: datetime | None = None
    last_activity_at: datetime | None = None
    expected_close_date: str | None = None  # ISO date string
    expected_value: float | None = None
    tags: list[str] = field(default_factory=list)
    updated_at: datetime | None = None
    graphiti_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize node to dictionary for storage.

        Returns:
            Dictionary suitable for database insertion.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "company_name": self.company_name,
            "company_id": self.company_id,
            "lifecycle_stage": self.lifecycle_stage,
            "status": self.status,
            "health_score": self.health_score,
            "crm_id": self.crm_id,
            "crm_provider": self.crm_provider,
            "first_touch_at": self.first_touch_at.isoformat() if self.first_touch_at else None,
            "last_activity_at": self.last_activity_at.isoformat()
            if self.last_activity_at
            else None,
            "expected_close_date": self.expected_close_date,
            "expected_value": self.expected_value,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "graphiti_node_id": self.graphiti_node_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeadMemoryNode":
        """Create a LeadMemoryNode from a dictionary.

        Args:
            data: Dictionary from database query.

        Returns:
            LeadMemoryNode instance.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            company_name=data["company_name"],
            company_id=data.get("company_id"),
            lifecycle_stage=data["lifecycle_stage"],
            status=data["status"],
            health_score=data["health_score"],
            crm_id=data.get("crm_id"),
            crm_provider=data.get("crm_provider"),
            first_touch_at=datetime.fromisoformat(data["first_touch_at"])
            if data.get("first_touch_at")
            else None,
            last_activity_at=datetime.fromisoformat(data["last_activity_at"])
            if data.get("last_activity_at")
            else None,
            expected_close_date=data.get("expected_close_date"),
            expected_value=data.get("expected_value"),
            tags=data.get("tags") or [],
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data.get("created_at"), str)
            else data.get("created_at") or datetime.now(UTC),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
            graphiti_node_id=data.get("graphiti_node_id"),
        )
