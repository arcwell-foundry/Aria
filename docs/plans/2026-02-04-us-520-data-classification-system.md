# US-520: Data Classification System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a data classification system that automatically classifies data by sensitivity level to protect customer data before any skill can access it.

**Architecture:** Pattern-based classification with regex detection for sensitive data types (SSN, credit cards, PHI, etc.). Data flows through classification before reaching any skill. Enum-based classification levels (PUBLIC → REGULATED) with context-aware fallback classification.

**Tech Stack:** Python 3.11+, Pydantic dataclasses, regex patterns, pytest for testing

---

## Task 1: Create Security Directory and Module Structure

**Files:**
- Create: `backend/src/security/__init__.py`
- Create: `backend/src/security/data_classification.py`

**Step 1: Create security directory and __init__.py**

```bash
mkdir -p /Users/dhruv/aria/backend/src/security
```

**Step 2: Create the module __init__.py**

Create file `backend/src/security/__init__.py`:

```python
"""Security module for ARIA.

Provides data classification, sanitization, sandboxing, and audit
capabilities for the skills integration system.
"""

from src.security.data_classification import (
    ClassifiedData,
    DataClass,
    DataClassifier,
)

__all__ = [
    "ClassifiedData",
    "DataClass",
    "DataClassifier",
]
```

**Step 3: Commit**

```bash
git add backend/src/security/__init__.py
git commit -m "feat(security): create security module structure

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create DataClass Enum

**Files:**
- Create: `backend/src/security/data_classification.py`
- Test: `backend/tests/test_data_classification.py`

**Step 1: Write the failing test for DataClass enum**

Create file `backend/tests/test_data_classification.py`:

```python
"""Tests for data classification system."""

import pytest


def test_data_class_enum_has_five_levels() -> None:
    """Test DataClass enum has PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, REGULATED."""
    from src.security.data_classification import DataClass

    assert DataClass.PUBLIC.value == "public"
    assert DataClass.INTERNAL.value == "internal"
    assert DataClass.CONFIDENTIAL.value == "confidential"
    assert DataClass.RESTRICTED.value == "restricted"
    assert DataClass.REGULATED.value == "regulated"
    assert len(DataClass) == 5


def test_data_class_enum_ordering_by_sensitivity() -> None:
    """Test DataClass values are ordered from least to most sensitive."""
    from src.security.data_classification import DataClass

    # Verify ordering: PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED < REGULATED
    sensitivity_order = [
        DataClass.PUBLIC,
        DataClass.INTERNAL,
        DataClass.CONFIDENTIAL,
        DataClass.RESTRICTED,
        DataClass.REGULATED,
    ]

    # Enums can be compared by their definition order
    for i in range(len(sensitivity_order) - 1):
        # Using list index as proxy for sensitivity level
        assert sensitivity_order.index(sensitivity_order[i]) < sensitivity_order.index(
            sensitivity_order[i + 1]
        )
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation for DataClass enum**

Create file `backend/src/security/data_classification.py`:

```python
"""Data classification system for ARIA skill security.

Every piece of data in ARIA has a classification that determines
what skills can access it. Skills are treated as untrusted code
until proven otherwise.
"""

from enum import Enum


class DataClass(Enum):
    """Data classification levels - determines what skills can access.

    Ordered from least sensitive (PUBLIC) to most sensitive (REGULATED).
    """

    PUBLIC = "public"  # Can be shared freely (company names, public info)
    INTERNAL = "internal"  # Company internal (goals, strategies, notes)
    CONFIDENTIAL = "confidential"  # Need-to-know (deal details, contacts)
    RESTRICTED = "restricted"  # Financial, competitive (revenue, pricing, contracts)
    REGULATED = "regulated"  # PHI, PII - legal requirements (HIPAA, GDPR)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/data_classification.py backend/tests/test_data_classification.py
git commit -m "feat(security): add DataClass enum with five sensitivity levels

Implements US-520: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, REGULATED

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create ClassifiedData Dataclass

**Files:**
- Modify: `backend/src/security/data_classification.py`
- Modify: `backend/tests/test_data_classification.py`

**Step 1: Write the failing tests for ClassifiedData**

Add to `backend/tests/test_data_classification.py`:

```python
def test_classified_data_initializes_with_required_fields() -> None:
    """Test ClassifiedData initializes with required fields."""
    from src.security.data_classification import ClassifiedData, DataClass

    classified = ClassifiedData(
        data="test data",
        classification=DataClass.PUBLIC,
        data_type="general",
        source="test",
    )

    assert classified.data == "test data"
    assert classified.classification == DataClass.PUBLIC
    assert classified.data_type == "general"
    assert classified.source == "test"
    assert classified.can_be_tokenized is True  # Default
    assert classified.retention_days is None  # Default


