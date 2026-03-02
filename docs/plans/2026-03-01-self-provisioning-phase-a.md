# ARIA Self-Provisioning: Phase A Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the capability graph, gap detection engine, resolution strategy generator, and provisioning conversation so ARIA can reason about her own capabilities, detect missing integrations during goal planning, and present resolution options in natural chat.

**Architecture:** A `capability_graph` table acts as ARIA's self-knowledge about what she can do. When the SkillOrchestrator builds an execution plan, a GapDetectionService checks each step's required capabilities against the graph and the user's active integrations. Missing or degraded capabilities produce ranked resolution strategies (connect via OAuth, use composite fallback, ask user). The ProvisioningConversation formats these as natural chat messages. Demand tracking feeds the Pulse Engine for proactive suggestions.

**Tech Stack:** Python 3.11+ / FastAPI / Supabase (PostgreSQL) / Pydantic / APScheduler / Anthropic Claude API (Haiku for inference)

---

## Task 1: Database Migration — Tables

**Files:**
- Create: `backend/supabase/migrations/20260301100000_self_provisioning.sql`

**Step 1: Write the migration SQL for all 4 tables**

Create the migration file with `capability_graph`, `capability_gaps_log`, `capability_demand`, and `tenant_capability_config` tables. All tables get RLS policies.

```sql
-- Self-Provisioning: Phase A — Capability Graph + Gap Detection
-- Tables: capability_graph, capability_gaps_log, capability_demand, tenant_capability_config

-- ============================================================
-- Table 1: capability_graph (seed data — shared across all tenants)
-- Maps abstract capabilities to concrete providers
-- ============================================================
CREATE TABLE IF NOT EXISTS capability_graph (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Abstract capability
    capability_name TEXT NOT NULL,
    capability_category TEXT NOT NULL CHECK (capability_category IN (
        'research', 'data_access', 'communication', 'monitoring', 'analysis', 'creation'
    )),
    description TEXT,

    -- Concrete provider
    provider_name TEXT NOT NULL,
    provider_type TEXT NOT NULL CHECK (provider_type IN (
        'native',
        'composio_oauth',
        'composio_api_key',
        'composite',
        'mcp_server',
        'user_provided'
    )),

    -- Quality and availability
    quality_score FLOAT NOT NULL CHECK (quality_score >= 0 AND quality_score <= 1),
    setup_time_seconds INT DEFAULT 0,
    user_friction TEXT DEFAULT 'none' CHECK (user_friction IN ('none', 'low', 'medium', 'high')),
    estimated_cost_per_use FLOAT DEFAULT 0,

    -- Auth requirements
    composio_app_name TEXT,
    composio_action_name TEXT,
    required_capabilities TEXT[],

    -- Domain and constraints
    domain_constraint TEXT,
    limitations TEXT,
    life_sciences_priority BOOLEAN DEFAULT FALSE,

    -- Provider health
    is_active BOOLEAN DEFAULT TRUE,
    last_health_check TIMESTAMPTZ,
    health_status TEXT DEFAULT 'unknown' CHECK (health_status IN ('healthy', 'degraded', 'down', 'unknown')),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(capability_name, provider_name)
);

CREATE INDEX IF NOT EXISTS idx_capgraph_capability ON capability_graph(capability_name);
CREATE INDEX IF NOT EXISTS idx_capgraph_category ON capability_graph(capability_category);
CREATE INDEX IF NOT EXISTS idx_capgraph_composio ON capability_graph(composio_app_name) WHERE composio_app_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_capgraph_active ON capability_graph(capability_name, quality_score DESC) WHERE is_active = TRUE;

ALTER TABLE capability_graph ENABLE ROW LEVEL SECURITY;
CREATE POLICY "capability_graph_read" ON capability_graph
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "capability_graph_service" ON capability_graph
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 2: capability_gaps_log (per-user gap tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS capability_gaps_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,

    capability_name TEXT NOT NULL,
    goal_id UUID REFERENCES goals(id) ON DELETE SET NULL,
    goal_type TEXT,
    step_description TEXT,

    best_available_provider TEXT,
    best_available_quality FLOAT,

    strategies_offered JSONB,

    resolution_strategy TEXT CHECK (resolution_strategy IN (
        'direct_integration', 'composite', 'ecosystem_discovered',
        'skill_created', 'user_provided', 'web_fallback', 'skipped'
    )),
    resolution_provider TEXT,
    resolution_quality FLOAT,

    user_response TEXT CHECK (user_response IN (
        'connected', 'used_fallback', 'dismissed', 'deferred', 'pending'
    )),

    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_capgaps_user ON capability_gaps_log(user_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_capgaps_capability ON capability_gaps_log(capability_name);
CREATE INDEX IF NOT EXISTS idx_capgaps_unresolved ON capability_gaps_log(user_id) WHERE user_response = 'pending';

ALTER TABLE capability_gaps_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "capgaps_own" ON capability_gaps_log
    FOR ALL TO authenticated USING (user_id = auth.uid());
CREATE POLICY "capgaps_service" ON capability_gaps_log
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 3: capability_demand (aggregate learning per user)
-- ============================================================
CREATE TABLE IF NOT EXISTS capability_demand (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,

    capability_name TEXT NOT NULL,
    goal_type TEXT,

    times_needed INT DEFAULT 0,
    times_satisfied_directly INT DEFAULT 0,
    times_used_composite INT DEFAULT 0,
    times_used_fallback INT DEFAULT 0,

    avg_quality_achieved FLOAT,
    quality_with_ideal_provider FLOAT,

    suggestion_threshold_reached BOOLEAN DEFAULT FALSE,
    last_suggested_at TIMESTAMPTZ,
    suggestion_accepted BOOLEAN,

    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, capability_name, goal_type)
);

CREATE INDEX IF NOT EXISTS idx_capdemand_user ON capability_demand(user_id);
CREATE INDEX IF NOT EXISTS idx_capdemand_suggest ON capability_demand(user_id)
    WHERE suggestion_threshold_reached = FALSE AND times_needed >= 3;

ALTER TABLE capability_demand ENABLE ROW LEVEL SECURITY;
CREATE POLICY "capdemand_own" ON capability_demand
    FOR ALL TO authenticated USING (user_id = auth.uid());
CREATE POLICY "capdemand_service" ON capability_demand
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 4: tenant_capability_config (enterprise governance)
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_capability_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,

    allowed_composio_toolkits TEXT[],
    allowed_ecosystem_sources TEXT[] DEFAULT ARRAY['composio'],

    allow_skill_creation BOOLEAN DEFAULT TRUE,
    skill_creation_requires_admin_approval BOOLEAN DEFAULT TRUE,
    max_auto_trust_level TEXT DEFAULT 'MEDIUM' CHECK (max_auto_trust_level IN ('LOW', 'MEDIUM', 'HIGH')),

    allow_data_to_community_tools BOOLEAN DEFAULT FALSE,
    max_data_classification_external TEXT DEFAULT 'INTERNAL' CHECK (
        max_data_classification_external IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL')
    ),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id)
);

ALTER TABLE tenant_capability_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tenantcap_service" ON tenant_capability_config
    FOR ALL USING (auth.role() = 'service_role');
```

**Step 2: Add seed data to the migration**

Append to the same migration file. Each INSERT must match the column order of `capability_graph` exactly. Native and user_provided providers leave `composio_app_name`, `composio_action_name`, and `required_capabilities` as NULL. Composio providers fill in those fields.

