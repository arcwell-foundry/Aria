"""Feedback Pydantic models for ARIA.

This module contains all models related to user feedback on ARIA's responses
and general feedback on the system.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FeedbackType(str, Enum):
    """Type of general feedback."""

    RESPONSE = "response"
    BUG = "bug"
    FEATURE = "feature"
    OTHER = "other"


class FeedbackRating(str, Enum):
    """Rating for response feedback."""

    UP = "up"
    DOWN = "down"


class ResponseFeedbackRequest(BaseModel):
    """Request model for feedback on ARIA's response."""

    message_id: str = Field(..., description="ID of the message being rated")
    rating: FeedbackRating = Field(..., description="User's rating (up or down)")
    comment: str | None = Field(
        None,
        max_length=1000,
        description="Optional comment explaining the rating",
    )


class GeneralFeedbackRequest(BaseModel):
    """Request model for general feedback on the system."""

    type: FeedbackType = Field(..., description="Type of feedback (bug, feature, or other)")
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Feedback message from the user",
    )
    page: str | None = Field(
        None,
        max_length=200,
        description="Optional page where the feedback was submitted",
    )


class FeedbackResponse(BaseModel):
    """Response model for feedback data."""

    id: str = Field(..., description="Feedback entry ID")
    user_id: str = Field(..., description="User ID who submitted the feedback")
    type: FeedbackType = Field(..., description="Type of feedback")
    rating: FeedbackRating | None = Field(None, description="Rating for response feedback")
    message_id: str | None = Field(None, description="ID of the message (for response feedback)")
    comment: str | None = Field(None, description="Optional comment from user")
    page: str | None = Field(None, description="Page where feedback was submitted")
    created_at: datetime = Field(..., description="When the feedback was created")

    model_config = {"from_attributes": True}

    def to_dict(self) -> dict[str, object]:
        """Convert the feedback response to a dictionary.

        Returns:
            Dictionary representation of the feedback response.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type.value,
            "rating": self.rating.value if self.rating else None,
            "message_id": self.message_id,
            "comment": self.comment,
            "page": self.page,
            "created_at": self.created_at.isoformat(),
        }
