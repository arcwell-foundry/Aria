"""Conversation intelligence for extracting insights from lead events.

This module provides LLM-powered analysis of lead events to extract
actionable insights including objections, buying signals, commitments,
risks, and opportunities.

Usage:
    ```python
    from src.db.supabase import SupabaseClient
    from src.memory.conversation_intelligence import ConversationIntelligence

    # Initialize service with database client
    client = SupabaseClient.get_client()
    service = ConversationIntelligence(db_client=client)

    # Analyze an event
    insights = await service.analyze_event(
        user_id="user-123",
        lead_memory_id="lead-456",
        event=lead_event,
    )
    ```
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from src.core.llm import LLMClient

if TYPE_CHECKING:
    from supabase import Client

from src.memory.lead_memory_events import LeadEvent
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

    # Valid insight types (must match InsightType enum values)
    VALID_INSIGHT_TYPES = {"objection", "buying_signal", "commitment", "risk", "opportunity"}

    def __init__(self, db_client: Client) -> None:
        """Initialize the conversation intelligence service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    def _build_analysis_prompt(self, event: LeadEvent) -> str:
        """Build the LLM prompt for analyzing a lead event.

        Args:
            event: The LeadEvent to analyze.

        Returns:
            Prompt string for the LLM.
        """
        content = event.content or ""
        subject = event.subject or "(no subject)"

        return f"""Analyze this {event.event_type.value} and extract actionable sales insights.

Event Type: {event.event_type.value}
Direction: {event.direction.value if event.direction else "N/A"}
Subject: {subject}
Content: {content}

Extract the following types of insights if present:

1. **Objections**: Any concerns, pushback, or hesitations raised
2. **Buying Signals**: Indications of readiness or interest to proceed
3. **Commitments**: Promises or agreements made by either party
4. **Risks**: Potential threats to the deal or relationship
5. **Opportunities**: Chances to advance the deal or expand scope

For each insight found, provide:
- type: one of "objection", "buying_signal", "commitment", "risk", "opportunity"
- content: A clear, concise description of the insight
- confidence: A score from 0.0 to 1.0 indicating how confident you are

Return a JSON array of insights. If no insights are found, return an empty array [].

Example response:
[
  {{"type": "objection", "content": "Concerned about implementation timeline", "confidence": 0.85}},
  {{"type": "buying_signal", "content": "Asked about contract terms", "confidence": 0.75}}
]

Important:
- Only extract insights that are clearly present in the content
- Be conservative with confidence scores
- Focus on actionable intelligence for sales teams
- Keep content descriptions concise but specific

Respond with ONLY the JSON array, no additional text."""

    def _parse_llm_response(self, response: str) -> list[dict[str, Any]]:
        """Parse the LLM response JSON into insight dictionaries.

        Handles common LLM response formatting issues like markdown
        code blocks and validates insight types.

        Args:
            response: Raw LLM response string.

        Returns:
            List of validated insight dictionaries.
        """
        # Strip markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove opening ```json or ``` and closing ```
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse LLM response as JSON",
                extra={"response": response[:200]},
            )
            return []

        if not isinstance(parsed, list):
            logger.warning(
                "LLM response is not a list",
                extra={"response_type": type(parsed).__name__},
            )
            return []

        # Filter to valid insight types
        valid_insights = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            insight_type = item.get("type")
            if insight_type not in self.VALID_INSIGHT_TYPES:
                logger.debug("Skipping invalid insight type", extra={"type": insight_type})
                continue
            valid_insights.append(item)

        return valid_insights

    async def analyze_event(
        self,
        user_id: str,
        lead_memory_id: str,
        event: LeadEvent,
    ) -> list[Insight]:
        """Analyze a lead event and extract insights using LLM.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            event: The LeadEvent to analyze.

        Returns:
            List of extracted Insight instances.

        Raises:
            DatabaseError: If storage fails.
        """
        from src.core.exceptions import DatabaseError

        # Build prompt and call LLM
        prompt = self._build_analysis_prompt(event)
        llm = LLMClient()

        try:
            llm_response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Lower temperature for more consistent extraction
            )
        except Exception as e:
            logger.exception("LLM call failed during event analysis")
            raise DatabaseError(f"LLM analysis failed: {e}") from e

        # Parse response
        raw_insights = self._parse_llm_response(llm_response)

        if not raw_insights:
            return []

        # Convert to database records
        now = datetime.now(UTC)
        records = []
        for raw in raw_insights:
            records.append({
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "insight_type": raw["type"],
                "content": raw["content"],
                "confidence": raw.get("confidence", 0.7),
                "source_event_id": event.id,
                "detected_at": now.isoformat(),
            })

        # Store in database
        try:
            db_response = self.db.table("lead_memory_insights").insert(records).execute()

            if not db_response.data:
                raise DatabaseError("Failed to insert insights")

            # Convert to Insight instances
            insights = []
            for i, record in enumerate(db_response.data):
                record_dict = cast(dict[str, Any], record)
                # Merge our local data with DB response
                insight_data = {
                    "id": record_dict.get("id", records[i]["id"]),
                    "lead_memory_id": lead_memory_id,
                    "insight_type": records[i]["insight_type"],
                    "content": records[i]["content"],
                    "confidence": records[i]["confidence"],
                    "source_event_id": records[i]["source_event_id"],
                    "detected_at": record_dict.get("detected_at", records[i]["detected_at"]),
                    "addressed_at": None,
                    "addressed_by": None,
                }
                insights.append(Insight.from_dict(insight_data))

            logger.info(
                "Extracted insights from event",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "event_id": event.id,
                    "insight_count": len(insights),
                },
            )

            return insights

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to store insights")
            raise DatabaseError(f"Failed to store insights: {e}") from e
