# US-508: Lead Memory UI - List View Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a premium lead management page at `/dashboard/leads` with table/card views, health indicators, filtering, sorting, search, and bulk export.

**Architecture:** React page component using React Query for data fetching, following existing Goals page patterns. Backend API routes for lead CRUD operations. Apple-inspired luxury design with dark theme, subtle animations, and SF Pro typography feel using DM Sans.

**Tech Stack:** React 18, TypeScript, React Query, Tailwind CSS, Lucide Icons, Framer Motion

---

## Task 1: Create Backend Leads API Route

**Files:**
- Create: `backend/src/api/routes/leads.py`
- Modify: `backend/src/api/routes/__init__.py`

### Step 1: Write the failing test for list leads endpoint

Create test file `backend/tests/api/test_leads_route.py`:

```python
"""Tests for leads API routes."""

import pytest
from httpx import AsyncClient

from src.main import app


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Mock auth headers for testing."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def mock_user_id() -> str:
    """Mock user ID from token."""
    return "test-user-123"


class TestListLeads:
    """Tests for GET /leads endpoint."""

    @pytest.mark.asyncio
    async def test_list_leads_returns_empty_list(
        self, auth_headers: dict[str, str]
    ) -> None:
        """Test listing leads when none exist."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/leads", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_leads_requires_auth(self) -> None:
        """Test that listing leads requires authentication."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/leads")

        assert response.status_code == 401
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/api/test_leads_route.py -v`
Expected: FAIL - route doesn't exist

### Step 3: Write the leads API route

Create `backend/src/api/routes/leads.py`:

```python
"""Lead memory API routes.

Provides REST endpoints for managing sales pursuit leads including:
- List leads with filtering and sorting
- Get single lead details
- Create new leads
- Update lead status and details
- Add notes to leads
- Export leads
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import get_current_user_id
from src.core.exceptions import LeadMemoryError, LeadNotFoundError
from src.memory.lead_memory import LeadMemoryService, LeadStatus, LifecycleStage
from src.models.lead_memory import (
    LeadEventCreate,
    LeadEventResponse,
    LeadMemoryCreate,
    LeadMemoryResponse,
    LeadMemoryUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["leads"])


def _lead_to_response(lead) -> LeadMemoryResponse:
    """Convert LeadMemory dataclass to response model."""
    return LeadMemoryResponse(
        id=lead.id,
        user_id=lead.user_id,
        company_name=lead.company_name,
        company_id=lead.company_id,
        lifecycle_stage=LifecycleStage(lead.lifecycle_stage.value),
        status=LeadStatus(lead.status.value),
        health_score=lead.health_score,
        crm_id=lead.crm_id,
        crm_provider=lead.crm_provider,
        first_touch_at=lead.first_touch_at,
        last_activity_at=lead.last_activity_at,
        expected_close_date=lead.expected_close_date,
        expected_value=float(lead.expected_value) if lead.expected_value else None,
        tags=lead.tags,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


@router.get("", response_model=list[LeadMemoryResponse])
async def list_leads(
    user_id: str = Depends(get_current_user_id),
    status: str | None = Query(None, description="Filter by status"),
    stage: str | None = Query(None, description="Filter by lifecycle stage"),
    min_health: int | None = Query(None, ge=0, le=100, description="Minimum health score"),
    max_health: int | None = Query(None, ge=0, le=100, description="Maximum health score"),
    search: str | None = Query(None, description="Search by company name"),
    sort_by: str = Query("last_activity", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
) -> list[LeadMemoryResponse]:
    """List all leads for the current user with optional filters.

    Args:
        user_id: Current authenticated user.
        status: Optional filter by lead status (active, won, lost, dormant).
        stage: Optional filter by lifecycle stage (lead, opportunity, account).
        min_health: Optional minimum health score filter.
        max_health: Optional maximum health score filter.
        search: Optional company name search.
        sort_by: Field to sort by (health, last_activity, name, value).
        sort_order: Sort direction (asc, desc).
        limit: Maximum number of results.

    Returns:
        List of leads matching the filters.
    """
    try:
        service = LeadMemoryService()

        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = LeadStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status}",
                )

        # Parse stage filter
        stage_filter = None
        if stage:
            try:
                stage_filter = LifecycleStage(stage)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid stage: {stage}",
                )

        # Get leads from service
        leads = await service.list_by_user(
            user_id=user_id,
            status=status_filter,
            lifecycle_stage=stage_filter,
            min_health_score=min_health,
            max_health_score=max_health,
            limit=limit,
        )

        # Filter by search term if provided
        if search:
            search_lower = search.lower()
            leads = [l for l in leads if search_lower in l.company_name.lower()]

        # Sort results
        sort_key_map = {
            "health": lambda l: l.health_score,
            "last_activity": lambda l: l.last_activity_at,
            "name": lambda l: l.company_name.lower(),
            "value": lambda l: float(l.expected_value) if l.expected_value else 0,
        }

        if sort_by in sort_key_map:
            leads.sort(key=sort_key_map[sort_by], reverse=(sort_order == "desc"))

        return [_lead_to_response(lead) for lead in leads]

    except HTTPException:
        raise
    except LeadMemoryError as e:
        logger.exception("Failed to list leads")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{lead_id}", response_model=LeadMemoryResponse)
async def get_lead(
    lead_id: str,
    user_id: str = Depends(get_current_user_id),
) -> LeadMemoryResponse:
    """Get a specific lead by ID.

    Args:
        lead_id: The lead ID to retrieve.
        user_id: Current authenticated user.

    Returns:
        The requested lead.

    Raises:
        HTTPException: 404 if lead not found.
    """
    try:
        service = LeadMemoryService()
        lead = await service.get_by_id(user_id=user_id, lead_id=lead_id)
        return _lead_to_response(lead)

    except LeadNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        )
    except LeadMemoryError as e:
        logger.exception("Failed to get lead")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/{lead_id}/notes", response_model=LeadEventResponse)
async def add_note(
    lead_id: str,
    note: LeadEventCreate,
    user_id: str = Depends(get_current_user_id),
) -> LeadEventResponse:
    """Add a note to a lead.

    Args:
        lead_id: The lead ID to add note to.
        note: The note content.
        user_id: Current authenticated user.

    Returns:
        The created note event.

    Raises:
        HTTPException: 404 if lead not found.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_memory_events import LeadEventService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=user_id, lead_id=lead_id)

        # Create note event
        client = SupabaseClient.get_client()
        event_service = LeadEventService(db_client=client)

        event = await event_service.record_event(
            user_id=user_id,
            lead_memory_id=lead_id,
            event_type="note",
            content=note.content,
            subject=note.subject,
            occurred_at=note.occurred_at or datetime.now(UTC),
        )

        return LeadEventResponse(
            id=event.id,
            lead_memory_id=event.lead_memory_id,
            event_type=event.event_type,
            direction=None,
            subject=event.subject,
            content=event.content,
            participants=event.participants,
            occurred_at=event.occurred_at,
            source=event.source,
            created_at=event.created_at,
        )

    except LeadNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        )
    except LeadMemoryError as e:
        logger.exception("Failed to add note")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/export")
async def export_leads(
    lead_ids: list[str],
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Export leads to CSV format.

    Args:
        lead_ids: List of lead IDs to export.
        user_id: Current authenticated user.

    Returns:
        CSV content as string with filename.
    """
    import csv
    import io

    try:
        service = LeadMemoryService()
        leads = []

        for lead_id in lead_ids:
            try:
                lead = await service.get_by_id(user_id=user_id, lead_id=lead_id)
                leads.append(lead)
            except LeadNotFoundError:
                continue

        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Company Name",
            "Stage",
            "Status",
            "Health Score",
            "Expected Value",
            "Expected Close Date",
            "Last Activity",
            "Tags",
        ])

        # Data rows
        for lead in leads:
            writer.writerow([
                lead.company_name,
                lead.lifecycle_stage.value,
                lead.status.value,
                lead.health_score,
                str(lead.expected_value) if lead.expected_value else "",
                lead.expected_close_date.isoformat() if lead.expected_close_date else "",
                lead.last_activity_at.isoformat(),
                ", ".join(lead.tags),
            ])

        return {
            "filename": f"leads_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv",
            "content": output.getvalue(),
            "content_type": "text/csv",
        }

    except LeadMemoryError as e:
        logger.exception("Failed to export leads")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
```

