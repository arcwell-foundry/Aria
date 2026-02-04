"""Tests for Lead Memory audit enum."""


def test_memory_type_includes_lead() -> None:
    """Test MemoryType enum includes LEAD variant."""
    from src.memory.audit import MemoryType

    assert hasattr(MemoryType, "LEAD")
    assert MemoryType.LEAD.value == "lead"
