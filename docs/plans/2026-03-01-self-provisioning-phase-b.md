# ARIA Self-Provisioning Phase B: Skill Creation + Ecosystem Search + Enterprise Governance

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give ARIA the ability to search external tool ecosystems, create her own skills when no tool exists, and govern skill trust through approval workflows and health monitoring.

**Architecture:** Phase B extends Phase A's `capability_provisioning.py` with three new services: `EcosystemSearchService` (searches Composio/MCP Registry/Smithery), `SkillCreationEngine` (generates prompt-chain/API-wrapper/composite skills), and `SkillTrustManager` + `SkillHealthMonitor` (trust graduation and health checks). These wire into the existing `ResolutionEngine.generate_strategies()` as two new strategy types (`ecosystem_discovered` and `skill_creation`), and `ProvisioningConversation.handle_user_choice()` handles execution. Two new scheduled jobs are added to `scheduler.py`.

**Tech Stack:** Python 3.11+ / FastAPI / Supabase (PostgreSQL) / Pydantic / httpx / APScheduler / pytest + AsyncMock

---

### Task 1: Database Migration — ecosystem_search_cache, aria_generated_skills, skill_approval_queue, published_skills

**Files:**
- Create: `backend/supabase/migrations/20260301110000_skill_creation_governance.sql`

**Step 1: Write the migration file**

```sql
-- Migration: Skill Creation & Enterprise Governance tables (Phase B)
-- Depends on: 20260301100000_self_provisioning.sql (Phase A)

-- ============================================================
-- Table 1: ecosystem_search_cache
-- Caches external ecosystem search results for 7 days
-- ============================================================
CREATE TABLE ecosystem_search_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capability_name TEXT NOT NULL,
    search_source TEXT NOT NULL CHECK (search_source IN ('composio', 'mcp_registry', 'smithery')),
    search_query TEXT NOT NULL,
    results JSONB NOT NULL DEFAULT '[]',
    result_count INT DEFAULT 0,
    searched_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),
    UNIQUE(capability_name, search_source)
);

CREATE INDEX idx_ecosystem_cache_capability ON ecosystem_search_cache(capability_name);
CREATE INDEX idx_ecosystem_cache_expires ON ecosystem_search_cache(expires_at);

ALTER TABLE ecosystem_search_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ecosystem_cache_service" ON ecosystem_search_cache
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "ecosystem_cache_read" ON ecosystem_search_cache
    FOR SELECT TO authenticated USING (true);

-- ============================================================
-- Table 2: aria_generated_skills
-- Skills ARIA creates herself (prompt chains, API wrappers, composite workflows)
-- ============================================================
CREATE TABLE aria_generated_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    tenant_id UUID NOT NULL,
    skill_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    skill_type TEXT NOT NULL CHECK (skill_type IN ('prompt_chain', 'api_wrapper', 'composite_workflow')),
    created_from_capability_gap TEXT,
    created_from_goal_id UUID,
    creation_reasoning TEXT,
    definition JSONB NOT NULL,
    generated_code TEXT,
    code_hash TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN (
        'draft', 'tested', 'user_reviewed', 'active', 'graduated',
        'tenant_approved', 'published', 'disabled', 'deprecated'
    )),
    trust_level TEXT DEFAULT 'LOW' CHECK (trust_level IN ('LOW', 'MEDIUM', 'HIGH')),
    execution_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    failure_count INT DEFAULT 0,
    avg_quality_score FLOAT,
    avg_execution_time_ms INT,
    last_executed_at TIMESTAMPTZ,
    user_feedback_score FLOAT,
    last_health_check TIMESTAMPTZ,
    health_status TEXT DEFAULT 'unknown' CHECK (health_status IN ('healthy', 'degraded', 'broken', 'unknown')),
    error_rate_7d FLOAT DEFAULT 0,
    sandbox_test_passed BOOLEAN DEFAULT FALSE,
    sandbox_test_output JSONB,
    sandbox_tested_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_aria_skills_user ON aria_generated_skills(user_id, status);
CREATE INDEX idx_aria_skills_tenant ON aria_generated_skills(tenant_id, status);
CREATE INDEX idx_aria_skills_capability ON aria_generated_skills(created_from_capability_gap);
CREATE INDEX idx_aria_skills_health ON aria_generated_skills(health_status)
    WHERE status = 'active' OR status = 'graduated';

ALTER TABLE aria_generated_skills ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aria_skills_own" ON aria_generated_skills
    FOR ALL TO authenticated USING (user_id = auth.uid());
CREATE POLICY "aria_skills_tenant_read" ON aria_generated_skills
    FOR SELECT TO authenticated USING (
        tenant_id IN (SELECT company_id FROM user_profiles WHERE id = auth.uid())
        AND status IN ('tenant_approved', 'published')
    );
CREATE POLICY "aria_skills_service" ON aria_generated_skills
    FOR ALL USING (auth.role() = 'service_role');

CREATE TRIGGER update_aria_generated_skills_updated_at
    BEFORE UPDATE ON aria_generated_skills
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Table 3: skill_approval_queue
-- Admin approval workflow for trust graduation and publishing
-- ============================================================
CREATE TABLE skill_approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID REFERENCES aria_generated_skills(id) ON DELETE CASCADE NOT NULL,
    tenant_id UUID NOT NULL,
    requested_by UUID REFERENCES auth.users(id) NOT NULL,
    approval_type TEXT NOT NULL CHECK (approval_type IN (
        'first_use', 'trust_graduation', 'tenant_publish', 'marketplace_publish'
    )),
    current_trust_level TEXT,
    requested_trust_level TEXT,
    justification TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    decided_by UUID REFERENCES auth.users(id),
    decision_reason TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approval_queue_pending ON skill_approval_queue(tenant_id, status)
    WHERE status = 'pending';

ALTER TABLE skill_approval_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "approval_queue_service" ON skill_approval_queue
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 4: published_skills (marketplace schema — future use)
-- ============================================================
CREATE TABLE published_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_skill_id UUID REFERENCES aria_generated_skills(id),
    source_tenant_id UUID NOT NULL,
    published_by_role TEXT,
    skill_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    skill_type TEXT NOT NULL,
    definition JSONB NOT NULL,
    industry_vertical TEXT DEFAULT 'life_sciences',
    install_count INT DEFAULT 0,
    avg_rating FLOAT,
    rating_count INT DEFAULT 0,
    tags TEXT[],
    moderation_status TEXT DEFAULT 'pending' CHECK (moderation_status IN (
        'pending', 'approved', 'rejected', 'flagged'
    )),
    moderated_by TEXT,
    moderated_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE published_skills ENABLE ROW LEVEL SECURITY;
CREATE POLICY "published_skills_read" ON published_skills
    FOR SELECT TO authenticated USING (moderation_status = 'approved');
CREATE POLICY "published_skills_service" ON published_skills
    FOR ALL USING (auth.role() = 'service_role');
```

**Step 2: Verify no conflicts with Phase A migration**

