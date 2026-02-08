# US-940: ARIA Activity Feed / Command Center — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a central view of everything ARIA is doing — chronological activity stream with real-time polling, filtering, agent status overview, and reasoning transparency.

**Architecture:** Database table `aria_activity` stores all agent actions with RLS. `ActivityService` provides recording and querying. FastAPI routes serve feed, agent status, and detail endpoints. React frontend at `/activity` renders agent status strip + infinite-scroll activity stream with filters and expandable reasoning.

**Tech Stack:** Python/FastAPI, Supabase (PostgreSQL + RLS), React 18, TypeScript, Tailwind CSS, React Query, Axios

---

### Task 1: Database Migration

**Files:**
- Create: `backend/supabase/migrations/20260208030000_activity_feed.sql`

**Step 1: Write the migration SQL**

```sql
-- US-940: ARIA Activity Feed / Command Center
CREATE TABLE IF NOT EXISTS aria_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    agent TEXT,
    activity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    reasoning TEXT DEFAULT '',
    confidence FLOAT DEFAULT 0.5,
    related_entity_type TEXT,
    related_entity_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_activity_user_created
    ON aria_activity(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_user_type
    ON aria_activity(user_id, activity_type);

CREATE INDEX IF NOT EXISTS idx_activity_user_agent
    ON aria_activity(user_id, agent);

ALTER TABLE aria_activity ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_own_activity" ON aria_activity;
CREATE POLICY "users_own_activity" ON aria_activity
    FOR ALL TO authenticated USING (user_id = auth.uid());
```

**Step 2: Verify migration file is valid SQL**

