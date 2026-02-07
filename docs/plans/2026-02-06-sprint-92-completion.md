# Sprint 9.2 Completion — Fix Remaining Gaps

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the 3 remaining gaps in Sprint 9.2: fix the `memory_prospective` table name bug (US-912), implement real readiness score calculations (US-913), and add Strategist agent activation (US-915).

**Architecture:** All changes are additive/corrective to existing well-tested services. US-912 is a string rename across 9 files. US-913 replaces 5 placeholder methods with real Supabase queries. US-915 adds one new activation method following the existing pattern.

**Tech Stack:** Python 3.11+ / FastAPI / Supabase / pytest / TDD

---

## Task 1: Fix `memory_prospective` → `prospective_memories` table name (US-912)

**Files:**
- Modify: `backend/src/onboarding/gap_detector.py` (lines 416, 440)
- Modify: `backend/src/onboarding/first_goal.py` (line 746)
- Modify: `backend/src/onboarding/first_conversation.py` (line 512)
- Modify: `backend/src/onboarding/enrichment.py` (line 830)
- Modify: `backend/src/onboarding/email_bootstrap.py` (line 692)
- Modify: `backend/tests/test_first_conversation.py` (line 137)
- Modify: `backend/tests/onboarding/test_email_bootstrap.py` (lines 629, 636)
- Modify: `backend/tests/test_enrichment_engine.py` (lines 1073, 1128)
- Modify: `docs/ARIA_PRD.md` (line 131)

**Step 1: Run existing tests to confirm green baseline**

```bash
cd backend
python3 -m pytest tests/test_gap_detector.py tests/test_first_conversation.py tests/test_enrichment_engine.py -v --tb=short
```

