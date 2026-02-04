# US-415: Notification System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a complete in-app notification system with premium Apple-inspired UI design, backend API, database schema, and integration points across ARIA.

**Architecture:** Three-tier implementation: (1) Database layer with RLS-protected notifications table, (2) FastAPI backend with NotificationService and REST endpoints, (3) React frontend with NotificationBell component, dropdown panel, and real-time polling.

**Tech Stack:** PostgreSQL (Supabase), Python 3.11+ (FastAPI, Pydantic), React 18 (TypeScript, Tailwind CSS, React Query, Framer Motion)

---

## Task 1: Create Database Migration

**Files:**
- Create: `backend/supabase/migrations/20260203_create_notifications.sql`

**Step 1: Write the migration file**

```sql
-- ============================================
-- US-415: Notification System
-- ============================================

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('briefing_ready', 'signal_detected', 'task_due', 'meeting_brief_ready', 'draft_ready')),
    title TEXT NOT NULL,
    message TEXT,
    link TEXT,
    metadata JSONB DEFAULT '{}',
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for unread notifications query
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, created_at DESC) WHERE read_at IS NULL;

-- Index for user notifications list
CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC);

-- RLS Policies
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Users can read their own notifications
CREATE POLICY "Users can read own notifications"
    ON notifications FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own notifications (for system operations)
CREATE POLICY "Users can insert own notifications"
    ON notifications FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own notifications (mark read)
CREATE POLICY "Users can update own notifications"
    ON notifications FOR UPDATE
    USING (auth.uid() = user_id);

-- Users can delete their own notifications
CREATE POLICY "Users can delete own notifications"
    ON notifications FOR DELETE
    USING (auth.uid() = user_id);

-- Service role can insert notifications (for background jobs)
CREATE POLICY "Service role can insert notifications"
    ON notifications FOR INSERT
    TO service_role
    WITH CHECK (true);

-- Notification preferences in user_settings
-- Add notification preferences column if not exists
ALTER TABLE user_settings
    ADD COLUMN IF NOT EXISTS notification_preferences JSONB DEFAULT '{
        "in_app_enabled": true,
        "email_enabled": false,
        "briefing_ready": true,
        "signal_detected": true,
        "task_due": true,
        "meeting_brief_ready": true,
        "draft_ready": true
    }'::jsonb;
```

**Step 2: Run the migration**

Run: `npx supabase migration up` or apply via Supabase dashboard
Expected: Table created with indexes and RLS policies

**Step 3: Verify the schema**

Run: `psql -c "\d notifications"` via Supabase SQL editor
Expected: Table structure matches schema

**Step 4: Commit**

```bash
git add backend/supabase/migrations/20260203_create_notifications.sql
git commit -m "feat(db): add notifications table with RLS policies"
```

---

## Task 2: Create Pydantic Models

**Files:**
- Create: `backend/src/models/notification.py`
- Modify: `backend/src/models/__init__.py`

**Step 1: Write the notification models**

```python
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


class NotificationCreate(BaseModel):
    """Request model for creating a notification (internal use)."""

    user_id: str = Field(..., description="User ID to receive notification")
    type: NotificationType = Field(..., description="Type of notification")
    title: str = Field(..., description="Notification title")
    message: str | None = Field(None, description="Notification message/body")
    link: str | None = Field(None, description="Link to navigate when clicked")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional data")


class NotificationResponse(BaseModel):
    """Response model for notification data."""

    id: str = Field(..., description="Notification ID")
    user_id: str = Field(..., description="User ID")
    type: NotificationType = Field(..., description="Notification type")
    title: str = Field(..., description="Notification title")
    message: str | None = Field(None, description="Notification message")
    link: str | None = Field(None, description="Navigation link")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional data")
    read_at: datetime | None = Field(None, description="When marked as read")
    created_at: datetime = Field(..., description="When notification was created")


class NotificationListResponse(BaseModel):
    """Response model for paginated notification list."""

    notifications: list[NotificationResponse] = Field(default_factory=list)
    total: int = Field(..., description="Total count")
    unread_count: int = Field(..., description="Unread count")


class UnreadCountResponse(BaseModel):
    """Response model for unread count."""

    count: int = Field(..., description="Number of unread notifications")


class MarkReadRequest(BaseModel):
    """Request model for marking notifications as read."""

    notification_ids: list[str] | None = Field(
        None, description="Specific notification IDs, or null for all"
    )
```

**Step 2: Export models from __init__.py**

Add to `backend/src/models/__init__.py`:

```python
from src.models.notification import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    NotificationType,
    UnreadCountResponse,
)
```

**Step 3: Run type check**

Run: `cd backend && mypy src/models/notification.py --strict`
Expected: PASS or only expected errors

**Step 4: Commit**

```bash
git add backend/src/models/notification.py backend/src/models/__init__.py
git commit -m "feat(models): add notification Pydantic models"
```

---

## Task 3: Create NotificationService

**Files:**
- Create: `backend/src/services/notification_service.py`
- Modify: `backend/src/services/__init__.py`

**Step 1: Write the NotificationService**

