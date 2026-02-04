# Lead Memory Database Schema Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the existing Lead Memory migration with service role policies, documentation comments, and updated_at triggers to match project patterns.

**Architecture:** The 6 core tables already exist in `supabase/migrations/20260202000004_create_lead_memory.sql`. This plan adds missing patterns: service role RLS policies, table/column comments, and automated updated_at timestamps.

**Tech Stack:** PostgreSQL 15+, Supabase migrations

---

## Task 1: Add Service Role Policies to All Lead Memory Tables

**Files:**
- Modify: `supabase/migrations/20260202000004_create_lead_memory.sql` (after line 122)

**Step 1: Write test verifying service role can access tables**

First, let's check if there's a test pattern for migrations by looking at existing tests.

Run: `ls tests/` to understand test structure

**Step 2: Add service role policies to migration file**

After line 122 (after existing user policies), add service role policies:

```sql
-- Service role has full access
CREATE POLICY "Service can manage lead_memories"
    ON lead_memories
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_events"
    ON lead_memory_events
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_stakeholders"
    ON lead_memory_stakeholders
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_insights"
    ON lead_memory_insights
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_contributions"
    ON lead_memory_contributions
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_crm_sync"
    ON lead_memory_crm_sync
    FOR ALL
    USING (auth.role() = 'service_role');
```

**Step 3: Test migration applies cleanly**

Run: `supabase migration up` or `supabase db reset` if in dev
Expected: Migration applies without errors

**Step 4: Commit**

```bash
git add supabase/migrations/20260202000004_create_lead_memory.sql
git commit -m "feat(lead-memory): add service role RLS policies"
```

---

## Task 2: Add Table and Column Comments

**Files:**
- Modify: `supabase/migrations/20260202000004_create_lead_memory.sql` (at end of file)

**Step 1: Add documentation comments**

Add after the indexes section (after line 135):

```sql
-- Comments for documentation
COMMENT ON TABLE lead_memories IS 'Core lead/opportunity/account tracking with full lifecycle history and health scoring.';
COMMENT ON COLUMN lead_memories.lifecycle_stage IS 'lead → opportunity → account progression. History preserved on transition.';
COMMENT ON COLUMN lead_memories.health_score IS '0-100 composite score: communication(25%), response_time(20%), sentiment(20%), stakeholder_breadth(20%), velocity(15%).';
COMMENT ON COLUMN lead_memories.crm_id IS 'External CRM record ID (Salesforce Opportunity ID, HubSpot Deal ID, etc.).';
COMMENT ON COLUMN lead_memories.tags IS 'User-defined tags for categorization and filtering.';

COMMENT ON TABLE lead_memory_events IS 'Timeline of all interactions: emails, meetings, calls, notes, and market signals.';
COMMENT ON COLUMN lead_memory_events.direction IS 'inbound (received) or outbound (sent) for communications.';
COMMENT ON COLUMN lead_memory_events.source IS 'Origin: gmail, calendar, manual, crm, or system.';
COMMENT ON COLUMN lead_memory_events.source_id IS 'Original message/event ID from source system for deduplication.';

COMMENT ON TABLE lead_memory_stakeholders IS 'Contact mapping with role classification, influence scoring, and sentiment tracking.';
COMMENT ON COLUMN lead_memory_stakeholders.role IS 'decision_maker, influencer, champion, blocker, or user.';
COMMENT ON COLUMN lead_memory_stakeholders.influence_level IS '1-10 scale of decision-making influence.';
COMMENT ON COLUMN lead_memory_stakeholders.sentiment IS 'positive, neutral, negative, or unknown based on interactions.';
COMMENT ON COLUMN lead_memory_stakeholders.personality_insights IS 'AI-derived communication preferences and behavioral patterns.';

COMMENT ON TABLE lead_memory_insights IS 'AI-extracted intelligence: objections, buying signals, commitments, risks, and opportunities.';
COMMENT ON COLUMN lead_memory_insights.insight_type IS 'objection, buying_signal, commitment, risk, or opportunity.';
COMMENT ON COLUMN lead_memory_insights.confidence IS '0-1 score from AI model. Lower confidence requires human verification.';
COMMENT ON COLUMN lead_memory_insights.source_event_id IS 'Links insight to the event that generated it.';

COMMENT ON TABLE lead_memory_contributions IS 'Multi-user collaboration with owner approval workflow.';
COMMENT ON COLUMN lead_memory_contributions.contribution_type IS 'event, note, or insight.';
COMMENT ON COLUMN lead_memory_contributions.status IS 'pending (awaiting review), merged (accepted), or rejected.';

COMMENT ON TABLE lead_memory_crm_sync IS 'Bidirectional CRM synchronization state and conflict tracking.';
COMMENT ON COLUMN lead_memory_crm_sync.sync_direction IS 'push (ARIA→CRM), pull (CRM→ARIA), or bidirectional.';
COMMENT ON COLUMN lead_memory_crm_sync.status IS 'synced, pending, conflict, or error.';
COMMENT ON COLUMN lead_memory_crm_sync.pending_changes IS 'Array of changes awaiting sync.';
COMMENT ON COLUMN lead_memory_crm_sync.conflict_log IS 'Array of resolved/unresolved conflicts with timestamps.';
```