### Step 4: Register the router in routes/__init__.py

Read `backend/src/api/routes/__init__.py` first, then add the leads router import and include:

```python
from src.api.routes.leads import router as leads_router

# Add to the list of routers being included
api_router.include_router(leads_router)
```

### Step 5: Run test to verify basic structure works

Run: `cd backend && pytest tests/api/test_leads_route.py -v`
Expected: May still fail due to auth/db mocking, but route should be recognized

### Step 6: Commit

```bash
git add backend/src/api/routes/leads.py backend/src/api/routes/__init__.py backend/tests/api/test_leads_route.py
git commit -m "$(cat <<'EOF'
feat(leads): add leads API routes for list, get, notes, export

- GET /leads with filters (status, stage, health range, search)
- GET /leads/{id} for single lead details
- POST /leads/{id}/notes to add notes
- POST /leads/export for CSV export

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create Frontend API Client for Leads

**Files:**
- Create: `frontend/src/api/leads.ts`

### Step 1: Create the leads API client

Create `frontend/src/api/leads.ts`:

```typescript
import { apiClient } from "./client";

// Enums matching backend
export type LifecycleStage = "lead" | "opportunity" | "account";
export type LeadStatus = "active" | "won" | "lost" | "dormant";
export type EventType = "email_sent" | "email_received" | "meeting" | "call" | "note" | "signal";

