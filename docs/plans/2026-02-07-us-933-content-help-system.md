# US-933: Content & Help System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a complete content and help system including feedback collection, help center with FAQs, changelog, contextual help tooltips, onboarding tooltips, and feedback widgets.

**Architecture:**
- Backend: FastAPI routes for feedback collection with Supabase storage
- Frontend: React components with LIGHT SURFACE theme per ARIA Design System v1.0
- Database: New `feedback` table with RLS policies

**Tech Stack:**
- Backend: Python 3.11+, FastAPI, Supabase (PostgreSQL)
- Frontend: React 18, TypeScript, Tailwind CSS, Lucide React icons

---

## Task 1: Database Migration - Feedback Table

**Files:**
- Create: `backend/supabase/migrations/20260207000000_feedback.sql`

**Step 1: Create the feedback table migration file**

Create `backend/supabase/migrations/20260207000000_feedback.sql`:

```sql
-- ============================================
-- US-933: Content & Help System - Feedback Table
-- ============================================
-- Creates feedback table for collecting user feedback on ARIA responses and general feedback

-- Feedback table
CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('response', 'bug', 'feature', 'other')),
    rating TEXT CHECK (rating IN ('up', 'down')),
    message_id TEXT,
    comment TEXT,
    page TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Add table comment
COMMENT ON TABLE feedback IS 'Stores user feedback for ARIA responses and general feedback';

-- Index for user feedback queries
CREATE INDEX IF NOT EXISTS idx_feedback_user_created ON feedback(user_id, created_at DESC);

-- Index for feedback type filtering
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(type, created_at DESC);

-- Index for message_id lookups (response feedback)
CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback(message_id) WHERE message_id IS NOT NULL;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

-- Users can read their own feedback
CREATE POLICY "Users can read own feedback"
    ON feedback FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own feedback
CREATE POLICY "Users can insert own feedback"
    ON feedback FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Service role bypass for all operations (for analytics)
CREATE POLICY "Service role full access to feedback"
    ON feedback FOR ALL
    USING (auth.role() = 'service_role');
```

**Step 2: Run the migration**

Run: `cd backend && supabase db push`
Expected: Migration applied successfully, feedback table created

**Step 3: Verify table creation**

Run: `cd backend && supabase db remote tables`
Expected: `feedback` table appears in list

**Step 4: Commit**

```bash
git add backend/supabase/migrations/20260207000000_feedback.sql
git commit -m "feat: add feedback table for US-933 content and help system"
```

---

## Task 2: Backend Pydantic Models for Feedback

**Files:**
- Create: `backend/src/models/feedback.py`
- Modify: `backend/src/models/__init__.py`

**Step 1: Create feedback models**

Create `backend/src/models/feedback.py`:

```python
"""Pydantic models for feedback API (US-933)."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ResponseFeedbackRequest(BaseModel):
    """Request model for submitting feedback on an ARIA response."""

    message_id: str = Field(..., description="ID of the ARIA message being rated")
    rating: str = Field(..., pattern="^(up|down)$", description="Rating: 'up' or 'down'")
    comment: str | None = Field(None, max_length=1000, description="Optional comment")


class GeneralFeedbackRequest(BaseModel):
    """Request model for submitting general feedback."""

    type: str = Field(..., pattern="^(bug|feature|other)$", description="Feedback type")
    message: str = Field(..., min_length=1, max_length=2000, description="Feedback message")
    page: str | None = Field(None, max_length=200, description="Optional page context")


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    id: str
    user_id: str
    type: str
    rating: str | None
    message_id: str | None
    comment: str | None
    page: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "rating": self.rating,
            "message_id": self.message_id,
            "comment": self.comment,
            "page": self.page,
            "created_at": self.created_at.isoformat(),
        }
```

**Step 2: Update models __init__.py**

Add to `backend/src/models/__init__.py`:

```python
from src.models.feedback import (
    ResponseFeedbackRequest,
    GeneralFeedbackRequest,
    FeedbackResponse,
)
```

**Step 3: Run type check**

Run: `cd backend && mypy src/models/feedback.py --strict`
Expected: No type errors

**Step 4: Commit**

```bash
git add backend/src/models/feedback.py backend/src/models/__init__.py
git commit -m "feat: add Pydantic models for feedback API"
```

---

## Task 3: Backend Feedback Service

**Files:**
- Create: `backend/src/services/feedback_service.py`

**Step 1: Create the feedback service**

Create `backend/src/services/feedback_service.py`:

```python
"""Feedback service for ARIA (US-933).

This service handles collecting and storing user feedback on:
- ARIA responses (thumbs up/down with optional comment)
- General feedback (bug reports, feature requests, other)
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.exceptions import DatabaseError
from src.db.supabase import SupabaseClient
from src.models.feedback import FeedbackResponse

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service for managing user feedback."""

    @staticmethod
    async def submit_response_feedback(
        user_id: str,
        message_id: str,
        rating: str,
        comment: str | None = None,
    ) -> FeedbackResponse:
        """Submit feedback on an ARIA response.

        Args:
            user_id: The user's UUID.
            message_id: ID of the ARIA message being rated.
            rating: Rating value ('up' or 'down').
            comment: Optional comment explaining the rating.

        Returns:
            Created feedback record.

        Raises:
            DatabaseError: If submission fails.
        """
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "type": "response",
                "rating": rating,
                "message_id": message_id,
                "comment": comment,
            }
            response = client.table("feedback").insert(data).execute()

            if response.data and len(response.data) > 0:
                logger.info(
                    "Response feedback submitted",
                    extra={
                        "user_id": user_id,
                        "message_id": message_id,
                        "rating": rating,
                        "feedback_id": response.data[0]["id"],
                    },
                )
                return FeedbackResponse(**response.data[0])

            raise DatabaseError("Failed to submit response feedback")
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Error submitting response feedback",
                extra={"user_id": user_id, "message_id": message_id},
            )
            raise DatabaseError(f"Failed to submit response feedback: {e}") from e

    @staticmethod
    async def submit_general_feedback(
        user_id: str,
        feedback_type: str,
        message: str,
        page: str | None = None,
    ) -> FeedbackResponse:
        """Submit general feedback (bug, feature, other).

        Args:
            user_id: The user's UUID.
            feedback_type: Type of feedback ('bug', 'feature', 'other').
            message: Feedback message.
            page: Optional page URL where feedback was submitted.

        Returns:
            Created feedback record.

        Raises:
            DatabaseError: If submission fails.
        """
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "type": feedback_type,
                "message": message,
                "page": page,
            }
            response = client.table("feedback").insert(data).execute()

            if response.data and len(response.data) > 0:
                logger.info(
                    "General feedback submitted",
                    extra={
                        "user_id": user_id,
                        "type": feedback_type,
                        "feedback_id": response.data[0]["id"],
                    },
                )
                return FeedbackResponse(**response.data[0])

            raise DatabaseError("Failed to submit general feedback")
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Error submitting general feedback",
                extra={"user_id": user_id, "type": feedback_type},
            )
            raise DatabaseError(f"Failed to submit general feedback: {e}") from e
```