```sql
-- ============================================================
-- Seed: Day-1 Capability Map
-- ============================================================

-- RESEARCH CAPABILITIES
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority) VALUES
('research_person', 'research', 'exa_people_search', 'native', 0.80, 'Search for person background via Exa web search', NULL, FALSE),
('research_person', 'research', 'pubmed_author_search', 'native', 0.70, 'Search PubMed for scientific author publications', 'scientific', TRUE),
('research_person', 'research', 'ask_user', 'user_provided', 0.40, 'Ask user directly for information about a person', NULL, FALSE),
('research_company', 'research', 'exa_company_search', 'native', 0.85, 'Search for company information via Exa', NULL, FALSE),
('research_company', 'research', 'memory_corporate_facts', 'native', 0.60, 'Check ARIA corporate memory for known facts', NULL, FALSE),
('research_company', 'research', 'ask_user', 'user_provided', 0.40, 'Ask user directly about the company', NULL, FALSE),
('research_scientific', 'research', 'pubmed_api', 'native', 0.90, 'Search PubMed for scientific literature', 'scientific', TRUE),
('research_scientific', 'research', 'clinicaltrials_gov', 'native', 0.90, 'Search ClinicalTrials.gov for trial data', 'scientific', TRUE),
('research_scientific', 'research', 'exa_web_search', 'native', 0.70, 'General web search for scientific topics', NULL, FALSE);

-- DATA ACCESS CAPABILITIES (Composio OAuth)
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority, setup_time_seconds, user_friction, estimated_cost_per_use, composio_app_name, composio_action_name, required_capabilities) VALUES
('read_email', 'data_access', 'composio_outlook', 'composio_oauth', 0.95, 'Read emails via Microsoft Outlook', NULL, FALSE, 0, 'low', 0, 'OUTLOOK365', 'OUTLOOK365_READ_EMAILS', NULL),
('read_email', 'data_access', 'composio_gmail', 'composio_oauth', 0.95, 'Read emails via Gmail', NULL, FALSE, 0, 'low', 0, 'GMAIL', 'GMAIL_FETCH_EMAILS', NULL),
('read_crm_pipeline', 'data_access', 'composio_veeva', 'composio_oauth', 0.95, 'Read CRM pipeline from Veeva CRM', NULL, TRUE, 0, 'low', 0, 'VEEVA_CRM', NULL, NULL),
('read_crm_pipeline', 'data_access', 'composio_salesforce', 'composio_oauth', 0.95, 'Read CRM pipeline from Salesforce', NULL, FALSE, 0, 'low', 0, 'SALESFORCE', 'SALESFORCE_GET_OPPORTUNITIES', NULL),
('read_crm_pipeline', 'data_access', 'composio_hubspot', 'composio_oauth', 0.95, 'Read CRM pipeline from HubSpot', NULL, FALSE, 0, 'low', 0, 'HUBSPOT', 'HUBSPOT_GET_DEALS', NULL),
('read_crm_pipeline', 'data_access', 'email_deal_inference', 'composite', 0.65, 'Infer deal stages from email thread language patterns', NULL, FALSE, 0, 'none', 0.05, NULL, NULL, ARRAY['read_email']),
('read_crm_pipeline', 'data_access', 'user_stated', 'user_provided', 0.50, 'Ask user about current pipeline status', NULL, FALSE, 0, 'medium', 0, NULL, NULL, NULL),
('read_calendar', 'data_access', 'composio_google_calendar', 'composio_oauth', 0.95, 'Read Google Calendar events', NULL, FALSE, 0, 'low', 0, 'GOOGLE_CALENDAR', NULL, NULL),
('read_calendar', 'data_access', 'composio_outlook_calendar', 'composio_oauth', 0.95, 'Read Outlook Calendar events', NULL, FALSE, 0, 'low', 0, 'OUTLOOK365', NULL, NULL),
('read_calendar', 'data_access', 'ask_user', 'user_provided', 0.40, 'Ask user about upcoming meetings', NULL, FALSE, 0, 'medium', 0, NULL, NULL, NULL);

-- COMMUNICATION CAPABILITIES
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority, setup_time_seconds, user_friction, estimated_cost_per_use, composio_app_name, composio_action_name, required_capabilities) VALUES
('send_email', 'communication', 'composio_outlook', 'composio_oauth', 0.95, 'Send emails via Outlook', NULL, FALSE, 0, 'low', 0, 'OUTLOOK365', 'OUTLOOK365_SEND_EMAIL', NULL),
('send_email', 'communication', 'composio_gmail', 'composio_oauth', 0.95, 'Send emails via Gmail', NULL, FALSE, 0, 'low', 0, 'GMAIL', 'GMAIL_SEND_EMAIL', NULL);

INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority) VALUES
('send_email', 'communication', 'resend_transactional', 'native', 0.70, 'Send transactional emails via Resend (no reply tracking)', NULL, FALSE),
('send_email', 'communication', 'draft_for_user', 'native', 0.30, 'Generate draft text for user to copy-paste', NULL, FALSE);

-- MONITORING CAPABILITIES
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority) VALUES
('monitor_competitor', 'monitoring', 'exa_web_search', 'native', 0.75, 'Monitor competitor news via Exa web search', NULL, FALSE),
('monitor_competitor', 'monitoring', 'exa_company_news', 'native', 0.70, 'Track company-specific news feed', NULL, FALSE),
('track_fda_activity', 'monitoring', 'openfda_api', 'native', 0.85, 'Track FDA approvals, recalls, warnings via openFDA', 'life_sciences', TRUE),
('track_fda_activity', 'monitoring', 'clinicaltrials_gov', 'native', 0.80, 'Monitor clinical trial status changes', 'life_sciences', TRUE),
('track_fda_activity', 'monitoring', 'exa_regulatory_search', 'native', 0.70, 'Search web for regulatory news', NULL, FALSE),
('track_patents', 'monitoring', 'exa_web_search', 'native', 0.60, 'Search web for patent filings (limited accuracy)', NULL, FALSE);
```

**Step 3: Apply the migration**

Run:
```bash
cd /Users/dhruv/aria && npx supabase db push --linked 2>&1 | tail -20
```
If `supabase` CLI is not available, apply via direct SQL execution against the Supabase project using the MCP `mcp__supabase__query` tool, splitting the migration into individual statements.

Expected: All 4 tables created, seed data inserted, indexes and RLS policies applied.

**Step 4: Verify tables exist**

Run via `mcp__supabase__query`:
```sql
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('capability_graph', 'capability_gaps_log', 'capability_demand', 'tenant_capability_config') ORDER BY table_name;
```
Expected: 4 rows returned.

Verify seed data:
```sql
SELECT capability_name, COUNT(*) as provider_count FROM capability_graph GROUP BY capability_name ORDER BY capability_name;
```
Expected: ~10 capability names with varying provider counts.

**Step 5: Commit**

```bash
git add backend/supabase/migrations/20260301100000_self_provisioning.sql
git commit -m "feat: add self-provisioning database schema and seed capability graph

Create 4 tables for ARIA self-provisioning:
- capability_graph: maps abstract capabilities to concrete providers
- capability_gaps_log: per-user gap tracking during goal execution
- capability_demand: aggregate usage patterns for proactive suggestions
- tenant_capability_config: enterprise governance controls

Seed capability_graph with day-1 providers across research, data access,
communication, and monitoring categories. All tables have RLS policies.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Pydantic Data Models

**Files:**
- Create: `backend/src/models/capability.py`

**Step 1: Write the failing test**

Create `backend/tests/test_capability_models.py`:

```python
"""Tests for capability provisioning Pydantic models."""

import pytest
from src.models.capability import (
    CapabilityGap,
    CapabilityProvider,
    ResolutionStrategy,
)


class TestCapabilityProvider:
    def test_native_provider_construction(self):
        provider = CapabilityProvider(
            id="test-id",
            capability_name="research_person",
            capability_category="research",
            provider_name="exa_people_search",
            provider_type="native",
            quality_score=0.80,
        )
        assert provider.capability_name == "research_person"
        assert provider.provider_type == "native"
        assert provider.quality_score == 0.80
        assert provider.composio_app_name is None
        assert provider.is_active is True

    def test_composio_provider_construction(self):
        provider = CapabilityProvider(
            id="test-id",
            capability_name="read_email",
            capability_category="data_access",
            provider_name="composio_outlook",
            provider_type="composio_oauth",
            quality_score=0.95,
            composio_app_name="OUTLOOK365",
            composio_action_name="OUTLOOK365_READ_EMAILS",
        )
        assert provider.composio_app_name == "OUTLOOK365"
        assert provider.composio_action_name == "OUTLOOK365_READ_EMAILS"

    def test_composite_provider_construction(self):
        provider = CapabilityProvider(
            id="test-id",
            capability_name="read_crm_pipeline",
            capability_category="data_access",
            provider_name="email_deal_inference",
            provider_type="composite",
            quality_score=0.65,
            required_capabilities=["read_email"],
        )
        assert provider.required_capabilities == ["read_email"]


class TestResolutionStrategy:
    def test_direct_integration_strategy(self):
        strategy = ResolutionStrategy(
            strategy_type="direct_integration",
            provider_name="composio_outlook",
            quality=0.95,
            composio_app="OUTLOOK365",
            description="Connect Outlook",
            action_label="Connect OUTLOOK365",
        )
        assert strategy.strategy_type == "direct_integration"
        assert strategy.auto_usable is False

    def test_composite_auto_usable(self):
        strategy = ResolutionStrategy(
            strategy_type="composite",
            provider_name="email_deal_inference",
            quality=0.65,
            auto_usable=True,
        )
        assert strategy.auto_usable is True


class TestCapabilityGap:
    def test_blocking_gap(self):
        gap = CapabilityGap(
            capability="read_crm_pipeline",
            step={"description": "Check pipeline"},
            severity="blocking",
        )
        assert gap.severity == "blocking"
        assert gap.can_proceed is False
        assert gap.current_quality == 0

    def test_degraded_gap_with_resolutions(self):
        strategy = ResolutionStrategy(
            strategy_type="direct_integration",
            provider_name="composio_salesforce",
            quality=0.95,
            composio_app="SALESFORCE",
        )
        gap = CapabilityGap(
            capability="read_crm_pipeline",
            step={"description": "Check pipeline"},
            severity="degraded",
            current_provider="user_stated",
            current_quality=0.50,
            can_proceed=True,
            resolutions=[strategy],
        )
        assert gap.can_proceed is True
        assert len(gap.resolutions) == 1

    def test_gap_to_dict(self):
        gap = CapabilityGap(
            capability="read_email",
            step={"description": "Read inbox"},
            severity="blocking",
        )
        d = gap.model_dump()
        assert d["capability"] == "read_email"
        assert d["severity"] == "blocking"
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_models.py -v 2>&1 | tail -20
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.models.capability'`

**Step 3: Write the models**

Create `backend/src/models/capability.py`:

