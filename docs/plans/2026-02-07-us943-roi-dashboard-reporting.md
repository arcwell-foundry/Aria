# US-943: ROI Dashboard & Reporting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dashboard showing measurable ROI: time saved, actions taken, intelligence delivered, pipeline impact.

**Architecture:** Backend analytics service calculates metrics from messages, goals, and agent executions; frontend dashboard with Apple Health-inspired data visualization using Recharts.

**Tech Stack:** Python FastAPI (backend), React TypeScript + Recharts (frontend), Supabase PostgreSQL (data source).

---

## Task 1: Create Database Migration for ROI Metrics Tracking

**Files:**
- Create: `backend/supabase/migrations/20260207130000_roi_analytics.sql`

**Step 1: Write the migration file**

```sql
-- ROI Analytics tables for tracking time saved and value delivered
-- US-943: ROI Dashboard & Reporting

-- Track ARIA-generated actions that save user time
CREATE TABLE IF NOT EXISTS aria_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('email_draft', 'meeting_prep', 'research_report', 'crm_update', 'follow_up', 'lead_discovery')),
    source_id TEXT, -- Reference to messages, goals, or agent_executions
    status TEXT NOT NULL CHECK (status IN ('pending', 'auto_approved', 'user_approved', 'rejected')),
    estimated_minutes_saved INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Track intelligence delivered to users
CREATE TABLE IF NOT EXISTS intelligence_delivered (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    intelligence_type TEXT NOT NULL CHECK (intelligence_type IN ('fact', 'signal', 'gap_filled', 'briefing', 'proactive_insight')),
    source_id TEXT, -- Reference to memory tables or briefings
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    delivered_at TIMESTAMPTZ DEFAULT NOW()
);

-- Track pipeline impact metrics
CREATE TABLE IF NOT EXISTS pipeline_impact (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    impact_type TEXT NOT NULL CHECK (impact_type IN ('lead_discovered', 'meeting_prepped', 'follow_up_sent', 'deal_influenced')),
    source_id TEXT, -- Reference to leads, meetings, or opportunities
    estimated_value NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_aria_actions_user_created ON aria_actions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aria_actions_type ON aria_actions(action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intelligence_delivered_user ON intelligence_delivered(user_id, delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_impact_user ON pipeline_impact(user_id, created_at DESC);

-- Row Level Security
ALTER TABLE aria_actions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_actions" ON aria_actions
    FOR ALL TO authenticated USING (user_id = auth.uid());

ALTER TABLE intelligence_delivered ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_intelligence" ON intelligence_delivered
    FOR ALL TO authenticated USING (user_id = auth.uid());

ALTER TABLE pipeline_impact ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_pipeline" ON pipeline_impact
    FOR ALL TO authenticated USING (user_id = auth.uid());

-- Admin access for analytics
CREATE POLICY "admin_can_read_actions" ON aria_actions
    FOR SELECT TO authenticated USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role IN ('admin', 'manager')
        )
    );

CREATE POLICY "admin_can_read_intelligence" ON intelligence_delivered
    FOR SELECT TO authenticated USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role IN ('admin', 'manager')
        )
    );

CREATE POLICY "admin_can_read_pipeline" ON pipeline_impact
    FOR SELECT TO authenticated USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role IN ('admin', 'manager')
        )
    );
```

**Step 2: Apply migration to local database**

Run: `cd backend && supabase db push`

Expected: Tables created successfully

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260207130000_roi_analytics.sql
git commit -m "feat: add ROI analytics database tables (US-943 Task 1)"
```

---

## Task 2: Create ROI Pydantic Models

**Files:**
- Create: `backend/src/models/roi.py`

**Step 1: Write the Pydantic models**

```python
"""ROI analytics models for US-943."""

from datetime import datetime
from pydantic import BaseModel, Field


class TimeSavedBreakdown(BaseModel):
    """Time saved breakdown by category."""

    email_drafts: dict[str, int | float] = Field(default_factory=lambda: {"count": 0, "estimated_hours": 0.0})
    meeting_prep: dict[str, int | float] = Field(default_factory=lambda: {"count": 0, "estimated_hours": 0.0})
    research_reports: dict[str, int | float] = Field(default_factory=lambda: {"count": 0, "estimated_hours": 0.0})
    crm_updates: dict[str, int | float] = Field(default_factory=lambda: {"count": 0, "estimated_hours": 0.0})


class TimeSavedMetrics(BaseModel):
    """Time saved metrics."""

    hours: float = 0.0
    breakdown: TimeSavedBreakdown = Field(default_factory=TimeSavedBreakdown)


class IntelligenceDeliveredMetrics(BaseModel):
    """Intelligence delivered metrics."""

    facts_discovered: int = 0
    signals_detected: int = 0
    gaps_filled: int = 0
    briefings_generated: int = 0


class ActionsTakenMetrics(BaseModel):
    """Actions taken metrics."""

    total: int = 0
    auto_approved: int = 0
    user_approved: int = 0
    rejected: int = 0


class PipelineImpactMetrics(BaseModel):
    """Pipeline impact metrics."""

    leads_discovered: int = 0
    meetings_prepped: int = 0
    follow_ups_sent: int = 0


class WeeklyTrendPoint(BaseModel):
    """Single point in weekly trend data."""

    week_start: str
    hours_saved: float


class ROIMetricsResponse(BaseModel):
    """Complete ROI metrics response."""

    time_saved: TimeSavedMetrics
    intelligence_delivered: IntelligenceDeliveredMetrics
    actions_taken: ActionsTakenMetrics
    pipeline_impact: PipelineImpactMetrics
    weekly_trend: list[WeeklyTrendPoint] = Field(default_factory=list)
    period: str
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