**Step 2: Run type check**

Run: `cd backend && mypy src/services/feedback_service.py --strict`
Expected: No type errors

**Step 3: Commit**

```bash
git add backend/src/services/feedback_service.py
git commit -m "feat: add feedback service for US-933"
```

---

## Task 4: Backend Feedback API Routes

**Files:**
- Create: `backend/src/api/routes/feedback.py`
- Modify: `backend/src/api/routes/__init__.py`
- Modify: `backend/src/main.py`

**Step 1: Create feedback routes**

Create `backend/src/api/routes/feedback.py`:

```python
"""Feedback API routes for US-933.

This module provides endpoints for:
- Submitting feedback on ARIA responses (thumbs up/down)
- Submitting general feedback (bug reports, feature requests)
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser
from src.models.feedback import (
    FeedbackResponse,
    GeneralFeedbackRequest,
    ResponseFeedbackRequest,
)
from src.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/response", status_code=status.HTTP_201_CREATED)
async def submit_response_feedback(
    current_user: CurrentUser,
    request: ResponseFeedbackRequest,
) -> dict[str, Any]:
    """Submit feedback on an ARIA response.

    Args:
        current_user: The authenticated user.
        request: Feedback request with message_id, rating, and optional comment.

    Returns:
        Confirmation message with feedback ID.

    Raises:
        HTTPException: If submission fails.
    """
    try:
        feedback_service = FeedbackService()
        result = await feedback_service.submit_response_feedback(
            user_id=current_user.id,
            message_id=request.message_id,
            rating=request.rating,
            comment=request.comment,
        )

        return {
            "message": "Thank you for your feedback!",
            "feedback_id": result.id,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}",
        ) from e


@router.post("/general", status_code=status.HTTP_201_CREATED)
async def submit_general_feedback(
    current_user: CurrentUser,
    request: GeneralFeedbackRequest,
) -> dict[str, Any]:
    """Submit general feedback.

    Args:
        current_user: The authenticated user.
        request: Feedback request with type, message, and optional page.

    Returns:
        Confirmation message with feedback ID.

    Raises:
        HTTPException: If submission fails.
    """
    try:
        feedback_service = FeedbackService()
        result = await feedback_service.submit_general_feedback(
            user_id=current_user.id,
            feedback_type=request.type,
            message=request.message,
            page=request.page,
        )

        return {
            "message": "Thank you for your feedback!",
            "feedback_id": result.id,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}",
        ) from e
```

**Step 2: Add to routes __init__.py**

Add to `backend/src/api/routes/__init__.py`:

```python
from src.api.routes import feedback as feedback
```

**Step 3: Register router in main.py**

Add to `backend/src/main.py` imports:

```python
from src.api.routes import feedback,
```

Add to app includes:

```python
app.include_router(feedback.router, prefix="/api/v1")
```

**Step 4: Verify server starts**

Run: `cd backend && uvicorn src.main:app --reload --port 8000`
Expected: Server starts without errors, feedback routes registered

**Step 5: Commit**

```bash
git add backend/src/api/routes/feedback.py backend/src/api/routes/__init__.py backend/src/main.py
git commit -m "feat: add feedback API routes for US-933"
```

---

## Task 5: Backend Tests for Feedback API

**Files:**
- Create: `backend/tests/test_api_feedback.py`

**Step 1: Write failing test for response feedback**

Create `backend/tests/test_api_feedback.py`:

```python
"""Tests for feedback API routes (US-933)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


def test_submit_response_feedback_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test successful response feedback submission."""
    request_data = {
        "message_id": "msg_123",
        "rating": "up",
        "comment": "This was helpful!",
    }

    with patch("src.services.feedback_service.SupabaseClient.get_client") as mock_client:
        mock_response = AsyncMock()
        mock_response.data = [{
            "id": "feedback_123",
            "user_id": "user_123",
            "type": "response",
            "rating": "up",
            "message_id": "msg_123",
            "comment": "This was helpful!",
            "page": None,
            "created_at": "2026-02-07T00:00:00Z",
        }]
        mock_client.return_value.table.return_value.insert.return_value.execute.return_value = mock_response

        response = client.post("/api/v1/feedback/response", json=request_data, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Thank you for your feedback!"
        assert "feedback_id" in data


def test_submit_response_feedback_invalid_rating(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test response feedback with invalid rating."""
    request_data = {
        "message_id": "msg_123",
        "rating": "invalid",
    }

    response = client.post("/api/v1/feedback/response", json=request_data, headers=auth_headers)

    assert response.status_code == 422  # Validation error


def test_submit_general_feedback_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test successful general feedback submission."""
    request_data = {
        "type": "bug",
        "message": "Found a bug on the dashboard",
        "page": "/dashboard",
    }

    with patch("src.services.feedback_service.SupabaseClient.get_client") as mock_client:
        mock_response = AsyncMock()
        mock_response.data = [{
            "id": "feedback_123",
            "user_id": "user_123",
            "type": "bug",
            "rating": None,
            "message_id": None,
            "comment": "Found a bug on the dashboard",
            "page": "/dashboard",
            "created_at": "2026-02-07T00:00:00Z",
        }]
        mock_client.return_value.table.return_value.insert.return_value.execute.return_value = mock_response

        response = client.post("/api/v1/feedback/general", json=request_data, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Thank you for your feedback!"
        assert "feedback_id" in data


def test_submit_general_feedback_missing_message(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test general feedback without required message."""
    request_data = {
        "type": "bug",
    }

    response = client.post("/api/v1/feedback/general", json=request_data, headers=auth_headers)

    assert response.status_code == 422  # Validation error


def test_submit_response_feedback_unauthorized(client: TestClient) -> None:
    """Test feedback submission without authentication."""
    request_data = {
        "message_id": "msg_123",
        "rating": "up",
    }

    response = client.post("/api/v1/feedback/response", json=request_data)

    assert response.status_code == 401  # Unauthorized
```