```python
"""Pydantic models for ARIA's self-provisioning capability system.

Defines the data structures for capability providers, gaps, and resolution
strategies used by CapabilityGraphService, GapDetectionService, and
ProvisioningConversation.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CapabilityProvider(BaseModel):
    """A concrete provider that can fulfill an abstract capability."""

    id: str
    capability_name: str
    capability_category: str
    provider_name: str
    provider_type: str  # native, composio_oauth, composio_api_key, composite, mcp_server, user_provided
    quality_score: float = Field(ge=0, le=1)
    setup_time_seconds: int = 0
    user_friction: str = "none"
    estimated_cost_per_use: float = 0
    composio_app_name: Optional[str] = None
    composio_action_name: Optional[str] = None
    required_capabilities: Optional[list[str]] = None
    domain_constraint: Optional[str] = None
    limitations: Optional[str] = None
    life_sciences_priority: bool = False
    is_active: bool = True
    health_status: str = "unknown"


class ResolutionStrategy(BaseModel):
    """A ranked strategy for filling a capability gap."""

    strategy_type: str  # direct_integration, composite, ecosystem_discovered, skill_created, user_provided, web_fallback
    provider_name: str
    quality: float = Field(ge=0, le=1)
    setup_time_seconds: int = 0
    user_friction: str = "none"
    estimated_cost_per_use: float = 0
    composio_app: Optional[str] = None
    description: str = ""
    action_label: str = ""
    auto_usable: bool = False
    ecosystem_source: Optional[str] = None
    ecosystem_data: Optional[dict[str, Any]] = None


class CapabilityGap(BaseModel):
    """A detected gap between what a goal step needs and what is available."""

    capability: str
    step: dict[str, Any]
    severity: str  # blocking, degraded
    current_provider: Optional[str] = None
    current_quality: float = 0
    can_proceed: bool = False
    auto_resolved: bool = False
    resolved_with: Optional[ResolutionStrategy] = None
    resolutions: list[ResolutionStrategy] = Field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_models.py -v 2>&1 | tail -20
```
Expected: All 7 tests PASS.

**Step 5: Commit**