Expected: All pass (these tests mock the DB, so the wrong table name doesn't cause test failures — but it will fail at runtime).

**Step 2: Apply the fix across all source files**

In each file, replace `"memory_prospective"` with `"prospective_memories"`. There are exactly 5 source files:

`backend/src/onboarding/gap_detector.py`:
- Line 416 (docstring): `memory_prospective` → `prospective_memories`
- Line 440 (code): `.table("memory_prospective")` → `.table("prospective_memories")`

`backend/src/onboarding/first_goal.py`:
- Line 746: `.table("memory_prospective")` → `.table("prospective_memories")`

`backend/src/onboarding/first_conversation.py`:
- Line 512: `.table("memory_prospective")` → `.table("prospective_memories")`

`backend/src/onboarding/enrichment.py`:
- Line 830: `.table("memory_prospective")` → `.table("prospective_memories")`

`backend/src/onboarding/email_bootstrap.py`:
- Line 692: `.table("memory_prospective")` → `.table("prospective_memories")`

**Step 3: Apply the fix across all test files**

`backend/tests/test_first_conversation.py`:
- Line 137: `"memory_prospective"` → `"prospective_memories"`

`backend/tests/onboarding/test_email_bootstrap.py`:
- Line 629 (docstring): `memory_prospective` → `prospective_memories`
- Line 636 (assertion): `"memory_prospective"` → `"prospective_memories"`

`backend/tests/test_enrichment_engine.py`:
- Line 1073 (docstring): `memory_prospective` → `prospective_memories`
- Line 1128 (assertion): `"memory_prospective"` → `"prospective_memories"`

**Step 4: Fix documentation**

`docs/ARIA_PRD.md`:
- Line 131: `memory_prospective` → `prospective_memories`

**Step 5: Run all affected tests**

```bash
cd backend
python3 -m pytest tests/test_gap_detector.py tests/test_first_conversation.py tests/test_enrichment_engine.py tests/onboarding/test_email_bootstrap.py -v --tb=short
```

Expected: All pass.

**Step 6: Verify no remaining references**

```bash
cd backend
grep -rn "memory_prospective" src/ tests/ ../docs/
```

Expected: Zero results.

**Step 7: Commit**

```bash
git add backend/src/onboarding/gap_detector.py backend/src/onboarding/first_goal.py backend/src/onboarding/first_conversation.py backend/src/onboarding/enrichment.py backend/src/onboarding/email_bootstrap.py backend/tests/test_first_conversation.py backend/tests/onboarding/test_email_bootstrap.py backend/tests/test_enrichment_engine.py docs/ARIA_PRD.md
git commit -m "fix: rename memory_prospective to prospective_memories across onboarding modules

The migration creates 'prospective_memories' but 5 onboarding modules
referenced the incorrect table name 'memory_prospective'. This would
cause runtime failures on any code path that creates prospective
memory entries (gap detection, enrichment, email bootstrap, first
goal, first conversation).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Add Strategist agent activation (US-915)

**Files:**
- Modify: `backend/src/onboarding/activation.py`
- Modify: `backend/tests/test_activation.py`

**Step 1: Write the failing test for Strategist activation**

Add to `backend/tests/test_activation.py` inside `TestOnboardingCompletionOrchestrator`:

```python
@pytest.mark.asyncio
async def test_activate_includes_strategist(self, activator, mock_goal_service):
    """Strategist agent is activated when user has an active goal."""
    mock_goal_service.create_goal.side_effect = [
        {"id": "goal-1"},  # Scout
        {"id": "goal-2"},  # Analyst
        {"id": "goal-3"},  # Hunter
        {"id": "goal-4"},  # Operator
        {"id": "goal-5"},  # Scribe
        {"id": "goal-6"},  # Strategist
    ]

    onboarding_data = {
        "company_id": "company-123",
        "company_discovery": {"website": "example.com"},
        "enrichment": {"competitors": ["c1.com"]},
        "integration_wizard": {"crm_connected": True, "email_connected": True},
        "first_goal": {"goal_type": "lead_gen", "description": "Generate leads"},
    }

    with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
        result = await activator.activate("user-123", onboarding_data)

    assert result["activations"]["strategist"] is not None
    assert "goal_id" in result["activations"]["strategist"]


@pytest.mark.asyncio
async def test_activate_strategist_without_goal_still_activates(self, activator, mock_goal_service):
    """Strategist activates even without explicit goal — creates strategy assessment goal."""
    mock_goal_service.create_goal.side_effect = [
        {"id": "goal-1"},  # Scout
        {"id": "goal-2"},  # Strategist
    ]

    onboarding_data = {
        "company_id": "company-123",
        "company_discovery": {"website": "example.com"},
        "enrichment": {},
        "integration_wizard": {"crm_connected": False, "email_connected": False},
        "first_goal": {},
    }

    with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
        result = await activator.activate("user-123", onboarding_data)

    assert result["activations"]["strategist"] is not None
```

**Step 2: Run test to verify it fails**

```bash
cd backend
python3 -m pytest tests/test_activation.py::TestOnboardingCompletionOrchestrator::test_activate_includes_strategist -v
```

Expected: FAIL — `result["activations"]["strategist"]` → KeyError

**Step 3: Implement `_activate_strategist` in `activation.py`**

Add `"strategist": None` to the `activations` dict in `activate()` (after line 66).

Add the call in `activate()` (after the Scribe block, before `_record_activation_event`):

```python
# Strategist: Build go-to-market and account strategy
activations["strategist"] = await self._activate_strategist(user_id, onboarding_data)
```

Add the method (after `_activate_scribe`, before `_record_activation_event`):

```python
async def _activate_strategist(
    self,
    user_id: str,
    onboarding_data: dict[str, Any],
) -> dict[str, Any] | None:
    """Activate Strategist agent for go-to-market strategy.

    Strategist:
    - Synthesizes company intelligence into strategic recommendations
    - Identifies key account priorities based on enrichment data
    - Creates territory and engagement strategies

    Args:
        user_id: The user's ID.
        onboarding_data: Collected intelligence.

    Returns:
        Created goal dict or None if activation failed.
    """
    try:
        enrichment_data = onboarding_data.get("enrichment", {})
        user_goal = onboarding_data.get("first_goal", {})

        goal = GoalCreate(
            title="Strategic Assessment & Prioritization",
            description="ARIA analyzes your market position and recommends strategic account priorities.",
            goal_type=GoalType.ANALYSIS,
            config={
                "agent": "strategist",
                "agent_type": "strategist",
                "priority": "low",
                "company_type": enrichment_data.get("company_type"),
                "user_goal_type": user_goal.get("goal_type"),
                "source": "onboarding_activation",
            },
        )

        created = await self._goal_service.create_goal(user_id, goal)

        logger.info(
            "Strategist agent activated for strategic assessment",
            extra={"user_id": user_id, "goal_id": created["id"]},
        )

        return {"goal_id": created["id"]}

    except Exception as e:
        logger.error(
            "Strategist activation failed",
            extra={"user_id": user_id, "error": str(e)},
        )
        return None
```

Also update the docstring on `activate()` to say "six core agents" instead of five.

**Step 4: Run tests to verify all pass**

```bash
cd backend
python3 -m pytest tests/test_activation.py -v --tb=short
```

Expected: All 11 tests pass (9 existing + 2 new).

**Step 5: Run quality gates**

```bash
cd backend
python3 -m ruff check src/onboarding/activation.py && python3 -m ruff format --check src/onboarding/activation.py
```

Expected: All checks passed.

**Step 6: Commit**

```bash
git add backend/src/onboarding/activation.py backend/tests/test_activation.py
git commit -m "feat: add Strategist agent activation to onboarding completion (US-915)

CLAUDE.md defines 6 core agents but activation only started 5.
Adds _activate_strategist() which creates a strategic assessment
goal. Strategist always activates (no conditional gating) since
strategic analysis benefits every user regardless of integrations.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Implement real readiness score calculations (US-913)

**Files:**
- Modify: `backend/src/onboarding/readiness.py` (lines 232-333)
- Modify: `backend/tests/test_onboarding_readiness.py`

### Step 1: Write failing tests for `_calculate_corporate_memory`

Add to `backend/tests/test_onboarding_readiness.py`:

```python
class TestCorporateMemoryCalculation:
    """Tests for real corporate memory score calculation."""

    @pytest.mark.asyncio
    async def test_no_facts_returns_zero(self, presenter, mock_db):
        """No corporate facts → 0 score."""
        # company query returns company_id
        company_chain = _build_chain({"company_id": "comp-1"})
        # facts query returns empty
        facts_chain = _build_chain([])
        # docs query returns empty
        docs_chain = _build_chain([])
        mock_db.table.side_effect = [company_chain, facts_chain, docs_chain]

        score = await presenter._calculate_corporate_memory("user-123")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_facts_contribute_to_score(self, presenter, mock_db):
        """Corporate facts push score up (max 60 from facts)."""
        company_chain = _build_chain({"company_id": "comp-1"})
        facts = [{"id": f"f{i}"} for i in range(20)]
        facts_chain = _build_chain(facts)
        docs_chain = _build_chain([])
        mock_db.table.side_effect = [company_chain, facts_chain, docs_chain]

        score = await presenter._calculate_corporate_memory("user-123")
        assert 30.0 <= score <= 70.0

    @pytest.mark.asyncio
    async def test_documents_add_to_score(self, presenter, mock_db):
        """Documents add up to 40 points."""
        company_chain = _build_chain({"company_id": "comp-1"})
        facts_chain = _build_chain([])
        docs = [{"id": f"d{i}"} for i in range(5)]
        docs_chain = _build_chain(docs)
        mock_db.table.side_effect = [company_chain, facts_chain, docs_chain]

        score = await presenter._calculate_corporate_memory("user-123")
        assert score > 0.0

    @pytest.mark.asyncio
    async def test_no_company_returns_zero(self, presenter, mock_db):
        """No company linked → 0 score."""
        company_chain = _build_chain(None)
        mock_db.table.return_value = company_chain

        score = await presenter._calculate_corporate_memory("user-123")
        assert score == 0.0
```

### Step 2: Run tests to verify they fail

```bash
cd backend
python3 -m pytest tests/test_onboarding_readiness.py::TestCorporateMemoryCalculation -v
```

Expected: FAIL — methods return hardcoded 50.0 regardless of mock data.

### Step 3: Implement `_calculate_corporate_memory`

Replace the placeholder in `backend/src/onboarding/readiness.py` (lines 232-251):

```python
async def _calculate_corporate_memory(self, user_id: str) -> float:
    """Calculate corporate memory readiness from actual data.

    Score composition:
    - Facts discovered: up to 60 points (1 point per fact, capped at 60)
    - Documents uploaded: up to 40 points (8 points per doc, capped at 40)

    Args:
        user_id: The user's ID.

    Returns:
        Corporate memory score (0-100).
    """
    try:
        # Get user's company
        profile = (
            self._db.table("user_profiles")
            .select("company_id")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not profile.data or not profile.data.get("company_id"):
            return 0.0

        company_id = profile.data["company_id"]

        # Count corporate facts
        facts_result = (
            self._db.table("corporate_facts")
            .select("id")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .execute()
        )
        fact_count = len(facts_result.data or [])
        fact_score = min(fact_count, 60)  # 1 point per fact, cap 60

        # Count uploaded documents
        docs_result = (
            self._db.table("company_documents")
            .select("id")
            .eq("company_id", company_id)
            .execute()
        )
        doc_count = len(docs_result.data or [])
        doc_score = min(doc_count * 8, 40)  # 8 points per doc, cap 40

        return min(fact_score + doc_score, 100.0)

    except Exception as e:
        logger.warning("Corporate memory calculation failed: %s", e)
        return 0.0
```

### Step 4: Run tests to verify they pass

```bash
cd backend
python3 -m pytest tests/test_onboarding_readiness.py::TestCorporateMemoryCalculation -v
```

Expected: All pass.

### Step 5: Write failing tests for `_calculate_digital_twin`

```python
class TestDigitalTwinCalculation:
    """Tests for real digital twin score calculation."""

    @pytest.mark.asyncio
    async def test_no_settings_returns_zero(self, presenter, mock_db):
        """No user settings → 0 score."""
        chain = _build_chain(None)
        mock_db.table.return_value = chain

        score = await presenter._calculate_digital_twin("user-123")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_writing_style_contributes(self, presenter, mock_db):
        """Writing style fingerprint adds up to 50 points."""
        settings = {
            "preferences": {
                "digital_twin": {
                    "writing_style": {
                        "avg_sentence_length": 15,
                        "directness": 0.7,
                    }
                }
            }
        }
        chain = _build_chain(settings)
        mock_db.table.return_value = chain

        score = await presenter._calculate_digital_twin("user-123")
        assert score >= 50.0

    @pytest.mark.asyncio
    async def test_personality_calibration_adds_points(self, presenter, mock_db):
        """Personality calibration adds 50 points."""
        settings = {
            "preferences": {
                "digital_twin": {
                    "personality_calibration": {
                        "directness": 0.7,
                        "warmth": 0.5,
                    }
                }
            }
        }
        chain = _build_chain(settings)
        mock_db.table.return_value = chain

        score = await presenter._calculate_digital_twin("user-123")
        assert score >= 50.0

    @pytest.mark.asyncio
    async def test_both_writing_and_personality_full_score(self, presenter, mock_db):
        """Both writing style + personality calibration → high score."""
        settings = {
            "preferences": {
                "digital_twin": {
                    "writing_style": {"avg_sentence_length": 15},
                    "personality_calibration": {"directness": 0.7},
                }
            }
        }
        chain = _build_chain(settings)
        mock_db.table.return_value = chain

        score = await presenter._calculate_digital_twin("user-123")
        assert score == 100.0
```

### Step 6: Implement `_calculate_digital_twin`

```python
async def _calculate_digital_twin(self, user_id: str) -> float:
    """Calculate digital twin readiness from actual data.

    Score composition:
    - Writing style fingerprint present: 50 points
    - Personality calibration complete: 50 points

    Args:
        user_id: The user's ID.

    Returns:
        Digital twin score (0-100).
    """
    try:
        result = (
            self._db.table("user_settings")
            .select("preferences")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            return 0.0

        prefs = result.data.get("preferences") or {}
        dt = prefs.get("digital_twin") or {}

        score = 0.0
        if dt.get("writing_style"):
            score += 50.0
        if dt.get("personality_calibration"):
            score += 50.0

        return min(score, 100.0)

    except Exception as e:
        logger.warning("Digital twin calculation failed: %s", e)
        return 0.0
```

### Step 7: Write failing tests for `_calculate_relationship_graph`

```python
class TestRelationshipGraphCalculation:
    """Tests for real relationship graph score calculation."""

    @pytest.mark.asyncio
    async def test_no_leads_returns_zero(self, presenter, mock_db):
        """No lead memories → 0 score."""
        leads_chain = _build_chain([])
        mock_db.table.return_value = leads_chain

        score = await presenter._calculate_relationship_graph("user-123")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_leads_with_stakeholders_contribute(self, presenter, mock_db):
        """Leads with stakeholders push score up."""
        leads = [{"id": "lead-1"}, {"id": "lead-2"}, {"id": "lead-3"}]
        leads_chain = _build_chain(leads)
        stakeholders = [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}, {"id": "s4"}, {"id": "s5"}]
        stakeholders_chain = _build_chain(stakeholders)
        mock_db.table.side_effect = [leads_chain, stakeholders_chain]

        score = await presenter._calculate_relationship_graph("user-123")
        assert score > 0.0
```

### Step 8: Implement `_calculate_relationship_graph`

```python
async def _calculate_relationship_graph(self, user_id: str) -> float:
    """Calculate relationship graph readiness from actual data.

    Score composition:
    - Active leads: up to 50 points (10 points per lead, cap 50)
    - Stakeholders mapped: up to 50 points (5 points per stakeholder, cap 50)

    Args:
        user_id: The user's ID.

    Returns:
        Relationship graph score (0-100).
    """
    try:
        # Count active leads
        leads_result = (
            self._db.table("lead_memories")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        lead_count = len(leads_result.data or [])
        lead_score = min(lead_count * 10, 50)

        # Count stakeholders across all leads
        if lead_count > 0:
            lead_ids = [lead["id"] for lead in leads_result.data]
            stakeholders_result = (
                self._db.table("lead_memory_stakeholders")
                .select("id")
                .in_("lead_memory_id", lead_ids)
                .execute()
            )
            stakeholder_count = len(stakeholders_result.data or [])
        else:
            stakeholder_count = 0
        stakeholder_score = min(stakeholder_count * 5, 50)

        return min(lead_score + stakeholder_score, 100.0)

    except Exception as e:
        logger.warning("Relationship graph calculation failed: %s", e)
        return 0.0
```

### Step 9: Write failing tests for `_calculate_integrations`

```python
class TestIntegrationsCalculation:
    """Tests for real integrations score calculation."""

    @pytest.mark.asyncio
    async def test_no_integrations_returns_zero(self, presenter, mock_db):
        """No connected integrations → 0 score."""
        chain = _build_chain([])
        mock_db.table.return_value = chain

        score = await presenter._calculate_integrations("user-123")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_active_integrations_contribute(self, presenter, mock_db):
        """Each active integration adds 25 points (cap 100)."""
        integrations = [
            {"integration_type": "gmail", "status": "active"},
            {"integration_type": "google_calendar", "status": "active"},
            {"integration_type": "salesforce", "status": "active"},
        ]
        chain = _build_chain(integrations)
        mock_db.table.return_value = chain

        score = await presenter._calculate_integrations("user-123")
        assert score == 75.0

    @pytest.mark.asyncio
    async def test_disconnected_integrations_excluded(self, presenter, mock_db):
        """Disconnected integrations don't count."""
        integrations = [
            {"integration_type": "gmail", "status": "active"},
            {"integration_type": "salesforce", "status": "disconnected"},
        ]
        chain = _build_chain(integrations)
        mock_db.table.return_value = chain

        score = await presenter._calculate_integrations("user-123")
        assert score == 25.0
```

### Step 10: Implement `_calculate_integrations`

```python
async def _calculate_integrations(self, user_id: str) -> float:
    """Calculate integrations readiness from actual data.

    Score composition:
    - Each active integration: 25 points (cap 100)
    - Key integrations: CRM, Calendar, Email, Slack

    Args:
        user_id: The user's ID.

    Returns:
        Integrations score (0-100).
    """
    try:
        result = (
            self._db.table("user_integrations")
            .select("integration_type, status")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        active_count = len(result.data or [])
        return min(active_count * 25.0, 100.0)

    except Exception as e:
        logger.warning("Integrations calculation failed: %s", e)
        return 0.0
```

### Step 11: Write failing tests for `_calculate_goal_clarity`

```python
class TestGoalClarityCalculation:
    """Tests for real goal clarity score calculation."""

    @pytest.mark.asyncio
    async def test_no_goals_returns_zero(self, presenter, mock_db):
        """No goals → 0 score."""
        goals_chain = _build_chain([])
        agents_chain = _build_chain([])
        mock_db.table.side_effect = [goals_chain, agents_chain]

        score = await presenter._calculate_goal_clarity("user-123")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_active_goals_contribute(self, presenter, mock_db):
        """Each active goal adds 30 points (cap 60)."""
        goals = [
            {"id": "g1", "status": "active"},
            {"id": "g2", "status": "active"},
        ]
        goals_chain = _build_chain(goals)
        agents = [{"goal_id": "g1"}, {"goal_id": "g2"}]
        agents_chain = _build_chain(agents)
        mock_db.table.side_effect = [goals_chain, agents_chain]

        score = await presenter._calculate_goal_clarity("user-123")
        assert score >= 60.0

    @pytest.mark.asyncio
    async def test_agent_assignments_add_points(self, presenter, mock_db):
        """Agent assignments add up to 40 points."""
        goals = [{"id": "g1", "status": "active"}]
        goals_chain = _build_chain(goals)
        agents = [{"goal_id": "g1"}, {"goal_id": "g1"}]
        agents_chain = _build_chain(agents)
        mock_db.table.side_effect = [goals_chain, agents_chain]

        score = await presenter._calculate_goal_clarity("user-123")
        assert score > 30.0
```

### Step 12: Implement `_calculate_goal_clarity`

```python
async def _calculate_goal_clarity(self, user_id: str) -> float:
    """Calculate goal clarity readiness from actual data.

    Score composition:
    - Active goals: up to 60 points (30 points per goal, cap 60)
    - Agent assignments: up to 40 points (10 points per assignment, cap 40)

    Args:
        user_id: The user's ID.

    Returns:
        Goal clarity score (0-100).
    """
    try:
        # Count active goals
        goals_result = (
            self._db.table("goals")
            .select("id")
            .eq("user_id", user_id)
            .in_("status", ["active", "draft"])
            .execute()
        )
        goal_count = len(goals_result.data or [])
        goal_score = min(goal_count * 30, 60)

        # Count agent assignments
        if goal_count > 0:
            goal_ids = [g["id"] for g in goals_result.data]
            agents_result = (
                self._db.table("goal_agents")
                .select("id")
                .in_("goal_id", goal_ids)
                .execute()
            )
            agent_count = len(agents_result.data or [])
        else:
            agent_count = 0
        agent_score = min(agent_count * 10, 40)

        return min(goal_score + agent_score, 100.0)

    except Exception as e:
        logger.warning("Goal clarity calculation failed: %s", e)
        return 0.0
```

### Step 13: Run all readiness tests

```bash
cd backend
python3 -m pytest tests/test_onboarding_readiness.py -v --tb=short
```

Expected: All pass (existing 16 + new ~15 = ~31 tests). Note: existing `test_recalculate_*` tests mock the `_calculate_*()` methods, so they continue to work.

### Step 14: Run quality gates

```bash
cd backend
python3 -m ruff check src/onboarding/readiness.py && python3 -m ruff format --check src/onboarding/readiness.py
```

### Step 15: Commit

```bash
git add backend/src/onboarding/readiness.py backend/tests/test_onboarding_readiness.py
git commit -m "feat: implement real readiness score calculations (US-913)

Replace 5 placeholder methods that returned hardcoded 50.0 with
real Supabase queries:
- corporate_memory: counts corporate_facts + company_documents
- digital_twin: checks writing_style + personality_calibration
- relationship_graph: counts lead_memories + stakeholders
- integrations: counts active user_integrations
- goal_clarity: counts active goals + agent assignments

All methods have graceful error handling (return 0.0 on failure).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Final verification

**Step 1: Run full test suite for affected modules**

```bash
cd backend
python3 -m pytest tests/test_gap_detector.py tests/test_activation.py tests/test_onboarding_readiness.py tests/test_delta_presenter.py tests/test_first_conversation.py tests/test_enrichment_engine.py -v --tb=short
```

Expected: All pass.

**Step 2: Run quality gates across all modified files**

```bash
cd backend
python3 -m ruff check src/onboarding/activation.py src/onboarding/readiness.py src/onboarding/gap_detector.py src/onboarding/first_goal.py src/onboarding/first_conversation.py src/onboarding/enrichment.py src/onboarding/email_bootstrap.py
python3 -m ruff format --check src/onboarding/activation.py src/onboarding/readiness.py src/onboarding/gap_detector.py src/onboarding/first_goal.py src/onboarding/first_conversation.py src/onboarding/enrichment.py src/onboarding/email_bootstrap.py
```

Expected: All checks passed.