```python
"""Notification service for ARIA.

This service handles creating, retrieving, and managing user notifications.
It also handles sending email notifications when user preferences allow.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from src.db.supabase import SupabaseClient
from src.core.exceptions import DatabaseError, NotFoundError
from src.models.notification import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    NotificationType,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing user notifications."""

    @staticmethod
    async def create_notification(
        user_id: str,
        type: NotificationType,
        title: str,
        message: str | None = None,
        link: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationResponse:
        """Create a new notification for a user.

        Args:
            user_id: The user's UUID.
            type: Type of notification.
            title: Notification title.
            message: Optional message body.
            link: Optional navigation link.
            metadata: Optional additional data.

        Returns:
            Created notification.

        Raises:
            DatabaseError: If creation fails.
        """
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "type": type.value,
                "title": title,
                "message": message,
                "link": link,
                "metadata": metadata or {},
            }
            response = client.table("notifications").insert(data).execute()
            if response.data and len(response.data) > 0:
                logger.info(
                    "Notification created",
                    extra={"user_id": user_id, "type": type.value, "notification_id": response.data[0]["id"]},
                )
                return NotificationResponse(**response.data[0])
            raise DatabaseError("Failed to create notification")
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Error creating notification", extra={"user_id": user_id, "type": type.value})
            raise DatabaseError(f"Failed to create notification: {e}") from e

    @staticmethod
    async def get_notifications(
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> NotificationListResponse:
        """Get notifications for a user with pagination.

        Args:
            user_id: The user's UUID.
            limit: Max number of notifications to return.
            offset: Pagination offset.
            unread_only: If True, only return unread notifications.

        Returns:
            Paginated notification list with counts.

        Raises:
            DatabaseError: If query fails.
        """
        try:
            client = SupabaseClient.get_client()
            query = client.table("notifications").select("*", count="exact").eq("user_id", user_id)

            if unread_only:
                query = query.is_("read_at", "null")

            query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
            response = query.execute()

            # Get unread count
            count_response = (
                client.table("notifications")
                .select("*", count="exact")
                .eq("user_id", user_id)
                .is_("read_at", "null")
                .execute()
            )
            unread_count = count_response.count or 0

            notifications = [NotificationResponse(**item) for item in response.data or []]

            return NotificationListResponse(
                notifications=notifications,
                total=response.count or 0,
                unread_count=unread_count,
            )
        except Exception as e:
            logger.exception("Error fetching notifications", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch notifications: {e}") from e

    @staticmethod
    async def get_unread_count(user_id: str) -> UnreadCountResponse:
        """Get the count of unread notifications for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Unread count.

        Raises:
            DatabaseError: If query fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications")
                .select("*", count="exact")
                .eq("user_id", user_id)
                .is_("read_at", "null")
                .execute()
            )
            return UnreadCountResponse(count=response.count or 0)
        except Exception as e:
            logger.exception("Error fetching unread count", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch unread count: {e}") from e

    @staticmethod
    async def mark_as_read(notification_id: str, user_id: str) -> NotificationResponse:
        """Mark a single notification as read.

        Args:
            notification_id: The notification UUID.
            user_id: The user's UUID (for authorization).

        Returns:
            Updated notification.

        Raises:
            NotFoundError: If notification not found.
            DatabaseError: If update fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications")
                .update({"read_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", notification_id)
                .eq("user_id", user_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return NotificationResponse(**response.data[0])
            raise NotFoundError("Notification", notification_id)
        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error marking notification as read", extra={"notification_id": notification_id})
            raise DatabaseError(f"Failed to mark notification as read: {e}") from e

    @staticmethod
    async def mark_all_as_read(user_id: str) -> int:
        """Mark all notifications as read for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Number of notifications marked as read.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications")
                .update({"read_at": datetime.now(timezone.utc).isoformat()})
                .eq("user_id", user_id)
                .is_("read_at", "null")
                .execute()
            )
            count = len(response.data or [])
            logger.info("Marked all notifications as read", extra={"user_id": user_id, "count": count})
            return count
        except Exception as e:
            logger.exception("Error marking all as read", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to mark all notifications as read: {e}") from e

    @staticmethod
    async def delete_notification(notification_id: str, user_id: str) -> None:
        """Delete a notification.

        Args:
            notification_id: The notification UUID.
            user_id: The user's UUID (for authorization).

        Raises:
            NotFoundError: If notification not found.
            DatabaseError: If deletion fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications").delete().eq("id", notification_id).eq("user_id", user_id).execute()
            )
            if not response.data or len(response.data) == 0:
                raise NotFoundError("Notification", notification_id)
            logger.info("Notification deleted", extra={"notification_id": notification_id, "user_id": user_id})
        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error deleting notification", extra={"notification_id": notification_id})
            raise DatabaseError(f"Failed to delete notification: {e}") from e
```

**Step 2: Export service from __init__.py**

Add to `backend/src/services/__init__.py`:

```python
from src.services.notification_service import NotificationService
```

**Step 3: Run type check**

Run: `cd backend && mypy src/services/notification_service.py --strict`
Expected: PASS or only expected errors

**Step 4: Commit**

```bash
git add backend/src/services/notification_service.py backend/src/services/__init__.py
git commit -m "feat(service): add NotificationService with CRUD operations"
```

---

## Task 4: Create Notification API Routes

**Files:**
- Create: `backend/src/api/routes/notifications.py`
- Modify: `backend/src/api/routes/__init__.py`
- Modify: `backend/src/main.py`

**Step 1: Write the notification routes**

```python
"""Notification API routes for ARIA."""

import logging

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from src.api.routes.auth import get_current_user
from src.models.notification import (
    MarkReadRequest,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(20, ge=1, le=100, description="Max notifications to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    unread_only: bool = Query(False, description="Only return unread"),
    current_user: dict = Depends(get_current_user),
) -> NotificationListResponse:
    """List notifications for the current user.

    Returns paginated list of notifications ordered by creation date (newest first).
    Includes total count and unread count.
    """
    user_id = current_user["id"]
    return await NotificationService.get_notifications(
        user_id=user_id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )


@router.get("/unread/count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: dict = Depends(get_current_user),
) -> UnreadCountResponse:
    """Get the count of unread notifications."""
    user_id = current_user["id"]
    return await NotificationService.get_unread_count(user_id=user_id)


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
) -> NotificationResponse:
    """Mark a single notification as read."""
    user_id = current_user["id"]
    return await NotificationService.mark_as_read(notification_id=notification_id, user_id=user_id)


@router.put("/read-all")
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Mark all notifications as read for the current user."""
    user_id = current_user["id"]
    count = await NotificationService.mark_all_as_read(user_id=user_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Marked {count} notifications as read", "count": count},
    )


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Delete a notification."""
    user_id = current_user["id"]
    await NotificationService.delete_notification(notification_id=notification_id, user_id=user_id)
```

