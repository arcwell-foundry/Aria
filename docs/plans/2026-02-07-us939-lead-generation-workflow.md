# US-939: Lead Generation Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a complete lead generation pipeline from ICP definition through Hunter agent discovery, lead review queue, scoring explainability, pipeline visualization, and outreach initiation.

**Architecture:** Extends existing Lead Memory system (leads.py routes, hunter.py agent, lead_memory.py models) with a new lead generation layer. New `LeadGenerationService` orchestrates ICP storage, Hunter agent invocation, discovered lead management, and outreach drafting. New `LeadGenPage` provides ICP Builder, Review Queue, and Pipeline View tabs. All new endpoints go on the existing `/leads` router — no new router registration needed.

**Tech Stack:** Python 3.11+ / FastAPI / Pydantic, Supabase (PostgreSQL + RLS), React 18 / TypeScript / Tailwind CSS 4, React Query, Recharts, Lucide React icons

---

## File Structure

```
backend/src/models/
├── lead_generation.py                  # NEW: Pydantic models for ICP, discovery, pipeline

backend/src/core/
├── lead_generation.py                  # NEW: LeadGenerationService class

backend/src/api/routes/
├── leads.py                            # MODIFY: Add 7 new endpoints

backend/supabase/migrations/
├── 20260207170000_lead_generation.sql  # NEW: lead_icp_profiles + discovered_leads tables

backend/tests/
├── test_lead_generation.py             # NEW: Service + API tests

frontend/src/api/
├── leadGeneration.ts                   # NEW: API client functions

frontend/src/hooks/
├── useLeadGeneration.ts                # NEW: React Query hooks

frontend/src/pages/
├── LeadGenPage.tsx                     # NEW: Main page with tabs
├── index.ts                            # MODIFY: Add LeadGenPage export

frontend/src/components/leads/
├── ICPBuilder.tsx                      # NEW: ICP form with tag inputs
├── LeadReviewQueue.tsx                 # NEW: Review cards with actions
├── PipelineView.tsx                    # NEW: Recharts funnel + stage cards
├── ScoreBreakdown.tsx                  # NEW: Score detail panel
├── OutreachModal.tsx                   # NEW: Compose outreach modal

frontend/src/App.tsx                    # MODIFY: Add /leads route
```

---

## Task 1: Database Migration

**Files:**
- Create: `backend/supabase/migrations/20260207170000_lead_generation.sql`

**Step 1: Write the migration**

```sql
-- US-939: Lead Generation Workflow
-- Tables for ICP profiles and discovered leads

-- ICP Profiles: One active ICP per user
CREATE TABLE lead_icp_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    icp_data JSONB NOT NULL DEFAULT '{}',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_icp_profiles_user ON lead_icp_profiles(user_id);

ALTER TABLE lead_icp_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_icp_profiles" ON lead_icp_profiles
    FOR ALL TO authenticated USING (user_id = auth.uid());

-- Discovered Leads: Leads found by Hunter agent pending review
CREATE TABLE discovered_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    icp_id UUID REFERENCES lead_icp_profiles(id),
    company_name TEXT NOT NULL,
    company_data JSONB NOT NULL DEFAULT '{}',
    contacts JSONB NOT NULL DEFAULT '[]',
    fit_score INT NOT NULL DEFAULT 0 CHECK (fit_score >= 0 AND fit_score <= 100),
    score_breakdown JSONB NOT NULL DEFAULT '{}',
    signals JSONB NOT NULL DEFAULT '[]',
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'approved', 'rejected', 'saved')),
    reviewed_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'hunter_agent',
    lead_memory_id UUID REFERENCES lead_memories(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_discovered_leads_user ON discovered_leads(user_id);
CREATE INDEX idx_discovered_leads_status ON discovered_leads(user_id, review_status);
CREATE INDEX idx_discovered_leads_score ON discovered_leads(user_id, fit_score DESC);

ALTER TABLE discovered_leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_discovered_leads" ON discovered_leads
    FOR ALL TO authenticated USING (user_id = auth.uid());
```

**Step 2: Commit**

```bash
git add backend/supabase/migrations/20260207170000_lead_generation.sql
git commit -m "feat(US-939): add lead generation database migration"
```

---

## Task 2: Backend Pydantic Models

**Files:**
- Create: `backend/src/models/lead_generation.py`

**Step 1: Write the models**

