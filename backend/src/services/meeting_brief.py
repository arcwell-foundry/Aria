"""Meeting brief service for pre-meeting research.

Manages meeting brief CRUD operations and coordinates research generation.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class MeetingBriefService:
    """Service for managing pre-meeting research briefs."""

    def __init__(self) -> None:
        """Initialize meeting brief service."""
        self._db = SupabaseClient.get_client()

    async def get_brief(self, user_id: str, calendar_event_id: str) -> dict[str, Any] | None:
        """Get a meeting brief by calendar event ID.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.

        Returns:
            Brief dict if found, None otherwise.
        """
        result = (
            self._db.table("meeting_briefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("calendar_event_id", calendar_event_id)
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def get_brief_by_id(self, user_id: str, brief_id: str) -> dict[str, Any] | None:
        """Get a meeting brief by its ID.

        Args:
            user_id: The user's ID.
            brief_id: The brief's ID.

        Returns:
            Brief dict if found, None otherwise.
        """
        result = (
            self._db.table("meeting_briefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", brief_id)
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def create_brief(
        self,
        user_id: str,
        calendar_event_id: str,
        meeting_title: str | None,
        meeting_time: datetime,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a pending meeting brief.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.
            meeting_title: Meeting title.
            meeting_time: Meeting start time.
            attendees: List of attendee email addresses.

        Returns:
            Created brief dict.
        """
        brief_data: dict[str, Any] = {
            "user_id": user_id,
            "calendar_event_id": calendar_event_id,
            "meeting_title": meeting_title,
            "meeting_time": meeting_time.isoformat(),
            "attendees": attendees or [],
            "status": "pending",
            "brief_content": {},
        }

        result = self._db.table("meeting_briefs").insert(brief_data).execute()

        logger.info(
            "Created pending meeting brief",
            extra={
                "user_id": user_id,
                "calendar_event_id": calendar_event_id,
                "meeting_title": meeting_title,
            },
        )

        return cast(dict[str, Any], result.data[0])

    async def update_brief_status(
        self,
        user_id: str,
        brief_id: str,
        status: str,
        brief_content: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        """Update brief status and optionally content.

        Args:
            user_id: The user's ID.
            brief_id: The brief's ID.
            status: New status (pending/generating/completed/failed).
            brief_content: Optional brief content to set.
            error_message: Optional error message if failed.

        Returns:
            Updated brief dict, or None if not found.
        """
        update_data: dict[str, Any] = {"status": status}

        if brief_content is not None:
            update_data["brief_content"] = brief_content
            update_data["generated_at"] = datetime.now(UTC).isoformat()

        if error_message is not None:
            update_data["error_message"] = error_message

        result = (
            self._db.table("meeting_briefs")
            .update(update_data)
            .eq("id", brief_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            logger.warning(
                "Brief not found for update",
                extra={"brief_id": brief_id, "user_id": user_id},
            )
            return None

        logger.info(
            "Updated meeting brief status",
            extra={"brief_id": brief_id, "status": status, "user_id": user_id},
        )

        return cast(dict[str, Any], result.data[0])

    async def get_upcoming_meetings(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get upcoming meetings with brief status.

        Args:
            user_id: The user's ID.
            limit: Maximum number of meetings to return.

        Returns:
            List of meeting briefs ordered by meeting time.
        """
        now = datetime.now(UTC).isoformat()

        result = (
            self._db.table("meeting_briefs")
            .select("id, calendar_event_id, meeting_title, meeting_time, status, attendees")
            .eq("user_id", user_id)
            .gte("meeting_time", now)
            .order("meeting_time", desc=False)
            .limit(limit)
            .execute()
        )

        return cast(list[dict[str, Any]], result.data or [])

    async def upsert_brief(
        self,
        user_id: str,
        calendar_event_id: str,
        meeting_title: str | None,
        meeting_time: datetime,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create or update a meeting brief.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.
            meeting_title: Meeting title.
            meeting_time: Meeting start time.
            attendees: List of attendee email addresses.

        Returns:
            Upserted brief dict.
        """
        brief_data: dict[str, Any] = {
            "user_id": user_id,
            "calendar_event_id": calendar_event_id,
            "meeting_title": meeting_title,
            "meeting_time": meeting_time.isoformat(),
            "attendees": attendees or [],
            "status": "pending",
            "brief_content": {},
        }

        result = (
            self._db.table("meeting_briefs")
            .upsert(brief_data, on_conflict="user_id,calendar_event_id")
            .execute()
        )

        return cast(dict[str, Any], result.data[0])
