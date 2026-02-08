# US-936: Goal Lifecycle Management — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade basic goal CRUD (US-310-312) to full lifecycle management with ARIA collaboration, templates, milestones, retrospectives, and a rich dashboard UI.

**Architecture:** Extend existing GoalService + goals router with new service methods and endpoints. Add `goal_milestones` and `goal_retrospectives` tables. LLM-powered goal creation (ARIA suggests SMART refinements, sub-tasks, agent assignments, timeline). Frontend: rebuild GoalsPage with dashboard view, detail slide-out, creation wizard, templates, and retrospective sections.

**Tech Stack:** Python/FastAPI, Supabase, Claude LLM, React 18, TypeScript, TanStack Query, Tailwind CSS, Lucide React icons.

---

## Existing Foundation (Phase 3 — US-310-312)

| Layer | File | What Exists |
|-------|------|-------------|
| Models | `backend/src/models/goal.py` | GoalType, GoalStatus, GoalCreate, GoalUpdate, GoalResponse |
| Service | `backend/src/services/goal_service.py` | CRUD, start/pause/complete, progress tracking |
| Routes | `backend/src/api/routes/goals.py` | POST/GET/PATCH/DELETE + lifecycle + progress endpoints |
| DB | `backend/supabase/migrations/002_goals_schema.sql` | goals, goal_agents, agent_executions tables |
| API Client | `frontend/src/api/goals.ts` | Typed functions for all existing endpoints |
| Hooks | `frontend/src/hooks/useGoals.ts` | useGoals, useGoal, useGoalProgress, mutations |
| Page | `frontend/src/pages/Goals.tsx` | Grid view with filters, create/delete modals |
| Components | `frontend/src/components/goals/` | GoalCard, ProgressRing, badges, modals, EmptyGoals |
| Tests | `backend/tests/test_goal_service.py` | 16 tests covering all service methods |
| Onboarding | `backend/src/onboarding/first_goal.py` | Templates, SMART validation, agent assignment |

---

## What US-936 Adds

1. **Database:** `goal_milestones` table, `goal_retrospectives` table
2. **Backend Models:** Milestone, Retrospective, GoalDashboard, ARIAGoalSuggestion models
3. **Backend Service:** Dashboard aggregation, ARIA-collaborative creation, milestone CRUD, retrospective generation
4. **Backend Routes:** 5 new endpoints (dashboard, create-with-aria, templates, milestone, retrospective)
5. **Frontend API + Hooks:** New API functions and React Query hooks for all new endpoints
6. **Frontend Page:** Rebuilt GoalsPage with dashboard, detail slide-out, creation wizard, templates, retrospective

---

### Task 1: Database Migration — Milestones & Retrospectives

**Files:**
- Create: `backend/supabase/migrations/20260208_goal_lifecycle.sql`

**Step 1: Write the migration**

```sql
-- US-936: Goal Lifecycle Management - Milestones & Retrospectives

-- Goal milestones for tracking progress within a goal
CREATE TABLE goal_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    due_date TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT goal_milestones_status_check CHECK (status IN ('pending', 'in_progress', 'complete', 'skipped'))
);

-- Goal retrospectives for post-completion analysis
CREATE TABLE goal_retrospectives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    what_worked JSONB DEFAULT '[]',
    what_didnt JSONB DEFAULT '[]',
    time_analysis JSONB DEFAULT '{}',
    agent_effectiveness JSONB DEFAULT '{}',
    learnings JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add new columns to goals table for lifecycle features
ALTER TABLE goals ADD COLUMN IF NOT EXISTS target_date TIMESTAMPTZ;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS health TEXT DEFAULT 'on_track';
ALTER TABLE goals ALTER COLUMN goal_type DROP NOT NULL;
ALTER TABLE goals DROP CONSTRAINT IF EXISTS goals_type_check;
ALTER TABLE goals ADD CONSTRAINT goals_type_check
    CHECK (goal_type IN ('lead_gen', 'research', 'outreach', 'analysis', 'custom', 'meeting_prep', 'competitive_intel', 'territory'));
ALTER TABLE goals ADD CONSTRAINT goals_health_check
    CHECK (health IN ('on_track', 'at_risk', 'behind', 'blocked'));

-- RLS
ALTER TABLE goal_milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE goal_retrospectives ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage milestones for own goals" ON goal_milestones
    FOR ALL USING (goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid()));

CREATE POLICY "Service role can manage milestones" ON goal_milestones
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users can manage retrospectives for own goals" ON goal_retrospectives
    FOR ALL USING (goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid()));

CREATE POLICY "Service role can manage retrospectives" ON goal_retrospectives
    FOR ALL USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_goal_milestones_goal ON goal_milestones(goal_id);
CREATE INDEX idx_goal_milestones_status ON goal_milestones(goal_id, status);
CREATE INDEX idx_goal_retrospectives_goal ON goal_retrospectives(goal_id);
```

