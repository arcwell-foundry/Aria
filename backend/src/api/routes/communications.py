"""Communications page API routes.

User-facing endpoints for the Communications page, including:
- Contact history: Unified timeline of all communications with a specific contact
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient

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


class ContactHistoryResponse(BaseModel):
    """Response from contact history endpoint."""

    contact_email: str = Field(..., description="The contact's email address")
    contact_name: str | None = Field(None, description="The contact's display name (if known)")
    entries: list[ContactHistoryEntry] = Field(
        default_factory=list,
        description="Chronologically sorted timeline entries",
    )
    total_count: int = Field(..., description="Total number of entries")
    received_count: int = Field(0, description="Number of emails received from contact")
    sent_count: int = Field(0, description="Number of emails sent to contact")
    draft_count: int = Field(0, description="Number of pending drafts to contact")


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
