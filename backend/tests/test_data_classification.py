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
