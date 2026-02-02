"""Tests for OperatorAgent module."""

import pytest
from unittest.mock import MagicMock


def test_operator_agent_has_name_and_description() -> None:
    """Test OperatorAgent has correct name and description class attributes."""
    from src.agents.operator import OperatorAgent

    assert OperatorAgent.name == "Operator"
    assert OperatorAgent.description == "System operations for calendar, CRM, and integrations"