Run: `ls backend/supabase/migrations/20260301*`
Expected: Both `20260301100000_self_provisioning.sql` (Phase A) and the new `20260301110000_skill_creation_governance.sql` are present.

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260301110000_skill_creation_governance.sql
git commit -m "feat: add Phase B migration — ecosystem cache, generated skills, approval queue, marketplace"
```

---

### Task 2: Pydantic Models — SkillCreationProposal, EcosystemResult

**Files:**
- Modify: `backend/src/models/capability.py` (append new models after existing ones)
- Test: `backend/tests/test_skill_creation.py` (create, write model validation tests first)

**Step 1: Write the failing test for new models**

Create `backend/tests/test_skill_creation.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestSkillCreationModels -v --no-header -x 2>&1 | tail -20`
Expected: FAIL — `ImportError: cannot import name 'EcosystemResult' from 'src.models.capability'`

**Step 3: Write the models**

Append to `backend/src/models/capability.py` (after the existing `CapabilityGap` class at line 67):

```python


class EcosystemResult(BaseModel):
    """A tool/server discovered from an external ecosystem search."""

    name: str
    source: str  # composio, mcp_registry, smithery
    description: str = ""
    quality_estimate: float = Field(default=0.5, ge=0, le=1)
    relevance_score: float = Field(default=0.5, ge=0, le=1)
    final_score: float = Field(default=0.5, ge=0, le=1)
    app: Optional[str] = None  # Composio app identifier
    qualified_name: Optional[str] = None  # Smithery qualified name
    url: Optional[str] = None
    author: Optional[str] = None
    auth_type: str = "varies"
    setup_time: int = 60  # seconds
    stars: int = 0
    last_updated: Optional[str] = None


class SkillCreationProposal(BaseModel):
    """LLM assessment of whether ARIA can build a skill for a capability gap."""

    can_create: bool
    skill_type: str  # prompt_chain, api_wrapper, composite_workflow
    confidence: float = Field(ge=0, le=1)
    skill_name: str
    description: str
    estimated_quality: float = Field(default=0.5, ge=0, le=1)
    approach: str = ""
    public_api_url: Optional[str] = None
    required_capabilities: list[str] = Field(default_factory=list)
    reason_if_no: Optional[str] = None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestSkillCreationModels -v --no-header -x 2>&1 | tail -20`
Expected: 2 passed

**Step 5: Commit**

```bash
git add backend/src/models/capability.py backend/tests/test_skill_creation.py
git commit -m "feat: add EcosystemResult and SkillCreationProposal Pydantic models"
```

---

### Task 3: Ecosystem Search Service

**Files:**
- Create: `backend/src/services/ecosystem_search.py`
- Test: `backend/tests/test_skill_creation.py` (append tests)

**Step 1: Write the failing tests for ecosystem search**

Append to `backend/tests/test_skill_creation.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestEcosystemSearchService -v --no-header -x 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.ecosystem_search'`

**Step 3: Write the implementation**

Create `backend/src/services/ecosystem_search.py`:

```python
"""Ecosystem search service — discovers tools from Composio, MCP Registry, Smithery.

When ARIA hits a capability gap, this service searches external tool ecosystems
for solutions. Results are cached for 7 days and filtered by tenant whitelist.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.models.capability import EcosystemResult

logger = logging.getLogger(__name__)

# Static mapping of capabilities → known Composio apps (fallback when SDK unavailable)
_COMPOSIO_CAPABILITY_MAP: dict[str, list[dict[str, str]]] = {
    "read_crm_pipeline": [
        {"name": "Salesforce", "app": "SALESFORCE", "description": "CRM pipeline data"},
        {"name": "HubSpot", "app": "HUBSPOT", "description": "CRM pipeline data"},
        {"name": "Pipedrive", "app": "PIPEDRIVE", "description": "CRM pipeline data"},
    ],
    "read_email": [
        {"name": "Outlook", "app": "OUTLOOK365", "description": "Email access via Microsoft"},
        {"name": "Gmail", "app": "GMAIL", "description": "Email access via Google"},
    ],
    "read_calendar": [
        {"name": "Google Calendar", "app": "GOOGLE_CALENDAR", "description": "Calendar events"},
        {"name": "Outlook Calendar", "app": "OUTLOOK365", "description": "Calendar events"},
    ],
    "send_email": [
        {"name": "Outlook", "app": "OUTLOOK365", "description": "Send emails"},
        {"name": "Gmail", "app": "GMAIL", "description": "Send emails"},
    ],
    "monitor_competitor": [
        {"name": "Google Alerts", "app": "GOOGLE_ALERTS", "description": "Competitor monitoring"},
        {"name": "Mention", "app": "MENTION", "description": "Brand monitoring"},
    ],
    "track_patents": [
        {"name": "Google Patents", "app": "GOOGLE_PATENTS", "description": "Patent search"},
    ],
    "manage_tasks": [
        {"name": "Asana", "app": "ASANA", "description": "Task management"},
        {"name": "Linear", "app": "LINEAR", "description": "Project management"},
    ],
}


class EcosystemSearchService:
    """Searches external ecosystems for tools/skills when ARIA hits a capability gap.

    Search priority:
    1. Composio Tool Router (managed, production-grade, OAuth handled)
    2. MCP Registry (official, standardized)
    3. Smithery (broad community catalog)

    Results are cached for 7 days. Tenant whitelist is enforced.
    """

    def __init__(
        self,
        db_client: Any,
        tenant_config: Any = None,
    ) -> None:
        self._db = db_client
        self._tenant_config = tenant_config

    async def search_for_capability(
        self,
        capability_name: str,
        description: str,
        user_id: str,
    ) -> list[EcosystemResult]:
        """Search all allowed ecosystems for tools matching a capability need."""
        allowed_sources = (
            getattr(self._tenant_config, "allowed_ecosystem_sources", None)
            or ["composio"]
        )

        # Check cache first
        cached = await self._get_cached_results(capability_name)
        if cached:
            return [r for r in cached if r.source in allowed_sources]

        results: list[EcosystemResult] = []

        if "composio" in allowed_sources:
            results.extend(await self._search_composio(capability_name, description))

        if "mcp_registry" in allowed_sources:
            results.extend(await self._search_mcp_registry(capability_name, description))

        if "smithery" in allowed_sources:
            results.extend(await self._search_smithery(capability_name, description))

        # Cache results (best-effort)
        await self._cache_results(capability_name, results)

        return results

    async def _search_composio(
        self, capability_name: str, description: str
    ) -> list[EcosystemResult]:
        """Search Composio for managed toolkits. Falls back to static mapping."""
        try:
            try:
                from composio import ComposioToolSet

                toolset = ComposioToolSet()
                actions = toolset.find_actions_by_use_case(
                    use_case=description, limit=5
                )
                return [
                    EcosystemResult(
                        name=action.name,
                        source="composio",
                        description=getattr(action, "description", ""),
                        app=getattr(action, "app", None),
                        quality_estimate=0.85,
                        auth_type="oauth",
                        setup_time=30,
                    )
                    for action in actions
                ]
            except (ImportError, Exception):
                logger.info("Composio SDK unavailable, using static mapping")
                return self._static_composio_search(capability_name)
        except Exception:
            logger.warning("Composio search failed", exc_info=True)
            return []

    async def _search_mcp_registry(
        self, capability_name: str, description: str
    ) -> list[EcosystemResult]:
        """Search the official MCP Registry for community MCP servers."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://registry.modelcontextprotocol.io/v0/servers",
                    params={"q": description, "limit": 5},
                )
                if response.status_code == 200:
                    servers = response.json().get("servers", [])
                    return [
                        EcosystemResult(
                            name=s.get("name", "Unknown"),
                            source="mcp_registry",
                            description=s.get("description", ""),
                            url=s.get("url", ""),
                            author=s.get("author", ""),
                            quality_estimate=0.70,
                            auth_type="varies",
                            setup_time=120,
                            last_updated=s.get("updated_at"),
                        )
                        for s in servers[:5]
                    ]
            return []
        except Exception:
            logger.warning("MCP Registry search failed", exc_info=True)
            return []

    async def _search_smithery(
        self, capability_name: str, description: str
    ) -> list[EcosystemResult]:
        """Search Smithery for MCP servers."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://registry.smithery.ai/servers",
                    params={"q": description, "pageSize": 5},
                )
                if response.status_code == 200:
                    data = response.json()
                    servers = data.get("servers", data.get("results", []))
                    return [
                        EcosystemResult(
                            name=s.get("displayName", s.get("qualifiedName", "Unknown")),
                            source="smithery",
                            description=s.get("description", ""),
                            qualified_name=s.get("qualifiedName", ""),
                            quality_estimate=0.65,
                            auth_type="varies",
                            setup_time=180,
                            stars=s.get("stars", 0),
                        )
                        for s in servers[:5]
                    ]
            return []
        except Exception:
            logger.warning("Smithery search failed", exc_info=True)
            return []

    def _static_composio_search(self, capability_name: str) -> list[EcosystemResult]:
        """Static fallback mapping of capabilities to known Composio apps."""
        entries = _COMPOSIO_CAPABILITY_MAP.get(capability_name, [])
        return [
            EcosystemResult(
                name=e["name"],
                source="composio",
                description=e["description"],
                app=e.get("app"),
                quality_estimate=0.85,
                auth_type="oauth",
                setup_time=30,
            )
            for e in entries
        ]

    async def _get_cached_results(
        self, capability_name: str
    ) -> list[EcosystemResult] | None:
        """Check cache for recent results."""
        try:
            result = (
                self._db.table("ecosystem_search_cache")
                .select("*")
                .eq("capability_name", capability_name)
                .gt("expires_at", datetime.now(timezone.utc).isoformat())
                .execute()
            )
            if result.data:
                all_results: list[EcosystemResult] = []
                for row in result.data:
                    for r in row.get("results") or []:
                        r["source"] = row["search_source"]
                        all_results.append(EcosystemResult(**r))
                return all_results
        except Exception:
            logger.warning("Failed to check ecosystem cache", exc_info=True)
        return None

    async def _cache_results(
        self, capability_name: str, results: list[EcosystemResult]
    ) -> None:
        """Cache search results for 7 days."""
        try:
            for source in {r.source for r in results}:
                source_results = [
                    r.model_dump() for r in results if r.source == source
                ]
                self._db.table("ecosystem_search_cache").upsert({
                    "capability_name": capability_name,
                    "search_source": source,
                    "search_query": capability_name,
                    "results": source_results,
                    "result_count": len(source_results),
                }).execute()
        except Exception:
            logger.warning("Failed to cache ecosystem results", exc_info=True)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestEcosystemSearchService -v --no-header -x 2>&1 | tail -20`
