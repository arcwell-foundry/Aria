"""Tests for AnalystAgent module."""

from unittest.mock import MagicMock

import pytest


def test_analyst_agent_has_name_and_description() -> None:
    """Test AnalystAgent has correct name and description class attributes."""
    from src.agents.analyst import AnalystAgent

    assert AnalystAgent.name == "Analyst"
    assert AnalystAgent.description == "Scientific research agent for life sciences queries"


def test_analyst_agent_extends_base_agent() -> None:
    """Test AnalystAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.analyst import AnalystAgent

    assert issubclass(AnalystAgent, BaseAgent)