class PeriodValidation(BaseModel):
    """Period validation."""

    period: str = Field(..., pattern="^(7d|30d|90d|all)$")
```

**Step 2: Run type check**

Run: `cd backend && mypy src/models/roi.py --strict`

Expected: PASS (or fix any type errors)

**Step 3: Commit**

```bash
git add backend/src/models/roi.py
git commit -m "feat: add ROI Pydantic models (US-943 Task 2)"
```

---

## Task 3: Create ROI Service Layer

**Files:**
- Create: `backend/src/services/roi_service.py`

**Step 1: Write the ROI service**

```python
"""ROI calculation service for US-943.

Time saved calculations:
- Email draft: 15 min saved per draft
- Meeting prep brief: 30 min saved per brief
- Research report: 60 min saved per report
- CRM update: 5 min saved per update
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


# Time saved in minutes per action type
TIME_SAVED_MINUTES = {
    "email_draft": 15,
    "meeting_prep": 30,
    "research_report": 60,
    "crm_update": 5,
}


class ROIService:
    """Service for calculating ROI metrics."""

    def __init__(self, db_client: SupabaseClient) -> None:
        """Initialize the ROI service."""
        self.db = db_client

    def _get_period_start(self, period: str) -> datetime:
        """Get the start datetime for a period.

        Args:
            period: One of '7d', '30d', '90d', 'all'

        Returns:
            Datetime for the start of the period
        """
        now = datetime.utcnow()
        if period == "7d":
            return now - timedelta(days=7)
        if period == "30d":
            return now - timedelta(days=30)
        if period == "90d":
            return now - timedelta(days=90)
        # 'all' - return a very old date
        return datetime(2020, 1, 1)

    async def get_time_saved_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, Any]:
        """Calculate time saved metrics.

        Args:
            user_id: User ID to calculate metrics for
            period_start: Start of the calculation period

        Returns:
            Dictionary with time saved metrics
        """
        # Query aria_actions table
        result = (
            self.db.table("aria_actions")
            .select("action_type", "status", "estimated_minutes_saved")
            .eq("user_id", user_id)
            .gte("created_at", period_start.isoformat())
            .in_("status", ["auto_approved", "user_approved"])
            .execute()
        )

        # Initialize breakdown
        breakdown = {
            "email_drafts": {"count": 0, "estimated_hours": 0.0},
            "meeting_prep": {"count": 0, "estimated_hours": 0.0},
            "research_reports": {"count": 0, "estimated_hours": 0.0},
            "crm_updates": {"count": 0, "estimated_hours": 0.0},
        }

        total_hours = 0.0

        for action in result.data:
            action_type = action.get("action_type")
            minutes = action.get("estimated_minutes_saved", 0)

            if action_type == "email_draft":
                breakdown["email_drafts"]["count"] += 1
                breakdown["email_drafts"]["estimated_hours"] += minutes / 60
            elif action_type == "meeting_prep":
                breakdown["meeting_prep"]["count"] += 1
                breakdown["meeting_prep"]["estimated_hours"] += minutes / 60
            elif action_type == "research_report":
                breakdown["research_reports"]["count"] += 1
                breakdown["research_reports"]["estimated_hours"] += minutes / 60
            elif action_type == "crm_update":
                breakdown["crm_updates"]["count"] += 1
                breakdown["crm_updates"]["estimated_hours"] += minutes / 60

            total_hours += minutes / 60

        return {
            "hours": round(total_hours, 1),
            "breakdown": breakdown,
        }

    async def get_intelligence_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, int]:
        """Calculate intelligence delivered metrics.

        Args:
            user_id: User ID to calculate metrics for
            period_start: Start of the calculation period

        Returns:
            Dictionary with intelligence metrics
        """
        result = (
            self.db.table("intelligence_delivered")
            .select("intelligence_type")
            .eq("user_id", user_id)
            .gte("delivered_at", period_start.isoformat())
            .execute()
        )

        metrics = {
            "facts_discovered": 0,
            "signals_detected": 0,
            "gaps_filled": 0,
            "briefings_generated": 0,
        }

        for item in result.data:
            intel_type = item.get("intelligence_type")
            if intel_type == "fact":
                metrics["facts_discovered"] += 1
            elif intel_type == "signal":
                metrics["signals_detected"] += 1
            elif intel_type == "gap_filled":
                metrics["gaps_filled"] += 1
            elif intel_type == "briefing":
                metrics["briefings_generated"] += 1
            elif intel_type == "proactive_insight":
                metrics["signals_detected"] += 1

        return metrics

    async def get_actions_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, int]:
        """Calculate actions taken metrics.

        Args:
            user_id: User ID to calculate metrics for
            period_start: Start of the calculation period

        Returns:
            Dictionary with action metrics
        """
        result = (
            self.db.table("aria_actions")
            .select("status")
            .eq("user_id", user_id)
            .gte("created_at", period_start.isoformat())
            .execute()
        )

        metrics = {
            "total": len(result.data),
            "auto_approved": 0,
            "user_approved": 0,
            "rejected": 0,
        }

        for item in result.data:
            status = item.get("status")
            if status == "auto_approved":
                metrics["auto_approved"] += 1
            elif status == "user_approved":
                metrics["user_approved"] += 1
            elif status == "rejected":
                metrics["rejected"] += 1

        return metrics

    async def get_pipeline_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, int]:
        """Calculate pipeline impact metrics.

        Args:
            user_id: User ID to calculate metrics for
            period_start: Start of the calculation period

        Returns:
            Dictionary with pipeline metrics
        """
        result = (
            self.db.table("pipeline_impact")
            .select("impact_type")
            .eq("user_id", user_id)
            .gte("created_at", period_start.isoformat())
            .execute()
        )

        metrics = {
            "leads_discovered": 0,
            "meetings_prepped": 0,
            "follow_ups_sent": 0,
        }

        for item in result.data:
            impact_type = item.get("impact_type")
            if impact_type == "lead_discovered":
                metrics["leads_discovered"] += 1
            elif impact_type == "meeting_prepped":
                metrics["meetings_prepped"] += 1
            elif impact_type == "follow_up_sent":
                metrics["follow_ups_sent"] += 1

        return metrics

    async def get_weekly_trend(
        self,
        user_id: str,
        period_start: datetime,
    ) -> list[dict[str, Any]]:
        """Calculate weekly time saved trend.

        Args:
            user_id: User ID to calculate trend for
            period_start: Start of the calculation period

        Returns:
            List of weekly data points
        """
        result = (
            self.db.table("aria_actions")
            .select("created_at", "estimated_minutes_saved")
            .eq("user_id", user_id)
            .gte("created_at", period_start.isoformat())
            .in_("status", ["auto_approved", "user_approved"])
            .order("created_at")
            .execute()
        )

        # Group by week
        weekly_data: dict[str, float] = {}

        for action in result.data:
            created_at_str = action.get("created_at")
            if not created_at_str:
                continue

            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            # Get Monday of the week
            week_start = (created_at - timedelta(days=created_at.weekday())).strftime(
                "%Y-%m-%d"
            )

            minutes = action.get("estimated_minutes_saved", 0)
            weekly_data[week_start] = weekly_data.get(week_start, 0) + minutes / 60

        # Convert to list and sort
        trend = [
            {"week_start": week, "hours_saved": round(hours, 1)}
            for week, hours in sorted(weekly_data.items())
        ]

        return trend

    async def get_all_metrics(
        self,
        user_id: str,
        period: str = "30d",
    ) -> dict[str, Any]:
        """Get all ROI metrics for a user and period.

        Args:
            user_id: User ID to calculate metrics for
            period: One of '7d', '30d', '90d', 'all'

        Returns:
            Complete ROI metrics dictionary
        """
        period_start = self._get_period_start(period)

        time_saved = await self.get_time_saved_metrics(user_id, period_start)
        intelligence = await self.get_intelligence_metrics(user_id, period_start)
        actions = await self.get_actions_metrics(user_id, period_start)
        pipeline = await self.get_pipeline_metrics(user_id, period_start)
        weekly_trend = await self.get_weekly_trend(user_id, period_start)

        return {
            "time_saved": time_saved,
            "intelligence_delivered": intelligence,
            "actions_taken": actions,
            "pipeline_impact": pipeline,
            "weekly_trend": weekly_trend,
            "period": period,
            "calculated_at": datetime.utcnow().isoformat(),
        }
```

**Step 2: Run type check**

Run: `cd backend && mypy src/services/roi_service.py --strict`

Expected: PASS (or fix any type errors)

**Step 3: Commit**

```bash
git add backend/src/services/roi_service.py
git commit -m "feat: add ROI calculation service (US-943 Task 3)"
```

---

## Task 4: Create ROI API Routes

**Files:**
- Create: `backend/src/api/routes/analytics.py`
- Modify: `backend/src/main.py` to register the router

**Step 1: Write the API routes**

```python
"""ROI analytics API routes for US-943."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field, ValidationError

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client
from src.models.roi import (
    ActionsTakenMetrics,
    IntelligenceDeliveredMetrics,
    PeriodValidation,
    PipelineImpactMetrics,
    ROIMetricsResponse,
    TimeSavedBreakdown,
    TimeSavedMetrics,
    WeeklyTrendPoint,
)
from src.services.roi_service import ROIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/roi", response_model=ROIMetricsResponse)
async def get_roi_metrics(
    current_user: CurrentUser,
    period: str = Query(
        default="30d",
        description="Time period: 7d, 30d, 90d, or all",
        regex="^(7d|30d|90d|all)$",
    ),
) -> ROIMetricsResponse:
    """Get ROI metrics for the dashboard.

    Returns time saved, intelligence delivered, actions taken,
    and pipeline impact for the specified time period.

    Args:
        current_user: Authenticated user
        period: Time period for metrics (default: 30d)

    Returns:
        ROI metrics response with all calculated metrics
    """
    try:
        # Validate period
        PeriodValidation(period=period)
    except ValidationError as e:
        logger.warning(f"Invalid period requested: {period}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period. Must be one of: 7d, 30d, 90d, all",
        ) from e

    db = get_supabase_client()
    service = ROIService(db_client=db)

    try:
        metrics = await service.get_all_metrics(
            user_id=current_user.id,
            period=period,
        )

        logger.info(
            "ROI metrics retrieved",
            extra={
                "user_id": current_user.id,
                "period": period,
                "hours_saved": metrics["time_saved"]["hours"],
            },
        )

        return ROIMetricsResponse(**metrics)

    except Exception as e:
        logger.exception(
            "Failed to calculate ROI metrics",
            extra={"user_id": current_user.id, "period": period},
        )
        raise HTTPException(
            status_code=503,
            detail="ROI metrics service temporarily unavailable",
        ) from e


