"""Drafts API routes for email draft management."""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import EmailDraftError, EmailSendError, NotFoundError
from src.db.supabase import SupabaseClient
from src.models.email_draft import (
    EmailDraftCreate,
    EmailDraftListResponse,
    EmailDraftResponse,
    EmailDraftUpdate,
    EmailRegenerateRequest,
    EmailSendResponse,
)
from src.services.action_gatekeeper import get_action_gatekeeper
from src.services.activity_service import ActivityService
from src.services.draft_service import get_draft_service
from src.services.email_client_writer import DraftSaveError, get_email_client_writer
from src.utils.company_aliases import normalize_company_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str = Field(..., min_length=1, max_length=500)


class BatchActionRequest(BaseModel):
    """Request body for batch draft actions."""

    draft_ids: list[str] = Field(..., min_length=1, max_length=50, description="List of draft IDs to act on")
    action: str = Field(..., pattern="^(approve|dismiss)$", description="Action to perform: 'approve' or 'dismiss'")


class BatchActionResultItem(BaseModel):
    """Result for a single draft in a batch action."""

    draft_id: str
    success: bool
    error: str | None = None


class BatchActionResponse(BaseModel):
    """Response for batch draft actions."""

    results: list[BatchActionResultItem]
    total: int
    succeeded: int
    failed: int


@router.post("/email", response_model=EmailDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_email_draft(
    current_user: CurrentUser, request: EmailDraftCreate
) -> dict[str, Any]:
    """Generate a new email draft.

    Args:
        current_user: The authenticated user.
        request: Email draft creation parameters.

    Returns:
        The created email draft.

    Raises:
        HTTPException: If draft creation fails.
    """
    try:
        service = get_draft_service()
        draft = await service.create_draft(
            user_id=current_user.id,
            recipient_email=request.recipient_email,
            purpose=request.purpose,
            tone=request.tone,
            recipient_name=request.recipient_name,
            subject_hint=request.subject_hint,
            context=request.context,
            lead_memory_id=request.lead_memory_id,
        )
        logger.info(
            "Email draft created via API",
            extra={"user_id": current_user.id, "draft_id": draft["id"]},
        )
        return draft
    except EmailDraftError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message
        ) from e
    except Exception as e:
        logger.exception("Unexpected error creating draft")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate email draft",
        ) from e


@router.get("", response_model=list[EmailDraftListResponse])
async def list_drafts(
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status (draft, sent, failed)"),
    include_dismissed: bool = Query(False, description="Include dismissed drafts in results"),
) -> list[dict[str, Any]]:
    """List user's email drafts.

    By default, dismissed drafts are excluded from results since they are not actionable.
    Set include_dismissed=true to include them.

    Args:
        current_user: The authenticated user.
        limit: Maximum number of drafts to return (1-100).
        status: Optional status filter.
        include_dismissed: If True, include dismissed drafts (default: False).

    Returns:
        List of email drafts.
    """
    service = get_draft_service()
    drafts = await service.list_drafts(current_user.id, limit, status, include_dismissed)
    logger.info("Drafts listed", extra={"user_id": current_user.id, "count": len(drafts)})
    return drafts


@router.get("/{draft_id}", response_model=EmailDraftResponse)
async def get_draft(current_user: CurrentUser, draft_id: str) -> dict[str, Any]:
    """Get a specific email draft.

    For reply drafts, enriches the response with the original incoming email
    from email_scan_log so users can see what they're replying to.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to retrieve.

    Returns:
        The email draft, optionally with original_email field for replies.

    Raises:
        HTTPException: If draft not found.
    """
    service = get_draft_service()
    draft = await service.get_draft(current_user.id, draft_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Draft {draft_id} not found"
        )

    # For reply drafts, enrich with the original incoming email
    if draft.get("purpose") == "reply":
        original_email = await _get_original_email_for_draft(draft, current_user.id)
        if original_email:
            draft["original_email"] = original_email

    return draft


