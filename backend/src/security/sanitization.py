"""Data sanitization pipeline for ARIA skill security.

Tokenizes, redacts, and validates data based on skill trust levels
before any data reaches external skills.
"""

from dataclasses import dataclass, field
from typing import Any

from src.security.data_classification import ClassifiedData, DataClass, DataClassifier
from src.security.trust_levels import SkillTrustLevel, can_access_data


@dataclass
class TokenMap:
    """Maps token strings to their original values.

    Tokens use format [DATA_TYPE_NNN] e.g. [FINANCIAL_001], [CONTACT_002].
    Maintains bidirectional mapping for tokenization and detokenization.

    Attributes:
        tokens: Dict mapping token strings to original values.
    """

    tokens: dict[str, Any] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def add_token(self, data_type: str, value: Any) -> str:
        """Add a value to the token map and return its token string.

        Args:
            data_type: Category of data (e.g., "financial", "contact").
            value: The original value to tokenize.

        Returns:
            Token string in format [DATA_TYPE_NNN].
        """
        normalized_type = data_type.upper()
        self._counters[normalized_type] = self._counters.get(normalized_type, 0) + 1
        counter = self._counters[normalized_type]
        token = f"[{normalized_type}_{counter:03d}]"
        self.tokens[token] = value
        return token

    def get_original(self, token: str) -> Any | None:
        """Get the original value for a token.

        Args:
            token: The token string to look up.

        Returns:
            The original value, or None if token not found.
        """
        return self.tokens.get(token)


@dataclass
class LeakageReport:
    """Report of potential data leakage in skill output.

    Attributes:
        leaked: Whether any sensitive data was found in output.
        leaked_values: List of leaked values that were detected.
        severity: Severity level - "none", "low", "medium", "high", "critical".
    """

    leaked: bool
    leaked_values: list[Any]
    severity: str


class DataSanitizer:
    """Sanitizes data for skill execution based on trust levels."""

    def __init__(self, classifier: DataClassifier) -> None:
        """Initialize DataSanitizer with a classifier."""
        self.classifier = classifier
