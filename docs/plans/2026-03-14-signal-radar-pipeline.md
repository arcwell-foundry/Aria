# Plan: Wire Signal Radar into Proactive Signal-to-Outreach Pipeline

**Date:** 2026-03-14
**Status:** Draft
**Scope:** Connect SignalRadarCapability's 15+ data sources to the downstream signal cascade, add ICP-aware buying signal scoring, and enable signal-to-lead auto-discovery.

---

## Phase 0: Documentation Discovery — Key Findings

### Architecture Facts (verified from source code)

**SignalRadarCapability** (`backend/src/agents/capabilities/signal_radar.py`, 2004 lines):
- Already has its own cron: `run_signal_radar_cron()` at line 1954, registered in `scheduler.py:2706` running every 30 minutes
- `scan_all_sources(user_id)` fetches entities internally via `_get_monitored_entities()` (line 307) — does NOT accept external entity lists
- Already stores signals to `market_signals` via `_store_market_signal()` (line 1741)
- Already scores relevance via `score_relevance()` (line 383) — but NO buying-signal/deal-implication scoring
- Already calls `create_alerts()` for signals with relevance >= 0.7

**scout_signal_scan_job.py** (684 lines):
- Runs every 15 minutes via `CronTrigger(minute="*/15")`
- Uses ScoutAgent (Exa-based) — completely separate from SignalRadarCapability
- Has 5 existing downstream cascades after signal save (lines 186-302): Watch Topics, Memory Compounding, Pulse Engine, Jarvis Orchestrator, ProactiveRouter
- Gathers entities from 5 sources via `_get_scan_entities()` (line 344)

**signal_lead_trigger.py** (281 lines):
- Runs every 30 minutes via `CronTrigger(minute="*/30")`
- Scores signals with 27 bioprocessing keywords (scores 55-95)
- Creates lead_gen goals (NOT aria_action_queue entries) for scores >= 70
- Auto-approves goals immediately via `GoalService.start_goal()`

### Critical Schema Mismatches vs Prompt Pseudocode

The prompt's pseudocode assumes columns/tables that **don't exist**. Corrections needed:

| Prompt Assumes | Reality | Fix |
|---------------|---------|-----|
| `market_signals.processed_for_leads_at` | Does NOT exist | Use `metadata` JSONB field instead, or add column via migration |
| `market_signals.lead_relevance_score` | Does NOT exist | Use `metadata` JSONB field instead, or add column via migration |
| `battle_cards.metadata` column | Does NOT exist | Use existing `overview` or skip battle card updates that need metadata |
| `battle_cards.user_id` column | Does NOT exist — uses `company_id` via RLS | Must join through `user_profiles.company_id` |
| `lead_memory_events.user_id` | Does NOT exist — uses `lead_memory_id` FK | Join through `lead_memories` table |
| `lead_memory_events.title` | Column is `subject` | Use `subject` field |
| `memory_semantic.content` | Column is `fact` | Use `fact` field |
| `pulse_signals.time_sensitivity` | Single float, not column default | Must provide as float |

### What Signal Radar Already Does vs What's Missing

**Already works (via its own cron):**
- Scans FDA, ClinicalTrials.gov, SEC EDGAR, Patents, 8 RSS feeds, Wire Services, LinkedIn
- Stores signals in `market_signals`
- Creates alerts for high-relevance signals
- Updates `monitored_entities.last_checked_at`

**What's missing:**
1. No buying-signal / deal-implication scoring (bioprocessing-specific)
2. No signal cascade to lead_memory_events, battle_cards, memory_semantic, pulse_signals
3. No ICP-sector scanning (only monitors known entities, not sector-wide signals)
4. No first-mover window tracking
5. No auto-discovery of new leads from signals about unknown companies
6. scout_signal_scan_job doesn't call signal radar (but signal radar has its own cron — this is fine)

### Decision: Don't duplicate signal radar into scout_signal_scan_job

The prompt says "wire SignalRadarCapability into scout_signal_scan_job.py" but signal radar **already has its own cron job** in `scheduler.py:2706-2713`. Adding it to scout_signal_scan_job would cause duplicate scans. Instead:
- Enhance the existing signal radar cron pipeline
- Add the missing cascade service
- Add buying signal scoring to signal_radar.py
- Enhance signal_lead_trigger.py with first-mover awareness and aria_action_queue proposals

---

## Phase 1: Add `processed_for_leads_at` and `lead_relevance_score` columns to market_signals

**What to implement:**
- Create a new migration file adding two columns to `market_signals`:
  - `processed_for_leads_at` (TIMESTAMPTZ, nullable) — tracks when signal_lead_trigger processed this signal
  - `lead_relevance_score` (FLOAT, nullable) — buying-signal score from signal_lead_trigger

**File to create:** `backend/supabase/migrations/20260314000001_market_signals_lead_columns.sql`