@router.get("/roi/trend", response_model=list[WeeklyTrendPoint])
async def get_roi_trend(
    current_user: CurrentUser,
    period: str = Query(
        default="90d",
        description="Time period: 7d, 30d, 90d, or all",
        regex="^(7d|30d|90d|all)$",
    ),
) -> list[WeeklyTrendPoint]:
    """Get weekly ROI trend data.

    Returns time saved per week for the specified period.

    Args:
        current_user: Authenticated user
        period: Time period for trend data (default: 90d)

    Returns:
        List of weekly trend data points
    """
    try:
        PeriodValidation(period=period)
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period. Must be one of: 7d, 30d, 90d, all",
        ) from e

    db = get_supabase_client()
    service = ROIService(db_client=db)

    try:
        period_start = service._get_period_start(period)
        trend = await service.get_weekly_trend(
            user_id=current_user.id,
            period_start=period_start,
        )

        return [WeeklyTrendPoint(**point) for point in trend]

    except Exception as e:
        logger.exception(
            "Failed to get ROI trend",
            extra={"user_id": current_user.id, "period": period},
        )
        raise HTTPException(
            status_code=503,
            detail="ROI trend service temporarily unavailable",
        ) from e
```

**Step 2: Register router in main.py**

Add to `backend/src/main.py`:
```python
from src.api.routes import analytics

