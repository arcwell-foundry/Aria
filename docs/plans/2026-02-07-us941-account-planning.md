# US-941: Account Planning & Strategic Workflows — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build account-level strategic tools: account plans, territory view, pipeline forecasting, quota tracking — all powered by Lead Memory data and LLM-generated strategy.

**Architecture:** Accounts are views over existing Lead Memory records (lifecycle_stage = any). The `account_plans` table stores LLM-generated strategy documents per lead. `user_quotas` stores quota targets. Forecasting is computed at query time from lead health_score × expected_value. Frontend is a single AccountsPage with territory table, account detail slide-over, forecast chart (Recharts), and quota tracker.

**Tech Stack:** Python/FastAPI backend, Supabase (PostgreSQL), LLMClient (Claude), React/TypeScript/Tailwind frontend, Recharts for charts, React Query for data fetching.

---

## Task 1: Database Migration

**Files:**
- Create: `backend/supabase/migrations/20260208_account_planning.sql`

**Step 1: Write the migration**

```sql
-- US-941: Account Planning & Strategic Workflows
-- account_plans: LLM-generated strategy documents per lead
CREATE TABLE IF NOT EXISTS account_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    lead_memory_id UUID NOT NULL REFERENCES lead_memories(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL DEFAULT '',
    next_actions JSONB NOT NULL DEFAULT '[]',
    stakeholder_summary JSONB NOT NULL DEFAULT '{}',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, lead_memory_id)
);

ALTER TABLE account_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_account_plans" ON account_plans
    FOR ALL TO authenticated USING (user_id = auth.uid());

CREATE INDEX idx_account_plans_user ON account_plans(user_id);
CREATE INDEX idx_account_plans_lead ON account_plans(lead_memory_id);

-- user_quotas: quota tracking per user per period
CREATE TABLE IF NOT EXISTS user_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    period TEXT NOT NULL,  -- e.g. '2026-Q1', '2026-02'
    target_value NUMERIC NOT NULL DEFAULT 0,
    actual_value NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, period)
);

ALTER TABLE user_quotas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_user_quotas" ON user_quotas
    FOR ALL TO authenticated USING (user_id = auth.uid());

CREATE INDEX idx_user_quotas_user_period ON user_quotas(user_id, period);
```

**Step 2: Apply migration to remote database**

Run: `cd /Users/dhruv/aria && PGPASSWORD=$SUPABASE_DB_PASSWORD psql -h $SUPABASE_DB_HOST -U postgres -d postgres -f backend/supabase/migrations/20260208_account_planning.sql`

If env vars are not set, check `.env` files or Supabase dashboard for connection string.

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260208_account_planning.sql
git commit -m "feat(US-941): add account_plans and user_quotas tables with RLS"
```

---

## Task 2: Backend Pydantic Models

**Files:**
- Create: `backend/src/models/account_planning.py`

**Step 1: Write the models**

```python
"""Pydantic models for US-941 Account Planning & Strategic Workflows."""

from datetime import datetime

from pydantic import BaseModel, Field


# --- Account Plan ---

class AccountPlanUpdate(BaseModel):
    """Request body for updating an account plan's strategy text."""

    strategy: str = Field(..., min_length=1, description="User-edited strategy document")


class AccountPlanResponse(BaseModel):
    """Response for an account plan."""

    id: str
    user_id: str
    lead_memory_id: str
    strategy: str
    next_actions: list[dict[str, object]]
    stakeholder_summary: dict[str, object]
    generated_at: datetime
    updated_at: datetime


# --- Territory / Account list item ---

class AccountListItem(BaseModel):
    """Single row in the territory table."""

    id: str
    company_name: str
    lifecycle_stage: str
    status: str
    health_score: int
    expected_value: float | None
    last_activity_at: datetime | None
    next_action: str | None


# --- Forecast ---

class ForecastStage(BaseModel):
    """Pipeline value for a single lifecycle stage."""

    stage: str
    count: int
    total_value: float
    weighted_value: float


class ForecastResponse(BaseModel):
    """Pipeline forecast response."""

    stages: list[ForecastStage]
    total_pipeline: float
    weighted_pipeline: float


# --- Quota ---

class QuotaSet(BaseModel):
    """Request body for setting a quota."""

    period: str = Field(
        ..., min_length=1, max_length=20, description="Period key, e.g. '2026-Q1'"
    )
    target_value: float = Field(..., ge=0, description="Quota target value")


class QuotaResponse(BaseModel):
    """Quota tracking response."""

    id: str
    user_id: str
    period: str
    target_value: float
    actual_value: float
    created_at: datetime
    updated_at: datetime