**Why:** signal_lead_trigger.py already writes to these columns (line 130 calls `_mark_processed` which sets both) but the columns may not exist in the schema. The migration ensures they exist.

**Verification:**
- `grep -r "processed_for_leads_at" backend/supabase/migrations/` — should find the new migration
- `grep -r "lead_relevance_score" backend/supabase/migrations/` — should find the new migration

---

## Phase 2: Add BUYING_SIGNAL_BOOSTS and ICP-aware scoring to signal_radar.py

**What to implement:**

1. Add `BUYING_SIGNAL_BOOSTS` constant dict after existing `SIGNAL_TYPES` constant (around line 90)
2. Add `REGULATORY_DEAL_IMPLICATIONS` constant dict
3. Add `_is_cdmo_bioprocess_relevant()` method to `SignalRadarCapability` class
4. Add `_add_deal_implication()` method to `SignalRadarCapability` class
5. In `scan_all_sources()`, after scoring relevance (line 352), call `_add_deal_implication()` on each signal to enrich with buying-signal metadata

**Pattern to follow:** The existing `score_relevance()` method at line 383 is additive scoring capped at 1.0. The new buying signal scoring should be stored in `signal.metadata["buying_signal_score"]` and `signal.metadata["deal_implication"]` rather than overriding `relevance_score`.

**Files to modify:**
- `backend/src/agents/capabilities/signal_radar.py`
  - Add constants after line ~90
  - Add methods after `score_relevance()` (after line 451)
  - Modify `scan_all_sources()` to call `_add_deal_implication()` after line 352

**Verification:**
- `grep "BUYING_SIGNAL_BOOSTS" backend/src/agents/capabilities/signal_radar.py` — should find constant
- `grep "_add_deal_implication" backend/src/agents/capabilities/signal_radar.py` — should find method and call site

---

## Phase 3: Create SignalCascadeService

**What to implement:**

Create `backend/src/services/signal_cascade_service.py` with a `SignalCascadeService` class that fans out a new market signal to downstream systems.

**Cascade targets (fail-open, asyncio.gather with return_exceptions=True):**

1. **`_update_lead_health()`** — If `company_name` matches a `discovered_leads` record for this user, boost `fit_score` by up to 10 points based on `lead_relevance_score`
2. **`_write_lead_memory_event()`** — If company matches `lead_memories`, insert a `lead_memory_events` record with `event_type="market_signal"`, `subject=headline[:200]`, `content=summary`
   - NOTE: `lead_memory_events` has NO `user_id` column — must look up `lead_memory_id` from `lead_memories` table
3. **`_update_battle_card()`** — If company matches `battle_cards.competitor_name`, update the battle card
   - NOTE: `battle_cards` has NO `metadata` column and NO `user_id` — uses `company_id`. Must join through `user_profiles` to get `company_id` for the user, then match `competitor_name`
   - Store recent developments in `overview` field (TEXT) by appending signal info
4. **`_write_semantic_memory()`** — Insert into `memory_semantic` with `fact="{company}: {headline}"`, `confidence=relevance_score`, `source="signal_cascade"`
   - NOTE: Column is `fact`, not `content`
5. **`_update_monitored_entity()`** — Update `last_checked_at` on matching monitored_entities
6. **`_push_pulse_signal()`** — For signals with `relevance_score >= 0.75`, insert into `pulse_signals` with proper salience scores

**Pattern to follow:** Copy the fail-open pattern from `scout_signal_scan_job.py` lines 186-302, where each cascade operation is wrapped in its own try/except.

**Files to create:**
- `backend/src/services/signal_cascade_service.py`

**Verification:**
- `python -c "from src.services.signal_cascade_service import SignalCascadeService"` — should import without error
- `grep "asyncio.gather" backend/src/services/signal_cascade_service.py` — should find parallel execution

---

## Phase 4: Wire cascade into signal_radar's scan_all_sources()

**What to implement:**

In `signal_radar.py`, after `_store_market_signal()` (line 363 in `scan_all_sources()`), call `SignalCascadeService.cascade()` for each stored signal.

**Modification point:** `scan_all_sources()` at lines 360-363:
```python
# Current code:
client = SupabaseClient.get_client()
for signal in deduped:
    self._store_market_signal(client, user_id, signal)

# Add after store:
    cascade = SignalCascadeService()
    await cascade.cascade(signal.model_dump(), user_id)
```

**Also wire into scout_signal_scan_job.py** after signal insert (around line 179) so signals from ScoutAgent also cascade.

**Files to modify:**
- `backend/src/agents/capabilities/signal_radar.py` — `scan_all_sources()` method
- `backend/src/jobs/scout_signal_scan_job.py` — after signal insert at line 179

**Verification:**
- `grep "SignalCascadeService" backend/src/agents/capabilities/signal_radar.py` — should find import and usage
- `grep "SignalCascadeService" backend/src/jobs/scout_signal_scan_job.py` — should find import and usage