# Include after other router inclusions
app.include_router(analytics.router, prefix="/api/v1")
```

**Step 3: Run type check**

Run: `cd backend && mypy src/api/routes/analytics.py --strict`

Expected: PASS (or fix any type errors)

**Step 4: Commit**

```bash
git add backend/src/api/routes/analytics.py backend/src/main.py
git commit -m "feat: add ROI analytics API routes (US-943 Task 4)"
```

---

## Task 5: Add Recharts Dependency to Frontend

**Files:**
- Modify: `frontend/package.json`

**Step 1: Add Recharts dependency**

Add to `dependencies` in `frontend/package.json`:
```json
"recharts": "^2.15.0"
```

**Step 2: Install the dependency**

Run: `cd frontend && npm install`

Expected: Recharts installed successfully

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat: add Recharts dependency for ROI dashboard (US-943 Task 5)"
```

---

## Task 6: Create ROI API Client

**Files:**
- Create: `frontend/src/api/roi.ts`

**Step 1: Write the API client**

```typescript
/** ROI analytics API client for US-943. */

import { apiClient } from "./client";

// Time saved breakdown by category
export interface TimeSavedBreakdown {
  email_drafts: { count: number; estimated_hours: number };
  meeting_prep: { count: number; estimated_hours: number };
  research_reports: { count: number; estimated_hours: number };
  crm_updates: { count: number; estimated_hours: number };
}

// Time saved metrics
export interface TimeSavedMetrics {
  hours: number;
  breakdown: TimeSavedBreakdown;
}

// Intelligence delivered metrics
export interface IntelligenceDeliveredMetrics {
  facts_discovered: number;
  signals_detected: number;
  gaps_filled: number;
  briefings_generated: number;
}

// Actions taken metrics
export interface ActionsTakenMetrics {
  total: number;
  auto_approved: number;
  user_approved: number;
  rejected: number;
}

// Pipeline impact metrics
export interface PipelineImpactMetrics {
  leads_discovered: number;
  meetings_prepped: number;
  follow_ups_sent: number;
}

// Weekly trend data point
export interface WeeklyTrendPoint {
  week_start: string;
  hours_saved: number;
}

// Complete ROI metrics response
export interface ROIMetricsResponse {
  time_saved: TimeSavedMetrics;
  intelligence_delivered: IntelligenceDeliveredMetrics;
  actions_taken: ActionsTakenMetrics;
  pipeline_impact: PipelineImpactMetrics;
  weekly_trend: WeeklyTrendPoint[];
  period: string;
  calculated_at: string;
}

/** Get ROI metrics for the specified period. */
export async function getROIMetrics(period: string = "30d"): Promise<ROIMetricsResponse> {
  const response = await apiClient.get<ROIMetricsResponse>("/analytics/roi", {
    params: { period },
  });
  return response.data;
}

/** Get weekly ROI trend data. */
export async function getROITrend(period: string = "90d"): Promise<WeeklyTrendPoint[]> {
  const response = await apiClient.get<WeeklyTrendPoint[]>("/analytics/roi/trend", {
    params: { period },
  });
  return response.data;
}
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`

Expected: PASS (or fix any type errors)

**Step 3: Commit**

```bash
git add frontend/src/api/roi.ts
git commit -m "feat: add ROI analytics API client (US-943 Task 6)"
```

---

## Task 7: Create ROI Custom Hook

**Files:**
- Create: `frontend/src/hooks/useROI.ts`

**Step 1: Write the custom hook**

```typescript
/** Custom hook for ROI analytics data. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getROIMetrics, getROITrend, ROIMetricsResponse, WeeklyTrendPoint } from "@/api/roi";

/** Query keys for ROI data. */
export const roiKeys = {
  all: ["roi"] as const,
  metrics: (period: string) => ["roi", "metrics", period] as const,
  trend: (period: string) => ["roi", "trend", period] as const,
};

/** Hook for fetching ROI metrics. */
export function useROIMetrics(period: string = "30d") {
  const queryClient = useQueryClient();

  return useQuery({
    queryKey: roiKeys.metrics(period),
    queryFn: () => getROIMetrics(period),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 15 * 60 * 1000, // 15 minutes
  });
}

/** Hook for fetching ROI trend data. */
export function useROITrend(period: string = "90d") {
  return useQuery({
    queryKey: roiKeys.trend(period),
    queryFn: () => getROITrend(period),
    staleTime: 10 * 60 * 1000, // 10 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/** Hook for invalidating ROI queries. */
export function useInvalidateROI() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.invalidateQueries({ queryKey: roiKeys.all });
  };
}
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`

Expected: PASS (or fix any type errors)

**Step 3: Commit**

```bash
git add frontend/src/hooks/useROI.ts
git commit -m "feat: add ROI custom React hook (US-943 Task 7)"
```

---

## Task 8: Create ROI Dashboard Page Component

**Files:**
- Create: `frontend/src/pages/ROIDashboardPage.tsx`

**Step 1: Write the ROI dashboard page**

