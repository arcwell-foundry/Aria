"""Communications page API routes.

User-facing endpoints for the Communications page, including:
- Contact history: Unified timeline of all communications with a specific contact
- Analytics: Communication metrics and response time analytics
- Upcoming meetings: Calendar events enriched with email context
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.utils.email_pipeline_linker import get_pipeline_context_for_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/communications", tags=["communications"])


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class ContactHistoryEntry(BaseModel):
    """A single entry in the contact history timeline."""

    type: str = Field(..., description="Entry type: received, draft, sent, or dismissed")
    timestamp: str = Field(..., description="ISO timestamp of the communication")
    subject: str | None = Field(None, description="Email subject line")
    snippet: str | None = Field(None, description="Preview/snippet of the content")
    status: str | None = Field(None, description="Status for drafts (draft, sent, dismissed, etc.)")
    email_id: str | None = Field(None, description="Email ID from email_scan_log")
    draft_id: str | None = Field(None, description="Draft ID from email_drafts")
    category: str | None = Field(None, description="Category for received emails (NEEDS_REPLY, FYI, SKIP)")
    urgency: str | None = Field(None, description="Urgency level for received emails")
    confidence: float | None = Field(None, description="Confidence score")


class PipelineContextModel(BaseModel):
    """Pipeline context for a contact."""

    company_name: str | None = None
    lead_name: str | None = None
    lead_id: str | None = None
    lifecycle_stage: str | None = None
    health_score: int | None = None
    relationship_type: str | None = None
    source: str = "unknown"


class ContactHistoryResponse(BaseModel):
    """Response from contact history endpoint."""

    contact_email: str = Field(..., description="The contact's email address")
    contact_name: str | None = Field(None, description="The contact's display name (if known)")
    pipeline_context: PipelineContextModel | None = Field(
        None, description="Pipeline context if contact is linked to a lead/account"
    )
    entries: list[ContactHistoryEntry] = Field(
        default_factory=list,
        description="Chronologically sorted timeline entries",
    )
    total_count: int = Field(..., description="Total number of entries")
    received_count: int = Field(0, description="Number of emails received from contact")
    sent_count: int = Field(0, description="Number of emails sent to contact")
    draft_count: int = Field(0, description="Number of pending drafts to contact")


class CommunicationAnalyticsResponse(BaseModel):
    """Response model for communications analytics endpoint."""

    has_data: bool = Field(..., description="Whether user has enough data for analytics")
    avg_response_hours: float | None = Field(None, description="Average response time in hours")
    fastest_response_hours: float | None = Field(None, description="Fastest response time in hours")
    slowest_response_hours: float | None = Field(None, description="Slowest response time in hours")
    draft_coverage_pct: float | None = Field(None, description="Percentage of NEEDS_REPLY emails with drafts (0-100)")
    draft_coverage_count: int = Field(0, description="Number of NEEDS_REPLY emails with drafts")
    needs_reply_count: int = Field(0, description="Total NEEDS_REPLY emails")
    volume_7d: list[dict[str, Any]] = Field(
        default_factory=list,
        description="7-day email volume trends (received, drafted, sent)",
    )
    classification: dict[str, int] = Field(
        default_factory=lambda: {"NEEDS_REPLY": 0, "FYI": 0, "SKIP": 0},
        description="Email classification distribution counts",
    )
    classification_pct: dict[str, float] = Field(
        default_factory=lambda: {"NEEDS_REPLY": 0.0, "FYI": 0.0, "SKIP": 0.0},
        description="Email classification distribution percentages",
    )
    response_by_contact_type: dict[str, float] = Field(
        default_factory=dict,
        description="Average response time by contact type (investor, partner, etc.)",
    )


class VolumeDayEntry(BaseModel):
    """A single day's volume data."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    received: int = Field(0, description="Number of emails received")
    drafted: int = Field(0, description="Number of drafts created")
    sent: int = Field(0, description="Number of emails sent")


class MeetingAttendee(BaseModel):
    """An attendee in an upcoming meeting."""

    name: str = Field(..., description="Attendee display name")
    email: str = Field(..., description="Attendee email address")


class MeetingEmailContext(BaseModel):
    """Email communication context for an upcoming meeting."""

    contact_email: str = Field(..., description="Primary contact email")
    total_emails: int = Field(0, description="Total email interactions with this contact")
    latest_subject: str | None = Field(None, description="Subject of the most recent email")
    latest_date: str | None = Field(None, description="ISO timestamp of the most recent email")
    latest_date_relative: str | None = Field(None, description="Relative time string (e.g., '5d ago')")
    has_pending_draft: bool = Field(False, description="Whether there is a pending draft for this contact")
    draft_id: str | None = Field(None, description="ID of the pending draft, if any")
    pipeline_context: dict[str, Any] | None = Field(
        None, description="Pipeline context (company, lead, stage, health)"
    )