---

## Phase 5: Enhance signal_lead_trigger.py with first-mover awareness and action queue proposals

**What to implement:**

1. Add `SIGNAL_TO_NEWS_LAG` constant dict (first-mover window in days per signal type)
2. Add `BUYING_SIGNAL_TYPES` set constant
3. In the `run()` method, after creating a goal (line 167), ALSO create an `aria_action_queue` entry with:
   - `action_type = "lead_discovered"`
   - `title = "{company} — {signal_type} detected"`
   - `aria_reasoning` including first-mover window countdown language
   - `payload` including `first_mover_window_days` from `SIGNAL_TO_NEWS_LAG`
   - `risk_level = "low"`
   - `status = "pending"`

**Pattern to follow:** Existing goal creation at line 146-179. The action queue entry is additive — it surfaces the proposal in the UI action queue alongside the auto-started goal.

**Files to modify:**
- `backend/src/services/signal_lead_trigger.py`

**Verification:**
- `grep "SIGNAL_TO_NEWS_LAG" backend/src/services/signal_lead_trigger.py` — should find constant
- `grep "aria_action_queue" backend/src/services/signal_lead_trigger.py` — should find insert
- `grep "first_mover_window_days" backend/src/services/signal_lead_trigger.py` — should find in payload

---

## Phase 6: Expand entity coverage in signal_radar's _get_monitored_entities()

**What to implement:**

Enhance `_get_monitored_entities()` (line 1316) to also include:
1. Companies from `discovered_leads` table (prospects already in pipeline)
2. Companies from `lead_memories` table (active leads)
3. ICP sector-level keywords from `lead_icp_profiles` table

This expands signal radar from only monitoring explicitly tracked entities to also watching prospect companies and ICP-matching sectors.

**Files to modify:**
- `backend/src/agents/capabilities/signal_radar.py` — `_get_monitored_entities()` method

**Verification:**
- `grep "discovered_leads" backend/src/agents/capabilities/signal_radar.py` — should find query
- `grep "lead_icp_profiles" backend/src/agents/capabilities/signal_radar.py` — should find query

---

## Phase 7: Verification & Integration Test

**What to verify:**

1. **Migration applied:** Run the migration to add `processed_for_leads_at` and `lead_relevance_score` columns
2. **Import check:** `python -c "from src.services.signal_cascade_service import SignalCascadeService; from src.agents.capabilities.signal_radar import BUYING_SIGNAL_BOOSTS"`
3. **Insert test signal** (the Mabion test from the prompt):
```sql
INSERT INTO market_signals (
  user_id, company_name, signal_type, headline, summary,
  relevance_score, source_name, detected_at
) VALUES (
  '41475700-c1fb-4f66-8c56-77bd90b73abb',
  'Mabion',
  'facility_expansion',
  'Mabion announces €50M investment in biologics manufacturing expansion',
  'Polish CDMO Mabion is expanding upstream and downstream bioprocessing capacity with new bioreactor installation',
  0.92,
  'signal_radar_test',
  NOW()
);
```
4. **Verify cascade writes:**
```sql
-- Memory written?
SELECT fact, confidence FROM memory_semantic
WHERE source = 'signal_cascade' ORDER BY created_at DESC LIMIT 3;

-- Pulse signal pushed?
SELECT title, priority_score FROM pulse_signals
ORDER BY created_at DESC LIMIT 3;

-- monitored_entities updated?
SELECT entity_name, last_checked_at FROM monitored_entities
WHERE last_checked_at IS NOT NULL ORDER BY last_checked_at DESC LIMIT 5;
```

5. **Check signal types in DB** (should show diversity after radar runs):
```sql
SELECT signal_type, source_name, COUNT(*) FROM market_signals
WHERE user_id = '41475700-c1fb-4f66-8c56-77bd90b73abb'
GROUP BY signal_type, source_name ORDER BY count DESC;
```

---

## Anti-Pattern Guards

- **Do NOT add SignalRadarCapability.scan_all_sources() call into scout_signal_scan_job.py** — signal radar already has its own cron job at scheduler.py:2706. Duplicating would cause double-scanning.
- **Do NOT use `content` column on memory_semantic** — the column is `fact`.
- **Do NOT use `title` on lead_memory_events** — the column is `subject`.
- **Do NOT assume battle_cards has `metadata` or `user_id`** — it uses `company_id` and has no metadata JSONB column.
- **Do NOT assume lead_memory_events has `user_id`** — it links through `lead_memory_id` FK.
- **Do NOT query `auth.users`** — always use user_id from context.
- **Do NOT hardcode user IDs** — all queries filter by user_id from function parameters.
- **Always use `(get("key") or {}).get(...)` pattern** — not `get("key", {}).get(...)` for nullable fields.