**Step 2: Apply migration to remote database**

Run: `cd /Users/dhruv/aria/backend && npx supabase db push`

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260208_goal_lifecycle.sql
git commit -m "feat(US-936): add goal_milestones and goal_retrospectives tables"
```

---

### Task 2: Backend Models — Lifecycle Types

**Files:**
- Modify: `backend/src/models/goal.py`
- Test: `backend/tests/test_goal_schema.py`

**Step 1: Add new types to `backend/src/models/goal.py`**

Add after existing models (after line 111):

```python
class GoalHealth(str, Enum):
    """Health status of a goal."""

    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BEHIND = "behind"
    BLOCKED = "blocked"


class MilestoneStatus(str, Enum):
    """Status of a goal milestone."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"


class MilestoneCreate(BaseModel):
    """Request model for creating a milestone."""

    title: str
    description: str | None = None
    due_date: str | None = None


class MilestoneResponse(BaseModel):
    """Response model for a milestone."""

    id: str
    goal_id: str
    title: str
    description: str | None
    due_date: datetime | None
    completed_at: datetime | None
    status: MilestoneStatus
    sort_order: int
    created_at: datetime


class CreateWithARIARequest(BaseModel):
    """Request model for ARIA-collaborative goal creation."""

    title: str
    description: str | None = None


class ARIAGoalSuggestion(BaseModel):
    """ARIA's suggestions for refining a goal."""

    refined_title: str
    refined_description: str
    smart_score: int = Field(ge=0, le=100)
    sub_tasks: list[dict[str, str]]
    agent_assignments: list[str]
    suggested_timeline_days: int
    reasoning: str


class RetrospectiveResponse(BaseModel):
    """Response model for a goal retrospective."""

    id: str
    goal_id: str
    summary: str
    what_worked: list[str]
    what_didnt: list[str]
    time_analysis: dict[str, Any]
    agent_effectiveness: dict[str, Any]
    learnings: list[str]
    created_at: datetime
    updated_at: datetime
```

Also update `GoalType` to include new types (add after line 20, before `CUSTOM`):

```python
    MEETING_PREP = "meeting_prep"
    COMPETITIVE_INTEL = "competitive_intel"
    TERRITORY = "territory"
```

Also add `target_date` and `health` to `GoalUpdate` (modify the class around line 51):

```python
class GoalUpdate(BaseModel):
    """Request model for updating an existing goal."""

    title: str | None = None
    description: str | None = None
    status: GoalStatus | None = None
    progress: int | None = None
    config: dict[str, Any] | None = None
    target_date: str | None = None
    health: GoalHealth | None = None

    @field_validator("progress")
    @classmethod
    def validate_progress(cls, v: int | None) -> int | None:
        """Validate that progress is between 0 and 100."""
        if v is not None and (v < 0 or v > 100):
            raise ValueError("progress must be between 0 and 100")
        return v
```

**Step 2: Write tests for new models in `backend/tests/test_goal_schema.py`**

Add tests for GoalHealth enum values, MilestoneStatus enum values, MilestoneCreate validation, CreateWithARIARequest validation, ARIAGoalSuggestion field constraints.

**Step 3: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_goal_schema.py -v`

