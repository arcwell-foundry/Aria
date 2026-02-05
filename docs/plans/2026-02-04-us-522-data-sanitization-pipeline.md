# US-522: Data Sanitization Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a data sanitization pipeline that tokenizes, redacts, and validates data before it reaches skills based on trust levels.

**Architecture:** The sanitizer sits between classified data and skill execution. It uses `DataClassifier` to identify sensitive data, `can_access_data()` to check permissions, and replaces disallowed data with tokens or redaction markers. On output, it validates for leakage and detokenizes authorized values.

**Tech Stack:** Python 3.11+, dataclasses, regex, pytest, mypy

---

## Task 1: Create TokenMap Class

**Files:**
- Create: `backend/src/security/sanitization.py`
- Test: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for TokenMap initialization**

```python
# backend/tests/test_sanitization.py
"""Tests for data sanitization pipeline."""

import pytest


class TestTokenMap:
    """Tests for TokenMap class."""

    def test_token_map_initializes_empty(self) -> None:
        """Test TokenMap starts with empty tokens dict."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        assert token_map.tokens == {}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestTokenMap::test_token_map_initializes_empty -v`
Expected: FAIL with "No module named 'src.security.sanitization'" or "cannot import name 'TokenMap'"

**Step 3: Write minimal implementation**

```python
# backend/src/security/sanitization.py
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestTokenMap::test_token_map_initializes_empty -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add TokenMap class skeleton

Initial TokenMap dataclass for US-522 sanitization pipeline.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement TokenMap.add_token() Method

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for add_token**

```python
# Add to backend/tests/test_sanitization.py, in TestTokenMap class

    def test_add_token_returns_token_string(self) -> None:
        """Test add_token returns formatted token string."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token = token_map.add_token("financial", "$4.2M")

        assert token == "[FINANCIAL_001]"

    def test_add_token_stores_mapping(self) -> None:
        """Test add_token stores token to value mapping."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token = token_map.add_token("contact", "john@example.com")

        assert token_map.tokens[token] == "john@example.com"

    def test_add_token_increments_counter(self) -> None:
        """Test add_token increments counter for same data type."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token1 = token_map.add_token("contact", "john@example.com")
        token2 = token_map.add_token("contact", "jane@example.com")
        token3 = token_map.add_token("financial", "$1M")

        assert token1 == "[CONTACT_001]"
        assert token2 == "[CONTACT_002]"
        assert token3 == "[FINANCIAL_001]"

    def test_add_token_uppercases_data_type(self) -> None:
        """Test add_token uppercases the data type in token."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token = token_map.add_token("Credit_Card", "1234-5678")

        assert token == "[CREDIT_CARD_001]"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestTokenMap::test_add_token_returns_token_string -v`
Expected: FAIL with "AttributeError: 'TokenMap' object has no attribute 'add_token'"

**Step 3: Write minimal implementation**

```python
# Update backend/src/security/sanitization.py

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
```

**Step 4: Run all TokenMap tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestTokenMap -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add TokenMap.add_token() method

Generates tokens in [DATA_TYPE_NNN] format with incrementing counters.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement TokenMap.get_original() Method

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for get_original**

```python
# Add to backend/tests/test_sanitization.py, in TestTokenMap class

    def test_get_original_returns_value(self) -> None:
        """Test get_original returns the original value for a token."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()
        token = token_map.add_token("financial", "$4.2M")

        original = token_map.get_original(token)

        assert original == "$4.2M"

    def test_get_original_returns_none_for_unknown_token(self) -> None:
        """Test get_original returns None for unknown token."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        original = token_map.get_original("[UNKNOWN_001]")

        assert original is None

    def test_get_original_preserves_complex_types(self) -> None:
        """Test get_original preserves complex data types."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()
        complex_value = {"amount": 4200000, "currency": "USD"}
        token = token_map.add_token("financial", complex_value)

        original = token_map.get_original(token)

        assert original == {"amount": 4200000, "currency": "USD"}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestTokenMap::test_get_original_returns_value -v`
Expected: FAIL with "AttributeError: 'TokenMap' object has no attribute 'get_original'"

**Step 3: Write minimal implementation**

```python
# Add to TokenMap class in backend/src/security/sanitization.py

    def get_original(self, token: str) -> Any | None:
        """Get the original value for a token.

        Args:
            token: The token string to look up.

        Returns:
            The original value, or None if token not found.
        """
        return self.tokens.get(token)
```

**Step 4: Run all TokenMap tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestTokenMap -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add TokenMap.get_original() method

Retrieves original values from token strings for detokenization.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Create LeakageReport Dataclass

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for LeakageReport**

```python
# Add to backend/tests/test_sanitization.py

class TestLeakageReport:
    """Tests for LeakageReport dataclass."""

    def test_leakage_report_initializes_with_required_fields(self) -> None:
        """Test LeakageReport initializes with required fields."""
        from src.security.sanitization import LeakageReport

        report = LeakageReport(
            leaked=True,
            leaked_values=["$4.2M", "john@example.com"],
            severity="high",
        )

        assert report.leaked is True
        assert report.leaked_values == ["$4.2M", "john@example.com"]
        assert report.severity == "high"

    def test_leakage_report_no_leak(self) -> None:
        """Test LeakageReport for clean output."""
        from src.security.sanitization import LeakageReport

        report = LeakageReport(
            leaked=False,
            leaked_values=[],
            severity="none",
        )

        assert report.leaked is False
        assert report.leaked_values == []
        assert report.severity == "none"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestLeakageReport -v`
Expected: FAIL with "cannot import name 'LeakageReport'"

**Step 3: Write minimal implementation**

```python
# Add to backend/src/security/sanitization.py after TokenMap

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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestLeakageReport -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add LeakageReport dataclass

Reports data leakage detection results with severity levels.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create DataSanitizer Class Skeleton

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for DataSanitizer initialization**

```python
# Add to backend/tests/test_sanitization.py

class TestDataSanitizer:
    """Tests for DataSanitizer class."""

    def test_data_sanitizer_initializes(self) -> None:
        """Test DataSanitizer initializes with classifier."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        assert sanitizer.classifier is classifier
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_data_sanitizer_initializes -v`
Expected: FAIL with "cannot import name 'DataSanitizer'"

**Step 3: Write minimal implementation**

```python
# Add to backend/src/security/sanitization.py

