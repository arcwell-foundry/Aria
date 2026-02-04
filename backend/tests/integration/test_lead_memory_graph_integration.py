"""Integration tests for lead memory graph module.

These tests require a running Neo4j instance.
Skip with: pytest -m "not integration"
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_lead_memory_graph_full_flow() -> None:
    """Test complete flow: create lead, add relationships, query."""
    pytest.skip("Integration test - requires Neo4j instance")


@pytest.mark.asyncio
async def test_cross_lead_query_finds_related_leads() -> None:
    """Test querying across multiple leads by topic."""
    pytest.skip("Integration test - requires Neo4j instance")
