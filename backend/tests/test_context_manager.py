"""Tests for skill context manager."""

import pytest


def test_summary_verbosity_enum_has_three_levels() -> None:
    """Test SummaryVerbosity enum has MINIMAL, STANDARD, DETAILED."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.MINIMAL.value == "minimal"
    assert SummaryVerbosity.STANDARD.value == "standard"
    assert SummaryVerbosity.DETAILED.value == "detailed"
    assert len(SummaryVerbosity) == 3


def test_summary_verbosity_minimal_has_token_target() -> None:
    """Test MINIMAL verbosity has 300 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.MINIMAL.token_target == 300


def test_summary_verbosity_standard_has_token_target() -> None:
    """Test STANDARD verbosity has 800 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.STANDARD.token_target == 800


def test_summary_verbosity_detailed_has_token_target() -> None:
    """Test DETAILED verbosity has 1500 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.DETAILED.token_target == 1500


def test_context_allocation_dataclass_initializes() -> None:
    """Test ContextAllocation initializes with all fields."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="skill_index",
        allocated_tokens=600,
        used_tokens=450,
        content="# Skill summaries\n...",
    )

    assert allocation.component == "skill_index"
    assert allocation.allocated_tokens == 600
    assert allocation.used_tokens == 450
    assert allocation.content == "# Skill summaries\n..."


def test_context_allocation_has_remaining_tokens_property() -> None:
    """Test ContextAllocation.remaining_tokens returns correct value."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="working_memory",
        allocated_tokens=800,
        used_tokens=350,
        content="Some content",
    )

    assert allocation.remaining_tokens == 450


def test_context_allocation_remaining_tokens_when_over() -> None:
    """Test remaining_tokens returns 0 when over budget."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="over_budget",
        allocated_tokens=100,
        used_tokens=150,
        content="Too much content",
    )

    assert allocation.remaining_tokens == 0


def test_context_allocation_is_over_budget_property() -> None:
    """Test is_over_budget returns correct boolean."""
    from src.skills.context_manager import ContextAllocation

    under = ContextAllocation(
        component="under",
        allocated_tokens=100,
        used_tokens=50,
        content="OK",
    )

    over = ContextAllocation(
        component="over",
        allocated_tokens=100,
        used_tokens=150,
        content="Too much",
    )

    assert under.is_over_budget is False
    assert over.is_over_budget is True
