"""Video-related Pydantic models for ARIA.

This module contains all models related to video sessions, including
Tavus integration and transcript entries.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class VideoSessionStatus(str, Enum):
    """Status of a video session."""

    CREATED = "created"
    ACTIVE = "active"
    ENDED = "ended"
    ERROR = "error"


class SessionType(str, Enum):
    """Type of video session."""

    CHAT = "chat"
    BRIEFING = "briefing"
    DEBRIEF = "debrief"
    CONSULTATION = "consultation"


class VideoSessionCreate(BaseModel):
    """Request model for creating a new video session."""

    session_type: SessionType = SessionType.CHAT
    context: str | None = None
    custom_greeting: str | None = None
    lead_id: str | None = None


class VideoSessionResponse(BaseModel):
    """Response model for video session data."""

    id: str
    user_id: str
    tavus_conversation_id: str
    room_url: str | None
    status: VideoSessionStatus
    session_type: SessionType
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    created_at: datetime
    lead_id: str | None = None
    perception_analysis: dict[str, Any] | None = None
    transcripts: list["TranscriptEntryResponse"] | None = None


class TranscriptEntryResponse(BaseModel):
    """Response model for transcript entry data."""

    id: str
    video_session_id: str
    speaker: str
    content: str
    timestamp_ms: int
    created_at: datetime


class VideoSessionListResponse(BaseModel):
    """Response model for paginated list of video sessions."""

    items: list[VideoSessionResponse]
    total: int
    limit: int
    offset: int


# Rebuild model to resolve forward reference
VideoSessionResponse.model_rebuild()