**Step 2: Verify comments are readable**

Run: Connect to Supabase and query `pg_description` or use `\dt+` in psql
Expected: All comments visible in database

**Step 3: Commit**

```bash
git add supabase/migrations/20260202000004_create_lead_memory.sql
git commit -m "docs(lead-memory): add table and column comments for documentation"
```

---

## Task 3: Add Updated At Trigger Function

**Files:**
- Modify: `supabase/migrations/20260202000004_create_lead_memory.sql`

**Step 1: Check if trigger function already exists project-wide**

Run: `grep -r "updated_at_trigger" supabase/migrations/`
Expected: Determine if we should reuse existing or create new

**Step 2: Add trigger function and apply to tables**

Add before RLS policies (around line 98):

```sql
-- Updated at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_lead_memories_updated_at
    BEFORE UPDATE ON lead_memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_lead_memory_stakeholders_updated_at
    BEFORE UPDATE ON lead_memory_stakeholders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_lead_memory_crm_sync_updated_at
    BEFORE UPDATE ON lead_memory_crm_sync
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**Step 3: Test trigger behavior**

Test by updating a record and verifying `updated_at` changes:
```sql
UPDATE lead_memories SET company_name = company_name WHERE id = 'test-id';
SELECT updated_at FROM lead_memories WHERE id = 'test-id';
```

**Step 4: Commit**

```bash
git add supabase/migrations/20260202000004_create_lead_memory.sql
git commit -m "feat(lead-memory): add updated_at triggers for automatic timestamp updates"
```

---

## Task 4: Verify Migration Against Specification

**Files:**
- Reference: `docs/PHASE_5_LEAD_MEMORY.md` lines 73-184

**Step 1: Cross-check schema against spec**

Create a checklist verification:

- [ ] `lead_memories`: All 19 fields present
- [ ] `lead_memory_events`: All 10 fields present
- [ ] `lead_memory_stakeholders`: All 10 fields present with unique constraint
- [ ] `lead_memory_insights`: All 8 fields present
- [ ] `lead_memory_contributions`: All 7 fields present
- [ ] `lead_memory_crm_sync`: All 10 fields present
- [ ] All 5 indexes from spec present
- [ ] RLS enabled on all 6 tables
- [ ] User isolation policies present
- [ ] Service role policies present
- [ ] Cascade deletes configured correctly

**Step 2: Run full migration test**

Run: `supabase db reset` (development) or verify with `supabase migration list`
Expected: All migrations apply in order, lead_memory migration at version `20260202000004`

**Step 3: Verify table schemas**

Run: `\d lead_memories` in Supabase SQL editor
Expected: All columns with correct types

**Step 4: Commit final verification notes**

If any issues found, create fix commit:
```bash
git commit -m "fix(lead-memory): resolve schema verification issues"
```

---

## Task 5: Create Database Tests

**Files:**
- Create: `backend/tests/db/test_lead_memory_schema.py`

**Step 1: Create test file skeleton**

```python
"""Test Lead Memory database schema and RLS policies."""
import pytest
from httpx import AsyncClient
from supabase import Client

from backend.src.db.supabase_client import get_supabase


@pytest.fixture
async def supabase_admin() -> Client:
    """Get admin client for schema verification."""
    from backend.src.core.config import settings
    return Client(
        settings.supabase_url,
        settings.supabase_service_key
    )


