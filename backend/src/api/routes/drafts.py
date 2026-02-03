"""Drafts API routes for email draft management."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

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
from src.services.draft_service import get_draft_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


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
