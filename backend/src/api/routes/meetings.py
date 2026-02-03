"""Meeting brief API routes for pre-meeting research."""

import logging

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.models.meeting_brief import (
    BriefStatus,
    GenerateBriefRequest,
    MeetingBriefResponse,
    UpcomingMeetingResponse,
)
from src.services.meeting_brief import MeetingBriefService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("/upcoming", response_model=list[UpcomingMeetingResponse])
async def get_upcoming_meetings(
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50, description="Maximum number of meetings"),
) -> list[UpcomingMeetingResponse]:
    """Get upcoming meetings with brief status.

    Returns a list of upcoming meetings for the current user,
    including the status of any existing meeting briefs.
    """
    service = MeetingBriefService()
    meetings = await service.get_upcoming_meetings(current_user.id, limit)

    logger.info(
        "Retrieved upcoming meetings",
        extra={"user_id": current_user.id, "count": len(meetings)},
    )

    return [
        UpcomingMeetingResponse(
            calendar_event_id=m["calendar_event_id"],
            meeting_title=m.get("meeting_title"),
            meeting_time=m["meeting_time"],
            attendees=m.get("attendees", []),
            brief_status=BriefStatus(m["status"]) if m.get("status") else None,
            brief_id=m.get("id"),
        )
        for m in meetings
    ]


@router.get("/{calendar_event_id}/brief", response_model=MeetingBriefResponse)
async def get_meeting_brief(
    current_user: CurrentUser,
    calendar_event_id: str,
) -> MeetingBriefResponse:
    """Get meeting brief by calendar event ID.

    Returns the meeting brief for the specified calendar event.
    Raises 404 if no brief exists for this event.
    """
    service = MeetingBriefService()
    brief = await service.get_brief(current_user.id, calendar_event_id)

    if not brief:
        raise HTTPException(
            status_code=404,
            detail=f"Meeting brief for event {calendar_event_id} not found",
        )

    logger.info(
        "Retrieved meeting brief",
        extra={
            "user_id": current_user.id,
            "calendar_event_id": calendar_event_id,
            "status": brief.get("status"),
        },
    )

    return MeetingBriefResponse(
        id=brief["id"],
        calendar_event_id=brief["calendar_event_id"],
        meeting_title=brief.get("meeting_title"),
        meeting_time=brief["meeting_time"],
        status=BriefStatus(brief["status"]),
        brief_content=brief.get("brief_content", {}),
        generated_at=brief.get("generated_at"),
        error_message=brief.get("error_message"),
    )


@router.post(
    "/{calendar_event_id}/brief/generate",
    response_model=MeetingBriefResponse,
    status_code=202,
)
async def generate_meeting_brief(
    current_user: CurrentUser,
    calendar_event_id: str,
    request: GenerateBriefRequest,
) -> MeetingBriefResponse:
    """Generate or regenerate a meeting brief on-demand.

    Creates a new meeting brief if one doesn't exist, or triggers
    regeneration if a brief already exists. The actual generation
    happens asynchronously via a background job.

    Returns 202 Accepted with the brief status for polling.
    """
    service = MeetingBriefService()

    # Check if brief already exists
    existing_brief = await service.get_brief(current_user.id, calendar_event_id)

    if existing_brief:
        # Reset status to pending for regeneration
        await service.update_brief_status(
            user_id=current_user.id,
            brief_id=existing_brief["id"],
            status="pending",
        )
        brief_id = existing_brief["id"]
        is_regeneration = True
    else:
        # Create new brief
        new_brief = await service.create_brief(
            user_id=current_user.id,
            calendar_event_id=calendar_event_id,
            meeting_title=request.meeting_title,
            meeting_time=request.meeting_time,
            attendees=[str(email) for email in request.attendee_emails],
        )
        brief_id = new_brief["id"]
        is_regeneration = False

    logger.info(
        "Meeting brief generation requested",
        extra={
            "user_id": current_user.id,
            "calendar_event_id": calendar_event_id,
            "brief_id": brief_id,
            "is_regeneration": is_regeneration,
        },
    )

    # Note: Background job would pick this up and call generate_brief_content
    # For now, we return 202 to indicate the request is accepted

    # Fetch the updated brief to return complete response
    updated_brief = await service.get_brief(current_user.id, calendar_event_id)
    if not updated_brief:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve brief after creation/update",
        )

    return MeetingBriefResponse(
        id=updated_brief["id"],
        calendar_event_id=updated_brief["calendar_event_id"],
        meeting_title=updated_brief.get("meeting_title"),
        meeting_time=updated_brief["meeting_time"],
        status=BriefStatus(updated_brief["status"]),
        brief_content=updated_brief.get("brief_content", {}),
        generated_at=updated_brief.get("generated_at"),
        error_message=updated_brief.get("error_message"),
    )