Run: `cd /Users/dhruv/aria && python -c "open('backend/supabase/migrations/20260208030000_activity_feed.sql').read(); print('OK')"`

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260208030000_activity_feed.sql
git commit -m "feat(US-940): add aria_activity table migration"
```

---

### Task 2: Pydantic Models

**Files:**
- Create: `backend/src/models/activity.py`

**Step 1: Write the failing test**

Create `backend/tests/test_activity_feed.py`:

```python
"""Tests for US-940 Activity Feed / Command Center."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.models.activity import ActivityCreate, ActivityFilter, ActivityItem


class TestActivityModels:
    """Test Pydantic model validation."""

    def test_activity_create_valid(self) -> None:
        a = ActivityCreate(
            agent="hunter",
            activity_type="research_complete",
            title="Researched Acme Corp",
            description="Found 5 key contacts",
            reasoning="User has meeting next week, pre-research triggered",
            confidence=0.85,
        )
        assert a.agent == "hunter"
        assert a.confidence == 0.85

    def test_activity_create_minimal(self) -> None:
        a = ActivityCreate(
            activity_type="signal_detected",
            title="FDA approval detected",
        )
        assert a.agent is None
        assert a.confidence == 0.5

    def test_activity_create_rejects_empty_title(self) -> None:
        with pytest.raises(ValueError):
            ActivityCreate(activity_type="research_complete", title="")

    def test_activity_create_rejects_empty_type(self) -> None:
        with pytest.raises(ValueError):
            ActivityCreate(activity_type="", title="Some title")

    def test_activity_create_clamps_confidence(self) -> None:
        with pytest.raises(ValueError):
            ActivityCreate(
                activity_type="test", title="Test", confidence=1.5
            )

    def test_activity_filter_defaults(self) -> None:
        f = ActivityFilter()
        assert f.agent is None
        assert f.activity_type is None
        assert f.limit == 50
        assert f.offset == 0

    def test_activity_filter_validates_limit(self) -> None:
        with pytest.raises(ValueError):
            ActivityFilter(limit=0)

    def test_activity_item_full(self) -> None:
        item = ActivityItem(
            id="abc-123",
            user_id="user-1",
            agent="analyst",
            activity_type="research_complete",
            title="Research done",
            description="Details",
            reasoning="Because goal required it",
            confidence=0.9,
            related_entity_type="lead",
            related_entity_id="lead-1",
            metadata={},
            created_at="2026-02-08T00:00:00Z",
        )
        assert item.id == "abc-123"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_activity_feed.py::TestActivityModels -v`
Expected: FAIL (import error — models don't exist yet)

**Step 3: Write the models**

Create `backend/src/models/activity.py`:

```python
"""Pydantic models for US-940 Activity Feed."""

from pydantic import BaseModel, Field


class ActivityCreate(BaseModel):
    """Request body for recording an activity."""

    agent: str | None = Field(None, description="Which agent performed this")
    activity_type: str = Field(..., min_length=1, description="Activity type key")
    title: str = Field(..., min_length=1, description="Short title")
    description: str = Field("", description="Longer description")
    reasoning: str = Field("", description="ARIA reasoning chain")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confidence 0-1")
    related_entity_type: str | None = Field(None, description="lead, goal, contact, company")
    related_entity_id: str | None = Field(None, description="UUID of related entity")
    metadata: dict = Field(default_factory=dict, description="Extra metadata")


class ActivityFilter(BaseModel):
    """Query parameters for filtering the activity feed."""

    agent: str | None = None
    activity_type: str | None = None
    date_start: str | None = Field(None, description="ISO date start")
    date_end: str | None = Field(None, description="ISO date end")
    search: str | None = Field(None, description="Text search in title/description")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class ActivityItem(BaseModel):
    """Response model for a single activity."""

    id: str
    user_id: str
    agent: str | None = None
    activity_type: str
    title: str
    description: str = ""
    reasoning: str = ""
    confidence: float = 0.5
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_activity_feed.py::TestActivityModels -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/models/activity.py backend/tests/test_activity_feed.py
git commit -m "feat(US-940): add Pydantic models for activity feed"
```

---

### Task 3: ActivityService

**Files:**
- Create: `backend/src/services/activity_service.py`
- Modify: `backend/tests/test_activity_feed.py` (add service tests)

**Step 1: Write failing tests**

Append to `backend/tests/test_activity_feed.py`:

```python
# ------------------------------------------------------------------ #
# Helper mocks (same pattern as test_account_planning.py)             #
# ------------------------------------------------------------------ #


def _mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


def _chain(mock: MagicMock, data: list[dict[str, Any]]) -> MagicMock:
    """Make a fluent mock chain return data on .execute()."""
    execute_result = MagicMock()
    execute_result.data = data
    mock.execute.return_value = execute_result
    for method in (
        "select",
        "eq",
        "neq",
        "gte",
        "lte",
        "ilike",
        "or_",
        "order",
        "limit",
        "offset",
        "insert",
        "update",
        "maybe_single",
        "single",
        "range",
    ):
        getattr(mock, method, lambda *a, **kw: mock).return_value = mock  # noqa: ARG005
    mock.execute.return_value = execute_result
    return mock


class TestActivityServiceRecord:
    """Test ActivityService.record."""

    @pytest.mark.asyncio
    async def test_record_activity(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        inserted = {
            "id": "act-1",
            "user_id": "user-1",
            "agent": "hunter",
            "activity_type": "research_complete",
            "title": "Researched Acme",
            "description": "",
            "reasoning": "",
            "confidence": 0.8,
            "related_entity_type": None,
            "related_entity_id": None,
            "metadata": {},
            "created_at": "2026-02-08T00:00:00Z",
        }
        _chain(mock_table, [inserted])
        db.table = lambda _: mock_table

        from unittest.mock import patch

        with patch("src.services.activity_service.SupabaseClient") as mock_sb:
            mock_sb.get_client.return_value = db
            service = ActivityService()
            service._db = db
            result = await service.record(
                user_id="user-1",
                agent="hunter",
                activity_type="research_complete",
                title="Researched Acme",
                confidence=0.8,
            )

        assert result["id"] == "act-1"
        assert result["agent"] == "hunter"


class TestActivityServiceGetFeed:
    """Test ActivityService.get_feed."""

    @pytest.mark.asyncio
    async def test_get_feed_returns_data(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        feed_data = [
            {
                "id": "act-1",
                "user_id": "user-1",
                "agent": "analyst",
                "activity_type": "research_complete",
                "title": "Finished research",
                "description": "",
                "reasoning": "Goal required research",
                "confidence": 0.9,
                "related_entity_type": None,
                "related_entity_id": None,
                "metadata": {},
                "created_at": "2026-02-08T01:00:00Z",
            },
        ]
        _chain(mock_table, feed_data)
        db.table = lambda _: mock_table

        from unittest.mock import patch

        with patch("src.services.activity_service.SupabaseClient"):
            service = ActivityService()
            service._db = db
            result = await service.get_feed("user-1")

        assert len(result) == 1
        assert result[0]["agent"] == "analyst"

    @pytest.mark.asyncio
    async def test_get_feed_empty(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        from unittest.mock import patch

        with patch("src.services.activity_service.SupabaseClient"):
            service = ActivityService()
            service._db = db
            result = await service.get_feed("user-1")

        assert result == []


class TestActivityServiceAgentStatus:
    """Test ActivityService.get_agent_status."""

    @pytest.mark.asyncio
    async def test_agent_status_with_activity(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        status_data = [
            {
                "agent": "hunter",
                "activity_type": "research_complete",
                "title": "Researched leads",
                "created_at": "2026-02-08T01:00:00Z",
            },
            {
                "agent": "analyst",
                "activity_type": "research_complete",
                "title": "Analyzed market",
                "created_at": "2026-02-08T00:30:00Z",
            },
        ]
        _chain(mock_table, status_data)
        db.table = lambda _: mock_table

        from unittest.mock import patch

        with patch("src.services.activity_service.SupabaseClient"):
            service = ActivityService()
            service._db = db
            result = await service.get_agent_status("user-1")

        assert "hunter" in result
        assert result["hunter"]["last_activity"] == "Researched leads"
        assert "analyst" in result
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_activity_feed.py::TestActivityServiceRecord -v`
Expected: FAIL (module not found)

**Step 3: Implement ActivityService**

Create `backend/src/services/activity_service.py`:

```python
"""Activity feed service for US-940.