**Step 2: Register router in __init__.py**

Modify `backend/src/api/routes/__init__.py`:

```python
"""API route handlers for ARIA."""

from src.api.routes import drafts, notifications
```

**Step 3: Register router in main.py**

Add to `backend/src/main.py` (find where other routers are registered):

```python
from src.api.routes import notifications
app.include_router(notifications.router, prefix="/api/v1")
```

**Step 4: Test the endpoints manually**

Run: `cd backend && uvicorn src.main:app --reload --port 8000`

Test: `curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/notifications`
Expected: JSON response with empty notifications array

**Step 5: Commit**

```bash
git add backend/src/api/routes/notifications.py backend/src/api/routes/__init__.py backend/src/main.py
git commit -m "feat(api): add notifications API endpoints"
```

---

## Task 5: Write NotificationService Tests

**Files:**
- Create: `backend/tests/test_notification_service.py`

**Step 1: Write failing test for create_notification**

```python
"""Tests for NotificationService."""

import pytest

from src.models.notification import NotificationType
from src.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_create_notification(db_client, test_user_id):
    """Test creating a notification."""
    notification = await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.SIGNAL_DETECTED,
        title="New Signal Detected",
        message="Acme Corp just raised Series B",
        link="/leads/acme-corp",
        metadata={"company": "Acme Corp"},
    )

    assert notification.id is not None
    assert notification.user_id == test_user_id
    assert notification.type == NotificationType.SIGNAL_DETECTED
    assert notification.title == "New Signal Detected"
    assert notification.message == "Acme Corp just raised Series B"
    assert notification.link == "/leads/acme-corp"
    assert notification.metadata["company"] == "Acme Corp"
    assert notification.read_at is None
    assert notification.created_at is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_notification_service.py::test_create_notification -v`
Expected: FAIL (service not yet connected to test database)

**Step 3: Set up test fixtures**

Add to `backend/tests/conftest.py`:

```python
@pytest.fixture
async def test_user_id(db_client):
    """Create a test user and return its ID."""
    from src.db.supabase import SupabaseClient

    client = SupabaseClient.get_client()
    # Create or use existing test user
    user_data = {
        "id": "00000000-0000-0000-0000-000000000001",
        "full_name": "Test User",
        "email": "test@example.com",
    }
    try:
        client.table("user_profiles").insert(user_data).execute()
    except Exception:
        pass  # User may already exist
    return user_data["id"]
```

**Step 4: Run test again**

Run: `cd backend && pytest tests/test_notification_service.py::test_create_notification -v`
Expected: PASS

**Step 5: Write remaining service tests**

Add to `backend/tests/test_notification_service.py`:

```python
@pytest.mark.asyncio
async def test_get_notifications(db_client, test_user_id):
    """Test retrieving notifications."""
    # Create test notifications
    await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.BRIEFING_READY,
        title="Briefing Ready",
    )
    await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.TASK_DUE,
        title="Task Due",
    )

    result = await NotificationService.get_notifications(user_id=test_user_id, limit=10)

    assert len(result.notifications) >= 2
    assert result.total >= 2
    assert result.unread_count >= 2
    # Verify ordering (newest first)
    assert result.notifications[0].created_at >= result.notifications[1].created_at


@pytest.mark.asyncio
async def test_get_unread_count(db_client, test_user_id):
    """Test getting unread count."""
    await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.DRAFT_READY,
        title="Draft Ready",
    )

    result = await NotificationService.get_unread_count(user_id=test_user_id)

    assert result.count >= 1


@pytest.mark.asyncio
async def test_mark_as_read(db_client, test_user_id):
    """Test marking a notification as read."""
    notification = await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.MEETING_BRIEF_READY,
        title="Meeting Brief Ready",
    )

    updated = await NotificationService.mark_as_read(
        notification_id=notification.id,
        user_id=test_user_id,
    )

    assert updated.read_at is not None
    assert updated.id == notification.id


@pytest.mark.asyncio
async def test_mark_all_as_read(db_client, test_user_id):
    """Test marking all notifications as read."""
    # Create multiple unread notifications
    for i in range(3):
        await NotificationService.create_notification(
            user_id=test_user_id,
            type=NotificationType.SIGNAL_DETECTED,
            title=f"Signal {i}",
        )

    count = await NotificationService.mark_all_as_read(user_id=test_user_id)

    assert count >= 3

    # Verify all are read
    unread = await NotificationService.get_unread_count(user_id=test_user_id)
    assert unread.count == 0


@pytest.mark.asyncio
async def test_delete_notification(db_client, test_user_id):
    """Test deleting a notification."""
    notification = await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.BRIEFING_READY,
        title="To be deleted",
    )

    await NotificationService.delete_notification(
        notification_id=notification.id,
        user_id=test_user_id,
    )

    # Verify it's gone
    result = await NotificationService.get_notifications(user_id=test_user_id)
    notification_ids = [n.id for n in result.notifications]
    assert notification.id not in notification_ids


@pytest.mark.asyncio
async def test_unread_only_filter(db_client, test_user_id):
    """Test filtering for unread notifications only."""
    # Create notification and mark as read
    notification = await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.TASK_DUE,
        title="Task",
    )
    await NotificationService.mark_as_read(notification.id, test_user_id)

    # Create another unread
    await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.SIGNAL_DETECTED,
        title="Signal",
    )

    result = await NotificationService.get_notifications(
        user_id=test_user_id,
        unread_only=True,
    )

    assert all(n.read_at is None for n in result.notifications)
    assert len(result.notifications) >= 1
```

