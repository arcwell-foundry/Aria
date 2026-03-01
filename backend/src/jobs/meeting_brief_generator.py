"""Background job for pre-meeting brief generation.

This job should be scheduled to run hourly (e.g., via cron or
a task scheduler). It finds pending meeting briefs within a
configurable time window and generates brief content for each.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.services.meeting_brief import MeetingBriefService

logger = logging.getLogger(__name__)


async def find_meetings_needing_briefs(hours_ahead: int = 24) -> list[dict[str, Any]]:
    """Find pending meeting briefs within the specified time window.

    Args:
        hours_ahead: Number of hours ahead to look for meetings.

    Returns:
        List of meeting brief dicts with status "pending" within the window.
    """
    db = SupabaseClient.get_client()

    now = datetime.now(UTC)
    window_end = now + timedelta(hours=hours_ahead)

    result = (
        db.table("meeting_briefs")
        .select("*")
        .eq("status", "pending")
        .gte("meeting_time", now.isoformat())
        .lte("meeting_time", window_end.isoformat())
        .execute()
    )

    briefs = cast(list[dict[str, Any]], result.data or [])

    logger.info(
        "Found pending meeting briefs",
        extra={
            "count": len(briefs),
            "hours_ahead": hours_ahead,
            "window_start": now.isoformat(),
            "window_end": window_end.isoformat(),
        },
    )

    return briefs


async def run_meeting_brief_job(hours_ahead: int = 24) -> dict[str, Any]:
    """Run the meeting brief generation job.

    Finds all pending meeting briefs within the time window and
    generates brief content for each using the MeetingBriefService.

    Args:
        hours_ahead: Number of hours ahead to look for meetings.

    Returns:
        Summary dict with meetings_found, briefs_generated, errors, and hours_ahead.
    """
    # Find pending briefs within the window
    pending_briefs = await find_meetings_needing_briefs(hours_ahead)

    service = MeetingBriefService()
    briefs_generated = 0
    errors = 0

    for brief in pending_briefs:
        brief_id = cast(str, brief["id"])
        user_id = cast(str, brief["user_id"])

        try:
            result = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            if result is not None:
                briefs_generated += 1
                logger.info(
                    "Generated meeting brief",
                    extra={
                        "brief_id": brief_id,
                        "user_id": user_id,
                        "meeting_title": brief.get("meeting_title"),
                    },
                )

                # Record activity
                try:
                    from src.services.activity_service import ActivityService

                    await ActivityService().record(
                        user_id=user_id,
                        agent="analyst",
                        activity_type="meeting_prepped",
                        title=f"Prepared for: {brief.get('meeting_title', 'meeting')}",
                        description=(
                            f"Generated meeting brief for "
                            f"'{brief.get('meeting_title', 'upcoming meeting')}'."
                        ),
                        confidence=0.9,
                        related_entity_type="meeting_brief",
                        related_entity_id=brief_id,
                        metadata={"meeting_title": brief.get("meeting_title")},
                    )
                except Exception:
                    logger.debug("Failed to record meeting_prepped activity", exc_info=True)
            else:
                errors += 1
                logger.warning(
                    "Brief generation returned None",
                    extra={
                        "brief_id": brief_id,
                        "user_id": user_id,
                    },
                )
        except Exception as e:
            errors += 1
            logger.exception(
                "Failed to generate meeting brief",
                extra={
                    "brief_id": brief_id,
                    "user_id": user_id,
                    "error": str(e),
                },
            )

    result_summary = {
        "meetings_found": len(pending_briefs),
        "briefs_generated": briefs_generated,
        "errors": errors,
        "hours_ahead": hours_ahead,
    }

    logger.info("Meeting brief job completed", extra=result_summary)
    return result_summary
