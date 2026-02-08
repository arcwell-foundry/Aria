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

    period: str = Field(..., min_length=1, max_length=20, description="Period key, e.g. '2026-Q1'")
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