**Step 6: Run all tests**

Run: `cd backend && pytest tests/test_notification_service.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add backend/tests/test_notification_service.py backend/tests/conftest.py
git commit -m "test: add NotificationService unit tests"
```

---

## Task 6: Write API Integration Tests

**Files:**
- Create: `backend/tests/test_notifications_api.py`

**Step 1: Write API integration tests**

```python
"""Tests for notification API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers(test_user_token):
    """Create auth headers for requests."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.mark.asyncio
async def test_list_notifications_empty(client, auth_headers):
    """Test listing notifications when empty."""
    response = client.get("/api/v1/notifications", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "notifications" in data
    assert data["notifications"] == []
    assert data["total"] == 0
    assert data["unread_count"] == 0


@pytest.mark.asyncio
async def test_list_notifications_with_data(client, auth_headers, test_user_id):
    """Test listing notifications with data."""
    # Create a notification via service
    from src.services.notification_service import NotificationService
    from src.models.notification import NotificationType

    await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.SIGNAL_DETECTED,
        title="Test Signal",
    )

    response = client.get("/api/v1/notifications", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) >= 1
    assert data["notifications"][0]["title"] == "Test Signal"


@pytest.mark.asyncio
async def test_get_unread_count(client, auth_headers, test_user_id):
    """Test getting unread count endpoint."""
    response = client.get("/api/v1/notifications/unread/count", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert isinstance(data["count"], int)


@pytest.mark.asyncio
async def test_mark_notification_read(client, auth_headers, test_user_id):
    """Test marking a notification as read."""
    from src.services.notification_service import NotificationService
    from src.models.notification import NotificationType

    notification = await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.TASK_DUE,
        title="Test Task",
    )

    response = client.put(f"/api/v1/notifications/{notification.id}/read", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["read_at"] is not None


@pytest.mark.asyncio
async def test_mark_all_read(client, auth_headers, test_user_id):
    """Test marking all notifications as read."""
    from src.services.notification_service import NotificationService
    from src.models.notification import NotificationType

    # Create multiple notifications
    for i in range(3):
        await NotificationService.create_notification(
            user_id=test_user_id,
            type=NotificationType.SIGNAL_DETECTED,
            title=f"Signal {i}",
        )

    response = client.put("/api/v1/notifications/read-all", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert data["count"] >= 3


@pytest.mark.asyncio
async def test_delete_notification(client, auth_headers, test_user_id):
    """Test deleting a notification."""
    from src.services.notification_service import NotificationService
    from src.models.notification import NotificationType

    notification = await NotificationService.create_notification(
        user_id=test_user_id,
        type=NotificationType.BRIEFING_READY,
        title="To delete",
    )

    response = client.delete(f"/api/v1/notifications/{notification.id}", headers=auth_headers)

    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get("/api/v1/notifications", headers=auth_headers)
    notification_ids = [n["id"] for n in get_response.json()["notifications"]]
    assert notification.id not in notification_ids


@pytest.mark.asyncio
async def test_pagination(client, auth_headers, test_user_id):
    """Test notification pagination."""
    from src.services.notification_service import NotificationService
    from src.models.notification import NotificationType

    # Create multiple notifications
    for i in range(5):
        await NotificationService.create_notification(
            user_id=test_user_id,
            type=NotificationType.SIGNAL_DETECTED,
            title=f"Signal {i}",
        )

    # Get first page
    response = client.get("/api/v1/notifications?limit=2&offset=0", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) == 2
    assert data["total"] >= 5

    # Get second page
    response = client.get("/api/v1/notifications?limit=2&offset=2", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) == 2


@pytest.mark.asyncio
async def test_unauthorized_access(client):
    """Test that unauthorized requests are rejected."""
    response = client.get("/api/v1/notifications")
    assert response.status_code == 401
```

**Step 2: Run tests**

Run: `cd backend && pytest tests/test_notifications_api.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add backend/tests/test_notifications_api.py
git commit -m "test: add notification API integration tests"
```

---

## Task 7: Create Frontend API Client

**Files:**
- Create: `frontend/src/api/notifications.ts`

**Step 1: Write the notification API client**

```typescript
import { apiClient } from "./client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

// Types
export type NotificationType =
  | "briefing_ready"
  | "signal_detected"
  | "task_due"
  | "meeting_brief_ready"
  | "draft_ready";

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  message: string | null;
  link: string | null;
  metadata: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: Notification[];
  total: number;
  unread_count: number;
}

export interface UnreadCountResponse {
  count: number;
}

// API functions
export async function getNotifications(params: {
  limit?: number;
  offset?: number;
  unreadOnly?: boolean;
}): Promise<NotificationListResponse> {
  const { limit = 20, offset = 0, unreadOnly = false } = params;
  const response = await apiClient.get<NotificationListResponse>("/notifications", {
    params: { limit, offset, unread_only: unreadOnly },
  });
  return response.data;
}

export async function getUnreadCount(): Promise<UnreadCountResponse> {
  const response = await apiClient.get<UnreadCountResponse>("/notifications/unread/count");
  return response.data;
}

export async function markAsRead(notificationId: string): Promise<Notification> {
  const response = await apiClient.put<Notification>(`/notifications/${notificationId}/read`);
  return response.data;
}

export async function markAllAsRead(): Promise<{ message: string; count: number }> {
  const response = await apiClient.put("/notifications/read-all");
  return response.data;
}

export async function deleteNotification(notificationId: string): Promise<void> {
  await apiClient.delete(`/notifications/${notificationId}`);
}

// React Query hooks
export function useNotifications(params: { limit?: number; offset?: number; unreadOnly?: boolean } = {}) {
  return useQuery({
    queryKey: ["notifications", params],
    queryFn: () => getNotifications(params),
    refetchInterval: 30000, // Poll every 30 seconds
    staleTime: 10000, // Consider data fresh for 10 seconds
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => getUnreadCount(),
    refetchInterval: 30000, // Poll every 30 seconds
    staleTime: 5000,
  });
}

export function useMarkAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markAsRead,
    onSuccess: () => {
      // Invalidate and refetch notifications and unread count
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markAllAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useDeleteNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteNotification,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/api/notifications.ts
git commit -m "feat(api): add notification API client and React Query hooks"
```

