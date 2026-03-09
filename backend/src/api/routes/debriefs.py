"""Meeting debrief API routes for ARIA.

This module provides endpoints for:
- Initiating debriefs (Phase 1: create pending debrief)
- Submitting debrief notes (Phase 2+3: AI extraction + downstream integration)
- Querying debriefs with pagination and filtering
- Finding meetings that need debriefing
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.debrief_service import DebriefService

logger = logging.getLogger(__name__)


# =============================================================================
# Email Backfill
# =============================================================================


async def run_email_backfill(user_id: str, lookback_days: int = 90) -> dict[str, Any]:
    """Paginate OUTLOOK_LIST_MESSAGES to backfill historical emails.

    This gives ARIA 90 days of email context for ALL capabilities:
    debriefs, briefings, email drafting, intelligence, pipeline.

    Uses $skip pagination through Inbox and SentItems folders, storing
    results in email_scan_log with deduplication by email_id.

    Args:
        user_id: The user's UUID string.
        lookback_days: How many days of history to fetch (default 90).

    Returns:
        Status dict with count of emails stored.
    """
    from src.db.supabase import SupabaseClient
    from src.integrations.oauth import get_oauth_client

    logger.info("[BACKFILL] Starting %d-day email backfill for user %s", lookback_days, user_id)

    oauth = get_oauth_client()
    db = SupabaseClient.get_client()

    # Get user's active email connection
    integrations = (
        db.table("user_integrations")
        .select("composio_connection_id, integration_type")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )

    conn_id = None
    provider = None
    for i in integrations.data or []:
        if i.get("integration_type") in ("outlook", "microsoft"):
            conn_id = i.get("composio_connection_id")
            provider = "outlook"
            break
        elif i.get("integration_type") == "gmail":
            conn_id = i.get("composio_connection_id")
            provider = "gmail"
            break

    if not conn_id:
        logger.warning("[BACKFILL] No active email connection for user %s", user_id)
        return {"status": "no_connection", "emails_stored": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    cutoff_iso = cutoff.isoformat()
    total_stored = 0

    if provider == "outlook":
        # Backfill both Inbox and SentItems
        for folder in ("Inbox", "SentItems"):
            skip = 0
            page_size = 50
            max_pages = 60  # 60 pages x 50 = 3000 emails per folder
            folder_stored = 0
            reached_cutoff = False

            for page in range(max_pages):
                if reached_cutoff:
                    break

                try:
                    call_params = {
                        "folder": folder,
                        "top": page_size,
                        "$skip": skip,
                    }
                    logger.info(
                        "[BACKFILL] %s page %d: calling OUTLOOK_LIST_MESSAGES with params=%s",
                        folder,
                        page,
                        call_params,
                    )

                    resp = await asyncio.wait_for(
                        oauth.execute_action(
                            connection_id=conn_id,
                            action="OUTLOOK_LIST_MESSAGES",
                            params=call_params,
                            user_id=user_id,
                            dangerously_skip_version_check=True,
                        ),
                        timeout=60.0,
                    )

                    if not resp.get("successful") or not resp.get("data"):
                        logger.info("[BACKFILL] %s page %d: no data, stopping", folder, page)
                        break

                    data = resp["data"]
                    if isinstance(data, dict) and "response_data" in data:
                        data = data["response_data"]
                    messages = data if isinstance(data, list) else data.get("value", [])

                    if not messages:
                        logger.info("[BACKFILL] %s page %d: empty, stopping", folder, page)
                        break

                    logger.info(
                        "[BACKFILL] %s page %d: got %d messages (skip=%d)",
                        folder,
                        page,
                        len(messages),
                        skip,
                    )

                    for msg in messages:
                        received = msg.get("receivedDateTime", "") or msg.get("sentDateTime", "")
                        if received and received < cutoff_iso:
                            reached_cutoff = True
                            break

                        from_addr = msg.get("from", {}).get("emailAddress", {})
                        sender_email = (from_addr.get("address", "") or "").lower()
                        sender_name = from_addr.get("name", "") or ""
                        subject = msg.get("subject", "")
                        snippet = (msg.get("bodyPreview", "") or "")[:500]
                        email_id = msg.get("internetMessageId") or msg.get("id", "")
                        thread_id = msg.get("conversationId") or None

                        if not email_id or not sender_email:
                            continue

                        # Deduplicate: check if already scanned with a snippet
                        try:
                            existing = (
                                db.table("email_scan_log")
                                .select("id, snippet")
                                .eq("user_id", user_id)
                                .eq("email_id", email_id)
                                .limit(1)
                                .execute()
                            )

                            if existing.data and existing.data[0].get("snippet"):
                                # Already fully scanned — skip
                                continue

                            if existing.data:
                                # Existing entry with NULL snippet — update it
                                db.table("email_scan_log").update(
                                    {
                                        "snippet": snippet,
                                        "category": "FYI",
                                        "urgency": "LOW",
                                    }
                                ).eq("id", existing.data[0]["id"]).execute()
                            else:
                                # New entry — insert
                                db.table("email_scan_log").insert(
                                    {
                                        "id": str(uuid.uuid4()),
                                        "user_id": user_id,
                                        "email_id": email_id,
                                        "thread_id": thread_id,
                                        "sender_email": sender_email,
                                        "sender_name": sender_name,
                                        "subject": subject[:500],
                                        "snippet": snippet,
                                        "category": "FYI",
                                        "urgency": "LOW",
                                        "needs_draft": False,
                                        "reason": "backfill",
                                        "scanned_at": datetime.now(timezone.utc).isoformat(),
                                    }
                                ).execute()

                            folder_stored += 1
                        except Exception:
                            pass

                    if len(messages) < page_size:
                        logger.info(
                            "[BACKFILL] %s: fewer than %d results, no more pages",
                            folder,
                            page_size,
                        )
                        break

                    skip += len(messages)

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

                except asyncio.TimeoutError:
                    logger.warning("[BACKFILL] %s page %d timed out", folder, page)
                    if page == 0 and skip == 0:
                        # First page timed out — retry with minimal params (no $skip)
                        logger.info("[BACKFILL] %s: retrying page 0 with minimal params", folder)
                        try:
                            resp = await asyncio.wait_for(
                                oauth.execute_action(
                                    connection_id=conn_id,
                                    action="OUTLOOK_LIST_MESSAGES",
                                    params={"folder": folder, "top": 50},
                                    user_id=user_id,
                                    dangerously_skip_version_check=True,
                                ),
                                timeout=60.0,
                            )
                            if resp.get("successful") and resp.get("data"):
                                data = resp["data"]
                                if isinstance(data, dict) and "response_data" in data:
                                    data = data["response_data"]
                                fallback_msgs = (
                                    data if isinstance(data, list) else data.get("value", [])
                                )
                                logger.info(
                                    "[BACKFILL] %s fallback: got %d messages",
                                    folder,
                                    len(fallback_msgs),
                                )
                                for msg in fallback_msgs:
                                    received = (
                                        msg.get("receivedDateTime", "")
                                        or msg.get("sentDateTime", "")
                                    )
                                    if received and received < cutoff_iso:
                                        break

                                    from_addr = msg.get("from", {}).get("emailAddress", {})
                                    s_email = (from_addr.get("address", "") or "").lower()
                                    s_name = from_addr.get("name", "") or ""
                                    subj = msg.get("subject", "")
                                    snip = (msg.get("bodyPreview", "") or "")[:500]
                                    eid = msg.get("internetMessageId") or msg.get("id", "")
                                    tid = msg.get("conversationId") or None

                                    if not eid or not s_email:
                                        continue
                                    try:
                                        existing = (
                                            db.table("email_scan_log")
                                            .select("id, snippet")
                                            .eq("user_id", user_id)
                                            .eq("email_id", eid)
                                            .limit(1)
                                            .execute()
                                        )
                                        if existing.data and existing.data[0].get("snippet"):
                                            continue
                                        if existing.data:
                                            db.table("email_scan_log").update(
                                                {
                                                    "snippet": snip,
                                                    "category": "FYI",
                                                    "urgency": "LOW",
                                                }
                                            ).eq("id", existing.data[0]["id"]).execute()
                                        else:
                                            db.table("email_scan_log").insert(
                                                {
                                                    "id": str(uuid.uuid4()),
                                                    "user_id": user_id,
                                                    "email_id": eid,
                                                    "thread_id": tid,
                                                    "sender_email": s_email,
                                                    "sender_name": s_name,
                                                    "subject": subj[:500],
                                                    "snippet": snip,
                                                    "category": "FYI",
                                                    "urgency": "LOW",
                                                    "needs_draft": False,
                                                    "reason": "backfill",
                                                    "scanned_at": datetime.now(
                                                        timezone.utc
                                                    ).isoformat(),
                                                }
                                            ).execute()
                                        folder_stored += 1
                                    except Exception:
                                        pass
                                logger.info(
                                    "[BACKFILL] %s fallback stored %d emails",
                                    folder,
                                    folder_stored,
                                )
                        except Exception as fallback_err:
                            logger.warning(
                                "[BACKFILL] %s fallback also failed: %s",
                                folder,
                                str(fallback_err)[:200],
                            )
                    break
                except Exception as e:
                    logger.warning("[BACKFILL] %s page %d error: %s", folder, page, str(e)[:200])
                    break

            logger.info(
                "[BACKFILL] %s complete: %d emails stored across %d pages",
                folder,
                folder_stored,
                page + 1,
            )
            total_stored += folder_stored

    elif provider == "gmail":
        # Gmail backfill using GMAIL_FETCH_EMAILS with date query
        try:
            since_epoch = int(cutoff.timestamp())
            resp = await asyncio.wait_for(
                oauth.execute_action(
                    connection_id=conn_id,
                    action="GMAIL_FETCH_EMAILS",
                    params={
                        "label": "INBOX",
                        "max_results": 500,
                        "query": f"after:{since_epoch}",
                    },
                    user_id=user_id,
                    dangerously_skip_version_check=True,
                ),
                timeout=30.0,
            )
            if resp.get("successful") and resp.get("data"):
                emails = resp["data"]
                if isinstance(emails, dict):
                    emails = emails.get("messages", []) or emails.get("value", [])
                for msg in emails or []:
                    # TODO: Gmail normalization — store emails the same way
                    pass
        except Exception as e:
            logger.warning("[BACKFILL] Gmail backfill error: %s", str(e)[:200])

    # TODO: Auto-trigger this backfill during onboarding when user first
    # connects their email integration. For now, triggered manually via
    # the /debriefs/backfill-email-scan endpoint.

    logger.info("[BACKFILL] Complete: %d total emails stored for user %s", total_stored, user_id)
    return {"status": "complete", "emails_stored": total_stored}

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

    user_email = getattr(current_user, "email", None)
    pending_meetings = await service.check_pending_debriefs(current_user.id, user_email=user_email)

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


@router.post("/backfill-email-scan")
async def backfill_email_scan(
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    lookback_days: int = Query(90, ge=1, le=365, description="Days to look back"),
) -> dict[str, Any]:
    """Trigger a paginated email backfill to give ARIA historical context.

    Paginates through Inbox and SentItems using OUTLOOK_LIST_MESSAGES with
    $skip pagination to capture up to 90 days of email history. This gives
    ARIA context for ALL capabilities: debriefs, briefings, email drafting,
    intelligence, and pipeline.

    Deduplicates by email_id — safe to run multiple times.

    Args:
        current_user: The authenticated user.
        background_tasks: FastAPI background task queue.
        lookback_days: How many days back to scan (default 90).

    Returns:
        Status confirmation with lookback parameters.
    """
    background_tasks.add_task(run_email_backfill, str(current_user.id), lookback_days)

    logger.info(
        "Email backfill triggered for user %s (lookback=%d days)",
        current_user.id,
        lookback_days,
    )

    return {
        "status": "backfill_started",
        "lookback_days": lookback_days,
    }


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
