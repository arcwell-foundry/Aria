"""Email API routes for inbox scanning and urgency detection.

Provides endpoints for:
- Manual inbox scan trigger
- Real-time urgent email notifications
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.email_analyzer import EmailAnalyzer
from src.services.realtime_email_notifier import get_realtime_email_notifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["email"])


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class UrgentEmailInfo(BaseModel):
    """Information about an urgent email."""

    email_id: str = Field(..., description="Unique email identifier")
    sender: str = Field(..., description="Sender display name")
    sender_email: str = Field(..., description="Sender email address")
    subject: str = Field(..., description="Email subject line")
    urgency: str = Field(..., description="Urgency level (URGENT, NORMAL, LOW)")
    topic_summary: str = Field(..., description="Brief summary of email topic")
    reason: str = Field(..., description="Reason for urgency classification")
    draft_id: str | None = Field(None, description="Draft reply ID if generated")


class ScanInboxResponse(BaseModel):
    """Response from inbox scan endpoint."""

    total_emails: int = Field(..., description="Total emails scanned")
    needs_reply: int = Field(..., description="Emails needing a reply")
    urgent: int = Field(..., description="Urgent emails found")
    urgent_emails: list[UrgentEmailInfo] = Field(
        default_factory=list,
        description="Details of urgent emails",
    )
    scanned_at: str = Field(..., description="Timestamp of scan")
    notifications_sent: int = Field(0, description="Number of real-time notifications sent")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/scan-now", response_model=ScanInboxResponse)
async def scan_inbox_now(
    current_user: CurrentUser,
    since_hours: int = Query(
        24,
        ge=1,
        le=168,
        description="Hours of history to scan (1-168, default 24)",
    ),
    generate_drafts: bool = Query(
        True,
        description="Whether to generate draft replies for urgent emails",
    ),
    notify: bool = Query(
        True,
        description="Whether to send real-time notifications for urgent emails",
    ),
) -> dict[str, Any]:
    """Trigger immediate inbox scan and return results.

    This endpoint is used when:
    - User explicitly requests "ARIA, check my email"
    - User clicks a refresh button in the UI
    - Manual periodic check is needed

    For each urgent email found:
    1. Generate draft reply (if generate_drafts=True)
    2. Save draft to email client (Gmail/Outlook)
    3. Send real-time WebSocket notification (if notify=True and user active)

    Args:
        current_user: The authenticated user.
        since_hours: How many hours of history to scan (1-168).
        generate_drafts: Whether to generate draft replies.
        notify: Whether to send real-time notifications.

    Returns:
        ScanInboxResponse with scan results and urgent email details.

    Raises:
        HTTPException: If scan fails due to integration or API errors.
    """
    user_id = current_user.id
    scanned_at = datetime.now(UTC).isoformat()

    logger.info(
        "EMAIL_API: Manual inbox scan requested by user %s (since %d hours)",
        user_id,
        since_hours,
    )

    try:
        # Scan inbox via EmailAnalyzer
        analyzer = EmailAnalyzer()
        result = await analyzer.scan_inbox(user_id, since_hours=since_hours)

        logger.info(
            "EMAIL_API: Scan complete for user %s - %d total, %d needs_reply, %d urgent",
            user_id,
            result.total_emails,
            len(result.needs_reply),
            len(result.urgent),
        )

        # Build response with urgent email details
        urgent_emails: list[dict[str, Any]] = []
        notifications_sent = 0

        if result.urgent:
            # Process urgent emails with notifications and drafts
            if notify:
                notifier = get_realtime_email_notifier()
                notifications = await notifier.process_and_notify(
                    user_id=user_id,
                    urgent_emails=result.urgent,
                    generate_drafts=generate_drafts,
                )
                notifications_sent = len(notifications)

                # Build urgent email info from notifications
                for notification in notifications:
                    urgent_emails.append({
                        "email_id": notification.email_id,
                        "sender": notification.sender_name,
                        "sender_email": notification.sender_email,
                        "subject": notification.subject,
                        "urgency": "URGENT",
                        "topic_summary": notification.topic_summary,
                        "reason": notification.urgency_reason,
                        "draft_id": notification.draft_id,
                    })
            else:
                # Just build info from email categories
                for email in result.urgent:
                    urgent_emails.append({
                        "email_id": email.email_id,
                        "sender": email.sender_name,
                        "sender_email": email.sender_email,
                        "subject": email.subject,
                        "urgency": email.urgency,
                        "topic_summary": email.topic_summary,
                        "reason": email.reason,
                        "draft_id": None,
                    })

        return {
            "total_emails": result.total_emails,
            "needs_reply": len(result.needs_reply),
            "urgent": len(result.urgent),
            "urgent_emails": urgent_emails,
            "scanned_at": scanned_at,
            "notifications_sent": notifications_sent,
        }

    except Exception as e:
        logger.error(
            "EMAIL_API: Inbox scan failed for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan inbox: {e}",
        ) from e


@router.get("/scan-status", response_model=dict[str, Any])
async def get_scan_status(current_user: CurrentUser) -> dict[str, Any]:
    """Get the last inbox scan status for the current user.

    Returns information about the most recent email processing run,
    including scan timestamp and statistics.

    Args:
        current_user: The authenticated user.

    Returns:
        Dict with last scan status information.
    """
    from src.db.supabase import SupabaseClient

    user_id = current_user.id

    try:
        db = SupabaseClient.get_client()

        result = (
            db.table("email_processing_runs")
            .select("*")
            .eq("user_id", user_id)
            .order("started_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )

        if not result.data:
            return {
                "has_previous_scan": False,
                "message": "No previous inbox scan found",
            }

        run = result.data
        return {
            "has_previous_scan": True,
            "run_id": run.get("id"),
            "status": run.get("status"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
            "emails_scanned": run.get("emails_scanned", 0),
            "drafts_generated": run.get("drafts_generated", 0),
        }

    except Exception as e:
        logger.warning(
            "EMAIL_API: Failed to get scan status for user %s: %s",
            user_id,
            e,
        )
        return {
            "has_previous_scan": False,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Scan Decisions Transparency Endpoint
# ---------------------------------------------------------------------------


class ScanDecisionInfo(BaseModel):
    """Information about a single scan decision."""

    email_id: str = Field(..., description="Unique email identifier")
    thread_id: str | None = Field(None, description="Email thread ID")
    sender_email: str = Field(..., description="Sender email address")
    sender_name: str | None = Field(None, description="Sender display name")
    subject: str | None = Field(None, description="Email subject line")
    category: str = Field(..., description="Category: NEEDS_REPLY, FYI, or SKIP")
    urgency: str = Field(..., description="Urgency: URGENT, NORMAL, or LOW")
    needs_draft: bool = Field(..., description="Whether a draft was needed")
    reason: str = Field(..., description="Reason for categorization")
    scanned_at: str = Field(..., description="Timestamp of scan")
    confidence: float | None = Field(None, description="Confidence score (0.0-1.0)")


class ScanDecisionsResponse(BaseModel):
    """Response from scan decisions endpoint."""

    decisions: list[ScanDecisionInfo] = Field(
        default_factory=list,
        description="List of scan decisions",
    )
    total_count: int = Field(..., description="Total number of decisions returned")
    filters_applied: dict[str, Any] = Field(
        default_factory=dict,
        description="Filters applied to the query",
    )
    scanned_after: str | None = Field(None, description="ISO timestamp of filter start")


@router.get("/decisions", response_model=ScanDecisionsResponse)
async def get_scan_decisions(
    current_user: CurrentUser,
    since_hours: int = Query(
        24,
        ge=1,
        le=168,
        description="Hours of history to include (1-168, default 24)",
    ),
    category: str | None = Query(
        None,
        description="Filter by category: NEEDS_REPLY, FYI, or SKIP",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Maximum number of decisions to return (1-200)",
    ),
) -> dict[str, Any]:
    """Get ARIA's email categorization decisions for transparency.

    This endpoint provides visibility into why ARIA categorized emails
    the way it did, showing the reasoning behind NEEDS_REPLY, FYI, and
    SKIP classifications.

    Args:
        current_user: The authenticated user.
        since_hours: How many hours of history to include.
        category: Optional filter by category type.
        limit: Maximum number of results.

    Returns:
        ScanDecisionsResponse with list of decisions and metadata.

    Raises:
        HTTPException: If query fails due to database errors.
    """
    from datetime import timedelta

    from src.db.supabase import SupabaseClient

    user_id = current_user.id
    since = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

    logger.info(
        "EMAIL_API: Fetching scan decisions for user %s (since %d hours, category=%s)",
        user_id,
        since_hours,
        category,
    )

    try:
        db = SupabaseClient.get_client()

        query = (
            db.table("email_scan_log")
            .select("*")
            .eq("user_id", user_id)
            .gte("scanned_at", since)
            .order("scanned_at", desc=True)
            .limit(limit)
        )

        if category:
            query = query.eq("category", category.upper())

        result = query.execute()

        decisions = [
            ScanDecisionInfo(
                email_id=row.get("email_id", ""),
                thread_id=row.get("thread_id"),
                sender_email=row.get("sender_email", ""),
                sender_name=row.get("sender_name"),
                subject=row.get("subject"),
                category=row.get("category", "UNKNOWN"),
                urgency=row.get("urgency", "NORMAL"),
                needs_draft=row.get("needs_draft", False),
                reason=row.get("reason", ""),
                scanned_at=row.get("scanned_at", ""),
                confidence=row.get("confidence"),
            )
            for row in (result.data or [])
        ]

        logger.info(
            "EMAIL_API: Returned %d scan decisions for user %s",
            len(decisions),
            user_id,
        )

        return {
            "decisions": decisions,
            "total_count": len(decisions),
            "filters_applied": {"since_hours": since_hours, "category": category},
            "scanned_after": since,
        }

    except Exception as e:
        logger.error(
            "EMAIL_API: Failed to get scan decisions for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve scan decisions: {e}",
        ) from e


# ---------------------------------------------------------------------------
# Router Registration Helper
# ---------------------------------------------------------------------------


def register_email_routes(app: Any) -> None:
    """Register email routes with the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """
    app.include_router(router)