// Response types
export interface Lead {
  id: string;
  user_id: string;
  company_name: string;
  company_id: string | null;
  lifecycle_stage: LifecycleStage;
  status: LeadStatus;
  health_score: number;
  crm_id: string | null;
  crm_provider: string | null;
  first_touch_at: string | null;
  last_activity_at: string | null;
  expected_close_date: string | null;
  expected_value: number | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface LeadEvent {
  id: string;
  lead_memory_id: string;
  event_type: EventType;
  direction: "inbound" | "outbound" | null;
  subject: string | null;
  content: string | null;
  participants: string[];
  occurred_at: string;
  source: string | null;
  created_at: string;
}

export interface NoteCreate {
  content: string;
  subject?: string;
  occurred_at?: string;
}

export interface LeadFilters {
  status?: LeadStatus;
  stage?: LifecycleStage;
  minHealth?: number;
  maxHealth?: number;
  search?: string;
  sortBy?: "health" | "last_activity" | "name" | "value";
  sortOrder?: "asc" | "desc";
  limit?: number;
}

export interface ExportResult {
  filename: string;
  content: string;
  content_type: string;
}

// API functions
export async function listLeads(filters?: LeadFilters): Promise<Lead[]> {
  const params = new URLSearchParams();

  if (filters?.status) params.append("status", filters.status);
  if (filters?.stage) params.append("stage", filters.stage);
  if (filters?.minHealth !== undefined) params.append("min_health", filters.minHealth.toString());
  if (filters?.maxHealth !== undefined) params.append("max_health", filters.maxHealth.toString());
  if (filters?.search) params.append("search", filters.search);
  if (filters?.sortBy) params.append("sort_by", filters.sortBy);
  if (filters?.sortOrder) params.append("sort_order", filters.sortOrder);
  if (filters?.limit) params.append("limit", filters.limit.toString());

  const url = params.toString() ? `/leads?${params}` : "/leads";
  const response = await apiClient.get<Lead[]>(url);
  return response.data;
}

export async function getLead(leadId: string): Promise<Lead> {
  const response = await apiClient.get<Lead>(`/leads/${leadId}`);
  return response.data;
}

export async function addNote(leadId: string, note: NoteCreate): Promise<LeadEvent> {
  const response = await apiClient.post<LeadEvent>(`/leads/${leadId}/notes`, {
    event_type: "note",
    content: note.content,
    subject: note.subject,
    occurred_at: note.occurred_at || new Date().toISOString(),
  });
  return response.data;
}

export async function exportLeads(leadIds: string[]): Promise<ExportResult> {
  const response = await apiClient.post<ExportResult>("/leads/export", leadIds);
  return response.data;
}

// Helper to trigger CSV download
export function downloadCsv(result: ExportResult): void {
  const blob = new Blob([result.content], { type: result.content_type });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = result.filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
```

### Step 2: Verify TypeScript compiles

Run: `cd frontend && npm run typecheck`
Expected: PASS (no type errors)

### Step 3: Commit

```bash
git add frontend/src/api/leads.ts
git commit -m "$(cat <<'EOF'
feat(leads): add frontend API client for leads endpoints

- listLeads with filtering, sorting, search
- getLead for single lead
- addNote for quick note creation
- exportLeads with CSV download helper

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create React Query Hooks for Leads

**Files:**
- Create: `frontend/src/hooks/useLeads.ts`

### Step 1: Create the leads hooks

Create `frontend/src/hooks/useLeads.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addNote,
  downloadCsv,
  exportLeads,
  getLead,
  listLeads,
  type Lead,
  type LeadFilters,
  type NoteCreate,
} from "@/api/leads";

// Query keys
export const leadKeys = {
  all: ["leads"] as const,
  lists: () => [...leadKeys.all, "list"] as const,
  list: (filters?: LeadFilters) => [...leadKeys.lists(), { filters }] as const,
  details: () => [...leadKeys.all, "detail"] as const,
  detail: (id: string) => [...leadKeys.details(), id] as const,
};

// List leads query
export function useLeads(filters?: LeadFilters) {
  return useQuery({
    queryKey: leadKeys.list(filters),
    queryFn: () => listLeads(filters),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
}

// Single lead query
export function useLead(leadId: string) {
  return useQuery({
    queryKey: leadKeys.detail(leadId),
    queryFn: () => getLead(leadId),
    enabled: !!leadId,
  });
}

// Add note mutation
export function useAddNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, note }: { leadId: string; note: NoteCreate }) =>
      addNote(leadId, note),
    onSuccess: (_data, { leadId }) => {
      // Invalidate the specific lead and lists
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}

// Export leads mutation
export function useExportLeads() {
  return useMutation({
    mutationFn: (leadIds: string[]) => exportLeads(leadIds),
    onSuccess: (result) => {
      // Trigger download
      downloadCsv(result);
    },
  });
}

// Helper hook for selected leads management
export function useLeadSelection() {
  const queryClient = useQueryClient();

  const getSelectedLeads = (): Set<string> => {
    return queryClient.getQueryData(["leads", "selection"]) || new Set();
  };

  const setSelectedLeads = (ids: Set<string>) => {
    queryClient.setQueryData(["leads", "selection"], ids);
  };

  const toggleLead = (id: string) => {
    const current = getSelectedLeads();
    const next = new Set(current);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedLeads(next);
  };

  const selectAll = (leads: Lead[]) => {
    setSelectedLeads(new Set(leads.map((l) => l.id)));
  };

  const clearSelection = () => {
    setSelectedLeads(new Set());
  };

  return {
    getSelectedLeads,
    setSelectedLeads,
    toggleLead,
    selectAll,
    clearSelection,
  };
}
```

### Step 2: Verify TypeScript compiles

Run: `cd frontend && npm run typecheck`
Expected: PASS

### Step 3: Commit

```bash
git add frontend/src/hooks/useLeads.ts
git commit -m "$(cat <<'EOF'
feat(leads): add React Query hooks for leads data fetching

- useLeads for listing with filters
- useLead for single lead details
- useAddNote mutation with cache invalidation
- useExportLeads mutation with download trigger
- useLeadSelection helper for bulk actions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Create Lead Card Component

**Files:**
- Create: `frontend/src/components/leads/LeadCard.tsx`
- Create: `frontend/src/components/leads/index.ts`

### Step 1: Create the LeadCard component

Create `frontend/src/components/leads/LeadCard.tsx`:

```typescript
import { Building2, Calendar, DollarSign, MessageSquarePlus, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import type { Lead } from "@/api/leads";

interface LeadCardProps {
  lead: Lead;
  isSelected: boolean;
  onSelect: () => void;
  onAddNote: () => void;
}

function HealthBadge({ score }: { score: number }) {
  const getHealthConfig = (score: number) => {
    if (score >= 70) {
      return {
        emoji: "🟢",
        bg: "bg-emerald-500/10",
        border: "border-emerald-500/20",
        text: "text-emerald-400",
        label: "Healthy",
      };
    }
    if (score >= 40) {
      return {
        emoji: "🟡",
        bg: "bg-amber-500/10",
        border: "border-amber-500/20",
        text: "text-amber-400",
        label: "Attention",
      };
    }
    return {
      emoji: "🔴",
      bg: "bg-red-500/10",
      border: "border-red-500/20",
      text: "text-red-400",
      label: "At Risk",
    };
  };

  const config = getHealthConfig(score);

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ${config.bg} ${config.border} border`}
    >
      <span className="text-sm">{config.emoji}</span>
      <span className={`text-xs font-medium ${config.text}`}>{score}</span>
    </div>
  );
}

function StageBadge({ stage }: { stage: string }) {
  const stageConfig: Record<string, { bg: string; text: string }> = {
    lead: { bg: "bg-slate-500/10", text: "text-slate-400" },
    opportunity: { bg: "bg-primary-500/10", text: "text-primary-400" },
    account: { bg: "bg-accent-500/10", text: "text-accent-400" },
  };

  const config = stageConfig[stage] || stageConfig.lead;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${config.bg} ${config.text}`}
    >
      {stage}
    </span>
  );
}

export function LeadCard({ lead, isSelected, onSelect, onAddNote }: LeadCardProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  };

