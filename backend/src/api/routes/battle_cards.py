"""Battle cards API routes for competitive intelligence."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.services.battle_card_service import (
    BattleCardCreate,
    BattleCardService,
    BattleCardUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/battlecards", tags=["battle_cards"])


def _get_service() -> BattleCardService:
    """Get battle card service instance."""
    return BattleCardService()


async def _get_user_company_id(user_id: str) -> str:
    """Get the user's company_id from their profile.

    Args:
        user_id: The user's UUID.

    Returns:
        The company_id from the user's profile.

    Raises:
        HTTPException: If user profile not found or no company_id.
    """
    try:
        profile = await SupabaseClient.get_user_by_id(user_id)
        company_id = profile.get("company_id")
        if not company_id:
            raise HTTPException(
                status_code=400,
                detail="User must be associated with a company to access battle cards",
            )
        return str(company_id)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="User profile not found") from None
        raise


@router.get("/")
async def list_battle_cards(
    current_user: CurrentUser,
    search: str | None = Query(None, description="Search term for competitor name"),
) -> list[dict[str, Any]]:
    """List all battle cards for the user's company.

    Args:
        current_user: Authenticated user.
        search: Optional search term to filter by competitor name.

    Returns:
        List of battle cards.
    """
    company_id = await _get_user_company_id(current_user.id)

    logger.info(
        "Listing battle cards",
        extra={"user_id": current_user.id, "company_id": company_id, "search": search},
    )

    svc = _get_service()
    return await svc.list_battle_cards(company_id, search)


@router.get("/{competitor_name}")
async def get_battle_card(
    competitor_name: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a specific battle card by competitor name.

    Args:
        competitor_name: The competitor name.
        current_user: Authenticated user.

    Returns:
        Battle card data.

    Raises:
        HTTPException: 404 if battle card not found.
    """
    company_id = await _get_user_company_id(current_user.id)
    svc = _get_service()

    card = await svc.get_battle_card(company_id, competitor_name)
    if not card:
        raise HTTPException(status_code=404, detail="Battle card not found")

    return card


@router.post("/")
async def create_battle_card(
    data: BattleCardCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Create a new battle card.

    Args:
        data: Battle card creation data.
        current_user: Authenticated user.

    Returns:
        Created battle card with ID.
    """
    company_id = await _get_user_company_id(current_user.id)

    logger.info(
        "Creating battle card",
        extra={"user_id": current_user.id, "company_id": company_id, "competitor_name": data.competitor_name},
    )
    svc = _get_service()

    return await svc.create_battle_card(company_id, data)


@router.patch("/{card_id}")
async def update_battle_card(
    card_id: str,
    data: BattleCardUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update a battle card.

    Args:
        card_id: The battle card ID.
        data: Update data.
        current_user: Authenticated user.

    Returns:
        Updated battle card.
    """
    logger.info(
        "Updating battle card",
        extra={"user_id": current_user.id, "card_id": card_id},
    )
    svc = _get_service()

    return await svc.update_battle_card(card_id, data)


@router.delete("/{card_id}")
async def delete_battle_card(
    card_id: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Delete a battle card.

    Args:
        card_id: The battle card ID.
        current_user: Authenticated user.

    Returns:
        Success status.
    """
    svc = _get_service()
    await svc.delete_battle_card(card_id)

    logger.info(
        "Deleted battle card",
        extra={"user_id": current_user.id, "card_id": card_id},
    )

    return {"status": "deleted"}


@router.get("/{card_id}/history")
async def get_battle_card_history(
    card_id: str,
    _current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of changes"),
) -> list[dict[str, Any]]:
    """Get change history for a battle card.

    Args:
        card_id: The battle card ID.
        limit: Maximum number of changes to return.
        current_user: Authenticated user.

    Returns:
        List of change records.
    """
    svc = _get_service()
    return await svc.get_card_history(card_id, limit)


@router.post("/{card_id}/objections")
async def add_objection_handler(
    card_id: str,
    current_user: CurrentUser,
    objection: str = Query(..., description="The objection statement"),
    response: str = Query(..., description="The recommended response"),
) -> dict[str, Any]:
    """Add an objection handler to a battle card.

    Args:
        card_id: The battle card ID.
        objection: The objection statement.
        response: The recommended response.
        current_user: Authenticated user.

    Returns:
        Updated battle card.
    """
    logger.info(
        "Adding objection handler",
        extra={"user_id": current_user.id, "card_id": card_id, "objection": objection},
    )
    svc = _get_service()

    return await svc.add_objection_handler(card_id, objection, response)
