"""Deck generation API routes for AI-powered Gamma presentations.

Endpoints:
- POST /create - Create deck from meeting context
- POST /adhoc - Create deck from ad-hoc prompt
- GET / - List user's decks
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.config import settings
from src.db.supabase import SupabaseClient
from src.services.deck_service import (
    DeckServiceError,
    create_adhoc_deck,
    create_deck_from_context,
    list_user_decks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decks", tags=["decks"])


# ============================================================================
# Request/Response Models
# ============================================================================


class MeetingContextDeckRequest(BaseModel):
    """Request to create a deck from meeting context."""

    meeting_id: str = Field(..., description="Meeting ID to associate deck with")
    meeting_title: str = Field(..., description="Title of the meeting")
    meeting_objective: str | None = Field(None, description="Meeting objective")
    attendees: list[dict[str, Any]] | None = Field(None, description="List of attendees")
    account_research: str | None = Field(None, description="Research about the account")
    talking_points: list[str] | None = Field(None, description="Key talking points")
    previous_interactions: str | None = Field(None, description="History with this account")
    post_to_meeting: bool = Field(
        False, description="Whether to post deck link to meeting chat"
    )


class AdhocDeckRequest(BaseModel):
    """Request to create a deck from an ad-hoc prompt."""

    prompt: str = Field(..., description="Text prompt or content to generate deck from")
    title: str | None = Field(None, description="Optional title for the deck")
    text_mode: str = Field(
        "generate",
        description="How to process text: generate, condense, or preserve",
    )


class DeckResponse(BaseModel):
    """Response for deck creation."""

    deck_id: str
    gamma_url: str
    gamma_id: str
    pptx_url: str | None = None
    status: str
    credits_used: int


class DeckListResponse(BaseModel):
    """Response for deck listing."""

    id: str
    user_id: str
    calendar_event_id: str | None = None
    title: str
    status: str
    gamma_url: str | None = None
    gamma_id: str | None = None
    pptx_url: str | None = None
    created_at: str
    completed_at: str | None = None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/create", response_model=DeckResponse)
async def create_deck(
    current_user: CurrentUser,
    request: MeetingContextDeckRequest,
) -> DeckResponse:
    """Create a presentation deck from meeting context.

    Generates an AI-powered presentation using meeting briefing data,
    account research, and other contextual information.

    Requires GAMMA_API_KEY to be configured.

    Args:
        current_user: Authenticated user.
        request: Meeting context and options.

    Returns:
        Deck creation result with gamma_url.

    Raises:
        HTTPException: If deck generation fails.
    """
    if not settings.gamma_configured:
        raise HTTPException(
            status_code=503,
            detail="Gamma API not configured. Please set GAMMA_API_KEY.",
        )

    logger.info(
        "Creating deck from meeting context: user=%s meeting=%s",
        current_user.id,
        request.meeting_id,
    )

    try:
        db = SupabaseClient.get_client()

        context = {
            "meeting_title": request.meeting_title,
            "meeting_objective": request.meeting_objective,
            "attendees": request.attendees or [],
            "account_research": request.account_research,
            "talking_points": request.talking_points or [],
            "previous_interactions": request.previous_interactions,
        }

        result = await create_deck_from_context(
            db=db,
            user_id=current_user.id,
            meeting_id=request.meeting_id,
            context=context,
            post_to_meeting=request.post_to_meeting,
        )

        return DeckResponse(
            deck_id=result["deck_id"],
            gamma_url=result["gamma_url"],
            gamma_id=result["gamma_id"],
            pptx_url=result.get("pptx_url"),
            status=result["status"],
            credits_used=result["credits_used"],
        )

    except DeckServiceError as e:
        logger.error("Deck creation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/adhoc", response_model=DeckResponse)
async def create_adhoc(
    current_user: CurrentUser,
    request: AdhocDeckRequest,
) -> DeckResponse:
    """Create a presentation deck from an ad-hoc prompt.

    Generates an AI-powered presentation from user-provided text.
    Supports three modes:
    - generate: Create from scratch using AI
    - condense: Summarize existing content
    - preserve: Keep content, just format nicely

    Requires GAMMA_API_KEY to be configured.

    Args:
        current_user: Authenticated user.
        request: Prompt and options.

    Returns:
        Deck creation result with gamma_url.

    Raises:
        HTTPException: If deck generation fails.
    """
    if not settings.gamma_configured:
        raise HTTPException(
            status_code=503,
            detail="Gamma API not configured. Please set GAMMA_API_KEY.",
        )

    if request.text_mode not in ("generate", "condense", "preserve"):
        raise HTTPException(
            status_code=400,
            detail="text_mode must be 'generate', 'condense', or 'preserve'",
        )

    logger.info(
        "Creating ad-hoc deck: user=%s mode=%s",
        current_user.id,
        request.text_mode,
    )

    try:
        db = SupabaseClient.get_client()

        result = await create_adhoc_deck(
            db=db,
            user_id=current_user.id,
            prompt=request.prompt,
            title=request.title,
            text_mode=request.text_mode,
        )

        return DeckResponse(
            deck_id=result["deck_id"],
            gamma_url=result["gamma_url"],
            gamma_id=result["gamma_id"],
            pptx_url=result.get("pptx_url"),
            status=result["status"],
            credits_used=result["credits_used"],
        )

    except DeckServiceError as e:
        logger.error("Ad-hoc deck creation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/", response_model=list[DeckListResponse])
async def list_decks(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of decks"),
    calendar_event_id: str | None = Query(None, description="Filter by calendar event ID"),
) -> list[DeckListResponse]:
    """List decks for the current user.

    Args:
        current_user: Authenticated user.
        limit: Maximum number of decks to return.
        calendar_event_id: Optional calendar event ID to filter by.

    Returns:
        List of deck records.
    """
    logger.info(
        "Listing decks: user=%s calendar_event=%s limit=%d",
        current_user.id,
        calendar_event_id,
        limit,
    )

    db = SupabaseClient.get_client()
    decks = await list_user_decks(
        db=db,
        user_id=current_user.id,
        limit=limit,
        calendar_event_id=calendar_event_id,
    )

    return [
        DeckListResponse(
            id=deck["id"],
            user_id=deck["user_id"],
            calendar_event_id=deck.get("calendar_event_id"),
            title=deck["title"],
            status=deck["status"],
            gamma_url=deck.get("deck_url"),  # DB column is deck_url, but API exposes gamma_url
            gamma_id=deck.get("gamma_id"),
            pptx_url=deck.get("pptx_url"),
            created_at=deck["created_at"],
            completed_at=deck.get("completed_at"),
        )
        for deck in decks
    ]


@router.get("/{deck_id}/download")
async def download_deck(
    current_user: CurrentUser,
    deck_id: str,
) -> RedirectResponse:
    """Download a deck's PPTX file via signed URL redirect.

    Returns a 302 redirect to the Supabase Storage signed URL.
    Returns 404 if the deck doesn't exist or has no PPTX file.

    Args:
        current_user: Authenticated user.
        deck_id: The deck ID to download.

    Returns:
        302 redirect to the signed PPTX download URL.
    """
    db = SupabaseClient.get_client()

    try:
        result = (
            db.table("decks")
            .select("pptx_url")
            .eq("id", deck_id)
            .eq("user_id", current_user.id)
            .single()
            .execute()
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Deck not found")

    if not result.data or not result.data.get("pptx_url"):
        raise HTTPException(
            status_code=404,
            detail="PPTX file not available for this deck",
        )

    return RedirectResponse(url=result.data["pptx_url"], status_code=302)


@router.get("/health")
async def deck_health_check() -> dict[str, Any]:
    """Check if deck generation is available.

    Returns:
        Dict with status and configuration info.
    """
    return {
        "available": settings.gamma_configured,
        "message": "Gamma API configured" if settings.gamma_configured else "GAMMA_API_KEY not set",
    }