def test_classified_data_initializes_with_all_fields() -> None:
    """Test ClassifiedData initializes with all optional fields."""
    from src.security.data_classification import ClassifiedData, DataClass

    classified = ClassifiedData(
        data={"revenue": 1000000},
        classification=DataClass.RESTRICTED,
        data_type="financial",
        source="crm",
        can_be_tokenized=False,
        retention_days=90,
    )

    assert classified.data == {"revenue": 1000000}
    assert classified.classification == DataClass.RESTRICTED
    assert classified.data_type == "financial"
    assert classified.source == "crm"
    assert classified.can_be_tokenized is False
    assert classified.retention_days == 90


def test_classified_data_accepts_any_data_type() -> None:
    """Test ClassifiedData.data can be any type."""
    from src.security.data_classification import ClassifiedData, DataClass

    # String
    string_data = ClassifiedData(
        data="hello",
        classification=DataClass.PUBLIC,
        data_type="text",
        source="test",
    )
    assert string_data.data == "hello"

    # Dict
    dict_data = ClassifiedData(
        data={"key": "value"},
        classification=DataClass.INTERNAL,
        data_type="object",
        source="test",
    )
    assert dict_data.data == {"key": "value"}

    # List
    list_data = ClassifiedData(
        data=[1, 2, 3],
        classification=DataClass.CONFIDENTIAL,
        data_type="array",
        source="test",
    )
    assert list_data.data == [1, 2, 3]

    # None
    none_data = ClassifiedData(
        data=None,
        classification=DataClass.PUBLIC,
        data_type="empty",
        source="test",
    )
    assert none_data.data is None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py::test_classified_data_initializes_with_required_fields -v`
Expected: FAIL with "ImportError" for ClassifiedData

**Step 3: Write minimal implementation for ClassifiedData**

Add to `backend/src/security/data_classification.py` after DataClass:

```python
from dataclasses import dataclass
from typing import Any, Optional


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
```

Update imports at top of file:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/data_classification.py backend/tests/test_data_classification.py
git commit -m "feat(security): add ClassifiedData dataclass

Wraps data with classification, data_type, source, and handling rules

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create DataClassifier with PATTERNS Dict

**Files:**
- Modify: `backend/src/security/data_classification.py`
- Modify: `backend/tests/test_data_classification.py`

**Step 1: Write failing tests for DataClassifier.PATTERNS**

Add to `backend/tests/test_data_classification.py`:

```python
def test_data_classifier_has_patterns_dict() -> None:
    """Test DataClassifier has PATTERNS dict with regex patterns."""
    from src.security.data_classification import DataClass, DataClassifier

    classifier = DataClassifier()

    assert hasattr(classifier, "PATTERNS")
    assert isinstance(classifier.PATTERNS, dict)

    # Should have patterns for REGULATED, RESTRICTED, CONFIDENTIAL
    assert DataClass.REGULATED in classifier.PATTERNS
    assert DataClass.RESTRICTED in classifier.PATTERNS
    assert DataClass.CONFIDENTIAL in classifier.PATTERNS

    # Each entry should be a list of patterns
    assert isinstance(classifier.PATTERNS[DataClass.REGULATED], list)
    assert len(classifier.PATTERNS[DataClass.REGULATED]) > 0


def test_data_classifier_patterns_are_valid_regex() -> None:
    """Test all patterns in PATTERNS are valid regex."""
    import re

    from src.security.data_classification import DataClassifier

    classifier = DataClassifier()

    for data_class, patterns in classifier.PATTERNS.items():
        for pattern in patterns:
            # Should not raise
            try:
                re.compile(pattern)
            except re.error as e:
                pytest.fail(f"Invalid regex pattern '{pattern}' for {data_class}: {e}")
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py::test_data_classifier_has_patterns_dict -v`
Expected: FAIL with "ImportError" for DataClassifier

**Step 3: Write minimal implementation for DataClassifier with PATTERNS**

Add to `backend/src/security/data_classification.py`:

```python
import re


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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/data_classification.py backend/tests/test_data_classification.py
git commit -m "feat(security): add DataClassifier with PATTERNS dict