class UpcomingMeetingWithContext(BaseModel):
    """An upcoming meeting enriched with email context."""

    meeting_id: str | None = Field(None, description="Calendar event ID")
    meeting_title: str = Field(..., description="Meeting title")
    meeting_time: str = Field(..., description="ISO timestamp of meeting start")
    time_until: str = Field(..., description="Human-readable time until meeting (e.g., '2 hours')")
    attendees: list[MeetingAttendee] = Field(
        default_factory=list, description="Meeting attendees"
    )
    email_context: MeetingEmailContext = Field(
        ..., description="Email communication context for the primary contact"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/contact-history", response_model=ContactHistoryResponse)
async def get_contact_history(
    current_user: CurrentUser,
    email: str = Query(
        ...,
        description="Contact email address to look up",
        min_length=1,
        max_length=255,
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Maximum number of entries to return (1-200)",
    ),
) -> dict[str, Any]:
    """Get unified communication history with a specific contact.

    Merges data from both email_scan_log (incoming emails) and email_drafts
    (outgoing drafts/sent emails) to provide a complete timeline of all
    communications with a specific contact.

    Args:
        current_user: The authenticated user.
        email: The contact's email address to look up.
        limit: Maximum number of entries to return.

    Returns:
        ContactHistoryResponse with merged timeline sorted by timestamp (newest first).

    Raises:
        HTTPException: If query fails due to database errors.
    """
    user_id = current_user.id
    normalized_email = email.lower().strip()

    logger.info(
        "COMMUNICATIONS_API: Fetching contact history for user %s, email %s",
        user_id,
        normalized_email,
    )

    try:
        db = SupabaseClient.get_client()
        entries: list[dict[str, Any]] = []
        contact_name: str | None = None
        received_count = 0
        sent_count = 0
        draft_count = 0

        # 1. Query email_scan_log for incoming emails FROM this contact
        scan_result = (
            db.table("email_scan_log")
            .select("*")
            .eq("user_id", user_id)
            .ilike("sender_email", normalized_email)
            .order("scanned_at", desc=True)
            .limit(limit)
            .execute()
        )

        for row in scan_result.data or []:
            # Capture contact name from first match
            if not contact_name and row.get("sender_name"):
                contact_name = row.get("sender_name")

            entries.append({
                "type": "received",
                "timestamp": row.get("scanned_at", ""),
                "subject": row.get("subject"),
                "snippet": row.get("snippet") or row.get("reason", "")[:200],
                "status": None,
                "email_id": row.get("email_id"),
                "draft_id": None,
                "category": row.get("category"),
                "urgency": row.get("urgency"),
                "confidence": row.get("confidence"),
            })
            received_count += 1

        # 2. Query email_drafts for outgoing emails TO this contact
        drafts_result = (
            db.table("email_drafts")
            .select("*")
            .eq("user_id", user_id)
            .ilike("recipient_email", normalized_email)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        for row in drafts_result.data or []:
            # Capture contact name from first match
            if not contact_name and row.get("recipient_name"):
                contact_name = row.get("recipient_name")

            status_val = row.get("status", "draft")
            entry_type = "sent" if status_val == "sent" else "draft"
            if status_val == "dismissed":
                entry_type = "dismissed"

            entries.append({
                "type": entry_type,
                "timestamp": row.get("created_at", ""),
                "subject": row.get("subject"),
                "snippet": _generate_snippet(row.get("body")),
                "status": status_val,
                "email_id": row.get("original_email_id"),
                "draft_id": row.get("id"),
                "category": None,
                "urgency": None,
                "confidence": row.get("confidence_level"),
            })

            if status_val == "sent":
                sent_count += 1
            elif status_val in ("draft", "pending_review", "approved"):
                draft_count += 1

        # 3. Sort all entries by timestamp (newest first)
        entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # 4. Apply limit
        entries = entries[:limit]

        # 5. Get pipeline context for this contact
        pipeline_ctx = None
        try:
            pipeline_ctx = await get_pipeline_context_for_email(
                db=db,
                user_id=user_id,
                contact_email=normalized_email,
            )
        except Exception as e:
            logger.warning(
                "COMMUNICATIONS_API: Pipeline context lookup failed for %s: %s",
                normalized_email,
                e,
            )

        logger.info(
            "COMMUNICATIONS_API: Returned %d entries for contact %s (received=%d, sent=%d, draft=%d)",
            len(entries),
            normalized_email,
            received_count,
            sent_count,
            draft_count,
        )

        return {
            "contact_email": normalized_email,
            "contact_name": contact_name,
            "pipeline_context": pipeline_ctx,
            "entries": entries,
            "total_count": len(entries),
            "received_count": received_count,
            "sent_count": sent_count,
            "draft_count": draft_count,
        }

    except Exception as e:
        logger.error(
            "COMMUNICATIONS_API: Failed to get contact history for user %s, email %s: %s",
            user_id,
            normalized_email,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contact history. Please try again.",
        ) from e


@router.get("/analytics", response_model=CommunicationAnalyticsResponse)
async def get_communications_analytics(
    current_user: CurrentUser,
    days_back: int = Query(
        7,
        ge=1,
        le=90,
        description="Number of days to look back for analytics (default: 7)",
    ),
) -> dict[str, Any]:
    """Get communication analytics metrics for the authenticated user.

    Provides comprehensive email communication analytics including:
    - Response time analytics (avg, fastest, slowest hours)
    - Draft coverage rate (% NEEDS_REPLY emails with drafts)
    - Email volume trends (7-day: received, drafted, sent counts)
    - Classification distribution (NEEDS_REPLY/FYI/SKIP counts and percentages)
    - Response time by contact type (using monitored_entities)

    Args:
        current_user: The authenticated user.
        days_back: Number of days to look back (default: 7, max: 90).

    Returns:
        CommunicationAnalyticsResponse with all analytics metrics.
        Returns has_data=False if user has no email scan logs.

    Raises:
        HTTPException: If database query fails.
    """
    user_id = current_user.id

    logger.info(
        "COMMUNICATIONS_API: Fetching analytics for user %s, days_back=%d",
        user_id,
        days_back,
    )

    try:
        from src.services.analytics_service import AnalyticsService

        service = AnalyticsService()
        metrics = await service.get_communications_analytics(
            user_id=user_id,
            days_back=days_back,
        )

        logger.info(
            "COMMUNICATIONS_API: Analytics calculated for user %s (has_data=%s)",
            user_id,
            metrics.get("has_data", False),
        )

        return CommunicationAnalyticsResponse(**metrics)

    except Exception as e:
        logger.error(
            "COMMUNICATIONS_API: Failed to get analytics for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve communication analytics. Please try again.",
        ) from e


@router.get(
    "/upcoming-meetings",
    response_model=list[UpcomingMeetingWithContext],
)
async def get_upcoming_meetings_with_context(
    current_user: CurrentUser,
    hours_ahead: int = Query(
        24,
        ge=1,
        le=168,
        description="How many hours ahead to look for meetings (default: 24, max: 168)",
    ),
) -> list[dict[str, Any]]:
    """Get upcoming meetings enriched with email context.

    Queries calendar_events for meetings in the next N hours, then enriches
    each meeting with email communication context from email_scan_log and
    email_drafts.  Only returns meetings where ARIA can add value — i.e.,
    where there is email history with at least one attendee.

    Returns an empty list (not an error) if:
    - No calendar integration is connected
    - No upcoming meetings exist
    - No meetings have email context

    Args:
        current_user: The authenticated user.
        hours_ahead: How many hours ahead to look (default: 24).

    Returns:
        List of UpcomingMeetingWithContext, possibly empty.
    """
    user_id = current_user.id

    logger.info(
        "COMMUNICATIONS_API: Fetching upcoming meetings with context for user %s, hours_ahead=%d",
        user_id,
        hours_ahead,
    )

    try:
        from src.services.pre_meeting_context import PreMeetingContextService

        service = PreMeetingContextService()
        meetings = await service.get_upcoming_meetings_with_context(
            user_id=user_id,
            hours_ahead=hours_ahead,
            user_email=getattr(current_user, "email", None),
        )

        logger.info(
            "COMMUNICATIONS_API: Found %d upcoming meetings with email context for user %s",
            len(meetings),
            user_id,
        )

        return meetings

    except Exception as e:
        # Graceful degradation — never block the page for calendar failures
        logger.warning(
            "COMMUNICATIONS_API: Failed to get upcoming meetings for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        return []


def _generate_snippet(body: str | None, max_length: int = 150) -> str | None:
    """Generate a clean snippet from email body.

    Args:
        body: The email body text (may contain HTML).
        max_length: Maximum snippet length.

    Returns:
        Clean text snippet or None if body is empty.
    """
    if not body:
        return None

    # Strip HTML tags
    import re

    text = re.sub(r"<[^>]*>", " ", body)

    # Decode common HTML entities
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return None

    # Truncate
    if len(text) > max_length:
        return text[:max_length].strip() + "..."

    return text
