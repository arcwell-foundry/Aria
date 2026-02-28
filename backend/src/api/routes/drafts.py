"""Drafts API routes for email draft management."""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import EmailDraftError, EmailSendError, NotFoundError
from src.models.email_draft import (
    EmailDraftCreate,
    EmailDraftListResponse,
    EmailDraftResponse,
    EmailDraftUpdate,
    EmailRegenerateRequest,
    EmailSendResponse,
)
from src.db.supabase import SupabaseClient
from src.services.action_gatekeeper import get_action_gatekeeper
from src.services.activity_service import ActivityService
from src.services.draft_service import get_draft_service
from src.services.email_client_writer import DraftSaveError, get_email_client_writer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str = Field(..., min_length=1, max_length=500)


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
) -> list[dict[str, Any]]:
    """List user's email drafts.

    Args:
        current_user: The authenticated user.
        limit: Maximum number of drafts to return (1-100).
        status: Optional status filter.

    Returns:
        List of email drafts.
    """
    service = get_draft_service()
    drafts = await service.list_drafts(current_user.id, limit, status)
    logger.info("Drafts listed", extra={"user_id": current_user.id, "count": len(drafts)})
    return drafts


@router.get("/{draft_id}", response_model=EmailDraftResponse)
async def get_draft(current_user: CurrentUser, draft_id: str) -> dict[str, Any]:
    """Get a specific email draft.

    Args:
        current_user: The authenticated user.
        draft_id: The ID of the draft to retrieve.

    Returns:
        The email draft.

    Raises:
        HTTPException: If draft not found.
    """
    service = get_draft_service()
    draft = await service.get_draft(current_user.id, draft_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Draft {draft_id} not found"
        )
    return draft


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
            .select("id, status, user_id, recipient_name, subject")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.exception("Failed to look up draft for approval")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to look up draft",
        ) from e

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    draft_data = result.data
    if draft_data["status"] != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Draft status is '{draft_data['status']}', expected 'pending_review'",
        )

    # Update status to approved
    try:
        db.table("email_drafts").update(
            {"status": "approved"}
        ).eq("id", draft_id).execute()
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
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.exception("Failed to look up draft for dismissal")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to look up draft",
        ) from e

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    draft_data = result.data

    # Update status to dismissed
    try:
        db.table("email_drafts").update(
            {"status": "dismissed"}
        ).eq("id", draft_id).execute()
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