Regex patterns for SSN, credit cards, DOB, PHI, revenue, pricing, emails, phones

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Implement Pattern Detection Tests

**Files:**
- Modify: `backend/tests/test_data_classification.py`

**Step 1: Write pattern detection tests**

Add to `backend/tests/test_data_classification.py`:

```python
class TestSSNPatternDetection:
    """Tests for SSN pattern detection."""

    def test_detects_ssn_with_dashes(self) -> None:
        """Test detection of SSN in format XXX-XX-XXXX."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "Customer SSN is 123-45-6789"
        assert any(re.search(p, text) for p in patterns)

    def test_detects_ssn_without_dashes(self) -> None:
        """Test detection of SSN without dashes (9 digits)."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "SSN: 123456789"
        assert any(re.search(p, text) for p in patterns)

    def test_does_not_false_positive_on_regular_numbers(self) -> None:
        """Test that regular numbers don't trigger SSN detection."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        # Only check SSN-specific patterns
        ssn_patterns = [
            r"\b\d{3}-\d{2}-\d{4}\b",
            r"\b\d{9}\b",
        ]

        text = "The year is 2024 and we have 150 customers"
        assert not any(re.search(p, text) for p in ssn_patterns)


class TestCreditCardPatternDetection:
    """Tests for credit card pattern detection."""

    def test_detects_credit_card_with_dashes(self) -> None:
        """Test detection of credit card with dashes."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "Card: 1234-5678-9012-3456"
        assert any(re.search(p, text) for p in patterns)

    def test_detects_credit_card_with_spaces(self) -> None:
        """Test detection of credit card with spaces."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "Card: 1234 5678 9012 3456"
        assert any(re.search(p, text) for p in patterns)

    def test_detects_credit_card_without_separators(self) -> None:
        """Test detection of credit card without separators."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "Card number: 1234567890123456"
        assert any(re.search(p, text) for p in patterns)


class TestDOBPatternDetection:
    """Tests for date of birth pattern detection."""

    def test_detects_dob_with_slashes(self) -> None:
        """Test detection of DOB with slashes."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "DOB: 01/15/1990"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_dob_with_dashes(self) -> None:
        """Test detection of DOB with dashes."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "DOB-12-25-1985"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)


class TestPHIPatternDetection:
    """Tests for Protected Health Information pattern detection."""

    def test_detects_diagnosis(self) -> None:
        """Test detection of diagnosis keyword."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "Patient diagnosis indicates stage 2"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_medication(self) -> None:
        """Test detection of medication keyword."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "Current medication includes lisinopril"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_patient_id(self) -> None:
        """Test detection of patient ID reference."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "Patient ID: 12345"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_medical_record(self) -> None:
        """Test detection of medical record reference."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.REGULATED]

        text = "See medical record for history"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)


class TestFinancialPatternDetection:
    """Tests for financial/RESTRICTED pattern detection."""

    def test_detects_dollar_amount(self) -> None:
        """Test detection of dollar amounts."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.RESTRICTED]

        text = "Deal worth $4.2M"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_revenue_mention(self) -> None:
        """Test detection of revenue keyword."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.RESTRICTED]

        text = "Q4 revenue targets"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_profit_mention(self) -> None:
        """Test detection of profit keyword."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.RESTRICTED]

        text = "Projected profits for next quarter"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_deal_size(self) -> None:
        """Test detection of deal size reference."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.RESTRICTED]

        text = "The deal size is estimated at"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_confidential_marker(self) -> None:
        """Test detection of explicit confidential marker."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.RESTRICTED]

        text = "CONFIDENTIAL: Internal projections"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)


class TestContactPatternDetection:
    """Tests for contact information (CONFIDENTIAL) pattern detection."""

    def test_detects_email_address(self) -> None:
        """Test detection of email addresses."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.CONFIDENTIAL]

        text = "Contact: john.doe@company.com"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_phone_number_with_dashes(self) -> None:
        """Test detection of phone numbers with dashes."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.CONFIDENTIAL]

        text = "Call me at 555-123-4567"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_phone_number_with_dots(self) -> None:
        """Test detection of phone numbers with dots."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.CONFIDENTIAL]

        text = "Phone: 555.123.4567"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def test_detects_international_phone(self) -> None:
        """Test detection of international phone numbers."""
        import re

        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        patterns = classifier.PATTERNS[DataClass.CONFIDENTIAL]

        text = "International: +1-555-123-4567"
        assert any(re.search(p, text, re.IGNORECASE) for p in patterns)
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS (patterns should already match)

**Step 3: Commit**

```bash
git add backend/tests/test_data_classification.py
git commit -m "test(security): add pattern detection tests

