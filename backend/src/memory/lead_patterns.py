"""Lead pattern detection for cross-lead learning.

This module analyzes patterns across all leads to extract actionable insights:
- Average time to close by segment
- Common objection patterns
- Successful engagement patterns
- Silent/inactive leads detection

Patterns are stored in Corporate Memory (Graphiti) with privacy protections -
no user-identifiable data is stored in patterns.

Usage:
    ```python
    from src.db.supabase import SupabaseClient
    from src.memory.lead_patterns import LeadPatternDetector

    client = SupabaseClient.get_client()
    detector = LeadPatternDetector(db_client=client)

    # Detect closing time patterns by segment
    patterns = await detector.avg_time_to_close_by_segment(company_id="...")

    # Find silent leads (inactive 14+ days)
    silent = await detector.find_silent_leads(user_id="...", inactive_days=14)
    ```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class ClosingTimePattern:
    """Pattern for average time to close by segment.

    Attributes:
        segment: The lead segment (e.g., "enterprise", "smb", "healthcare").
        avg_days_to_close: Average days from first touch to close.
        sample_size: Number of leads used to calculate.
        calculated_at: When pattern was calculated.
    """

    segment: str
    avg_days_to_close: float
    sample_size: int
    calculated_at: datetime


@dataclass
class ObjectionPattern:
    """Pattern for common objections across leads.

    Attributes:
        objection_text: The normalized objection content.
        frequency: Number of leads with this objection.
        resolution_rate: Percentage of leads where objection was addressed.
        calculated_at: When pattern was calculated.
    """

    objection_text: str
    frequency: int
    resolution_rate: float
    calculated_at: datetime


@dataclass
class EngagementPattern:
    """Pattern for successful engagement strategies.

    Attributes:
        pattern_type: Type of engagement (e.g., "response_time", "touchpoint_frequency").
        description: Human-readable description of the pattern.
        success_correlation: Correlation with deal success (0.0 to 1.0).
        sample_size: Number of leads analyzed.
        calculated_at: When pattern was calculated.
    """

    pattern_type: str
    description: str
    success_correlation: float
    sample_size: int
    calculated_at: datetime


@dataclass
class SilentLead:
    """A lead that has been inactive for a specified period.

    Attributes:
        lead_id: The lead memory ID.
        company_name: Name of the company (not user-identifiable).
        days_inactive: Number of days since last activity.
        last_activity_at: When the lead was last active.
        health_score: Current health score.
    """

    lead_id: str
    company_name: str
    days_inactive: int
    last_activity_at: datetime
    health_score: int


class LeadPatternDetector:
    """Service for detecting patterns across leads.

    Analyzes lead data to extract company-wide patterns that can be
    applied to current leads. Stores patterns in Corporate Memory
    with privacy protections.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the pattern detector.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    async def avg_time_to_close_by_segment(
        self,
        company_id: str,
    ) -> list[ClosingTimePattern]:
        """Calculate average time to close deals by segment.

        Analyzes all closed/won leads to determine average closing time
        for each segment (based on tags). Privacy-safe: only aggregated
        data is returned, no user-identifiable information.

        Args:
            company_id: The company to analyze leads for.

        Returns:
            List of ClosingTimePattern, one per segment found.

        Raises:
            DatabaseError: If query fails.
            ValueError: If company_id is empty.
        """
        from src.core.exceptions import DatabaseError

        # Input validation
        if not company_id:
            raise ValueError("company_id must not be empty")

        try:
            # Query closed/won leads
            response = (
                self.db.table("lead_memories")
                .select("id, first_touch_at, updated_at, tags")
                .eq("company_id", company_id)
                .eq("status", "won")
                .execute()
            )

            if not response.data:
                return []

            now = datetime.now(UTC)

            # Group by segment (first tag or "untagged")
            segment_data: dict[str, list[float]] = {}
            for item in response.data:
                # Cast Supabase JSON response to typed dict
                lead: dict[str, Any] = cast(dict[str, Any], item)
                tags = lead.get("tags", []) or []
                segment = str(tags[0]) if tags else "untagged"

                first_touch = datetime.fromisoformat(str(lead["first_touch_at"]))
                closed_at = datetime.fromisoformat(str(lead["updated_at"]))
                days_to_close = (closed_at - first_touch).days

                # Skip records with invalid (negative) days to close
                if days_to_close < 0:
                    logger.warning(
                        "Skipping lead with negative days_to_close",
                        extra={
                            "lead_id": lead.get("id"),
                            "days_to_close": days_to_close,
                        },
                    )
                    continue

                if segment not in segment_data:
                    segment_data[segment] = []
                segment_data[segment].append(float(days_to_close))

            # Calculate averages
            patterns = []
            for segment, days_list in segment_data.items():
                avg_days = sum(days_list) / len(days_list)
                patterns.append(
                    ClosingTimePattern(
                        segment=segment,
                        avg_days_to_close=avg_days,
                        sample_size=len(days_list),
                        calculated_at=now,
                    )
                )

            logger.info(
                "Calculated closing time patterns",
                extra={
                    "company_id": company_id,
                    "segment_count": len(patterns),
                },
            )

            return patterns

        except Exception as e:
            logger.exception("Failed to calculate closing time patterns")
            raise DatabaseError(f"Failed to calculate closing time patterns: {e}") from e