from src.security.data_classification import DataClassifier, ClassifiedData, DataClass
from src.security.trust_levels import SkillTrustLevel, can_access_data


class DataSanitizer:
    """Sanitizes data for skill execution based on trust levels.

    Implements the full sanitization pipeline:
    1. Classify all data fields
    2. Check trust permissions
    3. Tokenize allowed sensitive data
    4. Redact disallowed data
    5. Validate output for leakage
    6. Detokenize on return

    Attributes:
        classifier: DataClassifier instance for data classification.
    """

    def __init__(self, classifier: DataClassifier) -> None:
        """Initialize DataSanitizer with a classifier.

        Args:
            classifier: DataClassifier to use for classification.
        """
        self.classifier = classifier
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_data_sanitizer_initializes -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add DataSanitizer class skeleton

Initial DataSanitizer with classifier dependency injection.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement tokenize_value() Method

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for tokenize_value**

```python
# Add to TestDataSanitizer class in backend/tests/test_sanitization.py

    def test_tokenize_value_returns_token_and_updates_map(self) -> None:
        """Test tokenize_value returns token and updates token map."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        token_map = TokenMap()

        token = sanitizer.tokenize_value("$4.2M", "financial", token_map)

        assert token == "[FINANCIAL_001]"
        assert token_map.get_original("[FINANCIAL_001]") == "$4.2M"

    def test_tokenize_value_handles_multiple_values(self) -> None:
        """Test tokenize_value handles multiple values of same type."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        token_map = TokenMap()

        token1 = sanitizer.tokenize_value("john@example.com", "contact", token_map)
        token2 = sanitizer.tokenize_value("jane@example.com", "contact", token_map)

        assert token1 == "[CONTACT_001]"
        assert token2 == "[CONTACT_002]"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_tokenize_value_returns_token_and_updates_map -v`
Expected: FAIL with "AttributeError: 'DataSanitizer' object has no attribute 'tokenize_value'"

**Step 3: Write minimal implementation**

```python
# Add to DataSanitizer class in backend/src/security/sanitization.py

    def tokenize_value(self, value: Any, data_type: str, token_map: TokenMap) -> str:
        """Replace a sensitive value with a token.

        Args:
            value: The sensitive value to tokenize.
            data_type: Category of data for token naming.
            token_map: TokenMap to store the mapping.

        Returns:
            Token string that replaces the value.
        """
        return token_map.add_token(data_type, value)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_tokenize_value_returns_token_and_updates_map tests/test_sanitization.py::TestDataSanitizer::test_tokenize_value_handles_multiple_values -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add DataSanitizer.tokenize_value() method

Replaces sensitive values with tokens using TokenMap.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Implement redact_value() Method

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for redact_value**

```python
# Add to TestDataSanitizer class in backend/tests/test_sanitization.py

    def test_redact_value_returns_redaction_marker(self) -> None:
        """Test redact_value returns [REDACTED: type] marker."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import ClassifiedData, DataClass, DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        classified = ClassifiedData(
            data="123-45-6789",
            classification=DataClass.REGULATED,
            data_type="ssn",
            source="user_input",
        )

        result = sanitizer.redact_value(classified)

        assert result == "[REDACTED: ssn]"

    def test_redact_value_uses_data_type(self) -> None:
        """Test redact_value uses data_type in marker."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import ClassifiedData, DataClass, DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        classified = ClassifiedData(
            data="john@example.com",
            classification=DataClass.CONFIDENTIAL,
            data_type="contact",
            source="crm",
        )

        result = sanitizer.redact_value(classified)

        assert result == "[REDACTED: contact]"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_redact_value_returns_redaction_marker -v`
Expected: FAIL with "AttributeError: 'DataSanitizer' object has no attribute 'redact_value'"

**Step 3: Write minimal implementation**

```python
# Add to DataSanitizer class in backend/src/security/sanitization.py

    def redact_value(self, classified_data: ClassifiedData) -> str:
        """Redact a classified value completely.

        Used when data cannot be tokenized or skill has no access.

        Args:
            classified_data: The classified data to redact.

        Returns:
            Redaction marker string.
        """
        return f"[REDACTED: {classified_data.data_type}]"
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_redact_value_returns_redaction_marker tests/test_sanitization.py::TestDataSanitizer::test_redact_value_uses_data_type -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add DataSanitizer.redact_value() method