async def _get_original_email_for_draft(
    draft: dict[str, Any], user_id: str
) -> dict[str, Any] | None:
    """Fetch the original incoming email for a reply draft.

    Tries multiple strategies to find the original email:
    1. Look up by original_email_id in email_scan_log
    2. Look up by thread_id for the most recent incoming email
    3. Look up by in_reply_to (Message-ID header)

    Args:
        draft: The draft data dictionary.
        user_id: The user ID for security filtering.

    Returns:
        Dictionary with original email data, or None if not found.
    """
    db = SupabaseClient.get_client()

    original_email_id = draft.get("original_email_id")
    thread_id = draft.get("thread_id")
    in_reply_to = draft.get("in_reply_to")

    # Strategy 1: Direct lookup by original_email_id (most reliable)
    if original_email_id:
        result = (
            db.table("email_scan_log")
            .select("sender_email, sender_name, subject, snippet, scanned_at")
            .eq("user_id", user_id)
            .eq("email_id", original_email_id)
            .limit(1)
            .execute()
        )
        if result.data:
            logger.debug(
                "Found original email by original_email_id",
                extra={"draft_id": draft.get("id"), "email_id": original_email_id},
            )
            return _format_original_email(result.data[0])

    # Strategy 2: Find by thread_id - get the most recent incoming email
    if thread_id:
        result = (
            db.table("email_scan_log")
            .select("sender_email, sender_name, subject, snippet, scanned_at, email_id")
            .eq("user_id", user_id)
            .eq("thread_id", thread_id)
            .eq("category", "NEEDS_REPLY")  # Only emails that needed a reply
            .order("scanned_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            logger.debug(
                "Found original email by thread_id",
                extra={"draft_id": draft.get("id"), "thread_id": thread_id},
            )
            return _format_original_email(result.data[0])

    # Strategy 3: Try to match by recipient_email being the sender
    # (the draft recipient is who sent the original email)
    recipient_email = draft.get("recipient_email")
    if recipient_email:
        # Look for recent emails from this sender that needed a reply
        result = (
            db.table("email_scan_log")
            .select("sender_email, sender_name, subject, snippet, scanned_at")
            .eq("user_id", user_id)
            .eq("sender_email", recipient_email)
            .eq("category", "NEEDS_REPLY")
            .order("scanned_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            logger.debug(
                "Found original email by sender_email fallback",
                extra={"draft_id": draft.get("id"), "sender_email": recipient_email},
            )
            return _format_original_email(result.data[0])

    logger.debug(
        "No original email found for reply draft",
        extra={
            "draft_id": draft.get("id"),
            "original_email_id": original_email_id,
            "thread_id": thread_id,
        },
    )
    return None


def _format_original_email(scan_log_entry: dict[str, Any]) -> dict[str, Any]:
    """Format an email_scan_log entry for the original_email response.

    Args:
        scan_log_entry: A row from email_scan_log.

    Returns:
        Formatted dictionary with from, date, subject, snippet.
    """
    sender_name = scan_log_entry.get("sender_name")
    sender_email = scan_log_entry.get("sender_email", "")

    # Format "from" as "Name <email>" or just "email"
    if sender_name:
        from_field = f"{sender_name} <{sender_email}>"
    else:
        from_field = sender_email

    return {
        "from": from_field,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "date": scan_log_entry.get("scanned_at"),
        "subject": scan_log_entry.get("subject", ""),
        "snippet": scan_log_entry.get("snippet", ""),
    }


@router.put("/{draft_id}", response_model=EmailDraftResponse)
async def update_draft(
    current_user: CurrentUser, draft_id: str, request: EmailDraftUpdate
) -> dict[str, Any]:
    """Update an email draft.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to update.
        request: Update parameters.

    Returns:
        The updated email draft.

    Raises:
        HTTPException: If draft not found or update fails.
    """
    try:
        service = get_draft_service()
        updates = request.model_dump(exclude_unset=True)
        draft = await service.update_draft(current_user.id, draft_id, updates)
        logger.info("Draft updated", extra={"user_id": current_user.id, "draft_id": draft_id})
        return draft
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except EmailDraftError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message
        ) from e


@router.delete("/{draft_id}", response_model=MessageResponse)
async def delete_draft(current_user: CurrentUser, draft_id: str) -> dict[str, str]:
    """Delete an email draft.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to delete.

    Returns:
        Success message.

    Raises:
        HTTPException: If deletion fails.
    """
    service = get_draft_service()
    success = await service.delete_draft(current_user.id, draft_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete draft",
        )
    logger.info("Draft deleted", extra={"user_id": current_user.id, "draft_id": draft_id})
    return {"message": "Draft deleted successfully"}


@router.post("/{draft_id}/regenerate", response_model=EmailDraftResponse)
async def regenerate_draft(
    current_user: CurrentUser,
    draft_id: str,
    request: EmailRegenerateRequest | None = None,
) -> dict[str, Any]:
    """Regenerate an email draft with different parameters.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to regenerate.
        request: Optional regeneration parameters.

    Returns:
        The regenerated email draft.

    Raises:
        HTTPException: If draft not found or regeneration fails.
    """
    try:
        db = SupabaseClient.get_client()

        # Check if this is an intelligence-generated draft first
        draft_check = (
            db.table("email_drafts")
            .select("draft_type, competitive_positioning, context, body, aria_notes, insight_id, aria_reasoning")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .limit(1)
            .execute()
        )

        if draft_check.data and draft_check.data[0].get("draft_type") in (
            "competitive_displacement",
            "conference_outreach",
            "clinical_trial_outreach",
        ):
            # Route to intelligence draft regeneration
            tone = request.tone.value if request and request.tone else None
            additional_context = request.additional_context if request else None
            return await _regenerate_intelligence_draft(
                draft_check.data[0], draft_id, tone, current_user.id, db, additional_context
            )

        # Standard draft regeneration via DraftService
        service = get_draft_service()
        tone = request.tone if request else None
        additional_context = request.additional_context if request else None
        draft = await service.regenerate_draft(current_user.id, draft_id, tone, additional_context)
        logger.info(
            "Draft regenerated",
            extra={"user_id": current_user.id, "draft_id": draft_id},
        )
        return draft
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except EmailDraftError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message
        ) from e


