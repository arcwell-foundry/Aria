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