Creates [REDACTED: type] markers for non-tokenizable data.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Implement sanitize() Method for Simple Strings

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for sanitize with string**

```python
# Add to TestDataSanitizer class in backend/tests/test_sanitization.py

    @pytest.mark.asyncio
    async def test_sanitize_string_returns_tuple(self) -> None:
        """Test sanitize returns (sanitized_data, TokenMap) tuple."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        result = await sanitizer.sanitize("Hello world", SkillTrustLevel.COMMUNITY)

        assert isinstance(result, tuple)
        assert len(result) == 2
        sanitized, token_map = result
        assert isinstance(token_map, TokenMap)

    @pytest.mark.asyncio
    async def test_sanitize_string_tokenizes_for_allowed_access(self) -> None:
        """Test sanitize tokenizes data when skill has access."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # CORE can access RESTRICTED (financial) data
        sanitized, token_map = await sanitizer.sanitize(
            "Revenue: $4.2M",
            SkillTrustLevel.CORE,
        )

        # Should tokenize the financial value
        assert "[FINANCIAL_001]" in sanitized
        assert token_map.get_original("[FINANCIAL_001]") is not None

    @pytest.mark.asyncio
    async def test_sanitize_string_redacts_for_no_access(self) -> None:
        """Test sanitize redacts data when skill lacks access."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # COMMUNITY cannot access RESTRICTED (financial) data
        sanitized, token_map = await sanitizer.sanitize(
            "Revenue: $4.2M",
            SkillTrustLevel.COMMUNITY,
        )

        assert "[REDACTED:" in sanitized
        assert len(token_map.tokens) == 0

    @pytest.mark.asyncio
    async def test_sanitize_string_redacts_non_tokenizable(self) -> None:
        """Test sanitize redacts data that cannot be tokenized."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # SSN cannot be tokenized even for CORE
        sanitized, token_map = await sanitizer.sanitize(
            "SSN: 123-45-6789",
            SkillTrustLevel.CORE,
        )

        assert "[REDACTED:" in sanitized
        assert "123-45-6789" not in sanitized
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_sanitize_string_returns_tuple -v`
Expected: FAIL with "AttributeError: 'DataSanitizer' object has no attribute 'sanitize'"

**Step 3: Write minimal implementation**

