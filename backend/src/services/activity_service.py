"""Activity feed service for US-940.

Records agent activity and serves the chronological feed with
filtering, pagination, and agent status overview.
"""

import logging
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

KNOWN_AGENTS = ("hunter", "analyst", "strategist", "scribe", "operator", "scout")


class ActivityService:
    """Records and serves ARIA activity for the feed."""

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    async def record(
        self,
        user_id: str,
        agent: str | None = None,
        activity_type: str = "",
        title: str = "",
        description: str = "",
        reasoning: str = "",
        confidence: float = 0.5,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an activity event.

        Args:
            user_id: The user's ID.
            agent: Which agent performed this.
            activity_type: Type key (research_complete, email_drafted, etc).
            title: Short human-readable title.
            description: Longer description.
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
            "Activity recorded",
            extra={
                "user_id": user_id,
                "activity_id": activity["id"],
                "agent": agent,
                "type": activity_type,
            },
        )
        return activity

    async def get_feed(
        self,
        user_id: str,
        agent: str | None = None,
        activity_type: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get activity feed with optional filters.

        Args:
            user_id: The user's ID.
            agent: Filter by agent name.
            activity_type: Filter by activity type.
            date_start: ISO datetime lower bound.
            date_end: ISO datetime upper bound.
            search: Text search in title/description.
            limit: Max rows (1-200).
            offset: Pagination offset.

        Returns:
            List of activity dicts, newest first.
        """
        query = self._db.table("aria_activity").select("*").eq("user_id", user_id)

        if agent:
            query = query.eq("agent", agent)
        if activity_type:
            query = query.eq("activity_type", activity_type)
        if date_start:
            query = query.gte("created_at", date_start)
        if date_end:
            query = query.lte("created_at", date_end)
        if search:
            query = query.or_(f"title.ilike.%{search}%,description.ilike.%{search}%")

        result = query.order("created_at", desc=True).limit(limit).offset(offset).execute()

        data = cast(list[dict[str, Any]], result.data)
        logger.info(
            "Activity feed retrieved",
            extra={"user_id": user_id, "count": len(data)},
        )
        return data

    async def get_activity_detail(self, user_id: str, activity_id: str) -> dict[str, Any] | None:
        """Get a single activity with full reasoning.

        Args:
            user_id: The user's ID.
            activity_id: The activity UUID.

        Returns:
            Activity dict or None if not found.
        """
        result = (
            self._db.table("aria_activity")
            .select("*")
            .eq("id", activity_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result is None or result.data is None:
            return None
        return cast(dict[str, Any], result.data)

    async def get_agent_status(self, user_id: str) -> dict[str, Any]:
        """Get current status of each agent.

        Args:
            user_id: The user's ID.

        Returns:
            Dict keyed by agent name with status, last_activity, last_time.
        """
        result = (
            self._db.table("aria_activity")
            .select("agent, activity_type, title, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        rows = cast(list[dict[str, Any]], result.data)

        seen: set[str] = set()
        agent_map: dict[str, Any] = {}
        for row in rows:
            agent_name = row.get("agent")
            if agent_name and agent_name not in seen:
                seen.add(agent_name)
                agent_map[agent_name] = {
                    "status": "idle",
                    "last_activity": row["title"],
                    "last_activity_type": row.get("activity_type"),
                    "last_time": row["created_at"],
                }

        for name in KNOWN_AGENTS:
            if name not in agent_map:
                agent_map[name] = {
                    "status": "idle",
                    "last_activity": None,
                    "last_activity_type": None,
                    "last_time": None,
                }

        logger.info(
            "Agent status retrieved",
            extra={"user_id": user_id, "active_agents": len(seen)},
        )
        return agent_map
