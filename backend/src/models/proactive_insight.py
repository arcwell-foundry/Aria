"""Models for proactive memory surfacing.

ProactiveInsight represents a memory that ARIA should volunteer
to the user based on current context. SurfacedInsightRecord
tracks what was surfaced and when for cooldown and analytics.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class InsightType(Enum):
    """Types of proactive insights ARIA can surface."""

    PATTERN_MATCH = "pattern_match"  # Similar topics discussed before
    CONNECTION = "connection"  # Entity connections via knowledge graph
    TEMPORAL = "temporal"  # Time-based triggers (deadlines, anniversaries)
    GOAL_RELEVANT = "goal_relevant"  # Relates to active goals


@dataclass
class ProactiveInsight:
    """A memory worth volunteering to the user.

    Represents a piece of context from memory that is relevant
    to the current conversation and should be surfaced proactively.

    Attributes:
        insight_type: Category of why this is relevant
        content: The actual insight content to share
        relevance_score: How relevant this is (0.0 to 1.0)
        source_memory_id: ID of the underlying memory
        source_memory_type: Type of memory (semantic, episodic, etc.)
        explanation: Why this insight is relevant
    """

    insight_type: InsightType
    content: str
    relevance_score: float
    source_memory_id: str
    source_memory_type: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize insight to dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "insight_type": self.insight_type.value,
            "content": self.content,
            "relevance_score": self.relevance_score,
            "source_memory_id": self.source_memory_id,
            "source_memory_type": self.source_memory_type,
            "explanation": self.explanation,
        }


@dataclass
class SurfacedInsightRecord:
    """Database record for a surfaced insight.

    Tracks when insights were shown to users for cooldown
    logic and engagement analytics.

    Attributes:
        id: Record UUID
        user_id: User who received the insight
        memory_type: Type of source memory
        memory_id: ID of source memory
        insight_type: Category of insight
        context: What triggered surfacing
        relevance_score: Relevance at time of surfacing
        explanation: Why it was surfaced
        surfaced_at: When it was shown
        engaged: Whether user engaged with it
        engaged_at: When user engaged
        dismissed: Whether user dismissed it
        dismissed_at: When user dismissed
    """

    id: str
    user_id: str
    memory_type: str
    memory_id: str
    insight_type: str
    context: str | None
    relevance_score: float
    explanation: str | None
    surfaced_at: datetime
    engaged: bool
    engaged_at: datetime | None
    dismissed: bool
    dismissed_at: datetime | None
