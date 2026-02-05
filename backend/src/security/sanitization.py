"""Data sanitization pipeline for ARIA skill security.

Tokenizes, redacts, and validates data based on skill trust levels
before any data reaches external skills.
"""

from dataclasses import dataclass, field
from typing import Any


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