  const formatCurrency = (value: number | null) => {
    if (!value) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  };

  return (
    <div
      className={`group relative bg-slate-800/40 backdrop-blur-sm border rounded-xl p-5 transition-all duration-300 hover:bg-slate-800/60 hover:shadow-lg hover:shadow-primary-500/5 hover:-translate-y-0.5 ${
        isSelected
          ? "border-primary-500/50 ring-1 ring-primary-500/20"
          : "border-slate-700/50 hover:border-slate-600/50"
      }`}
    >
      {/* Selection checkbox */}
      <div className="absolute top-4 right-4 z-10">
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onSelect();
          }}
          className={`w-5 h-5 rounded border-2 transition-all duration-200 flex items-center justify-center ${
            isSelected
              ? "bg-primary-500 border-primary-500"
              : "border-slate-600 hover:border-slate-500 group-hover:border-slate-500"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </button>
      </div>

      <Link to={`/dashboard/leads/${lead.id}`} className="block">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-slate-700 to-slate-800 rounded-xl flex items-center justify-center border border-slate-600/50">
            <Building2 className="w-6 h-6 text-slate-400" />
          </div>
          <div className="flex-1 min-w-0 pr-8">
            <h3 className="text-lg font-semibold text-white truncate group-hover:text-primary-300 transition-colors">
              {lead.company_name}
            </h3>
            <div className="flex items-center gap-2 mt-1">
              <StageBadge stage={lead.lifecycle_stage} />
              <span
                className={`text-xs capitalize ${
                  lead.status === "active"
                    ? "text-emerald-400"
                    : lead.status === "won"
                      ? "text-primary-400"
                      : lead.status === "lost"
                        ? "text-red-400"
                        : "text-slate-500"
                }`}
              >
                {lead.status}
              </span>
            </div>
          </div>
        </div>

        {/* Health Score */}
        <div className="mb-4">
          <HealthBadge score={lead.health_score} />
        </div>

        {/* Meta info */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="flex items-center gap-2 text-slate-400">
            <Calendar className="w-4 h-4 text-slate-500" />
            <span>Last: {formatDate(lead.last_activity_at)}</span>
          </div>
          <div className="flex items-center gap-2 text-slate-400">
            <DollarSign className="w-4 h-4 text-slate-500" />
            <span>{formatCurrency(lead.expected_value)}</span>
          </div>
          {lead.expected_close_date && (
            <div className="flex items-center gap-2 text-slate-400 col-span-2">
              <TrendingUp className="w-4 h-4 text-slate-500" />
              <span>Close: {formatDate(lead.expected_close_date)}</span>
            </div>
          )}
        </div>

        {/* Tags */}
        {lead.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-4 pt-4 border-t border-slate-700/50">
            {lead.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400"
              >
                {tag}
              </span>
            ))}
            {lead.tags.length > 3 && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-500">
                +{lead.tags.length - 3}
              </span>
            )}
          </div>
        )}
      </Link>

      {/* Quick action - Add Note */}
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onAddNote();
        }}
        className="absolute bottom-4 right-4 p-2 rounded-lg bg-slate-700/50 text-slate-400 opacity-0 group-hover:opacity-100 hover:bg-primary-500/20 hover:text-primary-400 transition-all duration-200"
        title="Add note"
      >
        <MessageSquarePlus className="w-4 h-4" />
      </button>
    </div>
  );
}
```

### Step 2: Create the barrel export file

Create `frontend/src/components/leads/index.ts`:

```typescript
export { LeadCard } from "./LeadCard";
```

### Step 3: Verify TypeScript compiles

Run: `cd frontend && npm run typecheck`
Expected: PASS

### Step 4: Commit

```bash
git add frontend/src/components/leads/
git commit -m "$(cat <<'EOF'
feat(leads): add LeadCard component with health badges

- Health indicator badges (🟢 ≥70, 🟡 40-69, 🔴 <40)
- Stage badge (lead/opportunity/account)
- Selection checkbox for bulk actions
- Quick action button for adding notes
- Hover effects and animations

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create Lead Table Row Component

**Files:**
- Modify: `frontend/src/components/leads/index.ts`
- Create: `frontend/src/components/leads/LeadTableRow.tsx`

### Step 1: Create the LeadTableRow component

Create `frontend/src/components/leads/LeadTableRow.tsx`:

```typescript
import { Eye, MessageSquarePlus } from "lucide-react";
import { Link } from "react-router-dom";
import type { Lead } from "@/api/leads";

interface LeadTableRowProps {
  lead: Lead;
  isSelected: boolean;
  onSelect: () => void;
  onAddNote: () => void;
}

function HealthIndicator({ score }: { score: number }) {
  const getConfig = (score: number) => {
    if (score >= 70) return { emoji: "🟢", color: "text-emerald-400" };
    if (score >= 40) return { emoji: "🟡", color: "text-amber-400" };
    return { emoji: "🔴", color: "text-red-400" };
  };

  const { emoji, color } = getConfig(score);

  return (
    <div className="flex items-center gap-2">
      <span>{emoji}</span>
      <span className={`font-medium ${color}`}>{score}</span>
    </div>
  );
}

export function LeadTableRow({ lead, isSelected, onSelect, onAddNote }: LeadTableRowProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatCurrency = (value: number | null) => {
    if (!value) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  };

  return (
    <tr
      className={`group border-b border-slate-700/30 transition-colors hover:bg-slate-800/30 ${
        isSelected ? "bg-primary-500/5" : ""
      }`}
    >
      {/* Checkbox */}
      <td className="w-12 px-4 py-4">
        <button
          onClick={onSelect}
          className={`w-5 h-5 rounded border-2 transition-all duration-200 flex items-center justify-center ${
            isSelected
              ? "bg-primary-500 border-primary-500"
              : "border-slate-600 hover:border-slate-500"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </button>
      </td>

      {/* Company Name */}
      <td className="px-4 py-4">
        <Link
          to={`/dashboard/leads/${lead.id}`}
          className="font-medium text-white hover:text-primary-300 transition-colors"
        >
          {lead.company_name}
        </Link>
      </td>

      {/* Health Score */}
      <td className="px-4 py-4">
        <HealthIndicator score={lead.health_score} />
      </td>

      {/* Stage */}
      <td className="px-4 py-4">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium capitalize ${
            lead.lifecycle_stage === "account"
              ? "bg-accent-500/10 text-accent-400"
              : lead.lifecycle_stage === "opportunity"
                ? "bg-primary-500/10 text-primary-400"
                : "bg-slate-500/10 text-slate-400"
          }`}
        >
          {lead.lifecycle_stage}
        </span>
      </td>

      {/* Status */}
      <td className="px-4 py-4">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium capitalize ${
            lead.status === "active"
              ? "bg-emerald-500/10 text-emerald-400"
              : lead.status === "won"
                ? "bg-primary-500/10 text-primary-400"
                : lead.status === "lost"
                  ? "bg-red-500/10 text-red-400"
                  : "bg-slate-500/10 text-slate-500"
          }`}
        >
          {lead.status}
        </span>
      </td>

      {/* Expected Value */}
      <td className="px-4 py-4 text-slate-400">
        {formatCurrency(lead.expected_value)}
      </td>

      {/* Last Activity */}
      <td className="px-4 py-4 text-slate-400">
        {formatDate(lead.last_activity_at)}
      </td>

      {/* Actions */}
      <td className="px-4 py-4">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Link
            to={`/dashboard/leads/${lead.id}`}
            className="p-2 rounded-lg hover:bg-slate-700/50 text-slate-400 hover:text-white transition-colors"
            title="View details"
          >
            <Eye className="w-4 h-4" />
          </Link>
          <button
            onClick={onAddNote}
            className="p-2 rounded-lg hover:bg-slate-700/50 text-slate-400 hover:text-primary-400 transition-colors"
            title="Add note"
          >
            <MessageSquarePlus className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}
```

### Step 2: Update barrel export

Modify `frontend/src/components/leads/index.ts`:

```typescript
export { LeadCard } from "./LeadCard";
export { LeadTableRow } from "./LeadTableRow";
```

### Step 3: Verify TypeScript compiles

Run: `cd frontend && npm run typecheck`
Expected: PASS

### Step 4: Commit

```bash
git add frontend/src/components/leads/
git commit -m "$(cat <<'EOF'
feat(leads): add LeadTableRow component for table view

- Health indicator with emoji and score
- Stage and status badges
- Expected value and last activity columns
- Row selection and hover actions
- View and add note quick actions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Create Add Note Modal Component

**Files:**
- Modify: `frontend/src/components/leads/index.ts`
- Create: `frontend/src/components/leads/AddNoteModal.tsx`

### Step 1: Create the AddNoteModal component

Create `frontend/src/components/leads/AddNoteModal.tsx`:

```typescript
import { X } from "lucide-react";
import { useState } from "react";
import type { Lead } from "@/api/leads";

interface AddNoteModalProps {
  lead: Lead | null;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (content: string) => void;
  isLoading: boolean;
}

export function AddNoteModal({ lead, isOpen, onClose, onSubmit, isLoading }: AddNoteModalProps) {
  const [content, setContent] = useState("");

  if (!isOpen || !lead) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (content.trim()) {
      onSubmit(content.trim());
      setContent("");
    }
  };

  const handleClose = () => {
    setContent("");
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-white">Add Note</h2>
            <p className="text-sm text-slate-400 mt-0.5">{lead.company_name}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6">
          <div className="mb-6">
            <label htmlFor="note-content" className="block text-sm font-medium text-slate-300 mb-2">
              Note
            </label>
            <textarea
              id="note-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Add your note about this lead..."
              rows={4}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
              autoFocus
            />
          </div>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!content.trim() || isLoading}
              className="px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Saving...
                </span>
              ) : (
                "Add Note"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

### Step 2: Update barrel export

Modify `frontend/src/components/leads/index.ts`:

```typescript
export { AddNoteModal } from "./AddNoteModal";
export { LeadCard } from "./LeadCard";
export { LeadTableRow } from "./LeadTableRow";
```

### Step 3: Verify TypeScript compiles

Run: `cd frontend && npm run typecheck`
Expected: PASS

### Step 4: Commit

```bash
git add frontend/src/components/leads/
git commit -m "$(cat <<'EOF'
feat(leads): add AddNoteModal component

- Modal with backdrop blur animation
- Textarea for note content
- Loading state with spinner
- Keyboard-friendly (ESC to close, auto-focus)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Create Empty State and Loading Components

**Files:**
- Modify: `frontend/src/components/leads/index.ts`
- Create: `frontend/src/components/leads/EmptyLeads.tsx`
- Create: `frontend/src/components/leads/LeadsSkeleton.tsx`

### Step 1: Create the EmptyLeads component

Create `frontend/src/components/leads/EmptyLeads.tsx`:

```typescript
import { Building2, Plus } from "lucide-react";

interface EmptyLeadsProps {
  hasFilters: boolean;
  onClearFilters?: () => void;
}

export function EmptyLeads({ hasFilters, onClearFilters }: EmptyLeadsProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-20 h-20 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-6 border border-slate-700/50">
        <Building2 className="w-10 h-10 text-slate-500" />
      </div>

      {hasFilters ? (
        <>
          <h3 className="text-xl font-semibold text-white mb-2">No leads found</h3>
          <p className="text-slate-400 text-center max-w-md mb-6">
            No leads match your current filters. Try adjusting your search or filter criteria.
          </p>
          <button
            onClick={onClearFilters}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-lg transition-colors"
          >
            Clear Filters
          </button>
        </>
      ) : (
        <>
          <h3 className="text-xl font-semibold text-white mb-2">No leads yet</h3>
          <p className="text-slate-400 text-center max-w-md mb-6">
            Leads will appear here as ARIA tracks your sales pursuits. Start a conversation or approve an outbound email to begin.
          </p>
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <Plus className="w-4 h-4" />
            <span>Leads are created automatically from your interactions</span>
          </div>
        </>
      )}
    </div>
  );
}
```

### Step 2: Create the LeadsSkeleton component

Create `frontend/src/components/leads/LeadsSkeleton.tsx`:

```typescript
interface LeadsSkeletonProps {
  viewMode: "card" | "table";
}

function CardSkeleton() {
  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 animate-pulse">
      <div className="flex items-start gap-4 mb-4">
        <div className="w-12 h-12 bg-slate-700 rounded-xl" />
        <div className="flex-1">
          <div className="h-5 bg-slate-700 rounded w-3/4 mb-2" />
          <div className="h-4 bg-slate-700 rounded w-1/2" />
        </div>
      </div>
      <div className="h-8 bg-slate-700 rounded-full w-20 mb-4" />
      <div className="grid grid-cols-2 gap-3">
        <div className="h-4 bg-slate-700 rounded" />
        <div className="h-4 bg-slate-700 rounded" />
      </div>
    </div>
  );
}

function TableRowSkeleton() {
  return (
    <tr className="border-b border-slate-700/30">
      <td className="px-4 py-4">
        <div className="w-5 h-5 bg-slate-700 rounded animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-40 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-16 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-6 bg-slate-700 rounded-full w-24 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-6 bg-slate-700 rounded-full w-20 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-20 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-24 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-16 animate-pulse" />
      </td>
    </tr>
  );
}

export function LeadsSkeleton({ viewMode }: LeadsSkeletonProps) {
  if (viewMode === "table") {
    return (
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-800/60 text-left">
              <th className="w-12 px-4 py-3" />
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Company</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Health</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Stage</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Status</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Value</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Last Activity</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Actions</th>
            </tr>
          </thead>
          <tbody>
            {[...Array(5)].map((_, i) => (
              <TableRowSkeleton key={i} />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {[...Array(6)].map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}
```

### Step 3: Update barrel export

Modify `frontend/src/components/leads/index.ts`:

```typescript
export { AddNoteModal } from "./AddNoteModal";
export { EmptyLeads } from "./EmptyLeads";
export { LeadCard } from "./LeadCard";
export { LeadsSkeleton } from "./LeadsSkeleton";
export { LeadTableRow } from "./LeadTableRow";
```

### Step 4: Verify TypeScript compiles

Run: `cd frontend && npm run typecheck`
Expected: PASS

### Step 5: Commit

```bash
git add frontend/src/components/leads/
git commit -m "$(cat <<'EOF'
feat(leads): add EmptyLeads and LeadsSkeleton components

- EmptyLeads with filter-aware messaging
- LeadsSkeleton for both card and table views
- Animated pulse loading state

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Create the Leads Page

**Files:**
- Create: `frontend/src/pages/Leads.tsx`
- Modify: `frontend/src/pages/index.ts`

### Step 1: Create the Leads page component

Create `frontend/src/pages/Leads.tsx`:

```typescript
import {
  ArrowDownAZ,
  ArrowUpAZ,
  Download,
  Filter,
  Grid3X3,
  List,
  Search,
  X,
} from "lucide-react";
import { useState, useMemo } from "react";
import type { Lead, LeadFilters, LeadStatus, LifecycleStage } from "@/api/leads";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  AddNoteModal,
  EmptyLeads,
  LeadCard,
  LeadsSkeleton,
  LeadTableRow,
} from "@/components/leads";
import { useAddNote, useExportLeads, useLeads } from "@/hooks/useLeads";

type ViewMode = "card" | "table";
type SortField = "health" | "last_activity" | "name" | "value";
type SortOrder = "asc" | "desc";

const statusOptions: { value: LeadStatus | "all"; label: string }[] = [
  { value: "all", label: "All Status" },
  { value: "active", label: "Active" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
  { value: "dormant", label: "Dormant" },
];

const stageOptions: { value: LifecycleStage | "all"; label: string }[] = [
  { value: "all", label: "All Stages" },
  { value: "lead", label: "Lead" },
  { value: "opportunity", label: "Opportunity" },
  { value: "account", label: "Account" },
];

const healthRanges = [
  { value: "all", label: "All Health", min: undefined, max: undefined },
  { value: "healthy", label: "🟢 Healthy (70+)", min: 70, max: 100 },
  { value: "attention", label: "🟡 Needs Attention (40-69)", min: 40, max: 69 },
  { value: "risk", label: "🔴 At Risk (<40)", min: 0, max: 39 },
];

const sortOptions: { value: SortField; label: string }[] = [
  { value: "last_activity", label: "Last Activity" },
  { value: "health", label: "Health Score" },
  { value: "name", label: "Company Name" },
  { value: "value", label: "Expected Value" },
];

export function LeadsPage() {
  // View state
  const [viewMode, setViewMode] = useState<ViewMode>("card");
  const [showFilters, setShowFilters] = useState(false);

  // Filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<LeadStatus | "all">("all");
  const [stageFilter, setStageFilter] = useState<LifecycleStage | "all">("all");
  const [healthFilter, setHealthFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<SortField>("last_activity");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Modal state
  const [noteModalLead, setNoteModalLead] = useState<Lead | null>(null);

  // Build filters object
  const filters: LeadFilters = useMemo(() => {
    const healthRange = healthRanges.find((r) => r.value === healthFilter);
    return {
      status: statusFilter !== "all" ? statusFilter : undefined,
      stage: stageFilter !== "all" ? stageFilter : undefined,
      minHealth: healthRange?.min,
      maxHealth: healthRange?.max,
      search: searchQuery || undefined,
      sortBy,
      sortOrder,
    };
  }, [statusFilter, stageFilter, healthFilter, searchQuery, sortBy, sortOrder]);

  const hasActiveFilters =
    statusFilter !== "all" ||
    stageFilter !== "all" ||
    healthFilter !== "all" ||
    searchQuery !== "";

  // Queries and mutations
  const { data: leads, isLoading, error } = useLeads(filters);
  const addNoteMutation = useAddNote();
  const exportMutation = useExportLeads();

  // Selection handlers
  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => {
    if (leads) {
      setSelectedIds(new Set(leads.map((l) => l.id)));
    }
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const clearFilters = () => {
    setSearchQuery("");
    setStatusFilter("all");
    setStageFilter("all");
    setHealthFilter("all");
  };

  // Action handlers
  const handleAddNote = (content: string) => {
    if (noteModalLead) {
      addNoteMutation.mutate(
        { leadId: noteModalLead.id, note: { content } },
        {
          onSuccess: () => {
            setNoteModalLead(null);
          },
        }
      );
    }
  };

  const handleExport = () => {
    if (selectedIds.size > 0) {
      exportMutation.mutate(Array.from(selectedIds));
    }
  };

  const toggleSortOrder = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  };

  return (
    <DashboardLayout>
      <div className="relative min-h-screen">
        {/* Subtle gradient background */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-8">
            <div>
              <h1 className="text-3xl font-bold text-white tracking-tight">Lead Memory</h1>
              <p className="mt-1 text-slate-400">
                Track and manage your sales pursuits with AI-powered insights
              </p>
            </div>

            {/* View toggle and export */}
            <div className="flex items-center gap-3">
              {selectedIds.size > 0 && (
                <button
                  onClick={handleExport}
                  disabled={exportMutation.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
                >
                  <Download className="w-4 h-4" />
                  Export ({selectedIds.size})
                </button>
              )}

              <div className="flex items-center bg-slate-800/50 border border-slate-700/50 rounded-lg p-1">
                <button
                  onClick={() => setViewMode("card")}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === "card"
                      ? "bg-slate-700 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                  title="Card view"
                >
                  <Grid3X3 className="w-5 h-5" />
                </button>
                <button
                  onClick={() => setViewMode("table")}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === "table"
                      ? "bg-slate-700 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                  title="Table view"
                >
                  <List className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>

          {/* Search and filters bar */}
          <div className="flex flex-col sm:flex-row gap-3 mb-6">
            {/* Search */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by company name..."
                className="w-full pl-10 pr-4 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-400"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Filter toggle */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`inline-flex items-center gap-2 px-4 py-2.5 border rounded-lg font-medium transition-colors ${
                showFilters || hasActiveFilters
                  ? "bg-primary-600/20 border-primary-500/30 text-primary-400"
                  : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white hover:border-slate-600/50"
              }`}
            >
              <Filter className="w-4 h-4" />
              Filters
              {hasActiveFilters && (
                <span className="w-2 h-2 rounded-full bg-primary-500" />
              )}
            </button>

            {/* Sort controls */}
            <div className="flex items-center gap-2">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortField)}
                className="px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                {sortOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    Sort: {opt.label}
                  </option>
                ))}
              </select>
              <button
                onClick={toggleSortOrder}
                className="p-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-400 hover:text-white transition-colors"
                title={sortOrder === "asc" ? "Ascending" : "Descending"}
              >
                {sortOrder === "asc" ? (
                  <ArrowUpAZ className="w-5 h-5" />
                ) : (
                  <ArrowDownAZ className="w-5 h-5" />
                )}
              </button>
            </div>
          </div>

          {/* Expanded filters */}
          {showFilters && (
            <div className="mb-6 p-4 bg-slate-800/30 border border-slate-700/30 rounded-xl animate-in fade-in slide-in-from-top-2 duration-200">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {/* Status filter */}
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Status
                  </label>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as LeadStatus | "all")}
                    className="w-full px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {statusOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Stage filter */}
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Stage
                  </label>
                  <select
                    value={stageFilter}
                    onChange={(e) => setStageFilter(e.target.value as LifecycleStage | "all")}
                    className="w-full px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {stageOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Health filter */}
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Health Score
                  </label>
                  <select
                    value={healthFilter}
                    onChange={(e) => setHealthFilter(e.target.value)}
                    className="w-full px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {healthRanges.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {hasActiveFilters && (
                <div className="mt-4 pt-4 border-t border-slate-700/30 flex justify-end">
                  <button
                    onClick={clearFilters}
                    className="text-sm text-slate-400 hover:text-white transition-colors"
                  >
                    Clear all filters
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Selection bar */}
          {leads && leads.length > 0 && (
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <button
                  onClick={selectedIds.size === leads.length ? clearSelection : selectAll}
                  className="text-sm text-slate-400 hover:text-white transition-colors"
                >
                  {selectedIds.size === leads.length ? "Deselect all" : "Select all"}
                </button>
                {selectedIds.size > 0 && (
                  <span className="text-sm text-slate-500">
                    {selectedIds.size} of {leads.length} selected
                  </span>
                )}
              </div>
              <span className="text-sm text-slate-500">
                {leads.length} lead{leads.length !== 1 ? "s" : ""}
              </span>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400">Failed to load leads. Please try again.</p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && <LeadsSkeleton viewMode={viewMode} />}

          {/* Empty state */}
          {!isLoading && leads && leads.length === 0 && (
            <EmptyLeads hasFilters={hasActiveFilters} onClearFilters={clearFilters} />
          )}

          {/* Lead grid/table */}
          {!isLoading && leads && leads.length > 0 && (
            <>
              {viewMode === "card" ? (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {leads.map((lead, index) => (
                    <div
                      key={lead.id}
                      className="animate-in fade-in slide-in-from-bottom-4"
                      style={{
                        animationDelay: `${Math.min(index * 50, 300)}ms`,
                        animationFillMode: "both",
                      }}
                    >
                      <LeadCard
                        lead={lead}
                        isSelected={selectedIds.has(lead.id)}
                        onSelect={() => toggleSelection(lead.id)}
                        onAddNote={() => setNoteModalLead(lead)}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl overflow-hidden overflow-x-auto">
                  <table className="w-full min-w-[800px]">
                    <thead>
                      <tr className="bg-slate-800/60 text-left">
                        <th className="w-12 px-4 py-3">
                          <button
                            onClick={selectedIds.size === leads.length ? clearSelection : selectAll}
                            className={`w-5 h-5 rounded border-2 transition-all duration-200 flex items-center justify-center ${
                              selectedIds.size === leads.length
                                ? "bg-primary-500 border-primary-500"
                                : "border-slate-600 hover:border-slate-500"
                            }`}
                          >
                            {selectedIds.size === leads.length && (
                              <svg
                                className="w-3 h-3 text-white"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={3}
                                  d="M5 13l4 4L19 7"
                                />
                              </svg>
                            )}
                          </button>
                        </th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Company</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Health</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Stage</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Status</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Value</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">
                          Last Activity
                        </th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leads.map((lead) => (
                        <LeadTableRow
                          key={lead.id}
                          lead={lead}
                          isSelected={selectedIds.has(lead.id)}
                          onSelect={() => toggleSelection(lead.id)}
                          onAddNote={() => setNoteModalLead(lead)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>

        {/* Add Note Modal */}
        <AddNoteModal
          lead={noteModalLead}
          isOpen={noteModalLead !== null}
          onClose={() => setNoteModalLead(null)}
          onSubmit={handleAddNote}
          isLoading={addNoteMutation.isPending}
        />
      </div>
    </DashboardLayout>
  );
}
```

### Step 2: Update pages barrel export

Read `frontend/src/pages/index.ts` first, then add:

```typescript
export { LeadsPage } from "./Leads";
```

### Step 3: Verify TypeScript compiles

Run: `cd frontend && npm run typecheck`
Expected: PASS

### Step 4: Commit

```bash
git add frontend/src/pages/Leads.tsx frontend/src/pages/index.ts
git commit -m "$(cat <<'EOF'
feat(leads): add LeadsPage with full filtering and views

- Table/card view toggle
- Health indicator badges (🟢🟡🔴)
- Sort by health, activity, name, value
- Filter by status, stage, health range
- Search by company name
- Bulk selection and export
- Quick add note action
- Staggered animation on card load

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Add Route and Navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/DashboardLayout.tsx` (if nav item doesn't exist)

### Step 1: Add the route to App.tsx

Read `frontend/src/App.tsx` and add the LeadsPage import and route.

Add to imports:
```typescript
import { LeadsPage } from "@/pages";
```

Add route after `/goals` route (around line 60):
```typescript
<Route
  path="/dashboard/leads"
  element={
    <ProtectedRoute>
      <LeadsPage />
    </ProtectedRoute>
  }
/>
```

### Step 2: Verify navigation link exists

Read `frontend/src/components/DashboardLayout.tsx` and check if there's already a "Lead Memory" or "Leads" nav item. If not, add one.

Look for the nav items array and add:
```typescript
{ name: "Lead Memory", href: "/dashboard/leads", icon: Building2 }
```

### Step 3: Verify application compiles

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS

### Step 4: Commit

```bash
git add frontend/src/App.tsx frontend/src/components/DashboardLayout.tsx
git commit -m "$(cat <<'EOF'
feat(leads): add /dashboard/leads route and navigation

- Protected route for leads page
- Navigation item in dashboard sidebar

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Final Verification and Lint

**Files:**
- All modified files

### Step 1: Run TypeScript check

Run: `cd frontend && npm run typecheck`
Expected: PASS

### Step 2: Run linting

Run: `cd frontend && npm run lint`
Expected: PASS (or fix any issues)

### Step 3: Run backend linting

Run: `cd backend && ruff check src/api/routes/leads.py && ruff format src/api/routes/leads.py`
Expected: PASS

### Step 4: Run backend type check

Run: `cd backend && mypy src/api/routes/leads.py --ignore-missing-imports`
Expected: PASS (or fix any issues)

### Step 5: Commit any lint fixes

```bash
git add -A
git commit -m "$(cat <<'EOF'
style(leads): apply lint fixes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan creates the complete Lead Memory UI List View feature (US-508) with:

1. **Backend API** (`/leads` routes) - List, get, add notes, export
2. **Frontend API client** - Type-safe API functions
3. **React Query hooks** - Data fetching with caching
4. **LeadCard component** - Card view with health badges
5. **LeadTableRow component** - Table view with inline actions
6. **AddNoteModal component** - Quick note creation
7. **EmptyLeads/Skeleton** - Loading and empty states
8. **LeadsPage** - Full page with filtering, sorting, search
9. **Routing** - Protected route at `/dashboard/leads`

**Design Highlights:**
- Apple-inspired luxury dark theme
- Health indicator badges (🟢 ≥70, 🟡 40-69, 🔴 <40)
- Smooth animations and transitions
- Responsive layout (card/table toggle)
- Bulk selection and CSV export
