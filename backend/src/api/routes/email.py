"""Email API routes for inbox scanning, draft generation, and urgency detection.

Provides endpoints for:
- Manual inbox scan trigger with full draft pipeline
- Real-time urgent email notifications
- Email bootstrap trigger for memory/digital twin population
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.autonomous_draft_engine import get_autonomous_draft_engine

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
    drafts_generated: int = Field(0, description="Draft replies generated")
    drafts_failed: int = Field(0, description="Draft generation failures")
    run_id: str | None = Field(None, description="Processing run ID for tracking")
    run_status: str | None = Field(None, description="Processing run final status")
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
    background_tasks: BackgroundTasks,
    since_hours: int = Query(
        24,
        ge=1,
        le=168,
        description="Hours of history to scan (1-168, default 24)",
    ),
    generate_drafts: bool = Query(
        True,
        description="Whether to generate draft replies for NEEDS_REPLY emails",
    ),
    notify: bool = Query(
        True,
        description="Whether to send real-time notifications for urgent emails",
    ),
) -> dict[str, Any]:
    """Trigger immediate inbox scan with full draft generation pipeline.

    This endpoint runs the complete email pipeline:
    1. Scan inbox and categorize emails (NEEDS_REPLY / FYI / SKIP)
    2. For each NEEDS_REPLY email: gather context, generate draft, save
    3. Track the processing run with counters and timing
    4. Send real-time notifications for urgent emails
    5. Trigger bootstrap enrichment for memory/digital twin (background)

    Args:
        current_user: The authenticated user.
        background_tasks: FastAPI background tasks for bootstrap.
        since_hours: How many hours of history to scan (1-168).
        generate_drafts: Whether to generate draft replies.
        notify: Whether to send real-time notifications.

    Returns:
        ScanInboxResponse with scan results, draft stats, and urgent email details.

    Raises:
        HTTPException: If scan fails due to integration or API errors.
    """
    user_id = current_user.id
    scanned_at = datetime.now(UTC).isoformat()

    logger.info(
        "[EMAIL_PIPELINE] Stage: scan_requested | user_id=%s | since_hours=%d | generate_drafts=%s",
        user_id,
        since_hours,
        generate_drafts,
    )

    try:
        # Run the FULL draft engine pipeline (scan + context + draft + save)
        engine = get_autonomous_draft_engine()
        run_result = await engine.process_inbox(user_id, since_hours=since_hours)

        logger.info(
            "[EMAIL_PIPELINE] Stage: pipeline_complete | user_id=%s | run_id=%s | "
            "emails_scanned=%d | needs_reply=%d | drafts_generated=%d | drafts_failed=%d | status=%s",
            user_id,
            run_result.run_id,
            run_result.emails_scanned,
            run_result.emails_needs_reply,
            run_result.drafts_generated,
            run_result.drafts_failed,
            run_result.status,
        )

        # Process urgent email notifications separately
        urgent_emails: list[dict[str, Any]] = []
        notifications_sent = 0

        # Build urgent email info from drafts that were for urgent emails
        urgent_drafts = [d for d in run_result.drafts if d.success]
        for draft in urgent_drafts:
            urgent_emails.append({
                "email_id": draft.original_email_id,
                "sender": draft.recipient_name or draft.recipient_email,
                "sender_email": draft.recipient_email,
                "subject": draft.subject,
                "urgency": "NORMAL",
                "topic_summary": f"Draft reply generated (confidence: {draft.confidence_level:.0%})",
                "reason": draft.aria_notes[:200] if draft.aria_notes else "Draft generated",
                "draft_id": draft.draft_id,
            })

        # Send real-time notifications for urgent emails if requested
        if notify and urgent_drafts:
            try:
                from src.core.ws import ws_manager

                if ws_manager.is_connected(user_id):
                    for draft in urgent_drafts:
                        try:
                            await ws_manager.send_aria_message(
                                user_id=user_id,
                                message=f"Drafted reply to {draft.recipient_name or draft.recipient_email}: {draft.subject}",
                                rich_content=[{
                                    "type": "email_draft",
                                    "draft_id": draft.draft_id,
                                    "recipient": draft.recipient_email,
                                    "subject": draft.subject,
                                    "confidence": draft.confidence_level,
                                }],
                                suggestions=["Review draft", "Edit draft", "Send now"],
                            )
                            notifications_sent += 1
                        except Exception as e:
                            logger.warning(
                                "[EMAIL_PIPELINE] Stage: notification_failed | draft_id=%s | error=%s",
                                draft.draft_id,
                                e,
                            )
            except Exception as e:
                logger.error(
                    "[EMAIL_PIPELINE] Stage: notifications_failed | user_id=%s | error=%s",
                    user_id,
                    e,
                    exc_info=True,
                )

        # Trigger bootstrap enrichment in the background if drafts were generated
        if run_result.emails_scanned > 0:
            background_tasks.add_task(_run_email_bootstrap, user_id)

        return {
            "total_emails": run_result.emails_scanned,
            "needs_reply": run_result.emails_needs_reply,
            "urgent": len([d for d in run_result.drafts if d.success]),
            "drafts_generated": run_result.drafts_generated,
            "drafts_failed": run_result.drafts_failed,
            "run_id": run_result.run_id,
            "run_status": run_result.status,
            "urgent_emails": urgent_emails,
            "scanned_at": scanned_at,
            "notifications_sent": notifications_sent,
        }

    except Exception as e:
        logger.error(
            "[EMAIL_PIPELINE] Stage: pipeline_failed | user_id=%s | error=%s",
            user_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to scan inbox. Please try again.",
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
            detail="Failed to retrieve scan decisions. Please try again.",
        ) from e


# ---------------------------------------------------------------------------
# Bootstrap Trigger
# ---------------------------------------------------------------------------


async def _run_email_bootstrap(user_id: str) -> None:
    """Run email bootstrap enrichment in the background.

    Populates memory_semantic and digital_twin_profiles from email data.
    Safe to call multiple times — bootstrap is idempotent.
    """
    try:
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        logger.info(
            "[EMAIL_PIPELINE] Stage: bootstrap_started | user_id=%s",
            user_id,
        )
        ingestion = PriorityEmailIngestion()
        result = await ingestion.run_bootstrap(user_id)
        logger.info(
            "[EMAIL_PIPELINE] Stage: bootstrap_complete | user_id=%s | "
            "contacts=%d | threads=%d | writing_samples=%d",
            user_id,
            result.contacts_discovered,
            result.active_threads,
            result.writing_samples_extracted,
        )
    except Exception as e:
        logger.error(
            "[EMAIL_PIPELINE] Stage: bootstrap_failed | user_id=%s | error=%s",
            user_id,
            e,
            exc_info=True,
        )


@router.post("/bootstrap", response_model=dict[str, Any])
async def trigger_email_bootstrap(current_user: CurrentUser) -> dict[str, Any]:
    """Trigger email bootstrap enrichment independently.

    Processes the last 60 days of sent emails to populate:
    - memory_semantic with contacts and deal threads
    - digital_twin writing style fingerprint
    - recipient_writing_profiles per-contact styles
    - Communication patterns

    This runs synchronously and returns results.

    Args:
        current_user: The authenticated user.

    Returns:
        Dict with bootstrap results.

    Raises:
        HTTPException: If bootstrap fails.
    """
    user_id = current_user.id

    logger.info(
        "[EMAIL_PIPELINE] Stage: bootstrap_manual_trigger | user_id=%s",
        user_id,
    )

    try:
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        ingestion = PriorityEmailIngestion()
        result = await ingestion.run_bootstrap(user_id)

        logger.info(
            "[EMAIL_PIPELINE] Stage: bootstrap_manual_complete | user_id=%s | "
            "contacts=%d | threads=%d | writing_samples=%d",
            user_id,
            result.contacts_discovered,
            result.active_threads,
            result.writing_samples_extracted,
        )

        return {
            "success": True,
            "emails_processed": result.emails_processed,
            "contacts_discovered": result.contacts_discovered,
            "active_threads": result.active_threads,
            "commitments_detected": result.commitments_detected,
            "writing_samples_extracted": result.writing_samples_extracted,
        }

    except Exception as e:
        logger.error(
            "[EMAIL_PIPELINE] Stage: bootstrap_manual_failed | user_id=%s | error=%s",
            user_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run email bootstrap. Please try again.",
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
