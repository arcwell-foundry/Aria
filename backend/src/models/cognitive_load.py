"""Pydantic models for cognitive load monitoring."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class LoadLevel(str, Enum):
    """Cognitive load level categories."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CognitiveLoadState(BaseModel):
    """Current cognitive load state with factors and recommendation."""

    level: LoadLevel
    score: float = Field(..., ge=0.0, le=1.0, description="Load score 0.0 to 1.0")
    factors: dict[str, float] = Field(default_factory=dict, description="Individual factor scores")
    recommendation: str = Field(
        ...,
        description="Response style recommendation: detailed, balanced, concise, concise_urgent",
    )


class CognitiveLoadSnapshotResponse(BaseModel):
    """Response model for cognitive load snapshot (matches DB schema)."""

    id: str
    user_id: str
    load_level: str
    load_score: float = Field(..., ge=0.0, le=1.0)
    factors: dict[str, float]
    session_id: str | None = None
    measured_at: datetime


class CognitiveLoadRequest(BaseModel):
    """Request model for cognitive load estimation."""

    session_id: str | None = Field(None, description="Optional session ID for tracking")


class CognitiveLoadHistoryResponse(BaseModel):
    """Response for cognitive load history."""

    snapshots: list[CognitiveLoadSnapshotResponse]
    average_score: float | None = None
    trend: str | None = Field(None, description="Trend direction: improving, stable, worsening")