**Step 4: Run type checking**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/models/goal.py --strict`

**Step 5: Commit**

```bash
git add backend/src/models/goal.py backend/tests/test_goal_schema.py
git commit -m "feat(US-936): add lifecycle models — milestones, retrospectives, ARIA suggestions"
```

---

### Task 3: Backend Service — Goal Lifecycle Methods

**Files:**
- Modify: `backend/src/services/goal_service.py`
- Test: `backend/tests/test_goal_lifecycle_service.py` (create)

**Step 1: Write failing tests for new service methods**

Create `backend/tests/test_goal_lifecycle_service.py` with tests for:
- `get_dashboard(user_id)` → returns goals with milestone counts, health
- `create_with_aria(user_id, title, description)` → calls LLM, returns suggestion
- `get_templates(role)` → returns templates filtered by role
- `add_milestone(user_id, goal_id, data)` → creates milestone in DB
- `complete_milestone(user_id, goal_id, milestone_id)` → sets completed_at
- `generate_retrospective(user_id, goal_id)` → calls LLM for retrospective, stores in DB
- `get_goal_detail(user_id, goal_id)` → returns goal + milestones + retrospective

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_goal_lifecycle_service.py -v`

**Step 3: Implement service methods**

Add to `GoalService` in `backend/src/services/goal_service.py`:

