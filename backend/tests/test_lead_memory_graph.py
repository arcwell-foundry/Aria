# backend/tests/test_lead_memory_graph.py
"""Tests for lead memory graph module."""

import pytest


def test_lead_memory_graph_error_exists() -> None:
    """Test LeadMemoryGraphError exception class exists."""
    from src.core.exceptions import LeadMemoryGraphError

    error = LeadMemoryGraphError("test error")
    assert "test error" in str(error)
    assert error.status_code == 500
    assert error.code == "LEAD_MEMORY_GRAPH_ERROR"


def test_lead_memory_not_found_error_exists() -> None:
    """Test LeadMemoryNotFoundError exception class exists."""
    from src.core.exceptions import LeadMemoryNotFoundError

    error = LeadMemoryNotFoundError("lead-123")
    assert "lead-123" in str(error)
    assert error.status_code == 404