```python
"""Lead generation workflow models (US-939).

Pydantic models for ICP definition, discovered leads,
score breakdowns, pipeline views, and outreach.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SAVED = "saved"


class PipelineStage(str, Enum):
    PROSPECT = "prospect"
    QUALIFIED = "qualified"
    OPPORTUNITY = "opportunity"
    CUSTOMER = "customer"


# ICP Models
class ICPDefinition(BaseModel):
    industry: list[str] = Field(default_factory=list)
    company_size: dict[str, int] = Field(
        default_factory=lambda: {"min": 0, "max": 0}
    )
    modalities: list[str] = Field(default_factory=list)
    therapeutic_areas: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class ICPResponse(BaseModel):
    id: str
    user_id: str
    icp_data: ICPDefinition
    version: int
    created_at: datetime
    updated_at: datetime


# Score Breakdown
class ScoreFactor(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    explanation: str


class LeadScoreBreakdown(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    factors: list[ScoreFactor]


# Discovered Lead Models
class DiscoveredLeadResponse(BaseModel):
    id: str
    user_id: str
    icp_id: str | None
    company_name: str
    company_data: dict[str, object]
    contacts: list[dict[str, object]]
    fit_score: int
    score_breakdown: LeadScoreBreakdown | None
    signals: list[str]
    review_status: ReviewStatus
    reviewed_at: datetime | None
    source: str
    lead_memory_id: str | None
    created_at: datetime
    updated_at: datetime


class LeadReviewRequest(BaseModel):
    action: ReviewStatus = Field(
        ..., description="Review action: approved, rejected, or saved"
    )


# Pipeline Models
class PipelineStageSummary(BaseModel):
    stage: PipelineStage
    count: int
    total_value: float


class PipelineSummary(BaseModel):
    stages: list[PipelineStageSummary]
    total_leads: int
    total_pipeline_value: float


# Outreach Models
class OutreachRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    tone: str = Field(default="professional")


class OutreachResponse(BaseModel):
    id: str
    lead_id: str
    draft_subject: str
    draft_body: str
    status: str
    created_at: datetime


# Discovery trigger
class DiscoverLeadsRequest(BaseModel):
    target_count: int = Field(default=10, ge=1, le=50)
```

**Step 2: Run quality checks**

```bash
cd backend && ruff check src/models/lead_generation.py && ruff format src/models/lead_generation.py && mypy src/models/lead_generation.py --strict
```

**Step 3: Commit**

```bash
git add backend/src/models/lead_generation.py
git commit -m "feat(US-939): add lead generation Pydantic models"
```

---

## Task 3: Backend LeadGenerationService

**Files:**
- Create: `backend/src/core/lead_generation.py`

**Step 1: Write the service**

The service needs these methods:
- `save_icp(user_id, icp_data) -> ICPResponse` — upsert ICP in `lead_icp_profiles`
- `get_icp(user_id) -> ICPResponse | None` — fetch current ICP
- `discover_leads(user_id, icp_id, target_count) -> list[DiscoveredLeadResponse]` — run Hunter agent, store results in `discovered_leads`
- `list_discovered(user_id, status_filter) -> list[DiscoveredLeadResponse]` — list discovered leads
- `review_lead(user_id, lead_id, action) -> DiscoveredLeadResponse` — approve/reject/save; approved creates Lead Memory entry
- `get_score_explanation(user_id, lead_id) -> LeadScoreBreakdown` — return score breakdown
- `get_pipeline(user_id) -> PipelineSummary` — aggregate by pipeline stage
- `initiate_outreach(user_id, lead_id, request) -> OutreachResponse` — create outreach draft

Key patterns to follow:
- Instantiate service with `LeadGenerationService()` (no constructor args), like `LeadMemoryService()`
- Use `from src.db.supabase import get_supabase_client` for database access
- Use `from src.agents.hunter import HunterAgent` for lead discovery
- Async methods throughout
- Logging via `logging.getLogger(__name__)`

When reviewing a lead as "approved":
1. Create a new Lead Memory entry via `LeadMemoryService().create()`
2. Store the resulting `lead_memory_id` back on the discovered lead record

Pipeline aggregation queries `lead_memories` table grouped by lifecycle_stage, summing expected_value.

**Step 2: Run quality checks**

```bash
cd backend && ruff check src/core/lead_generation.py && ruff format src/core/lead_generation.py && mypy src/core/lead_generation.py --strict
```

**Step 3: Commit**

```bash
git add backend/src/core/lead_generation.py
git commit -m "feat(US-939): add LeadGenerationService with ICP, discovery, review, pipeline"
```

---

## Task 4: Backend API Endpoints

**Files:**
- Modify: `backend/src/api/routes/leads.py` — add 7 new endpoints at the end of file

**Step 1: Add new imports and endpoints**