```python
async def get_dashboard(self, user_id: str) -> list[dict[str, Any]]:
    """Get all goals with milestone counts for dashboard view."""
    result = (
        self._db.table("goals")
        .select("*, goal_agents(*), goal_milestones(*)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    goals = cast(list[dict[str, Any]], result.data)
    # Compute milestone summary per goal
    for goal in goals:
        milestones = goal.get("goal_milestones", [])
        goal["milestone_total"] = len(milestones)
        goal["milestone_complete"] = sum(
            1 for m in milestones if m.get("status") == "complete"
        )
    return goals

async def create_with_aria(
    self, user_id: str, title: str, description: str | None
) -> dict[str, Any]:
    """Use LLM to suggest SMART refinements, sub-tasks, and timeline."""
    from src.core.llm import LLMClient
    llm = LLMClient()
    prompt = f"""You are ARIA, an AI sales assistant. A user wants to create a goal.

Title: {title}
Description: {description or 'None provided'}

Suggest:
1. A refined SMART version of this goal (Specific, Measurable, Achievable, Relevant, Time-bound)
2. 3-5 concrete sub-tasks to achieve this goal
3. Which ARIA agents should be assigned (from: hunter, analyst, strategist, scribe, operator, scout)
4. A realistic timeline in days

Respond with JSON only:
{{
    "refined_title": "...",
    "refined_description": "...",
    "smart_score": 0-100,
    "sub_tasks": [{{"title": "...", "description": "..."}}],
    "agent_assignments": ["analyst", "hunter"],
    "suggested_timeline_days": 14,
    "reasoning": "Brief explanation of suggestions"
}}"""

    import json
    response = await llm.generate_response(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        temperature=0.4,
    )
    try:
        suggestion = json.loads(response)
    except json.JSONDecodeError:
        suggestion = {
            "refined_title": title,
            "refined_description": description or "",
            "smart_score": 50,
            "sub_tasks": [{"title": "Define success criteria", "description": "Clarify what completion looks like"}],
            "agent_assignments": ["analyst"],
            "suggested_timeline_days": 14,
            "reasoning": "Unable to parse AI suggestions. Default provided.",
        }
    return suggestion

def get_templates(self, role: str | None = None) -> list[dict[str, Any]]:
    """Get goal templates, optionally filtered by role."""
    from src.onboarding.first_goal import FirstGoalService
    service = FirstGoalService.__new__(FirstGoalService)
    raw = service.TEMPLATES
    templates: list[dict[str, Any]] = []
    for _category, items in raw.items():
        for t in items:
            if role is None or any(role.lower() in r.lower() for r in t.applicable_roles):
                templates.append(t.model_dump())
    return templates

async def add_milestone(
    self, user_id: str, goal_id: str, title: str, description: str | None = None, due_date: str | None = None
) -> dict[str, Any] | None:
    """Add a milestone to a goal."""
    # Verify goal ownership
    goal = await self.get_goal(user_id, goal_id)
    if not goal:
        return None
    # Get current max sort_order
    existing = (
        self._db.table("goal_milestones")
        .select("sort_order")
        .eq("goal_id", goal_id)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    next_order = (existing.data[0]["sort_order"] + 1) if existing.data else 0
    insert_data: dict[str, Any] = {
        "goal_id": goal_id,
        "title": title,
        "description": description,
        "sort_order": next_order,
        "status": "pending",
    }
    if due_date:
        insert_data["due_date"] = due_date
    result = self._db.table("goal_milestones").insert(insert_data).execute()
    return cast(dict[str, Any], result.data[0])

async def complete_milestone(
    self, user_id: str, goal_id: str, milestone_id: str
) -> dict[str, Any] | None:
    """Mark a milestone as complete."""
    goal = await self.get_goal(user_id, goal_id)
    if not goal:
        return None
    now = datetime.now(UTC).isoformat()
    result = (
        self._db.table("goal_milestones")
        .update({"status": "complete", "completed_at": now})
        .eq("id", milestone_id)
        .eq("goal_id", goal_id)
        .execute()
    )
    if result.data:
        return cast(dict[str, Any], result.data[0])
    return None

async def generate_retrospective(
    self, user_id: str, goal_id: str
) -> dict[str, Any] | None:
    """Generate a retrospective for a completed/abandoned goal using LLM."""
    goal = await self.get_goal(user_id, goal_id)
    if not goal:
        return None
    # Get milestones for analysis
    milestones_result = (
        self._db.table("goal_milestones")
        .select("*")
        .eq("goal_id", goal_id)
        .order("sort_order")
        .execute()
    )
    milestones = milestones_result.data or []
    # Get agent executions
    agents = goal.get("goal_agents", [])
    executions: list[dict[str, Any]] = []
    for agent in agents:
        exec_result = (
            self._db.table("agent_executions")
            .select("*")
            .eq("goal_agent_id", agent["id"])
            .execute()
        )
        executions.extend(cast(list[dict[str, Any]], exec_result.data))

    from src.core.llm import LLMClient
    import json
    llm = LLMClient()
    prompt = f"""Analyze this completed goal and generate a retrospective.

Goal: {goal.get('title')}
Description: {goal.get('description', 'None')}
Status: {goal.get('status')}
Created: {goal.get('created_at')}
Completed: {goal.get('completed_at', 'Not yet')}
Progress: {goal.get('progress')}%
Milestones: {len(milestones)} total, {sum(1 for m in milestones if m.get('status') == 'complete')} completed
Agent executions: {len(executions)}

Provide a JSON retrospective:
{{
    "summary": "1-2 sentence summary",
    "what_worked": ["item1", "item2"],
    "what_didnt": ["item1"],
    "time_analysis": {{"estimated_days": null, "actual_days": null, "on_time": true}},
    "agent_effectiveness": {{"agents_used": [], "most_effective": null, "notes": ""}},
    "learnings": ["key learning 1", "key learning 2"]
}}"""

    response = await llm.generate_response(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.4,
    )
    try:
        retro_data = json.loads(response)
    except json.JSONDecodeError:
        retro_data = {
            "summary": f"Goal '{goal.get('title')}' has been reviewed.",
            "what_worked": [],
            "what_didnt": [],
            "time_analysis": {},
            "agent_effectiveness": {},
            "learnings": ["Retrospective generation encountered an issue. Review manually."],
        }

    # Upsert retrospective
    result = (
        self._db.table("goal_retrospectives")
        .upsert({
            "goal_id": goal_id,
            "summary": retro_data["summary"],
            "what_worked": retro_data.get("what_worked", []),
            "what_didnt": retro_data.get("what_didnt", []),
            "time_analysis": retro_data.get("time_analysis", {}),
            "agent_effectiveness": retro_data.get("agent_effectiveness", {}),
            "learnings": retro_data.get("learnings", []),
        }, on_conflict="goal_id")
        .execute()
    )
    return cast(dict[str, Any], result.data[0]) if result.data else None

async def get_goal_detail(
    self, user_id: str, goal_id: str
) -> dict[str, Any] | None:
    """Get full goal detail including milestones and retrospective."""
    goal = await self.get_goal(user_id, goal_id)
    if not goal:
        return None
    # Get milestones
    milestones_result = (
        self._db.table("goal_milestones")
        .select("*")
        .eq("goal_id", goal_id)
        .order("sort_order")
        .execute()
    )
    goal["milestones"] = milestones_result.data or []
    # Get retrospective if exists
    retro_result = (
        self._db.table("goal_retrospectives")
        .select("*")
        .eq("goal_id", goal_id)
        .maybe_single()
        .execute()
    )
    goal["retrospective"] = retro_result.data if retro_result and retro_result.data else None
    return goal
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_goal_lifecycle_service.py -v`