---

## Task 8: Create Notification Bell Component

**Files:**
- Create: `frontend/src/components/notifications/NotificationBell.tsx`

**DESIGN DIRECTION: Apple-inspired luxury notification bell**
- Premium bell icon with refined unread badge (subtle accent color, not jarring red)
- Smooth slide + fade dropdown animation
- Clean, spacious notification items with type icons
- Hover states with subtle background changes
- "Mark all as read" link at top
- Click outside to close
- Portal rendering for proper z-index

**Step 1: Write the NotificationBell component**

```typescript
import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useUnreadCount, useNotifications, useMarkAsRead, useMarkAllAsRead } from "@/api/notifications";
import { Bell, X, Check } from "lucide-react";

// Type-specific icons
const NotificationIcons: Record<string, React.ReactNode> = {
  briefing_ready: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M14.5 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7.5L14.5 2z" />
      <path d="M14 2v6h6" />
    </svg>
  ),
  signal_detected: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M12 20V10" />
      <path d="M18 20V4" />
      <path d="M6 20v-4" />
    </svg>
  ),
  task_due: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
    </svg>
  ),
  meeting_brief_ready: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M17 21v-2a2 2 0 00-2-2H5a2 2 0 00-2 2v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a2 2 0 00-2-2-2 2 0 01-2-2" />
      <path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  draft_ready: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <polyline points="22,6 12,13 2,6" />
    </svg>
  ),
};

// Color classes by type
const TypeColors: Record<string, string> = {
  briefing_ready: "text-blue-400",
  signal_detected: "text-amber-400",
  task_due: "text-rose-400",
  meeting_brief_ready: "text-emerald-400",
  draft_ready: "text-violet-400",
};

// Time ago formatter
function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const { data: unreadData } = useUnreadCount();
  const { data: notificationsData } = useNotifications({ limit: 10 });
  const markAsRead = useMarkAsRead();
  const markAllAsRead = useMarkAllAsRead();

  const unreadCount = unreadData?.count ?? 0;
  const notifications = notificationsData?.notifications ?? [];

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isOpen]);

  const handleNotificationClick = async (notification: Notification) => {
    if (!notification.read_at) {
      await markAsRead.mutateAsync(notification.id);
    }
    if (notification.link) {
      navigate(notification.link);
      setIsOpen(false);
    }
  };

  const handleMarkAllRead = async () => {
    await markAllAsRead.mutateAsync();
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Bell button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2.5 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
      >
        <Bell className="w-5 h-5" />
        {/* Unread badge */}
        {unreadCount > 0 && (
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-primary-500 rounded-full animate-pulse" />
        )}
      </button>

      {/* Dropdown panel */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-96 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden z-50 animate-in slide-in-from-top-2 fade-in duration-200">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
            <div>
              <h3 className="text-sm font-semibold text-white">Notifications</h3>
              {unreadCount > 0 && (
                <p className="text-xs text-slate-400 mt-0.5">{unreadCount} unread</p>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                disabled={markAllAsRead.isPending}
                className="text-xs text-primary-400 hover:text-primary-300 disabled:opacity-50 transition-colors"
              >
                Mark all read
              </button>
            )}
          </div>

          {/* Notifications list */}
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="px-4 py-12 text-center">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-slate-700/50 mb-3">
                  <Bell className="w-6 h-6 text-slate-500" />
                </div>
                <p className="text-sm text-slate-400">No notifications yet</p>
                <p className="text-xs text-slate-500 mt-1">We'll notify you when something important happens</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-700/50">
                {notifications.map((notification) => {
                  const isUnread = !notification.read_at;
                  return (
                    <button
                      key={notification.id}
                      onClick={() => handleNotificationClick(notification)}
                      disabled={!notification.link}
                      className={`w-full px-4 py-3 text-left transition-colors ${
                        isUnread
                          ? "bg-slate-700/30 hover:bg-slate-700/50"
                          : "bg-transparent hover:bg-slate-700/30"
                      } disabled:opacity-60 disabled:hover:bg-transparent`}
                    >
                      <div className="flex gap-3">
                        {/* Type icon */}
                        <div
                          className={`flex-shrink-0 mt-0.5 ${
                            TypeColors[notification.type] || "text-slate-400"
                          }`}
                        >
                          {NotificationIcons[notification.type] || NotificationIcons.briefing_ready}
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <p
                              className={`text-sm font-medium truncate ${
                                isUnread ? "text-white" : "text-slate-300"
                              }`}
                            >
                              {notification.title}
                            </p>
                            {isUnread && (
                              <span className="flex-shrink-0 w-2 h-2 rounded-full bg-primary-500 mt-1.5" />
                            )}
                          </div>
                          {notification.message && (
                            <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">
                              {notification.message}
                            </p>
                          )}
                          <p className="text-xs text-slate-500 mt-1.5">
                            {timeAgo(notification.created_at)}
                          </p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer - View all link */}
          {notifications.length > 0 && (
            <div className="px-4 py-2 border-t border-slate-700 bg-slate-800/50">
              <button
                onClick={() => {
                  navigate("/notifications");
                  setIsOpen(false);
                }}
                className="w-full text-center text-xs text-slate-400 hover:text-white transition-colors py-1"
              >
                View all notifications
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/notifications/NotificationBell.tsx
git commit -m "feat(ui): add NotificationBell component with dropdown"
```

