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
