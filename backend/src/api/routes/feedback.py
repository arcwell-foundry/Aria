"""Feedback API routes for US-933.

This module provides endpoints for:
- Response feedback (thumbs up/down on ARIA's responses)
- General feedback (bug reports, feature requests, other)
"""

import logging

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser
from src.core.exceptions import DatabaseError
from src.models.feedback import (
    FeedbackResponse,
    GeneralFeedbackRequest,
    ResponseFeedbackRequest,
)
from src.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = logging.getLogger(__name__)


@router.post("/response", status_code=status.HTTP_201_CREATED)
async def submit_response_feedback(
    request: ResponseFeedbackRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Submit feedback on an ARIA response.

    Allows users to rate ARIA's responses with thumbs up/down and optionally
    provide a comment explaining their rating.

    Args:
        request: Feedback request containing message_id, rating, and optional comment.
        current_user: The authenticated user.

    Returns:
        Confirmation message with feedback ID.

    Raises:
        HTTPException: If feedback submission fails.
    """
    try:
        feedback_service = FeedbackService()
        result = await feedback_service.submit_response_feedback(
            user_id=current_user.id,
            message_id=request.message_id,
            rating=request.rating,
            comment=request.comment,
        )
        logger.info(
            "Response feedback submitted successfully",
            extra={
                "user_id": current_user.id,
                "message_id": request.message_id,
                "rating": request.rating.value,
                "feedback_id": result.id,
            },
        )
        return {
            "message": "Thank you for your feedback!",
            "feedback_id": result.id,
        }
    except DatabaseError as e:
        logger.error(
            "Database error submitting response feedback",
            extra={"user_id": current_user.id, "message_id": request.message_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback. Please try again later.",
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error submitting response feedback",
            extra={"user_id": current_user.id, "message_id": request.message_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        ) from e


@router.post("/general", status_code=status.HTTP_201_CREATED)
async def submit_general_feedback(
    request: GeneralFeedbackRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Submit general feedback on the system.

    Allows users to submit bug reports, feature requests, and other general feedback.

    Args:
        request: Feedback request containing type, message, and optional page.
        current_user: The authenticated user.

    Returns:
        Confirmation message with feedback ID.

    Raises:
        HTTPException: If feedback submission fails.
    """
    try:
        feedback_service = FeedbackService()
        result = await feedback_service.submit_general_feedback(
            user_id=current_user.id,
            feedback_type=request.type,
            message=request.message,
            page=request.page,
        )
        logger.info(
            "General feedback submitted successfully",
            extra={
                "user_id": current_user.id,
                "type": request.type.value,
                "page": request.page,
                "feedback_id": result.id,
            },
        )
        return {
            "message": "Thank you for your feedback!",
            "feedback_id": result.id,
        }
    except ValueError as e:
        # Validation errors like message too long
        logger.warning(
            "Validation error submitting general feedback",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except DatabaseError as e:
        logger.error(
            "Database error submitting general feedback",
            extra={"user_id": current_user.id, "type": request.type.value},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback. Please try again later.",
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error submitting general feedback",
            extra={"user_id": current_user.id, "type": request.type.value},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        ) from e