Tests for SSN, credit cards, DOB, PHI, financial, and contact patterns

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement DataClassifier.classify() Method

**Files:**
- Modify: `backend/src/security/data_classification.py`
- Modify: `backend/tests/test_data_classification.py`

**Step 1: Write failing tests for classify method**

Add to `backend/tests/test_data_classification.py`:

```python
class TestDataClassifierClassify:
    """Tests for DataClassifier.classify() method."""

    @pytest.mark.asyncio
    async def test_classify_returns_classified_data(self) -> None:
        """Test classify returns ClassifiedData instance."""
        from src.security.data_classification import (
            ClassifiedData,
            DataClassifier,
        )

        classifier = DataClassifier()
        result = await classifier.classify("test data", {"source": "test"})

        assert isinstance(result, ClassifiedData)
        assert result.data == "test data"
        assert result.source == "test"

    @pytest.mark.asyncio
    async def test_classify_detects_ssn_as_regulated(self) -> None:
        """Test SSN is classified as REGULATED."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Customer SSN: 123-45-6789",
            {"source": "user_input"},
        )

        assert result.classification == DataClass.REGULATED

    @pytest.mark.asyncio
    async def test_classify_detects_credit_card_as_regulated(self) -> None:
        """Test credit card is classified as REGULATED."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Payment: 1234-5678-9012-3456",
            {"source": "user_input"},
        )

        assert result.classification == DataClass.REGULATED

    @pytest.mark.asyncio
    async def test_classify_detects_phi_as_regulated(self) -> None:
        """Test PHI keywords are classified as REGULATED."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Patient diagnosis shows improvement",
            {"source": "medical_record"},
        )

        assert result.classification == DataClass.REGULATED

    @pytest.mark.asyncio
    async def test_classify_detects_revenue_as_restricted(self) -> None:
        """Test revenue mention is classified as RESTRICTED."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Q4 revenue exceeded targets",
            {"source": "financial_report"},
        )

        assert result.classification == DataClass.RESTRICTED

    @pytest.mark.asyncio
    async def test_classify_detects_dollar_amount_as_restricted(self) -> None:
        """Test dollar amounts are classified as RESTRICTED."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Deal worth $4.2M",
            {"source": "crm"},
        )

        assert result.classification == DataClass.RESTRICTED

    @pytest.mark.asyncio
    async def test_classify_detects_email_as_confidential(self) -> None:
        """Test email addresses are classified as CONFIDENTIAL."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Contact: john.doe@company.com",
            {"source": "contact_list"},
        )

        assert result.classification == DataClass.CONFIDENTIAL

    @pytest.mark.asyncio
    async def test_classify_detects_phone_as_confidential(self) -> None:
        """Test phone numbers are classified as CONFIDENTIAL."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Call 555-123-4567 for details",
            {"source": "notes"},
        )

        assert result.classification == DataClass.CONFIDENTIAL

    @pytest.mark.asyncio
    async def test_classify_defaults_to_internal(self) -> None:
        """Test non-sensitive data defaults to INTERNAL."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Meeting scheduled for next Tuesday",
            {"source": "calendar"},
        )

        assert result.classification == DataClass.INTERNAL

    @pytest.mark.asyncio
    async def test_classify_uses_most_sensitive_match(self) -> None:
        """Test that most sensitive pattern wins when multiple match."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        # Contains both email (CONFIDENTIAL) and SSN (REGULATED)
        result = await classifier.classify(
            "SSN 123-45-6789 email: test@example.com",
            {"source": "user_input"},
        )

        # Should be REGULATED (most sensitive)
        assert result.classification == DataClass.REGULATED

    @pytest.mark.asyncio
    async def test_classify_handles_dict_data(self) -> None:
        """Test classify handles dict data by converting to string."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            {"ssn": "123-45-6789", "name": "John"},
            {"source": "user_input"},
        )

        assert result.classification == DataClass.REGULATED
        assert result.data == {"ssn": "123-45-6789", "name": "John"}

    @pytest.mark.asyncio
    async def test_classify_handles_list_data(self) -> None:
        """Test classify handles list data by converting to string."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            ["john@example.com", "jane@example.com"],
            {"source": "user_input"},
        )

        assert result.classification == DataClass.CONFIDENTIAL

    @pytest.mark.asyncio
    async def test_classify_handles_none_data(self) -> None:
        """Test classify handles None data."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(None, {"source": "test"})

        assert result.classification == DataClass.INTERNAL
        assert result.data is None

    @pytest.mark.asyncio
    async def test_classify_is_case_insensitive(self) -> None:
        """Test pattern matching is case insensitive."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()

        result1 = await classifier.classify("REVENUE targets", {"source": "test"})
        result2 = await classifier.classify("revenue targets", {"source": "test"})
        result3 = await classifier.classify("Revenue Targets", {"source": "test"})

        assert result1.classification == DataClass.RESTRICTED
        assert result2.classification == DataClass.RESTRICTED
        assert result3.classification == DataClass.RESTRICTED
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py::TestDataClassifierClassify -v`
Expected: FAIL (classify method doesn't exist)

**Step 3: Implement classify method**

Add to DataClassifier class in `backend/src/security/data_classification.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/data_classification.py backend/tests/test_data_classification.py
git commit -m "feat(security): implement DataClassifier.classify() method

Async method that classifies data by scanning for sensitive patterns.
Returns most sensitive classification found.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add Context-Based Classification

**Files:**
- Modify: `backend/src/security/data_classification.py`
- Modify: `backend/tests/test_data_classification.py`

**Step 1: Write failing tests for context-based classification**

Add to `backend/tests/test_data_classification.py`:

```python
class TestContextBasedClassification:
    """Tests for context-based classification fallback."""

    @pytest.mark.asyncio
    async def test_crm_deal_source_classifies_as_confidential(self) -> None:
        """Test CRM deal data defaults to CONFIDENTIAL."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Meeting notes from customer call",
            {"source": "crm_deal"},
        )

        # Should be CONFIDENTIAL due to source context
        assert result.classification == DataClass.CONFIDENTIAL
        assert result.data_type == "deal_info"

    @pytest.mark.asyncio
    async def test_financial_report_source_classifies_as_restricted(self) -> None:
        """Test financial report data defaults to RESTRICTED."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Q4 summary report",
            {"source": "financial_report"},
        )

        # Should be RESTRICTED due to source context
        assert result.classification == DataClass.RESTRICTED
        assert result.data_type == "financial"

    @pytest.mark.asyncio
    async def test_pattern_match_overrides_context(self) -> None:
        """Test pattern match takes precedence over context."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        # Contains SSN, even though source is just "notes"
        result = await classifier.classify(
            "Customer SSN: 123-45-6789",
            {"source": "notes"},
        )

        # Should be REGULATED due to SSN pattern, not INTERNAL
        assert result.classification == DataClass.REGULATED

    @pytest.mark.asyncio
    async def test_unknown_source_defaults_to_internal(self) -> None:
        """Test unknown source defaults to INTERNAL."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "General meeting notes",
            {"source": "unknown_system"},
        )

        assert result.classification == DataClass.INTERNAL

    @pytest.mark.asyncio
    async def test_missing_source_uses_unknown(self) -> None:
        """Test missing source key uses 'unknown'."""
        from src.security.data_classification import DataClass, DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify("Some data", {})

        assert result.source == "unknown"
        assert result.classification == DataClass.INTERNAL
