"""Tests for Phase B: Ecosystem Search, Skill Creation, Trust & Health."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.capability import (
    EcosystemResult,
    ResolutionStrategy,
    SkillCreationProposal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_response(data: list[dict] | None = None):
    """Build a mock Supabase response object."""
    resp = MagicMock()
    resp.data = data or []
    return resp


def _setup_chain(db, data):
    """Wire up the chainable .table().select().eq().order().execute() pattern."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.gt.return_value = chain
    chain.gte.return_value = chain
    chain.lt.return_value = chain
    chain.in_.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.single.return_value = chain
    chain.maybe_single.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.upsert.return_value = chain
    chain.delete.return_value = chain
    chain.execute.return_value = _mock_db_response(data)
    db.table.return_value = chain
    return chain


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------

class TestSkillCreationModels:
    """Validate Pydantic models for Phase B."""

    def test_ecosystem_result_valid(self):
        r = EcosystemResult(
            name="Salesforce",
            source="composio",
            description="CRM pipeline data",
            quality_estimate=0.85,
        )
        assert r.name == "Salesforce"
        assert r.source == "composio"

    def test_skill_creation_proposal_valid(self):
        p = SkillCreationProposal(
            can_create=True,
            skill_type="prompt_chain",
            confidence=0.8,
            skill_name="fda_drug_lookup",
            description="Look up FDA drug approvals",
            estimated_quality=0.75,
            approach="Use openFDA API",
        )
        assert p.can_create is True
        assert p.skill_type == "prompt_chain"
        assert p.confidence == 0.8


# ---------------------------------------------------------------------------
# EcosystemSearchService tests
# ---------------------------------------------------------------------------

class TestEcosystemSearchService:
    """Tests for EcosystemSearchService."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_ecosystem_search_composio_static(self, mock_db):
        """Composio static search returns results with correct structure."""
        from src.services.ecosystem_search import EcosystemSearchService

        _setup_chain(mock_db, [])  # No cache

        tenant_config = SimpleNamespace(
            allowed_ecosystem_sources=["composio"],
        )
        service = EcosystemSearchService(mock_db, tenant_config=tenant_config)

        results = await service.search_for_capability(
            "read_crm_pipeline",
            "CRM pipeline data access",
            "user-1",
        )

        assert len(results) > 0
        for r in results:
            assert r.source == "composio"
            assert r.name
            assert 0 <= r.quality_estimate <= 1

    @pytest.mark.asyncio
    async def test_ecosystem_search_cache(self, mock_db):
        """Second search uses cache, not network."""
        from src.services.ecosystem_search import EcosystemSearchService

        tenant_config = SimpleNamespace(
            allowed_ecosystem_sources=["composio"],
        )
        service = EcosystemSearchService(mock_db, tenant_config=tenant_config)

        # First call: no cache → searches
        _setup_chain(mock_db, [])
        results1 = await service.search_for_capability(
            "read_crm_pipeline", "CRM", "user-1"
        )

        # Second call: cache hit → returns cached results
        cached_rows = [{
            "search_source": "composio",
            "results": [{"name": "Salesforce", "source": "composio", "description": "CRM", "quality_estimate": 0.85}],
        }]
        _setup_chain(mock_db, cached_rows)

        results2 = await service.search_for_capability(
            "read_crm_pipeline", "CRM", "user-1"
        )

        assert len(results2) > 0
        # Cached results have the data from the mock
        assert results2[0].name == "Salesforce"

    @pytest.mark.asyncio
    async def test_ecosystem_search_tenant_whitelist(self, mock_db):
        """Restricted tenant only gets allowed sources."""
        from src.services.ecosystem_search import EcosystemSearchService

        _setup_chain(mock_db, [])

        tenant_config = SimpleNamespace(
            allowed_ecosystem_sources=["composio"],  # Only Composio
        )
        service = EcosystemSearchService(mock_db, tenant_config=tenant_config)

        results = await service.search_for_capability(
            "read_crm_pipeline", "CRM", "user-1"
        )

        # All results must be from composio (not mcp_registry or smithery)
        for r in results:
            assert r.source == "composio"
