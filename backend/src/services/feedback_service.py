"""Feedback service for ARIA.

This service handles collecting and managing user feedback, including:
- Response feedback (thumbs up/down on ARIA's responses)
- General feedback (bug reports, feature requests, other)
"""

import logging
from typing import Any, cast

from src.core.exceptions import DatabaseError
from src.db.supabase import SupabaseClient
from src.models.feedback import (
    FeedbackRating,
    FeedbackResponse,
    FeedbackType,
)

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service for managing user feedback."""

    @staticmethod
    async def submit_response_feedback(
        user_id: str,
        message_id: str,
        rating: FeedbackRating,
        comment: str | None = None,
    ) -> FeedbackResponse:
        """Submit feedback on an ARIA response.

        Args:
            user_id: The user's UUID.
            message_id: The message UUID being rated.
            rating: User's rating (up or down).
            comment: Optional comment explaining the rating.

        Returns:
            Created feedback entry.

        Raises:
            DatabaseError: If submission fails.
        """
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "type": FeedbackType.RESPONSE.value,
                "rating": rating.value,
                "message_id": message_id,
                "comment": comment,
            }
            response = client.table("feedback").insert(data).execute()
            if response.data and len(response.data) > 0:
                feedback_data = cast(dict[str, Any], response.data[0])
                logger.info(
                    "Response feedback submitted",
                    extra={
                        "user_id": user_id,
                        "message_id": message_id,
                        "rating": rating.value,
                        "feedback_id": feedback_data["id"],
                    },
                )
                return FeedbackResponse(**feedback_data)
            raise DatabaseError("Failed to submit response feedback")
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Error submitting response feedback",
                extra={"user_id": user_id, "message_id": message_id, "rating": rating.value},
            )
            raise DatabaseError(f"Failed to submit response feedback: {e}") from e

    @staticmethod
    async def submit_general_feedback(
        user_id: str,
        feedback_type: FeedbackType,
        message: str,
        page: str | None = None,
    ) -> FeedbackResponse:
        """Submit general feedback on the system.

        Args:
            user_id: The user's UUID.
            feedback_type: Type of feedback (bug, feature, or other).
            message: Feedback message from the user.
            page: Optional page where the feedback was submitted.

        Returns:
            Created feedback entry.

        Raises:
            DatabaseError: If submission fails.
            ValueError: If message exceeds maximum length.
        """
        if len(message) > 2000:
            raise ValueError("Message exceeds maximum length of 2000 characters")
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "type": feedback_type.value,
                "message": message,
                "page": page,
            }
            response = client.table("feedback").insert(data).execute()
            if response.data and len(response.data) > 0:
                feedback_data = cast(dict[str, Any], response.data[0])
                logger.info(
                    "General feedback submitted",
                    extra={
                        "user_id": user_id,
                        "type": feedback_type.value,
                        "page": page,
                        "feedback_id": feedback_data["id"],
                    },
                )
                return FeedbackResponse(**feedback_data)
            raise DatabaseError("Failed to submit general feedback")
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Error submitting general feedback",
                extra={"user_id": user_id, "type": feedback_type.value, "page": page},
            )
            raise DatabaseError(f"Failed to submit general feedback: {e}") from e
