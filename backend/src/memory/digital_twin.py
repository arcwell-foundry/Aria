"""Digital twin module for user writing style analysis.

The Digital Twin captures a user's writing style fingerprint to enable
ARIA to communicate in their voice. This includes:
- Sentence structure and length patterns
- Vocabulary level and formality
- Common phrases and expressions
- Greeting and sign-off styles
- Punctuation and emoji usage patterns

Fingerprints are stored in Graphiti for semantic querying and
temporal tracking of style evolution.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WritingStyleFingerprint:
    """A writing style fingerprint representing a user's communication patterns.

    Captures linguistic features extracted from the user's emails, messages,
    and documents to enable style-matched content generation.
    """

    id: str
    user_id: str
    average_sentence_length: float
    vocabulary_level: str  # simple, moderate, advanced
    formality_score: float  # 0.0 (informal) to 1.0 (formal)
    common_phrases: list[str]
    greeting_style: str  # e.g., "Hi", "Dear", "Hey"
    sign_off_style: str  # e.g., "Best", "Thanks", "Regards"
    emoji_usage: bool
    punctuation_patterns: dict[str, float]  # char -> frequency ratio
    samples_analyzed: int
    confidence: float  # 0.0 to 1.0 based on sample size
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize fingerprint to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "average_sentence_length": self.average_sentence_length,
            "vocabulary_level": self.vocabulary_level,
            "formality_score": self.formality_score,
            "common_phrases": self.common_phrases,
            "greeting_style": self.greeting_style,
            "sign_off_style": self.sign_off_style,
            "emoji_usage": self.emoji_usage,
            "punctuation_patterns": self.punctuation_patterns,
            "samples_analyzed": self.samples_analyzed,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WritingStyleFingerprint":
        """Create a WritingStyleFingerprint instance from a dictionary.

        Args:
            data: Dictionary containing fingerprint data.

        Returns:
            WritingStyleFingerprint instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            average_sentence_length=data["average_sentence_length"],
            vocabulary_level=data["vocabulary_level"],
            formality_score=data["formality_score"],
            common_phrases=data["common_phrases"],
            greeting_style=data["greeting_style"],
            sign_off_style=data["sign_off_style"],
            emoji_usage=data["emoji_usage"],
            punctuation_patterns=data["punctuation_patterns"],
            samples_analyzed=data["samples_analyzed"],
            confidence=data["confidence"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