```

**Step 2: Run tests to verify some fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py::TestContextBasedClassification -v`
Expected: Some tests FAIL (context-based classification not implemented)

**Step 3: Update classify method with context-based classification**

Update the `classify` method in `backend/src/security/data_classification.py`:

```python
    async def classify(self, data: Any, context: dict[str, Any]) -> ClassifiedData:
        """Classify data based on content patterns and context.

        Scans data for sensitive patterns and returns appropriate classification.
        Checks from most sensitive (REGULATED) to least sensitive (CONFIDENTIAL).
        Falls back to context-based classification if no patterns match.
        Defaults to INTERNAL if no sensitive patterns or context found.

        Args:
            data: The data to classify (any type, will be converted to string for scanning).
            context: Context about the data source and type.
                - source: Where this data came from (e.g., "crm", "user_input").

        Returns:
            ClassifiedData with appropriate classification and metadata.
        """
        # Convert data to string for pattern matching
        text = str(data) if data is not None else ""
        source = context.get("source", "unknown")

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
                        source=source,
                    )

        # Context-based classification fallback
        if source == "crm_deal":
            return ClassifiedData(
                data=data,
                classification=DataClass.CONFIDENTIAL,
                data_type="deal_info",
                source=source,
            )

        if source == "financial_report":
            return ClassifiedData(
                data=data,
                classification=DataClass.RESTRICTED,
                data_type="financial",
                source=source,
            )

        # Default to INTERNAL if no sensitive patterns or context found
        return ClassifiedData(
            data=data,
            classification=DataClass.INTERNAL,
            data_type="general",
            source=source,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/data_classification.py backend/tests/test_data_classification.py
git commit -m "feat(security): add context-based classification fallback

CRM deals -> CONFIDENTIAL, financial reports -> RESTRICTED
Pattern matches still take precedence over context

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Add can_be_tokenized Logic

**Files:**
- Modify: `backend/src/security/data_classification.py`
- Modify: `backend/tests/test_data_classification.py`

**Step 1: Write failing tests for can_be_tokenized**

Add to `backend/tests/test_data_classification.py`:

```python
class TestCanBeTokenized:
    """Tests for can_be_tokenized logic."""

    @pytest.mark.asyncio
    async def test_ssn_cannot_be_tokenized(self) -> None:
        """Test SSNs are marked as not tokenizable."""
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "SSN: 123-45-6789",
            {"source": "user_input"},
        )

        assert result.can_be_tokenized is False

    @pytest.mark.asyncio
    async def test_credit_card_cannot_be_tokenized(self) -> None:
        """Test credit cards are marked as not tokenizable."""
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Card: 1234-5678-9012-3456",
            {"source": "user_input"},
        )

        assert result.can_be_tokenized is False

    @pytest.mark.asyncio
    async def test_dob_cannot_be_tokenized(self) -> None:
        """Test DOB is marked as not tokenizable."""
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "DOB: 01/15/1990",
            {"source": "user_input"},
        )

        assert result.can_be_tokenized is False

    @pytest.mark.asyncio
    async def test_email_can_be_tokenized(self) -> None:
        """Test emails can be tokenized."""
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Contact: john@example.com",
            {"source": "user_input"},
        )

        assert result.can_be_tokenized is True

    @pytest.mark.asyncio
    async def test_phone_can_be_tokenized(self) -> None:
        """Test phone numbers can be tokenized."""
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Call 555-123-4567",
            {"source": "user_input"},
        )

        assert result.can_be_tokenized is True

    @pytest.mark.asyncio
    async def test_financial_can_be_tokenized(self) -> None:
        """Test financial data can be tokenized."""
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Revenue: $4.2M",
            {"source": "user_input"},
        )

        assert result.can_be_tokenized is True

    @pytest.mark.asyncio
    async def test_internal_data_can_be_tokenized(self) -> None:
        """Test internal data can be tokenized."""
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        result = await classifier.classify(
            "Meeting notes",
            {"source": "user_input"},
        )

        assert result.can_be_tokenized is True