```typescript
/** ROI Dashboard page - US-943. */

import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { HelpTooltip } from "@/components/HelpTooltip";
import { useROIMetrics, useROITrend } from "@/hooks/useROI";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  LineChart,
  Line,
  Legend,
} from "recharts";

type Period = "7d" | "30d" | "90d" | "all";

const PERIODS: { value: Period; label: string }[] = [
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "90d", label: "90 days" },
  { value: "all", label: "All time" },
];

// Colors for charts (desaturated, per design system)
const CHART_COLORS = {
  emailDrafts: "#5B6E8A",
  meetingPrep: "#6B7FA3",
  researchReports: "#8B92A5",
  crmUpdates: "#7B8EAA",
  trend: "#5B6E8A",
};

// Data for pie chart from time saved breakdown
function getTimeSavedData(breakdown: typeof import("@/api/roi").TimeSavedBreakdown) {
  return [
    { name: "Email drafts", hours: breakdown.email_drafts.estimated_hours, color: CHART_COLORS.emailDrafts },
    { name: "Meeting prep", hours: breakdown.meeting_prep.estimated_hours, color: CHART_COLORS.meetingPrep },
    { name: "Research reports", hours: breakdown.research_reports.estimated_hours, color: CHART_COLORS.researchReports },
    { name: "CRM updates", hours: breakdown.crm_updates.estimated_hours, color: CHART_COLORS.crmUpdates },
  ].filter((item) => item.hours > 0);
}

export function ROIDashboardPage() {
  const [selectedPeriod, setSelectedPeriod] = useState<Period>("30d");

  const { data: roiData, isLoading, error } = useROIMetrics(selectedPeriod);
  const { data: trendData } = useROITrend(selectedPeriod);

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8 min-h-screen bg-[#0F1117]">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-2">
              <h1 className="font-display text-3xl text-[#E8E6E1]">Your ARIA ROI</h1>
              <HelpTooltip
                content="Track the measurable value ARIA delivers: time saved, intelligence discovered, and impact on your pipeline."
                placement="right"
              />
            </div>

            {/* Period Selector */}
            <div className="flex bg-[#161B2E] rounded-lg p-1 border border-[#2A2F42]">
              {PERIODS.map((period) => (
                <button
                  key={period.value}
                  onClick={() => setSelectedPeriod(period.value)}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    selectedPeriod === period.value
                      ? "bg-[#5B6E8A] text-white"
                      : "text-[#8B92A5] hover:text-[#E8E6E1]"
                  }`}
                >
                  {period.label}
                </button>
              ))}
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="text-center py-12">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[#5B6E8A]"></div>
              <p className="mt-4 text-[#8B92A5]">Calculating your ROI...</p>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-[#A66B6B]/10 border border-[#A66B6B]/30 rounded-lg p-6 text-center">
              <p className="text-[#A66B6B]">Unable to load ROI metrics. Please try again later.</p>
            </div>
          )}

          {/* ROI Dashboard Content */}
          {roiData && (
            <div className="space-y-6">
              {/* Hero Metric - Time Saved */}
              <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-8">
                <p className="text-[#8B92A5] text-sm uppercase tracking-wide mb-2">Total Time Saved</p>
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-6xl text-[#5B6E8A]">
                    {roiData.time_saved.hours}
                  </span>
                  <span className="text-[#8B92A5] text-xl">hours</span>
                </div>
                <p className="text-[#8B92A5] mt-2">
                  in the {selectedPeriod === "all" ? "lifetime" : `last ${PERIODS.find((p) => p.value === selectedPeriod)?.label.toLowerCase()}`}
                </p>
              </div>

              {/* Metrics Grid - 2x2 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Time Saved Breakdown */}
                <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
                  <h3 className="font-display text-lg text-[#E8E6E1] mb-4">Time Saved by Activity</h3>
                  {roiData.time_saved.hours > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={getTimeSavedData(roiData.time_saved.breakdown)}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                          outerRadius={70}
                          dataKey="hours"
                        >
                          {getTimeSavedData(roiData.time_saved.breakdown).map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#161B2E",
                            border: "1px solid #2A2F42",
                            borderRadius: "8px",
                            color: "#E8E6E1",
                          }}
                          formatter={(value: number) => [`${value.toFixed(1)}h`, "Time saved"]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-[#8B92A5] text-center py-8">No data yet for this period</p>
                  )}
                </div>

                {/* Intelligence Delivered */}
                <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
                  <h3 className="font-display text-lg text-[#E8E6E1] mb-4">Intelligence Delivered</h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Facts discovered</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">
                        {roiData.intelligence_delivered.facts_discovered}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Signals detected</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">
                        {roiData.intelligence_delivered.signals_detected}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Knowledge gaps filled</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">
                        {roiData.intelligence_delivered.gaps_filled}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Briefings generated</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">
                        {roiData.intelligence_delivered.briefings_generated}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Actions Taken */}
                <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
                  <h3 className="font-display text-lg text-[#E8E6E1] mb-4">Actions Taken</h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Total actions</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">{roiData.actions_taken.total}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Auto-approved</span>
                      <span className="font-mono text-[#6B8F71] text-xl">
                        {roiData.actions_taken.auto_approved}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">You approved</span>
                      <span className="font-mono text-[#5B6E8A] text-xl">
                        {roiData.actions_taken.user_approved}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Rejected</span>
                      <span className="font-mono text-[#A66B6B] text-xl">{roiData.actions_taken.rejected}</span>
                    </div>
                  </div>
                </div>

                {/* Pipeline Impact */}
                <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
                  <h3 className="font-display text-lg text-[#E8E6E1] mb-4">Pipeline Impact</h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Leads discovered</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">
                        {roiData.pipeline_impact.leads_discovered}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Meetings prepared</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">
                        {roiData.pipeline_impact.meetings_prepped}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[#8B92A5]">Follow-ups sent</span>
                      <span className="font-mono text-[#E8E6E1] text-xl">
                        {roiData.pipeline_impact.follow_ups_sent}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Weekly Trend Line Chart */}
              {trendData && trendData.length > 0 && (
                <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
                  <h3 className="font-display text-lg text-[#E8E6E1] mb-4">Weekly Time Saved Trend</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={trendData}>
                      <XAxis
                        dataKey="week_start"
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                        stroke="#8B92A5"
                        tick={{ fill: "#8B92A5", fontSize: 11 }}
                      />
                      <YAxis
                        stroke="#8B92A5"
                        tick={{ fill: "#8B92A5", fontSize: 11 }}
                        label={{ value: "Hours saved", angle: -90, position: "insideLeft", fill: "#8B92A5" }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#161B2E",
                          border: "1px solid #2A2F42",
                          borderRadius: "8px",
                          color: "#E8E6E1",
                        }}
                        labelFormatter={(value) => `Week of ${new Date(value).toLocaleDateString()}`}
                        formatter={(value: number) => [`${value}h`, "Time saved"]}
                      />
                      <Line
                        type="monotone"
                        dataKey="hours_saved"
                        stroke={CHART_COLORS.trend}
                        strokeWidth={2}
                        dot={{ fill: CHART_COLORS.trend, strokeWidth: 2, r: 4 }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Export Button */}
              <div className="flex justify-end">
                <button
                  onClick={() => {
                    // TODO: Implement PDF export
                    console.log("Export not yet implemented");
                  }}
                  className="px-6 py-2.5 bg-[#5B6E8A] text-white rounded-lg font-medium hover:bg-[#4A5D79] transition-colors duration-150"
                >
                  Download Report
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
```

**Step 2: Run type check**

Run: `cd frontend && npm run typecheck`

Expected: PASS (or fix any type errors)

**Step 3: Commit**

```bash
git add frontend/src/pages/ROIDashboardPage.tsx
git commit -m "feat: add ROI dashboard page component (US-943 Task 8)"
```

---

## Task 9: Add ROI Dashboard Route and Export

**Files:**
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Add ROI dashboard to pages index**

Add to `frontend/src/pages/index.ts`:
```typescript
export { ROIDashboardPage } from "./ROIDashboardPage";
```

**Step 2: Add route to App.tsx**

Add to routes in `frontend/src/App.tsx`:
```typescript
import { ROIDashboardPage } from "./pages";
```

Then add the route:
```typescript
<Route path="/dashboard/roi" element={<ROIDashboardPage />} />
```

**Step 3: Run type check**

Run: `cd frontend && npm run typecheck`

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat: add ROI dashboard route (US-943 Task 9)"
```

---

## Task 10: Write Backend Tests for ROI Service

**Files:**
- Create: `backend/tests/services/test_roi_service.py`

**Step 1: Write failing tests**

```python
"""Tests for ROI service."""

import pytest
from datetime import datetime, timedelta

from src.services.roi_service import ROIService
from src.db.supabase import get_supabase_client


@pytest.fixture
def roi_service():
    """Create ROI service fixture."""
    db = get_supabase_client()
    return ROIService(db_client=db)


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "00000000-0000-0000-0000-000000000000"


def test_get_period_start(roi_service):
    """Test period start calculation."""
    # 7d period
    period_7d = roi_service._get_period_start("7d")
    expected_7d = datetime.utcnow() - timedelta(days=7)
    assert abs((period_7d - expected_7d).total_seconds()) < 60  # Within 1 minute

    # 30d period
    period_30d = roi_service._get_period_start("30d")
    expected_30d = datetime.utcnow() - timedelta(days=30)
    assert abs((period_30d - expected_30d).total_seconds()) < 60

    # 90d period
    period_90d = roi_service._get_period_start("90d")
    expected_90d = datetime.utcnow() - timedelta(days=90)
    assert abs((period_90d - expected_90d).total_seconds()) < 60

    # all period
    period_all = roi_service._get_period_start("all")
    assert period_all.year == 2020
    assert period_all.month == 1
    assert period_all.day == 1


def test_get_time_saved_metrics_empty(roi_service, test_user_id):
    """Test time saved metrics with no data."""
    period_start = datetime.utcnow() - timedelta(days=30)
    metrics = roi_service.get_time_saved_metrics(test_user_id, period_start)

    # Should return empty metrics
    assert metrics["hours"] == 0.0
    assert metrics["breakdown"]["email_drafts"]["count"] == 0
    assert metrics["breakdown"]["email_drafts"]["estimated_hours"] == 0.0


def test_get_intelligence_metrics_empty(roi_service, test_user_id):
    """Test intelligence metrics with no data."""
    period_start = datetime.utcnow() - timedelta(days=30)
    metrics = roi_service.get_intelligence_metrics(test_user_id, period_start)

    assert metrics["facts_discovered"] == 0
    assert metrics["signals_detected"] == 0
    assert metrics["gaps_filled"] == 0
    assert metrics["briefings_generated"] == 0


def test_get_actions_metrics_empty(roi_service, test_user_id):
    """Test actions metrics with no data."""
    period_start = datetime.utcnow() - timedelta(days=30)
    metrics = roi_service.get_actions_metrics(test_user_id, period_start)

    assert metrics["total"] == 0
    assert metrics["auto_approved"] == 0
    assert metrics["user_approved"] == 0
    assert metrics["rejected"] == 0


def test_get_pipeline_metrics_empty(roi_service, test_user_id):
    """Test pipeline metrics with no data."""
    period_start = datetime.utcnow() - timedelta(days=30)
    metrics = roi_service.get_pipeline_metrics(test_user_id, period_start)

    assert metrics["leads_discovered"] == 0
    assert metrics["meetings_prepped"] == 0
    assert metrics["follow_ups_sent"] == 0


def test_get_weekly_trend_empty(roi_service, test_user_id):
    """Test weekly trend with no data."""
    period_start = datetime.utcnow() - timedelta(days=30)
    trend = roi_service.get_weekly_trend(test_user_id, period_start)

    assert trend == []


@pytest.mark.asyncio
async def test_get_all_metrics(roi_service, test_user_id):
    """Test getting all metrics together."""
    metrics = await roi_service.get_all_metrics(test_user_id, "30d")

    assert "time_saved" in metrics
    assert "intelligence_delivered" in metrics
    assert "actions_taken" in metrics
    assert "pipeline_impact" in metrics
    assert "weekly_trend" in metrics
    assert metrics["period"] == "30d"
    assert "calculated_at" in metrics
```

**Step 2: Run tests to verify they fail appropriately**

Run: `cd backend && pytest tests/services/test_roi_service.py -v`

Expected: Some tests may pass (structure tests), data tests will return 0 due to no test data

**Step 3: Commit**

```bash
git add backend/tests/services/test_roi_service.py
git commit -m "test: add ROI service tests (US-943 Task 10)"
```

---

## Task 11: Write Frontend Tests for ROI Dashboard

**Files:**
- Create: `frontend/src/pages/__tests__/ROIDashboardPage.test.tsx`

**Step 1: Write the tests**

```typescript
/** Tests for ROI Dashboard page. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ROIDashboardPage } from "../ROIDashboardPage";

// Mock the API module
vi.mock("@/api/roi", () => ({
  getROIMetrics: vi.fn(),
  getROITrend: vi.fn(),
}));

// Mock DashboardLayout
vi.mock("@/components/DashboardLayout", () => ({
  DashboardLayout: ({ children }: { children: React.ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));

// Mock HelpTooltip
vi.mock("@/components/HelpTooltip", () => ({
  HelpTooltip: ({ content }: { content: string }) => <div data-testid="help-tooltip">{content}</div>,
}));

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
}

function renderWithQueryClient(component: React.ReactElement) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      {component}
    </QueryClientProvider>
  );
}

describe("ROIDashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the page header with title", () => {
    renderWithQueryClient(<ROIDashboardPage />);

    expect(screen.getByText("Your ARIA ROI")).toBeInTheDocument();
  });

  it("renders period selector buttons", () => {
    renderWithQueryClient(<ROIDashboardPage />);

    expect(screen.getByText("7 days")).toBeInTheDocument();
    expect(screen.getByText("30 days")).toBeInTheDocument();
    expect(screen.getByText("90 days")).toBeInTheDocument();
    expect(screen.getByText("All time")).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    renderWithQueryClient(<ROIDashboardPage />);

    expect(screen.getByText(/Calculating your ROI/i)).toBeInTheDocument();
  });

  it("renders metrics cards when data is loaded", async () => {
    // Mock successful response
    const { getROIMetrics } = await import("@/api/roi");
    vi.mocked(getROIMetrics).mockResolvedValue({
      time_saved: {
        hours: 12.5,
        breakdown: {
          email_drafts: { count: 10, estimated_hours: 2.5 },
          meeting_prep: { count: 5, estimated_hours: 2.5 },
          research_reports: { count: 2, estimated_hours: 2.0 },
          crm_updates: { count: 20, estimated_hours: 1.7 },
        },
      },
      intelligence_delivered: {
        facts_discovered: 50,
        signals_detected: 15,
        gaps_filled: 8,
        briefings_generated: 10,
      },
      actions_taken: {
        total: 37,
        auto_approved: 20,
        user_approved: 15,
        rejected: 2,
      },
      pipeline_impact: {
        leads_discovered: 5,
        meetings_prepped: 8,
        follow_ups_sent: 12,
      },
      weekly_trend: [],
      period: "30d",
      calculated_at: new Date().toISOString(),
    });

    renderWithQueryClient(<ROIDashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("12.5")).toBeInTheDocument(); // Hours saved
    });

    expect(screen.getByText("Time Saved by Activity")).toBeInTheDocument();
    expect(screen.getByText("Intelligence Delivered")).toBeInTheDocument();
    expect(screen.getByText("Actions Taken")).toBeInTheDocument();
    expect(screen.getByText("Pipeline Impact")).toBeInTheDocument();
  });

  it("shows empty state when no data available", async () => {
    const { getROIMetrics } = await import("@/api/roi");
    vi.mocked(getROIMetrics).mockResolvedValue({
      time_saved: { hours: 0, breakdown: { email_drafts: { count: 0, estimated_hours: 0 }, meeting_prep: { count: 0, estimated_hours: 0 }, research_reports: { count: 0, estimated_hours: 0 }, crm_updates: { count: 0, estimated_hours: 0 } } },
      intelligence_delivered: { facts_discovered: 0, signals_detected: 0, gaps_filled: 0, briefings_generated: 0 },
      actions_taken: { total: 0, auto_approved: 0, user_approved: 0, rejected: 0 },
      pipeline_impact: { leads_discovered: 0, meetings_prepped: 0, follow_ups_sent: 0 },
      weekly_trend: [],
      period: "30d",
      calculated_at: new Date().toISOString(),
    });

    renderWithQueryClient(<ROIDashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("No data yet for this period")).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run tests**

Run: `cd frontend && npm test -- ROIDashboardPage`

Expected: Tests pass

**Step 3: Commit**

```bash
git add frontend/src/pages/__tests__/ROIDashboardPage.test.tsx
git commit -m "test: add ROI dashboard frontend tests (US-943 Task 11)"
```

---

## Task 12: Run Quality Gates

**Files:**
- None (verification task)

**Step 1: Run backend type check**

Run: `cd backend && mypy src/ --strict`

Expected: PASS or fix type errors

**Step 2: Run backend tests**

Run: `cd backend && pytest tests/ -v`

Expected: All tests pass

**Step 3: Run frontend type check**

Run: `cd frontend && npm run typecheck`

Expected: PASS

**Step 4: Run frontend linting**

Run: `cd frontend && npm run lint`

Expected: PASS or run `npm run lint:fix`

**Step 5: Run frontend tests**

Run: `cd frontend && npm test:run`

Expected: All tests pass

**Step 6: Manual verification**

1. Start backend: `cd backend && uvicorn src.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to `http://localhost:5173/dashboard/roi`
4. Verify:
   - Dashboard loads with DARK SURFACE theme
   - Period selector works
   - Charts render (empty state is okay for new installation)
   - All metric cards display
   - No console errors

**Step 7: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: resolve quality gate issues for ROI dashboard (US-943 Task 12)"
```

---

## Task 13: Apply Database Migration to Production

**Files:**
- None (deployment task)

**Step 1: Apply migration to remote Supabase**

Run: `cd backend && supabase db push --db-url "$DATABASE_URL"`

Expected: Migration applied successfully

**Step 2: Verify tables exist**

Run: `cd backend && python -c "from src.db.supabase import get_supabase_client; db = get_supabase_client(); print(db.table('aria_actions').select('*').limit(1).execute())"`

Expected: Query succeeds (even with empty result)

**Step 3: Commit**

```bash
git add -A
git commit -m "deploy: apply ROI analytics migration to production (US-943 Task 13)"
```

---

## Task 14: Final Integration - Seed Test Data

**Files:**
- Create: `backend/scripts/seed_roi_data.py` (optional, for demonstration)

**Step 1: Create seed script for testing (optional)**

```python
"""Seed ROI data for testing the dashboard."""

import asyncio
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.supabase import get_supabase_client


async def seed_test_data(user_id: str):
    """Seed test ROI data for a user."""
    db = get_supabase_client()

    # Seed some aria_actions
    actions = [
        {"user_id": user_id, "action_type": "email_draft", "status": "user_approved", "estimated_minutes_saved": 15},
        {"user_id": user_id, "action_type": "email_draft", "status": "auto_approved", "estimated_minutes_saved": 15},
        {"user_id": user_id, "action_type": "meeting_prep", "status": "user_approved", "estimated_minutes_saved": 30},
        {"user_id": user_id, "action_type": "research_report", "status": "user_approved", "estimated_minutes_saved": 60},
        {"user_id": user_id, "action_type": "crm_update", "status": "auto_approved", "estimated_minutes_saved": 5},
    ]

    for i, action in enumerate(actions):
        # Create actions from the last 5 days
        created_at = (datetime.utcnow() - timedelta(days=i)).isoformat()
        action["created_at"] = created_at
        db.table("aria_actions").insert(action).execute()

    # Seed intelligence_delivered
    intelligence = [
        {"user_id": user_id, "intelligence_type": "fact", "confidence_score": 0.9},
        {"user_id": user_id, "intelligence_type": "signal", "confidence_score": 0.8},
        {"user_id": user_id, "intelligence_type": "gap_filled", "confidence_score": 0.7},
        {"user_id": user_id, "intelligence_type": "briefing", "confidence_score": 1.0},
    ]

    for item in intelligence:
        db.table("intelligence_delivered").insert(item).execute()

    # Seed pipeline_impact
    pipeline = [
        {"user_id": user_id, "impact_type": "lead_discovered"},
        {"user_id": user_id, "impact_type": "meeting_prepped"},
        {"user_id": user_id, "impact_type": "follow_up_sent"},
    ]

    for item in pipeline:
        db.table("pipeline_impact").insert(item).execute()

    print(f"Seeded test ROI data for user {user_id}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seed_roi_data.py <user_id>")
        sys.exit(1)

    user_id = sys.argv[1]
    asyncio.run(seed_test_data(user_id))
```

**Step 2: Commit (optional)**

```bash
git add backend/scripts/seed_roi_data.py
git commit -m "feat: add ROI data seeding script for testing (US-943 Task 14)"
```

---

## Task 15: Final Verification and Documentation

**Files:**
- Modify: `docs/PHASE_9_PRODUCT_COMPLETENESS.md` (mark US-943 complete)

**Step 1: Update Phase 9 checklist**

In `docs/PHASE_9_PRODUCT_COMPLETENESS.md`, add checkbox for US-943:

```markdown
- [ ] US-943: ROI dashboard calculating meaningful metrics
```

**Step 2: Final integration test**

1. Verify route works: navigate to `/dashboard/roi`
2. Test period selector changes
3. Verify API responses are correct format
4. Check empty states display properly

**Step 3: Create summary commit**

```bash
git add docs/PHASE_9_PRODUCT_COMPLETENESS.md
git commit -m "docs: mark US-943 ROI Dashboard complete in Phase 9 checklist"
```

**Step 4: Push to remote**

Run: `git push origin main`

---

## Notes for Implementation

### Design System Compliance
- Use DARK SURFACE theme (`bg-[#0F1117]`, `bg-[#161B2E]`)
- Colors from design system only
- Instrument Serif for headings, JetBrains Mono for data
- Desaturated colors for charts (no neon)

### Time Saved Calculation Logic
The backend service calculates time saved from `aria_actions` table. For production:
- Email drafts, meeting prep, research must create entries in `aria_actions` when completed
- Each action should set `estimated_minutes_saved` based on action type
- Status should be updated as actions are approved/rejected

### Future Enhancements (Not in Scope)
- PDF export functionality (placeholder in UI)
- Attribution tracking (which ARIA action led to which outcome)
- Team-level ROI aggregation (admin view)
- Industry benchmark comparisons

### Testing
- Tests verify structure and empty state behavior
- Full integration tests require seeded data
- Manual verification recommended for chart rendering
