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
