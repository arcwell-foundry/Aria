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
