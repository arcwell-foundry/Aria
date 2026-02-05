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
