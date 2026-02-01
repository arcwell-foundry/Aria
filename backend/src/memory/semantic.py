"""Semantic memory module for storing facts and knowledge.

Semantic memory stores factual knowledge with:
- Subject-predicate-object triple structure
- Confidence scores (0.0-1.0) based on source reliability
- Temporal validity windows (valid_from, valid_to)
- Source tracking for provenance
- Soft invalidation for history preservation
- Contradiction detection

Facts are stored in Graphiti (Neo4j) for semantic search and
temporal querying capabilities.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.exceptions import FactNotFoundError, SemanticMemoryError

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


class FactSource(Enum):
    """Source of a semantic fact, used for confidence scoring."""

    USER_STATED = "user_stated"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    CRM_IMPORT = "crm_import"
    WEB_RESEARCH = "web_research"


# Base confidence by source type
SOURCE_CONFIDENCE: dict[FactSource, float] = {
    FactSource.USER_STATED: 0.95,
    FactSource.CRM_IMPORT: 0.90,
    FactSource.EXTRACTED: 0.75,
    FactSource.WEB_RESEARCH: 0.70,
    FactSource.INFERRED: 0.60,
}


@dataclass
class SemanticFact:
    """A semantic fact representing knowledge about an entity.

    Uses subject-predicate-object triple structure (e.g., "John works_at Acme").
    Tracks confidence, source, and temporal validity.
    """

    id: str
    user_id: str
    subject: str  # Entity the fact is about
    predicate: str  # Relationship type
    object: str  # Value or related entity
    confidence: float  # 0.0 to 1.0
    source: FactSource
    valid_from: datetime
    valid_to: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize fact to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source": self.source.value,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "invalidated_at": self.invalidated_at.isoformat() if self.invalidated_at else None,
            "invalidation_reason": self.invalidation_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticFact":
        """Create a SemanticFact instance from a dictionary.

        Args:
            data: Dictionary containing fact data.

        Returns:
            SemanticFact instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            confidence=data["confidence"],
            source=FactSource(data["source"]),
            valid_from=datetime.fromisoformat(data["valid_from"]),
            valid_to=datetime.fromisoformat(data["valid_to"]) if data.get("valid_to") else None,
            invalidated_at=datetime.fromisoformat(data["invalidated_at"]) if data.get("invalidated_at") else None,
            invalidation_reason=data.get("invalidation_reason"),
        )

    def is_valid(self, as_of: datetime | None = None) -> bool:
        """Check if this fact is valid at a given point in time.

        Args:
            as_of: The point in time to check validity. Defaults to now.

        Returns:
            True if the fact is valid at the specified time.
        """
        check_time = as_of or datetime.now(UTC)

        # Invalidated facts are never valid
        if self.invalidated_at is not None:
            return False

        # Check if we're within the validity window
        if check_time < self.valid_from:
            return False

        if self.valid_to is not None and check_time > self.valid_to:
            return False

        return True

    def contradicts(self, other: "SemanticFact") -> bool:
        """Check if this fact contradicts another fact.

        Two facts contradict if they have the same subject and predicate
        but different objects. This is used for contradiction detection
        when adding new facts.

        Args:
            other: Another fact to compare against.

        Returns:
            True if the facts contradict each other.
        """
        return (
            self.subject.lower() == other.subject.lower()
            and self.predicate.lower() == other.predicate.lower()
            and self.object.lower() != other.object.lower()
        )