async def _regenerate_intelligence_draft(
    draft_data: dict,
    draft_id: str,
    new_tone: str | None,
    user_id: str,
    db,
    additional_context: str | None = None,
) -> dict[str, Any]:
    """Regenerate an intelligence-generated draft with a new tone or refinement.

    Intelligence drafts don't have thread_id or original_email_id like reply drafts.
    They use competitive_positioning and signal context instead.
    """
    # Parse stored context
    competitive_positioning = draft_data.get("competitive_positioning", {})
    if isinstance(competitive_positioning, str):
        try:
            competitive_positioning = json.loads(competitive_positioning)
        except:  # noqa: E722
            competitive_positioning = {}

    context_data = draft_data.get("context", {})
    if isinstance(context_data, str):
        try:
            context_data = json.loads(context_data)
        except:  # noqa: E722
            context_data = {}

    company_name = competitive_positioning.get("competitor", "") or context_data.get("company_name", "")
    differentiation = competitive_positioning.get("differentiation", [])
    weaknesses = competitive_positioning.get("weaknesses", [])
    pricing = competitive_positioning.get("pricing", {})
    signal_context = context_data.get("signal_context", "") or draft_data.get("aria_notes", "")

    # Get digital twin
    twin = (
        db.table("digital_twin_profiles")
        .select("tone, writing_style, formality_level, vocabulary_patterns")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    writing_style = (
        twin.data[0]
        if twin.data
        else {
            "tone": "professional",
            "writing_style": "concise and direct",
            "formality_level": "business",
            "vocabulary_patterns": "simple, professional",
        }
    )

    # Get user company
    user_company = "our company"
    try:
        profile = (
            db.table("user_profiles")
            .select("company_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if profile.data and profile.data[0].get("company_id"):
            company = (
                db.table("companies")
                .select("name")
                .eq("id", profile.data[0]["company_id"])
                .limit(1)
                .execute()
            )
            if company.data:
                user_company = company.data[0]["name"]
    except:  # noqa: E722
        pass

    tone_value = new_tone or "formal"

    tone_instructions = {
        "formal": "Write in a formal, professional business tone. Structured paragraphs, no contractions.",
        "friendly": "Write in a warm, friendly but professional tone. Use contractions. More conversational, shorter sentences.",
        "casual": "Write in a warm, friendly but professional tone. Use contractions. More conversational, shorter sentences.",
        "urgent": "Write with urgency. Lead with the time-sensitive opportunity. Shorter paragraphs, direct language, imply a deadline.",
    }

    system_prompt = f"""You are writing an email for a sales professional at {user_company}.
WRITING STYLE: {writing_style.get('writing_style', 'concise and direct')}
TONE: {tone_instructions.get(tone_value, tone_instructions['formal'])}

CRITICAL RULES:
1. NEVER mention competitor problems (FDA, recalls, quality issues) directly
2. Lead with VALUE and supply continuity
3. Compliance-safe language only
4. Low-friction call to action
5. 4-6 short paragraphs max
6. Use [Contact Name] as recipient placeholder"""

    diff_text = (
        "; ".join(str(d) for d in differentiation[:3])
        if differentiation
        else "specialized solutions"
    )
    user_prompt = f"""Write a competitive displacement email targeting accounts using {company_name}.
YOUR ADVANTAGES: {diff_text}
CONTEXT: {signal_context[:200] if signal_context else ''}

Write ONLY the email body. No JSON, no markdown formatting, no subject line. Just the email text."""
    if additional_context:
        user_prompt += f"\n\nADDITIONAL REFINEMENT: {additional_context}"

    try:
        from src.core.llm import LLMClient
        from src.core.task_types import TaskType

        llm = LLMClient()
        response = await llm.generate_response(
            task=TaskType.SCRIBE_DRAFT_EMAIL,
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
        )
        new_body = str(response).strip()
        new_body = new_body.strip().strip("`").strip()
        if new_body.startswith("```") or new_body.startswith("{"):
            new_body = draft_data.get("body", "")  # fallback
    except Exception as e:
        logger.warning("LLM regeneration failed for intelligence draft: %s", e)
        new_body = draft_data.get("body", "")  # keep existing on failure

    # Map tone to DB enum
    tone_map = {
        "casual": "friendly",
        "professional": "formal",
        "formal": "formal",
        "friendly": "friendly",
        "urgent": "urgent",
    }
    db_tone = tone_map.get(tone_value, "formal")

    # Build update data - preserve aria_reasoning across tone changes
    update_data: dict[str, Any] = {
        "body": new_body,
        "tone": db_tone,
    }

    # Append tone change info to aria_notes instead of replacing
    existing_notes = draft_data.get("aria_notes", "") or ""
    tone_note = f" | Regenerated with {tone_value} tone."
    if additional_context:
        tone_note += f" Refinement: {additional_context[:100]}"

    # Only append if not already appended (idempotent)
    if "Regenerated with" not in existing_notes:
        update_data["aria_notes"] = existing_notes + tone_note
    else:
        # Replace just the regeneration suffix
        base_notes = existing_notes.split(" | Regenerated with")[0]
        update_data["aria_notes"] = base_notes + tone_note

    # Never overwrite aria_reasoning - it's about WHY the email was written, not what tone it's in

    db.table("email_drafts").update(update_data).eq("id", draft_id).execute()

    # Return updated draft
    updated = db.table("email_drafts").select("*").eq("id", draft_id).limit(1).execute()
    if updated.data:
        result = updated.data[0]
        # Parse JSONB fields for response
        for field in ["context", "competitive_positioning"]:
            if isinstance(result.get(field), str):
                try:
                    result[field] = json.loads(result[field])
                except:  # noqa: E722
                    pass
        return result
    return draft_data


@router.post("/batch-action", response_model=BatchActionResponse)
async def batch_draft_action(
    current_user: CurrentUser,
    request: BatchActionRequest,
) -> dict[str, Any]:
    """Perform a batch action on multiple drafts.

    Supports 'approve' (approve + save to email client) and 'dismiss' actions.
    Only acts on drafts with status 'pending_review' or 'draft'.
    Skips drafts that are already sent, failed, or dismissed.

    Args:
        current_user: The authenticated user.
        request: Batch action parameters with draft IDs and action type.

    Returns:
        Per-draft results with overall counts.
    """
    db = SupabaseClient.get_client()
    results: list[dict[str, Any]] = []

    for draft_id in request.draft_ids:
        try:
            # Verify draft belongs to user and is in actionable state
            result = (
                db.table("email_drafts")
                .select("id, status, user_id, recipient_name, subject, body")
                .eq("id", draft_id)
                .eq("user_id", current_user.id)
                .limit(1)
                .execute()
            )

            record = result.data[0] if result and result.data else None
            if not record:
                results.append({"draft_id": draft_id, "success": False, "error": "Draft not found"})
                continue

            draft_status = record["status"]
            if draft_status in ("sent", "failed", "dismissed", "approved", "saved_to_client"):
                results.append({
                    "draft_id": draft_id,
                    "success": False,
                    "error": f"Draft status '{draft_status}' is not actionable",
                })
                continue

            if request.action == "approve":
                # Must be pending_review for approval
                if draft_status != "pending_review":
                    results.append({
                        "draft_id": draft_id,
                        "success": False,
                        "error": f"Draft status is '{draft_status}', expected 'pending_review'",
                    })
                    continue

                # Approve: update status + save to email client
                now = datetime.now(UTC).isoformat()
                db.table("email_drafts").update({
                    "status": "approved",
                    "user_action": "approved",
                    "edit_distance": 0.0,
                    "action_detected_at": now,
                }).eq("id", draft_id).execute()

                try:
                    client_writer = get_email_client_writer()
                    await client_writer.save_draft_to_client(
                        user_id=current_user.id,
                        draft_id=draft_id,
                    )
                except Exception as save_err:
                    # Revert on client save failure
                    db.table("email_drafts").update(
                        {"status": "pending_review"}
                    ).eq("id", draft_id).execute()
                    results.append({
                        "draft_id": draft_id,
                        "success": False,
                        "error": f"Failed to save to email client: {save_err}",
                    })
                    continue

                # Log activity (non-blocking)
                try:
                    activity_service = ActivityService()
                    await activity_service.record(
                        user_id=current_user.id,
                        agent="scribe",
                        activity_type="draft_saved_to_client",
                        title="Draft saved to Outlook (batch)",
                        description=f"Reply to {record.get('recipient_name', 'Unknown')}: {record.get('subject', 'No subject')}",
                        confidence=1.0,
                        related_entity_type="email_draft",
                        related_entity_id=draft_id,
                    )
                except Exception as e:
                    logger.warning("Failed to log batch approval activity: %s", e)

                results.append({"draft_id": draft_id, "success": True, "error": None})

            elif request.action == "dismiss":
                # Dismiss: update status
                db.table("email_drafts").update({
                    "status": "dismissed",
                    "user_action": "rejected",
                    "action_detected_at": datetime.now(UTC).isoformat(),
                }).eq("id", draft_id).execute()

                # Log activity (non-blocking)
                try:
                    activity_service = ActivityService()
                    await activity_service.record(
                        user_id=current_user.id,
                        agent="scribe",
                        activity_type="draft_dismissed",
                        title=f"Draft dismissed (batch): {record.get('subject', 'No subject')}",
                        description=f"User dismissed draft to {record.get('recipient_name', 'Unknown')}",
                        confidence=1.0,
                        related_entity_type="email_draft",
                        related_entity_id=draft_id,
                    )
                except Exception as e:
                    logger.warning("Failed to log batch dismissal activity: %s", e)

                results.append({"draft_id": draft_id, "success": True, "error": None})

        except Exception as e:
            logger.exception("Batch action failed for draft %s", draft_id)
            results.append({"draft_id": draft_id, "success": False, "error": str(e)})

    succeeded = sum(1 for r in results if r["success"])
    failed = len(results) - succeeded

    logger.info(
        "Batch draft action completed",
        extra={
            "user_id": current_user.id,
            "action": request.action,
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
        },
    )

    return {
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
    }


@router.post("/{draft_id}/send", response_model=EmailSendResponse)
async def send_draft(current_user: CurrentUser, draft_id: str) -> dict[str, Any]:
    """Send an email draft via user's connected email service.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to send.

    Returns:
        Send result with updated status.

    Raises:
        HTTPException: If draft not found or send fails.
    """
    try:
        service = get_draft_service()
        result = await service.send_draft(current_user.id, draft_id)
        logger.info("Draft sent", extra={"user_id": current_user.id, "draft_id": draft_id})
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except EmailSendError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e


class SaveToClientResponse(BaseModel):
    """Response model for saving draft to email client."""

    success: bool = Field(..., description="Whether the save was successful")
    saved_at: str = Field(..., description="Timestamp when saved")
    client_draft_id: str | None = Field(None, description="ID in Gmail/Outlook")
    provider: str | None = Field(None, description="Email client (gmail or outlook)")
    already_saved: bool = Field(False, description="Whether draft was already saved before")


@router.post("/{draft_id}/save-to-client", response_model=SaveToClientResponse)
async def save_draft_to_client(
    current_user: CurrentUser,
    draft_id: str,
) -> dict[str, Any]:
    """Save an existing draft to the user's email client (Gmail/Outlook).

    ARIA NEVER sends - this only saves to the Drafts folder for user to review
    and manually send.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to save.

    Returns:
        Save result with client draft ID and provider.

    Raises:
        HTTPException: If draft not found or save fails.
    """
    try:
        client_writer = get_email_client_writer()
        result = await client_writer.save_draft_to_client(
            user_id=current_user.id,
            draft_id=draft_id,
        )
        logger.info(
            "Draft saved to client",
            extra={
                "user_id": current_user.id,
                "draft_id": draft_id,
                "provider": result.get("provider"),
            },
        )
        return {
            "success": True,
            "saved_at": datetime.now(UTC).isoformat(),
            "client_draft_id": result.get("client_draft_id"),
            "provider": result.get("provider"),
            "already_saved": result.get("already_saved", False),
        }
    except DraftSaveError as e:
        logger.warning(
            "Failed to save draft to client",
            extra={"user_id": current_user.id, "draft_id": draft_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to save draft to email client. Please try again.",
        ) from e
    except Exception as e:
        logger.exception("Unexpected error saving draft to client")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save draft to email client. Please try again.",
        ) from e


class ApproveRequest(BaseModel):
    """Request body for approving a draft, optionally with user edits."""

    edited_body: str | None = Field(None, description="User-edited draft body, if modified")


class ApproveResponse(BaseModel):
    """Response model for approving a draft."""

    success: bool = Field(..., description="Whether the approval was successful")
    saved_at: str = Field(..., description="Timestamp when saved to email client")


class DismissResponse(BaseModel):
    """Response model for dismissing a draft."""

    success: bool = Field(..., description="Whether the dismissal was successful")


@router.post("/{draft_id}/approve", response_model=ApproveResponse)
async def approve_draft(
    current_user: CurrentUser,
    draft_id: str,
    body: ApproveRequest | None = None,
) -> dict[str, Any]:
    """Approve a pending draft and save it to the user's email client.

    Drafts generated by ARIA are saved with status 'pending_review'.
    This endpoint approves the draft, changes status to 'approved',
    and saves it to Gmail/Outlook.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to approve.

    Returns:
        Success status with saved_at timestamp.

    Raises:
        HTTPException: If draft not found, wrong status, or save fails.
    """
    # Verify user permission via ActionGatekeeper
    gatekeeper = get_action_gatekeeper()
    if not await gatekeeper.authorize_approval("email_draft_save_to_client", current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to approve this action",
        )

    db = SupabaseClient.get_client()

    # Verify draft belongs to user and is pending review
    try:
        result = (
            db.table("email_drafts")
            .select("id, status, user_id, recipient_name, subject, body")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.exception("Failed to look up draft for approval")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to look up draft",
        ) from e

    record = result.data[0] if result and result.data else None
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    draft_data = record
    if draft_data["status"] != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Draft status is '{draft_data['status']}', expected 'pending_review'",
        )

    # Update status to approved with feedback tracking
    try:
        from src.services.draft_feedback_tracker import levenshtein_ratio

        edited_body = body.edited_body if body else None
        original_body = draft_data.get("body", "")
        now = datetime.now(UTC).isoformat()

        update_data: dict[str, Any] = {"status": "approved", "action_detected_at": now}

        if edited_body and edited_body != original_body:
            edit_distance = levenshtein_ratio(original_body, edited_body)
            update_data["user_action"] = "edited"
            update_data["user_edited_body"] = edited_body
            update_data["edit_distance"] = edit_distance
            update_data["body"] = edited_body
        else:
            update_data["user_action"] = "approved"
            update_data["edit_distance"] = 0.0

        db.table("email_drafts").update(update_data).eq("id", draft_id).execute()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update draft status to approved")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update draft status",
        ) from e

    # Save to email client
    try:
        client_writer = get_email_client_writer()
        await client_writer.save_draft_to_client(
            user_id=current_user.id,
            draft_id=draft_id,
        )
    except DraftSaveError as e:
        # Revert status on failure so user can retry
        db.table("email_drafts").update(
            {"status": "pending_review"}
        ).eq("id", draft_id).execute()
        logger.warning(
            "Draft approval: client save failed, reverted to pending_review",
            extra={"user_id": current_user.id, "draft_id": draft_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to save draft to email client. Please try again.",
        ) from e
    except Exception as e:
        db.table("email_drafts").update(
            {"status": "pending_review"}
        ).eq("id", draft_id).execute()
        logger.exception("Unexpected error during draft approval client save")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save draft to email client. Please try again.",
        ) from e

    saved_at = datetime.now(UTC).isoformat()
    logger.info(
        "Draft approved and saved to client",
        extra={"user_id": current_user.id, "draft_id": draft_id},
    )

    # Log to activity feed (non-blocking)
    try:
        activity_service = ActivityService()
        await activity_service.record(
            user_id=current_user.id,
            agent="scribe",
            activity_type="draft_saved_to_client",
            title="Draft saved to Outlook",
            description=f"Reply to {draft_data.get('recipient_name', 'Unknown')}: {draft_data.get('subject', 'No subject')}",
            confidence=1.0,
            related_entity_type="email_draft",
            related_entity_id=draft_id,
        )
    except Exception as e:
        logger.warning("Failed to log draft approval activity: %s", e)

    return {"success": True, "saved_at": saved_at}


@router.post("/{draft_id}/dismiss", response_model=DismissResponse)
async def dismiss_draft(
    current_user: CurrentUser,
    draft_id: str,
) -> dict[str, Any]:
    """Dismiss a pending draft without saving to email client.

    Changes draft status to 'dismissed'. The draft remains in the
    database but is not pushed to Gmail/Outlook.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to dismiss.

    Returns:
        Success status.

    Raises:
        HTTPException: If draft not found.
    """
    db = SupabaseClient.get_client()

    # Verify draft belongs to user
    try:
        result = (
            db.table("email_drafts")
            .select("id, user_id, recipient_name, subject")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.exception("Failed to look up draft for dismissal")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to look up draft",
        ) from e

    draft_data = result.data[0] if result and result.data else None
    if not draft_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    # Update status to dismissed with feedback tracking
    try:
        db.table("email_drafts").update({
            "status": "dismissed",
            "user_action": "rejected",
            "action_detected_at": datetime.now(UTC).isoformat(),
        }).eq("id", draft_id).execute()
    except Exception as e:
        logger.exception("Failed to dismiss draft")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dismiss draft",
        ) from e

    logger.info(
        "Draft dismissed",
        extra={"user_id": current_user.id, "draft_id": draft_id},
    )

    # Log to activity feed (non-blocking)
    try:
        activity_service = ActivityService()
        await activity_service.record(
            user_id=current_user.id,
            agent="scribe",
            activity_type="draft_dismissed",
            title=f"Draft dismissed: {draft_data.get('subject', 'No subject')}",
            description=f"User dismissed draft reply to {draft_data.get('recipient_name', 'Unknown')}",
            confidence=1.0,
            related_entity_type="email_draft",
            related_entity_id=draft_id,
        )
    except Exception as e:
        logger.warning("Failed to log draft dismissal activity: %s", e)

    return {"success": True}