```python
# Add to DataSanitizer class in backend/src/security/sanitization.py

    async def sanitize(
        self,
        data: Any,
        skill_trust_level: SkillTrustLevel,
        context: dict[str, Any] | None = None,
    ) -> tuple[Any, TokenMap]:
        """Sanitize data for skill execution.

        Full pipeline: classify → check permissions → tokenize/redact.

        Args:
            data: The data to sanitize (string, dict, list, or any type).
            skill_trust_level: Trust level of the skill that will receive data.
            context: Optional context for classification (e.g., source).

        Returns:
            Tuple of (sanitized_data, token_map).
        """
        if context is None:
            context = {}

        token_map = TokenMap()

        if isinstance(data, str):
            return await self._sanitize_string(data, skill_trust_level, context, token_map)

        # For non-string data, classify and handle
        classified = await self.classifier.classify(data, context)
        return self._handle_classified_data(classified, skill_trust_level, token_map)

    async def _sanitize_string(
        self,
        text: str,
        skill_trust_level: SkillTrustLevel,
        context: dict[str, Any],
        token_map: TokenMap,
    ) -> tuple[str, TokenMap]:
        """Sanitize a string by finding and replacing sensitive patterns."""
        import re

        result = text

        # Check all patterns from most to least sensitive
        for classification in [DataClass.REGULATED, DataClass.RESTRICTED, DataClass.CONFIDENTIAL]:
            patterns = self.classifier.PATTERNS.get(classification, [])
            for pattern in patterns:
                matches = list(re.finditer(pattern, result, re.IGNORECASE))
                for match in reversed(matches):  # Reverse to preserve positions
                    matched_text = match.group()
                    data_type = self.classifier._infer_data_type(pattern)
                    can_tokenize = self.classifier._can_be_tokenized(pattern)

                    # Create a ClassifiedData for this match
                    classified = ClassifiedData(
                        data=matched_text,
                        classification=classification,
                        data_type=data_type,
                        source=context.get("source", "unknown"),
                        can_be_tokenized=can_tokenize,
                    )

                    # Check if skill has access
                    has_access = can_access_data(skill_trust_level, classification)

                    if has_access and can_tokenize:
                        replacement = self.tokenize_value(matched_text, data_type, token_map)
                    else:
                        replacement = self.redact_value(classified)

                    result = result[:match.start()] + replacement + result[match.end():]

        return result, token_map

    def _handle_classified_data(
        self,
        classified: ClassifiedData,
        skill_trust_level: SkillTrustLevel,
        token_map: TokenMap,
    ) -> tuple[Any, TokenMap]:
        """Handle pre-classified data based on trust level."""
        has_access = can_access_data(skill_trust_level, classified.classification)

        if has_access and classified.can_be_tokenized:
            token = self.tokenize_value(classified.data, classified.data_type, token_map)
            return token, token_map
        elif not has_access or not classified.can_be_tokenized:
            return self.redact_value(classified), token_map

        return classified.data, token_map
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_sanitize_string_returns_tuple tests/test_sanitization.py::TestDataSanitizer::test_sanitize_string_tokenizes_for_allowed_access tests/test_sanitization.py::TestDataSanitizer::test_sanitize_string_redacts_for_no_access tests/test_sanitization.py::TestDataSanitizer::test_sanitize_string_redacts_non_tokenizable -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add DataSanitizer.sanitize() for strings

Implements full sanitization pipeline for string data:
- Pattern detection and classification
- Trust-based permission checks
- Tokenization or redaction based on access

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Implement sanitize() for Nested Dicts

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for dict sanitization**

```python
# Add to TestDataSanitizer class in backend/tests/test_sanitization.py

    @pytest.mark.asyncio
    async def test_sanitize_dict_processes_all_values(self) -> None:
        """Test sanitize processes all values in a dict."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = {
            "name": "Acme Corp",
            "revenue": "$4.2M",
            "contact": "john@example.com",
        }

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.CORE)

        assert isinstance(sanitized, dict)
        assert "name" in sanitized
        # Financial data should be tokenized for CORE
        assert "[FINANCIAL_" in str(sanitized.get("revenue"))
        # Contact should be tokenized for CORE
        assert "[CONTACT_" in str(sanitized.get("contact"))

    @pytest.mark.asyncio
    async def test_sanitize_dict_handles_nested_dicts(self) -> None:
        """Test sanitize handles nested dictionaries."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = {
            "company": "Acme",
            "financials": {
                "revenue": "$4.2M",
                "profit": "$1.5M",
            },
        }

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.COMMUNITY)

        assert isinstance(sanitized["financials"], dict)
        # COMMUNITY cannot access RESTRICTED
        assert "[REDACTED:" in str(sanitized["financials"]["revenue"])
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_sanitize_dict_processes_all_values -v`
Expected: FAIL (dict not handled properly)

**Step 3: Update implementation to handle dicts**

```python
# Update sanitize method in DataSanitizer class

    async def sanitize(
        self,
        data: Any,
        skill_trust_level: SkillTrustLevel,
        context: dict[str, Any] | None = None,
    ) -> tuple[Any, TokenMap]:
        """Sanitize data for skill execution.

        Full pipeline: classify → check permissions → tokenize/redact.

        Args:
            data: The data to sanitize (string, dict, list, or any type).
            skill_trust_level: Trust level of the skill that will receive data.
            context: Optional context for classification (e.g., source).

        Returns:
            Tuple of (sanitized_data, token_map).
        """
        if context is None:
            context = {}

        token_map = TokenMap()
        sanitized = await self._sanitize_recursive(data, skill_trust_level, context, token_map)
        return sanitized, token_map

    async def _sanitize_recursive(
        self,
        data: Any,
        skill_trust_level: SkillTrustLevel,
        context: dict[str, Any],
        token_map: TokenMap,
    ) -> Any:
        """Recursively sanitize data structures."""
        if isinstance(data, str):
            result, _ = await self._sanitize_string(data, skill_trust_level, context, token_map)
            return result

        if isinstance(data, dict):
            return {
                key: await self._sanitize_recursive(value, skill_trust_level, context, token_map)
                for key, value in data.items()
            }

        if isinstance(data, list):
            return [
                await self._sanitize_recursive(item, skill_trust_level, context, token_map)
                for item in data
            ]

        # For other types (int, float, bool, None), classify and handle
        if data is None:
            return None

        classified = await self.classifier.classify(data, context)
        result, _ = self._handle_classified_data(classified, skill_trust_level, token_map)
        return result
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_sanitize_dict_processes_all_values tests/test_sanitization.py::TestDataSanitizer::test_sanitize_dict_handles_nested_dicts -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add nested dict support to sanitize()

Recursively processes dict values for deep data structures.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Implement sanitize() for Lists

**Files:**
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for list sanitization**

```python
# Add to TestDataSanitizer class in backend/tests/test_sanitization.py

    @pytest.mark.asyncio
    async def test_sanitize_list_processes_all_items(self) -> None:
        """Test sanitize processes all items in a list."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = ["john@example.com", "jane@example.com", "public info"]

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.CORE)

        assert isinstance(sanitized, list)
        assert len(sanitized) == 3
        # Emails should be tokenized
        assert "[CONTACT_" in sanitized[0]
        assert "[CONTACT_" in sanitized[1]
        # Non-sensitive data unchanged
        assert sanitized[2] == "public info"

    @pytest.mark.asyncio
    async def test_sanitize_list_of_dicts(self) -> None:
        """Test sanitize handles list of dictionaries."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = [
            {"name": "John", "email": "john@example.com"},
            {"name": "Jane", "email": "jane@example.com"},
        ]

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.CORE)

        assert isinstance(sanitized, list)
        assert len(sanitized) == 2
        assert sanitized[0]["name"] == "John"
        assert "[CONTACT_" in sanitized[0]["email"]
```

**Step 2: Run test to verify it passes (already implemented)**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_sanitize_list_processes_all_items tests/test_sanitization.py::TestDataSanitizer::test_sanitize_list_of_dicts -v`
Expected: PASS (2 tests) - list handling already in place

**Step 3: Commit test additions**

```bash
git add backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
test(security): add list sanitization tests