**Step 2: Run tests to verify they fail initially**

Run: `cd backend && pytest tests/test_api_feedback.py -v`
Expected: Tests fail (implementation exists but may need auth fixture setup)

**Step 3: Run tests again after auth is properly configured**

Run: `cd backend && pytest tests/test_api_feedback.py -v`
Expected: Tests pass

**Step 4: Commit**

```bash
git add backend/tests/test_api_feedback.py
git commit -m "test: add feedback API tests for US-933"
```

---

## Task 6: Frontend API Client for Feedback

**Files:**
- Modify: `frontend/src/api/client.ts` (if needed)
- Create: `frontend/src/api/feedback.ts`

**Step 1: Create feedback API client**

Create `frontend/src/api/feedback.ts`:

```typescript
/**
 * Feedback API client functions for US-933.
 * Handles submitting feedback on ARIA responses and general feedback.
 */

import { apiClient } from "./client";

/**
 * Response feedback request
 */
interface ResponseFeedbackRequest {
  message_id: string;
  rating: "up" | "down";
  comment?: string;
}

/**
 * General feedback request
 */
interface GeneralFeedbackRequest {
  type: "bug" | "feature" | "other";
  message: string;
  page?: string;
}

/**
 * Feedback submission response
 */
interface FeedbackSubmissionResponse {
  message: string;
  feedback_id: string;
}

/**
 * Submit feedback on an ARIA response
 */
export async function submitResponseFeedback(
  request: ResponseFeedbackRequest
): Promise<FeedbackSubmissionResponse> {
  const response = await apiClient.post<FeedbackSubmissionResponse>(
    "/feedback/response",
    request
  );
  return response.data;
}

/**
 * Submit general feedback
 */
export async function submitGeneralFeedback(
  request: GeneralFeedbackRequest
): Promise<FeedbackSubmissionResponse> {
  const response = await apiClient.post<FeedbackSubmissionResponse>(
    "/feedback/general",
    request
  );
  return response.data;
}
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 3: Commit**

```bash
git add frontend/src/api/feedback.ts
git commit -m "feat: add feedback API client for US-933"
```

---

## Task 7: Frontend HelpTooltip Component

**Files:**
- Create: `frontend/src/components/HelpTooltip.tsx`
- Modify: `frontend/src/components/index.ts`

**Step 1: Create HelpTooltip component**

Create `frontend/src/components/HelpTooltip.tsx`:

```typescript
/**
 * HelpTooltip - Contextual help tooltip component
 *
 * Follows ARIA Design System v1.0:
 * - HelpCircle icon (16px, muted color)
 * - Tooltip on hover/click with accessible aria-describedby
 * - Satoshi font for content (15px)
 * - Light bg-[#FAFAF9] with border-[#E2E0DC] for tooltip
 */

import { useState } from "react";
import { HelpCircle } from "lucide-react";
import type { ReactNode } from "react";

interface HelpTooltipProps {
  /** Content to display in the tooltip */
  content: string | ReactNode;
  /** Tooltip placement preference */
  placement?: "top" | "bottom" | "left" | "right";
  /** Optional custom className */
  className?: string;
}

export function HelpTooltip({
  content,
  placement = "top",
  className = "",
}: HelpTooltipProps) {
  const [isOpen, setIsOpen] = useState(false);

  const placementClasses = {
    top: "bottom-full mb-2",
    bottom: "top-full mt-2",
    left: "right-full mr-2",
    right: "left-full ml-2",
  };

  return (
    <div className={`relative inline-flex ${className}`}>
      {/* Help Icon */}
      <button
        type="button"
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        onClick={() => setIsOpen(!isOpen)}
        aria-describedby="help-tooltip-content"
        aria-label="Get help"
        className="text-[#8B92A5] hover:text-[#5B6E8A] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 rounded-sm"
      >
        <HelpCircle size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>

      {/* Tooltip */}
      {isOpen && (
        <div
          id="help-tooltip-content"
          role="tooltip"
          className={`absolute ${placementClasses[placement]} left-1/2 -translate-x-1/2 z-50 w-64 bg-white border border-[#E2E0DC] rounded-lg px-4 py-3 shadow-sm`}
        >
          <p className="font-sans text-[15px] leading-[1.6] text-[#1A1D27]">
            {content}
          </p>
          {/* Arrow */}
          <div className="absolute left-1/2 -translate-x-1/2 w-2 h-2 bg-white border border-[#E2E0DC] rotate-45" />
        </div>
      )}
    </div>
  );
}
```

**Step 2: Add to components barrel**

Add to `frontend/src/components/index.ts`:

```typescript
export { HelpTooltip } from "./HelpTooltip";
```

**Step 3: Run type check and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/HelpTooltip.tsx frontend/src/components/index.ts
git commit -m "feat: add HelpTooltip component for US-933"
```

---

## Task 8: Frontend FeedbackWidget Component

**Files:**
- Create: `frontend/src/components/FeedbackWidget.tsx`
- Modify: `frontend/src/components/index.ts`

**Step 1: Create FeedbackWidget component**

Create `frontend/src/components/FeedbackWidget.tsx`:

