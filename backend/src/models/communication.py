"""Communication routing models for ARIA.

This module contains all models related to communication surface orchestration.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessagePriority(str, Enum):
    """Priority level for routing messages to appropriate channels.

    CRITICAL: Urgent, time-sensitive - requires immediate attention
    IMPORTANT: Significant but not urgent - needs timely attention
    FYI: Informational - user should know but no action required
    BACKGROUND: Logging only - no notification needed
    """

    CRITICAL = "critical"  # push + in_app
    IMPORTANT = "important"  # email or slack (user preference)
    FYI = "fyi"  # in_app activity feed only
    BACKGROUND = "background"  # no notification, logged only


class ChannelType(str, Enum):
    """Available communication channels."""

    IN_APP = "in_app"  # NotificationService (US-931)
    EMAIL = "email"  # EmailService (US-934)
    SLACK = "slack"  # Composio Slack integration (future)
    PUSH = "push"  # Push notification (future)


class CommunicationRequest(BaseModel):
    """Request model for sending a routed communication."""

    user_id: str = Field(..., description="User ID to receive the message")
    message: str = Field(..., min_length=1, max_length=5000, description="Message content")
    priority: MessagePriority = Field(..., description="Message priority for routing")
    title: str | None = Field(None, max_length=200, description="Optional title/header")
    link: str | None = Field(None, max_length=500, description="Optional link to relevant resource")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    force_channels: list[ChannelType] | None = Field(
        None, description="Override routing - force specific channels"
    )


class ChannelResult(BaseModel):
    """Result of sending to a specific channel."""

    channel: ChannelType = Field(..., description="Channel used")
    success: bool = Field(..., description="Whether send succeeded")
    message_id: str | None = Field(None, description="ID of sent message (if applicable)")
    error: str | None = Field(None, description="Error message if failed")


class CommunicationResponse(BaseModel):
    """Response model for routed communication."""

    user_id: str = Field(..., description="User who received the communication")
    priority: MessagePriority = Field(..., description="Original message priority")
    channels_used: list[ChannelType] = Field(..., description="Channels actually used")
    results: dict[ChannelType, ChannelResult] = Field(
        ...,
        description="Result per channel attempted",
    )