```bash
git add backend/src/models/capability.py backend/tests/test_capability_models.py
git commit -m "feat: add Pydantic models for capability provisioning system

CapabilityProvider, ResolutionStrategy, and CapabilityGap models define
the data structures for self-provisioning gap detection and resolution.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: CapabilityGraphService — Core Graph Queries

**Files:**
- Create: `backend/src/services/capability_provisioning.py`
- Test: `backend/tests/test_capability_provisioning.py`

**Step 1: Write failing tests for CapabilityGraphService**

Create `backend/tests/test_capability_provisioning.py`:

```python
"""Tests for capability provisioning services."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.capability import CapabilityGap, CapabilityProvider, ResolutionStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_response(data: list[dict] | None = None):
    """Build a mock Supabase response object."""
    resp = MagicMock()
    resp.data = data or []
    return resp


def _make_provider_row(
    capability_name: str,
    provider_name: str,
    provider_type: str,
    quality_score: float,
    composio_app_name: str | None = None,
    composio_action_name: str | None = None,
    required_capabilities: list[str] | None = None,
    **kwargs,
) -> dict:
    """Build a dict that looks like a capability_graph row."""
    row = {
        "id": f"id-{provider_name}",
        "capability_name": capability_name,
        "capability_category": kwargs.get("capability_category", "research"),
        "description": kwargs.get("description", ""),
        "provider_name": provider_name,
        "provider_type": provider_type,
        "quality_score": quality_score,
        "setup_time_seconds": kwargs.get("setup_time_seconds", 0),
        "user_friction": kwargs.get("user_friction", "none"),
        "estimated_cost_per_use": kwargs.get("estimated_cost_per_use", 0),
        "composio_app_name": composio_app_name,
        "composio_action_name": composio_action_name,
        "required_capabilities": required_capabilities,
        "domain_constraint": kwargs.get("domain_constraint"),
        "limitations": kwargs.get("limitations"),
        "life_sciences_priority": kwargs.get("life_sciences_priority", False),
        "is_active": True,
        "health_status": "unknown",
    }
    return row


# ---------------------------------------------------------------------------
# CapabilityGraphService tests
# ---------------------------------------------------------------------------

class TestCapabilityGraphService:
    """Tests for CapabilityGraphService.get_best_available()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock Supabase client with chainable query builder."""
        db = MagicMock()
        return db

    def _setup_chain(self, db, data):
        """Wire up the chainable .table().select().eq().order().execute() pattern."""
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = _mock_db_response(data)
        db.table.return_value = chain
        return chain

    @pytest.mark.asyncio
    async def test_get_best_available_native(self, mock_db):
        """Native provider always returns as available."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row("research_person", "exa_people_search", "native", 0.80),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)
        result = await service.get_best_available("research_person", "user-1")

        assert result is not None
        assert result.provider_name == "exa_people_search"
        assert result.provider_type == "native"

    @pytest.mark.asyncio
    async def test_get_best_available_composio_connected(self, mock_db):
        """Returns composio provider when user has active connection."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock _check_user_connection to return True
        service._check_user_connection = AsyncMock(return_value=True)

        result = await service.get_best_available("read_email", "user-1")

        assert result is not None
        assert result.provider_name == "composio_outlook"

    @pytest.mark.asyncio
    async def test_get_best_available_composio_not_connected(self, mock_db):
        """Skips composio provider when not connected, falls back to next."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "send_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="communication",
            ),
            _make_provider_row(
                "send_email", "resend_transactional", "native", 0.70,
                capability_category="communication",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)
        service._check_user_connection = AsyncMock(return_value=False)

        result = await service.get_best_available("send_email", "user-1")

        assert result is not None
        assert result.provider_name == "resend_transactional"
        assert result.provider_type == "native"

    @pytest.mark.asyncio
    async def test_get_best_available_composite(self, mock_db):
        """Returns composite provider when all sub-capabilities are available."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_crm_pipeline", "email_deal_inference", "composite", 0.65,
                required_capabilities=["read_email"],
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock recursive call: read_email sub-capability IS available
        original_get_best = service.get_best_available

        async def _mock_get_best(cap_name, user_id):
            if cap_name == "read_email":
                return CapabilityProvider(
                    id="id-native-email",
                    capability_name="read_email",
                    capability_category="data_access",
                    provider_name="composio_outlook",
                    provider_type="composio_oauth",
                    quality_score=0.95,
                )
            return await original_get_best(cap_name, user_id)

        service.get_best_available = _mock_get_best

        result = await service.get_best_available("read_crm_pipeline", "user-1")

        assert result is not None
        assert result.provider_name == "email_deal_inference"
        assert result.provider_type == "composite"

    @pytest.mark.asyncio
    async def test_get_best_available_composite_deps_missing(self, mock_db):
        """Skips composite when sub-capability is unavailable, falls back."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_crm_pipeline", "email_deal_inference", "composite", 0.65,
                required_capabilities=["read_email"],
                capability_category="data_access",
            ),
            _make_provider_row(
                "read_crm_pipeline", "user_stated", "user_provided", 0.50,
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock recursive call: read_email NOT available
        async def _mock_get_best(cap_name, user_id):
            if cap_name == "read_email":
                return None
            # For other capabilities, use real logic
            providers = await service.get_providers(cap_name)
            for p in providers:
                if p.provider_type == "user_provided":
                    return p
            return None

        service.get_best_available = _mock_get_best

        result = await service.get_best_available("read_crm_pipeline", "user-1")

        assert result is not None
        assert result.provider_name == "user_stated"
        assert result.provider_type == "user_provided"

    @pytest.mark.asyncio
    async def test_graceful_degradation_table_missing(self, mock_db):
        """If capability_graph table query fails, log and return None."""
        from src.services.capability_provisioning import CapabilityGraphService

        mock_db.table.side_effect = Exception("relation does not exist")

        service = CapabilityGraphService(mock_db)
        result = await service.get_best_available("research_person", "user-1")

        assert result is None
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestCapabilityGraphService -v 2>&1 | tail -20
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.capability_provisioning'`

**Step 3: Implement CapabilityGraphService**

Create `backend/src/services/capability_provisioning.py`:

```python
"""ARIA Self-Provisioning: Capability Graph, Gap Detection, Resolution Engine.

This module contains the core services for ARIA's self-provisioning system:
- CapabilityGraphService: queries and resolves capability providers
- GapDetectionService: detects capability gaps during goal planning
- ResolutionEngine: generates ranked resolution strategies
- ProvisioningConversation: formats gaps as natural chat messages
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.models.capability import CapabilityGap, CapabilityProvider, ResolutionStrategy

logger = logging.getLogger(__name__)

# Map Composio app names to integration types in user_integrations table
_COMPOSIO_APP_TO_INTEGRATION_TYPE: dict[str, str] = {
    "OUTLOOK365": "email",
    "GMAIL": "email",
    "GOOGLE_CALENDAR": "calendar",
    "SALESFORCE": "crm",
    "HUBSPOT": "crm",
    "VEEVA_CRM": "crm",
    "SLACK": "messaging",
}


class CapabilityGraphService:
    """Manages the capability graph — what ARIA can do and at what quality."""

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def get_providers(self, capability_name: str) -> list[CapabilityProvider]:
        """Get all providers for a capability, sorted by quality descending."""
        try:
            result = (
                self._db.table("capability_graph")
                .select("*")
                .eq("capability_name", capability_name)
                .eq("is_active", True)
                .order("quality_score", desc=True)
                .execute()
            )
            return [CapabilityProvider(**r) for r in (result.data or [])]
        except Exception:
            logger.exception(
                "Failed to query capability_graph",
                extra={"capability_name": capability_name},
            )
            return []

    async def get_best_available(
        self, capability_name: str, user_id: str
    ) -> Optional[CapabilityProvider]:
        """Get the highest-quality available provider for a user.

        Availability rules:
        - native → always available
        - composio_oauth/api_key → user has active connection
        - composite → all required sub-capabilities are available
        - user_provided → always available (lowest quality)
        """
        try:
            providers = await self.get_providers(capability_name)
        except Exception:
            logger.exception(
                "Failed to get providers for capability",
                extra={"capability_name": capability_name},
            )
            return None

        for provider in providers:
            if provider.provider_type == "native":
                return provider

            elif provider.provider_type in ("composio_oauth", "composio_api_key"):
                connected = await self._check_user_connection(
                    user_id, provider.composio_app_name
                )
                if connected:
                    return provider

            elif provider.provider_type == "composite":
                all_available = True
                for req_cap in provider.required_capabilities or []:
                    sub = await self.get_best_available(req_cap, user_id)
                    if sub is None:
                        all_available = False
                        break
                if all_available:
                    return provider

            elif provider.provider_type == "user_provided":
                return provider

        return None

    async def _check_user_connection(
        self, user_id: str, composio_app: str | None
    ) -> bool:
        """Check if user has active Composio connection for this app.

        Uses active_integrations view (status = 'active' only).
        """
        if not composio_app:
            return False

        integration_type = _COMPOSIO_APP_TO_INTEGRATION_TYPE.get(composio_app)
        if not integration_type:
            return False

        try:
            result = (
                self._db.table("active_integrations")
                .select("id")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type)
                .limit(1)
                .execute()
            )
            return len(result.data or []) > 0
        except Exception:
            logger.warning(
                "Failed to check user connection",
                extra={"user_id": user_id, "composio_app": composio_app},
            )
            return False
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestCapabilityGraphService -v 2>&1 | tail -20
```
Expected: All 6 tests PASS.

**Step 5: Commit**

```bash
git add backend/src/services/capability_provisioning.py backend/tests/test_capability_provisioning.py
git commit -m "feat: add CapabilityGraphService with provider resolution logic

Resolves best available provider per capability per user by checking
native availability, Composio OAuth connection status via
active_integrations view, composite sub-capability dependencies,
and user_provided fallbacks. Graceful degradation on all failures.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: ResolutionEngine — Strategy Generation

**Files:**
- Modify: `backend/src/services/capability_provisioning.py`
- Modify: `backend/tests/test_capability_provisioning.py`

**Step 1: Write failing tests for ResolutionEngine**

Append to `backend/tests/test_capability_provisioning.py`:

```python
class TestResolutionEngine:
    """Tests for ResolutionEngine.generate_strategies()."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    def _setup_chain(self, db, data):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_db_response(data)
        db.table.return_value = chain
        return chain

    @pytest.mark.asyncio
    async def test_resolution_strategies_ranked(self, mock_db):
        """Strategies sorted by quality descending."""
        from src.services.capability_provisioning import ResolutionEngine, CapabilityGraphService

        providers = [
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="data_access",
            )),
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_gmail", "composio_oauth", 0.95,
                composio_app_name="GMAIL",
                capability_category="data_access",
            )),
        ]

        graph = CapabilityGraphService(mock_db)
        graph._check_user_connection = AsyncMock(return_value=False)

        # No tenant config
        self._setup_chain(mock_db, [])

        engine = ResolutionEngine(mock_db, graph)
        strategies = await engine.generate_strategies("read_email", "user-1", providers)

        # Should have: 2 direct_integration + user_provided at minimum
        assert len(strategies) >= 3

        # Verify sorted by quality descending
        qualities = [s.quality for s in strategies]
        assert qualities == sorted(qualities, reverse=True)

        # Last strategy should be user_provided
        assert strategies[-1].strategy_type == "user_provided"

    @pytest.mark.asyncio
    async def test_resolution_respects_tenant_whitelist(self, mock_db):
        """Excluded toolkits not offered as resolution strategies."""
        from src.services.capability_provisioning import ResolutionEngine, CapabilityGraphService

        providers = [
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="data_access",
            )),
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_gmail", "composio_oauth", 0.95,
                composio_app_name="GMAIL",
                capability_category="data_access",
            )),
        ]

        graph = CapabilityGraphService(mock_db)
        graph._check_user_connection = AsyncMock(return_value=False)

        engine = ResolutionEngine(mock_db, graph)

        # Mock tenant config: only OUTLOOK365 is allowed
        engine._get_tenant_config = AsyncMock(return_value=MagicMock(
            allowed_composio_toolkits=["OUTLOOK365"],
            allowed_ecosystem_sources=["composio"],
        ))

        strategies = await engine.generate_strategies("read_email", "user-1", providers)

        # Gmail should NOT appear as a direct_integration option
        direct_strategies = [s for s in strategies if s.strategy_type == "direct_integration"]
        direct_apps = [s.composio_app for s in direct_strategies]
        assert "GMAIL" not in direct_apps
        assert "OUTLOOK365" in direct_apps
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestResolutionEngine -v 2>&1 | tail -20
```
Expected: FAIL — `ImportError: cannot import name 'ResolutionEngine'`

**Step 3: Implement ResolutionEngine**

Append to `backend/src/services/capability_provisioning.py`:

```python
class ResolutionEngine:
    """Generates ranked resolution strategies for capability gaps."""

    def __init__(self, db_client: Any, capability_graph: CapabilityGraphService) -> None:
        self._db = db_client
        self._graph = capability_graph

    async def generate_strategies(
        self,
        capability_name: str,
        user_id: str,
        all_providers: list[CapabilityProvider],
    ) -> list[ResolutionStrategy]:
        """Generate ranked strategies for filling a capability gap.

        Strategy types (in order of preference):
        1. direct_integration — Connect via Composio OAuth
        2. composite — Use existing capabilities to approximate
        3. ecosystem_discovered — Search Composio for solutions
        4. user_provided — Ask the user
        """
        strategies: list[ResolutionStrategy] = []
        tenant_config = await self._get_tenant_config(user_id)

        # Strategy 1: Direct integrations not yet connected
        for provider in all_providers:
            if provider.provider_type in ("composio_oauth", "composio_api_key"):
                connected = await self._graph._check_user_connection(
                    user_id, provider.composio_app_name
                )
                if not connected:
                    if tenant_config and tenant_config.allowed_composio_toolkits:
                        if provider.composio_app_name not in tenant_config.allowed_composio_toolkits:
                            continue
                    strategies.append(
                        ResolutionStrategy(
                            strategy_type="direct_integration",
                            provider_name=provider.provider_name,
                            quality=provider.quality_score,
                            setup_time_seconds=30,
                            user_friction="low",
                            composio_app=provider.composio_app_name,
                            description=f"Connect {provider.composio_app_name} for {provider.description}",
                            action_label=f"Connect {provider.composio_app_name}",
                        )
                    )

        # Strategy 2: Composite capabilities available now
        for provider in all_providers:
            if provider.provider_type == "composite":
                all_deps_met = True
                for req_cap in provider.required_capabilities or []:
                    sub = await self._graph.get_best_available(req_cap, user_id)
                    if sub is None:
                        all_deps_met = False
                        break
                if all_deps_met:
                    strategies.append(
                        ResolutionStrategy(
                            strategy_type="composite",
                            provider_name=provider.provider_name,
                            quality=provider.quality_score,
                            setup_time_seconds=0,
                            user_friction="none",
                            description=provider.description,
                            action_label="Use automatically",
                            auto_usable=True,
                        )
                    )

        # Strategy 3: Ecosystem search (if tenant allows)
        if tenant_config is None or "composio" in (
            tenant_config.allowed_ecosystem_sources or ["composio"]
        ):
            ecosystem_results = self._search_composio_tools(capability_name)
            for result in ecosystem_results[:2]:
                strategies.append(
                    ResolutionStrategy(
                        strategy_type="ecosystem_discovered",
                        provider_name=result.get("toolkit_name", "discovered_tool"),
                        quality=0.75,
                        setup_time_seconds=60,
                        user_friction="low",
                        description=f"Found: {result.get('description', 'External tool')}",
                        action_label=f"Connect {result.get('toolkit_name', 'tool')}",
                        ecosystem_source="composio",
                        ecosystem_data=result,
                    )
                )

        # Strategy 4: User-provided (always available)
        strategies.append(
            ResolutionStrategy(
                strategy_type="user_provided",
                provider_name="ask_user",
                quality=0.40,
                setup_time_seconds=120,
                user_friction="medium",
                description="I'll ask you directly for this information",
                action_label="I'll provide it",
            )
        )

        strategies.sort(key=lambda s: s.quality, reverse=True)
        return strategies

    async def _get_tenant_config(self, user_id: str) -> Any:
        """Look up tenant governance config for this user's company."""
        try:
            # Get user's company_id from user_profiles
            profile_result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not profile_result.data or not profile_result.data.get("company_id"):
                return None

            company_id = profile_result.data["company_id"]
            config_result = (
                self._db.table("tenant_capability_config")
                .select("*")
                .eq("tenant_id", company_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not config_result.data:
                return None

            # Return as a simple namespace object
            from types import SimpleNamespace
            return SimpleNamespace(**config_result.data)
        except Exception:
            logger.warning(
                "Failed to load tenant capability config",
                extra={"user_id": user_id},
            )
            return None

    def _search_composio_tools(self, capability_name: str) -> list[dict[str, Any]]:
        """Map capability names to known Composio toolkit names.

        This is a static fallback. When Composio Tool Router API becomes
        available, replace with dynamic search.
        """
        capability_to_toolkits: dict[str, list[str]] = {
            "read_crm_pipeline": ["salesforce", "hubspot", "pipedrive"],
            "read_email": ["outlook365", "gmail"],
            "read_calendar": ["google_calendar", "outlook365"],
            "send_email": ["outlook365", "gmail"],
            "monitor_competitor": ["google_alerts", "mention"],
            "track_patents": ["google_patents"],
        }
        return [
            {"toolkit_name": t, "description": f"{t} integration via Composio"}
            for t in capability_to_toolkits.get(capability_name, [])
        ]
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestResolutionEngine -v 2>&1 | tail -20
```
Expected: 2 tests PASS.

**Step 5: Commit**

```bash
git add backend/src/services/capability_provisioning.py backend/tests/test_capability_provisioning.py
git commit -m "feat: add ResolutionEngine for ranked capability gap strategies

Generates resolution strategies (direct OAuth, composite fallback,
ecosystem discovery, user-provided) ranked by quality. Respects
tenant governance whitelist for allowed toolkits.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: GapDetectionService — Plan Analysis

**Files:**
- Modify: `backend/src/services/capability_provisioning.py`
- Modify: `backend/tests/test_capability_provisioning.py`

**Step 1: Write failing tests for GapDetectionService**

Append to `backend/tests/test_capability_provisioning.py`:

```python
class TestGapDetectionService:
    """Tests for GapDetectionService.analyze_capabilities_for_plan()."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    def _setup_chain(self, db, data):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_db_response(data)
        db.table.return_value = chain
        return chain

    @pytest.mark.asyncio
    async def test_gap_detection_no_gaps(self, mock_db):
        """All capabilities available returns empty gaps list."""
        from src.services.capability_provisioning import (
            CapabilityGraphService,
            GapDetectionService,
            ResolutionEngine,
        )

        self._setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        engine = ResolutionEngine(mock_db, graph)
        detector = GapDetectionService(mock_db, graph, engine)

        # Mock infer to return capabilities that are all available
        detector._infer_capabilities_for_step = AsyncMock(return_value=["research_person"])

        # Mock graph to say research_person IS available at high quality
        graph.get_best_available = AsyncMock(return_value=CapabilityProvider(
            id="id-exa", capability_name="research_person",
            capability_category="research", provider_name="exa_people_search",
            provider_type="native", quality_score=0.80,
        ))
        graph.get_providers = AsyncMock(return_value=[])

        plan = {"steps": [{"description": "Research target person"}]}
        gaps = await detector.analyze_capabilities_for_plan(plan, "user-1")

        assert len(gaps) == 0

    @pytest.mark.asyncio
    async def test_gap_detection_blocking(self, mock_db):
        """Missing capability returns blocking gap."""
        from src.services.capability_provisioning import (
            CapabilityGraphService,
            GapDetectionService,
            ResolutionEngine,
        )

        self._setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        engine = ResolutionEngine(mock_db, graph)
        detector = GapDetectionService(mock_db, graph, engine)

        detector._infer_capabilities_for_step = AsyncMock(return_value=["read_crm_pipeline"])
        graph.get_best_available = AsyncMock(return_value=None)
        graph.get_providers = AsyncMock(return_value=[])
        engine.generate_strategies = AsyncMock(return_value=[
            ResolutionStrategy(
                strategy_type="user_provided",
                provider_name="ask_user",
                quality=0.40,
            )
        ])

        plan = {"steps": [{"description": "Check pipeline status"}]}
        gaps = await detector.analyze_capabilities_for_plan(plan, "user-1")

        assert len(gaps) == 1
        assert gaps[0].severity == "blocking"
        assert gaps[0].capability == "read_crm_pipeline"

    @pytest.mark.asyncio
    async def test_gap_detection_degraded(self, mock_db):
        """Low-quality available provider returns degraded gap."""
        from src.services.capability_provisioning import (
            CapabilityGraphService,
            GapDetectionService,
            ResolutionEngine,
        )

        self._setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        engine = ResolutionEngine(mock_db, graph)
        detector = GapDetectionService(mock_db, graph, engine)

        detector._infer_capabilities_for_step = AsyncMock(return_value=["read_crm_pipeline"])
        graph.get_best_available = AsyncMock(return_value=CapabilityProvider(
            id="id-user", capability_name="read_crm_pipeline",
            capability_category="data_access", provider_name="user_stated",
            provider_type="user_provided", quality_score=0.50,
        ))
        graph.get_providers = AsyncMock(return_value=[])
        engine.generate_strategies = AsyncMock(return_value=[])

        plan = {"steps": [{"description": "Check pipeline"}]}
        gaps = await detector.analyze_capabilities_for_plan(plan, "user-1")

        assert len(gaps) == 1
        assert gaps[0].severity == "degraded"
        assert gaps[0].can_proceed is True
        assert gaps[0].current_quality == 0.50
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestGapDetectionService -v 2>&1 | tail -20
```
Expected: FAIL — `ImportError: cannot import name 'GapDetectionService'`

**Step 3: Implement GapDetectionService**

Append to `backend/src/services/capability_provisioning.py`:

```python
class GapDetectionService:
    """Detects capability gaps during goal planning."""

    # Quality threshold: below this, capability is considered degraded
    _QUALITY_THRESHOLD = 0.7

    def __init__(
        self,
        db_client: Any,
        capability_graph: CapabilityGraphService,
        resolution_engine: ResolutionEngine,
    ) -> None:
        self._db = db_client
        self._graph = capability_graph
        self._resolution = resolution_engine

    async def analyze_capabilities_for_plan(
        self,
        execution_plan: dict[str, Any],
        user_id: str,
    ) -> list[CapabilityGap]:
        """Check each step's required capabilities against available providers.

        Returns gaps with severity and resolution strategies.
        """
        gaps: list[CapabilityGap] = []

        for step in execution_plan.get("steps", []):
            try:
                required = await self._infer_capabilities_for_step(step)
            except Exception:
                logger.warning(
                    "Failed to infer capabilities for step",
                    extra={"step": str(step)[:200]},
                )
                continue

            for cap_name in required:
                best = await self._graph.get_best_available(cap_name, user_id)
                all_providers = await self._graph.get_providers(cap_name)

                if best is None:
                    gaps.append(
                        CapabilityGap(
                            capability=cap_name,
                            step=step,
                            severity="blocking",
                            current_provider=None,
                            current_quality=0,
                            resolutions=await self._resolution.generate_strategies(
                                cap_name, user_id, all_providers
                            ),
                        )
                    )
                elif best.quality_score < self._QUALITY_THRESHOLD:
                    gaps.append(
                        CapabilityGap(
                            capability=cap_name,
                            step=step,
                            severity="degraded",
                            current_provider=best.provider_name,
                            current_quality=best.quality_score,
                            can_proceed=True,
                            resolutions=await self._resolution.generate_strategies(
                                cap_name, user_id, all_providers
                            ),
                        )
                    )

        # Log gaps for demand tracking (best-effort)
        for gap in gaps:
            await self._log_gap(user_id, gap)

        return gaps

    async def _infer_capabilities_for_step(
        self, step: dict[str, Any]
    ) -> list[str]:
        """Use LLM to infer which capabilities a step needs.

        Uses Haiku for cost efficiency.
        """
        try:
            # Get all unique capability names from the graph
            cap_result = self._db.table("capability_graph").select("capability_name").execute()
            unique_caps = sorted(set(r["capability_name"] for r in (cap_result.data or [])))
        except Exception:
            logger.warning("Failed to query capability names, using static list")
            unique_caps = [
                "monitor_competitor", "read_calendar", "read_crm_pipeline",
                "read_email", "research_company", "research_person",
                "research_scientific", "send_email", "track_fda_activity",
                "track_patents",
            ]

        step_desc = step.get("description", step.get("task_description", str(step)))

        prompt = (
            "Given this task step, identify which capabilities are needed.\n\n"
            f"Available capabilities: {', '.join(unique_caps)}\n\n"
            f"Task step: {step_desc}\n\n"
            "Return ONLY a JSON array of capability names needed. "
            'Example: ["research_company", "read_crm_pipeline"]'
        )

        from src.core.llm import LLMClient, TaskType

        llm = LLMClient()
        response = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a capability classifier. Output only valid JSON arrays.",
            temperature=0.0,
            max_tokens=200,
            task=TaskType.SKILL_EXECUTE,
            agent_id="capability_detector",
        )

        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, list):
                return [c for c in parsed if isinstance(c, str)]
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Failed to parse capability inference response",
                extra={"response": response[:200]},
            )
        return []

    async def _log_gap(self, user_id: str, gap: CapabilityGap) -> None:
        """Log a detected gap to capability_gaps_log (best-effort)."""
        try:
            self._db.table("capability_gaps_log").insert({
                "user_id": user_id,
                "capability_name": gap.capability,
                "step_description": gap.step.get("description", str(gap.step)[:500]),
                "best_available_provider": gap.current_provider,
                "best_available_quality": gap.current_quality,
                "strategies_offered": [s.model_dump() for s in gap.resolutions],
                "user_response": "pending",
            }).execute()
        except Exception:
            logger.warning(
                "Failed to log capability gap",
                extra={"capability": gap.capability, "user_id": user_id},
            )
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestGapDetectionService -v 2>&1 | tail -20
```
Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add backend/src/services/capability_provisioning.py backend/tests/test_capability_provisioning.py
git commit -m "feat: add GapDetectionService for plan capability analysis

Analyzes execution plan steps to detect missing or degraded capabilities.
Uses LLM inference (Haiku) to map steps to required capabilities, then
checks availability via CapabilityGraphService. Logs gaps to
capability_gaps_log for demand tracking.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: ProvisioningConversation — Natural Language Gap Presentation

**Files:**
- Modify: `backend/src/services/capability_provisioning.py`
- Modify: `backend/tests/test_capability_provisioning.py`

**Step 1: Write failing test**

Append to `backend/tests/test_capability_provisioning.py`:

```python
class TestProvisioningConversation:
    """Tests for ProvisioningConversation.format_gap_message()."""

    @pytest.mark.asyncio
    async def test_provisioning_message_format(self):
        """Gap message includes labeled options (A, B, C, D)."""
        from src.services.capability_provisioning import ProvisioningConversation

        gaps = [
            CapabilityGap(
                capability="read_crm_pipeline",
                step={"description": "Check existing pipeline"},
                severity="blocking",
                resolutions=[
                    ResolutionStrategy(
                        strategy_type="direct_integration",
                        provider_name="composio_salesforce",
                        quality=0.95,
                        setup_time_seconds=30,
                        composio_app="SALESFORCE",
                        action_label="Connect SALESFORCE",
                    ),
                    ResolutionStrategy(
                        strategy_type="user_provided",
                        provider_name="ask_user",
                        quality=0.40,
                        setup_time_seconds=120,
                        action_label="I'll provide it",
                    ),
                ],
            ),
        ]

        conv = ProvisioningConversation()
        message = await conv.format_gap_message(gaps, "Analyze competitive landscape")

        assert "**A.**" in message
        assert "**B.**" in message
        assert "SALESFORCE" in message
        assert "read_crm_pipeline" in message

    @pytest.mark.asyncio
    async def test_provisioning_message_empty_gaps(self):
        """Empty gaps returns empty string."""
        from src.services.capability_provisioning import ProvisioningConversation

        conv = ProvisioningConversation()
        message = await conv.format_gap_message([], "Some goal")

        assert message == ""

    @pytest.mark.asyncio
    async def test_provisioning_message_degraded_shows_upgrade(self):
        """Degraded gap message shows current quality and upgrade option."""
        from src.services.capability_provisioning import ProvisioningConversation

        gaps = [
            CapabilityGap(
                capability="read_crm_pipeline",
                step={"description": "Check pipeline"},
                severity="degraded",
                current_provider="user_stated",
                current_quality=0.50,
                can_proceed=True,
                resolutions=[
                    ResolutionStrategy(
                        strategy_type="direct_integration",
                        provider_name="composio_salesforce",
                        quality=0.95,
                        composio_app="SALESFORCE",
                        action_label="Connect SALESFORCE",
                    ),
                ],
            ),
        ]

        conv = ProvisioningConversation()
        message = await conv.format_gap_message(gaps, "Analyze pipeline")

        assert "50%" in message
        assert "95%" in message
        assert "SALESFORCE" in message
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestProvisioningConversation -v 2>&1 | tail -20
```
Expected: FAIL — `ImportError: cannot import name 'ProvisioningConversation'`

**Step 3: Implement ProvisioningConversation**

Append to `backend/src/services/capability_provisioning.py`:

```python
class ProvisioningConversation:
    """Presents capability gaps to users in natural conversation."""

    async def format_gap_message(
        self,
        gaps: list[CapabilityGap],
        goal_title: str,
    ) -> str:
        """Generate natural language message presenting gaps and options.

        Injected into chat context — not a settings page or modal.
        """
        if not gaps:
            return ""

        blocking = [g for g in gaps if g.severity == "blocking"]
        degraded = [g for g in gaps if g.severity == "degraded"]

        message_parts: list[str] = []

        for gap in blocking:
            options = self._format_resolution_options(gap.resolutions)
            step_desc = gap.step.get("description", "a step")
            message_parts.append(
                f"For **{step_desc}**, I need {gap.capability} access "
                f"but don't have it yet. Options:\n{options}"
            )

        for gap in degraded:
            best_upgrade = gap.resolutions[0] if gap.resolutions else None
            step_desc = gap.step.get("description", "this step")
            if best_upgrade and best_upgrade.strategy_type == "direct_integration":
                message_parts.append(
                    f"I can handle **{step_desc}** with "
                    f"{gap.current_provider} (~{int(gap.current_quality * 100)}% accuracy). "
                    f"For better results, connect {best_upgrade.composio_app} "
                    f"({int(best_upgrade.quality * 100)}% accuracy)."
                )
            else:
                message_parts.append(
                    f"I can handle **{step_desc}** with "
                    f"{gap.current_provider} (~{int(gap.current_quality * 100)}% accuracy), "
                    f"but results may be limited."
                )

        return "\n\n".join(message_parts)

    def _format_resolution_options(
        self, strategies: list[ResolutionStrategy]
    ) -> str:
        """Format strategies as labeled options for chat."""
        labels = ["A", "B", "C", "D"]
        options: list[str] = []
        for i, strategy in enumerate(strategies[:4]):
            quality_pct = int(strategy.quality * 100)
            if strategy.setup_time_seconds < 60:
                setup = f"{strategy.setup_time_seconds}s"
            else:
                setup = f"~{strategy.setup_time_seconds // 60}min"
            options.append(
                f"**{labels[i]}.** {strategy.action_label} "
                f"({quality_pct}% accuracy, {setup} setup)"
            )
        return "\n".join(options)
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestProvisioningConversation -v 2>&1 | tail -20
```
Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add backend/src/services/capability_provisioning.py backend/tests/test_capability_provisioning.py
git commit -m "feat: add ProvisioningConversation for natural language gap messages

Formats capability gaps as conversational messages with labeled options
(A/B/C/D) showing quality percentages and setup time. Handles both
blocking gaps (full options list) and degraded gaps (upgrade suggestion).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Demand Tracking Service

**Files:**
- Modify: `backend/src/services/capability_provisioning.py`
- Modify: `backend/tests/test_capability_provisioning.py`

**Step 1: Write failing test**

Append to `backend/tests/test_capability_provisioning.py`:

```python
class TestDemandTracking:
    """Tests for capability demand tracking."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_demand_tracking_increments(self, mock_db):
        """Capability demand record incremented after goal execution."""
        from src.services.capability_provisioning import DemandTracker

        # Mock: existing demand row found
        existing_row = {
            "id": "demand-1",
            "times_needed": 2,
            "times_satisfied_directly": 1,
            "times_used_composite": 0,
            "times_used_fallback": 1,
            "avg_quality_achieved": 0.60,
        }

        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = _mock_db_response([existing_row])

        update_chain = MagicMock()
        update_chain.eq.return_value = update_chain
        update_chain.execute.return_value = _mock_db_response([])
        chain.update = MagicMock(return_value=update_chain)

        mock_db.table.return_value = chain

        tracker = DemandTracker(mock_db)
        await tracker.record_capability_usage(
            user_id="user-1",
            goal_type="research",
            capabilities_used=[
                {
                    "name": "research_person",
                    "provider_type": "native",
                    "quality": 0.80,
                    "direct": True,
                },
            ],
        )

        # Verify update was called
        chain.update.assert_called_once()
        update_args = chain.update.call_args[0][0]
        assert update_args["times_needed"] == 3
        assert update_args["times_satisfied_directly"] == 2
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestDemandTracking -v 2>&1 | tail -20
```
Expected: FAIL — `ImportError: cannot import name 'DemandTracker'`

**Step 3: Implement DemandTracker**

Append to `backend/src/services/capability_provisioning.py`:

```python
class DemandTracker:
    """Tracks capability demand patterns for proactive suggestions."""

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def record_capability_usage(
        self,
        user_id: str,
        goal_type: str,
        capabilities_used: list[dict[str, Any]],
    ) -> None:
        """Update capability_demand after goal execution completes."""
        for cap in capabilities_used:
            cap_name = cap.get("name", "")
            if not cap_name:
                continue

            try:
                existing = (
                    self._db.table("capability_demand")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("capability_name", cap_name)
                    .eq("goal_type", goal_type)
                    .limit(1)
                    .execute()
                )

                if existing.data:
                    row = existing.data[0]
                    prev_count = row.get("times_needed", 0) or 1
                    prev_avg = row.get("avg_quality_achieved", 0) or 0

                    updates: dict[str, Any] = {
                        "times_needed": row["times_needed"] + 1,
                        "avg_quality_achieved": (
                            (prev_avg * prev_count + cap.get("quality", 0.5))
                            / (prev_count + 1)
                        ),
                        "updated_at": "now()",
                    }

                    provider_type = cap.get("provider_type", "")
                    if provider_type == "native" or cap.get("direct", False):
                        updates["times_satisfied_directly"] = (
                            row.get("times_satisfied_directly", 0) + 1
                        )
                    elif provider_type == "composite":
                        updates["times_used_composite"] = (
                            row.get("times_used_composite", 0) + 1
                        )
                    else:
                        updates["times_used_fallback"] = (
                            row.get("times_used_fallback", 0) + 1
                        )

                    (
                        self._db.table("capability_demand")
                        .update(updates)
                        .eq("id", row["id"])
                        .execute()
                    )
                else:
                    provider_type = cap.get("provider_type", "")
                    self._db.table("capability_demand").insert({
                        "user_id": user_id,
                        "capability_name": cap_name,
                        "goal_type": goal_type,
                        "times_needed": 1,
                        "times_satisfied_directly": (
                            1 if (provider_type == "native" or cap.get("direct")) else 0
                        ),
                        "times_used_composite": (
                            1 if provider_type == "composite" else 0
                        ),
                        "times_used_fallback": (
                            1 if provider_type not in ("native", "composite") and not cap.get("direct") else 0
                        ),
                        "avg_quality_achieved": cap.get("quality", 0.5),
                        "quality_with_ideal_provider": 0.95,
                    }).execute()
            except Exception:
                logger.warning(
                    "Failed to update capability demand",
                    extra={"user_id": user_id, "capability": cap_name},
                )
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestDemandTracking -v 2>&1 | tail -20
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/src/services/capability_provisioning.py backend/tests/test_capability_provisioning.py
git commit -m "feat: add DemandTracker for capability usage pattern tracking

Records capability usage after goal execution to capability_demand table.
Tracks times_needed, satisfaction method (direct/composite/fallback),
and running average quality. Enables proactive integration suggestions.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Hook into SkillOrchestrator

**Files:**
- Modify: `backend/src/skills/orchestrator.py:358-382` (between plan creation and return)

**Step 1: Write failing test**

Append to `backend/tests/test_capability_provisioning.py`:

```python
class TestOrchestratorIntegration:
    """Test that gap detection integrates with SkillOrchestrator plans."""

    @pytest.mark.asyncio
    async def test_plan_annotated_with_gaps(self):
        """ExecutionPlan dict gets capability_gaps key when gaps exist."""
        from src.services.capability_provisioning import annotate_plan_with_gaps

        mock_db = MagicMock()
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_db_response([])
        mock_db.table.return_value = chain

        # Plan dict (what analyze_task returns serialized)
        plan_dict = {
            "plan_id": "test-plan-1",
            "steps": [
                {"step_number": 1, "description": "Research competitors"},
            ],
        }

        # Mock the gap detector to return one blocking gap
        with patch(
            "src.services.capability_provisioning.GapDetectionService"
        ) as MockDetector:
            mock_instance = AsyncMock()
            mock_instance.analyze_capabilities_for_plan.return_value = [
                CapabilityGap(
                    capability="read_crm_pipeline",
                    step={"description": "Research competitors"},
                    severity="blocking",
                ),
            ]
            MockDetector.return_value = mock_instance

            result = await annotate_plan_with_gaps(plan_dict, "user-1", mock_db)

        assert "capability_gaps" in result
        assert result["has_blocking_gaps"] is True
        assert len(result["capability_gaps"]) == 1
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestOrchestratorIntegration -v 2>&1 | tail -20
```
Expected: FAIL — `ImportError: cannot import name 'annotate_plan_with_gaps'`

**Step 3: Implement annotate_plan_with_gaps function**

Append to `backend/src/services/capability_provisioning.py`:

```python
async def annotate_plan_with_gaps(
    plan_dict: dict[str, Any],
    user_id: str,
    db_client: Any,
) -> dict[str, Any]:
    """Annotate an execution plan dict with capability gap information.

    Called by SkillOrchestrator.analyze_task() after building the plan,
    before returning it. Adds 'capability_gaps', 'has_blocking_gaps',
    and 'has_degraded_gaps' keys to the plan dict.

    Graceful degradation: if anything fails, the original plan is returned
    unchanged.
    """
    try:
        graph = CapabilityGraphService(db_client)
        engine = ResolutionEngine(db_client, graph)
        detector = GapDetectionService(db_client, graph, engine)

        gaps = await detector.analyze_capabilities_for_plan(plan_dict, user_id)

        if gaps:
            plan_dict["capability_gaps"] = [g.model_dump() for g in gaps]
            plan_dict["has_blocking_gaps"] = any(
                g.severity == "blocking" for g in gaps
            )
            plan_dict["has_degraded_gaps"] = any(
                g.severity == "degraded" for g in gaps
            )

            # Auto-resolve degraded gaps with auto-usable composites
            for gap in gaps:
                if gap.severity == "degraded":
                    auto_strategies = [s for s in gap.resolutions if s.auto_usable]
                    if auto_strategies:
                        gap.auto_resolved = True
                        gap.resolved_with = auto_strategies[0]
        else:
            plan_dict["capability_gaps"] = []
            plan_dict["has_blocking_gaps"] = False
            plan_dict["has_degraded_gaps"] = False

    except Exception:
        logger.exception("Failed to annotate plan with capability gaps")
        # Graceful degradation — return plan unchanged
        plan_dict.setdefault("capability_gaps", [])
        plan_dict.setdefault("has_blocking_gaps", False)
        plan_dict.setdefault("has_degraded_gaps", False)

    return plan_dict
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestOrchestratorIntegration -v 2>&1 | tail -20
```
Expected: PASS.

**Step 5: Hook into SkillOrchestrator.analyze_task()**

Edit `backend/src/skills/orchestrator.py`. Insert after line 369 (after `await self._persist_plan(plan, user_id)`) and before the `logger.info(...)` on line 371:

```python
        # --- Self-provisioning: annotate plan with capability gaps ---
        try:
            from src.services.capability_provisioning import annotate_plan_with_gaps

            plan_dict = {
                "plan_id": plan.plan_id,
                "steps": [
                    {
                        "step_number": s.step_number,
                        "skill_id": s.skill_id,
                        "skill_path": s.skill_path,
                        "description": s.input_data.get("description", s.skill_path),
                        "input_data": s.input_data,
                    }
                    for s in plan.steps
                ],
            }
            annotated = await annotate_plan_with_gaps(plan_dict, user_id, self._db)
            # Attach gap metadata to plan for downstream consumers
            plan.capability_gaps = annotated.get("capability_gaps", [])  # type: ignore[attr-defined]
            plan.has_blocking_gaps = annotated.get("has_blocking_gaps", False)  # type: ignore[attr-defined]
            plan.has_degraded_gaps = annotated.get("has_degraded_gaps", False)  # type: ignore[attr-defined]
        except Exception:
            logger.warning("Self-provisioning gap detection failed (non-fatal)")
```

**Step 6: Run existing orchestrator tests to make sure nothing broke**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_orchestrator*.py -v 2>&1 | tail -30
```
Expected: All existing tests still PASS.

**Step 7: Commit**

```bash
git add backend/src/services/capability_provisioning.py backend/src/skills/orchestrator.py backend/tests/test_capability_provisioning.py
git commit -m "feat: integrate capability gap detection into SkillOrchestrator

annotate_plan_with_gaps() is called after plan creation in analyze_task().
Attaches capability_gaps, has_blocking_gaps, and has_degraded_gaps to
ExecutionPlan. Graceful degradation — if detection fails, plan proceeds
unchanged.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Hook into GoalExecutionService

**Files:**
- Modify: `backend/src/services/goal_execution.py`

**Step 1: Identify the insertion point**

In `backend/src/services/goal_execution.py`, the `execute_goal_sync()` method at line 433 fetches the goal and gathers context before executing agents. The provisioning conversation should be triggered after context gathering but before agent execution — around line 484 (after `context = await self._gather_execution_context(user_id)`).

**Step 2: Add provisioning check**

Insert after the `context = await self._gather_execution_context(user_id)` line (approximately line 484) in `execute_goal_sync()`:

```python
        # --- Self-provisioning: check for capability gaps ---
        try:
            from src.services.capability_provisioning import (
                CapabilityGraphService,
                GapDetectionService,
                ProvisioningConversation,
                ResolutionEngine,
            )

            graph = CapabilityGraphService(self._db)
            resolution = ResolutionEngine(self._db, graph)
            detector = GapDetectionService(self._db, graph, resolution)

            # Build a minimal plan dict from goal agents
            agents = goal.get("goal_agents", [])
            plan_steps = [
                {"description": a.get("agent_type", "execute task")}
                for a in agents
                if a.get("status") in ("pending", "active", "running", None)
            ]

            if plan_steps:
                gaps = await detector.analyze_capabilities_for_plan(
                    {"steps": plan_steps}, user_id
                )
                blocking = [g for g in gaps if g.severity == "blocking"]

                if blocking:
                    conv = ProvisioningConversation()
                    gap_message = await conv.format_gap_message(
                        gaps, goal.get("title", "this goal")
                    )
                    # Send via WebSocket as provisioning options
                    try:
                        from src.core.ws import ws_manager

                        await ws_manager.send_to_user(
                            user_id=user_id,
                            event_type="provisioning_options",
                            data={
                                "goal_id": goal_id,
                                "message": gap_message,
                                "gaps": [g.model_dump() for g in gaps],
                            },
                        )
                    except Exception:
                        logger.debug("Failed to send provisioning options via WS")
        except Exception:
            logger.debug("Self-provisioning check failed (non-fatal)")
```

**Step 3: Run existing goal execution tests**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_goal_execution*.py -v 2>&1 | tail -30
```
Expected: All existing tests still PASS. The new code is wrapped in try/except so it cannot break existing functionality.

**Step 4: Commit**

```bash
git add backend/src/services/goal_execution.py
git commit -m "feat: integrate provisioning conversation into goal execution

When executing goals, checks for capability gaps before starting agents.
Blocking gaps are presented to user via WebSocket as natural language
options. Graceful degradation — if check fails, execution proceeds.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Hook into Pulse Engine via Scheduler

**Files:**
- Modify: `backend/src/services/scheduler.py`

**Step 1: Add the capability demand check function**

Append the following function to `backend/src/services/scheduler.py`, before the `start_scheduler()` function (around line 1095):

```python
async def _run_capability_demand_check() -> None:
    """Check if any capabilities have crossed suggestion threshold.

    When a user has needed a capability 3+ times without direct access,
    generate a proactive pulse signal suggesting they connect the tool.
    """
    try:
        from src.db.supabase import SupabaseClient
        from src.services.intelligence_pulse import get_pulse_engine

        db = SupabaseClient.get_client()
        pulse_engine = get_pulse_engine()

        # Get all users with unresolved demand
        demands_result = (
            db.table("capability_demand")
            .select("*")
            .gte("times_needed", 3)
            .eq("suggestion_threshold_reached", False)
            .execute()
        )

        for demand in demands_result.data or []:
            fallback_uses = (
                demand.get("times_used_composite", 0)
                + demand.get("times_used_fallback", 0)
            )
            if fallback_uses < 3:
                continue

            avg_quality = demand.get("avg_quality_achieved", 0.5) or 0.5
            ideal_quality = demand.get("quality_with_ideal_provider", 0.95) or 0.95

            await pulse_engine.process_signal(
                user_id=demand["user_id"],
                signal={
                    "pulse_type": "intelligent",
                    "source": "capability_demand",
                    "title": f"Improve your {demand['capability_name']} accuracy",
                    "content": (
                        f"You've needed {demand['capability_name']} "
                        f"{demand['times_needed']} times. Currently getting "
                        f"~{int(avg_quality * 100)}% accuracy. Connecting the "
                        f"right tool would get you to ~{int(ideal_quality * 100)}%."
                    ),
                    "signal_category": "capability",
                    "raw_data": demand,
                },
            )

            # Mark threshold reached
            (
                db.table("capability_demand")
                .update({"suggestion_threshold_reached": True})
                .eq("id", demand["id"])
                .execute()
            )

            logger.info(
                "Capability demand pulse generated",
                extra={
                    "user_id": demand["user_id"],
                    "capability": demand["capability_name"],
                    "times_needed": demand["times_needed"],
                },
            )

    except Exception:
        logger.exception("Capability demand check scheduler run failed")
```

**Step 2: Register the job in start_scheduler()**

In `start_scheduler()`, add a new `_scheduler.add_job()` call. Insert it alongside the other pulse/demand-related jobs (after the `_run_pulse_sweep` job registration, around line 1419):

```python
        _scheduler.add_job(
            _run_capability_demand_check,
            trigger=CronTrigger(hour="*/6"),  # Every 6 hours
            id="capability_demand_check",
            name="Capability demand proactive suggestion check",
            replace_existing=True,
        )
```

**Step 3: Write a test for the demand threshold pulse**

Append to `backend/tests/test_capability_provisioning.py`:

```python
class TestDemandPulse:
    """Tests for capability demand → pulse signal integration."""

    @pytest.mark.asyncio
    async def test_demand_threshold_triggers_pulse(self):
        """3+ uses without direct access generates pulse signal."""
        from unittest.mock import call

        mock_db = MagicMock()
        demand_row = {
            "id": "demand-1",
            "user_id": "user-1",
            "capability_name": "read_crm_pipeline",
            "times_needed": 5,
            "times_satisfied_directly": 0,
            "times_used_composite": 2,
            "times_used_fallback": 3,
            "avg_quality_achieved": 0.55,
            "quality_with_ideal_provider": 0.95,
            "suggestion_threshold_reached": False,
        }

        # Mock the demand query
        demand_chain = MagicMock()
        demand_chain.select.return_value = demand_chain
        demand_chain.gte.return_value = demand_chain
        demand_chain.eq.return_value = demand_chain
        demand_chain.execute.return_value = _mock_db_response([demand_row])
        demand_chain.update.return_value = demand_chain

        mock_db.table.return_value = demand_chain

        # Mock pulse engine
        mock_pulse = AsyncMock()
        mock_pulse.process_signal = AsyncMock(return_value={"id": "signal-1"})

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_db), \
             patch("src.services.intelligence_pulse.get_pulse_engine", return_value=mock_pulse):
            # Import dynamically to get patched version
            import importlib
            import src.services.scheduler as sched_mod
            importlib.reload(sched_mod)

            await sched_mod._run_capability_demand_check()

        # Verify pulse was generated
        mock_pulse.process_signal.assert_called_once()
        signal_arg = mock_pulse.process_signal.call_args[1]["signal"] if mock_pulse.process_signal.call_args[1] else mock_pulse.process_signal.call_args[0][1]
        assert "read_crm_pipeline" in signal_arg["title"]
        assert signal_arg["signal_category"] == "capability"
```

**Step 4: Run the test**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py::TestDemandPulse -v 2>&1 | tail -20
```
Expected: PASS.

**Step 5: Run full scheduler tests**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_scheduler*.py -v 2>&1 | tail -20
```
Expected: All existing tests still PASS.

**Step 6: Commit**

```bash
git add backend/src/services/scheduler.py backend/tests/test_capability_provisioning.py
git commit -m "feat: add capability demand pulse check to scheduler

Every 6 hours, check capability_demand for users who have needed a
capability 3+ times without direct access. Generate proactive pulse
signal suggesting they connect the integration for better accuracy.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Run Full Test Suite and Final Verification

**Files:** None (verification only)

**Step 1: Run all capability provisioning tests**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py backend/tests/test_capability_models.py -v 2>&1 | tail -40
```
Expected: All 14+ tests PASS.

**Step 2: Run tests for modified files**

Run:
```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_orchestrator*.py backend/tests/test_goal_execution*.py -v --timeout=60 2>&1 | tail -30
```
Expected: No regressions.

**Step 3: Verify database tables exist via Supabase**

```sql
SELECT table_name,
       (SELECT COUNT(*) FROM information_schema.columns WHERE columns.table_name = tables.table_name AND columns.table_schema = 'public') as col_count
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('capability_graph', 'capability_gaps_log', 'capability_demand', 'tenant_capability_config')
ORDER BY table_name;
```

**Step 4: Verify seed data count**

```sql
SELECT capability_name, capability_category, COUNT(*) as providers
FROM capability_graph
GROUP BY capability_name, capability_category
ORDER BY capability_category, capability_name;
```
Expected: ~10 capability names with 2-7 providers each.

**Step 5: Verify RLS is active**

```sql
SELECT tablename, policyname
FROM pg_policies
WHERE tablename IN ('capability_graph', 'capability_gaps_log', 'capability_demand', 'tenant_capability_config')
ORDER BY tablename;
```
Expected: Each table has at least 1 RLS policy.

**Step 6: Commit any final fixes**

If any tests needed fixes, commit them:
```bash
git add -u
git commit -m "fix: address test failures from capability provisioning integration

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary of Files

### Created
| File | Description |
|------|-------------|
| `backend/supabase/migrations/20260301100000_self_provisioning.sql` | 4 tables + seed data + RLS |
| `backend/src/models/capability.py` | Pydantic models (CapabilityProvider, ResolutionStrategy, CapabilityGap) |
| `backend/src/services/capability_provisioning.py` | Core service (5 classes + 1 function) |
| `backend/tests/test_capability_models.py` | Model unit tests (7 tests) |
| `backend/tests/test_capability_provisioning.py` | Service tests (14+ tests) |

### Modified
| File | Change |
|------|--------|
| `backend/src/skills/orchestrator.py:369` | Insert gap detection after plan creation |
| `backend/src/services/goal_execution.py:484` | Insert provisioning conversation before agent execution |
| `backend/src/services/scheduler.py` | Add `_run_capability_demand_check()` + register job |

### Classes/Functions Created
| Name | Location | Purpose |
|------|----------|---------|
| `CapabilityGraphService` | capability_provisioning.py | Query/resolve capability providers |
| `ResolutionEngine` | capability_provisioning.py | Generate ranked resolution strategies |
| `GapDetectionService` | capability_provisioning.py | Detect gaps during plan analysis |
| `ProvisioningConversation` | capability_provisioning.py | Format gaps as natural chat |
| `DemandTracker` | capability_provisioning.py | Track usage patterns |
| `annotate_plan_with_gaps()` | capability_provisioning.py | Hook function for orchestrator |
| `_run_capability_demand_check()` | scheduler.py | Pulse engine integration |