Add to existing imports in leads.py:
```python
from src.core.lead_generation import LeadGenerationService
from src.models.lead_generation import (
    DiscoverLeadsRequest,
    DiscoveredLeadResponse,
    ICPDefinition,
    ICPResponse,
    LeadReviewRequest,
    LeadScoreBreakdown,
    OutreachRequest,
    OutreachResponse,
    PipelineSummary,
    ReviewStatus,
)
```

New endpoints (add at end of file):

```python
# --- Lead Generation Workflow (US-939) ---

@router.post("/icp", response_model=ICPResponse)
async def save_icp(
    current_user: CurrentUser,
    icp: ICPDefinition,
) -> ICPResponse:
    """Save or update the user's Ideal Customer Profile."""
    service = LeadGenerationService()
    return await service.save_icp(current_user.id, icp)


@router.get("/icp", response_model=ICPResponse | None)
async def get_icp(current_user: CurrentUser) -> ICPResponse | None:
    """Get the current user's ICP."""
    service = LeadGenerationService()
    return await service.get_icp(current_user.id)


@router.post("/discovered", response_model=list[DiscoveredLeadResponse])
async def discover_leads(
    current_user: CurrentUser,
    request: DiscoverLeadsRequest,
) -> list[DiscoveredLeadResponse]:
    """Trigger Hunter agent to discover leads matching the user's ICP."""
    service = LeadGenerationService()
    icp = await service.get_icp(current_user.id)
    if not icp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ICP defined. Create an ICP first.",
        )
    return await service.discover_leads(
        current_user.id, icp.id, request.target_count
    )


@router.get("/discovered", response_model=list[DiscoveredLeadResponse])
async def list_discovered_leads(
    current_user: CurrentUser,
    review_status: str | None = Query(None, description="Filter by review status"),
) -> list[DiscoveredLeadResponse]:
    """List discovered leads, optionally filtered by review status."""
    status_filter = None
    if review_status:
        try:
            status_filter = ReviewStatus(review_status)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid review status: {review_status}",
            ) from e
    service = LeadGenerationService()
    return await service.list_discovered(current_user.id, status_filter)


@router.post("/{lead_id}/review", response_model=DiscoveredLeadResponse)
async def review_lead(
    lead_id: str,
    current_user: CurrentUser,
    request: LeadReviewRequest,
) -> DiscoveredLeadResponse:
    """Review a discovered lead: approve, reject, or save for later."""
    service = LeadGenerationService()
    result = await service.review_lead(current_user.id, lead_id, request.action)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovered lead not found",
        )
    return result


@router.get("/{lead_id}/score-explanation", response_model=LeadScoreBreakdown)
async def get_score_explanation(
    lead_id: str,
    current_user: CurrentUser,
) -> LeadScoreBreakdown:
    """Get a detailed score breakdown for a discovered lead."""
    service = LeadGenerationService()
    result = await service.get_score_explanation(current_user.id, lead_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovered lead not found",
        )
    return result


@router.get("/pipeline", response_model=PipelineSummary)
async def get_pipeline(current_user: CurrentUser) -> PipelineSummary:
    """Get pipeline funnel view with stage counts and values."""
    service = LeadGenerationService()
    return await service.get_pipeline(current_user.id)


@router.post("/outreach/{lead_id}", response_model=OutreachResponse)
async def initiate_outreach(
    lead_id: str,
    current_user: CurrentUser,
    request: OutreachRequest,
) -> OutreachResponse:
    """Initiate outreach for a lead, creating a draft via Scribe agent."""
    service = LeadGenerationService()
    result = await service.initiate_outreach(current_user.id, lead_id, request)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    return result
```

**IMPORTANT:** The new `/{lead_id}/review` and `/{lead_id}/score-explanation` endpoints must be placed AFTER the existing `/{lead_id}` GET endpoint but the static routes (`/icp`, `/discovered`, `/pipeline`) must be placed BEFORE any `/{lead_id}` routes to avoid path conflicts. FastAPI matches routes in order — `/icp` would match `/{lead_id}` if `/{lead_id}` comes first.

**Step 2: Run quality checks**

```bash
cd backend && ruff check src/api/routes/leads.py && ruff format src/api/routes/leads.py && mypy src/api/routes/leads.py --strict
```

**Step 3: Commit**

```bash
git add backend/src/api/routes/leads.py
git commit -m "feat(US-939): add lead generation API endpoints to leads router"
```

---

## Task 5: Backend Tests

**Files:**
- Create: `backend/tests/test_lead_generation.py`

**Step 1: Write comprehensive tests**

Test structure using same patterns as `test_communication_router.py`:
- `unittest.mock.AsyncMock` for Supabase client
- `pytest.mark.asyncio` for async tests
- Direct service instantiation with mocked dependencies

