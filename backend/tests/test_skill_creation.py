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


# ---------------------------------------------------------------------------
# SkillCreationEngine tests
# ---------------------------------------------------------------------------

class TestSkillCreationEngine:
    """Tests for SkillCreationEngine."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_assess_creation_prompt_chain(self, mock_db):
        """LLM assessment returns valid proposal for prompt-chain skill."""
        from src.services.skill_creation import SkillCreationEngine

        _setup_chain(mock_db, [])  # No tenant config

        engine = SkillCreationEngine(mock_db)

        # Mock LLM to return a valid assessment
        mock_llm_response = json.dumps({
            "can_create": True,
            "skill_type": "prompt_chain",
            "confidence": 0.8,
            "skill_name": "fda_drug_lookup",
            "description": "Look up FDA drug approvals using structured prompts",
            "estimated_quality": 0.75,
            "approach": "Chain prompts to search and parse FDA data",
            "public_api_url": None,
            "required_capabilities": [],
            "reason_if_no": None,
        })
        engine._generate = AsyncMock(return_value=mock_llm_response)

        proposal = await engine.assess_creation_opportunity(
            "track_fda_approvals",
            "Track recent FDA drug approvals",
            "user-1",
        )

        assert proposal is not None
        assert proposal.can_create is True
        assert proposal.skill_type == "prompt_chain"
        assert proposal.confidence == 0.8

    @pytest.mark.asyncio
    async def test_assess_creation_api_wrapper(self, mock_db):
        """Assessment identifies public API opportunity."""
        from src.services.skill_creation import SkillCreationEngine

        _setup_chain(mock_db, [])

        engine = SkillCreationEngine(mock_db)

        mock_llm_response = json.dumps({
            "can_create": True,
            "skill_type": "api_wrapper",
            "confidence": 0.85,
            "skill_name": "openfda_search",
            "description": "Search openFDA for drug adverse events",
            "estimated_quality": 0.80,
            "approach": "Wrap the openFDA API for adverse event queries",
            "public_api_url": "https://api.fda.gov/drug/event.json",
            "required_capabilities": [],
            "reason_if_no": None,
        })
        engine._generate = AsyncMock(return_value=mock_llm_response)

        proposal = await engine.assess_creation_opportunity(
            "search_fda_adverse_events",
            "Search FDA adverse event reports",
            "user-1",
        )

        assert proposal is not None
        assert proposal.skill_type == "api_wrapper"
        assert proposal.public_api_url == "https://api.fda.gov/drug/event.json"

    @pytest.mark.asyncio
    async def test_assess_creation_refuses_impossible(self, mock_db):
        """Returns None for impossible capability."""
        from src.services.skill_creation import SkillCreationEngine

        _setup_chain(mock_db, [])

        engine = SkillCreationEngine(mock_db)

        mock_llm_response = json.dumps({
            "can_create": False,
            "skill_type": "prompt_chain",
            "confidence": 0.1,
            "skill_name": "",
            "description": "",
            "estimated_quality": 0,
            "approach": "",
            "public_api_url": None,
            "required_capabilities": [],
            "reason_if_no": "No public API or data source exists for this",
        })
        engine._generate = AsyncMock(return_value=mock_llm_response)

        proposal = await engine.assess_creation_opportunity(
            "read_competitor_internal_financials",
            "Access competitor internal financial data",
            "user-1",
        )

        assert proposal is None

    @pytest.mark.asyncio
    async def test_create_prompt_chain_skill(self, mock_db):
        """Creates prompt chain skill, saves to aria_generated_skills table."""
        from src.services.skill_creation import SkillCreationEngine

        skill_row = {
            "id": "skill-001",
            "skill_name": "fda_drug_lookup",
            "display_name": "Fda Drug Lookup",
            "status": "draft",
            "trust_level": "LOW",
        }
        _setup_chain(mock_db, [skill_row])

        engine = SkillCreationEngine(mock_db)

        # Mock LLM to return a prompt chain definition
        chain_def = json.dumps({
            "steps": [
                {
                    "name": "search_fda",
                    "prompt": "Search for {drug_name} in FDA database...",
                    "output_schema": {"drug_info": "object"},
                    "capability_required": None,
                    "input_from": None,
                }
            ],
            "input_schema": {"drug_name": "string"},
            "output_schema": {"drug_info": "object"},
        })
        engine._generate = AsyncMock(return_value=chain_def)

        proposal = SkillCreationProposal(
            can_create=True,
            skill_type="prompt_chain",
            confidence=0.8,
            skill_name="fda_drug_lookup",
            description="Look up FDA drug approvals",
            estimated_quality=0.75,
            approach="Chain prompts",
        )

        skill = await engine.create_skill(proposal, "user-1", "tenant-1")

        assert skill["id"] == "skill-001"
        # Verify insert was called on the DB
        mock_db.table.assert_any_call("aria_generated_skills")

    @pytest.mark.asyncio
    async def test_create_api_wrapper_skill(self, mock_db):
        """Creates API wrapper skill with code and code_hash."""
        from src.services.skill_creation import SkillCreationEngine

        skill_row = {
            "id": "skill-002",
            "skill_name": "openfda_search",
            "display_name": "Openfda Search",
            "status": "draft",
            "trust_level": "LOW",
            "generated_code": "async def execute(data): pass",
            "code_hash": "abc123",
        }
        _setup_chain(mock_db, [skill_row])

        engine = SkillCreationEngine(mock_db)

        wrapper_def = json.dumps({
            "code": "async def execute(data):\n    return {'results': []}",
            "api_url": "https://api.fda.gov/drug/event.json",
            "allowed_domains": ["api.fda.gov"],
            "input_schema": {"query": "string"},
            "output_schema": {"results": "array"},
            "test_input": {"query": "aspirin"},
        })
        engine._generate = AsyncMock(return_value=wrapper_def)

        proposal = SkillCreationProposal(
            can_create=True,
            skill_type="api_wrapper",
            confidence=0.85,
            skill_name="openfda_search",
            description="Search openFDA",
            estimated_quality=0.80,
            approach="Wrap openFDA API",
            public_api_url="https://api.fda.gov/drug/event.json",
        )

        skill = await engine.create_skill(proposal, "user-1", "tenant-1")

        assert skill["id"] == "skill-002"
        # Verify DB insert included code hash
        insert_call = None
        for call in mock_db.table.return_value.insert.call_args_list:
            if call[0]:
                insert_call = call[0][0]
        assert insert_call is not None
        assert insert_call.get("generated_code") is not None
        assert insert_call.get("code_hash") is not None

    @pytest.mark.asyncio
    async def test_sandbox_test_prompt_chain(self, mock_db):
        """Runs prompt chain against test data in sandbox."""
        from src.services.skill_creation import SkillCreationEngine

        skill_record = {
            "id": "skill-001",
            "skill_type": "prompt_chain",
            "definition": {
                "steps": [
                    {
                        "name": "analyze",
                        "prompt": "Analyze {topic} and return JSON: {\"summary\": \"...\"}",
                        "output_schema": {"summary": "string"},
                        "capability_required": None,
                        "input_from": None,
                    }
                ],
                "input_schema": {"topic": "string"},
                "output_schema": {"summary": "string"},
            },
            "status": "draft",
        }

        # Mock DB: single() for skill fetch, then update()
        chain = _setup_chain(mock_db, skill_record)
        chain.single.return_value = chain
        chain.execute.return_value = _mock_db_response(skill_record)

        engine = SkillCreationEngine(mock_db)
        engine._generate = AsyncMock(return_value='{"summary": "Test analysis complete"}')

        result = await engine.test_skill_in_sandbox(
            "skill-001", {"topic": "clinical trials"}
        )

        assert result["passed"] is True
        assert result["errors"] == []
        assert result["execution_time_ms"] >= 0
