"""Shared fixtures for MCP server tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.capability_tokens import DCTMinter, DelegationCapabilityToken


@pytest.fixture
def analyst_dct() -> DelegationCapabilityToken:
    """A valid DCT for the analyst agent."""
    minter = DCTMinter()
    return minter.mint("analyst", goal_id="test-goal", time_limit=300)


@pytest.fixture
def operator_dct() -> DelegationCapabilityToken:
    """A valid DCT for the operator agent."""
    minter = DCTMinter()
    return minter.mint("operator", goal_id="test-goal", time_limit=300)


@pytest.fixture
def scout_dct() -> DelegationCapabilityToken:
    """A valid DCT for the scout agent."""
    minter = DCTMinter()
    return minter.mint("scout", goal_id="test-goal", time_limit=300)


@pytest.fixture
def expired_dct() -> DelegationCapabilityToken:
    """A DCT that has already expired."""
    return DelegationCapabilityToken(
        token_id=str(uuid.uuid4()),
        delegatee="analyst",
        goal_id="test-goal",
        allowed_actions=["read_pubmed"],
        denied_actions=[],
        time_limit_seconds=0,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def mock_trace_service() -> AsyncMock:
    """A mock DelegationTraceService for testing trace lifecycle."""
    svc = AsyncMock()
    svc.start_trace = AsyncMock(return_value="trace-123")
    svc.complete_trace = AsyncMock()
    svc.fail_trace = AsyncMock()
    return svc


@pytest.fixture
def pubmed_search_response() -> dict[str, Any]:
    """Sample PubMed esearch response body."""
    return {
        "esearchresult": {
            "count": "42",
            "retmax": "20",
            "idlist": ["12345678", "87654321"],
        }
    }


@pytest.fixture
def pubmed_summary_response() -> dict[str, Any]:
    """Sample PubMed esummary response body."""
    return {
        "result": {
            "uids": ["12345678"],
            "12345678": {
                "uid": "12345678",
                "title": "CRISPR advances in oncology",
                "authors": [{"name": "Smith J"}],
            },
        }
    }