```

**Step 2: Run tests to verify some fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py::TestCanBeTokenized -v`
Expected: Some tests FAIL (can_be_tokenized not set correctly)

**Step 3: Update classify method to set can_be_tokenized**

Update the `classify` method and add helper in `backend/src/security/data_classification.py`:

```python
    # Add these class constants before PATTERNS
    # Patterns that indicate data that CANNOT be tokenized (must be fully redacted)
    NON_TOKENIZABLE_PATTERNS: set[str] = {
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN with dashes
        r"\b\d{9}\b",  # SSN without dashes
        r"\b(?:\d{4}[-\s]?){3}\d{4}\b",  # Credit card
        r"\b\d{16}\b",  # Credit card without separators
        r"\bDOB\s*[:\-]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",  # Date of birth
    }
```

Then update the `classify` method to check tokenizability:

```python
    async def classify(self, data: Any, context: dict[str, Any]) -> ClassifiedData:
        """Classify data based on content patterns and context.

        Scans data for sensitive patterns and returns appropriate classification.
        Checks from most sensitive (REGULATED) to least sensitive (CONFIDENTIAL).
        Falls back to context-based classification if no patterns match.
        Defaults to INTERNAL if no sensitive patterns or context found.

        Args:
            data: The data to classify (any type, will be converted to string for scanning).
            context: Context about the data source and type.
                - source: Where this data came from (e.g., "crm", "user_input").

        Returns:
            ClassifiedData with appropriate classification and metadata.
        """
        # Convert data to string for pattern matching
        text = str(data) if data is not None else ""
        source = context.get("source", "unknown")

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
                        source=source,
                        can_be_tokenized=self._can_be_tokenized(pattern),
                    )

        # Context-based classification fallback
        if source == "crm_deal":
            return ClassifiedData(
                data=data,
                classification=DataClass.CONFIDENTIAL,
                data_type="deal_info",
                source=source,
                can_be_tokenized=True,
            )

        if source == "financial_report":
            return ClassifiedData(
                data=data,
                classification=DataClass.RESTRICTED,
                data_type="financial",
                source=source,
                can_be_tokenized=True,
            )

        # Default to INTERNAL if no sensitive patterns or context found
        return ClassifiedData(
            data=data,
            classification=DataClass.INTERNAL,
            data_type="general",
            source=source,
            can_be_tokenized=True,
        )

    def _can_be_tokenized(self, pattern: str) -> bool:
        """Determine if data matching this pattern can be tokenized.

        Some data (like SSNs) should never be tokenized, only fully redacted.

        Args:
            pattern: The regex pattern that matched.

        Returns:
            True if data can be tokenized, False if it must be redacted.
        """
        return pattern not in self.NON_TOKENIZABLE_PATTERNS
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/data_classification.py backend/tests/test_data_classification.py
git commit -m "feat(security): add can_be_tokenized logic

SSN, credit cards, DOB cannot be tokenized (must be redacted)
Other sensitive data can be replaced with tokens

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Module Exports and Final Tests

**Files:**
- Modify: `backend/src/security/__init__.py`
- Modify: `backend/tests/test_data_classification.py`

**Step 1: Write tests for module exports**

Add to `backend/tests/test_data_classification.py`:

```python
class TestModuleExports:
    """Tests for module exports."""

    def test_security_module_exports_data_class(self) -> None:
        """Test DataClass is exported from security module."""
        from src.security import DataClass

        assert DataClass.PUBLIC.value == "public"

    def test_security_module_exports_classified_data(self) -> None:
        """Test ClassifiedData is exported from security module."""
        from src.security import ClassifiedData, DataClass

        data = ClassifiedData(
            data="test",
            classification=DataClass.PUBLIC,
            data_type="test",
            source="test",
        )
        assert data.data == "test"

    def test_security_module_exports_data_classifier(self) -> None:
        """Test DataClassifier is exported from security module."""
        from src.security import DataClassifier

        classifier = DataClassifier()
        assert hasattr(classifier, "PATTERNS")
        assert hasattr(classifier, "classify")
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py::TestModuleExports -v`
Expected: PASS

**Step 3: Add integration test**

Add to `backend/tests/test_data_classification.py`:

```python
class TestDataClassificationIntegration:
    """Integration tests for data classification system."""

    @pytest.mark.asyncio
    async def test_full_classification_workflow(self) -> None:
        """Test complete classification workflow with various data types."""
        from src.security import ClassifiedData, DataClass, DataClassifier

        classifier = DataClassifier()

        # Test various data types
        test_cases = [
            # (data, context, expected_class, expected_tokenizable)
            ("SSN: 123-45-6789", {"source": "user"}, DataClass.REGULATED, False),
            ("Card: 1234567890123456", {"source": "payment"}, DataClass.REGULATED, False),
            ("DOB: 01/15/1990", {"source": "form"}, DataClass.REGULATED, False),
            ("Patient diagnosis is stable", {"source": "ehr"}, DataClass.REGULATED, True),
            ("Revenue: $4.2M", {"source": "report"}, DataClass.RESTRICTED, True),
            ("Deal size estimate", {"source": "crm"}, DataClass.RESTRICTED, True),
            ("Contact: john@example.com", {"source": "email"}, DataClass.CONFIDENTIAL, True),
            ("Call 555-123-4567", {"source": "notes"}, DataClass.CONFIDENTIAL, True),
            ("Meeting scheduled", {"source": "calendar"}, DataClass.INTERNAL, True),
        ]

        for data, context, expected_class, expected_tokenizable in test_cases:
            result = await classifier.classify(data, context)
            assert isinstance(result, ClassifiedData), f"Failed for: {data}"
            assert result.classification == expected_class, f"Wrong class for: {data}"
            assert result.can_be_tokenized == expected_tokenizable, f"Wrong tokenizable for: {data}"

    @pytest.mark.asyncio
    async def test_classifier_handles_complex_mixed_data(self) -> None:
        """Test classifier with complex data containing multiple patterns."""
        from src.security import DataClass, DataClassifier

        classifier = DataClassifier()

        # Data with multiple sensitive items - should get most sensitive
        mixed_data = """
        Customer Record:
        Name: John Doe
        Email: john.doe@company.com
        SSN: 123-45-6789
        Revenue Target: $5M
        """

        result = await classifier.classify(mixed_data, {"source": "crm"})

        # Should be REGULATED due to SSN
        assert result.classification == DataClass.REGULATED
        assert result.can_be_tokenized is False

    @pytest.mark.asyncio
    async def test_classifier_performance_with_large_text(self) -> None:
        """Test classifier handles large text efficiently."""
        import time

        from src.security import DataClass, DataClassifier

        classifier = DataClassifier()

        # Generate large text (100KB)
        large_text = "This is a test sentence. " * 5000
        large_text += " SSN: 123-45-6789"  # Add sensitive data at end

        start = time.time()
        result = await classifier.classify(large_text, {"source": "test"})
        elapsed = time.time() - start

        assert result.classification == DataClass.REGULATED
        # Should complete in under 1 second
        assert elapsed < 1.0, f"Classification took too long: {elapsed}s"
