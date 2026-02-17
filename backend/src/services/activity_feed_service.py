"""Activity feed service for ARIA.

Provides paginated activity feeds with entity detail enrichment,
real-time polling support, standardized activity type recording,
and activity statistics aggregation.
"""

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Standardized activity types that all services should use
STANDARD_ACTIVITY_TYPES = frozenset(
    {
        "email_drafted",
        "meeting_prepped",
        "lead_discovered",
        "goal_updated",
        "signal_detected",
        "debrief_processed",
        "briefing_generated",
        "score_calculated",
    }
)

# Maps related_entity_type to (table_name, name_column)
_ENTITY_TABLE_MAP: dict[str, tuple[str, str]] = {
    "lead": ("lead_memory", "company_name"),
    "goal": ("goals", "title"),
    "contact": ("contacts", "full_name"),
    "company": ("companies", "name"),
}

_PERIOD_DELTAS: dict[str, timedelta] = {
    "day": timedelta(days=1),
    "1d": timedelta(days=1),
    "week": timedelta(weeks=1),
    "7d": timedelta(weeks=1),
    "month": timedelta(days=30),
    "30d": timedelta(days=30),
}


class ActivityFeedService:
    """Serves the ARIA activity feed with enrichment and stats."""

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    async def get_activity_feed(
        self,
        user_id: str,
        filters: dict[str, str] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Get a paginated activity feed with optional filters and entity enrichment.

        Args:
            user_id: The user's ID.
            filters: Optional dict with keys: activity_type, agent,
                     related_entity_type, date_start, date_end.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            Dict with activities, total_count, page, page_size.
        """
        filters = filters or {}
        offset = (page - 1) * page_size

        query = self._db.table("aria_activity").select("*").eq("user_id", user_id)

        if filters.get("activity_type"):
            query = query.eq("activity_type", filters["activity_type"])
        if filters.get("agent"):
            query = query.eq("agent", filters["agent"])
        if filters.get("related_entity_type"):
            query = query.eq("related_entity_type", filters["related_entity_type"])
        if filters.get("related_entity_id"):
            query = query.eq("related_entity_id", filters["related_entity_id"])
        if filters.get("date_start"):
            query = query.gte("created_at", filters["date_start"])
        if filters.get("date_end"):
            query = query.lte("created_at", filters["date_end"])

        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        activities = cast(list[dict[str, Any]], result.data)

        # Enrich with entity details
        for activity in activities:
            entity_type = activity.get("related_entity_type")
            entity_id = activity.get("related_entity_id")
            if entity_type and entity_id:
                details = await self._lookup_entity(entity_type, entity_id)
                activity["entity_details"] = details
            else:
                activity["entity_details"] = None

        total_count = len(activities)

        logger.info(
            "Activity feed retrieved",
            extra={"user_id": user_id, "count": total_count, "page": page},
        )

        return {
            "activities": activities,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
        }

    async def get_real_time_updates(
        self,
        user_id: str,
        since_timestamp: str,
    ) -> list[dict[str, Any]]:
        """Get new activities since the given timestamp.

        Designed for polling-based real-time updates (every 10s).

        Args:
            user_id: The user's ID.
            since_timestamp: ISO timestamp; returns activities created after this.

        Returns:
            List of activity dicts in chronological order (oldest first).
        """
        result = (
            self._db.table("aria_activity")
            .select("*")
            .eq("user_id", user_id)
            .gt("created_at", since_timestamp)
            .order("created_at", desc=False)
            .limit(100)
            .execute()
        )

        data = cast(list[dict[str, Any]], result.data)

        if data:
            logger.info(
                "Real-time updates retrieved",
                extra={"user_id": user_id, "count": len(data)},
            )

        return data

    async def create_activity(
        self,
        user_id: str,
        activity_type: str,
        title: str,
        description: str = "",
        agent: str | None = None,
        reasoning: str = "",
        confidence: float = 0.5,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new activity record.

        This should be called by ALL services when ARIA takes an action.

        Args:
            user_id: The user's ID.
            activity_type: One of STANDARD_ACTIVITY_TYPES (or custom).
            title: Short human-readable title.
            description: Longer description.
            agent: Which agent performed this.
            reasoning: ARIA's reasoning chain for transparency.
            confidence: Confidence level 0-1.
            related_entity_type: Entity type (lead, goal, contact, company).
            related_entity_id: UUID of related entity.
            metadata: Extra JSON metadata.

        Returns:
            Inserted activity dict.
        """
        row: dict[str, Any] = {
            "user_id": user_id,
            "agent": agent,
            "activity_type": activity_type,
            "title": title,
            "description": description,
            "reasoning": reasoning,
            "confidence": confidence,
            "related_entity_type": related_entity_type,
            "related_entity_id": related_entity_id,
            "metadata": metadata or {},
        }

        result = self._db.table("aria_activity").insert(row).execute()
        activity = cast(dict[str, Any], result.data[0])

        logger.info(
            "Activity created",
            extra={
                "user_id": user_id,
                "activity_id": activity["id"],
                "agent": agent,
                "type": activity_type,
            },
        )
        return activity

    async def get_activity_stats(
        self,
        user_id: str,
        period: str = "day",
    ) -> dict[str, Any]:
        """Get summary counts of activities by type and agent for a period.

        Args:
            user_id: The user's ID.
            period: One of 'day', 'week', 'month'.

        Returns:
            Dict with total, by_type, by_agent, and period.
        """
        delta = _PERIOD_DELTAS.get(period, timedelta(days=1))
        since = (datetime.now(UTC) - delta).isoformat()

        result = (
            self._db.table("aria_activity")
            .select("activity_type, agent")
            .eq("user_id", user_id)
            .gte("created_at", since)
            .execute()
        )

        rows = cast(list[dict[str, Any]], result.data)

        type_counts: Counter[str] = Counter()
        agent_counts: Counter[str] = Counter()
        for row in rows:
            type_counts[row["activity_type"]] += 1
            if row.get("agent"):
                agent_counts[row["agent"]] += 1

        stats = {
            "total": len(rows),
            "by_type": dict(type_counts),
            "by_agent": dict(agent_counts),
            "period": period,
            "since": since,
        }

        logger.info(
            "Activity stats retrieved",
            extra={"user_id": user_id, "period": period, "total": len(rows)},
        )
        return stats

    async def _lookup_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, str] | None:
        """Look up linked entity details by type and ID.

        Args:
            entity_type: The entity type (lead, goal, contact, company).
            entity_id: The entity UUID.

        Returns:
            Dict with entity_name or None if not found/unsupported.
        """
        mapping = _ENTITY_TABLE_MAP.get(entity_type)
        if not mapping:
            return None

        table_name, name_column = mapping
        try:
            result = (
                self._db.table(table_name)
                .select(f"id, {name_column}")
                .eq("id", entity_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                return {"entity_name": result.data[name_column]}
        except Exception:
            logger.warning(
                "Failed to look up entity",
                extra={"entity_type": entity_type, "entity_id": entity_id},
            )
        return None
