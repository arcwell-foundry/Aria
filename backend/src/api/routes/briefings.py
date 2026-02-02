"""Briefing API routes for daily morning briefings."""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.briefing import BriefingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefings", tags=["briefings"])
briefing_service = BriefingService()


class BriefingContent(BaseModel):
    """Content of a daily briefing."""

    summary: str = Field(..., description="Executive summary")
    calendar: dict = Field(..., description="Calendar information")
    leads: dict = Field(..., description="Lead status summary")
    signals: dict = Field(..., description="Market signals")
    tasks: dict = Field(..., description="Task status")
    generated_at: str = Field(..., description="ISO timestamp of generation")


class BriefingResponse(BaseModel):
    """Response model for a briefing."""

    id: str = Field(..., description="Briefing ID")
    user_id: str = Field(..., description="User ID")
    briefing_date: str = Field(..., description="Briefing date (ISO format)")
    content: BriefingContent = Field(..., description="Briefing content")


class BriefingListResponse(BaseModel):
    """Response model for listing briefings."""

    id: str
    briefing_date: str
    content: dict


class GenerateBriefingRequest(BaseModel):
    """Request body for generating a briefing."""

    briefing_date: str | None = Field(None, description="ISO date string (e.g., 2026-02-01)")


@router.get("/today", response_model=BriefingContent)
async def get_today_briefing(
    regenerate: bool = Query(False, description="Force regenerate briefing"),
    current_user: CurrentUser,
) -> BriefingContent:
    """Get today's briefing, generating if needed.

    Returns the daily briefing content for the current user.
    If regenerate=true, forces generation of a new briefing.
    """
    if regenerate:
        content = await briefing_service.generate_briefing(current_user.id)
    else:
        content = await briefing_service.get_or_generate_briefing(current_user.id)

    logger.info(
        "Today's briefing retrieved",
        extra={"user_id": current_user.id, "regenerate": regenerate},
    )

    return BriefingContent(**content)


@router.get("", response_model=list[BriefingListResponse])
async def list_briefings(
    limit: int = Query(7, ge=1, le=30, description="Maximum number of briefings"),
    current_user: CurrentUser,
) -> list[BriefingListResponse]:
    """List recent briefings.

    Returns a list of recent briefings for the current user.
    """
    briefings = await briefing_service.list_briefings(current_user.id, limit)

    logger.info(
        "Briefings listed",
        extra={"user_id": current_user.id, "count": len(briefings)},
    )

    return [BriefingListResponse(**b) for b in briefings]


@router.get("/{briefing_date}", response_model=BriefingResponse)
async def get_briefing_by_date(
    briefing_date: date,
    current_user: CurrentUser,
) -> BriefingResponse:
    """Get briefing for specific date.

    Returns the briefing for the specified date.
    Raises 404 if not found.
    """
    briefing = await briefing_service.get_briefing(current_user.id, briefing_date)

    if not briefing:
        raise HTTPException(
            status_code=404, detail=f"Briefing for {briefing_date} not found"
        )

    logger.info(
        "Briefing retrieved by date",
        extra={"user_id": current_user.id, "briefing_date": str(briefing_date)},
    )

    return BriefingResponse(**briefing)


@router.post("/generate", response_model=BriefingContent)
async def generate_briefing(
    request: GenerateBriefingRequest | None = None,
    current_user: CurrentUser,
) -> BriefingContent:
    """Force generate a new briefing.

    Generates a new briefing for today or the specified date.
    """
    briefing_date = None
    if request and request.briefing_date:
        briefing_date = date.fromisoformat(request.briefing_date)

    content = await briefing_service.generate_briefing(current_user.id, briefing_date)

    logger.info(
        "Briefing generated",
        extra={"user_id": current_user.id, "briefing_date": str(briefing_date)},
    )

    return BriefingContent(**content)