Verifies list and nested list/dict handling in sanitization.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Implement detokenize() Method

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for detokenize**

```python
# Add to TestDataSanitizer class in backend/tests/test_sanitization.py

    def test_detokenize_string_restores_values(self) -> None:
        """Test detokenize restores tokenized values in string."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")
        token_map.add_token("contact", "john@example.com")

        output = "The deal is [FINANCIAL_001] and contact [CONTACT_001]"

        restored = sanitizer.detokenize(output, token_map)

        assert restored == "The deal is $4.2M and contact john@example.com"

    def test_detokenize_preserves_redaction_markers(self) -> None:
        """Test detokenize does not affect redaction markers."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        token_map = TokenMap()

        output = "SSN is [REDACTED: ssn] and name is John"

        restored = sanitizer.detokenize(output, token_map)

        assert restored == "SSN is [REDACTED: ssn] and name is John"

    def test_detokenize_handles_dict(self) -> None:
        """Test detokenize restores values in dict."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("contact", "john@example.com")

        output = {"result": "Contact is [CONTACT_001]", "status": "ok"}

        restored = sanitizer.detokenize(output, token_map)

        assert restored["result"] == "Contact is john@example.com"
        assert restored["status"] == "ok"

    def test_detokenize_handles_list(self) -> None:
        """Test detokenize restores values in list."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")

        output = ["Revenue is [FINANCIAL_001]", "Target achieved"]

        restored = sanitizer.detokenize(output, token_map)

        assert restored[0] == "Revenue is $4.2M"
        assert restored[1] == "Target achieved"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_detokenize_string_restores_values -v`
Expected: FAIL with "AttributeError: 'DataSanitizer' object has no attribute 'detokenize'"

**Step 3: Write minimal implementation**

```python
# Add to DataSanitizer class in backend/src/security/sanitization.py

    def detokenize(self, output: Any, token_map: TokenMap) -> Any:
        """Restore tokenized values in skill output.

        Replaces token strings with their original values.
        Does not affect [REDACTED: ...] markers.

        Args:
            output: The skill output to detokenize.
            token_map: TokenMap with token-to-value mappings.

        Returns:
            Output with tokens replaced by original values.
        """
        return self._detokenize_recursive(output, token_map)

    def _detokenize_recursive(self, data: Any, token_map: TokenMap) -> Any:
        """Recursively detokenize data structures."""
        if isinstance(data, str):
            result = data
            for token, original in token_map.tokens.items():
                result = result.replace(token, str(original))
            return result

        if isinstance(data, dict):
            return {
                key: self._detokenize_recursive(value, token_map)
                for key, value in data.items()
            }

        if isinstance(data, list):
            return [
                self._detokenize_recursive(item, token_map)
                for item in data
            ]

        return data
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_detokenize_string_restores_values tests/test_sanitization.py::TestDataSanitizer::test_detokenize_preserves_redaction_markers tests/test_sanitization.py::TestDataSanitizer::test_detokenize_handles_dict tests/test_sanitization.py::TestDataSanitizer::test_detokenize_handles_list -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add DataSanitizer.detokenize() method

Restores original values in skill output from token map.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Implement validate_output() Method

**Files:**
- Modify: `backend/src/security/sanitization.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for validate_output**

```python
# Add to TestDataSanitizer class in backend/tests/test_sanitization.py

    def test_validate_output_detects_leaked_values(self) -> None:
        """Test validate_output detects leaked original values."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")
        token_map.add_token("contact", "john@example.com")

        # Output contains leaked value
        output = "The revenue is $4.2M and target is [FINANCIAL_002]"

        report = sanitizer.validate_output(output, token_map)

        assert report.leaked is True
        assert "$4.2M" in report.leaked_values
        assert report.severity == "high"

    def test_validate_output_clean_output(self) -> None:
        """Test validate_output reports clean for safe output."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")

        # Output only contains tokens, no original values
        output = "The revenue is [FINANCIAL_001] as expected"

        report = sanitizer.validate_output(output, token_map)

        assert report.leaked is False
        assert report.leaked_values == []
        assert report.severity == "none"

    def test_validate_output_checks_nested_structures(self) -> None:
        """Test validate_output checks nested dicts and lists."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("contact", "john@example.com")

        # Leaked value in nested structure
        output = {
            "summary": "Contact info",
            "details": {
                "email": "john@example.com",  # Leaked!
            },
        }

        report = sanitizer.validate_output(output, token_map)

        assert report.leaked is True
        assert "john@example.com" in report.leaked_values

    def test_validate_output_severity_levels(self) -> None:
        """Test validate_output assigns correct severity levels."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # Single leak - high severity
        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")
        report = sanitizer.validate_output("Revenue: $4.2M", token_map)
        assert report.severity == "high"

        # Multiple leaks - critical severity
        token_map2 = TokenMap()
        token_map2.add_token("financial", "$4.2M")
        token_map2.add_token("contact", "john@example.com")
        report2 = sanitizer.validate_output("$4.2M and john@example.com", token_map2)
        assert report2.severity == "critical"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_validate_output_detects_leaked_values -v`
Expected: FAIL with "AttributeError: 'DataSanitizer' object has no attribute 'validate_output'"

**Step 3: Write minimal implementation**

