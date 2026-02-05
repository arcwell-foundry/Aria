"""Notification Pydantic models for ARIA.

This module contains all models related to user notifications.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationType(str, Enum):
    """Type of notification."""

    BRIEFING_READY = "briefing_ready"
    SIGNAL_DETECTED = "signal_detected"
    TASK_DUE = "task_due"
    MEETING_BRIEF_READY = "meeting_brief_ready"
    DRAFT_READY = "draft_ready"
    LEAD_SILENT = "lead_silent"
    LEAD_HEALTH_DROP = "lead_health_drop"


class NotificationCreate(BaseModel):
    """Request model for creating a new notification."""

    user_id: str = Field(..., description="User ID to receive the notification")
    type: NotificationType = Field(..., description="Type of notification")
    title: str = Field(..., description="Notification title")
    message: str | None = Field(None, description="Notification message")
    link: str | None = Field(None, description="Optional link to relevant resource")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class NotificationResponse(BaseModel):
    """Response model for notification data."""

    id: str = Field(..., description="Notification ID")
    user_id: str = Field(..., description="User ID who owns the notification")
    type: NotificationType = Field(..., description="Type of notification")
    title: str = Field(..., description="Notification title")
    message: str | None = Field(None, description="Notification message")
    link: str | None = Field(None, description="Link to relevant resource")
    metadata: dict[str, Any] = Field(..., description="Additional metadata")
    read_at: datetime | None = Field(None, description="When the notification was read")
    created_at: datetime = Field(..., description="When the notification was created")


class NotificationListResponse(BaseModel):
    """Response model for paginated list of notifications."""

    notifications: list[NotificationResponse] = Field(..., description="List of notifications")
    total: int = Field(..., description="Total count of notifications")
    unread_count: int = Field(..., description="Count of unread notifications")


class UnreadCountResponse(BaseModel):
    """Response model for unread notification count."""

    count: int = Field(..., description="Number of unread notifications")


class MarkReadRequest(BaseModel):
    """Request model for marking notifications as read."""

    notification_ids: list[str] | None = Field(
        None,
        description="List of specific notification IDs to mark as read. Null means mark all as read.",
    )
