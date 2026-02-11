"""Briefing API routes for daily morning briefings."""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.briefing import BriefingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefings", tags=["briefings"])


class BriefingContent(BaseModel):
    """Content of a daily briefing."""

    summary: str = Field(..., min_length=1, max_length=5000, description="Executive summary")
    calendar: dict[str, Any] = Field(..., description="Calendar information")
    leads: dict[str, Any] = Field(..., description="Lead status summary")
    signals: dict[str, Any] = Field(..., description="Market signals")
    tasks: dict[str, Any] = Field(..., description="Task status")
    generated_at: str = Field(..., min_length=1, max_length=100, description="ISO timestamp of generation")


class BriefingResponse(BaseModel):
    """Response model for a briefing."""

    id: str = Field(..., min_length=1, max_length=50, description="Briefing ID")
    user_id: str = Field(..., min_length=1, max_length=50, description="User ID")
    briefing_date: str = Field(..., min_length=10, max_length=10, description="Briefing date (ISO format)")
    content: BriefingContent = Field(..., description="Briefing content")


class BriefingListResponse(BaseModel):
    """Response model for listing briefings."""

    id: str
    briefing_date: str
    content: dict[str, Any]


class GenerateBriefingRequest(BaseModel):
    """Request body for generating a briefing."""

    briefing_date: str | None = Field(None, description="ISO date string (e.g., 2026-02-01)")


@router.get("/today")
async def get_today_briefing(
    current_user: CurrentUser,
    regenerate: bool = Query(False, description="Force regenerate briefing"),
) -> dict[str, Any]:
    """Get today's briefing, generating if needed.

    Returns the daily briefing content for the current user.
    If no briefing exists yet and regenerate is not requested,
    returns a not_generated status so the dashboard can show
    an empty state.
    """
    service = BriefingService()

    if regenerate:
        content = await service.generate_briefing(current_user.id)
        return {"briefing": content, "status": "ready"}

    existing = await service.get_briefing(current_user.id)
    if existing:
        content = existing.get("content")
        if isinstance(content, dict):
            return {"briefing": content, "status": "ready"}

    # No briefing yet — return empty default instead of generating
    logger.info(
        "No briefing available for user",
        extra={"user_id": current_user.id},
    )
    return {"briefing": None, "status": "not_generated"}


@router.get("", response_model=list[BriefingListResponse])
async def list_briefings(
    current_user: CurrentUser,
    limit: int = Query(7, ge=1, le=30, description="Maximum number of briefings"),
) -> list[BriefingListResponse]:
    """List recent briefings.

    Returns a list of recent briefings for the current user.
    """
    service = BriefingService()
    briefings = await service.list_briefings(current_user.id, limit)

    logger.info(
        "Briefings listed",
        extra={"user_id": current_user.id, "count": len(briefings)},
    )

    return [BriefingListResponse(**b) for b in briefings]


@router.get("/{briefing_date}", response_model=BriefingResponse)
async def get_briefing_by_date(
    current_user: CurrentUser,
    briefing_date: date,
) -> BriefingResponse:
    """Get briefing for specific date.

    Returns the briefing for the specified date.
    Raises 404 if not found.
    """
    service = BriefingService()
    briefing = await service.get_briefing(current_user.id, briefing_date)

    if not briefing:
        raise HTTPException(status_code=404, detail=f"Briefing for {briefing_date} not found")

    logger.info(
        "Briefing retrieved by date",
        extra={"user_id": current_user.id, "briefing_date": str(briefing_date)},
    )

    return BriefingResponse(**briefing)


@router.post("/generate", response_model=BriefingContent)
async def generate_briefing(
    current_user: CurrentUser,
    request: GenerateBriefingRequest | None = None,
) -> BriefingContent:
    """Force generate a new briefing.

    Generates a new briefing for today or the specified date.
    """
    briefing_date = None
    if request and request.briefing_date:
        briefing_date = date.fromisoformat(request.briefing_date)

    service = BriefingService()
    content = await service.generate_briefing(current_user.id, briefing_date)

    logger.info(
        "Briefing generated",
        extra={"user_id": current_user.id, "briefing_date": str(briefing_date)},
    )

    return BriefingContent(**content)


@router.post("/regenerate", response_model=BriefingContent)
async def regenerate_briefing(
    current_user: CurrentUser,
) -> BriefingContent:
    """Regenerate today's briefing with fresh data.

    Forces regeneration of today's briefing, useful when
    underlying data has changed (new leads, signals, etc.).
    """
    service = BriefingService()
    content = await service.generate_briefing(current_user.id)

    logger.info(
        "Briefing regenerated",
        extra={"user_id": current_user.id},
    )

    return BriefingContent(**content)