```typescript
/**
 * FeedbackWidget - Thumbs up/down feedback for ARIA responses
 *
 * Follows ARIA Design System v1.0:
 * - ThumbsUp/ThumbsDown icons (16px)
 * - Brief "Thanks!" confirmation after submission
 * - Optional comment field expands on thumbs down
 */

import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { submitResponseFeedback } from "@/api/feedback";

interface FeedbackWidgetProps {
  /** ID of the ARIA message being rated */
  messageId: string;
  /** Optional custom className */
  className?: string;
}

export function FeedbackWidget({ messageId, className = "" }: FeedbackWidgetProps) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRating = async (newRating: "up" | "down") => {
    if (submitted) return;

    setIsSubmitting(true);
    try {
      await submitResponseFeedback({
        message_id: messageId,
        rating: newRating,
      });

      setRating(newRating);
      setSubmitted(true);

      if (newRating === "down") {
        setShowComment(true);
      }
    } catch {
      // Silently fail - user can try again
      setIsSubmitting(false);
    } finally {
      if (rating === "up") {
        setIsSubmitting(false);
      }
    }
  };

  const handleSubmitComment = async () => {
    if (!rating || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await submitResponseFeedback({
        message_id: messageId,
        rating,
        comment: comment.trim() || undefined,
      });
      setShowComment(false);
    } catch {
      // Silently fail
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted && !showComment) {
    return (
      <span className={`font-sans text-[13px] text-[#6B8F71] ${className}`}>
        Thanks!
      </span>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Thumbs Up Button */}
      <button
        type="button"
        onClick={() => handleRating("up")}
        disabled={isSubmitting || submitted}
        aria-label="Thumbs up - this response was helpful"
        className={`p-1.5 rounded transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 ${
          rating === "up"
            ? "bg-[#6B8F71]/20 text-[#6B8F71]"
            : "text-[#8B92A5] hover:bg-[#F5F5F0] hover:text-[#5B6E8A]"
        }`}
      >
        <ThumbsUp size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>

      {/* Thumbs Down Button */}
      <button
        type="button"
        onClick={() => handleRating("down")}
        disabled={isSubmitting || submitted}
        aria-label="Thumbs down - this response needs improvement"
        className={`p-1.5 rounded transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 ${
          rating === "down"
            ? "bg-[#A66B6B]/20 text-[#A66B6B]"
            : "text-[#8B92A5] hover:bg-[#F5F5F0] hover:text-[#5B6E8A]"
        }`}
      >
        <ThumbsDown size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>

      {/* Comment Field (expands on thumbs down) */}
      {showComment && (
        <div className="flex items-center gap-2 ml-2">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Tell us more (optional)"
            className="bg-white border border-[#E2E0DC] rounded-lg px-3 py-1.5 text-[15px] font-sans focus:border-[#5B6E8A] focus:ring-1 focus:ring-[#5B6E8A] focus:outline-none w-48"
            onKeyPress={(e) => {
              if (e.key === "Enter") {
                handleSubmitComment();
              }
            }}
          />
          <button
            type="button"
            onClick={handleSubmitComment}
            disabled={isSubmitting}
            className="font-sans text-[13px] font-medium text-[#5B6E8A] hover:text-[#4A5D79] cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] rounded px-2 py-1"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Add to components barrel**

Add to `frontend/src/components/index.ts`:

```typescript
export { FeedbackWidget } from "./FeedbackWidget";
```

**Step 3: Run type check and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/FeedbackWidget.tsx frontend/src/components/index.ts
git commit -m "feat: add FeedbackWidget component for US-933"
```

---

## Task 9: Frontend HelpPage Component

**Files:**
- Create: `frontend/src/pages/HelpPage.tsx`
- Create: `frontend/src/components/help/HelpPage.tsx` (content component)
- Create: `frontend/src/components/help/index.ts`
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Create HelpPage content component**

Create `frontend/src/components/help/HelpPage.tsx`:

```typescript
/**
 * HelpPage - Help center with searchable FAQ articles
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT SURFACE theme (bg-[#FAFAF9])
 * - Search bar with Satoshi font
 * - Accordion categories with expandable articles
 * - "Contact Support" button at bottom
 */

import { useState } from "react";
import { Search, MessageSquare, Mail } from "lucide-react";

interface FAQArticle {
  id: string;
  question: string;
  answer: string;
}

interface FAQCategory {
  id: string;
  name: string;
  articles: FAQArticle[];
}

const FAQ_CATEGORIES: FAQCategory[] = [
  {
    id: "getting-started",
    name: "Getting Started",
    articles: [
      {
        id: "first-time-login",
        question: "How do I get started with ARIA?",
        answer: "After signing up, you'll go through a brief onboarding where ARIA learns about your company, your role, and your goals. This typically takes 10-15 minutes. Once complete, ARIA will begin working on your goals immediately.",
      },
      {
        id: "connect-integrations",
        question: "Which integrations should I connect first?",
        answer: "We recommend connecting your email and CRM first. These give ARIA the most context about your work. Calendar and Slack are optional but helpful for meeting prep and team communication.",
      },
      {
        id: "first-briefing",
        question: "When will I receive my first Daily Briefing?",
        answer: "Your first Daily Briefing will arrive the morning after you complete onboarding. It will include intelligence ARIA has gathered about your company and any initial goal progress.",
      },
    ],
  },
  {
    id: "account-settings",
    name: "Account & Settings",
    articles: [
      {
        id: "change-password",
        question: "How do I change my password?",
        answer: "Go to Settings > Account and click 'Change Password'. You'll need to enter your current password and then provide a new one. For security, we recommend using a password manager.",
      },
      {
        id: "2fa-setup",
        question: "How do I enable two-factor authentication?",
        answer: "In Settings > Account, you'll find the Two-Factor Authentication section. Click 'Enable' and follow the prompts to connect your authenticator app (Google Authenticator, Authy, etc.).",
      },
      {
        id: "team-invites",
        question: "How do I invite team members?",
        answer: "As an admin, go to the Team section in settings. Click 'Invite Member' and enter their email. They'll receive an invite link to join your company's ARIA workspace.",
      },
    ],
  },
  {
    id: "integrations",
    name: "Integrations",
    articles: [
      {
        id: "crm-sync",
        question: "How does CRM syncing work?",
        answer: "ARIA syncs with Salesforce and HubSpot. We pull opportunities, contacts, and accounts to build Lead Memory. We can also write back updates if you enable that option. Syncs happen automatically every few hours.",
      },
      {
        id: "email-privacy",
        question: "Is my email data private?",
        answer: "Yes. Your email content is encrypted at rest and never shared, even with team members at your company. ARIA uses it only to build your personal Digital Twin and improve recommendations.",
      },
      {
        id: "calendar-events",
        question: "Which calendar events does ARIA use?",
        answer: "ARIA looks at your calendar to identify meetings with external contacts. These are potential candidates for meeting briefs. Internal meetings and personal events are ignored.",
      },
    ],
  },
  {
    id: "features",
    name: "ARIA Features",
    articles: [
      {
        id: "daily-briefing",
        question: "What's in the Daily Briefing?",
        answer: "Your briefing includes: market signals relevant to your territory, updates on leads in your pipeline, meeting briefs for upcoming calls, and tasks ARIA has completed on your behalf.",
      },
      {
        id: "battle-cards",
        question: "How do I generate a battle card?",
        answer: "Navigate to the Battle Cards section and click 'Generate New'. ARIA will research the competitor and create a comprehensive battle card with positioning, pricing, and win strategies.",
      },
      {
        id: "goal-setting",
        question: "What kinds of goals can I set?",
        answer: "You can set goals for pipeline generation, meeting prep, competitive intelligence, or any custom outcome. ARIA will break them into subtasks and assign agents to work on them.",
      },
    ],
  },
  {
    id: "privacy-data",
    name: "Privacy & Data",
    articles: [
      {
        id: "data-retention",
        question: "How long is my data stored?",
        answer: "Conversation history and Corporate Memory are stored indefinitely. Email data can be configured with custom retention (default 1 year). You can delete your data at any time from Settings > Privacy.",
      },
      {
        id: "export-data",
        question: "Can I export my data?",
        answer: "Yes. Go to Settings > Privacy and click 'Export Data'. You'll receive a complete export of your Digital Twin data in JSON format. Admins can also export all company data.",
      },
      {
        id: "gdpr-rights",
        question: "What are my GDPR rights?",
        answer: "You have the right to access, rectify, and delete your personal data. You can exercise these from Settings > Privacy. For detailed requests, contact privacy@aria.ai.",
      },
    ],
  },
  {
    id: "billing",
    name: "Billing",
    articles: [
      {
        id: "pricing",
        question: "How much does ARIA cost?",
        answer: "ARIA is $200,000 per year for your entire company. This includes unlimited seats and all features. Additional users can be added at no extra cost.",
      },
      {
        id: "payment-methods",
        question: "What payment methods do you accept?",
        answer: "We accept all major credit cards, ACH transfers, and can invoice for enterprise customers. Payment is handled securely through Stripe.",
      },
      {
        id: "refund-policy",
        question: "What is your refund policy?",
        answer: "We offer annual contracts. If you're not satisfied, please contact our support team. We work with customers to ensure ARIA delivers value.",
      },
    ],
  },
];

export function HelpPageContent() {
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [expandedArticles, setExpandedArticles] = useState<Set<string>>(new Set());

  // Filter FAQs based on search
  const filteredCategories = FAQ_CATEGORIES.map((category) => ({
    ...category,
    articles: category.articles.filter(
      (article) =>
        article.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
        article.answer.toLowerCase().includes(searchQuery.toLowerCase())
    ),
  })).filter((category) => category.articles.length > 0);

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) {
        next.delete(categoryId);
      } else {
        next.add(categoryId);
      }
      return next;
    });
  };

  const toggleArticle = (articleId: string) => {
    setExpandedArticles((prev) => {
      const next = new Set(prev);
      if (next.has(articleId)) {
        next.delete(articleId);
      } else {
        next.add(articleId);
      }
      return next;
    });
  };

  return (
    <div className="bg-[#FAFAF9] min-h-screen">
      <div className="max-w-3xl mx-auto py-12 px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="font-display text-[32px] leading-[1.2] text-[#1A1D27] mb-3">
            Help Center
          </h1>
          <p className="font-sans text-[15px] leading-[1.6] text-[#6B7280]">
            Find answers to common questions and learn how to get the most out of ARIA.
          </p>
        </div>

        {/* Search Bar */}
        <div className="relative mb-8">
          <Search
            size={20}
            strokeWidth={1.5}
            className="absolute left-4 top-1/2 -translate-y-1/2 text-[#8B92A5]"
            aria-hidden="true"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search for help..."
            className="w-full bg-white border border-[#E2E0DC] rounded-lg pl-12 pr-4 py-3 text-[15px] font-sans focus:border-[#5B6E8A] focus:ring-1 focus:ring-[#5B6E8A] focus:outline-none placeholder:text-[#8B92A5]"
          />
        </div>

        {/* FAQ Categories */}
        <div className="space-y-4">
          {filteredCategories.map((category) => (
            <div
              key={category.id}
              className="bg-white border border-[#E2E0DC] rounded-lg overflow-hidden"
            >
              {/* Category Header */}
              <button
                type="button"
                onClick={() => toggleCategory(category.id)}
                className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-[#F5F5F0] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[#7B8EAA]"
                aria-expanded={expandedCategories.has(category.id)}
              >
                <h2 className="font-sans text-[18px] font-medium text-[#1A1D27]">
                  {category.name}
                </h2>
                <svg
                  className={`w-5 h-5 text-[#8B92A5] transition-transform duration-150 ${
                    expandedCategories.has(category.id) ? "rotate-180" : ""
                  }`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>

              {/* Articles */}
              {expandedCategories.has(category.id) && (
                <div className="border-t border-[#E2E0DC] divide-y divide-[#E2E0DC]">
                  {category.articles.map((article) => (
                    <div key={article.id}>
                      <button
                        type="button"
                        onClick={() => toggleArticle(article.id)}
                        className="w-full px-6 py-4 text-left hover:bg-[#F5F5F0] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[#7B8EAA]"
                        aria-expanded={expandedArticles.has(article.id)}
                      >
                        <h3 className="font-sans text-[15px] font-medium text-[#1A1D27] mb-1">
                          {article.question}
                        </h3>
                        {expandedArticles.has(article.id) && (
                          <p className="font-sans text-[15px] leading-[1.6] text-[#6B7280] mt-2">
                            {article.answer}
                          </p>
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Contact Support */}
        <div className="mt-12 p-6 bg-white border border-[#E2E0DC] rounded-lg">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-full bg-[#F5F5F0] flex items-center justify-center flex-shrink-0">
              <MessageSquare size={20} strokeWidth={1.5} className="text-[#5B6E8A]" aria-hidden="true" />
            </div>
            <div className="flex-1">
              <h3 className="font-sans text-[18px] font-medium text-[#1A1D27] mb-2">
                Still need help?
              </h3>
              <p className="font-sans text-[15px] leading-[1.6] text-[#6B7280] mb-4">
                Our support team is here to help you get the most out of ARIA.
              </p>
              <a
                href="mailto:support@aria.ai"
                className="inline-flex items-center gap-2 text-[#5B6E8A] font-sans text-[15px] font-medium hover:text-[#4A5D79] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] rounded"
              >
                <Mail size={16} strokeWidth={1.5} aria-hidden="true" />
                Contact Support
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Create help barrel**

Create `frontend/src/components/help/index.ts`:

```typescript
export { HelpPageContent } from "./HelpPage";
```

**Step 3: Create HelpPage page wrapper**

Create `frontend/src/pages/HelpPage.tsx`:

```typescript
import { HelpPageContent } from "@/components/help";

export function HelpPage() {
  return <HelpPageContent />;
}
```

**Step 4: Add to pages barrel**

Add to `frontend/src/pages/index.ts`:

```typescript
export { HelpPage } from "./HelpPage";
```

**Step 5: Add route to App.tsx**

Add to `frontend/src/App.tsx`:

```typescript
// In imports
import { HelpPage } from "@/pages";

// In Routes section
<Route
  path="/help"
  element={
    <ProtectedRoute>
      <HelpPage />
    </ProtectedRoute>
  }
/>
```

**Step 6: Run type check and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: No errors

**Step 7: Commit**

```bash
git add frontend/src/pages/HelpPage.tsx frontend/src/components/help/HelpPage.tsx frontend/src/components/help/index.ts frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat: add HelpPage with FAQ content for US-933"
```

---

## Task 10: Frontend ChangelogPage Component

**Files:**
- Create: `frontend/src/pages/ChangelogPage.tsx`
- Create: `frontend/src/components/changelog/ChangelogPage.tsx` (content component)
- Create: `frontend/src/components/changelog/index.ts`
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Create ChangelogPage content component**

Create `frontend/src/components/changelog/ChangelogPage.tsx`:

```typescript
/**
 * ChangelogPage - What's new in ARIA
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT SURFACE theme (bg-[#FAFAF9])
 * - JetBrains Mono for dates
 * - Version badges
 * - "New" badge on entries < 7 days old
 * - Chronological entries with title (Satoshi Medium) and description
 */

interface ChangelogEntry {
  id: string;
  date: string;
  version: string;
  title: string;
  description: string;
  isNew?: boolean;
}

const CHANGELOG_ENTRIES: ChangelogEntry[] = [
  {
    id: "v1.3.0-2026-02-06",
    date: "February 6, 2026",
    version: "v1.3.0",
    title: "Search & Navigation System",
    description: "Global search (Cmd+K), keyboard shortcuts, and breadcrumb navigation. Find anything in ARIA instantly.",
    isNew: true,
  },
  {
    id: "v1.2.0-2026-02-05",
    date: "February 5, 2026",
    version: "v1.2.0",
    title: "Security Hardening",
    description: "Enhanced security with rate limiting, CSRF protection, input validation, and comprehensive audit logging.",
    isNew: true,
  },
  {
    id: "v1.1.0-2026-02-01",
    date: "February 1, 2026",
    version: "v1.1.0",
    description: "GDPR/CCPA compliance features with data export, deletion, and privacy controls.",
    title: "Data Management & Compliance",
  },
  {
    id: "v1.0.0-2026-01-15",
    date: "January 15, 2026",
    version: "v1.0.0",
    title: "ARIA Launch",
    description: "Initial release with onboarding, daily briefings, battle cards, goal management, and agent orchestration.",
  },
];

export function ChangelogPageContent() {
  const isNewEntry = (date: string) => {
    const entryDate = new Date(date);
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    return entryDate > weekAgo;
  };

  return (
    <div className="bg-[#FAFAF9] min-h-screen">
      <div className="max-w-3xl mx-auto py-12 px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="font-display text-[32px] leading-[1.2] text-[#1A1D27] mb-3">
            What's New
          </h1>
          <p className="font-sans text-[15px] leading-[1.6] text-[#6B7280]">
            The latest updates and improvements to ARIA.
          </p>
        </div>

        {/* Changelog Entries */}
        <div className="space-y-6">
          {CHANGELOG_ENTRIES.map((entry) => (
            <article
              key={entry.id}
              className="bg-white border border-[#E2E0DC] rounded-lg p-6 hover:shadow-sm transition-shadow duration-150"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  {/* Version Badge */}
                  <span className="font-mono text-[13px] font-medium text-[#5B6E8A] bg-[#F5F5F0] px-2 py-1 rounded">
                    {entry.version}
                  </span>

                  {/* New Badge */}
                  {isNewEntry(entry.date) && (
                    <span className="font-sans text-[11px] font-medium text-[#5A7D60] bg-[#5A7D60]/10 px-2 py-1 rounded">
                      New
                    </span>
                  )}
                </div>

                {/* Date - JetBrains Mono */}
                <time className="font-mono text-[13px] text-[#8B92A5]" dateTime={entry.date}>
                  {entry.date}
                </time>
              </div>

              {/* Title - Satoshi Medium */}
              <h2 className="font-sans text-[18px] font-medium text-[#1A1D27] mb-2">
                {entry.title}
              </h2>

              {/* Description */}
              <p className="font-sans text-[15px] leading-[1.6] text-[#6B7280]">
                {entry.description}
              </p>
            </article>
          ))}
        </div>

        {/* Footer Note */}
        <div className="mt-12 text-center">
          <p className="font-sans text-[13px] text-[#8B92A5]">
            Have a suggestion?{" "}
            <a href="/help" className="text-[#5B6E8A] hover:text-[#4A5D79] underline">
              Let us know
            </a>
            .
          </p>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Create changelog barrel**

Create `frontend/src/components/changelog/index.ts`:

```typescript
export { ChangelogPageContent } from "./ChangelogPage";
```

**Step 3: Create ChangelogPage page wrapper**

Create `frontend/src/pages/ChangelogPage.tsx`:

```typescript
import { ChangelogPageContent } from "@/components/changelog";

export function ChangelogPage() {
  return <ChangelogPageContent />;
}
```

**Step 4: Add to pages barrel**

Add to `frontend/src/pages/index.ts`:

```typescript
export { ChangelogPage } from "./ChangelogPage";
```

**Step 5: Add route to App.tsx**

Add to `frontend/src/App.tsx`:

```typescript
// In imports
import { ChangelogPage } from "@/pages";

// In Routes section
<Route
  path="/changelog"
  element={
    <ProtectedRoute>
      <ChangelogPage />
    </ProtectedRoute>
  }
/>
```

**Step 6: Run type check and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: No errors

**Step 7: Commit**

```bash
git add frontend/src/pages/ChangelogPage.tsx frontend/src/components/changelog/ChangelogPage.tsx frontend/src/components/changelog/index.ts frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat: add ChangelogPage for US-933"
```

---

## Task 11: Frontend OnboardingTooltip Component

**Files:**
- Create: `frontend/src/components/OnboardingTooltip.tsx`
- Modify: `frontend/src/components/index.ts`

**Step 1: Create OnboardingTooltip component**

Create `frontend/src/components/OnboardingTooltip.tsx`:

```typescript
/**
 * OnboardingTooltip - First-time feature tooltip
 *
 * Follows ARIA Design System v1.0:
 * - Floating card with arrow
 * - Dismissable (not stored per design system artifact restrictions)
 * - Track dismissed state in React state (parent component manages)
 * - LIGHT bg-[#FFFFFF] with border-[#E2E0DC]
 */

import { useState } from "react";
import { X } from "lucide-react";
import type { ReactNode } from "react";

interface OnboardingTooltipProps {
  /** Tooltip content */
  children: ReactNode;
  /** Optional title */
  title?: string;
  /** Placement preference */
  placement?: "top" | "bottom" | "left" | "right";
  /** Optional custom className */
  className?: string;
  /** Initial dismissed state */
  initiallyDismissed?: boolean;
  /** Callback when dismissed */
  onDismiss?: () => void;
}

export function OnboardingTooltip({
  children,
  title,
  placement = "bottom",
  className = "",
  initiallyDismissed = false,
  onDismiss,
}: OnboardingTooltipProps) {
  const [isDismissed, setIsDismissed] = useState(initiallyDismissed);

  if (isDismissed) {
    return null;
  }

  const handleDismiss = () => {
    setIsDismissed(true);
    onDismiss?.();
  };

  const placementClasses = {
    top: "bottom-full mb-3",
    bottom: "top-full mt-3",
    left: "right-full mr-3",
    right: "left-full ml-3",
  };

  const arrowClasses = {
    top: "bottom-0 left-1/2 -translate-x-1/2 translate-y-full",
    bottom: "top-0 left-1/2 -translate-x-1/2 -translate-y-full",
    left: "right-0 top-1/2 -translate-y-1/2 translate-x-full",
    right: "left-0 top-1/2 -translate-y-1/2 -translate-x-full",
  };

  const arrowRotation = {
    top: "rotate-180",
    bottom: "rotate-0",
    left: "-rotate-90",
    right: "rotate-90",
  };

  return (
    <div className={`relative inline-block ${className}`}>
      {/* Tooltip Card */}
      <div className={`absolute ${placementClasses[placement]} left-1/2 -translate-x-1/2 z-50 w-72 bg-white border border-[#E2E0DC] rounded-lg shadow-sm`}>
        {/* Content */}
        <div className="p-4">
          {title && (
            <h3 className="font-sans text-[15px] font-medium text-[#1A1D27] mb-2">
              {title}
            </h3>
          )}
          <div className="font-sans text-[15px] leading-[1.6] text-[#6B7280]">
            {children}
          </div>
        </div>

        {/* Dismiss Button */}
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss tooltip"
          className="absolute top-2 right-2 p-1 text-[#8B92A5] hover:text-[#5B6E8A] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] rounded"
        >
          <X size={14} strokeWidth={1.5} aria-hidden="true" />
        </button>

        {/* Arrow */}
        <div
          className={`absolute ${arrowClasses[placement]} w-0 h-0 border-l-8 border-r-8 border-b-8 border-l-transparent border-r-transparent border-b-[#E2E0DC]`}
        />
        <div
          className={`absolute ${arrowClasses[placement]} w-0 h-0 border-l-8 border-r-8 border-b-8 border-l-transparent border-r-transparent border-b-white ${arrowRotation[placement]}`}
          style={{ transform: `translateY(${placement === "top" ? "-1px" : "1px"}) rotate(${arrowRotation[placement] === "rotate-0" ? "0deg" : arrowRotation[placement]})` }}
        />
      </div>
    </div>
  );
}
```

**Step 2: Add to components barrel**

Add to `frontend/src/components/index.ts`:

```typescript
export { OnboardingTooltip } from "./OnboardingTooltip";
```

**Step 3: Run type check and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/OnboardingTooltip.tsx frontend/src/components/index.ts
git commit -m "feat: add OnboardingTooltip component for US-933"
```

---

## Task 12: Frontend Component Tests

**Files:**
- Create: `frontend/src/components/__tests__/HelpTooltip.test.tsx`
- Create: `frontend/src/components/__tests__/FeedbackWidget.test.tsx`
- Create: `frontend/src/components/__tests__/OnboardingTooltip.test.tsx`

**Step 1: Write HelpTooltip tests**

Create `frontend/src/components/__tests__/HelpTooltip.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { HelpTooltip } from "../HelpTooltip";

describe("HelpTooltip", () => {
  it("renders help icon", () => {
    render(<HelpTooltip content="Help text" />);
    const button = screen.getByRole("button", { name: /get help/i });
    expect(button).toBeInTheDocument();
  });

  it("shows tooltip on hover", () => {
    render(<HelpTooltip content="Help text" />);
    const button = screen.getByRole("button", { name: /get help/i });

    // Simulate hover
    button.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));

    expect(screen.getByText("Help text")).toBeInTheDocument();
  });

  it("has accessible aria-describedby", () => {
    render(<HelpTooltip content="Help text" />);
    const button = screen.getByRole("button", { name: /get help/i });
    expect(button).toHaveAttribute("aria-describedby", "help-tooltip-content");
  });
});
```

**Step 2: Write FeedbackWidget tests**

Create `frontend/src/components/__tests__/FeedbackWidget.test.tsx`:

```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FeedbackWidget } from "../FeedbackWidget";

vi.mock("@/api/feedback", () => ({
  submitResponseFeedback: vi.fn(() => Promise.resolve({ message: "Thanks!", feedback_id: "123" })),
}));

describe("FeedbackWidget", () => {
  it("renders thumbs up and thumbs down buttons", () => {
    render(<FeedbackWidget messageId="msg-123" />);
    expect(screen.getByRole("button", { name: /thumbs up/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /thumbs down/i })).toBeInTheDocument();
  });

  it("shows thanks message after positive feedback", async () => {
    render(<FeedbackWidget messageId="msg-123" />);
    const thumbsUp = screen.getByRole("button", { name: /thumbs up/i });

    fireEvent.click(thumbsUp);

    await waitFor(() => {
      expect(screen.getByText("Thanks!")).toBeInTheDocument();
    });
  });

  it("expands comment field on thumbs down", async () => {
    render(<FeedbackWidget messageId="msg-123" />);
    const thumbsDown = screen.getByRole("button", { name: /thumbs down/i });

    fireEvent.click(thumbsDown);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/tell us more/i)).toBeInTheDocument();
    });
  });
});
```

**Step 3: Write OnboardingTooltip tests**

Create `frontend/src/components/__tests__/OnboardingTooltip.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { OnboardingTooltip } from "../OnboardingTooltip";

describe("OnboardingTooltip", () => {
  it("renders tooltip when not dismissed", () => {
    render(
      <OnboardingTooltip initiallyDismissed={false}>
        Tooltip content
      </OnboardingTooltip>
    );
    expect(screen.getByText("Tooltip content")).toBeInTheDocument();
  });

  it("does not render when initially dismissed", () => {
    render(
      <OnboardingTooltip initiallyDismissed>
        Tooltip content
      </OnboardingTooltip>
    );
    expect(screen.queryByText("Tooltip content")).not.toBeInTheDocument();
  });

  it("calls onDismiss when dismissed", () => {
    const onDismiss = vi.fn();
    render(
      <OnboardingTooltip initiallyDismissed={false} onDismiss={onDismiss}>
        Tooltip content
      </OnboardingTooltip>
    );

    const dismissButton = screen.getByRole("button", { name: /dismiss tooltip/i });
    dismissButton.click();

    expect(onDismiss).toHaveBeenCalled();
  });
});
```

**Step 4: Run tests**

Run: `cd frontend && npm run test`
Expected: All tests pass

**Step 5: Commit**

```bash
git add frontend/src/components/__tests__/HelpTooltip.test.tsx frontend/src/components/__tests__/FeedbackWidget.test.tsx frontend/src/components/__tests__/OnboardingTooltip.test.tsx
git commit -m "test: add component tests for US-933"
```

---

## Task 13: Quality Gates

**Files:**
- No files created - run verification commands

**Step 1: Run backend tests**

Run: `cd backend && pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Run backend type checking**

Run: `cd backend && mypy src/ --strict`
Expected: No type errors

**Step 3: Run backend linting**

Run: `cd backend && ruff check src/`
Expected: No linting errors

**Step 4: Run frontend tests**

Run: `cd frontend && npm run test`
Expected: All tests pass

**Step 5: Run frontend type checking**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 6: Run frontend linting**

Run: `cd frontend && npm run lint`
Expected: No linting errors

**Step 7: Verify database migration**

Run: `cd backend && supabase db remote tables`
Expected: `feedback` table exists with correct schema

**Step 8: Verify server starts**

Run: `cd backend && uvicorn src.main:app --reload --port 8000`
Expected: Server starts, feedback routes registered

**Step 9: Commit (if all gates pass)**

```bash
git add .
git commit -m "feat: complete US-933 content and help system implementation

- Database: feedback table with RLS policies
- Backend: Feedback service and API routes
- Frontend: HelpTooltip, FeedbackWidget, OnboardingTooltip components
- Frontend: HelpPage with searchable FAQs
- Frontend: ChangelogPage with version history
- Tests: Backend API tests, frontend component tests
- Quality: All tests passing, type checking, linting clean"
```

---

## Summary

This plan implements the complete US-933 Content & Help System:

1. **Database** - `feedback` table with RLS policies
2. **Backend** - Feedback service and API routes for response and general feedback
3. **Frontend Components**:
   - `HelpTooltip` - Contextual help tooltips
   - `FeedbackWidget` - Thumbs up/down feedback with optional comments
   - `OnboardingTooltip` - First-time feature tooltips
4. **Frontend Pages**:
   - `HelpPage` - Searchable FAQ center with categories
   - `ChangelogPage` - Version history with "New" badges
5. **Tests** - Complete test coverage for backend API and frontend components

All components follow ARIA Design System v1.0 with LIGHT SURFACE theme for help/changelog pages, proper accessibility, and consistent styling.