# ---------------------------------------------------------------------------
# Draft Intelligence Context - Relevance-based signal matching
# ---------------------------------------------------------------------------


class MarketSignalItem(BaseModel):
    """A relevant market signal for the draft context."""

    id: str
    signal_type: str
    company_name: str
    content: str
    source: str | None = None
    created_at: str
    relevance_source: str = Field(
        ..., description="How this signal was matched: 'domain', 'subject', or 'fallback'"
    )


class RelationshipContext(BaseModel):
    """Relationship context when no signals match."""

    recipient_email: str
    last_interaction_date: str | None = None
    interaction_count: int = 0
    relationship_summary: str = "No specific market intelligence for this contact."


class DraftIntelligenceContextResponse(BaseModel):
    """Response model for draft intelligence context."""

    has_signals: bool = Field(..., description="Whether relevant signals were found")
    signals: list[MarketSignalItem] = Field(default_factory=list)
    relationship_context: RelationshipContext | None = None
    match_type: str = Field(
        ..., description="Type of match: 'domain', 'subject', 'relationship', or 'empty'"
    )


@router.get("/{draft_id}/intelligence-context", response_model=DraftIntelligenceContextResponse)
async def get_draft_intelligence_context(
    current_user: CurrentUser,
    draft_id: str,
) -> dict[str, Any]:
    """Get relevance-matched intelligence context for a draft.

    Priority cascade:
    1. RECIPIENT MATCH: Check if recipient email domain matches any monitored_entity's domains
    2. SUBJECT MATCH: Extract keywords from subject line and find matching signals
    3. RELATIONSHIP CONTEXT: Show email interaction history as fallback
    4. EMPTY STATE: Return clean empty state if nothing relevant

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft.

    Returns:
        Intelligence context with relevant signals or relationship context.

    Raises:
        HTTPException: If draft not found.
    """
    db = SupabaseClient.get_client()

    # Get the draft
    draft_result = (
        db.table("email_drafts")
        .select("id, user_id, recipient_email, subject")
        .eq("id", draft_id)
        .eq("user_id", current_user.id)
        .limit(1)
        .execute()
    )

    if not draft_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    draft = draft_result.data[0]
    recipient_email = draft.get("recipient_email", "")
    subject = draft.get("subject", "")

    # Extract domain from recipient email
    recipient_domain = ""
    if recipient_email and "@" in recipient_email:
        recipient_domain = recipient_email.split("@")[-1].lower()

    # PRIORITY 1: Check monitored_entities for domain match
    matched_entity = None
    if recipient_domain:
        entity_result = (
            db.table("monitored_entities")
            .select("id, entity_name, entity_type, domains")
            .eq("user_id", current_user.id)
            .eq("is_active", True)
            .execute()
        )

        for entity in entity_result.data or []:
            entity_domains = entity.get("domains") or []
            if recipient_domain in [d.lower() for d in entity_domains]:
                matched_entity = entity
                break

    # If domain matched, get signals for that entity
    if matched_entity:
        entity_name = matched_entity.get("entity_name", "")
        normalized_name = normalize_company_name(entity_name, supabase_client=db)

        signals_result = (
            db.table("market_signals")
            .select("id, signal_type, company_name, headline, source_name, detected_at")
            .eq("user_id", current_user.id)
            .is_("dismissed_at", "null")
            .ilike("company_name", f"%{normalized_name}%")
            .order("detected_at", desc=True)
            .limit(5)
            .execute()
        )

        if signals_result.data:
            signals = [
                {
                    "id": s["id"],
                    "signal_type": s["signal_type"],
                    "company_name": s["company_name"],
                    "content": s["headline"],
                    "source": s.get("source_name"),
                    "created_at": s["detected_at"],
                    "relevance_source": "domain",
                }
                for s in signals_result.data
            ]
            logger.info(
                "Draft intelligence context: domain match",
                extra={
                    "user_id": current_user.id,
                    "draft_id": draft_id,
                    "domain": recipient_domain,
                    "entity": entity_name,
                    "signal_count": len(signals),
                },
            )
            return {
                "has_signals": True,
                "signals": signals,
                "relationship_context": None,
                "match_type": "domain",
            }

    # PRIORITY 2: Subject line keyword matching
    keywords = _extract_subject_keywords(subject)
    if keywords:
        # Build OR query for keywords in headline
        keyword_filters = " | ".join(keywords[:3])  # Limit to top 3 keywords

        signals_result = (
            db.table("market_signals")
            .select("id, signal_type, company_name, headline, source_name, detected_at")
            .eq("user_id", current_user.id)
            .is_("dismissed_at", "null")
            .or_(f"headline.ilike.%{keyword_filters}%,company_name.ilike.%{keyword_filters}%")
            .order("detected_at", desc=True)
            .limit(3)
            .execute()
        )

        if signals_result.data:
            signals = [
                {
                    "id": s["id"],
                    "signal_type": s["signal_type"],
                    "company_name": s["company_name"],
                    "content": s["headline"],
                    "source": s.get("source_name"),
                    "created_at": s["detected_at"],
                    "relevance_source": "subject",
                }
                for s in signals_result.data
            ]
            logger.info(
                "Draft intelligence context: subject match",
                extra={
                    "user_id": current_user.id,
                    "draft_id": draft_id,
                    "keywords": keywords,
                    "signal_count": len(signals),
                },
            )
            return {
                "has_signals": True,
                "signals": signals,
                "relationship_context": None,
                "match_type": "subject",
            }

    # PRIORITY 3: Relationship context fallback
    if recipient_email:
        interaction_result = (
            db.table("email_scan_log")
            .select("scanned_at, category")
            .eq("user_id", current_user.id)
            .eq("sender_email", recipient_email)
            .order("scanned_at", desc=True)
            .limit(50)
            .execute()
        )

        interactions = interaction_result.data or []
        interaction_count = len(interactions)
        last_interaction = interactions[0]["scanned_at"] if interactions else None

        if interaction_count > 0:
            relationship_summary = f"{interaction_count} prior email exchange"
            if interaction_count > 1:
                relationship_summary = f"{interaction_count} prior email exchanges"

            logger.info(
                "Draft intelligence context: relationship fallback",
                extra={
                    "user_id": current_user.id,
                    "draft_id": draft_id,
                    "recipient_email": recipient_email,
                    "interaction_count": interaction_count,
                },
            )
            return {
                "has_signals": False,
                "signals": [],
                "relationship_context": {
                    "recipient_email": recipient_email,
                    "last_interaction_date": last_interaction,
                    "interaction_count": interaction_count,
                    "relationship_summary": relationship_summary,
                },
                "match_type": "relationship",
            }

    # PRIORITY 4: Empty state
    logger.info(
        "Draft intelligence context: empty state",
        extra={
            "user_id": current_user.id,
            "draft_id": draft_id,
            "recipient_email": recipient_email,
        },
    )
    return {
        "has_signals": False,
        "signals": [],
        "relationship_context": None,
        "match_type": "empty",
    }


def _extract_subject_keywords(subject: str) -> list[str]:
    """Extract meaningful keywords from email subject.

    Strips Re:, Fwd:, and common noise words.
    Returns list of meaningful keywords.
    """
    if not subject:
        return []

    # Strip prefixes
    cleaned = re.sub(r"^(Re|Fwd|Fw|Aw|Sv|Antw):\s*", "", subject, flags=re.IGNORECASE)

    # Common noise words to filter out
    noise_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "it", "this", "that", "be", "are",
        "was", "were", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might", "must",
        "meeting", "call", "update", "follow", "up", "regarding", "about",
        "question", "quick", "hello", "hi", "thanks", "thank", "you", "your",
    }

    # Extract words (alphanumeric, 3+ chars)
    words = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned.lower())

    # Filter noise and dedupe
    keywords = []
    seen = set()
    for word in words:
        if word not in noise_words and word not in seen:
            keywords.append(word)
            seen.add(word)

    return keywords[:5]  # Return top 5 keywords