**Step 5: Run quality gates**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/services/goal_service.py --strict && ruff check src/services/goal_service.py`

**Step 6: Commit**

```bash
git add backend/src/services/goal_service.py backend/tests/test_goal_lifecycle_service.py
git commit -m "feat(US-936): add lifecycle service methods — dashboard, ARIA collab, milestones, retrospectives"
```

---

### Task 4: Backend Routes — New Endpoints

**Files:**
- Modify: `backend/src/api/routes/goals.py`
- Test: `backend/tests/test_goal_lifecycle_routes.py` (create)

**Step 1: Write failing route tests**

Create `backend/tests/test_goal_lifecycle_routes.py` with tests for:
- `GET /goals/dashboard` returns goals with milestone counts
- `POST /goals/create-with-aria` calls LLM, returns suggestion
- `GET /goals/templates` returns templates, optional `?role=sales` filter
- `POST /goals/{id}/milestone` creates milestone
- `POST /goals/{id}/retrospective` generates retrospective
- `GET /goals/{id}/detail` returns full goal detail

**Step 2: Add new endpoints to `backend/src/api/routes/goals.py`**

Add BEFORE the `/{goal_id}` route (to avoid path conflicts — FastAPI matches routes in order, so `/dashboard`, `/templates`, `/create-with-aria` must come before `/{goal_id}`):

```python
from src.models.goal import (
    GoalCreate, GoalStatus, GoalUpdate,
    MilestoneCreate, CreateWithARIARequest,
)

# --- US-936: Goal Lifecycle Endpoints ---

