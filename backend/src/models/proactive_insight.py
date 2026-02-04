"""Models for proactive memory surfacing.

ProactiveInsight represents a memory that ARIA should volunteer
to the user based on current context. SurfacedInsightRecord
tracks what was surfaced and when for cooldown and analytics.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InsightType(str, Enum):
    """Types of proactive insights ARIA can surface."""

    PATTERN_MATCH = "pattern_match"
    CONNECTION = "connection"
    TEMPORAL = "temporal"
    GOAL_RELEVANT = "goal_relevant"


class ProactiveInsight(BaseModel):
    """A memory worth volunteering to the user."""

    insight_type: InsightType
    content: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    source_memory_id: str
    source_memory_type: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize insight to dictionary."""
        return {
            "insight_type": self.insight_type.value,
            "content": self.content,
            "relevance_score": self.relevance_score,
            "source_memory_id": self.source_memory_id,
            "source_memory_type": self.source_memory_type,
            "explanation": self.explanation,
        }


class SurfacedInsightRecord(BaseModel):
    """Database record for a surfaced insight."""

    id: str
    user_id: str
    memory_type: str
    memory_id: str
    insight_type: str
    context: str | None
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str | None
    surfaced_at: datetime
    engaged: bool
    engaged_at: datetime | None
    dismissed: bool
    dismissed_at: datetime | None
