"""Debrief scheduler service for automatic post-meeting debrief prompts.

This service runs periodically to:
1. Check for meetings that ended in the last 2 hours without debriefs
2. Create notifications prompting users for debriefs
3. Check for overdue commitments_theirs from past debriefs
4. Provide debrief counts for daily briefing

The scheduler runs every 15 minutes via APScheduler integration.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.models.notification import NotificationType
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def _format_time_ago(end_time_str: str) -> str:
    """Format time elapsed since meeting ended.

    Args:
        end_time_str: ISO format datetime string of meeting end time.

    Returns:
        Human-readable string like "1 hour ago" or "30 minutes ago".
    """
    try:
        end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        delta = now - end_time

        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes < 60:
            if total_minutes <= 1:
                return "just now"
            return f"{total_minutes} minutes ago"

        hours = total_minutes // 60
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"
    except (ValueError, TypeError):
        return "recently"


class DebriefScheduler:
    """Service for prompting users to debrief after meetings end.

    Attributes:
        db: Supabase client for database operations.
        include_internal_default: Whether to include internal meetings by default.
    """

    def __init__(self) -> None:
        """Initialize the debrief scheduler service."""
        self.db = SupabaseClient.get_client()
        self.include_internal_default = False

    async def check_and_prompt_debriefs(
        self,
        user_id: str,
        include_internal: bool | None = None,
    ) -> dict[str, Any]:
        """Check for meetings that need debriefs and create notifications.

        Finds calendar events where end_time is within the last 2 hours,
        filters out internal meetings (unless include_internal=True),
        and creates notifications for meetings without existing debriefs.

        Also checks for overdue commitments_theirs from past debriefs.

        Args:
            user_id: The user's UUID.
            include_internal: Override default internal meeting filter.
                None uses include_internal_default.

        Returns:
            Dict with:
                - meetings_checked: Number of meetings in time window
                - notifications_sent: Number of notifications created
                - internal_filtered: Number of internal meetings filtered
                - overdue_commitments_found: Number of overdue commitments
        """
        if include_internal is None:
            include_internal = self.include_internal_default

        now = datetime.now(UTC)
        two_hours_ago = now - timedelta(hours=2)

        result: dict[str, Any] = {
            "meetings_checked": 0,
            "notifications_sent": 0,
            "internal_filtered": 0,
            "overdue_commitments_found": 0,
        }

        # Query calendar events that ended in the last 2 hours
        try:
            events_response = (
                self.db.table("calendar_events")
                .select("id, title, start_time, end_time, attendees, external_company, metadata")
                .eq("user_id", user_id)
                .gte("end_time", two_hours_ago.isoformat())
                .lte("end_time", now.isoformat())
                .execute()
            )

            events = events_response.data or []
            result["meetings_checked"] = len(events)

        except Exception:
            logger.exception(
                "Failed to query calendar events for debrief prompts",
                extra={"user_id": user_id},
            )
            return result

        # Process each event
        for event in events:
            try:
                # Check if internal meeting
                metadata = event.get("metadata") or {}
                is_internal = metadata.get("internal_only", False)

                if is_internal and not include_internal:
                    result["internal_filtered"] += 1
                    continue

                # Check if debrief already exists
                debrief_response = (
                    self.db.table("meeting_debriefs")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("meeting_id", event["id"])
                    .maybe_single()
                    .execute()
                )

                if debrief_response.data:
                    # Debrief already exists, skip
                    continue

                # Create debrief prompt notification
                await self._create_debrief_prompt_notification(user_id, event)
                result["notifications_sent"] += 1

            except Exception:
                logger.warning(
                    "Failed to process event for debrief prompt",
                    extra={"user_id": user_id, "event_id": event.get("id")},
                    exc_info=True,
                )

        # Check for overdue commitments_theirs
        try:
            overdue_commitments = await self._find_overdue_commitments(user_id)
            result["overdue_commitments_found"] = len(overdue_commitments)
        except Exception:
            logger.warning(
                "Failed to check overdue commitments",
                extra={"user_id": user_id},
                exc_info=True,
            )

        logger.info(
            "Debrief prompt check complete",
            extra={
                "user_id": user_id,
                "meetings_checked": result["meetings_checked"],
                "notifications_sent": result["notifications_sent"],
                "internal_filtered": result["internal_filtered"],
                "overdue_commitments": result["overdue_commitments_found"],
            },
        )

        return result

    async def _create_debrief_prompt_notification(
        self,
        user_id: str,
        event: dict[str, Any],
    ) -> None:
        """Create a notification prompting user to debrief a meeting.

        Args:
            user_id: The user's UUID.
            event: Calendar event data dict.
        """
        meeting_title = event.get("title", "Meeting")
        attendees = event.get("attendees", [])
        external_company = event.get("external_company")
        end_time = event.get("end_time", "")

        # Build message
        if external_company:
            attendees_str = external_company
        elif attendees:
            # Use first attendee email if no company
            first_attendee = attendees[0] if attendees else "attendees"
            attendees_str = (
                first_attendee
                if isinstance(first_attendee, str)
                else first_attendee.get("email", "attendees")
            )
        else:
            attendees_str = "your meeting"

        time_ago = _format_time_ago(end_time)

        message = f"Your meeting with {attendees_str} ended {time_ago}. Quick debrief?"

        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.MEETING_DEBRIEF_PROMPT,
            title=f"Debrief: {meeting_title}",
            message=message,
            link=f"/dashboard/debriefs/new?meeting_id={event['id']}",
            metadata={
                "meeting_id": event["id"],
                "prompt_type": "meeting_debrief_prompt",
            },
        )

    async def _find_overdue_commitments(self, user_id: str) -> list[dict[str, Any]]:
        """Find overdue commitments_theirs from past debriefs.

        Looks for commitments where:
        - The debrief has commitments_theirs
        - The debrief is not linked to a completed follow-up
        - The debrief was created more than 3 days ago

        Args:
            user_id: The user's UUID.

        Returns:
            List of debriefs with overdue commitments.
        """
        now = datetime.now(UTC)
        three_days_ago = now - timedelta(days=3)

        try:
            response = (
                self.db.table("meeting_debriefs")
                .select("id, meeting_title, commitments_theirs, linked_lead_id, created_at")
                .eq("user_id", user_id)
                .eq("follow_up_needed", True)
                .neq("commitments_theirs", [])
                .lt("created_at", three_days_ago.isoformat())
                .execute()
            )

            return response.data or []

        except Exception:
            logger.exception(
                "Failed to query overdue commitments",
                extra={"user_id": user_id},
            )
            return []

    async def get_debrief_prompt_count(
        self,
        user_id: str,
        include_internal: bool = False,
    ) -> int:
        """Get count of meetings needing debriefs for daily briefing.

        This is used by the daily briefing to show "You have N meetings without debriefs".

        Args:
            user_id: The user's UUID.
            include_internal: Whether to include internal meetings.

        Returns:
            Count of meetings without debriefs.
        """
        now = datetime.now(UTC)
        # Look back 7 days for unbriefted meetings
        seven_days_ago = now - timedelta(days=7)

        try:
            events_response = (
                self.db.table("calendar_events")
                .select("id, metadata")
                .eq("user_id", user_id)
                .gte("end_time", seven_days_ago.isoformat())
                .lte("end_time", now.isoformat())
                .execute()
            )

            events = events_response.data or []
            count = 0

            for event in events:
                # Check if internal meeting
                metadata = event.get("metadata") or {}
                is_internal = metadata.get("internal_only", False)

                if is_internal and not include_internal:
                    continue

                # Check if debrief exists
                debrief_response = (
                    self.db.table("meeting_debriefs")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("meeting_id", event["id"])
                    .maybe_single()
                    .execute()
                )

                if not debrief_response.data:
                    count += 1

            return count

        except Exception:
            logger.exception(
                "Failed to get debrief prompt count",
                extra={"user_id": user_id},
            )
            return 0


async def run_debrief_prompt_scheduler() -> dict[str, Any]:
    """Run the debrief prompt scheduler for all active users.

    This is the entry point called by APScheduler every 15 minutes.

    Returns:
        Dict with users_processed, total_notifications, and errors counts.
    """
    result: dict[str, Any] = {
        "users_processed": 0,
        "total_notifications": 0,
        "errors": 0,
    }

    try:
        db = SupabaseClient.get_client()

        # Find users who completed onboarding
        users_response = (
            db.table("onboarding_state")
            .select("user_id")
            .not_.is_("completed_at", "null")
            .execute()
        )

        user_ids = [row["user_id"] for row in (users_response.data or [])]
        logger.info("Debrief prompt scheduler: processing %d users", len(user_ids))

        scheduler = DebriefScheduler()

        for user_id in user_ids:
            try:
                user_result = await scheduler.check_and_prompt_debriefs(user_id)
                result["users_processed"] += 1
                result["total_notifications"] += user_result.get("notifications_sent", 0)
            except Exception:
                logger.warning(
                    "Debrief prompt scheduler failed for user %s",
                    user_id,
                    exc_info=True,
                )
                result["errors"] += 1

        logger.info(
            "Debrief prompt scheduler complete: %d users, %d notifications, %d errors",
            result["users_processed"],
            result["total_notifications"],
            result["errors"],
        )

    except Exception:
        logger.exception("Debrief prompt scheduler run failed")

    return result