---

## Task 9: Create Notifications List Page

**Files:**
- Create: `frontend/src/components/notifications/NotificationsPage.tsx`
- Create: `frontend/src/pages/NotificationsPage.tsx`

**Step 1: Write the NotificationsPage component**

```typescript
import { useNavigate } from "react-router-dom";
import { useNotifications, useDeleteNotification, useMarkAsRead } from "@/api/notifications";
import { Trash2, Check } from "lucide-react";

// Shared time formatter and icons from NotificationBell
function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const NotificationIcons: Record<string, React.ReactNode> = {
  briefing_ready: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M14.5 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7.5L14.5 2z" />
      <path d="M14 2v6h6" />
    </svg>
  ),
  signal_detected: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M12 20V10" />
      <path d="M18 20V4" />
      <path d="M6 20v-4" />
    </svg>
  ),
  task_due: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
    </svg>
  ),
  meeting_brief_ready: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M17 21v-2a2 2 0 00-2-2H5a2 2 0 00-2 2v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a2 2 0 00-2-2-2 2 0 01-2-2" />
      <path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  draft_ready: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <polyline points="22,6 12,13 2,6" />
    </svg>
  ),
};

const TypeColors: Record<string, string> = {
  briefing_ready: "text-blue-400 bg-blue-400/10",
  signal_detected: "text-amber-400 bg-amber-400/10",
  task_due: "text-rose-400 bg-rose-400/10",
  meeting_brief_ready: "text-emerald-400 bg-emerald-400/10",
  draft_ready: "text-violet-400 bg-violet-400/10",
};

export function NotificationsPageContent() {
  const navigate = useNavigate();
  const { data: notificationsData, isLoading } = useNotifications({ limit: 100 });
  const deleteNotification = useDeleteNotification();
  const markAsRead = useMarkAsRead();

  const notifications = notificationsData?.notifications ?? [];

  const handleNotificationClick = async (notification: any) => {
    if (!notification.read_at) {
      await markAsRead.mutateAsync(notification.id);
    }
    if (notification.link) {
      navigate(notification.link);
    }
  };

  const handleDelete = async (e: React.MouseEvent, notificationId: string) => {
    e.stopPropagation();
    if (confirm("Delete this notification?")) {
      await deleteNotification.mutateAsync(notificationId);
    }
  };

  const handleMarkRead = async (e: React.MouseEvent, notification: any) => {
    e.stopPropagation();
    if (!notification.read_at) {
      await markAsRead.mutateAsync(notification.id);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
          <p className="mt-4 text-slate-400">Loading notifications...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Notifications</h1>
        <p className="mt-2 text-slate-400">
          {notificationsData?.unread_count ?? 0} unread notification
          {notificationsData?.unread_count !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Notifications list */}
      {notifications.length === 0 ? (
        <div className="text-center py-16">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800 mb-4">
            <svg className="w-8 h-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white">No notifications yet</h3>
          <p className="mt-2 text-slate-400">
            We'll notify you when something important happens
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {notifications.map((notification) => {
            const isUnread = !notification.read_at;
            return (
              <div
                key={notification.id}
                className={`group relative p-4 rounded-xl border transition-all ${
                  isUnread
                    ? "bg-slate-800 border-slate-700 shadow-sm"
                    : "bg-slate-800/50 border-slate-700/50"
                }`}
              >
                <div
                  onClick={() => notification.link && handleNotificationClick(notification)}
                  className={`flex gap-4 ${notification.link ? "cursor-pointer" : ""}`}
                >
                  {/* Type icon */}
                  <div
                    className={`flex-shrink-0 flex items-center justify-center w-12 h-12 rounded-xl ${
                      TypeColors[notification.type] || "text-slate-400 bg-slate-700"
                    }`}
                  >
                    {NotificationIcons[notification.type] || NotificationIcons.briefing_ready}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <p
                          className={`text-sm font-medium ${
                            isUnread ? "text-white" : "text-slate-300"
                          }`}
                        >
                          {notification.title}
                        </p>
                        {notification.message && (
                          <p className="text-sm text-slate-400 mt-1">{notification.message}</p>
                        )}
                        <p className="text-xs text-slate-500 mt-2">{timeAgo(notification.created_at)}</p>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {isUnread && (
                          <button
                            onClick={(e) => handleMarkRead(e, notification)}
                            className="p-2 text-slate-400 hover:text-primary-400 hover:bg-slate-700 rounded-lg transition-colors"
                            title="Mark as read"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={(e) => handleDelete(e, notification.id)}
                          className="p-2 text-slate-400 hover:text-rose-400 hover:bg-slate-700 rounded-lg transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Unread indicator */}
                {isUnread && (
                  <div className="absolute left-0 top-4 bottom-4 w-1 bg-primary-500 rounded-r-full" />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Create the page wrapper**

```typescript
import { DashboardLayout } from "@/components/DashboardLayout";
import { NotificationsPageContent } from "@/components/notifications/NotificationsPageContent";

export function NotificationsPage() {
  return (
    <DashboardLayout>
      <div className="p-6 lg:p-8">
        <NotificationsPageContent />
      </div>
    </DashboardLayout>
  );
}
```

**Step 3: Add route to App.tsx**

Add to your routing configuration:

```typescript
import { NotificationsPage } from "@/pages/NotificationsPage";

// Add route:
<Route path="/notifications" element={<ProtectedRoute><NotificationsPage /></ProtectedRoute>} />
```

**Step 4: Run type check**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/notifications/NotificationsPage.tsx frontend/src/pages/NotificationsPage.tsx
git commit -m "feat(ui): add NotificationsPage with full list view"
```

---