```python
# Add to DataSanitizer class in backend/src/security/sanitization.py

    def validate_output(self, output: Any, token_map: TokenMap) -> LeakageReport:
        """Validate skill output for data leakage.

        Scans output for patterns matching original sensitive values
        that should have been tokenized.

        Args:
            output: The skill output to validate.
            token_map: TokenMap containing tokenized values to check for.

        Returns:
            LeakageReport with findings.
        """
        leaked_values: list[Any] = []

        # Convert output to string for scanning
        output_str = self._to_string_for_scan(output)

        # Check if any original values appear in output
        for token, original in token_map.tokens.items():
            original_str = str(original)
            if original_str in output_str:
                leaked_values.append(original)

        # Determine severity
        if len(leaked_values) == 0:
            severity = "none"
        elif len(leaked_values) == 1:
            severity = "high"
        else:
            severity = "critical"

        return LeakageReport(
            leaked=len(leaked_values) > 0,
            leaked_values=leaked_values,
            severity=severity,
        )

    def _to_string_for_scan(self, data: Any) -> str:
        """Convert data structure to string for leakage scanning."""
        if isinstance(data, str):
            return data

        if isinstance(data, dict):
            parts = [self._to_string_for_scan(v) for v in data.values()]
            return " ".join(parts)

        if isinstance(data, list):
            parts = [self._to_string_for_scan(item) for item in data]
            return " ".join(parts)

        return str(data) if data is not None else ""
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestDataSanitizer::test_validate_output_detects_leaked_values tests/test_sanitization.py::TestDataSanitizer::test_validate_output_clean_output tests/test_sanitization.py::TestDataSanitizer::test_validate_output_checks_nested_structures tests/test_sanitization.py::TestDataSanitizer::test_validate_output_severity_levels -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sanitization.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): add DataSanitizer.validate_output() method

Detects data leakage by scanning output for original values.
Assigns severity levels based on leak count.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Update Module Exports

**Files:**
- Modify: `backend/src/security/__init__.py`
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write the failing test for module exports**

```python
# Add to backend/tests/test_sanitization.py

class TestModuleExports:
    """Tests for sanitization module exports."""

    def test_security_module_exports_token_map(self) -> None:
        """Test TokenMap is exported from security module."""
        from src.security import TokenMap

        token_map = TokenMap()
        assert token_map.tokens == {}

    def test_security_module_exports_leakage_report(self) -> None:
        """Test LeakageReport is exported from security module."""
        from src.security import LeakageReport

        report = LeakageReport(leaked=False, leaked_values=[], severity="none")
        assert report.leaked is False

    def test_security_module_exports_data_sanitizer(self) -> None:
        """Test DataSanitizer is exported from security module."""
        from src.security import DataSanitizer, DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        assert sanitizer.classifier is classifier
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestModuleExports -v`
Expected: FAIL with "cannot import name 'TokenMap' from 'src.security'"

**Step 3: Update module exports**

```python
# Update backend/src/security/__init__.py
"""Security module for ARIA.

Provides data classification, trust levels, sanitization, sandboxing, and audit
capabilities for the skills integration system.
"""

from src.security.data_classification import (
    ClassifiedData,
    DataClass,
    DataClassifier,
)
from src.security.sanitization import (
    DataSanitizer,
    LeakageReport,
    TokenMap,
)
from src.security.trust_levels import (
    TRUST_DATA_ACCESS,
    TRUSTED_SKILL_SOURCES,
    SkillTrustLevel,
    can_access_data,
    determine_trust_level,
)

__all__ = [
    # Data classification
    "ClassifiedData",
    "DataClass",
    "DataClassifier",
    # Trust levels
    "SkillTrustLevel",
    "TRUST_DATA_ACCESS",
    "TRUSTED_SKILL_SOURCES",
    "determine_trust_level",
    "can_access_data",
    # Sanitization
    "TokenMap",
    "LeakageReport",
    "DataSanitizer",
]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestModuleExports -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/security/__init__.py backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
feat(security): export sanitization classes from security module

Adds TokenMap, LeakageReport, DataSanitizer to public API.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Integration Tests - Financial Report Scenario

**Files:**
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write integration test for financial report**

```python
# Add to backend/tests/test_sanitization.py

class TestIntegrationScenarios:
    """Integration tests with real-world scenarios."""

    @pytest.mark.asyncio
    async def test_financial_report_scenario(self) -> None:
        """Test sanitizing a financial report with revenue figures."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        financial_report = {
            "company": "Acme Corp",
            "quarter": "Q4 2025",
            "summary": "Strong quarter with revenue of $4.2M and profit margin of 35%.",
            "metrics": {
                "revenue": "$4.2M",
                "profit": "$1.47M",
                "growth": "15% YoY",
            },
            "notes": "Confidential: Do not share externally.",
        }

        # Scenario 1: COMMUNITY skill (only PUBLIC access)
        sanitized, token_map = await sanitizer.sanitize(
            financial_report,
            SkillTrustLevel.COMMUNITY,
        )

        # Company and quarter are PUBLIC - unchanged
        assert sanitized["company"] == "Acme Corp"
        assert sanitized["quarter"] == "Q4 2025"

        # Financial data should be REDACTED (not tokenized)
        assert "[REDACTED:" in sanitized["summary"]
        assert "[REDACTED:" in str(sanitized["metrics"]["revenue"])
        assert "[REDACTED:" in str(sanitized["metrics"]["profit"])

        # "Confidential" marker triggers RESTRICTED classification
        assert "[REDACTED:" in sanitized["notes"]

        # Scenario 2: CORE skill (can access RESTRICTED)
        sanitized_core, token_map_core = await sanitizer.sanitize(
            financial_report,
            SkillTrustLevel.CORE,
        )

        # Financial data should be TOKENIZED (not redacted)
        assert "[FINANCIAL_" in sanitized_core["summary"]
        assert "[FINANCIAL_" in str(sanitized_core["metrics"]["revenue"])

        # Verify detokenization works
        restored = sanitizer.detokenize(sanitized_core, token_map_core)
        assert "$4.2M" in str(restored["summary"])
```

**Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestIntegrationScenarios::test_financial_report_scenario -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
test(security): add financial report integration test

Verifies end-to-end sanitization for financial data scenarios.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Integration Tests - Contact List Scenario

**Files:**
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write integration test for contact list**

```python
# Add to TestIntegrationScenarios class in backend/tests/test_sanitization.py

    @pytest.mark.asyncio
    async def test_contact_list_scenario(self) -> None:
        """Test sanitizing a contact list with emails and phones."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        contact_list = [
            {
                "name": "John Smith",
                "title": "VP of Sales",
                "email": "john.smith@acmecorp.com",
                "phone": "555-123-4567",
                "notes": "Key decision maker",
            },
            {
                "name": "Jane Doe",
                "title": "Director of Procurement",
                "email": "jane.doe@acmecorp.com",
                "phone": "555-987-6543",
                "notes": "Budget holder, prefers email",
            },
        ]

        # VERIFIED skill can access INTERNAL but not CONFIDENTIAL
        sanitized, token_map = await sanitizer.sanitize(
            contact_list,
            SkillTrustLevel.VERIFIED,
        )

        # Names and titles are INTERNAL - accessible
        assert sanitized[0]["name"] == "John Smith"
        assert sanitized[1]["title"] == "Director of Procurement"

        # Emails and phones are CONFIDENTIAL - should be REDACTED
        assert "[REDACTED:" in sanitized[0]["email"]
        assert "[REDACTED:" in sanitized[0]["phone"]
        assert "[REDACTED:" in sanitized[1]["email"]

        # Notes don't contain sensitive patterns - unchanged
        assert sanitized[0]["notes"] == "Key decision maker"

        # Verify no leakage
        report = sanitizer.validate_output(sanitized, token_map)
        assert report.leaked is False
```

**Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestIntegrationScenarios::test_contact_list_scenario -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
test(security): add contact list integration test

Verifies email and phone sanitization for different trust levels.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Integration Tests - Deal Memo Scenario

**Files:**
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write integration test for deal memo**

```python
# Add to TestIntegrationScenarios class in backend/tests/test_sanitization.py

    @pytest.mark.asyncio
    async def test_deal_memo_scenario(self) -> None:
        """Test sanitizing a deal memo with pricing and terms."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        deal_memo = """
        DEAL MEMO - CONFIDENTIAL

        Customer: Acme Healthcare
        Contact: Sarah Johnson (sarah.johnson@acmehc.com)
        Phone: 555-234-5678

        Deal Summary:
        - Contract value: $2.5M over 3 years
        - Our pricing: $850K/year with 10% discount
        - Competitor pricing: BioTech offers at $750K/year
        - Expected revenue impact: +15% margin improvement

        Key Terms:
        - Net 60 payment terms
        - Annual price escalator of 3%
        - Exclusivity clause for 2 years

        Notes: Customer SSN for verification: 123-45-6789
        """

        # COMMUNITY skill - only PUBLIC access
        sanitized, token_map = await sanitizer.sanitize(
            deal_memo,
            SkillTrustLevel.COMMUNITY,
        )

        # All sensitive data should be redacted
        assert "sarah.johnson@acmehc.com" not in sanitized
        assert "555-234-5678" not in sanitized
        assert "$2.5M" not in sanitized
        assert "$850K" not in sanitized
        assert "123-45-6789" not in sanitized

        # SSN should be redacted (not tokenized)
        assert "[REDACTED:" in sanitized

        # CORE skill - full access except REGULATED
        sanitized_core, token_map_core = await sanitizer.sanitize(
            deal_memo,
            SkillTrustLevel.CORE,
        )

        # Financial data should be tokenized
        assert "[FINANCIAL_" in sanitized_core
        assert "[CONTACT_" in sanitized_core

        # SSN (REGULATED) should still be redacted for CORE
        assert "123-45-6789" not in sanitized_core
        assert "[REDACTED:" in sanitized_core  # SSN redaction

        # Verify detokenization restores financial and contact but not SSN
        restored = sanitizer.detokenize(sanitized_core, token_map_core)
        assert "$2.5M" in restored or "2.5M" in restored  # Financial restored
        assert "123-45-6789" not in restored  # SSN stays redacted
```

**Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestIntegrationScenarios::test_deal_memo_scenario -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
test(security): add deal memo integration test

Verifies mixed classification handling with pricing, contacts, and SSN.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Integration Tests - Mixed Classification Levels

**Files:**
- Modify: `backend/tests/test_sanitization.py`

**Step 1: Write integration test for mixed levels**

