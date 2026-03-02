"""Thesys C1 content routing classifier.

Determines whether ARIA's response content should be routed through C1
for rich UI rendering, and identifies the content type for prompt
specialization.
"""

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Minimum character length before C1 routing is considered.
# Short conversational replies don't benefit from generative UI.
MIN_LENGTH_FOR_C1 = 200

# Pattern groups for structured content detection
_PIPELINE_PATTERNS: list[str] = [
    r"\bpipeline\b",
    r"\brevenue\b",
    r"\bforecast\b",
    r"\bconversion\s+rate\b",
    r"\bdeal\b",
    r"\bstage\b",
    r"\bclose\s+rate\b",
    r"\bquota\b",
]

_BRIEFING_PATTERNS: list[str] = [
    r"\*\*Summary\*\*",
    r"\*\*Overview\*\*",
    r"\bbriefing\b",
    r"\baction\s+items?\b",
    r"\bmorning\s+brief\b",
    r"\bagenda\b",
    r"\bhighlights?\b",
]

_EMAIL_PATTERNS: list[str] = [
    r"\bSubject:\s",
    r"\bDear\s+(Dr\.|Mr\.|Ms\.|Mrs\.)",
    r"\bdraft\b",
    r"\bapprove\b",
    r"\bemail\b",
    r"\breply\b",
    r"\bsend\b",
]

_LEAD_PATTERNS: list[str] = [
    r"\bcontacts?\b",
    r"\baccounts?\b",
    r"\blead\b",
    r"\bstakeholder\b",
    r"\brelationship\b",
    r"\brecommend\b",
]

# All patterns combined for the generic "is structured?" check
STRUCTURED_PATTERNS: list[str] = (
    _PIPELINE_PATTERNS + _BRIEFING_PATTERNS + _EMAIL_PATTERNS + _LEAD_PATTERNS
)

# Minimum pattern matches needed for generic structured detection
_MIN_PATTERN_MATCHES = 2


def _count_matches(content: str, patterns: list[str]) -> int:
    """Count how many patterns match in the content (case-insensitive)."""
    return sum(1 for p in patterns if re.search(p, content, re.IGNORECASE))


class ThesysRoutingClassifier:
    """Decides whether content should be routed through Thesys C1."""

    @classmethod
    def should_visualize(
        cls,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Check if content should be sent through C1 for rich rendering.

        Args:
            content: The text response from Claude.
            metadata: Optional metadata dict; if ``rich_content`` key is True,
                bypasses pattern matching.

        Returns:
            True if the content is eligible for C1 visualization.
        """
        should, _ = cls.classify(content, metadata)
        return should

    @classmethod
    def classify(
        cls,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        """Classify content for C1 routing and identify content type.

        Returns:
            A tuple of ``(should_visualize, content_type)`` where
            ``content_type`` is one of ``pipeline_data``, ``briefing``,
            ``email_draft``, ``lead_card``, or ``None``.
        """
        # Feature flag check
        if not os.environ.get("THESYS_ENABLED", "false").lower() in ("true", "1", "yes"):
            return False, None

        # Length gate — short replies are always markdown
        if len(content) < MIN_LENGTH_FOR_C1:
            return False, None

        # Metadata override — explicit rich_content flag from agent layer
        if metadata and metadata.get("rich_content"):
            content_type = cls._detect_content_type(content)
            return True, content_type

        # Pattern-based detection
        content_type = cls._detect_content_type(content)
        if content_type is not None:
            return True, content_type

        # Generic structured check — need 2+ pattern matches across all groups
        total_matches = _count_matches(content, STRUCTURED_PATTERNS)
        if total_matches >= _MIN_PATTERN_MATCHES:
            return True, None

        return False, None

    @classmethod
    def _detect_content_type(cls, content: str) -> str | None:
        """Detect the specific content type from pattern groups.

        Returns the most specific match, or None if no group has enough
        signal.
        """
        scores: dict[str, int] = {
            "pipeline_data": _count_matches(content, _PIPELINE_PATTERNS),
            "briefing": _count_matches(content, _BRIEFING_PATTERNS),
            "email_draft": _count_matches(content, _EMAIL_PATTERNS),
            "lead_card": _count_matches(content, _LEAD_PATTERNS),
        }

        # Require at least 2 matches within a group to classify
        best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best_type] >= 2:
            return best_type

        return None