```

**Step 4: Run all tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/__init__.py backend/tests/test_data_classification.py
git commit -m "test(security): add module export and integration tests

Verifies complete classification workflow and performance

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Run Type Checking and Linting

**Files:**
- Modify: `backend/src/security/data_classification.py` (if needed)

**Step 1: Run mypy type checking**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/security/ --strict`
Expected: No errors (or fix any that appear)

**Step 2: Run ruff linting**

Run: `cd /Users/dhruv/aria/backend && python -m ruff check src/security/`
Expected: No errors (or fix any that appear)

**Step 3: Run ruff formatting**

Run: `cd /Users/dhruv/aria/backend && python -m ruff format src/security/`
Expected: Formatting applied if needed

**Step 4: Run all tests one final time**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v`
Expected: PASS

**Step 5: Commit any fixes**

```bash
git add backend/src/security/
git commit -m "style(security): apply type hints and formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Final Verification and Summary

**Step 1: Verify all files exist**

Run: `ls -la /Users/dhruv/aria/backend/src/security/`
Expected: `__init__.py` and `data_classification.py`

**Step 2: Verify test file exists**

Run: `ls -la /Users/dhruv/aria/backend/tests/test_data_classification.py`
Expected: File exists

**Step 3: Run full test suite for security module**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_data_classification.py -v --tb=short`
Expected: All tests PASS

**Step 4: Verify module can be imported**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.security import DataClass, ClassifiedData, DataClassifier; print('OK')"`
Expected: Prints "OK"

**Step 5: Final commit with summary**

```bash
git add -A
git commit -m "feat(security): complete US-520 data classification system

Implements:
- DataClass enum: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, REGULATED
- ClassifiedData dataclass with classification metadata
- DataClassifier with pattern detection for:
  - SSN, credit cards, DOB (REGULATED)
  - Revenue, pricing, confidential markers (RESTRICTED)
  - Emails, phone numbers (CONFIDENTIAL)
- Context-based classification fallback
- can_be_tokenized logic (SSN/CC must be redacted)

Reference: docs/ARIA_SKILLS_INTEGRATION_ARCHITECTURE.md Part 1.2

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan implements US-520 with:

1. **DataClass enum** - 5 sensitivity levels ordered from PUBLIC to REGULATED
2. **ClassifiedData dataclass** - Wraps data with classification, type, source, tokenizability
3. **DataClassifier** - Async pattern-based classification with:
   - REGULATED patterns: SSN, credit cards, DOB, PHI keywords
   - RESTRICTED patterns: Revenue, profits, deal sizes, confidential markers
   - CONFIDENTIAL patterns: Emails, phone numbers
   - Context-based fallback for CRM deals and financial reports
   - can_be_tokenized logic for sensitive data handling

All code follows TDD with tests written before implementation.
