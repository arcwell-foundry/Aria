"""Tests for agents module exports."""


def test_scout_agent_is_exported() -> None:
    """Test ScoutAgent is exported from agents module."""
    from src.agents import ScoutAgent

    assert ScoutAgent is not None
    assert ScoutAgent.name == "Scout"


def test_all_agents_includes_scout() -> None:
    """Test __all__ includes ScoutAgent."""
    from src.agents import __all__

    assert "ScoutAgent" in __all__