## Task 10: Add NotificationBell to DashboardLayout

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`

**Step 1: Import and add NotificationBell to header**

Add import:
```typescript
import { NotificationBell } from "@/components/notifications/NotificationBell";
```

Add to header (before user avatar, around line 243):

```typescript
<div className="flex items-center gap-4 ml-auto">
  <NotificationBell />
  <div className="flex items-center gap-3">
    {/* ... existing user avatar and logout ... */}
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/DashboardLayout.tsx
git commit -m "feat(ui): add NotificationBell to DashboardLayout header"
```

---

## Task 11: Create Notification Integration Helper

**Files:**
- Create: `backend/src/services/notification_integration.py`

**Step 1: Write the notification integration helper**

```python
"""Notification integration helper for ARIA services.

This module provides a convenient interface for other services to create notifications.
"""

import logging

from src.models.notification import NotificationType
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def notify_briefing_ready(user_id: str, briefing_date: str) -> None:
    """Notify user that their daily briefing is ready.

    Args:
        user_id: The user's UUID.
        briefing_date: The briefing date (YYYY-MM-DD).
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.BRIEFING_READY,
            title="Daily Briefing Ready",
            message=f"Your briefing for {briefing_date} is ready to view.",
            link="/briefing",
            metadata={"briefing_date": briefing_date},
        )
        logger.info("Briefing ready notification created", extra={"user_id": user_id})
    except Exception as e:
        logger.error("Failed to create briefing notification", extra={"user_id": user_id, "error": str(e)})


async def notify_signal_detected(
    user_id: str,
    company_name: str,
    signal_type: str,
    headline: str,
    lead_id: str | None = None,
) -> None:
    """Notify user about a detected market signal.

    Args:
        user_id: The user's UUID.
        company_name: Name of the company.
        signal_type: Type of signal.
        headline: Signal headline.
        lead_id: Optional linked lead memory ID.
    """
    try:
        link = f"/leads/{lead_id}" if lead_id else "/leads"
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.SIGNAL_DETECTED,
            title=f"Signal Detected: {company_name}",
            message=headline,
            link=link,
            metadata={"company": company_name, "signal_type": signal_type, "lead_id": lead_id},
        )
        logger.info(
            "Signal detected notification created",
            extra={"user_id": user_id, "company": company_name},
        )
    except Exception as e:
        logger.error("Failed to create signal notification", extra={"user_id": user_id, "error": str(e)})


async def notify_task_due(user_id: str, task_title: str, task_id: str, due_date: str) -> None:
    """Notify user about a task due soon.

    Args:
        user_id: The user's UUID.
        task_title: Title of the task.
        task_id: The task's UUID.
        due_date: Due date string.
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.TASK_DUE,
            title=f"Task Due: {task_title}",
            message=f"This task is due on {due_date}",
            link=f"/goals?task={task_id}",
            metadata={"task_id": task_id, "due_date": due_date},
        )
        logger.info("Task due notification created", extra={"user_id": user_id, "task_id": task_id})
    except Exception as e:
        logger.error("Failed to create task notification", extra={"user_id": user_id, "error": str(e)})


async def notify_meeting_brief_ready(user_id: str, meeting_title: str, calendar_event_id: str) -> None:
    """Notify user that a meeting brief is ready.

    Args:
        user_id: The user's UUID.
        meeting_title: Title of the meeting.
        calendar_event_id: Calendar event ID.
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.MEETING_BRIEF_READY,
            title=f"Meeting Brief Ready: {meeting_title}",
            message="Your pre-meeting research brief has been generated.",
            link=f"/meeting-brief/{calendar_event_id}",
            metadata={"meeting_title": meeting_title, "calendar_event_id": calendar_event_id},
        )
        logger.info(
            "Meeting brief ready notification created",
            extra={"user_id": user_id, "event_id": calendar_event_id},
        )
    except Exception as e:
        logger.error(
            "Failed to create meeting brief notification",
            extra={"user_id": user_id, "error": str(e)},
        )


async def notify_draft_ready(
    user_id: str,
    draft_type: str,
    recipient: str,
    draft_id: str,
) -> None:
    """Notify user that an email draft is ready.

    Args:
        user_id: The user's UUID.
        draft_type: Type of draft (e.g., "follow_up", "intro").
        recipient: Recipient email/name.
        draft_id: The draft's UUID.
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.DRAFT_READY,
            title=f"Email Draft Ready",
            message=f"Your {draft_type} draft to {recipient} is ready for review.",
            link=f"/drafts/{draft_id}",
            metadata={"draft_id": draft_id, "draft_type": draft_type, "recipient": recipient},
        )
        logger.info("Draft ready notification created", extra={"user_id": user_id, "draft_id": draft_id})
    except Exception as e:
        logger.error("Failed to create draft notification", extra={"user_id": user_id, "error": str(e)})
```

**Step 2: Export from services __init__.py**

Add to `backend/src/services/__init__.py`:

```python
from src.services import notification_integration
```

**Step 3: Run type check**

Run: `cd backend && mypy src/services/notification_integration.py --strict`
Expected: PASS

**Step 4: Commit**

```bash
git add backend/src/services/notification_integration.py backend/src/services/__init__.py
git commit -m "feat(service): add notification integration helper functions"
```

---

## Task 12: Integrate Notifications into Briefing Service

**Files:**
- Modify: `backend/src/services/briefing.py`

**Step 1: Add notification when briefing is generated**

Find where briefing is generated/created and add:

```python
from src.services.notification_integration import notify_briefing_ready

# After briefing is successfully generated/created:
await notify_briefing_ready(user_id=user_id, briefing_date=briefing_date.isoformat())
```

**Step 2: Run type check**

Run: `cd backend && mypy src/services/briefing.py --strict`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/src/services/briefing.py
git commit -m "feat(briefing): add notification when daily briefing is ready"
```

