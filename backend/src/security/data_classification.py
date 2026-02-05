"""Data classification system for ARIA skill security.

Every piece of data in ARIA has a classification that determines
what skills can access it. Skills are treated as untrusted code
until proven otherwise.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class DataClass(Enum):
    """Data classification levels - determines what skills can access.

    Ordered from least sensitive (PUBLIC) to most sensitive (REGULATED).
    """

    PUBLIC = "public"  # Can be shared freely (company names, public info)
    INTERNAL = "internal"  # Company internal (goals, strategies, notes)
    CONFIDENTIAL = "confidential"  # Need-to-know (deal details, contacts)
    RESTRICTED = "restricted"  # Financial, competitive (revenue, pricing, contracts)
    REGULATED = "regulated"  # PHI, PII - legal requirements (HIPAA, GDPR)


@dataclass
class ClassifiedData:
    """Data with its classification and handling rules.

    Attributes:
        data: The actual data content (any type).
        classification: The sensitivity level of this data.
        data_type: Category of data (financial, contact, health, competitive, etc.).
        source: Where this data came from (crm, user_input, memory, etc.).
        can_be_tokenized: Whether we can replace with placeholder tokens.
        retention_days: Auto-delete after N days (None means permanent).
    """

    data: Any
    classification: DataClass
    data_type: str
    source: str
    can_be_tokenized: bool = True
    retention_days: Optional[int] = None


class DataClassifier:
    """Placeholder for data classifier - to be implemented."""

    pass