Test cases:
1. **ICP CRUD:** save_icp creates record, get_icp returns it, save_icp again updates version
2. **Discovery:** discover_leads calls Hunter agent, stores results in discovered_leads
3. **Review - approve:** Creates Lead Memory entry, sets lead_memory_id
4. **Review - reject:** Sets review_status to rejected, no Lead Memory created
5. **Review - save:** Sets review_status to saved
6. **Score explanation:** Returns all 4 factors with explanations
7. **Pipeline:** Returns correct counts per stage
8. **List discovered:** Filters by review_status
9. **Outreach:** Creates draft with subject and body

**Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_lead_generation.py -v
```

**Step 3: Commit**

```bash
git add backend/tests/test_lead_generation.py
git commit -m "test(US-939): add lead generation service and API tests"
```

---

## Task 6: Frontend API Client & Hooks

**Files:**
- Create: `frontend/src/api/leadGeneration.ts`
- Create: `frontend/src/hooks/useLeadGeneration.ts`

**Step 1: Write API client**

Follow patterns from `frontend/src/api/leads.ts`:
- Import `apiClient` from `./client`
- TypeScript interfaces matching backend models
- Async functions for each endpoint

Key types:
```typescript
export interface ICPDefinition {
  industry: string[];
  company_size: { min: number; max: number };
  modalities: string[];
  therapeutic_areas: string[];
  geographies: string[];
  signals: string[];
  exclusions: string[];
}

export interface ICPResponse {
  id: string;
  user_id: string;
  icp_data: ICPDefinition;
  version: number;
  created_at: string;
  updated_at: string;
}

export type ReviewStatus = "pending" | "approved" | "rejected" | "saved";
export type PipelineStage = "prospect" | "qualified" | "opportunity" | "customer";

export interface ScoreFactor { name: string; score: number; weight: number; explanation: string; }
export interface LeadScoreBreakdown { overall_score: number; factors: ScoreFactor[]; }

export interface DiscoveredLead {
  id: string; user_id: string; icp_id: string | null;
  company_name: string; company_data: Record<string, unknown>;
  contacts: Record<string, unknown>[];
  fit_score: number; score_breakdown: LeadScoreBreakdown | null;
  signals: string[]; review_status: ReviewStatus;
  reviewed_at: string | null; source: string;
  lead_memory_id: string | null;
  created_at: string; updated_at: string;
}

export interface PipelineStageSummary { stage: PipelineStage; count: number; total_value: number; }
export interface PipelineSummary { stages: PipelineStageSummary[]; total_leads: number; total_pipeline_value: number; }