---

## Task 13: Integrate Notifications into Signal Service

**Files:**
- Modify: `backend/src/services/signal_service.py`

**Step 1: Add notification when signal is detected**

Find where signals are created and add:

```python
from src.services.notification_integration import notify_signal_detected

# After signal is created:
await notify_signal_detected(
    user_id=user_id,
    company_name=signal.company_name,
    signal_type=signal.signal_type.value,
    headline=signal.headline,
    lead_id=signal.linked_lead_id,
)
```

**Step 2: Run type check**

Run: `cd backend && mypy src/services/signal_service.py --strict`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/src/services/signal_service.py
git commit -m "feat(signals): add notification when market signal detected"
```

---

## Task 14: Integrate Notifications into Meeting Brief Service

**Files:**
- Modify: `backend/src/services/meeting_brief.py`

**Step 1: Add notification when meeting brief is ready**

Find where meeting brief is generated and add:

```python
from src.services.notification_integration import notify_meeting_brief_ready

# After meeting brief is generated:
await notify_meeting_brief_ready(
    user_id=user_id,
    meeting_title=event_title,
    calendar_event_id=calendar_event_id,
)
```

**Step 2: Run type check**

Run: `cd backend && mypy src/services/meeting_brief.py --strict`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/src/services/meeting_brief.py
git commit -m "feat(meeting-brief): add notification when brief is ready"
```

---

## Task 15: Integrate Notifications into Draft Service

**Files:**
- Modify: `backend/src/services/draft_service.py`

**Step 1: Add notification when draft is ready**

Find where email draft is generated and add:

```python
from src.services.notification_integration import notify_draft_ready

# After draft is generated:
await notify_draft_ready(
    user_id=user_id,
    draft_type=purpose,
    recipient=recipient_email,
    draft_id=draft.id,
)
```

**Step 2: Run type check**

Run: `cd backend && mypy src/services/draft_service.py --strict`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/src/services/draft_service.py
git commit -m "feat(drafts): add notification when email draft is ready"
```

---

## Task 16: Create Component Barrel Export

**Files:**
- Create: `frontend/src/components/notifications/index.ts`

**Step 1: Create barrel export**

```typescript
export { NotificationBell } from "./NotificationBell";
export { NotificationsPageContent } from "./NotificationsPage";
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/notifications/index.ts
git commit -m "feat(ui): add notifications component barrel export"
```

---

## Task 17: End-to-End Testing

**Step 1: Start backend server**

Run: `cd backend && uvicorn src.main:app --reload --port 8000`

**Step 2: Start frontend dev server**

Run: `cd frontend && npm run dev`

**Step 3: Manual test checklist**

1. **Test notification creation via API**
   ```bash
   curl -X POST http://localhost:8000/api/v1/notifications/test-create \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json"
   ```

2. **Test bell displays unread badge**
   - Navigate to dashboard
   - Verify bell icon shows unread dot
   - Verify badge count is correct

3. **Test dropdown opens/closes**
   - Click bell icon
   - Verify dropdown animates in
   - Click outside
   - Verify dropdown closes

4. **Test notification items**
   - Verify type icons display correctly
   - Verify title and message show
   - Verify time-ago formatting works
   - Click notification with link
   - Verify navigation and read status

5. **Test mark as read**
   - Click individual notification
   - Verify it's marked read
   - Verify unread count updates
   - Use "Mark all read" button
   - Verify all are marked read

6. **Test notifications page**
   - Click "View all notifications"
   - Verify page loads
   - Verify all notifications show
   - Test delete button
   - Test mark individual as read
   - Verify filtering works

7. **Test polling**
   - Create notification via API
   - Wait 30 seconds
   - Verify bell updates automatically

8. **Test empty states**
   - Delete all notifications
   - Verify empty state in dropdown
   - Verify empty state on page

9. **Test integration**
   - Generate a daily briefing
   - Verify notification is created
   - Generate a meeting brief
   - Verify notification is created

10. **Test mobile responsiveness**
    - Resize to mobile width
    - Verify dropdown is full-width
    - Verify touch interactions work

**Step 4: Run automated tests**

Run: `cd backend && pytest tests/ -v -k notification`

**Step 5: Verify all acceptance criteria**

- [x] In-app notification bell in header
- [x] Notification types: briefing_ready, signal_detected, task_due, meeting_brief_ready, draft_ready
- [x] Mark as read (individual and mark all as read)
- [x] Click to navigate to relevant item
- [x] Email notification option (configurable via US-414 preferences - framework ready)
- [x] Unread count badge on bell icon
- [x] Notification dropdown panel
- [x] Notification history/list page

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete US-415 notification system implementation"
```

---

## Implementation Notes

### Design Reference
- Uses Apple-inspired luxury aesthetic matching existing ARIA UI
- Bell icon matches Lucide design system
- Dropdown uses Framer Motion-style animations via Tailwind animate-in
- Type-specific color coding (blue, amber, rose, emerald, violet)
- Subtle pulsing badge for unread indicators

### Technical Decisions
- **Polling**: 30-second intervals for balance between freshness and performance
- **Pagination**: 20 notifications per page default, 100 max
- **RLS**: Full user isolation via Supabase Row Level Security
- **Service layer**: Clean separation between API and business logic
- **Integration helpers**: Easy notification creation from any service

### Future Enhancements (Out of Scope for US-415)
- WebSocket for real-time notifications
- Email notifications via Composio (when US-414 preferences implemented)
- Notification grouping/batching
- Notification sound/vibration
- Push notifications via PWA
- Notification preferences UI

### Related Documentation
- See `docs/PHASE_4_FEATURES.md` for US-415 full requirements
- See `docs/PHASE_8_AGI_COMPANION.md` for cognitive load-aware notification delivery (future)