Expected: 3 passed

**Step 5: Commit**

```bash
git add backend/src/services/ecosystem_search.py backend/tests/test_skill_creation.py
git commit -m "feat: add EcosystemSearchService with Composio/MCP/Smithery search and caching"
```

---

### Task 4: Skill Creation Engine

**Files:**
- Create: `backend/src/services/skill_creation.py`
- Test: `backend/tests/test_skill_creation.py` (append)

**Step 1: Write the failing tests for skill creation**

Append to `backend/tests/test_skill_creation.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestSkillCreationEngine -v --no-header -x 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.skill_creation'`

**Step 3: Write the implementation**

Create `backend/src/services/skill_creation.py`:

```python
"""Skill creation engine — ARIA builds her own skills when no tool exists.

Three types:
- prompt_chain: LLM-based, no code execution, safest
- api_wrapper: Wraps a public API with sandboxed Python
- composite_workflow: Chains existing capabilities into reusable workflow
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.models.capability import SkillCreationProposal

logger = logging.getLogger(__name__)


class SkillCreationEngine:
    """ARIA creates her own skills when no existing tool fills a capability gap."""

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def assess_creation_opportunity(
        self,
        capability_name: str,
        description: str,
        user_id: str,
    ) -> Optional[SkillCreationProposal]:
        """Determine if ARIA can create a skill for this capability gap.

        Returns a proposal with skill type, estimated quality, and preview.
        Returns None if creation isn't feasible or tenant disallows it.
        """
        # Check tenant config
        tenant_config = await self._get_tenant_config(user_id)
        if tenant_config and not tenant_config.get("allow_skill_creation", True):
            return None

        prompt = (
            "You are ARIA, an AI colleague for life sciences commercial teams.\n"
            f'A user needs the capability "{capability_name}": {description}\n\n'
            "No existing tool was found. Assess whether you can BUILD a skill.\n\n"
            "Consider:\n"
            "1. Is there a public API? (FDA, PubMed, USPTO, etc.)\n"
            "2. Can this be done by chaining existing capabilities?\n"
            "3. Can a structured LLM prompt template produce reliable results?\n\n"
            "Return JSON:\n"
            '{"can_create": true/false, "skill_type": "prompt_chain"|"api_wrapper"|"composite_workflow",\n'
            ' "confidence": 0.0-1.0, "skill_name": "name", "description": "what it does",\n'
            ' "estimated_quality": 0.0-1.0, "approach": "how to build it",\n'
            ' "public_api_url": "URL or null", "required_capabilities": [],\n'
            ' "reason_if_no": "why not or null"}'
        )

        try:
            response = await self._generate(prompt)
            assessment = json.loads(response.strip())
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to assess skill creation opportunity", exc_info=True)
            return None

        if not assessment.get("can_create", False):
            return None

        return SkillCreationProposal(**assessment)

    async def create_skill(
        self,
        proposal: SkillCreationProposal,
        user_id: str,
        tenant_id: str,
        goal_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new skill based on the proposal. Returns the DB record."""
        if proposal.skill_type == "prompt_chain":
            definition = await self._create_prompt_chain(proposal)
        elif proposal.skill_type == "api_wrapper":
            definition = await self._create_api_wrapper(proposal)
        elif proposal.skill_type == "composite_workflow":
            definition = await self._create_composite_workflow(proposal)
        else:
            raise ValueError(f"Unknown skill type: {proposal.skill_type}")

        skill_record: dict[str, Any] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "skill_name": proposal.skill_name,
            "display_name": proposal.skill_name.replace("_", " ").title(),
            "description": proposal.description,
            "skill_type": proposal.skill_type,
            "created_from_capability_gap": None,
            "created_from_goal_id": goal_id,
            "creation_reasoning": proposal.approach,
            "definition": definition,
            "generated_code": definition.get("code") if proposal.skill_type == "api_wrapper" else None,
            "status": "draft",
            "trust_level": "LOW",
        }

        if skill_record.get("generated_code"):
            skill_record["code_hash"] = hashlib.sha256(
                skill_record["generated_code"].encode()
            ).hexdigest()

        result = self._db.table("aria_generated_skills").insert(skill_record).execute()
        return result.data[0] if result.data else skill_record

    async def test_skill_in_sandbox(
        self, skill_id: str, test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Test a generated skill in sandbox environment.

        Returns: {passed: bool, output: Any, errors: list, execution_time_ms: int}
        """
        skill_result = (
            self._db.table("aria_generated_skills")
            .select("*")
            .eq("id", skill_id)
            .single()
            .execute()
        )
        skill = skill_result.data

        start_time = datetime.now(timezone.utc)
        errors: list[str] = []
        output = None

        try:
            if skill["skill_type"] == "prompt_chain":
                output = await self._test_prompt_chain(skill["definition"], test_input)
            elif skill["skill_type"] == "api_wrapper":
                output = await self._test_api_wrapper(skill, test_input)
            elif skill["skill_type"] == "composite_workflow":
                output = await self._test_composite(skill["definition"], test_input)
        except Exception as e:
            errors.append(str(e))

        elapsed_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )
        passed = len(errors) == 0 and output is not None

        # Update skill record
        try:
            (
                self._db.table("aria_generated_skills")
                .update({
                    "sandbox_test_passed": passed,
                    "sandbox_test_output": {"output": output, "errors": errors},
                    "sandbox_tested_at": datetime.now(timezone.utc).isoformat(),
                    "status": "tested" if passed else "draft",
                })
                .eq("id", skill_id)
                .execute()
            )
        except Exception:
            logger.warning("Failed to update skill sandbox test results", exc_info=True)

        return {
            "passed": passed,
            "output": output,
            "errors": errors,
            "execution_time_ms": elapsed_ms,
        }

    # ------------------------------------------------------------------
    # Private: skill definition generators
    # ------------------------------------------------------------------

    async def _create_prompt_chain(self, proposal: SkillCreationProposal) -> dict[str, Any]:
        """Generate a prompt chain skill definition."""
        prompt = (
            f"Create a prompt chain skill definition for: {proposal.description}\n\n"
            "Each step needs: name, prompt (use {variable} for inputs), "
            "output_schema, capability_required (or null), input_from (or null).\n\n"
            "Return JSON: {\"steps\": [...], \"input_schema\": {...}, \"output_schema\": {...}}\n"
            "Be specific. Life-sciences-aware. Include error handling in prompts."
        )
        response = await self._generate(prompt)
        return json.loads(response.strip())

    async def _create_api_wrapper(self, proposal: SkillCreationProposal) -> dict[str, Any]:
        """Generate a Python API wrapper skill."""
        prompt = (
            f"Create a Python API wrapper for: {proposal.description}\n"
            f"API URL: {proposal.public_api_url or 'determine from description'}\n\n"
            "Use httpx, async, error handling, type hints, under 100 lines.\n"
            "NO secrets or private API keys. Define an `execute(input_data)` function.\n\n"
            'Return JSON: {"code": "...", "api_url": "...", "allowed_domains": [...], '
            '"input_schema": {...}, "output_schema": {...}, "test_input": {...}}'
        )
        response = await self._generate(prompt)
        return json.loads(response.strip())

    async def _create_composite_workflow(self, proposal: SkillCreationProposal) -> dict[str, Any]:
        """Generate a composite workflow that chains existing capabilities."""
        prompt = (
            f"Create a composite workflow for: {proposal.description}\n"
            f"Available capabilities: {proposal.required_capabilities}\n\n"
            "Each step references an existing capability with data flow.\n\n"
            'Return JSON: {"steps": [...], "synthesis_prompt": "...", '
            '"trigger": null, "auto_execute": false, '
            '"input_schema": {...}, "output_schema": {...}}'
        )
        response = await self._generate(prompt)
        return json.loads(response.strip())

    # ------------------------------------------------------------------
    # Private: sandbox test runners
    # ------------------------------------------------------------------

    async def _test_prompt_chain(
        self, definition: dict[str, Any], test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute prompt chain steps with test data."""
        context = {**test_input}
        for step in definition.get("steps", []):
            prompt = step["prompt"]
            for key, value in context.items():
                if isinstance(value, str):
                    prompt = prompt.replace(f"{{{key}}}", value)

            response = await self._generate(prompt)
            try:
                step_output = json.loads(response.strip())
            except json.JSONDecodeError:
                step_output = {"raw": response.strip()}

            context[step["name"]] = step_output

        return context

    async def _test_api_wrapper(
        self, skill: dict[str, Any], test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Test API wrapper code — placeholder for full sandbox (Phase C)."""
        code = skill.get("generated_code", "")
        if not code:
            raise ValueError("No generated code found")
        # Full sandbox implementation deferred to Phase C
        raise NotImplementedError("API wrapper sandbox not yet implemented")

    async def _test_composite(
        self, definition: dict[str, Any], test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Dry-run composite workflow — verify step structure."""
        steps = definition.get("steps", [])
        if not steps:
            raise ValueError("Composite workflow has no steps")
        return {"dry_run": True, "steps_validated": len(steps)}

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    async def _generate(self, prompt: str) -> str:
        """Generate LLM response. Override in tests."""
        from src.core.llm import LLMClient, TaskType

        llm = LLMClient()
        return await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a skill engineering assistant. Output only valid JSON.",
            temperature=0.0,
            max_tokens=2000,
            task=TaskType.SKILL_EXECUTE,
            agent_id="skill_creation_engine",
        )

    async def _get_tenant_config(self, user_id: str) -> dict[str, Any] | None:
        """Load tenant config for skill creation permissions."""
        try:
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

            config_result = (
                self._db.table("tenant_capability_config")
                .select("*")
                .eq("tenant_id", profile_result.data["company_id"])
                .limit(1)
                .maybe_single()
                .execute()
            )
            return config_result.data if config_result.data else None
        except Exception:
            logger.warning("Failed to load tenant config", exc_info=True)
            return None
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestSkillCreationEngine -v --no-header -x 2>&1 | tail -20`
Expected: 7 passed

