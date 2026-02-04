"""Lead insights service for AI-powered sales intelligence.

This module provides the placeholder service for lead insights.
Full AI insight generation will be implemented in US-515.

Insights are derived from lead events and patterns, including:
- Buying signals (positive engagement, budget mentions)
- Objections (concerns raised, competitor mentions)
- Risks (stalled deals, missing stakeholder alignment)
- Commitments (timeline agreements, next steps)
- Opportunities (expansion potential, referrals)

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

from src.models.lead_memory import InsightType

logger = logging.getLogger(__name__)


@dataclass
class LeadInsight:
    """A domain model representing an AI-derived insight about a lead.

    Attributes:
        id: Unique identifier for this insight.
        lead_memory_id: ID of the lead memory this insight belongs to.
        insight_type: Type of insight (buying_signal, objection, risk, etc.).
        content: Human-readable description of the insight.
        confidence: AI confidence score (0-1).
        source_event_id: Optional ID of the event that generated this insight.
        detected_at: When this insight was detected.
        addressed_at: Optional timestamp when this insight was addressed/resolved.
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
            raw = data["addressed_at"]
            addressed_at = datetime.fromisoformat(raw) if isinstance(raw, str) else raw

        # Parse enum
        insight_type_raw = data["insight_type"]
        insight_type = (
            InsightType(insight_type_raw) if isinstance(insight_type_raw, str) else insight_type_raw
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
    """Service for managing lead insights operations.

    Provides async interface for storing, retrieving, and querying
    lead insights. Stored in Supabase with user isolation via RLS.

    NOTE: AI insight generation is a placeholder. Full implementation
    in US-515 will use Claude to analyze events and generate insights.
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
            include_addressed: Whether to include addressed insights (default False).

        Returns:
            List of LeadInsight instances, sorted by detected_at descending.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            query = client.table("lead_insights").select("*").eq("lead_memory_id", lead_memory_id)

            # Filter by insight type if specified
            if insight_type:
                query = query.eq("insight_type", insight_type.value)

            # Exclude addressed insights unless requested
            if not include_addressed:
                query = query.is_("addressed_at", "null")

            # Order by detection time (newest first)
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
                    "insight_type": insight_type.value if insight_type else None,
                    "include_addressed": include_addressed,
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
        confidence: float,
        source_event_id: str | None = None,
    ) -> str:
        """Create a new insight for a lead.

        NOTE: This is a placeholder. In US-515, this will be called
        automatically by the insight generation service after AI analysis.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            insight_type: Type of insight.
            content: Human-readable description.
            confidence: AI confidence score (0-1).
            source_event_id: Optional ID of the event that generated this insight.

        Returns:
            The ID of the created insight.

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

            if not insight_id:
                raise DatabaseError("Failed to insert insight")

            logger.info(
                "Created lead insight",
                extra={
                    "insight_id": insight_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "insight_type": insight_type.value,
                    "confidence": confidence,
                },
            )

            return insight_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to create lead insight")
            raise DatabaseError(f"Failed to create lead insight: {e}") from e
