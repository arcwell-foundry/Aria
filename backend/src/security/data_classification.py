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

    async def classify(self, data: Any, context: dict[str, Any]) -> ClassifiedData:
        """Classify data based on content patterns and context.

        Scans data for sensitive patterns and returns appropriate classification.
        Checks from most sensitive (REGULATED) to least sensitive (CONFIDENTIAL).
        Defaults to INTERNAL if no sensitive patterns found.

        Args:
            data: The data to classify (any type, will be converted to string for scanning).
            context: Context about the data source and type.
                - source: Where this data came from (e.g., "crm", "user_input").

        Returns:
            ClassifiedData with appropriate classification and metadata.
        """
        # Convert data to string for pattern matching
        text = str(data) if data is not None else ""

        # Check patterns from most to least sensitive
        for classification in [
            DataClass.REGULATED,
            DataClass.RESTRICTED,
            DataClass.CONFIDENTIAL,
        ]:
            patterns = self.PATTERNS.get(classification, [])
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return ClassifiedData(
                        data=data,
                        classification=classification,
                        data_type=self._infer_data_type(text, pattern),
                        source=context.get("source", "unknown"),
                    )

        # Default to INTERNAL if no sensitive patterns found
        return ClassifiedData(
            data=data,
            classification=DataClass.INTERNAL,
            data_type="general",
            source=context.get("source", "unknown"),
        )

    def _infer_data_type(self, text: str, matched_pattern: str) -> str:
        """Infer the data type based on which pattern matched.

        Args:
            text: The text that was classified.
            matched_pattern: The regex pattern that matched.

        Returns:
            A string describing the data type.
        """
        # SSN patterns
        if "\\d{3}-\\d{2}-\\d{4}" in matched_pattern or matched_pattern == r"\b\d{9}\b":
            return "ssn"

        # Credit card patterns
        if "\\d{4}" in matched_pattern and ("\\d{16}" in matched_pattern or "{3}" in matched_pattern):
            return "credit_card"

        # DOB pattern
        if "DOB" in matched_pattern.upper():
            return "date_of_birth"

        # PHI patterns
        if any(
            kw in matched_pattern.lower()
            for kw in ["diagnosis", "prognosis", "medication", "patient", "medical"]
        ):
            return "health"

        # Financial patterns
        if any(
            kw in matched_pattern.lower()
            for kw in ["revenue", "profit", "margin", "deal", "contract"]
        ):
            return "financial"

        if "\\$" in matched_pattern:
            return "financial"

        if any(kw in matched_pattern.lower() for kw in ["confidential", "proprietary", "nda"]):
            return "competitive"

        # Contact patterns
        if "@" in matched_pattern:
            return "contact"
        if "\\d{3}" in matched_pattern and "\\d{4}" in matched_pattern:
            return "contact"

        return "sensitive"