**Step 5: Commit**

```bash
git add backend/src/services/skill_creation.py backend/tests/test_skill_creation.py
git commit -m "feat: add SkillCreationEngine with prompt chain, API wrapper, and composite workflow generation"
```

---

### Task 5: Trust Graduation & Health Monitoring

**Files:**
- Create: `backend/src/services/skill_trust.py`
- Test: `backend/tests/test_skill_creation.py` (append)

**Step 1: Write the failing tests**

Append to `backend/tests/test_skill_creation.py`:

```python
# ---------------------------------------------------------------------------
# SkillTrustManager tests
# ---------------------------------------------------------------------------

class TestSkillTrustManager:
    """Tests for trust graduation and demotion."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_trust_graduation_low_to_medium(self, mock_db):
        """5 successes with 0 failures graduates LOW → MEDIUM."""
        from src.services.skill_trust import SkillTrustManager

        skill = {
            "id": "skill-001",
            "user_id": "user-1",
            "trust_level": "LOW",
            "execution_count": 4,
            "success_count": 4,
            "failure_count": 0,
            "avg_quality_score": 0.8,
            "status": "active",
        }

        chain = _setup_chain(mock_db, skill)
        chain.single.return_value = chain
        chain.execute.return_value = _mock_db_response(skill)

        manager = SkillTrustManager(mock_db)
        manager._get_tenant_config = AsyncMock(return_value=None)

        await manager.record_execution("skill-001", success=True, quality_score=0.85)

        # Verify update was called with MEDIUM trust level
        update_calls = mock_db.table.return_value.update.call_args_list
        assert len(update_calls) > 0
        update_data = update_calls[-1][0][0]
        assert update_data["trust_level"] == "MEDIUM"
        assert update_data["success_count"] == 5

    @pytest.mark.asyncio
    async def test_trust_graduation_blocked_by_tenant(self, mock_db):
        """Admin config blocks auto-graduation above MEDIUM."""
        from src.services.skill_trust import SkillTrustManager

        skill = {
            "id": "skill-001",
            "user_id": "user-1",
            "trust_level": "MEDIUM",
            "execution_count": 19,
            "success_count": 19,
            "failure_count": 0,
            "avg_quality_score": 0.9,
            "status": "graduated",
        }

        chain = _setup_chain(mock_db, skill)
        chain.single.return_value = chain
        chain.execute.return_value = _mock_db_response(skill)

        manager = SkillTrustManager(mock_db)
        # Tenant says max auto is MEDIUM (HIGH needs admin approval)
        manager._get_tenant_config = AsyncMock(
            return_value={"max_auto_trust_level": "MEDIUM"}
        )

        await manager.record_execution("skill-001", success=True, quality_score=0.95)

        # Verify trust_level was NOT auto-upgraded to HIGH
        update_calls = mock_db.table.return_value.update.call_args_list
        update_data = update_calls[-1][0][0]
        assert update_data.get("trust_level", "MEDIUM") != "HIGH"

        # Verify approval queue entry was created
        insert_calls = [
            c for c in mock_db.table.call_args_list
            if c[0][0] == "skill_approval_queue"
        ]
        assert len(insert_calls) > 0

    @pytest.mark.asyncio
    async def test_trust_demotion(self, mock_db):
        """3 consecutive failures demotes trust level."""
        from src.services.skill_trust import SkillTrustManager

        skill = {
            "id": "skill-001",
            "user_id": "user-1",
            "trust_level": "MEDIUM",
            "execution_count": 10,
            "success_count": 8,
            "failure_count": 2,
            "avg_quality_score": 0.7,
            "status": "graduated",
        }

        chain = _setup_chain(mock_db, skill)
        chain.single.return_value = chain

        # First execute() returns the skill, subsequent calls return various results
        call_count = 0
        original_execute = chain.execute

        def side_effect_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_response(skill)
            # Return 3 recent failures for demotion check
            return _mock_db_response([
                {"metadata": {"success": False}},
                {"metadata": {"success": False}},
                {"metadata": {"success": False}},
            ])

        chain.execute = MagicMock(side_effect=side_effect_execute)

        manager = SkillTrustManager(mock_db)
        manager._get_tenant_config = AsyncMock(return_value=None)

        await manager.record_execution("skill-001", success=False, quality_score=0.3)

        # Verify trust demoted from MEDIUM to LOW
        update_calls = mock_db.table.return_value.update.call_args_list
        update_data = update_calls[-1][0][0]
        assert update_data["trust_level"] == "LOW"


# ---------------------------------------------------------------------------
# SkillHealthMonitor tests
# ---------------------------------------------------------------------------

class TestSkillHealthMonitor:
    """Tests for skill health monitoring."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_skill_health_degraded(self, mock_db):
        """>15% error rate marks skill degraded."""
        from src.services.skill_trust import SkillHealthMonitor

        skills_data = [{
            "id": "skill-001",
            "user_id": "user-1",
            "display_name": "FDA Lookup",
            "skill_name": "fda_lookup",
            "status": "active",
        }]

        # Recent executions: 2 failures out of 10 = 20% error rate
        audit_data = [
            {"metadata": {"success": True}} for _ in range(8)
        ] + [
            {"metadata": {"success": False}} for _ in range(2)
        ]

        call_count = 0

        def side_effect_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_response(skills_data)
            elif call_count == 2:
                return _mock_db_response(audit_data)
            return _mock_db_response([])

        chain = _setup_chain(mock_db, [])
        chain.execute = MagicMock(side_effect=side_effect_execute)

        mock_pulse = AsyncMock()
        monitor = SkillHealthMonitor(mock_db, pulse_engine=mock_pulse)

        await monitor.check_all_active_skills()

        # Verify skill updated with degraded status
        update_calls = mock_db.table.return_value.update.call_args_list
        assert len(update_calls) > 0
        update_data = update_calls[0][0][0]
        assert update_data["health_status"] == "degraded"

        # Verify pulse signal generated
        mock_pulse.process_signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_health_broken_auto_disable(self, mock_db):
        """>50% error rate disables skill."""
        from src.services.skill_trust import SkillHealthMonitor

        skills_data = [{
            "id": "skill-002",
            "user_id": "user-1",
            "display_name": "Broken Skill",
            "skill_name": "broken_skill",
            "status": "active",
        }]

        # 6 failures out of 10 = 60% error rate
        audit_data = [
            {"metadata": {"success": True}} for _ in range(4)
        ] + [
            {"metadata": {"success": False}} for _ in range(6)
        ]

        call_count = 0

        def side_effect_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_response(skills_data)
            elif call_count == 2:
                return _mock_db_response(audit_data)
            return _mock_db_response([])

        chain = _setup_chain(mock_db, [])
        chain.execute = MagicMock(side_effect=side_effect_execute)

        mock_pulse = AsyncMock()
        monitor = SkillHealthMonitor(mock_db, pulse_engine=mock_pulse)

        await monitor.check_all_active_skills()

        # Verify skill updated with broken status AND disabled
        update_calls = mock_db.table.return_value.update.call_args_list
        # First update: health_status = broken
        # Second update: status = disabled
        update_data_all = [c[0][0] for c in update_calls]
        health_updates = [d for d in update_data_all if "health_status" in d]
        status_updates = [d for d in update_data_all if d.get("status") == "disabled"]
        assert len(health_updates) > 0
        assert health_updates[0]["health_status"] == "broken"
        assert len(status_updates) > 0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestSkillTrustManager -v --no-header -x 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.skill_trust'`

