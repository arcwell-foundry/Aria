"""Communication API routes (US-938).

Internal API used by agents to send communications through ARIA's
orchestrated routing system. Not directly user-facing.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser
from src.core.communication_router import get_communication_router
from src.models.communication import (
    CommunicationRequest,
    CommunicationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/communicate", tags=["communication"])


@router.post("", response_model=CommunicationResponse, status_code=status.HTTP_200_OK)
async def send_communication(
    request: CommunicationRequest,
    current_user: CurrentUser,
) -> CommunicationResponse:
    """Route a communication through ARIA's intelligent channel router.

    This endpoint is primarily used internally by agents to send notifications
    to users through the appropriate channel(s) based on urgency and preferences.

    Priority-based routing:
    - critical: in-app + push notification
    - important: in-app + email/Slack (user preference)
    - fyi: in-app only
    - background: no notification (logging only)

    The `user_id` in the request body is overridden by the authenticated user's ID
    for security. Agents can only send notifications on behalf of the authenticated user.

    Args:
        request: Communication request with message, priority, and optional context.
        current_user: The authenticated user (auto-injected).

    Returns:
        Response showing which channels were used and delivery results.

    Raises:
        HTTPException: If routing fails or all channels fail.
    """
    try:
        # Override user_id with authenticated user for security
        # (agents can only send for the current user)
        secured_request = CommunicationRequest(
            user_id=current_user.id,
            message=request.message,
            priority=request.priority,
            title=request.title,
            link=request.link,
            metadata=request.metadata,
            force_channels=request.force_channels,
        )

        router_instance = get_communication_router()
        response = await router_instance.route_message(secured_request)

        # Check if at least one channel succeeded
        any_success = any(result.success for result in response.results.values())

        if not any_success:
            logger.warning(
                "All communication channels failed",
                extra={
                    "user_id": current_user.id,
                    "priority": request.priority.value,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to send notification through all available channels",
            )

        logger.info(
            "Communication routed successfully",
            extra={
                "user_id": current_user.id,
                "priority": request.priority.value,
                "channels": [c.value for c in response.channels_used],
            },
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error routing communication",
            extra={"user_id": current_user.id, "priority": request.priority.value},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to route communication",
        ) from e
