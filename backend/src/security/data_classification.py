"""Data classification system for ARIA skill security.

Every piece of data in ARIA has a classification that determines
what skills can access it. Skills are treated as untrusted code
until proven otherwise.
"""

import re
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
    """Automatically classifies data based on content and context.

    Runs on ALL data before it reaches any skill.
    Uses pattern matching to detect sensitive data types.
    """

    # Patterns that indicate sensitive data
    PATTERNS: dict[DataClass, list[str]] = {
        DataClass.REGULATED: [
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN format: 123-45-6789
            r"\b\d{9}\b",  # SSN without dashes: 123456789
            r"\b(?:\d{4}[-\s]?){3}\d{4}\b",  # Credit card: 1234-5678-9012-3456
            r"\b\d{16}\b",  # Credit card without separators
            r"\bDOB\s*[:\-]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",  # Date of birth
            r"\b(?:diagnosis|prognosis|medication|prescription)\b",  # PHI indicators
            r"\bpatient\s+(?:id|ID|number|#)\b",  # Patient identifiers
            r"\bmedical\s+record\b",  # Medical records
            r"\bHIPAA\b",  # Explicit HIPAA reference
            r"\b(?:blood\s+type|HIV|AIDS|cancer\s+diagnosis)\b",  # Health conditions
        ],
        DataClass.RESTRICTED: [
            r"\$\s*[\d,]+\.?\d*\s*(?:M|K|million|thousand|B|billion)?",  # Money amounts
            r"\brevenue\b",  # Revenue mentions
            r"\bprofit(?:s|ability)?\b",  # Profit mentions
            r"\bmargin\b",  # Margin mentions
            r"\bcontract\s+value\b",  # Contract values
            r"\bdeal\s+(?:size|value|amount)\b",  # Deal sizes
            r"\bcompetitor\s+pricing\b",  # Competitor pricing
            r"\bour\s+pricing\b",  # Our pricing
            r"\bconfidential\b",  # Explicit confidential marker
            r"\bproprietary\b",  # Proprietary marker
            r"\bNDA\b",  # NDA reference
            r"\btrade\s+secret\b",  # Trade secrets
        ],
        DataClass.CONFIDENTIAL: [
            r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",  # Email addresses
            r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # Phone numbers (US format)
            r"\b\+\d{1,3}[-.\s]?\d{1,14}\b",  # International phone
            r"\bcontact\s+(?:info|information|details)\b",  # Contact info context
            r"\bpersonal\s+(?:email|phone|address)\b",  # Personal contact
            r"\bextension\s*[:\-]?\s*\d+\b",  # Phone extensions
        ],
    }