Records agent activity and serves the chronological feed with
filtering, pagination, and agent status overview.
"""

import logging
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Known ARIA agents for status overview
KNOWN_AGENTS = ("hunter", "analyst", "strategist", "scribe", "operator", "scout")


class ActivityService:
    """Records and serves ARIA activity for the feed."""

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    async def record(
        self,
        user_id: str,
        agent: str | None = None,
        activity_type: str = "",
        title: str = "",
        description: str = "",
        reasoning: str = "",
        confidence: float = 0.5,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an activity event.

        Called by agents after completing work.

        Args:
            user_id: The user's ID.
            agent: Which agent performed this.
            activity_type: Type key (research_complete, email_drafted, etc).
            title: Short human-readable title.
            description: Longer description.
            reasoning: ARIA's reasoning chain for transparency.
            confidence: Confidence level 0-1.
            related_entity_type: Entity type (lead, goal, contact, company).
            related_entity_id: UUID of related entity.
            metadata: Extra JSON metadata.

        Returns:
            Inserted activity dict.
        """
        row: dict[str, Any] = {
            "user_id": user_id,
            "agent": agent,
            "activity_type": activity_type,
            "title": title,
            "description": description,
            "reasoning": reasoning,
            "confidence": confidence,
            "related_entity_type": related_entity_type,
            "related_entity_id": related_entity_id,
            "metadata": metadata or {},
        }

        result = self._db.table("aria_activity").insert(row).execute()
        activity = cast(dict[str, Any], result.data[0])

        logger.info(
            "Activity recorded",
            extra={
                "user_id": user_id,
                "activity_id": activity["id"],
                "agent": agent,
                "type": activity_type,
            },
        )
        return activity

    async def get_feed(
        self,
        user_id: str,
        agent: str | None = None,
        activity_type: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get activity feed with optional filters.

        Args:
            user_id: The user's ID.
            agent: Filter by agent name.
            activity_type: Filter by activity type.
            date_start: ISO datetime lower bound.
            date_end: ISO datetime upper bound.
            search: Text search in title/description.
            limit: Max rows (1-200).
            offset: Pagination offset.

        Returns:
            List of activity dicts, newest first.
        """
        query = (
            self._db.table("aria_activity")
            .select("*")
            .eq("user_id", user_id)
        )

        if agent:
            query = query.eq("agent", agent)
        if activity_type:
            query = query.eq("activity_type", activity_type)
        if date_start:
            query = query.gte("created_at", date_start)
        if date_end:
            query = query.lte("created_at", date_end)
        if search:
            query = query.or_(
                f"title.ilike.%{search}%,description.ilike.%{search}%"
            )

        result = (
            query.order("created_at", desc=True)
            .limit(limit)
            .offset(offset)
            .execute()
        )

        data = cast(list[dict[str, Any]], result.data)
        logger.info(
            "Activity feed retrieved",
            extra={"user_id": user_id, "count": len(data)},
        )
        return data

    async def get_activity_detail(
        self, user_id: str, activity_id: str
    ) -> dict[str, Any] | None:
        """Get a single activity with full reasoning.

        Args:
            user_id: The user's ID.
            activity_id: The activity UUID.

        Returns:
            Activity dict or None if not found.
        """
        result = (
            self._db.table("aria_activity")
            .select("*")
            .eq("id", activity_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result is None or result.data is None:
            return None
        return cast(dict[str, Any], result.data)

    async def get_agent_status(self, user_id: str) -> dict[str, Any]:
        """Get current status of each agent.

        Fetches the most recent activity per known agent to determine
        status and last task.

        Args:
            user_id: The user's ID.

        Returns:
            Dict keyed by agent name with status, last_activity, last_time.
        """
        # Fetch recent activities across all agents
        result = (
            self._db.table("aria_activity")
            .select("agent, activity_type, title, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        rows = cast(list[dict[str, Any]], result.data)

        # Build per-agent status from most recent activity
        seen: set[str] = set()
        agent_map: dict[str, Any] = {}
        for row in rows:
            agent_name = row.get("agent")
            if agent_name and agent_name not in seen:
                seen.add(agent_name)
                agent_map[agent_name] = {
                    "status": "idle",
                    "last_activity": row["title"],
                    "last_activity_type": row.get("activity_type"),
                    "last_time": row["created_at"],
                }

        # Ensure all known agents are represented
        for name in KNOWN_AGENTS:
            if name not in agent_map:
                agent_map[name] = {
                    "status": "idle",
                    "last_activity": None,
                    "last_activity_type": None,
                    "last_time": None,
                }

        logger.info(
            "Agent status retrieved",
            extra={"user_id": user_id, "active_agents": len(seen)},
        )
        return agent_map
```

**Step 4: Run all service tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_activity_feed.py -v`
Expected: All PASS

**Step 5: Lint**

Run: `cd /Users/dhruv/aria && ruff check backend/src/services/activity_service.py backend/src/models/activity.py backend/tests/test_activity_feed.py`

**Step 6: Commit**

```bash
git add backend/src/services/activity_service.py backend/tests/test_activity_feed.py
git commit -m "feat(US-940): add ActivityService with record, feed, and agent status"
```

---

### Task 4: FastAPI Routes

**Files:**
- Create: `backend/src/api/routes/activity.py`
- Modify: `backend/src/main.py` (register router)

**Step 1: Write the routes**

Create `backend/src/api/routes/activity.py`:

```python
"""API routes for US-940 Activity Feed / Command Center."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activity", tags=["activity"])