export interface OutreachResponse { id: string; lead_id: string; draft_subject: string; draft_body: string; status: string; created_at: string; }
```

Functions: `saveICP`, `getICP`, `discoverLeads`, `listDiscoveredLeads`, `reviewLead`, `getScoreExplanation`, `getPipeline`, `initiateOutreach`

**Step 2: Write React Query hooks**

Follow patterns from `frontend/src/hooks/useLeads.ts`:
- Query key factory: `leadGenKeys`
- `useICP()` — query for current ICP
- `useSaveICP()` — mutation that invalidates ICP query
- `useDiscoverLeads()` — mutation
- `useDiscoveredLeads(statusFilter?)` — query
- `useReviewLead()` — mutation that invalidates discovered leads
- `usePipeline()` — query
- `useScoreExplanation(leadId)` — query
- `useInitiateOutreach()` — mutation

**Step 3: Commit**

```bash
cd frontend && npm run typecheck
git add frontend/src/api/leadGeneration.ts frontend/src/hooks/useLeadGeneration.ts
git commit -m "feat(US-939): add frontend API client and React Query hooks for lead gen"
```

---

## Task 7: Frontend LeadGenPage with ICP Builder Tab

**Files:**
- Create: `frontend/src/pages/LeadGenPage.tsx`
- Create: `frontend/src/components/leads/ICPBuilder.tsx`
- Modify: `frontend/src/pages/index.ts` — add export
- Modify: `frontend/src/App.tsx` — add route

**Step 1: Write ICPBuilder component**

Dark surface form with:
- Tag inputs for: industry, modalities, therapeutic_areas, geographies, signals, exclusions
- Company size range (min/max headcount inputs)
- ARIA suggestions section: "Based on your company type, I'd suggest targeting..."
- "Discover Leads" button that triggers Hunter agent
- Loading state while discovery runs

Tag input pattern: Text input + Enter to add tag, X to remove. Tags displayed as `bg-slate-700 text-slate-200` pills.

**Step 2: Write LeadGenPage**

Tab-based navigation with three tabs: ICP Builder | Review Queue | Pipeline
- Uses `DashboardLayout`
- State for active tab
- Dark surface: `bg-slate-900`, gradient overlay
- Tab buttons: `bg-slate-800/50 border border-slate-700/50` when inactive, `bg-primary-600/20 border-primary-500/50` when active

**Step 3: Register route**

Add to `frontend/src/pages/index.ts`:
```typescript
export { LeadGenPage } from "./LeadGenPage";
```

Add to `frontend/src/App.tsx` imports and routes:
```tsx
import { LeadGenPage } from "@/pages";
// In routes:
<Route path="/leads" element={<ProtectedRoute><LeadGenPage /></ProtectedRoute>} />
```

**Step 4: Commit**

```bash
git add frontend/src/pages/LeadGenPage.tsx frontend/src/components/leads/ICPBuilder.tsx frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(US-939): add LeadGenPage with ICP Builder tab"
```

---

## Task 8: Frontend Review Queue Tab

**Files:**
- Create: `frontend/src/components/leads/LeadReviewQueue.tsx`
- Create: `frontend/src/components/leads/ScoreBreakdown.tsx`

**Step 1: Write ScoreBreakdown component**

Panel showing:
- Overall score (large number with color: green 70+, amber 40-69, red <40)
- 4 factor bars: ICP Fit, Timing Signals, Relationship Proximity, Engagement
- Each bar with score, weight percentage, plain-language explanation
- Styled: `bg-slate-800 border border-slate-700 rounded-lg p-4`

**Step 2: Write LeadReviewQueue component**

- Card grid of discovered leads (`grid gap-4 md:grid-cols-2 xl:grid-cols-3`)
- Each card: company name, fit score badge, key signals as tags, contacts preview
- Quick action buttons: Approve (green), Reject (red), Save (amber)
- Click card → expand ScoreBreakdown
- Batch approve: checkbox per card + "Approve Selected" button
- Filter by review_status tabs: All | Pending | Saved
- Empty state when no discovered leads: "Define your ICP and discover leads to review them here"

**Step 3: Commit**

```bash
git add frontend/src/components/leads/LeadReviewQueue.tsx frontend/src/components/leads/ScoreBreakdown.tsx
git commit -m "feat(US-939): add lead review queue with score breakdown"
```

---

## Task 9: Frontend Pipeline View Tab

**Files:**
- Create: `frontend/src/components/leads/PipelineView.tsx`

**Step 1: Write PipelineView component**

Uses Recharts (already in dependencies) for funnel visualization:
- Horizontal bar chart showing: Prospect → Qualified → Opportunity → Customer
- Each bar shows count and total value
- Color coding: slate-600, primary-500, accent-500, emerald-500
- Below the chart: stage cards in a row, each showing lead count, total value, and health indicator
- Total pipeline value displayed prominently at top

Stage cards are `bg-slate-800/50 border border-slate-700/50 rounded-lg p-4` with:
- Stage name, count, value
- Percentage of total pipeline

**Step 2: Commit**

```bash
git add frontend/src/components/leads/PipelineView.tsx
git commit -m "feat(US-939): add pipeline funnel view with Recharts visualization"
```

---

## Task 10: Frontend Outreach Modal

**Files:**
- Create: `frontend/src/components/leads/OutreachModal.tsx`

**Step 1: Write OutreachModal**

Modal following existing pattern from `AddNoteModal.tsx`:
- Fixed overlay with `bg-slate-900/80 backdrop-blur-sm`
- Modal card: `bg-slate-800 border border-slate-700 rounded-2xl`
- Fields: Subject (text input), Message (textarea), Tone select (professional/friendly/direct)
- "Send to Scribe" button that calls initiate_outreach
- Loading state while creating draft

**Step 2: Wire outreach button into Review Queue cards (approved leads only)**

**Step 3: Commit**

```bash
git add frontend/src/components/leads/OutreachModal.tsx
git commit -m "feat(US-939): add outreach modal for Scribe agent integration"
```

---

## Task 11: Quality Gates

**Step 1: Run all backend checks**

```bash
cd backend
ruff check src/models/lead_generation.py src/core/lead_generation.py src/api/routes/leads.py
ruff format --check src/models/lead_generation.py src/core/lead_generation.py src/api/routes/leads.py
mypy src/models/lead_generation.py src/core/lead_generation.py --strict
python -m pytest tests/test_lead_generation.py -v
```

**Step 2: Run all frontend checks**

```bash
cd frontend
npm run typecheck
npm run lint
```

**Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(US-939): quality gate fixes"
```