**Step 3: Write the implementation**

Create `backend/src/services/skill_trust.py`:

```python
"""Skill trust graduation and health monitoring.

- SkillTrustManager: Records executions, graduates trust (LOW→MEDIUM→HIGH),
  demotes on consecutive failures.
- SkillHealthMonitor: Scheduled job checks error rates, marks degraded/broken,
  auto-disables broken skills.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TRUST_ORDER = ["LOW", "MEDIUM", "HIGH"]


class SkillTrustManager:
    """Manages trust graduation for ARIA-generated skills.

    LOW → MEDIUM: 5 successful executions, 0 failures
    MEDIUM → HIGH: 20 successful executions, <5% error rate
    Demotion: 3 consecutive failures → downgrade one level
    """

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def record_execution(
        self, skill_id: str, success: bool, quality_score: float
    ) -> None:
        """Record a skill execution and check for trust graduation/demotion."""
        skill_result = (
            self._db.table("aria_generated_skills")
            .select("*")
            .eq("id", skill_id)
            .single()
            .execute()
        )
        skill = skill_result.data

        updates: dict[str, Any] = {
            "execution_count": skill["execution_count"] + 1,
            "last_executed_at": datetime.now(timezone.utc).isoformat(),
        }

        if success:
            updates["success_count"] = skill["success_count"] + 1
        else:
            updates["failure_count"] = skill["failure_count"] + 1

        # Running average quality score
        prev_avg = skill.get("avg_quality_score") or quality_score
        prev_count = skill.get("execution_count", 0) or 1
        updates["avg_quality_score"] = (
            (prev_avg * prev_count + quality_score) / (prev_count + 1)
        )

        # Check trust graduation
        new_trust = self._check_graduation(skill, updates)
        if new_trust and new_trust != skill["trust_level"]:
            tenant_config = await self._get_tenant_config(skill["user_id"])
            max_auto = (tenant_config or {}).get("max_auto_trust_level", "MEDIUM")

            if _TRUST_ORDER.index(new_trust) <= _TRUST_ORDER.index(max_auto):
                updates["trust_level"] = new_trust
                if new_trust in ("MEDIUM", "HIGH"):
                    updates["status"] = "graduated"
            else:
                await self._request_approval(skill, "trust_graduation", new_trust)

        # Check for trust demotion (3 consecutive failures)
        if not success:
            try:
                recent = (
                    self._db.table("skill_audit_log")
                    .select("metadata")
                    .eq("skill_id", skill_id)
                    .order("timestamp", desc=True)
                    .limit(3)
                    .execute()
                )
                recent_failures = sum(
                    1
                    for r in (recent.data or [])
                    if (r.get("metadata") or {}).get("success") is False
                )
                if recent_failures >= 3:
                    current_idx = _TRUST_ORDER.index(skill["trust_level"])
                    if current_idx > 0:
                        updates["trust_level"] = _TRUST_ORDER[current_idx - 1]
                        logger.warning(
                            "Skill %s trust demoted to %s",
                            skill_id,
                            updates["trust_level"],
                        )
            except Exception:
                logger.warning("Failed to check demotion for %s", skill_id, exc_info=True)

        (
            self._db.table("aria_generated_skills")
            .update(updates)
            .eq("id", skill_id)
            .execute()
        )

    def _check_graduation(
        self, skill: dict[str, Any], updates: dict[str, Any]
    ) -> Optional[str]:
        """Check if skill qualifies for trust graduation."""
        total_success = updates.get("success_count", skill["success_count"])
        total_fail = updates.get("failure_count", skill["failure_count"])
        total = total_success + total_fail

        if total == 0:
            return None

        error_rate = total_fail / total

        if skill["trust_level"] == "LOW" and total_success >= 5 and total_fail == 0:
            return "MEDIUM"
        elif skill["trust_level"] == "MEDIUM" and total_success >= 20 and error_rate < 0.05:
            return "HIGH"

        return None

    async def _request_approval(
        self, skill: dict[str, Any], approval_type: str, requested_trust: str
    ) -> None:
        """Create approval queue entry for admin review."""
        try:
            self._db.table("skill_approval_queue").insert({
                "skill_id": skill["id"],
                "tenant_id": skill["tenant_id"],
                "requested_by": skill["user_id"],
                "approval_type": approval_type,
                "current_trust_level": skill["trust_level"],
                "requested_trust_level": requested_trust,
                "justification": (
                    f"Skill '{skill.get('display_name', skill['id'])}' has "
                    f"{skill['success_count']} successes with "
                    f"{skill['failure_count']} failures."
                ),
            }).execute()
        except Exception:
            logger.warning("Failed to create approval queue entry", exc_info=True)

    async def _get_tenant_config(self, user_id: str) -> dict[str, Any] | None:
        """Load tenant config for trust graduation limits."""
        try:
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

            config_result = (
                self._db.table("tenant_capability_config")
                .select("*")
                .eq("tenant_id", profile_result.data["company_id"])
                .limit(1)
                .maybe_single()
                .execute()
            )
            return config_result.data if config_result.data else None
        except Exception:
            logger.warning("Failed to load tenant config", exc_info=True)
            return None


class SkillHealthMonitor:
    """Monitors health of ARIA-generated skills. Runs as scheduled job.

    Checks error rate from skill_audit_log over last 7 days.
    >15% error rate → degraded (pulse signal generated)
    >50% error rate → broken (auto-disable, find replacement)
    """

    def __init__(self, db_client: Any, pulse_engine: Any = None) -> None:
        self._db = db_client
        self._pulse = pulse_engine

    async def check_all_active_skills(self) -> None:
        """Health check all active and graduated skills."""
        try:
            skills_result = (
                self._db.table("aria_generated_skills")
                .select("*")
                .in_("status", ["active", "graduated"])
                .execute()
            )
        except Exception:
            logger.exception("Failed to query active skills for health check")
            return

        for skill in skills_result.data or []:
            health = await self._assess_health(skill)

            try:
                (
                    self._db.table("aria_generated_skills")
                    .update({
                        "health_status": health["status"],
                        "error_rate_7d": health["error_rate_7d"],
                        "last_health_check": datetime.now(timezone.utc).isoformat(),
                    })
                    .eq("id", skill["id"])
                    .execute()
                )
            except Exception:
                logger.warning("Failed to update health for skill %s", skill["id"])

            if health["status"] == "degraded" and self._pulse:
                try:
                    await self._pulse.process_signal(
                        user_id=skill["user_id"],
                        signal={
                            "pulse_type": "skill_health",
                            "source": "skill_health_monitor",
                            "title": f"Skill '{skill['display_name']}' performance degraded",
                            "content": (
                                f"Error rate: {health['error_rate_7d']:.0%} (was <5%). "
                                f"I'm looking for alternatives or can rebuild this skill."
                            ),
                            "signal_category": "capability",
                        },
                    )
                except Exception:
                    logger.warning("Failed to send pulse for degraded skill %s", skill["id"])

            elif health["status"] == "broken":
                try:
                    (
                        self._db.table("aria_generated_skills")
                        .update({"status": "disabled"})
                        .eq("id", skill["id"])
                        .execute()
                    )
                except Exception:
                    logger.warning("Failed to disable broken skill %s", skill["id"])

    async def _assess_health(self, skill: dict[str, Any]) -> dict[str, Any]:
        """Assess skill health from recent execution data."""
        seven_days_ago = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).isoformat()
        try:
            recent = (
                self._db.table("skill_audit_log")
                .select("metadata")
                .eq("skill_id", skill.get("skill_name", skill["id"]))
                .gte("timestamp", seven_days_ago)
                .execute()
            )
        except Exception:
            return {"status": "unknown", "error_rate_7d": 0}

        if not recent.data:
            return {"status": "unknown", "error_rate_7d": 0}

        total = len(recent.data)
        failures = sum(
            1
            for r in recent.data
            if not (r.get("metadata") or {}).get("success", True)
        )
        error_rate = failures / total if total > 0 else 0

        if error_rate > 0.5:
            return {"status": "broken", "error_rate_7d": error_rate}
        elif error_rate > 0.15:
            return {"status": "degraded", "error_rate_7d": error_rate}
        else:
            return {"status": "healthy", "error_rate_7d": error_rate}
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestSkillTrustManager backend/tests/test_skill_creation.py::TestSkillHealthMonitor -v --no-header -x 2>&1 | tail -30`
Expected: 5 passed