```

**Step 2: Verify with ruff**

Run: `cd /Users/dhruv/aria && ruff check backend/src/models/account_planning.py && ruff format backend/src/models/account_planning.py`

**Step 3: Commit**

```bash
git add backend/src/models/account_planning.py
git commit -m "feat(US-941): add Pydantic models for account planning"
```

---

## Task 3: Backend Service Layer

**Files:**
- Create: `backend/src/services/account_planning_service.py`

**Dependencies:** Uses `SupabaseClient`, `LLMClient`, lead_memories table, account_plans table, user_quotas table, lead_stakeholders table, lead_events table.

**Step 1: Write the service**

```python
"""Account planning service for US-941.

Provides:
- Territory listing (accounts from lead_memories)
- Account plan generation & updates (LLM-powered)
- Pipeline forecasting (health_score × expected_value)
- Quota CRUD
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Stage probability weights for forecast
STAGE_WEIGHTS: dict[str, float] = {
    "lead": 0.10,
    "opportunity": 0.40,
    "account": 0.80,
}


class AccountPlanningService:
    """Service for account planning and strategic workflows."""

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    # ------------------------------------------------------------------ #
    # Territory                                                           #
    # ------------------------------------------------------------------ #

    async def list_accounts(
        self,
        user_id: str,
        stage: str | None = None,
        sort_by: str = "last_activity_at",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List accounts (lead memories) with optional stage filter.

        Args:
            user_id: The user's ID.
            stage: Optional lifecycle stage filter.
            sort_by: Column to sort by.
            limit: Max rows returned.

        Returns:
            List of account dicts.
        """
        query = (
            self._db.table("lead_memories")
            .select("id, company_name, lifecycle_stage, status, health_score, "
                    "expected_value, last_activity_at, tags")
            .eq("user_id", user_id)
        )

        if stage:
            query = query.eq("lifecycle_stage", stage)

        valid_sorts = {
            "last_activity_at", "health_score", "expected_value", "company_name",
        }
        col = sort_by if sort_by in valid_sorts else "last_activity_at"
        desc = col != "company_name"
        result = query.order(col, desc=desc).limit(limit).execute()

        accounts = cast(list[dict[str, Any]], result.data)

        # Attach latest next-action from account_plans if available
        if accounts:
            lead_ids = [a["id"] for a in accounts]
            plans_result = (
                self._db.table("account_plans")
                .select("lead_memory_id, next_actions")
                .eq("user_id", user_id)
                .in_("lead_memory_id", lead_ids)
                .execute()
            )
            plans_map: dict[str, list[Any]] = {
                p["lead_memory_id"]: p["next_actions"]
                for p in cast(list[dict[str, Any]], plans_result.data)
            }
            for acct in accounts:
                actions = plans_map.get(acct["id"], [])
                acct["next_action"] = actions[0].get("action", "") if actions else None

        logger.info(
            "Accounts listed",
            extra={"user_id": user_id, "count": len(accounts)},
        )
        return accounts

    # ------------------------------------------------------------------ #
    # Account Plan                                                        #
    # ------------------------------------------------------------------ #

    async def get_or_generate_plan(
        self, user_id: str, lead_id: str
    ) -> dict[str, Any] | None:
        """Get existing plan or generate one with LLM.

        Args:
            user_id: The user's ID.
            lead_id: The lead_memory ID.

        Returns:
            Account plan dict, or None if lead not found.
        """
        # Verify lead ownership
        lead_result = (
            self._db.table("lead_memories")
            .select("*")
            .eq("id", lead_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if lead_result is None or lead_result.data is None:
            return None
        lead = cast(dict[str, Any], lead_result.data)

        # Check for existing plan
        plan_result = (
            self._db.table("account_plans")
            .select("*")
            .eq("user_id", user_id)
            .eq("lead_memory_id", lead_id)
            .maybe_single()
            .execute()
        )
        if plan_result is not None and plan_result.data is not None:
            return cast(dict[str, Any], plan_result.data)

        # Generate new plan with LLM
        return await self._generate_plan(user_id, lead_id, lead)

    async def _generate_plan(
        self, user_id: str, lead_id: str, lead: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate an account plan using LLM.

        Args:
            user_id: The user's ID.
            lead_id: The lead_memory ID.
            lead: Lead data dict.

        Returns:
            Newly created account plan dict.
        """
        # Gather stakeholders
        stakeholders_result = (
            self._db.table("lead_stakeholders")
            .select("contact_name, contact_email, title, role, influence_level, sentiment")
            .eq("lead_memory_id", lead_id)
            .execute()
        )
        stakeholders = cast(list[dict[str, Any]], stakeholders_result.data)

        # Gather recent events
        events_result = (
            self._db.table("lead_events")
            .select("event_type, subject, occurred_at")
            .eq("lead_memory_id", lead_id)
            .order("occurred_at", desc=True)
            .limit(20)
            .execute()
        )
        events = cast(list[dict[str, Any]], events_result.data)

        prompt = (
            "You are ARIA, an AI sales strategist for life sciences commercial teams.\n\n"
            f"Account: {lead.get('company_name')}\n"
            f"Stage: {lead.get('lifecycle_stage')}\n"
            f"Health Score: {lead.get('health_score')}/100\n"
            f"Expected Value: ${lead.get('expected_value', 0):,.0f}\n"
            f"Status: {lead.get('status')}\n\n"
            f"Stakeholders: {json.dumps(stakeholders, default=str)}\n\n"
            f"Recent Activity: {json.dumps(events, default=str)}\n\n"
            "Generate a strategic account plan. Respond with ONLY a JSON object:\n"
            "{\n"
            '  "strategy": "Multi-paragraph strategy document in markdown...",\n'
            '  "next_actions": [\n'
            '    {"action": "...", "priority": "high|medium|low", "due_in_days": N}\n'
            "  ],\n"
            '  "stakeholder_summary": {\n'
            '    "champion": "name or null",\n'
            '    "decision_maker": "name or null",\n'
            '    "key_risk": "description"\n'
            "  }\n"
            "}"
        )

        llm = LLMClient()
        try:
            raw = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.4,
            )
            plan_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Account plan generation failed: %s", exc)
            plan_data = {
                "strategy": (
                    f"## Account Plan: {lead.get('company_name')}\n\n"
                    "Strategy generation is temporarily unavailable. "
                    "Please edit this plan manually."
                ),
                "next_actions": [
                    {"action": "Review account history", "priority": "high", "due_in_days": 7}
                ],
                "stakeholder_summary": {
                    "champion": None,
                    "decision_maker": None,
                    "key_risk": "Plan auto-generation failed",
                },
            }

        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("account_plans")
            .insert(
                {
                    "user_id": user_id,
                    "lead_memory_id": lead_id,
                    "strategy": plan_data.get("strategy", ""),
                    "next_actions": plan_data.get("next_actions", []),
                    "stakeholder_summary": plan_data.get("stakeholder_summary", {}),
                    "generated_at": now,
                    "updated_at": now,
                }
            )
            .execute()
        )

        plan = cast(dict[str, Any], result.data[0])
        logger.info(
            "Account plan generated",
            extra={"user_id": user_id, "lead_id": lead_id, "plan_id": plan["id"]},
        )
        return plan

    async def update_plan(
        self, user_id: str, lead_id: str, strategy: str
    ) -> dict[str, Any] | None:
        """Update account plan strategy text.

        Args:
            user_id: The user's ID.
            lead_id: The lead_memory ID.
            strategy: Updated strategy text.

        Returns:
            Updated plan dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("account_plans")
            .update({"strategy": strategy, "updated_at": now})
            .eq("user_id", user_id)
            .eq("lead_memory_id", lead_id)
            .execute()
        )

        if result.data:
            logger.info(
                "Account plan updated",
                extra={"user_id": user_id, "lead_id": lead_id},
            )
            return cast(dict[str, Any], result.data[0])
        return None

    # ------------------------------------------------------------------ #
    # Forecasting                                                         #
    # ------------------------------------------------------------------ #

    async def get_forecast(self, user_id: str) -> dict[str, Any]:
        """Calculate pipeline forecast from lead memories.

        Groups leads by lifecycle_stage, sums expected_value,
        applies stage probability weights.

        Args:
            user_id: The user's ID.

        Returns:
            Forecast dict with stages, total_pipeline, weighted_pipeline.
        """
        result = (
            self._db.table("lead_memories")
            .select("lifecycle_stage, status, health_score, expected_value")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

        leads = cast(list[dict[str, Any]], result.data)

        stage_agg: dict[str, dict[str, float | int]] = {}
        for lead in leads:
            stage = lead.get("lifecycle_stage", "lead")
            val = float(lead.get("expected_value") or 0)
            health = int(lead.get("health_score", 50))
            weight = STAGE_WEIGHTS.get(stage, 0.10)

            if stage not in stage_agg:
                stage_agg[stage] = {"count": 0, "total_value": 0.0, "weighted_value": 0.0}

            stage_agg[stage]["count"] = int(stage_agg[stage]["count"]) + 1
            stage_agg[stage]["total_value"] = float(stage_agg[stage]["total_value"]) + val
            stage_agg[stage]["weighted_value"] = (
                float(stage_agg[stage]["weighted_value"]) + val * weight * (health / 100)
            )

        stages = [
            {
                "stage": s,
                "count": int(d["count"]),
                "total_value": float(d["total_value"]),
                "weighted_value": round(float(d["weighted_value"]), 2),
            }
            for s, d in stage_agg.items()
        ]

        total_pipeline = sum(s["total_value"] for s in stages)
        weighted_pipeline = sum(s["weighted_value"] for s in stages)

        logger.info(
            "Forecast calculated",
            extra={
                "user_id": user_id,
                "total_pipeline": total_pipeline,
                "weighted_pipeline": weighted_pipeline,
            },
        )
        return {
            "stages": stages,
            "total_pipeline": total_pipeline,
            "weighted_pipeline": round(weighted_pipeline, 2),
        }

    # ------------------------------------------------------------------ #
    # Quota                                                               #
    # ------------------------------------------------------------------ #

    async def get_quota(self, user_id: str, period: str | None = None) -> list[dict[str, Any]]:
        """Get quota records for user.

        Args:
            user_id: The user's ID.
            period: Optional period filter.

        Returns:
            List of quota dicts.
        """
        query = self._db.table("user_quotas").select("*").eq("user_id", user_id)
        if period:
            query = query.eq("period", period)
        result = query.order("period", desc=True).limit(10).execute()
        return cast(list[dict[str, Any]], result.data)

    async def set_quota(self, user_id: str, period: str, target_value: float) -> dict[str, Any]:
        """Create or update a quota.

        Args:
            user_id: The user's ID.
            period: Period key (e.g. '2026-Q1').
            target_value: Quota target.

        Returns:
            Upserted quota dict.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("user_quotas")
            .upsert(
                {
                    "user_id": user_id,
                    "period": period,
                    "target_value": target_value,
                    "updated_at": now,
                },
                on_conflict="user_id,period",
            )
            .execute()
        )

        quota = cast(dict[str, Any], result.data[0])
        logger.info(
            "Quota set",
            extra={"user_id": user_id, "period": period, "target": target_value},
        )
        return quota
```

**Step 2: Verify with ruff**

Run: `cd /Users/dhruv/aria && ruff check backend/src/services/account_planning_service.py && ruff format backend/src/services/account_planning_service.py`

**Step 3: Commit**

```bash
git add backend/src/services/account_planning_service.py
git commit -m "feat(US-941): add account planning service with territory, forecasting, quota"
```

---

## Task 4: Backend API Routes

**Files:**
- Create: `backend/src/api/routes/accounts.py`
- Modify: `backend/src/main.py` (add import + router registration)

**Step 1: Write the route file**

```python
"""Account planning API routes for US-941.

Endpoints:
- GET  /accounts              — List accounts (territory view)
- GET  /accounts/{id}/plan    — Get or generate account plan
- PUT  /accounts/{id}/plan    — Update account plan strategy
- GET  /accounts/territory    — Territory overview (alias with stats)
- GET  /accounts/forecast     — Pipeline forecast
- GET  /accounts/quota        — Get quota records
- POST /accounts/quota        — Set/update quota
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.models.account_planning import AccountPlanUpdate, QuotaSet
from src.services.account_planning_service import AccountPlanningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _get_service() -> AccountPlanningService:
    """Get account planning service instance."""
    return AccountPlanningService()


# --- Static routes MUST come before parametric routes ---


@router.get("/territory")
async def get_territory(
    current_user: CurrentUser,
    stage: str | None = Query(None, description="Filter by lifecycle stage"),
    sort_by: str = Query("last_activity_at", description="Sort column"),
    limit: int = Query(50, ge=1, le=200, description="Max accounts"),
) -> dict[str, Any]:
    """Get territory overview with account list and summary stats.

    Returns accounts plus aggregate stats for the territory dashboard header.
    """
    service = _get_service()
    accounts = await service.list_accounts(current_user.id, stage, sort_by, limit)

    total_value = sum(float(a.get("expected_value") or 0) for a in accounts)
    avg_health = (
        round(sum(a.get("health_score", 0) for a in accounts) / len(accounts))
        if accounts
        else 0
    )
    stage_counts: dict[str, int] = {}
    for a in accounts:
        s = a.get("lifecycle_stage", "lead")
        stage_counts[s] = stage_counts.get(s, 0) + 1

    logger.info(
        "Territory overview retrieved",
        extra={"user_id": current_user.id, "account_count": len(accounts)},
    )

    return {
        "accounts": accounts,
        "stats": {
            "total_accounts": len(accounts),
            "total_value": total_value,
            "avg_health": avg_health,
            "stage_counts": stage_counts,
        },
    }


@router.get("/forecast")
async def get_forecast(current_user: CurrentUser) -> dict[str, Any]:
    """Get pipeline forecast based on lead health scores and expected values."""
    service = _get_service()
    return await service.get_forecast(current_user.id)


@router.get("/quota")
async def get_quota(
    current_user: CurrentUser,
    period: str | None = Query(None, description="Filter by period"),
) -> list[dict[str, Any]]:
    """Get quota tracking records."""
    service = _get_service()
    return await service.get_quota(current_user.id, period)


@router.post("/quota")
async def set_quota(
    data: QuotaSet,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Set or update a quota target for a period."""
    service = _get_service()
    quota = await service.set_quota(current_user.id, data.period, data.target_value)
    logger.info(
        "Quota set via API",
        extra={"user_id": current_user.id, "period": data.period},
    )
    return quota


# --- Parametric routes ---


@router.get("")
async def list_accounts(
    current_user: CurrentUser,
    stage: str | None = Query(None, description="Filter by lifecycle stage"),
    sort_by: str = Query("last_activity_at", description="Sort column"),
    limit: int = Query(50, ge=1, le=200, description="Max accounts"),
) -> list[dict[str, Any]]:
    """List accounts from Lead Memory."""
    service = _get_service()
    return await service.list_accounts(current_user.id, stage, sort_by, limit)


@router.get("/{lead_id}/plan")
async def get_account_plan(
    lead_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get or auto-generate an account plan for a lead."""
    service = _get_service()
    plan = await service.get_or_generate_plan(current_user.id, lead_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return plan


@router.put("/{lead_id}/plan")
async def update_account_plan(
    lead_id: str,
    data: AccountPlanUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update account plan strategy text (user edits)."""
    service = _get_service()
    plan = await service.update_plan(current_user.id, lead_id, data.strategy)
    if plan is None:
        raise HTTPException(status_code=404, detail="Account plan not found")
    logger.info(
        "Account plan updated via API",
        extra={"user_id": current_user.id, "lead_id": lead_id},
    )
    return plan
```

**Step 2: Register router in main.py**

In `backend/src/main.py`:

1. Add to the imports block (alphabetical, after `account`):
```python
from src.api.routes import (
    account,
    accounts,  # US-941: Account Planning
    ...
)
```

2. Add router registration (alphabetical, after `account.router`):
```python
app.include_router(accounts.router, prefix="/api/v1")
```

**Step 3: Verify with ruff**

Run: `cd /Users/dhruv/aria && ruff check backend/src/api/routes/accounts.py && ruff format backend/src/api/routes/accounts.py`

**Step 4: Commit**

```bash
git add backend/src/api/routes/accounts.py backend/src/main.py
git commit -m "feat(US-941): add account planning API routes and register in main"
```

---

## Task 5: Backend Tests

**Files:**
- Create: `backend/tests/test_account_planning.py`

**Step 1: Write the tests**

```python
"""Tests for US-941 Account Planning & Strategic Workflows."""

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.account_planning import (
    AccountListItem,
    AccountPlanResponse,
    AccountPlanUpdate,
    ForecastResponse,
    ForecastStage,
    QuotaResponse,
    QuotaSet,
)
from src.services.account_planning_service import AccountPlanningService, STAGE_WEIGHTS


# ------------------------------------------------------------------ #
# Model tests                                                         #
# ------------------------------------------------------------------ #

class TestModels:
    """Test Pydantic model validation."""

    def test_quota_set_valid(self) -> None:
        q = QuotaSet(period="2026-Q1", target_value=500000)
        assert q.period == "2026-Q1"
        assert q.target_value == 500000

    def test_quota_set_rejects_negative(self) -> None:
        with pytest.raises(Exception):
            QuotaSet(period="2026-Q1", target_value=-100)

    def test_quota_set_rejects_empty_period(self) -> None:
        with pytest.raises(Exception):
            QuotaSet(period="", target_value=1000)

    def test_account_plan_update_valid(self) -> None:
        u = AccountPlanUpdate(strategy="## New Strategy\n\nDetails here.")
        assert u.strategy.startswith("## New Strategy")

    def test_account_plan_update_rejects_empty(self) -> None:
        with pytest.raises(Exception):
            AccountPlanUpdate(strategy="")

    def test_forecast_stage_model(self) -> None:
        fs = ForecastStage(stage="opportunity", count=5, total_value=100000, weighted_value=40000)
        assert fs.weighted_value == 40000

    def test_account_list_item_optional_fields(self) -> None:
        item = AccountListItem(
            id="abc",
            company_name="Acme",
            lifecycle_stage="lead",
            status="active",
            health_score=75,
            expected_value=None,
            last_activity_at=None,
            next_action=None,
        )
        assert item.expected_value is None


# ------------------------------------------------------------------ #
# Service tests                                                       #
# ------------------------------------------------------------------ #

def _mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


def _chain(mock: MagicMock, data: list[dict[str, Any]]) -> MagicMock:
    """Make a fluent mock chain return data on .execute()."""
    execute_result = MagicMock()
    execute_result.data = data
    mock.execute.return_value = execute_result
    # Support chained methods
    for method in (
        "select", "eq", "in_", "order", "limit", "insert", "update",
        "upsert", "maybe_single", "single",
    ):
        getattr(mock, method, lambda *a, **kw: mock).return_value = mock
    mock.execute.return_value = execute_result
    return mock


class TestListAccounts:
    """Test AccountPlanningService.list_accounts."""

    @pytest.mark.asyncio
    async def test_list_accounts_returns_data(self) -> None:
        db = _mock_db()
        leads_mock = MagicMock()
        plans_mock = MagicMock()

        lead_data = [
            {
                "id": "lead-1",
                "company_name": "Acme Bio",
                "lifecycle_stage": "opportunity",
                "status": "active",
                "health_score": 80,
                "expected_value": 50000,
                "last_activity_at": "2026-01-15T00:00:00Z",
                "tags": [],
            }
        ]
        plan_data = [
            {
                "lead_memory_id": "lead-1",
                "next_actions": [{"action": "Send proposal", "priority": "high"}],
            }
        ]

        _chain(leads_mock, lead_data)
        _chain(plans_mock, plan_data)

        # table() returns different mocks based on table name
        def table_dispatch(name: str) -> MagicMock:
            if name == "lead_memories":
                return leads_mock
            return plans_mock

        db.table = table_dispatch

        with patch("src.services.account_planning_service.SupabaseClient") as mock_sb:
            mock_sb.get_client.return_value = db
            service = AccountPlanningService()
            service._db = db

            result = await service.list_accounts("user-1")

        assert len(result) == 1
        assert result[0]["company_name"] == "Acme Bio"
        assert result[0]["next_action"] == "Send proposal"

    @pytest.mark.asyncio
    async def test_list_accounts_empty(self) -> None:
        db = _mock_db()
        leads_mock = MagicMock()
        _chain(leads_mock, [])

        db.table = lambda _: leads_mock

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.list_accounts("user-1")

        assert result == []


class TestForecast:
    """Test AccountPlanningService.get_forecast."""

    @pytest.mark.asyncio
    async def test_forecast_calculation(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        lead_data = [
            {"lifecycle_stage": "lead", "status": "active", "health_score": 100, "expected_value": 10000},
            {"lifecycle_stage": "opportunity", "status": "active", "health_score": 80, "expected_value": 50000},
            {"lifecycle_stage": "account", "status": "active", "health_score": 90, "expected_value": 100000},
        ]
        _chain(mock_table, lead_data)
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_forecast("user-1")

        assert result["total_pipeline"] == 160000
        # lead: 10000 * 0.10 * 1.0 = 1000
        # opp:  50000 * 0.40 * 0.8 = 16000
        # acct: 100000 * 0.80 * 0.9 = 72000
        assert result["weighted_pipeline"] == 89000.0
        assert len(result["stages"]) == 3

    @pytest.mark.asyncio
    async def test_forecast_empty_pipeline(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_forecast("user-1")

        assert result["total_pipeline"] == 0
        assert result["weighted_pipeline"] == 0
        assert result["stages"] == []


class TestQuota:
    """Test AccountPlanningService quota methods."""

    @pytest.mark.asyncio
    async def test_set_quota(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [
            {
                "id": "q-1",
                "user_id": "user-1",
                "period": "2026-Q1",
                "target_value": 500000,
                "actual_value": 0,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ])
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.set_quota("user-1", "2026-Q1", 500000)

        assert result["period"] == "2026-Q1"
        assert result["target_value"] == 500000

    @pytest.mark.asyncio
    async def test_get_quota(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [
            {"id": "q-1", "period": "2026-Q1", "target_value": 500000, "actual_value": 125000},
        ])
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_quota("user-1")

        assert len(result) == 1
        assert result[0]["actual_value"] == 125000


class TestAccountPlan:
    """Test AccountPlanningService plan generation."""

    @pytest.mark.asyncio
    async def test_get_existing_plan(self) -> None:
        db = _mock_db()
        lead_mock = MagicMock()
        plan_mock = MagicMock()

        lead_exec = MagicMock()
        lead_exec.data = {"id": "lead-1", "company_name": "Test"}
        lead_mock.select.return_value = lead_mock
        lead_mock.eq.return_value = lead_mock
        lead_mock.maybe_single.return_value = lead_mock
        lead_mock.execute.return_value = lead_exec

        plan_exec = MagicMock()
        plan_exec.data = {
            "id": "plan-1",
            "strategy": "Existing strategy",
            "next_actions": [],
            "stakeholder_summary": {},
        }
        plan_mock.select.return_value = plan_mock
        plan_mock.eq.return_value = plan_mock
        plan_mock.maybe_single.return_value = plan_mock
        plan_mock.execute.return_value = plan_exec

        call_count = {"n": 0}

        def table_dispatch(name: str) -> MagicMock:
            if name == "lead_memories":
                return lead_mock
            call_count["n"] += 1
            return plan_mock

        db.table = table_dispatch

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_or_generate_plan("user-1", "lead-1")

        assert result is not None
        assert result["strategy"] == "Existing strategy"

    @pytest.mark.asyncio
    async def test_update_plan(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [
            {"id": "plan-1", "strategy": "Updated", "updated_at": "2026-02-08T00:00:00Z"},
        ])
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.update_plan("user-1", "lead-1", "Updated")

        assert result is not None
        assert result["strategy"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_plan_not_found(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.update_plan("user-1", "lead-1", "New text")

        assert result is None
```

**Step 2: Run tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_account_planning.py -v`

Expected: All tests pass.

**Step 3: Lint**

Run: `cd /Users/dhruv/aria && ruff check backend/tests/test_account_planning.py && ruff format backend/tests/test_account_planning.py`

**Step 4: Commit**

```bash
git add backend/tests/test_account_planning.py
git commit -m "test(US-941): add account planning service and model tests"
```

---

## Task 6: Frontend API Client

**Files:**
- Create: `frontend/src/api/accounts.ts`

**Step 1: Write the API client**

```typescript
import { apiClient } from "./client";

// --- Types ---

export interface AccountListItem {
  id: string;
  company_name: string;
  lifecycle_stage: string;
  status: string;
  health_score: number;
  expected_value: number | null;
  last_activity_at: string | null;
  tags: string[];
  next_action: string | null;
}

export interface TerritoryStats {
  total_accounts: number;
  total_value: number;
  avg_health: number;
  stage_counts: Record<string, number>;
}

export interface TerritoryResponse {
  accounts: AccountListItem[];
  stats: TerritoryStats;
}

export interface AccountPlan {
  id: string;
  user_id: string;
  lead_memory_id: string;
  strategy: string;
  next_actions: Array<{
    action: string;
    priority: "high" | "medium" | "low";
    due_in_days?: number;
  }>;
  stakeholder_summary: {
    champion?: string | null;
    decision_maker?: string | null;
    key_risk?: string;
  };
  generated_at: string;
  updated_at: string;
}

export interface ForecastStage {
  stage: string;
  count: number;
  total_value: number;
  weighted_value: number;
}

export interface ForecastResponse {
  stages: ForecastStage[];
  total_pipeline: number;
  weighted_pipeline: number;
}

export interface Quota {
  id: string;
  user_id: string;
  period: string;
  target_value: number;
  actual_value: number;
  created_at: string;
  updated_at: string;
}

// --- API functions ---

export async function listAccounts(
  stage?: string,
  sortBy?: string,
  limit?: number
): Promise<AccountListItem[]> {
  const params = new URLSearchParams();
  if (stage) params.append("stage", stage);
  if (sortBy) params.append("sort_by", sortBy);
  if (limit) params.append("limit", limit.toString());
  const url = params.toString() ? `/accounts?${params}` : "/accounts";
  const response = await apiClient.get<AccountListItem[]>(url);
  return response.data;
}

export async function getTerritory(
  stage?: string,
  sortBy?: string,
  limit?: number
): Promise<TerritoryResponse> {
  const params = new URLSearchParams();
  if (stage) params.append("stage", stage);
  if (sortBy) params.append("sort_by", sortBy);
  if (limit) params.append("limit", limit.toString());
  const url = params.toString()
    ? `/accounts/territory?${params}`
    : "/accounts/territory";
  const response = await apiClient.get<TerritoryResponse>(url);
  return response.data;
}

export async function getAccountPlan(leadId: string): Promise<AccountPlan> {
  const response = await apiClient.get<AccountPlan>(
    `/accounts/${leadId}/plan`
  );
  return response.data;
}

export async function updateAccountPlan(
  leadId: string,
  strategy: string
): Promise<AccountPlan> {
  const response = await apiClient.put<AccountPlan>(
    `/accounts/${leadId}/plan`,
    { strategy }
  );
  return response.data;
}

export async function getForecast(): Promise<ForecastResponse> {
  const response = await apiClient.get<ForecastResponse>(
    "/accounts/forecast"
  );
  return response.data;
}

export async function getQuotas(period?: string): Promise<Quota[]> {
  const params = period ? `?period=${period}` : "";
  const response = await apiClient.get<Quota[]>(
    `/accounts/quota${params}`
  );
  return response.data;
}

export async function setQuota(
  period: string,
  targetValue: number
): Promise<Quota> {
  const response = await apiClient.post<Quota>("/accounts/quota", {
    period,
    target_value: targetValue,
  });
  return response.data;
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/accounts.ts
git commit -m "feat(US-941): add frontend API client for accounts"
```

---

## Task 7: Frontend React Query Hooks

**Files:**
- Create: `frontend/src/hooks/useAccounts.ts`

**Step 1: Write the hooks**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getTerritory,
  getAccountPlan,
  updateAccountPlan,
  getForecast,
  getQuotas,
  setQuota,
  type TerritoryResponse,
} from "@/api/accounts";

export const accountKeys = {
  all: ["accounts"] as const,
  territory: (stage?: string) =>
    [...accountKeys.all, "territory", { stage }] as const,
  plan: (leadId: string) => [...accountKeys.all, "plan", leadId] as const,
  forecast: () => [...accountKeys.all, "forecast"] as const,
  quotas: (period?: string) =>
    [...accountKeys.all, "quotas", { period }] as const,
};

export function useTerritory(stage?: string) {
  return useQuery({
    queryKey: accountKeys.territory(stage),
    queryFn: () => getTerritory(stage),
  });
}

export function useAccountPlan(leadId: string) {
  return useQuery({
    queryKey: accountKeys.plan(leadId),
    queryFn: () => getAccountPlan(leadId),
    enabled: !!leadId,
  });
}

export function useUpdateAccountPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, strategy }: { leadId: string; strategy: string }) =>
      updateAccountPlan(leadId, strategy),
    onSuccess: (data) => {
      queryClient.setQueryData(
        accountKeys.plan(data.lead_memory_id),
        data
      );
      queryClient.invalidateQueries({ queryKey: accountKeys.territory() });
    },
  });
}

export function useForecast() {
  return useQuery({
    queryKey: accountKeys.forecast(),
    queryFn: () => getForecast(),
  });
}

export function useQuotas(period?: string) {
  return useQuery({
    queryKey: accountKeys.quotas(period),
    queryFn: () => getQuotas(period),
  });
}

export function useSetQuota() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      period,
      targetValue,
    }: {
      period: string;
      targetValue: number;
    }) => setQuota(period, targetValue),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: accountKeys.quotas() });
    },
  });
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useAccounts.ts
git commit -m "feat(US-941): add React Query hooks for accounts"
```

---

## Task 8: Frontend AccountsPage

**Files:**
- Create: `frontend/src/pages/AccountsPage.tsx`
- Modify: `frontend/src/pages/index.ts` (add export)
- Modify: `frontend/src/App.tsx` (add route)

This is the main page. Uses the frontend-design skill for the dark surface layout.

**Step 1: Write the page component**

Create `frontend/src/pages/AccountsPage.tsx` with:

- Territory table (sortable, filterable by stage)
- Account detail slide-over panel (shows plan, stakeholder summary, next actions)
- Editable strategy text (textarea)
- Forecast bar chart (Recharts BarChart)
- Quota tracker (progress bar)
- Stat cards in header (total accounts, total pipeline, avg health, weighted forecast)

Use these Tailwind patterns (matching existing pages):
- `bg-slate-900` base
- `bg-slate-800/50 border border-slate-700 rounded-xl` cards
- `text-white` primary, `text-slate-400` secondary
- `DashboardLayout` wrapper

Recharts is already installed (confirmed from US-943 ROI dashboard).

The page is large (~600 lines). The subagent implementing this should use the `frontend-design` skill for design quality. Key sections:

1. **Header** with title "Accounts" and subtitle "Strategic account management"
2. **Stat cards row**: Total Accounts, Total Pipeline $, Avg Health, Weighted Forecast
3. **Stage filter tabs**: All | Lead | Opportunity | Account
4. **Territory table**: Company, Stage, Health (colored badge), Value, Last Activity, Next Action
5. **Click row → slide-over panel** with:
   - Account name header
   - Tab group: Plan | Stakeholders | Actions
   - Plan tab: editable textarea with save button
   - Stakeholders tab: list from plan.stakeholder_summary
   - Actions tab: list from plan.next_actions with priority badges
6. **Forecast section**: Recharts BarChart with stages on x-axis, values on y-axis, weighted overlay
7. **Quota section**: period dropdown, progress bar (actual/target), set quota form

**Step 2: Export from pages/index.ts**

Add line: `export { AccountsPage } from "./AccountsPage";`

**Step 3: Register route in App.tsx**

Add import `AccountsPage` in the destructured import from `@/pages`.

Add route (after `/goals` route):
```tsx
<Route
  path="/accounts"
  element={
    <ProtectedRoute>
      <AccountsPage />
    </ProtectedRoute>
  }
/>
```

**Step 4: Lint and typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit && npm run lint`

**Step 5: Commit**

```bash
git add frontend/src/pages/AccountsPage.tsx frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(US-941): add AccountsPage with territory, forecast, and quota tracking"
```

---

## Task 9: Quality Gates

**Step 1: Run backend tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_account_planning.py -v`

Expected: All pass.

**Step 2: Run backend lint**

Run: `cd /Users/dhruv/aria && ruff check backend/src/models/account_planning.py backend/src/services/account_planning_service.py backend/src/api/routes/accounts.py backend/tests/test_account_planning.py`

Run: `cd /Users/dhruv/aria && ruff format --check backend/src/models/account_planning.py backend/src/services/account_planning_service.py backend/src/api/routes/accounts.py backend/tests/test_account_planning.py`

**Step 3: Run frontend typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`

**Step 4: Run frontend lint**

Run: `cd /Users/dhruv/aria/frontend && npm run lint`

**Step 5: Fix any issues found, re-run, commit fixes**

---

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/supabase/migrations/20260208_account_planning.sql` | Create | DB tables with RLS |
| `backend/src/models/account_planning.py` | Create | Pydantic request/response models |
| `backend/src/services/account_planning_service.py` | Create | Business logic service |
| `backend/src/api/routes/accounts.py` | Create | FastAPI route handlers |
| `backend/src/main.py` | Modify | Register accounts router |
| `backend/tests/test_account_planning.py` | Create | Backend unit tests |
| `frontend/src/api/accounts.ts` | Create | API client functions |
| `frontend/src/hooks/useAccounts.ts` | Create | React Query hooks |
| `frontend/src/pages/AccountsPage.tsx` | Create | Main page component |
| `frontend/src/pages/index.ts` | Modify | Export AccountsPage |
| `frontend/src/App.tsx` | Modify | Add /accounts route |