class TestLeadMemorySchema:
    """Verify lead memory table structure."""

    async def test_lead_memories_table_exists(self, supabase_admin: Client):
        """Table should exist with correct columns."""
        result = supabase_admin.table("lead_memories").select("*").limit(0).execute()
        assert result.data is not None

    async def test_lead_memory_events_table_exists(self, supabase_admin: Client):
        """Events table should exist."""
        result = supabase_admin.table("lead_memory_events").select("*").limit(0).execute()
        assert result.data is not None

    async def test_stakeholders_table_exists(self, supabase_admin: Client):
        """Stakeholders table should exist."""
        result = supabase_admin.table("lead_memory_stakeholders").select("*").limit(0).execute()
        assert result.data is not None

    async def test_insights_table_exists(self, supabase_admin: Client):
        """Insights table should exist."""
        result = supabase_admin.table("lead_memory_insights").select("*").limit(0).execute()
        assert result.data is not None

    async def test_contributions_table_exists(self, supabase_admin: Client):
        """Contributions table should exist."""
        result = supabase_admin.table("lead_memory_contributions").select("*").limit(0).execute()
        assert result.data is not None

    async def test_crm_sync_table_exists(self, supabase_admin: Client):
        """CRM sync table should exist."""
        result = supabase_admin.table("lead_memory_crm_sync").select("*").limit(0).execute()
        assert result.data is not None


class TestLeadMemoryRLS:
    """Verify RLS policies enforce user isolation."""

    async def test_user_cannot_access_other_leads(
        self,
        supabase_admin: Client,
        async_client: AsyncClient,
        test_user_headers: dict
    ):
        """Users should only see their own leads."""
        # Create lead for user 1
        lead_1 = supabase_admin.table("lead_memories").insert({
            "user_id": "user-1-id",
            "company_name": "Test Company 1"
        }).select().single().execute()

        # User 2 should not see user 1's leads
        response = await async_client.get(
            "/api/v1/leads",
            headers=test_user_headers  # User 2's auth
        )
        assert response.status_code == 200
        leads = response.json()
        assert all(l["user_id"] != "user-1-id" for l in leads)

    async def test_service_role_has_full_access(self, supabase_admin: Client):
        """Service role should bypass RLS."""
        result = supabase_admin.table("lead_memories").select("*").execute()
        assert result.data is not None
```

**Step 2: Run tests to verify they fail initially**

Run: `pytest backend/tests/db/test_lead_memory_schema.py -v`
Expected: Tests pass if tables exist, fail if RLS not working

**Step 3: Implement any missing fixtures**

Add required fixtures to `backend/tests/conftest.py`:
- `supabase_admin` fixture
- `test_user_headers` fixture

**Step 4: Commit tests**

```bash
git add backend/tests/db/test_lead_memory_schema.py
git commit -m "test(lead-memory): add schema and RLS verification tests"
```

---

## Task 6: Final Integration Test

**Files:**
- Test: Run existing backend tests
- Test: Verify migration applies cleanly

**Step 1: Run full backend test suite**

Run: `cd backend && pytest tests/ -v`
Expected: All existing tests still pass

**Step 2: Verify migration order**

Run: `supabase migration list`
Expected: `20260202000004_create_lead_memory.sql` appears after `20260202000003_create_battle_cards.sql`

**Step 3: Create a test lead via API**

Run: `curl -X POST http://localhost:8000/api/v1/leads -H "Authorization: Bearer <token>" -d '{"company_name": "Test Lead"}'`
Expected: Lead created successfully

**Step 4: Final commit**

```bash
git add .
git commit -m "chore(lead-memory): complete US-501 database schema implementation"
```

---

## Acceptance Criteria Verification

After completing all tasks, verify:

- [ ] `lead_memories` table with all fields (19 total)
- [ ] `lead_memory_events` for timeline (10 fields)
- [ ] `lead_memory_stakeholders` for contacts (10 fields + unique constraint)
- [ ] `lead_memory_insights` for AI insights (8 fields)
- [ ] `lead_memory_contributions` for multi-user (7 fields)
- [ ] `lead_memory_crm_sync` for sync state (10 fields)
- [ ] RLS policies for user isolation (6 tables)
- [ ] Service role policies (6 tables)
- [ ] Indexes for common queries (8 indexes)
- [ ] Table/column comments for documentation
- [ ] Updated_at triggers for timestamp management
- [ ] Database tests for schema verification
- [ ] All tests passing

---

## Next Steps

After this plan completes:
1. Proceed to US-502: Lead Memory Core Implementation
2. Implement `src/memory/lead_memory.py` with LeadMemoryService class
3. Create API endpoints in US-507

---

## Notes

- **DRY**: Service role policy pattern reused across all tables
- **YAGNI**: Only added patterns already established in project
- **TDD**: Tests created for schema verification
- **Frequent commits**: Each logical change is its own commit