**Step 5: Commit**

```bash
git add backend/src/services/skill_trust.py backend/tests/test_skill_creation.py
git commit -m "feat: add SkillTrustManager (graduation/demotion) and SkillHealthMonitor"
```

---

### Task 6: Wire Ecosystem Search + Skill Creation into Resolution Engine

**Files:**
- Modify: `backend/src/services/capability_provisioning.py:135-239` (ResolutionEngine class)
- Modify: `backend/src/models/capability.py` (add creation_proposal field to ResolutionStrategy)
- Test: `backend/tests/test_skill_creation.py` (append)

**Step 1: Write the failing tests**

Append to `backend/tests/test_skill_creation.py`:

```python
# ---------------------------------------------------------------------------
# Resolution Engine integration tests
# ---------------------------------------------------------------------------

class TestResolutionEnginePhaseB:
    """Tests for ecosystem + creation strategies in ResolutionEngine."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_resolution_engine_includes_ecosystem(self, mock_db):
        """Ecosystem results appear in strategies."""
        from src.services.capability_provisioning import CapabilityGraphService, ResolutionEngine
        from src.services.ecosystem_search import EcosystemSearchService

        _setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        graph._check_user_connection = AsyncMock(return_value=False)

        engine = ResolutionEngine(mock_db, graph)
        engine._get_tenant_config = AsyncMock(return_value=None)

        # Mock ecosystem search
        mock_ecosystem = AsyncMock()
        mock_ecosystem.search_for_capability = AsyncMock(return_value=[
            EcosystemResult(
                name="Salesforce",
                source="composio",
                description="CRM data",
                quality_estimate=0.85,
                final_score=0.80,
                setup_time=30,
            ),
        ])
        engine._ecosystem_search = mock_ecosystem
        engine._skill_creation = AsyncMock()
        engine._skill_creation.assess_creation_opportunity = AsyncMock(return_value=None)

        strategies = await engine.generate_strategies(
            "read_crm_pipeline", "user-1", []
        )

        ecosystem_strategies = [
            s for s in strategies if s.strategy_type == "ecosystem_discovered"
        ]
        assert len(ecosystem_strategies) >= 1
        assert ecosystem_strategies[0].provider_name == "Salesforce"

    @pytest.mark.asyncio
    async def test_resolution_engine_includes_creation(self, mock_db):
        """Skill creation appears when feasible."""
        from src.services.capability_provisioning import CapabilityGraphService, ResolutionEngine

        _setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        engine = ResolutionEngine(mock_db, graph)
        engine._get_tenant_config = AsyncMock(return_value=None)

        # Mock: no ecosystem results
        mock_ecosystem = AsyncMock()
        mock_ecosystem.search_for_capability = AsyncMock(return_value=[])
        engine._ecosystem_search = mock_ecosystem

        # Mock: creation is feasible
        mock_creation = AsyncMock()
        mock_creation.assess_creation_opportunity = AsyncMock(
            return_value=SkillCreationProposal(
                can_create=True,
                skill_type="prompt_chain",
                confidence=0.8,
                skill_name="patent_tracker",
                description="Track patent filings",
                estimated_quality=0.70,
                approach="Use LLM prompts with USPTO data",
            )
        )
        engine._skill_creation = mock_creation

        strategies = await engine.generate_strategies(
            "track_patents", "user-1", []
        )

        creation_strategies = [
            s for s in strategies if s.strategy_type == "skill_creation"
        ]
        assert len(creation_strategies) == 1
        assert "patent_tracker" in creation_strategies[0].provider_name
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py::TestResolutionEnginePhaseB -v --no-header -x 2>&1 | tail -20`
Expected: FAIL — ecosystem/creation attributes don't exist on ResolutionEngine