```python
# Add to TestIntegrationScenarios class in backend/tests/test_sanitization.py

    @pytest.mark.asyncio
    async def test_mixed_classification_levels(self) -> None:
        """Test data with multiple classification levels."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        mixed_data = {
            "public": {
                "company_name": "BioPharm Inc",
                "industry": "Life Sciences",
                "website": "https://biopharm.com",
            },
            "internal": {
                "strategy": "Focus on oncology market",
                "goals": "Increase market share by 20%",
            },
            "confidential": {
                "key_contact": "Dr. Smith (dr.smith@biopharm.com)",
                "phone": "555-111-2222",
            },
            "restricted": {
                "revenue": "$45M annually",
                "deal_pipeline": "$12M in active deals",
                "proprietary": "Novel drug delivery mechanism",
            },
            "regulated": {
                "patient_data": "Patient ID: 12345, diagnosis: stage 2",
                "ssn": "987-65-4321",
            },
        }

        # Test each trust level
        trust_levels = [
            (SkillTrustLevel.COMMUNITY, {"public"}),
            (SkillTrustLevel.USER, {"public", "internal"}),
            (SkillTrustLevel.VERIFIED, {"public", "internal"}),
            (SkillTrustLevel.CORE, {"public", "internal", "confidential", "restricted"}),
        ]

        for trust_level, accessible_categories in trust_levels:
            sanitized, token_map = await sanitizer.sanitize(mixed_data, trust_level)

            # Public data always accessible
            assert sanitized["public"]["company_name"] == "BioPharm Inc"

            # Check internal
            if "internal" in accessible_categories:
                assert sanitized["internal"]["strategy"] == "Focus on oncology market"
            else:
                # Should be unchanged (INTERNAL is not sensitive by pattern)
                pass

            # Check confidential
            if "confidential" in accessible_categories:
                assert "[CONTACT_" in sanitized["confidential"]["key_contact"]
            else:
                assert "[REDACTED:" in sanitized["confidential"]["key_contact"]

            # Check restricted
            if "restricted" in accessible_categories:
                assert "[FINANCIAL_" in str(sanitized["restricted"]["revenue"])
            else:
                assert "[REDACTED:" in str(sanitized["restricted"]["revenue"])

            # Regulated never accessible to any trust level
            assert "[REDACTED:" in sanitized["regulated"]["ssn"]
            assert "987-65-4321" not in str(sanitized)
```

**Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sanitization.py::TestIntegrationScenarios::test_mixed_classification_levels -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/test_sanitization.py
git commit -m "$(cat <<'EOF'
test(security): add mixed classification integration test

Verifies correct handling of all classification levels per trust tier.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Run Full Test Suite and Type Check

**Files:**
- None (verification only)

**Step 1: Run all sanitization tests**

Run: `cd backend && python -m pytest tests/test_sanitization.py -v`
Expected: All tests PASS

**Step 2: Run mypy type check**

Run: `cd backend && python -m mypy src/security/sanitization.py --strict`
Expected: No errors (or only minor ones to fix)

**Step 3: Run ruff linting**

Run: `cd backend && python -m ruff check src/security/sanitization.py`
Expected: No errors

**Step 4: Run ruff format**

Run: `cd backend && python -m ruff format src/security/sanitization.py`
Expected: File formatted

**Step 5: Final commit**

```bash
git add backend/src/security/sanitization.py
git commit -m "$(cat <<'EOF'
style(security): apply formatting and type hints to sanitization

Passes mypy strict mode and ruff checks.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Run Full Security Module Test Suite

**Files:**
- None (verification only)

**Step 1: Run all security tests**

Run: `cd backend && python -m pytest tests/test_data_classification.py tests/test_trust_levels.py tests/test_sanitization.py -v`
Expected: All tests PASS

**Step 2: Commit completion**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(security): complete US-522 data sanitization pipeline

Implements full sanitization pipeline for ARIA skill security:
- TokenMap for value-to-token mapping
- LeakageReport for output validation
- DataSanitizer with:
  - sanitize() for nested data structures
  - tokenize_value() and redact_value() methods
  - detokenize() for output restoration
  - validate_output() for leakage detection

Includes integration tests for:
- Financial reports with revenue figures
- Contact lists with emails/phones
- Deal memos with pricing and terms
- Mixed classification levels across trust tiers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements US-522 in 19 bite-sized tasks following TDD:

| Task | Description | Tests |
|------|-------------|-------|
| 1 | TokenMap skeleton | 1 |
| 2 | TokenMap.add_token() | 4 |
| 3 | TokenMap.get_original() | 3 |
| 4 | LeakageReport dataclass | 2 |
| 5 | DataSanitizer skeleton | 1 |
| 6 | tokenize_value() | 2 |
| 7 | redact_value() | 2 |
| 8 | sanitize() for strings | 4 |
| 9 | sanitize() for dicts | 2 |
| 10 | sanitize() for lists | 2 |
| 11 | detokenize() | 4 |
| 12 | validate_output() | 4 |
| 13 | Module exports | 3 |
| 14-17 | Integration tests | 4 |
| 18-19 | Verification | 0 |

**Total: ~38 test cases**

Each task follows the pattern:
1. Write failing test
2. Run to verify failure
3. Write minimal implementation
4. Run to verify pass
5. Commit