@router.get("/dashboard")
async def get_dashboard(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get all goals with health, progress, and milestone counts."""
    service = _get_service()
    return await service.get_dashboard(current_user.id)


@router.post("/create-with-aria")
async def create_with_aria(
    data: CreateWithARIARequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get ARIA's suggestions for a goal before creating it."""
    service = _get_service()
    return await service.create_with_aria(
        current_user.id, data.title, data.description
    )


@router.get("/templates")
async def get_templates(
    current_user: CurrentUser,
    role: str | None = Query(None, description="Filter templates by role"),
) -> list[dict[str, Any]]:
    """Get goal templates, optionally filtered by role."""
    service = _get_service()
    return service.get_templates(role)


# --- These go AFTER the existing /{goal_id} routes ---

@router.get("/{goal_id}/detail")
async def get_goal_detail(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get full goal detail with milestones and retrospective."""
    service = _get_service()
    detail = await service.get_goal_detail(current_user.id, goal_id)
    if detail is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Goal not found")
    return detail


@router.post("/{goal_id}/milestone")
async def add_milestone(
    goal_id: str,
    data: MilestoneCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Add a milestone to a goal."""
    service = _get_service()
    milestone = await service.add_milestone(
        current_user.id, goal_id, data.title, data.description, data.due_date
    )
    if milestone is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Goal not found")
    return milestone


@router.post("/{goal_id}/retrospective")
async def generate_retrospective(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate a retrospective for a completed goal."""
    service = _get_service()
    retro = await service.generate_retrospective(current_user.id, goal_id)
    if retro is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Goal not found")
    return retro
```

**Step 3: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_goal_lifecycle_routes.py -v`

**Step 4: Run quality gates**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/api/routes/goals.py --strict && ruff check src/api/routes/goals.py`

**Step 5: Commit**

```bash
git add backend/src/api/routes/goals.py backend/tests/test_goal_lifecycle_routes.py
git commit -m "feat(US-936): add lifecycle API routes — dashboard, ARIA collab, milestones, retrospective"
```

---

### Task 5: Frontend API Client & Hooks — New Functions

**Files:**
- Modify: `frontend/src/api/goals.ts`
- Modify: `frontend/src/hooks/useGoals.ts`

**Step 1: Add new types and API functions to `frontend/src/api/goals.ts`**

Add after existing types:

```typescript
// US-936: Lifecycle types
export type GoalHealth = "on_track" | "at_risk" | "behind" | "blocked";
export type MilestoneStatus = "pending" | "in_progress" | "complete" | "skipped";

export interface Milestone {
  id: string;
  goal_id: string;
  title: string;
  description: string | null;
  due_date: string | null;
  completed_at: string | null;
  status: MilestoneStatus;
  sort_order: number;
  created_at: string;
}

export interface Retrospective {
  id: string;
  goal_id: string;
  summary: string;
  what_worked: string[];
  what_didnt: string[];
  time_analysis: Record<string, unknown>;
  agent_effectiveness: Record<string, unknown>;
  learnings: string[];
  created_at: string;
  updated_at: string;
}

export interface GoalDashboard extends Goal {
  goal_milestones?: Milestone[];
  milestone_total: number;
  milestone_complete: number;
}

export interface GoalDetail extends Goal {
  milestones: Milestone[];
  retrospective: Retrospective | null;
}

export interface ARIAGoalSuggestion {
  refined_title: string;
  refined_description: string;
  smart_score: number;
  sub_tasks: Array<{ title: string; description: string }>;
  agent_assignments: string[];
  suggested_timeline_days: number;
  reasoning: string;
}

export interface GoalTemplate {
  title: string;
  description: string;
  category: string;
  goal_type: GoalType;
  applicable_roles: string[];
}
```

Add new API functions:

```typescript
export async function getDashboard(): Promise<GoalDashboard[]> {
  const response = await apiClient.get<GoalDashboard[]>("/goals/dashboard");
  return response.data;
}

export async function createWithARIA(
  title: string,
  description?: string
): Promise<ARIAGoalSuggestion> {
  const response = await apiClient.post<ARIAGoalSuggestion>(
    "/goals/create-with-aria",
    { title, description }
  );
  return response.data;
}

export async function getTemplates(role?: string): Promise<GoalTemplate[]> {
  const params = role ? `?role=${role}` : "";
  const response = await apiClient.get<GoalTemplate[]>(`/goals/templates${params}`);
  return response.data;
}

export async function getGoalDetail(goalId: string): Promise<GoalDetail> {
  const response = await apiClient.get<GoalDetail>(`/goals/${goalId}/detail`);
  return response.data;
}

export async function addMilestone(
  goalId: string,
  data: { title: string; description?: string; due_date?: string }
): Promise<Milestone> {
  const response = await apiClient.post<Milestone>(
    `/goals/${goalId}/milestone`,
    data
  );
  return response.data;
}

export async function generateRetrospective(
  goalId: string
): Promise<Retrospective> {
  const response = await apiClient.post<Retrospective>(
    `/goals/${goalId}/retrospective`
  );
  return response.data;
}
```

**Step 2: Add new hooks to `frontend/src/hooks/useGoals.ts`**

```typescript
import {
  // ... existing imports ...
  getDashboard,
  createWithARIA,
  getTemplates,
  getGoalDetail,
  addMilestone,
  generateRetrospective,
  type GoalDetail,
} from "@/api/goals";

// Add to goalKeys:
export const goalKeys = {
  // ... existing keys ...
  dashboard: () => [...goalKeys.all, "dashboard"] as const,
  templates: (role?: string) => [...goalKeys.all, "templates", { role }] as const,
  goalDetail: (id: string) => [...goalKeys.details(), id, "full"] as const,
};

// Dashboard query
export function useGoalDashboard() {
  return useQuery({
    queryKey: goalKeys.dashboard(),
    queryFn: () => getDashboard(),
  });
}

// Templates query
export function useGoalTemplates(role?: string) {
  return useQuery({
    queryKey: goalKeys.templates(role),
    queryFn: () => getTemplates(role),
  });
}

// Goal detail query (includes milestones + retrospective)
export function useGoalDetail(goalId: string) {
  return useQuery({
    queryKey: goalKeys.goalDetail(goalId),
    queryFn: () => getGoalDetail(goalId),
    enabled: !!goalId,
  });
}

// ARIA collaboration mutation
export function useCreateWithARIA() {
  return useMutation({
    mutationFn: ({ title, description }: { title: string; description?: string }) =>
      createWithARIA(title, description),
  });
}

// Add milestone mutation
export function useAddMilestone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      goalId,
      data,
    }: {
      goalId: string;
      data: { title: string; description?: string; due_date?: string };
    }) => addMilestone(goalId, data),
    onSuccess: (_data, { goalId }) => {
      queryClient.invalidateQueries({ queryKey: goalKeys.goalDetail(goalId) });
      queryClient.invalidateQueries({ queryKey: goalKeys.dashboard() });
    },
  });
}

// Generate retrospective mutation
export function useGenerateRetrospective() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) => generateRetrospective(goalId),
    onSuccess: (_data, goalId) => {
      queryClient.invalidateQueries({ queryKey: goalKeys.goalDetail(goalId) });
    },
  });
}
```

**Step 3: Run type checking**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`

**Step 4: Commit**

```bash
git add frontend/src/api/goals.ts frontend/src/hooks/useGoals.ts
git commit -m "feat(US-936): add lifecycle API client and React Query hooks"
```

---

### Task 6: Frontend — Goal Detail Slide-Out Component

**Files:**
- Create: `frontend/src/components/goals/GoalDetailPanel.tsx`
- Modify: `frontend/src/components/goals/index.ts`

**Step 1: Create GoalDetailPanel**

A right slide-out panel that shows:
- Goal title (editable), description (editable)
- Health indicator badge
- Progress ring + percentage
- Milestone checklist with add button
- Agent assignments
- Retrospective section (shown for complete/failed goals)

Pattern: Fixed right panel (`right-0 w-[480px]`) with backdrop, ESC to close. Uses `useGoalDetail` hook. Milestones shown as checklist items with completion toggle. Retrospective shown as summary cards.

Use Lucide icons: `Target`, `CheckCircle2`, `Circle`, `Plus`, `X`, `Clock`, `AlertTriangle`, `TrendingUp`.

**Step 2: Export from barrel**

Add to `frontend/src/components/goals/index.ts`:
```typescript
export { GoalDetailPanel } from "./GoalDetailPanel";
```

**Step 3: Run type checking**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`

**Step 4: Commit**

```bash
git add frontend/src/components/goals/GoalDetailPanel.tsx frontend/src/components/goals/index.ts
git commit -m "feat(US-936): add GoalDetailPanel slide-out component"
```

---

### Task 7: Frontend — Goal Creation Wizard with ARIA Collaboration

**Files:**
- Create: `frontend/src/components/goals/GoalCreationWizard.tsx`
- Modify: `frontend/src/components/goals/index.ts`

**Step 1: Create GoalCreationWizard**

A 3-step modal wizard:
1. **Step 1 — Input**: Title + description fields + optional template selection
2. **Step 2 — ARIA Suggestions**: Shows ARIA's refined SMART version, sub-tasks, agent assignments, timeline. User can accept/edit each. Uses `useCreateWithARIA` mutation.
3. **Step 3 — Confirm**: Summary of final goal. "Create Goal" button calls `useCreateGoal` with refined data.

Loading state during ARIA processing: "ARIA is analyzing your goal..." with subtle `aria-breathe` animation.

Template cards shown as a horizontal scrollable row with category labels.

**Step 2: Export from barrel**

Add to `frontend/src/components/goals/index.ts`:
```typescript
export { GoalCreationWizard } from "./GoalCreationWizard";
```

**Step 3: Run type checking**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`

**Step 4: Commit**

```bash
git add frontend/src/components/goals/GoalCreationWizard.tsx frontend/src/components/goals/index.ts
git commit -m "feat(US-936): add GoalCreationWizard with ARIA collaboration"
```

---

### Task 8: Frontend — Rebuild GoalsPage as Dashboard

**Files:**
- Modify: `frontend/src/pages/Goals.tsx`

**Step 1: Rebuild GoalsPage**

Replace current simple grid with full dashboard:

1. **Header**: "Goals" (font-display/Instrument Serif, text-3xl) + "New Goal" primary button
2. **Summary stats row**: Total goals, Active, Completed, At Risk (4 cards in a row)
3. **Filter tabs**: All / Active / Draft / Paused / Complete / Failed (same pattern as existing)
4. **View toggle**: Grid / List (small buttons in header)
5. **Goal cards grid** (2-col on md):
   - Enhanced GoalCard with health indicator, milestone progress bar, target date
   - Click card → opens GoalDetailPanel slide-out
6. **GoalCreationWizard** modal (replaces CreateGoalModal)
7. **GoalDetailPanel** slide-out

Replace existing `CreateGoalModal` usage with `GoalCreationWizard`. Keep `DeleteGoalModal`. Use `useGoalDashboard()` instead of `useGoals()`.

**Step 2: Run type checking**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`

**Step 3: Commit**

```bash
git add frontend/src/pages/Goals.tsx
git commit -m "feat(US-936): rebuild GoalsPage as full lifecycle dashboard"
```

---

### Task 9: Frontend — GoalCard Enhancement

**Files:**
- Modify: `frontend/src/components/goals/GoalCard.tsx`

**Step 1: Enhance GoalCard**

Add to GoalCard:
- Health indicator dot (green/amber/red) next to status badge
- Milestone progress bar (thin bar below description): `milestone_complete / milestone_total`
- Target date display with "X days left" or "Overdue" text
- Click handler wired to open detail panel

Add `GoalHealthBadge` inline (small colored dot + text):
- on_track → green
- at_risk → amber
- behind → red
- blocked → slate with strikethrough

**Step 2: Run type checking**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`

**Step 3: Commit**

```bash
git add frontend/src/components/goals/GoalCard.tsx
git commit -m "feat(US-936): enhance GoalCard with health, milestones, target date"
```

---

### Task 10: Quality Gates & Final Verification

**Files:**
- All modified files

**Step 1: Run all backend tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_goal_service.py tests/test_goal_schema.py tests/test_goal_lifecycle_service.py tests/test_goal_lifecycle_routes.py -v`
Expected: All pass.

**Step 2: Run backend type checking**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/models/goal.py src/services/goal_service.py src/api/routes/goals.py --strict`

**Step 3: Run backend linting**

Run: `cd /Users/dhruv/aria/backend && ruff check src/models/goal.py src/services/goal_service.py src/api/routes/goals.py && ruff format --check src/models/goal.py src/services/goal_service.py src/api/routes/goals.py`

**Step 4: Run frontend type checking**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`

**Step 5: Run frontend linting**

Run: `cd /Users/dhruv/aria/frontend && npm run lint`

**Step 6: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(US-936): quality gate fixes"
```
