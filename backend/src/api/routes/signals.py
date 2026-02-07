"""Market signal API routes for ARIA.

This module provides endpoints for:
- Creating and querying market signals
- Managing read/dismissed states
- Managing monitored entities
"""

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.models.signal import MonitoredEntityCreate, SignalType
from src.services.signal_service import SignalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])


def _get_service() -> SignalService:
    """Get signal service instance."""
    return SignalService()


class UnreadCountResponse(BaseModel):
    """Response model for unread count."""

    count: int = Field(..., description="Number of unread signals")


class MarkedReadResponse(BaseModel):
    """Response model for marking as read."""

    marked_read: int = Field(..., description="Number of signals marked as read")


class RemoveResponse(BaseModel):
    """Response model for removing monitored entity."""

    status: str = Field(..., min_length=1, max_length=50, description="Status of removal operation")


# Market Signals Endpoints


@router.get("")
async def get_signals(
    current_user: CurrentUser,
    unread_only: bool = Query(False, description="Only return unread signals"),
    signal_type: SignalType | None = Query(None, description="Filter by signal type"),
    company: str | None = Query(None, description="Filter by company name"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of signals to return"),
) -> list[dict[str, Any]]:
    """Get market signals.

    Returns a list of market signals with optional filters.
    """
    service = _get_service()
    signals = await service.get_signals(
        user_id=current_user.id,
        unread_only=unread_only,
        signal_type=signal_type,
        company_name=company,
        limit=limit,
    )

    logger.info(
        "Signals retrieved",
        extra={"user_id": current_user.id, "count": len(signals)},
    )

    return signals


@router.get("/unread/count")
async def get_unread_count(
    current_user: CurrentUser,
) -> UnreadCountResponse:
    """Get count of unread signals.

    Returns the number of unread market signals.
    """
    service = _get_service()
    count = await service.get_unread_count(current_user.id)

    logger.info(
        "Unread signal count retrieved",
        extra={"user_id": current_user.id, "count": count},
    )

    return UnreadCountResponse(count=count)


@router.post("/{signal_id}/read")
async def mark_signal_read(
    signal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any] | None:
    """Mark a signal as read.

    Marks a specific signal as read by setting the read_at timestamp.
    """
    service = _get_service()
    result = await service.mark_as_read(current_user.id, signal_id)

    if result is None:
        logger.warning(
            "Signal not found for marking as read",
            extra={"user_id": current_user.id, "signal_id": signal_id},
        )

    logger.info(
        "Signal marked as read",
        extra={"user_id": current_user.id, "signal_id": signal_id},
    )

    return result


@router.post("/read-all")
async def mark_all_read(
    current_user: CurrentUser,
) -> MarkedReadResponse:
    """Mark all signals as read.

    Marks all unread signals for the user as read.
    """
    service = _get_service()
    count = await service.mark_all_read(current_user.id)

    logger.info(
        "All signals marked as read",
        extra={"user_id": current_user.id, "count": count},
    )

    return MarkedReadResponse(marked_read=count)


@router.post("/{signal_id}/dismiss")
async def dismiss_signal(
    signal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any] | None:
    """Dismiss a signal.

    Dismisses a specific signal by setting the dismissed_at timestamp.
    """
    service = _get_service()
    result = await service.dismiss_signal(current_user.id, signal_id)

    if result is None:
        logger.warning(
            "Signal not found for dismissal",
            extra={"user_id": current_user.id, "signal_id": signal_id},
        )

    logger.info(
        "Signal dismissed",
        extra={"user_id": current_user.id, "signal_id": signal_id},
    )

    return result


# Monitored Entities Endpoints


@router.get("/monitored")
async def get_monitored_entities(
    current_user: CurrentUser,
    active_only: bool = Query(True, description="Only return active entities"),
) -> list[dict[str, Any]]:
    """Get monitored entities.

    Returns a list of entities being monitored for market signals.
    """
    service = _get_service()
    entities = await service.get_monitored_entities(
        user_id=current_user.id,
        active_only=active_only,
    )

    logger.info(
        "Monitored entities retrieved",
        extra={"user_id": current_user.id, "count": len(entities)},
    )

    return entities


@router.post("/monitored")
async def add_monitored_entity(
    data: MonitoredEntityCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Add an entity to monitor.

    Adds a new entity to be monitored for market signals.
    """
    service = _get_service()
    result = await service.add_monitored_entity(current_user.id, data)

    logger.info(
        "Monitored entity added",
        extra={
            "user_id": current_user.id,
            "entity_type": data.entity_type.value,
            "entity_name": data.entity_name,
        },
    )

    return result


@router.delete("/monitored/{entity_id}")
async def remove_monitored_entity(
    entity_id: str,
    current_user: CurrentUser,
) -> RemoveResponse:
    """Stop monitoring an entity.

    Deactivates monitoring for a specific entity.
    """
    service = _get_service()
    await service.remove_monitored_entity(current_user.id, entity_id)

    logger.info(
        "Monitored entity removed",
        extra={"user_id": current_user.id, "entity_id": entity_id},
    )

    return RemoveResponse(status="removed")
