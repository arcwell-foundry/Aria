"""Meeting debrief API routes for ARIA.

This module provides endpoints for:
- Initiating debriefs (Phase 1: create pending debrief)
- Submitting debrief notes (Phase 2+3: AI extraction + downstream integration)
- Querying debriefs with pagination and filtering
- Finding meetings that need debriefing
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.debrief_service import DebriefService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debriefs", tags=["debriefs"])


def _get_service() -> DebriefService:
    """Get debrief service instance."""
    return DebriefService()


# =============================================================================
# Request/Response Models
# =============================================================================


class DebriefInitiateRequest(BaseModel):
    """Request model for initiating a debrief."""

    meeting_id: str = Field(
        ..., min_length=1, max_length=100, description="The meeting's unique identifier"
    )
    calendar_event_id: UUID | None = Field(
        None, description="Optional calendar event UUID (alternative to meeting_id)"
    )


class DebriefInitiateResponse(BaseModel):
    """Response model for initiating a debrief."""

    id: str
    meeting_title: str | None
    meeting_time: str | None
    linked_lead_id: str | None
    pre_filled_context: dict[str, Any] = Field(default_factory=dict)


class DebriefSubmitRequest(BaseModel):
    """Request model for submitting debrief notes."""

    raw_notes: str = Field(
        ..., min_length=1, max_length=10000, description="User's debrief notes"
    )
    outcome: str | None = Field(
        None, description="Optional meeting outcome override (positive/neutral/negative)"
    )
    follow_up_needed: bool | None = Field(
        None, description="Optional override for follow-up flag"
    )


class DebriefSubmitResponse(BaseModel):
    """Response model for submitted debrief."""

    id: str
    summary: str
    action_items: list[dict[str, Any]]
    commitments_ours: list[str]
    commitments_theirs: list[str]
    insights: list[dict[str, Any]]
    follow_up_draft: str | None = None


class DebriefListItem(BaseModel):
    """Response model for debrief list items."""

    id: str
    meeting_id: str
    meeting_title: str | None
    meeting_time: str | None
    outcome: str | None
    action_items_count: int
    linked_lead_id: str | None
    status: str
    created_at: str


class DebriefListResponse(BaseModel):
    """Paginated response for debrief list."""

    items: list[DebriefListItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class DebriefResponse(BaseModel):
    """Response model for a full debrief."""

    id: str
    user_id: str
    meeting_id: str
    meeting_title: str | None
    meeting_time: str | None
    raw_notes: str | None
    summary: str | None
    outcome: str | None
    action_items: list[dict[str, Any]]
    commitments_ours: list[str]
    commitments_theirs: list[str]
    insights: list[dict[str, Any]]
    follow_up_needed: bool
    follow_up_draft: str | None
    linked_lead_id: str | None
    status: str
    created_at: str


class PendingMeetingResponse(BaseModel):
    """Response model for meetings needing debrief."""

    id: str
    title: str | None
    start_time: str | None
    end_time: str | None
    external_company: str | None
    attendees: list[Any]


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=DebriefInitiateResponse)
async def initiate_debrief(
    data: DebriefInitiateRequest,
    current_user: CurrentUser,
) -> DebriefInitiateResponse:
    """Initiate a debrief for a meeting.

    Creates a pending debrief linked to a calendar event. Auto-links to lead
    memory if attendees match known stakeholders. Pre-fills meeting context.

    Args:
        data: Debrief initiation request with meeting_id or calendar_event_id.
        current_user: The authenticated user.

    Returns:
        Created debrief with meeting info and pre-filled context.

    Raises:
        HTTPException: If meeting not found or debrief already exists.
    """
    service = _get_service()

    # Use calendar_event_id if provided, otherwise use meeting_id
    meeting_id = str(data.calendar_event_id) if data.calendar_event_id else data.meeting_id

    try:
        result = await service.initiate_debrief(
            user_id=current_user.id,
            meeting_id=meeting_id,
        )
    except Exception as e:
        logger.exception(
            "Failed to initiate debrief",
            extra={
                "user_id": current_user.id,
                "meeting_id": meeting_id,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="Failed to initiate debrief. Please try again.",
        ) from e

    logger.info(
        "Debrief initiated",
        extra={
            "user_id": current_user.id,
            "meeting_id": meeting_id,
            "debrief_id": result.get("id"),
        },
    )

    return DebriefInitiateResponse(
        id=result["id"],
        meeting_title=result.get("meeting_title"),
        meeting_time=result.get("meeting_time"),
        linked_lead_id=result.get("linked_lead_id"),
        pre_filled_context={
            "meeting_title": result.get("meeting_title"),
            "meeting_time": result.get("meeting_time"),
        },
    )


@router.put("/{debrief_id}", response_model=DebriefSubmitResponse)
async def submit_debrief(
    debrief_id: str,
    data: DebriefSubmitRequest,
    current_user: CurrentUser,
) -> DebriefSubmitResponse:
    """Submit debrief notes and trigger AI extraction pipeline.

    Processes user's debrief notes to extract structured data, then performs
    downstream integration (lead memory updates, email draft generation, etc.).

    Args:
        debrief_id: The debrief's UUID.
        data: Debrief submission with notes and optional overrides.
        current_user: The authenticated user.

    Returns:
        Extracted debrief data with action items, commitments, and insights.

    Raises:
        HTTPException: If debrief not found or processing fails.
    """
    service = _get_service()

    # Verify debrief belongs to user
    existing = await service.get_debrief(current_user.id, debrief_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Debrief not found")

    try:
        # Phase 2: Process notes with AI extraction
        result = await service.process_debrief(
            debrief_id=debrief_id,
            user_input=data.raw_notes,
        )

        # Apply optional overrides
        if data.outcome or data.follow_up_needed is not None:
            override_data: dict[str, Any] = {}
            if data.outcome:
                override_data["outcome"] = data.outcome
            if data.follow_up_needed is not None:
                override_data["follow_up_needed"] = data.follow_up_needed
            # The process_debrief already updated, we need to re-update

        # Phase 3: Post-process (lead memory, email draft, etc.)
        result = await service.post_process_debrief(debrief_id)

    except ValueError as e:
        logger.warning(
            "Debrief processing failed",
            extra={
                "user_id": current_user.id,
                "debrief_id": debrief_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid debrief data. Please check and try again.",
        ) from e
    except Exception as e:
        logger.exception(
            "Debrief processing failed unexpectedly",
            extra={
                "user_id": current_user.id,
                "debrief_id": debrief_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to process debrief. Please try again.",
        ) from e

    logger.info(
        "Debrief submitted and processed",
        extra={
            "user_id": current_user.id,
            "debrief_id": debrief_id,
            "outcome": result.get("outcome"),
            "action_items_count": len(result.get("action_items", [])),
        },
    )

    return DebriefSubmitResponse(
        id=result["id"],
        summary=result.get("summary", ""),
        action_items=result.get("action_items", []),
        commitments_ours=result.get("commitments_ours", []),
        commitments_theirs=result.get("commitments_theirs", []),
        insights=result.get("insights", []),
        follow_up_draft=result.get("follow_up_draft"),
    )


@router.get("", response_model=DebriefListResponse)
async def list_debriefs(
    current_user: CurrentUser,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    linked_lead_id: str | None = Query(None, description="Filter by linked lead ID"),
) -> DebriefListResponse:
    """List user's debriefs with pagination and filtering.

    Returns paginated list of debriefs with optional date range and lead filtering.

    Args:
        current_user: The authenticated user.
        page: Page number (1-indexed).
        page_size: Number of items per page.
        start_date: Optional start date filter.
        end_date: Optional end date filter.
        linked_lead_id: Optional lead ID filter.

    Returns:
        Paginated list of debriefs with summary info.
    """
    service = _get_service()

    # Get filtered debriefs from service
    debriefs = await service.list_debriefs_filtered(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        linked_lead_id=linked_lead_id,
    )

    # Transform to list items
    items = [
        DebriefListItem(
            id=d["id"],
            meeting_id=d.get("meeting_id", ""),
            meeting_title=d.get("meeting_title"),
            meeting_time=d.get("meeting_time"),
            outcome=d.get("outcome"),
            action_items_count=len(d.get("action_items", [])),
            linked_lead_id=d.get("linked_lead_id"),
            status=d.get("status", "completed"),
            created_at=d.get("created_at", ""),
        )
        for d in debriefs.get("items", [])
    ]

    logger.info(
        "Debriefs listed",
        extra={
            "user_id": current_user.id,
            "page": page,
            "count": len(items),
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "linked_lead_id": linked_lead_id,
            },
        },
    )

    return DebriefListResponse(
        items=items,
        total=debriefs.get("total", len(items)),
        page=page,
        page_size=page_size,
        has_more=debriefs.get("has_more", False),
    )


@router.get("/pending", response_model=list[PendingMeetingResponse])
async def get_pending_debriefs(
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50, description="Maximum meetings to return"),
) -> list[PendingMeetingResponse]:
    """Get meetings that need debriefing.

    Returns calendar events that have ended but don't have an associated debrief.

    Args:
        current_user: The authenticated user.
        limit: Maximum number of meetings to return.

    Returns:
        List of meetings needing debrief.
    """
    service = _get_service()

    pending_meetings = await service.check_pending_debriefs(current_user.id)

    # Apply limit
    pending_meetings = pending_meetings[:limit]

    logger.info(
        "Pending debriefs retrieved",
        extra={
            "user_id": current_user.id,
            "count": len(pending_meetings),
        },
    )

    return [
        PendingMeetingResponse(
            id=m["id"],
            title=m.get("title"),
            start_time=m.get("start_time"),
            end_time=m.get("end_time"),
            external_company=m.get("external_company"),
            attendees=m.get("attendees", []),
        )
        for m in pending_meetings
    ]


@router.get("/{debrief_id}", response_model=DebriefResponse)
async def get_debrief(
    debrief_id: str,
    current_user: CurrentUser,
) -> DebriefResponse:
    """Get full debrief details.

    Returns complete debrief information including all extracted data.

    Args:
        debrief_id: The debrief's UUID.
        current_user: The authenticated user.

    Returns:
        Full debrief data.

    Raises:
        HTTPException: If debrief not found.
    """
    service = _get_service()
    result = await service.get_debrief(current_user.id, debrief_id)

    if result is None:
        logger.warning(
            "Debrief not found",
            extra={
                "user_id": current_user.id,
                "debrief_id": debrief_id,
            },
        )
        raise HTTPException(status_code=404, detail="Debrief not found")

    logger.info(
        "Debrief retrieved",
        extra={
            "user_id": current_user.id,
            "debrief_id": debrief_id,
        },
    )

    return DebriefResponse(
        id=result["id"],
        user_id=result["user_id"],
        meeting_id=result["meeting_id"],
        meeting_title=result.get("meeting_title"),
        meeting_time=result.get("meeting_time"),
        raw_notes=result.get("raw_notes"),
        summary=result.get("summary"),
        outcome=result.get("outcome"),
        action_items=result.get("action_items", []),
        commitments_ours=result.get("commitments_ours", []),
        commitments_theirs=result.get("commitments_theirs", []),
        insights=result.get("insights", []),
        follow_up_needed=result.get("follow_up_needed", False),
        follow_up_draft=result.get("follow_up_draft"),
        linked_lead_id=result.get("linked_lead_id"),
        status=result.get("status", "completed"),
        created_at=result.get("created_at", ""),
    )


@router.get("/meeting/{meeting_id}", response_model=list[DebriefResponse])
async def get_debriefs_for_meeting(
    meeting_id: str,
    current_user: CurrentUser,
) -> list[DebriefResponse]:
    """Get all debriefs for a specific meeting.

    Returns all debriefs associated with a given meeting.

    Args:
        meeting_id: The meeting's unique identifier.
        current_user: The authenticated user.

    Returns:
        List of debrief data for the meeting.
    """
    service = _get_service()
    debriefs = await service.get_debriefs_for_meeting(current_user.id, meeting_id)

    logger.info(
        "Meeting debriefs retrieved",
        extra={
            "user_id": current_user.id,
            "meeting_id": meeting_id,
            "count": len(debriefs),
        },
    )

    return [
        DebriefResponse(
            id=d["id"],
            user_id=d["user_id"],
            meeting_id=d["meeting_id"],
            meeting_title=d.get("meeting_title"),
            meeting_time=d.get("meeting_time"),
            raw_notes=d.get("raw_notes"),
            summary=d.get("summary"),
            outcome=d.get("outcome"),
            action_items=d.get("action_items", []),
            commitments_ours=d.get("commitments_ours", []),
            commitments_theirs=d.get("commitments_theirs", []),
            insights=d.get("insights", []),
            follow_up_needed=d.get("follow_up_needed", False),
            follow_up_draft=d.get("follow_up_draft"),
            linked_lead_id=d.get("linked_lead_id"),
            status=d.get("status", "completed"),
            created_at=d.get("created_at", ""),
        )
        for d in debriefs
    ]