def _get_service() -> ActivityService:
    return ActivityService()


@router.get("")
async def get_activity_feed(
    current_user: CurrentUser,
    agent: str | None = Query(None, description="Filter by agent"),
    activity_type: str | None = Query(None, description="Filter by type"),
    date_start: str | None = Query(None, description="ISO start date"),
    date_end: str | None = Query(None, description="ISO end date"),
    search: str | None = Query(None, description="Search title/description"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Get activity feed with pagination and filters."""
    service = _get_service()
    activities = await service.get_feed(
        user_id=current_user.id,
        agent=agent,
        activity_type=activity_type,
        date_start=date_start,
        date_end=date_end,
        search=search,
        limit=limit,
        offset=offset,
    )
    logger.info(
        "Activity feed requested",
        extra={"user_id": current_user.id, "count": len(activities)},
    )
    return {"activities": activities, "count": len(activities)}


@router.get("/agents")
async def get_agent_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current status of each ARIA agent."""
    service = _get_service()
    status = await service.get_agent_status(current_user.id)
    return {"agents": status}


@router.get("/{activity_id}")
async def get_activity_detail(
    activity_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a single activity with full reasoning chain."""
    service = _get_service()
    activity = await service.get_activity_detail(current_user.id, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.post("")
async def record_activity(
    current_user: CurrentUser,
    agent: str | None = None,
    activity_type: str = "",
    title: str = "",
    description: str = "",
    reasoning: str = "",
    confidence: float = 0.5,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
) -> dict[str, Any]:
    """Record a new activity (internal use by agents)."""
    from src.models.activity import ActivityCreate

    body = ActivityCreate(
        agent=agent,
        activity_type=activity_type,
        title=title,
        description=description,
        reasoning=reasoning,
        confidence=confidence,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    service = _get_service()
    result = await service.record(
        user_id=current_user.id,
        agent=body.agent,
        activity_type=body.activity_type,
        title=body.title,
        description=body.description,
        reasoning=body.reasoning,
        confidence=body.confidence,
        related_entity_type=body.related_entity_type,
        related_entity_id=body.related_entity_id,
        metadata=body.metadata,
    )
    return result
```

**Step 2: Register router in main.py**

In `backend/src/main.py`:
- Add `activity` to the import block: `from src.api.routes import ( ..., activity, ... )`
- Add `app.include_router(activity.router, prefix="/api/v1")` with the other routers

**Step 3: Lint**

Run: `cd /Users/dhruv/aria && ruff check backend/src/api/routes/activity.py backend/src/main.py`
Run: `cd /Users/dhruv/aria && ruff format backend/src/api/routes/activity.py backend/src/main.py`

**Step 4: Commit**

```bash
git add backend/src/api/routes/activity.py backend/src/main.py
git commit -m "feat(US-940): add activity feed API routes and register router"
```

---

### Task 5: Frontend API Client

**Files:**
- Create: `frontend/src/api/activity.ts`

**Step 1: Write the API client**

```typescript
import { apiClient } from "./client";

// --- Types ---

export interface ActivityItem {
  id: string;
  user_id: string;
  agent: string | null;
  activity_type: string;
  title: string;
  description: string;
  reasoning: string;
  confidence: number;
  related_entity_type: string | null;
  related_entity_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ActivityFeedResponse {
  activities: ActivityItem[];
  count: number;
}

export interface ActivityFilters {
  agent?: string;
  activity_type?: string;
  date_start?: string;
  date_end?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface AgentStatusItem {
  status: string;
  last_activity: string | null;
  last_activity_type: string | null;
  last_time: string | null;
}

export interface AgentStatusResponse {
  agents: Record<string, AgentStatusItem>;
}

// --- API functions ---

export async function getActivityFeed(
  filters?: ActivityFilters
): Promise<ActivityFeedResponse> {
  const params = new URLSearchParams();
  if (filters?.agent) params.append("agent", filters.agent);
  if (filters?.activity_type)
    params.append("activity_type", filters.activity_type);
  if (filters?.date_start) params.append("date_start", filters.date_start);
  if (filters?.date_end) params.append("date_end", filters.date_end);
  if (filters?.search) params.append("search", filters.search);
  if (filters?.limit) params.append("limit", filters.limit.toString());
  if (filters?.offset) params.append("offset", filters.offset.toString());

  const url = params.toString() ? `/activity?${params}` : "/activity";
  const response = await apiClient.get<ActivityFeedResponse>(url);
  return response.data;
}

export async function getAgentStatus(): Promise<AgentStatusResponse> {
  const response = await apiClient.get<AgentStatusResponse>(
    "/activity/agents"
  );
  return response.data;
}

export async function getActivityDetail(
  activityId: string
): Promise<ActivityItem> {
  const response = await apiClient.get<ActivityItem>(
    `/activity/${activityId}`
  );
  return response.data;
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/activity.ts
git commit -m "feat(US-940): add frontend API client for activity feed"
```

---

### Task 6: React Query Hooks

**Files:**
- Create: `frontend/src/hooks/useActivity.ts`

**Step 1: Write the hooks**

```typescript
import { useQuery } from "@tanstack/react-query";
import {
  getActivityFeed,
  getAgentStatus,
  getActivityDetail,
} from "@/api/activity";
import type { ActivityFilters } from "@/api/activity";

export const activityKeys = {
  all: ["activity"] as const,
  feed: (filters?: ActivityFilters) =>
    [...activityKeys.all, "feed", filters ?? {}] as const,
  agents: () => [...activityKeys.all, "agents"] as const,
  detail: (id: string) => [...activityKeys.all, "detail", id] as const,
};

export function useActivityFeed(filters?: ActivityFilters) {
  return useQuery({
    queryKey: activityKeys.feed(filters),
    queryFn: () => getActivityFeed(filters),
    refetchInterval: 15_000, // Poll every 15s for real-time updates
  });
}

export function useAgentStatus() {
  return useQuery({
    queryKey: activityKeys.agents(),
    queryFn: () => getAgentStatus(),
    refetchInterval: 10_000, // Poll every 10s
  });
}

export function useActivityDetail(activityId: string) {
  return useQuery({
    queryKey: activityKeys.detail(activityId),
    queryFn: () => getActivityDetail(activityId),
    enabled: !!activityId,
  });
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useActivity.ts
git commit -m "feat(US-940): add React Query hooks for activity feed"
```

---

### Task 7: ActivityFeedPage Component

**Files:**
- Create: `frontend/src/pages/ActivityFeedPage.tsx`
- Modify: `frontend/src/pages/index.ts` (add export)
- Modify: `frontend/src/App.tsx` (add route + import)

This is the main UI component. Key elements:
1. Header with "ARIA Activity" title + filter bar
2. Agent status strip — horizontal row of agent cards
3. Chronological activity stream with infinite scroll (load more button)
4. Each item: agent badge, title, description, timestamp, confidence
5. Click to expand: full reasoning, related entity links
6. Type-specific icons (inline SVGs)
7. Empty state
8. Dark surface Tailwind styling (bg-slate-900/800/700, violet accents)

**Step 1: Write the page component**

Create `frontend/src/pages/ActivityFeedPage.tsx` — full implementation with:
- State: filters (agent, type, search), expanded activity ID, offset for pagination
- `useActivityFeed(filters)` + `useAgentStatus()`
- Agent status strip with pulse animation for recently-active agents
- Filter bar with dropdowns and search input
- Activity list with expand/collapse
- "Load more" button for pagination
- Empty state message
- Relative timestamps (JetBrains Mono)
- Confidence dot indicators (green/yellow/red)

See the code in the implementation step — the full component is ~450 lines of TSX.

**Step 2: Export from pages/index.ts**

Add to `frontend/src/pages/index.ts`:
```typescript
export { ActivityFeedPage } from "./ActivityFeedPage";
```

**Step 3: Register route in App.tsx**

In `frontend/src/App.tsx`:
- Add `ActivityFeedPage` to the import
- Add route:
```tsx
<Route
  path="/activity"
  element={
    <ProtectedRoute>
      <ActivityFeedPage />
    </ProtectedRoute>
  }
/>
```

**Step 4: Typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`

**Step 5: Lint**

Run: `cd /Users/dhruv/aria/frontend && npx eslint src/pages/ActivityFeedPage.tsx src/hooks/useActivity.ts src/api/activity.ts`

**Step 6: Commit**

```bash
git add frontend/src/pages/ActivityFeedPage.tsx frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(US-940): add ActivityFeedPage with agent status, filters, and activity stream"
```

---

### Task 8: Quality Gates

Run all quality checks to verify nothing is broken.

**Step 1: Backend tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_activity_feed.py -v`
Expected: All PASS

**Step 2: Backend lint**

Run: `cd /Users/dhruv/aria && ruff check backend/src/services/activity_service.py backend/src/models/activity.py backend/src/api/routes/activity.py`

**Step 3: Frontend typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`

**Step 4: Frontend lint**

Run: `cd /Users/dhruv/aria/frontend && npx eslint src/pages/ActivityFeedPage.tsx src/hooks/useActivity.ts src/api/activity.ts`

---

## File Summary

**Created:**
- `backend/supabase/migrations/20260208030000_activity_feed.sql`
- `backend/src/models/activity.py`
- `backend/src/services/activity_service.py`
- `backend/src/api/routes/activity.py`
- `backend/tests/test_activity_feed.py`
- `frontend/src/api/activity.ts`
- `frontend/src/hooks/useActivity.ts`
- `frontend/src/pages/ActivityFeedPage.tsx`

**Modified:**
- `backend/src/main.py` (add activity router import + registration)
- `frontend/src/pages/index.ts` (add ActivityFeedPage export)
- `frontend/src/App.tsx` (add import + route)