**Step 3: Add `creation_proposal` field to ResolutionStrategy model**

In `backend/src/models/capability.py`, modify the `ResolutionStrategy` class (at line 38-52) to add the field:

```python
class ResolutionStrategy(BaseModel):
    """A ranked strategy for filling a capability gap."""

    strategy_type: str  # direct_integration, composite, ecosystem_discovered, skill_creation, user_provided, web_fallback
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
    creation_proposal: Optional[Any] = None  # SkillCreationProposal when strategy_type == 'skill_creation'
```

**Step 4: Update ResolutionEngine to wire in ecosystem search and skill creation**

In `backend/src/services/capability_provisioning.py`, modify `ResolutionEngine.__init__` (line 138) and `generate_strategies` (lines 142-239):

Replace lines 135-296 with:

```python
class ResolutionEngine:
    """Generates ranked resolution strategies for capability gaps."""

    def __init__(
        self,
        db_client: Any,
        capability_graph: CapabilityGraphService,
        ecosystem_search: Any = None,
        skill_creation: Any = None,
    ) -> None:
        self._db = db_client
        self._graph = capability_graph
        self._ecosystem_search = ecosystem_search
        self._skill_creation = skill_creation

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
        3. ecosystem_discovered — Search external ecosystems
        4. skill_creation — ARIA builds a new skill
        5. user_provided — Ask the user
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

        # Strategy 3: Ecosystem search (Phase B)
        if self._ecosystem_search:
            try:
                ecosystem_results = await self._ecosystem_search.search_for_capability(
                    capability_name,
                    f"Tool for {capability_name} in life sciences context",
                    user_id,
                )
                for result in ecosystem_results[:2]:
                    strategies.append(
                        ResolutionStrategy(
                            strategy_type="ecosystem_discovered",
                            provider_name=result.name,
                            quality=result.final_score,
                            setup_time_seconds=result.setup_time,
                            user_friction="low",
                            description=f"Found in {result.source}: {result.description}",
                            action_label=f"Connect {result.name}",
                            ecosystem_source=result.source,
                            ecosystem_data=result.model_dump(),
                        )
                    )
            except Exception:
                logger.warning("Ecosystem search failed in resolution engine", exc_info=True)
        else:
            # Fallback: static Composio search (Phase A behavior)
            if tenant_config is None or "composio" in (
                getattr(tenant_config, "allowed_ecosystem_sources", None) or ["composio"]
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

        # Strategy 4: Skill creation (Phase B)
        if self._skill_creation:
            try:
                creation_proposal = await self._skill_creation.assess_creation_opportunity(
                    capability_name,
                    f"Need to {capability_name} for life sciences commercial goals",
                    user_id,
                )
                if creation_proposal and creation_proposal.confidence >= 0.6:
                    strategies.append(
                        ResolutionStrategy(
                            strategy_type="skill_creation",
                            provider_name=f"aria_create_{creation_proposal.skill_name}",
                            quality=creation_proposal.estimated_quality,
                            setup_time_seconds=120,
                            user_friction="low",
                            description=f"I can build: {creation_proposal.description}",
                            action_label=f"Create {creation_proposal.skill_name.replace('_', ' ').title()}",
                            creation_proposal=creation_proposal,
                        )
                    )
            except Exception:
                logger.warning("Skill creation assessment failed in resolution engine", exc_info=True)

        # Strategy 5: User-provided (always available)
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

            from types import SimpleNamespace
            return SimpleNamespace(**config_result.data)
        except Exception:
            logger.warning(
                "Failed to load tenant capability config",
                extra={"user_id": user_id},
            )
            return None

    def _search_composio_tools(self, capability_name: str) -> list[dict[str, Any]]:
        """Map capability names to known Composio toolkit names (Phase A fallback)."""
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

Also update the `annotate_plan_with_gaps` function (line 614-649) to wire in the new services:

```python
async def annotate_plan_with_gaps(
    plan_dict: dict[str, Any],
    user_id: str,
    db_client: Any,
) -> dict[str, Any]:
    """Annotate an execution plan dict with capability gap information."""
    try:
        from src.services.ecosystem_search import EcosystemSearchService
        from src.services.skill_creation import SkillCreationEngine

        graph = CapabilityGraphService(db_client)

        # Try to create Phase B services; fall back gracefully
        try:
            tenant_config_result = (
                db_client.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            company_id = (tenant_config_result.data or {}).get("company_id")
            tenant_config = None
            if company_id:
                tc_result = (
                    db_client.table("tenant_capability_config")
                    .select("*")
                    .eq("tenant_id", company_id)
                    .limit(1)
                    .maybe_single()
                    .execute()
                )
                if tc_result.data:
                    from types import SimpleNamespace
                    tenant_config = SimpleNamespace(**tc_result.data)

            ecosystem = EcosystemSearchService(db_client, tenant_config=tenant_config)
            creation = SkillCreationEngine(db_client)
        except Exception:
            ecosystem = None
            creation = None

        engine = ResolutionEngine(
            db_client, graph,
            ecosystem_search=ecosystem,
            skill_creation=creation,
        )
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
        plan_dict.setdefault("capability_gaps", [])
        plan_dict.setdefault("has_blocking_gaps", False)
        plan_dict.setdefault("has_degraded_gaps", False)

    return plan_dict
```

**Step 5: Run all tests to verify everything passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py backend/tests/test_capability_provisioning.py -v --no-header 2>&1 | tail -40`
Expected: All tests pass (existing Phase A tests + new Phase B tests)

**Step 6: Commit**

```bash
git add backend/src/models/capability.py backend/src/services/capability_provisioning.py backend/tests/test_skill_creation.py
git commit -m "feat: wire ecosystem search and skill creation into ResolutionEngine"
```

---

### Task 7: Scheduler Jobs — Health Monitor + Cache Cleanup

**Files:**
- Modify: `backend/src/services/scheduler.py:1218-1287` (add new job functions)
- Modify: `backend/src/services/scheduler.py:1576-1589` (register new jobs)

**Step 1: Add the new scheduler functions**

After `_run_capability_demand_check()` (line 1287), add:

```python

async def _run_skill_health_check() -> None:
    """Check health of ARIA-generated skills every 6 hours."""
    try:
        from src.db.supabase import SupabaseClient
        from src.services.intelligence_pulse import get_pulse_engine
        from src.services.skill_trust import SkillHealthMonitor

        db = SupabaseClient.get_client()
        pulse_engine = get_pulse_engine()
        monitor = SkillHealthMonitor(db, pulse_engine=pulse_engine)
        await monitor.check_all_active_skills()
    except Exception:
        logger.exception("Skill health check scheduler run failed")


async def _cleanup_expired_ecosystem_cache() -> None:
    """Remove expired ecosystem search cache entries daily."""
    try:
        from datetime import datetime, timezone

        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        (
            db.table("ecosystem_search_cache")
            .delete()
            .lt("expires_at", datetime.now(timezone.utc).isoformat())
            .execute()
        )
        logger.info("Expired ecosystem search cache cleaned")
    except Exception:
        logger.exception("Ecosystem cache cleanup failed")
```

**Step 2: Register the new jobs**

After the `capability_demand_check` job registration (line 1582), add:

```python
        _scheduler.add_job(
            _run_skill_health_check,
            trigger=CronTrigger(hour="*/6"),
            id="skill_health_check",
            name="Check health of ARIA-generated skills",
            replace_existing=True,
        )
        _scheduler.add_job(
            _cleanup_expired_ecosystem_cache,
            trigger=CronTrigger(hour=3, minute=0),
            id="ecosystem_cache_cleanup",
            name="Clean expired ecosystem search cache",
            replace_existing=True,
        )
```

**Step 3: Run existing scheduler-related tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py backend/tests/test_capability_provisioning.py -v --no-header 2>&1 | tail -30`
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/src/services/scheduler.py
git commit -m "feat: add skill health monitor and ecosystem cache cleanup scheduler jobs"
```

---

### Task 8: Final Verification — Run All Tests

**Step 1: Run the full Phase B test suite**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_creation.py -v --no-header 2>&1 | tail -40`

Expected output should show 16 tests passing:
- `TestSkillCreationModels` — 2 tests
- `TestEcosystemSearchService` — 3 tests
- `TestSkillCreationEngine` — 7 tests
- `TestSkillTrustManager` — 3 tests
- `TestSkillHealthMonitor` — 2 tests
- `TestResolutionEnginePhaseB` — 2 tests

Note: Some tests may need adjustment during implementation if mock patterns don't align with the actual DB client. Fix any assertion errors by adjusting mock setup, not by changing business logic.

**Step 2: Run Phase A tests to ensure no regressions**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_capability_provisioning.py -v --no-header 2>&1 | tail -30`
Expected: All 12 Phase A tests still pass

**Step 3: Final commit if any test fixes were needed**

```bash
git add -A
git commit -m "fix: adjust test mocks for Phase B integration"
```

---

## File Summary

### New files (4)
| File | Purpose |
|------|---------|
| `backend/supabase/migrations/20260301110000_skill_creation_governance.sql` | 4 tables: ecosystem_search_cache, aria_generated_skills, skill_approval_queue, published_skills |
| `backend/src/services/ecosystem_search.py` | EcosystemSearchService — Composio/MCP/Smithery search with caching |
| `backend/src/services/skill_creation.py` | SkillCreationEngine — prompt chain, API wrapper, composite workflow generation |
| `backend/src/services/skill_trust.py` | SkillTrustManager + SkillHealthMonitor — trust graduation and health checks |

### Modified files (3)
| File | Changes |
|------|---------|
| `backend/src/models/capability.py` | Add EcosystemResult, SkillCreationProposal models; add creation_proposal field to ResolutionStrategy |
| `backend/src/services/capability_provisioning.py` | Wire ecosystem_search and skill_creation into ResolutionEngine; update annotate_plan_with_gaps |
| `backend/src/services/scheduler.py` | Add _run_skill_health_check and _cleanup_expired_ecosystem_cache jobs |

### Test files (1)
| File | Tests |
|------|-------|
| `backend/tests/test_skill_creation.py` | 16 tests across 6 test classes |
