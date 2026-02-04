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

    async def common_objection_patterns(
        self,
        company_id: str,
        min_frequency: int = 1,
    ) -> list[ObjectionPattern]:
        """Detect common objection patterns across leads.

        Analyzes objection-type insights from all leads to identify
        recurring objection patterns and their resolution rates.
        Privacy-safe: only aggregated patterns returned.

        Note:
            Current implementation queries all objection insights without
            company_id filtering on the insights table. The company_id parameter
            is accepted for API consistency and future implementation when
            a proper join or two-step query approach is added.

        Args:
            company_id: The company to analyze (reserved for future filtering).
            min_frequency: Minimum occurrences to include (default 1).

        Returns:
            List of ObjectionPattern ordered by frequency descending.

        Raises:
            ValueError: If company_id is empty.
            DatabaseError: If query fails.
        """
        from src.core.exceptions import DatabaseError

        # Input validation
        if not company_id:
            raise ValueError("company_id must not be empty")

        try:
            # Query objection insights
            # Note: company_id filtering requires a join with lead_memories table
            # which is not directly supported by Supabase Python client dot notation.
            # For now, we query all objection insights. Future implementation could
            # use a two-step query or a database function for proper filtering.
            response = (
                self.db.table("lead_memory_insights")
                .select("id, content, addressed_at")
                .eq("insight_type", "objection")
                .execute()
            )

            if not response.data:
                return []

            now = datetime.now(UTC)

            # Group by content
            objection_data: dict[str, dict[str, Any]] = {}
            for item in response.data:
                insight: dict[str, Any] = cast(dict[str, Any], item)
                content = str(insight.get("content", ""))
                if not content:
                    continue

                if content not in objection_data:
                    objection_data[content] = {"total": 0, "resolved": 0}

                objection_data[content]["total"] += 1
                if insight.get("addressed_at"):
                    objection_data[content]["resolved"] += 1

            # Create patterns
            patterns = []
            for content, data in objection_data.items():
                if data["total"] >= min_frequency:
                    resolution_rate = data["resolved"] / data["total"] if data["total"] > 0 else 0.0
                    patterns.append(
                        ObjectionPattern(
                            objection_text=content,
                            frequency=data["total"],
                            resolution_rate=resolution_rate,
                            calculated_at=now,
                        )
                    )

            # Sort by frequency descending
            patterns.sort(key=lambda p: p.frequency, reverse=True)

            logger.info(
                "Detected objection patterns",
                extra={
                    "company_id": company_id,
                    "pattern_count": len(patterns),
                },
            )

            return patterns

        except Exception as e:
            logger.exception("Failed to detect objection patterns")
            raise DatabaseError(f"Failed to detect objection patterns: {e}") from e

    async def successful_engagement_patterns(
        self,
        company_id: str,
        min_sample_size: int = 5,
    ) -> list[EngagementPattern]:
        """Detect engagement patterns correlated with deal success.

        Analyzes health score components of won vs lost deals to identify
        which engagement factors correlate most strongly with success.
        Privacy-safe: only aggregated patterns returned.

        Args:
            company_id: The company to analyze.
            min_sample_size: Minimum closed deals required (default 5).

        Returns:
            List of EngagementPattern sorted by correlation strength.

        Raises:
            ValueError: If company_id is empty.
            DatabaseError: If query fails.
        """
        from src.core.exceptions import DatabaseError

        # Input validation
        if not company_id:
            raise ValueError("company_id must not be empty")

        try:
            # Query closed leads (won and lost)
            leads_response = (
                self.db.table("lead_memories")
                .select("id, status")
                .eq("company_id", company_id)
                .execute()
            )

            if not leads_response.data:
                return []

            # Filter to closed leads
            closed_leads = [
                cast(dict[str, Any], lead)
                for lead in leads_response.data
                if cast(dict[str, Any], lead).get("status") in ("won", "lost")
            ]

            if len(closed_leads) < min_sample_size:
                return []

            lead_ids = [lead["id"] for lead in closed_leads]
            lead_status_map = {lead["id"]: lead["status"] for lead in closed_leads}

            # Get health score history with component scores
            history_response = (
                self.db.table("health_score_history")
                .select(
                    "lead_memory_id, component_frequency, component_response_time, "
                    "component_sentiment, component_breadth, component_velocity"
                )
                .in_("lead_memory_id", lead_ids)
                .execute()
            )

            if not history_response.data:
                return []

            now = datetime.now(UTC)

            # Calculate correlation for each component
            components = [
                (
                    "touchpoint_frequency",
                    "component_frequency",
                    "Frequent communication correlates with success",
                ),
                (
                    "response_time",
                    "component_response_time",
                    "Fast response time correlates with success",
                ),
                (
                    "sentiment",
                    "component_sentiment",
                    "Positive sentiment correlates with success",
                ),
                (
                    "stakeholder_breadth",
                    "component_breadth",
                    "Multi-stakeholder engagement correlates with success",
                ),
                (
                    "stage_velocity",
                    "component_velocity",
                    "Fast stage progression correlates with success",
                ),
            ]

            patterns = []
            for pattern_type, component_field, description in components:
                # Get average component score for won vs lost
                won_scores: list[float] = []
                lost_scores: list[float] = []

                for item in history_response.data:
                    record = cast(dict[str, Any], item)
                    lead_id = record.get("lead_memory_id")
                    score = record.get(component_field, 0) or 0

                    if lead_status_map.get(lead_id) == "won":
                        won_scores.append(float(score))
                    elif lead_status_map.get(lead_id) == "lost":
                        lost_scores.append(float(score))

                if not won_scores or not lost_scores:
                    continue

                avg_won = sum(won_scores) / len(won_scores)
                avg_lost = sum(lost_scores) / len(lost_scores)

                # Simple correlation: how much higher is won vs lost
                # Normalize to 0-1 range
                if avg_won > avg_lost:
                    correlation = min((avg_won - avg_lost) / max(avg_won, 0.01), 1.0)
                else:
                    correlation = 0.0

                patterns.append(
                    EngagementPattern(
                        pattern_type=pattern_type,
                        description=description,
                        success_correlation=correlation,
                        sample_size=len(won_scores) + len(lost_scores),
                        calculated_at=now,
                    )
                )

            # Sort by correlation strength
            patterns.sort(key=lambda p: p.success_correlation, reverse=True)

            logger.info(
                "Detected engagement patterns",
                extra={
                    "company_id": company_id,
                    "pattern_count": len(patterns),
                },
            )

            return patterns

        except Exception as e:
            logger.exception("Failed to detect engagement patterns")
            raise DatabaseError(f"Failed to detect engagement patterns: {e}") from e
