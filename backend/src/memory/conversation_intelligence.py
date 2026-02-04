"""Conversation intelligence for extracting insights from lead events.

This module provides LLM-powered analysis of lead events to extract
actionable insights including objections, buying signals, commitments,
risks, and opportunities.

Usage:
    ```python
    from src.memory.conversation_intelligence import ConversationIntelligence, Insight
    from src.models.lead_memory import InsightType

    # Initialize service
    service = ConversationIntelligence()

    # Analyze an event
    insights = await service.analyze_event(
        user_id="user-123",
        lead_memory_id="lead-456",
        event=lead_event,
    )

    # Mark an insight as addressed
    await service.mark_addressed(
        user_id="user-123",
        insight_id="insight-789",
    )
    ```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import InsightType

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    """A domain model representing an extracted insight from a lead event.

    Insights capture actionable intelligence from conversations and
    interactions, including objections, buying signals, commitments,
    risks, and opportunities.

    Attributes:
        id: Unique identifier for this insight.
        lead_memory_id: ID of the lead memory this insight belongs to.
        insight_type: The category of insight (objection, buying_signal, etc.).
        content: The extracted insight content.
        confidence: Confidence score from 0.0 to 1.0.
        source_event_id: Optional ID of the event that generated this insight.
        detected_at: When this insight was detected.
        addressed_at: When this insight was marked as addressed (if applicable).
        addressed_by: User ID who addressed the insight (if applicable).
    """

    id: str
    lead_memory_id: str
    insight_type: InsightType
    content: str
    confidence: float
    source_event_id: str | None
    detected_at: datetime
    addressed_at: datetime | None
    addressed_by: str | None

    def to_dict(self) -> dict[str, object]:
        """Serialize the insight to a dictionary.

        Converts the insight to a dictionary suitable for JSON serialization,
        with datetime fields converted to ISO format strings.

        Returns:
            Dictionary representation of the insight.
        """
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "insight_type": self.insight_type.value,
            "content": self.content,
            "confidence": self.confidence,
            "source_event_id": self.source_event_id,
            "detected_at": self.detected_at.isoformat(),
            "addressed_at": self.addressed_at.isoformat() if self.addressed_at else None,
            "addressed_by": self.addressed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Insight:
        """Create an Insight from a dictionary.

        Deserializes a dictionary back into an Insight instance,
        handling both ISO format strings and datetime objects.

        Args:
            data: Dictionary containing insight data.

        Returns:
            An Insight instance with restored state.
        """
        # Parse detected_at - handle both string and datetime
        detected_at_raw = data["detected_at"]
        if isinstance(detected_at_raw, str):
            detected_at = datetime.fromisoformat(detected_at_raw)
        else:
            detected_at = cast(datetime, detected_at_raw)

        # Parse addressed_at - handle both string and datetime
        addressed_at_raw = data.get("addressed_at")
        addressed_at: datetime | None = None
        if addressed_at_raw is not None:
            if isinstance(addressed_at_raw, str):
                addressed_at = datetime.fromisoformat(addressed_at_raw)
            else:
                addressed_at = cast(datetime, addressed_at_raw)

        # Parse insight_type - handle both string and InsightType enum
        insight_type_raw = data["insight_type"]
        if isinstance(insight_type_raw, str):
            insight_type = InsightType(insight_type_raw)
        else:
            insight_type = cast(InsightType, insight_type_raw)

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            insight_type=insight_type,
            content=cast(str, data["content"]),
            confidence=cast(float, data["confidence"]),
            source_event_id=cast(str | None, data.get("source_event_id")),
            detected_at=detected_at,
            addressed_at=addressed_at,
            addressed_by=cast(str | None, data.get("addressed_by")),
        )


class ConversationIntelligence:
    """Service for extracting insights from lead events using LLM.

    Provides async interface for analyzing lead events and extracting
    actionable insights. Insights are stored in Supabase with links
    to their source events.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the conversation intelligence service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client
