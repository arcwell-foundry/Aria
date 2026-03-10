# ARIA Intelligence Pulse Engine Audit Report

**Date:** 2026-03-10
**Status:** CRITICAL - Multiple components are broken, incomplete, or disconnected

---

## Executive Summary

The Intelligence Pulse Engine is **partially built but critically disconnected**. Signal detection works, insights are generated, but **delivery is completely broken**. All 141 jarvis_insights have `delivered_at = NULL`, `intelligence_delivered` table is empty, and `monitored_entities.last_checked_at` is never updated.

### Root Causes Identified:
1. **jarvis_insights.delivered_at never set** - No delivery code writes to this field
2. **pulse_signals table not queried for delivery** - The delivery pipeline doesn't read from pulse_signals
3. **monitored_entities.last_checked_at never updated** - The scanner reads but never writes back
4. **action_routing_rules never fire** - 8 rules exist but no matching insights reach them

---

## STEP 1: Scheduler Audit

### Status: ✅ WORKING

**File:** `backend/src/services/scheduler.py`

### Registered Jobs:
| Job ID | Function | Interval | Status |
|--------|----------|----------|--------|
| `scout_signal_scan` | `_run_scout_signal_scan` | Every 15 min | ✅ Registered |
| `daily_briefing_check` | `_run_daily_briefing_check` | Every 15 min | ✅ Registered |
| `stale_leads_check` | `_run_stale_leads_check` | Daily 7 AM | ✅ Registered |
| `weekly_digest` | `_run_weekly_digest` | Monday 7 AM | ✅ Registered |
| `pulse_sweep` | `_run_pulse_sweep` | Every 15 min | ✅ Registered |
| `capability_demand_check` | `_run_capability_demand_check` | Every 6 hours | ✅ Registered |
| `skill_health_check` | `_run_skill_health_check` | Every 6 hours | ✅ Registered |
| `battle_card_refresh` | `_run_battle_card_refresh` | Weekly | ✅ Registered |
| `conversion_score_batch` | `_run_conversion_score_batch` | Weekly | ✅ Registered |
| `meeting_start_warning` | `_run_meeting_start_warning` | Every 10 min | ✅ Registered |
| `meeting_brief_generation` | `_run_meeting_brief_generation` | Every 15 min | ✅ Registered |
| `working_memory_sync` | `_run_working_memory_sync` | Every 30 sec | ✅ Registered |
| `calendar_meeting_checks` | `_run_calendar_meeting_checks` | Every 10 min | ✅ Registered |
| `style_recalibration` | `_run_style_recalibration` | Hourly | ✅ Registered |
| `draft_auto_approve` | `_run_draft_auto_approve` | Every 5 min | ✅ Registered |
| `salience_decay` | `_run_salience_decay` | Daily | ✅ Registered |

**Startup:** Called via `start_scheduler()` in `main.py:197`

**Verdict:** The scheduler is properly configured with 16+ jobs. Scout signal scan runs every 15 minutes.

---

## STEP 2: Scout Signal Scan Job Audit

### Status: ⚠️ PARTIAL

**File:** `backend/src/jobs/scout_signal_scan_job.py`

### What It Does (Lines 28-289):
1. ✅ Gets active users via `get_active_user_ids()`
2. ✅ Checks business hours per user timezone
3. ✅ Gathers entities from 5 sources:
   - `user_preferences.tracked_competitors`
   - `lead_memories.company_name` (status='active')
   - `monitored_entities` table (is_active=True)
   - `discovered_leads.company_name`
   - `market_signals.company_name` (fallback bootstrap)
4. ✅ Instantiates ScoutAgent with `user_id`
5. ✅ Calls `scout.execute({"entities": entities, "signal_types": ["news", "funding", "regulatory"]})`
6. ✅ Deduplicates by headline + company_name
7. ✅ Stores in `market_signals` table
8. ✅ Routes through `IntelligencePulseEngine.process_signal()`
9. ✅ Routes through `JarvisOrchestrator.process_event()`
10. ✅ Routes through `ProactiveRouter` for notifications
11. ✅ Generates goal proposals for high-relevance signals

### Failure Points:

| Issue | Severity | Location |
|-------|----------|----------|
| `monitored_entities.last_checked_at` never updated | MEDIUM | Job reads but never writes `last_checked_at` |
| ScoutAgent may fail silently | MEDIUM | Lines 94-100 catch exceptions but continue |
| No `action_routing_rules` trigger | HIGH | ActionRouter is called via Orchestrator, but insights don't match rules |

### The ScoutAgent Connection:
The ScoutAgent (lines 82-101) is properly instantiated with `user_id`. However, the agent's internal logic determines what signals it actually finds.

---

## STEP 3: SignalRadar Capability Audit

### Status: ⚠️ BUILT BUT NOT SCHEDULED

**File:** `backend/src/agents/capabilities/signal_radar.py` (2004 lines)

### What It Contains:
- 14 signal types defined: `fda_approval`, `fda_warning_letter`, `clinical_trial`, `sec_filing`, `patent`, `funding`, `leadership`, `partnership`, `product`, `hiring`, `earnings`, `regulatory`, `competitive_move`, `market_trend`
- 8 RSS feeds: BioPharma Dive, STAT News, Endpoints News, Fierce Pharma, BioSpace, Pharma Tech, GEN News, Drug Discovery & Development
- Government APIs: FDA openFDA, ClinicalTrials.gov, SEC EDGAR, Google Patents
- Wire services: PR Newswire, GlobeNewswire
- Social: LinkedIn company pages

### Key Functions:
- `scan_all_sources()` - Runs all scanners in parallel
- `_scan_rss_feeds()` - Parses RSS feeds for entity matches
- `_scan_fda()` - FDA approvals, warning letters, device clearances
- `_scan_clinical_trials()` - ClinicalTrials.gov with curl fallback
- `_scan_sec_edgar()` - SEC filings
- `_scan_patents()` - Google Patents XHR
- `_scan_wire_services()` - PR Newswire, GlobeNewswire
- `_scan_social()` - LinkedIn company pages

### The Problem:
**The `SignalRadarCapability` is NEVER called by the scheduler.** The `scout_signal_scan_job.py` uses `ScoutAgent`, not `SignalRadarCapability`.

The `SignalRadarCapability` has helper functions:
- `run_signal_radar_scan()` (line 1900)
- `run_signal_radar_cron()` (line 1954)

But these are **NOT registered in the scheduler**.

### Comparison:
| Component | Used by Scheduler | Sources |
|-----------|-------------------|---------|
| ScoutAgent | ✅ Yes | Exa (web search) |
| SignalRadarCapability | ❌ No | RSS, FDA, ClinicalTrials.gov, SEC, Patents, Wire Services |

**Verdict:** SignalRadarCapability exists but is orphaned. The scheduler only uses ScoutAgent, which has different (simpler) signal detection logic.

---

## STEP 4: Intelligence Pulse Engine Audit

### Status: ✅ WORKING

**File:** `backend/src/services/intelligence_pulse.py` (498 lines)

### What It Does:
1. ✅ Receives signals via `process_signal(user_id, signal)`
2. ✅ Scores salience across 5 dimensions: goal_relevance, time_sensitivity, value_impact, user_preference, surprise_factor
3. ✅ Computes priority score (weighted average)
4. ✅ Determines delivery channel: `immediate`, `check_in`, `morning_brief`, `weekly_digest`, `silent`
5. ✅ Persists to `pulse_signals` table
6. ✅ Delivers via `_deliver()` for "immediate" priority

### Delivery Logic (Lines 313-374):
```python
async def _deliver(self, record, channel, user_id):
    if channel != "immediate":
        return  # Only immediate signals get delivered now

    # 1. Create notification via NotificationService
    await self._notifications.create_notification(...)

    # 2. WebSocket push via ws_manager.send_signal()
    await ws_manager.send_signal(user_id, signal_type, title, severity, data)

    # 3. Mark delivered_at
    self._db.table("pulse_signals").update({"delivered_at": ...})
```

### The Problem:
**Only `immediate` channel triggers delivery.** Other channels (`check_in`, `morning_brief`, `weekly_digest`) are "consumed" by:
- `check_in` → Chat priming at next conversation (NOT IMPLEMENTED)
- `morning_brief` → Briefing generator (NOT IMPLEMENTED to query pulse_signals)
- `weekly_digest` → Weekly digest job (NOT IMPLEMENTED to query pulse_signals)

### Evidence:
- `pulse_signals` table likely has records but `delivered_at` is only set for "immediate" priority
- No code queries `pulse_signals` for `morning_brief` or `check_in` channel delivery

---

## STEP 5: Jarvis Insight Delivery Pipeline Audit

### Status: ❌ BROKEN

**Files:**
- `backend/src/intelligence/orchestrator.py` (1181 lines)
- `backend/src/intelligence/action_router.py` (900 lines)

### The Flow:
```
scout_signal_scan_job.py
    → jarvis.process_event()
        → ImplicationEngine.analyze_event()
        → GoalImpactMapper.assess_event_impact()
        → ButterflyDetector.detect()
        → ConnectionEngine.find_connections()
        → Persists to jarvis_insights
        → ActionRouter.route_insight()
```

### What's Broken:
1. **`jarvis_insights.delivered_at` is NEVER set** - The `JarvisOrchestrator.process_event()` persists insights but has no delivery step

2. **No `deliver_insights()` function exists** - Searched for `deliver_insight|deliver_insights|insight_deliver` - no matches

3. **ActionRouter only creates downstream actions** - It writes to:
   - `memory_semantic`
   - `proactive_proposals`
   - `aria_action_queue`
   - `notifications`
   - `pulse_signals`
   - `briefing_queue`

   But it does **NOT**:
   - Update `jarvis_insights.delivered_at`
   - Write to `intelligence_delivered`
   - Write to `surfaced_insights`

4. **`intelligence_delivered` table is empty** - No code inserts into this table

### The Gap:
The `jarvis_insights` table has 141 rows but the delivery mechanism was never implemented. Insights are generated and routed, but the final "deliver to user" step is missing.

---

## STEP 6: Action Router Audit

### Status: ✅ WORKING (but not triggered correctly)

**File:** `backend/src/intelligence/action_router.py` (900 lines)

### What It Does:
1. ✅ Loads rules from `action_routing_rules` table (line 128-145)
2. ✅ Matches insights against rules (line 147-195)
3. ✅ Dispatches actions: `write_memory`, `create_proposal`, `create_notification`, `create_pulse`, `update_battle_card`, `draft_email`, `update_briefing`
4. ✅ Logs to `action_execution_log`

### Rule Matching (Lines 147-195):
```python
def _match_rule(self, insight, context, rules):
    # AND logic — all specified conditions must match
    for rule in rules:
        if rule.get("insight_classification") and rule["insight_classification"] != insight_classification:
            continue
        if rule.get("urgency_level") and rule["urgency_level"] != urgency:
            continue
        if rule.get("entity_type") and rule["entity_type"] != entity_type:
            continue
        if rule.get("signal_types") and signal_type not in rule_types:
            continue
        if rule.get("min_confidence", 0) > confidence:
            continue
        return rule
```

### Why Rules Don't Fire:
The 8 rules in `action_routing_rules` likely have specific conditions that don't match the generated insights. For example:
- Rule expects `insight_classification = "competitive_intelligence"` but insights have `classification = "threat"` or `"opportunity"`
- Rule expects `entity_type = "competitor"` but context doesn't set this correctly

### The `intelligence_delivered` Table:
**This table is NEVER written to.** The ActionRouter logs to `action_execution_log` but there's no code that inserts into `intelligence_delivered`.

---

## STEP 7: Jarvis Engines Audit

### Status: ✅ BUILT AND WORKING

**File:** `backend/src/intelligence/orchestrator.py`

### Engines (Lazy-Loaded):
| Engine | Status | Purpose |
|--------|--------|---------|
| CausalChainEngine | ✅ Built | Traverses causal relationships |
| ImplicationEngine | ✅ Built | Derives implications from signals |
| ButterflyDetector | ✅ Built | Detects cascade effects |
| CrossDomainConnectionEngine | ✅ Built | Finds non-obvious connections |
| GoalImpactMapper | ✅ Built | Assesses goal impact |
| PredictiveEngine | ✅ Built | Generates predictions |
| MentalSimulationEngine | ✅ Built | Runs what-if scenarios |
| MultiScaleTemporalReasoner | ✅ Built | Time-scale analysis |
| TimeHorizonAnalyzer | ✅ Built | Categorizes urgency |

### Triggering:
All engines are triggered via `JarvisOrchestrator.process_event()` which is called from:
- `scout_signal_scan_job.py` (line 214-228)
- `signal_radar.py` capability (via `create_alerts()`)

### The Missing Link:
Engines generate insights correctly, but **delivery is not implemented**. The orchestrator persists to `jarvis_insights` and routes through `ActionRouter`, but neither updates `delivered_at`.

---

## STEP 8: Monitored Entities Integration Audit

### Status: ⚠️ PARTIAL

**Files:**
- `backend/src/services/monitored_entity_service.py`
- `backend/src/jobs/scout_signal_scan_job.py`

### The Service:
`MonitoredEntityService` provides `ensure_entity()` for upserting entities. Used by:
- Lead creation
- Onboarding enrichment
- ICP profile saves

### The Scanner Integration:
`scout_signal_scan_job.py` **READS** from `monitored_entities` (lines 331-345):
```python
# 3. Entity names from monitored_entities table
try:
    monitored_result = (
        db.table("monitored_entities")
        .select("entity_name")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .limit(20)
        .execute()
    )
    for entity in monitored_result.data or []:
        name = entity.get("entity_name")
        if name:
            entities.add(name)
except Exception:
    pass
```

### The Problem:
**`last_checked_at` is never updated.** The scanner reads entities but doesn't write back when they were last scanned.

### Fix Required:
Add to `scout_signal_scan_job.py` after processing each user:
```python
db.table("monitored_entities")
    .update({"last_checked_at": datetime.now(UTC).isoformat()})
    .eq("user_id", user_id)
    .eq("is_active", True)
    .execute()
```

---

## STEP 9: Watch Topics Integration Audit

### Status: ✅ WORKING

**File:** `backend/src/intelligence/watch_topics_service.py` (287 lines)

### Integration Point:
In `scout_signal_scan_job.py` (lines 152-172):
```python
# Check watch topics for this signal
try:
    from src.intelligence.watch_topics_service import WatchTopicsService

    wts = WatchTopicsService(db)
    watch_matches = await wts.match_signal(
        user_id=user_id,
        signal={
            "id": signal_id,
            "headline": headline,
            "company_name": canonical_company_name,
            "signal_type": signal.get("signal_type", "news"),
        },
    )
```

### What It Does:
1. ✅ Matches signals against user's watch topics
2. ✅ Updates `watch_topics.signal_count` and `last_matched_at`
3. ✅ Writes match to `memory_semantic`

### Status:
This is properly wired. The single `watch_topics` row in the database just hasn't matched any signals yet (or the topic keywords don't align with detected signals).

---

## STEP 10: WebSocket/Notification Delivery Audit

### Status: ⚠️ PARTIAL

**File:** `backend/src/core/ws.py` (inferred from usage)

### Delivery Paths:

1. **IntelligencePulseEngine** (for `immediate` channel):
   ```python
   await ws_manager.send_signal(
       user_id=user_id,
       signal_type=record.get("signal_category", "system"),
       title=record["title"],
       severity="high" if record.get("priority_score", 0) >= 90 else "medium",
       data={...}
   )
   ```

2. **ProactiveRouter** (for HIGH priority):
   ```python
   await ws_manager.send_aria_message(
       user_id=user_id,
       message=f"I noticed something important: {message}",
       rich_content=rich_content,
       ui_commands=ui_commands,
       suggestions=suggestions,
   )
   ```

3. **ProactiveRouter** (for MEDIUM priority):
   ```python
   await ws_manager.send_to_user(
       user_id,
       {"type": "signal.detected", "payload": {...}}
   )
   ```

### The Problem:
**These only fire if:**
1. Pulse Engine channel is `immediate` (requires priority_score >= 90)
2. ProactiveRouter receives HIGH/MEDIUM priority signals

**But the delivery confirmation is not tracked in `intelligence_delivered` or `surfaced_insights` tables.**

### Missing:
- No `send_intelligence` WebSocket event type for jarvis insights
- No code reads from `pulse_signals` for morning briefing
- No code reads from `jarvis_insights` for delivery

---

## ROOT CAUSE SUMMARY

| Component | Issue | Impact |
|-----------|-------|--------|
| **jarvis_insights** | `delivered_at` never set | 141 insights exist, user never sees them |
| **pulse_signals** | Only `immediate` delivered, others never consumed | Non-urgent signals never reach user |
| **intelligence_delivered** | Table never written to | Tracking layer is dead |
| **surfaced_insights** | Table never written to | Tracking layer is dead |
| **monitored_entities** | `last_checked_at` never updated | Can't tell if monitoring is working |
| **action_routing_rules** | Rules don't match insight classifications | Rules exist but never fire |
| **SignalRadarCapability** | Not called by scheduler | Rich multi-source scanning is orphaned |
| **Briefing/Digest** | Don't query pulse_signals | Check-in/morning_brief channels never consumed |

---

## PRIORITIZED FIX LIST

### P0 - Critical (User sees nothing)

#### Fix 1: Implement jarvis_insights Delivery
**File:** `backend/src/intelligence/orchestrator.py`
**Location:** After line 590 in `process_event()`

```python
# Add after deduplicated insights are scored:
for insight in deduplicated[:5]:
    try:
        # Create notification for high-urgency insights
        if insight.urgency >= 0.7:
            from src.services.notification_service import NotificationService
            from src.models.notification import NotificationType

            await NotificationService.create_notification(
                user_id=user_id,
                type=NotificationType.SIGNAL_DETECTED,
                title=insight.title or insight.trigger_event[:100],
                message=insight.content[:500],
                link="/intelligence",
                metadata={"insight_id": str(insight.id), "classification": insight.classification},
            )

        # Mark as delivered
        self._db.table("jarvis_insights").update(
            {"delivered_at": datetime.now(UTC).isoformat()}
        ).eq("id", str(insight.id)).execute()

        # Write to intelligence_delivered for tracking
        self._db.table("intelligence_delivered").insert({
            "user_id": user_id,
            "insight_id": str(insight.id),
            "delivery_channel": "notification" if insight.urgency >= 0.7 else "briefing_queue",
            "delivered_at": datetime.now(UTC).isoformat(),
        }).execute()
    except Exception:
        logger.warning("Failed to deliver insight %s", insight.id)
```

**Prompt for Claude Code:**
```
In backend/src/intelligence/orchestrator.py, after line 590 (after the action routing loop in process_event()), add delivery logic that:
1. Creates notifications for insights with urgency >= 0.7
2. Updates jarvis_insights.delivered_at for all returned insights
3. Inserts into intelligence_delivered for tracking
Import NotificationService and NotificationType. Handle exceptions gracefully.
```

---

#### Fix 2: Update monitored_entities.last_checked_at
**File:** `backend/src/jobs/scout_signal_scan_job.py`
**Location:** After line 288 (after deduplication completes)

```python
# Update last_checked_at for all monitored entities
try:
    db.table("monitored_entities")
        .update({"last_checked_at": datetime.now(UTC).isoformat()})
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
except Exception:
    logger.debug("Failed to update monitored_entities.last_checked_at")
```

**Prompt for Claude Code:**
```
In backend/src/jobs/scout_signal_scan_job.py, after the signal deduplication block (around line 288), add code to update monitored_entities.last_checked_at for the current user. Use datetime.now(UTC).isoformat() and handle exceptions gracefully.
```

---

### P1 - High (Intelligence not flowing correctly)

#### Fix 3: Wire SignalRadarCapability to Scheduler
**File:** `backend/src/services/scheduler.py`
**Location:** Add new job after `scout_signal_scan` job

```python
async def _run_signal_radar_scan() -> None:
    """Run SignalRadar capability for multi-source intelligence."""
    try:
        from src.agents.capabilities.signal_radar import run_signal_radar_cron
        await run_signal_radar_cron()
    except Exception:
        logger.exception("Signal radar scheduler run failed")

# In start_scheduler():
_scheduler.add_job(
    _run_signal_radar_scan,
    trigger=CronTrigger(hour="*/2"),  # Every 2 hours (expensive)
    id="signal_radar_scan",
    name="SignalRadar multi-source intelligence scan",
    replace_existing=True,
)
```

**Prompt for Claude Code:**
```
In backend/src/services/scheduler.py:
1. Add a new async function _run_signal_radar_scan() that imports and calls run_signal_radar_cron() from src.agents.capabilities.signal_radar
2. Register it in start_scheduler() to run every 2 hours with id="signal_radar_scan"
3. Add appropriate exception handling and logging
```

---

#### Fix 4: Fix action_routing_rules Matching
**File:** `backend/src/intelligence/action_router.py`
**Location:** Line 147 in `_match_rule()`

The rules likely don't fire because the context doesn't populate `entity_type` and `signal_type` correctly. Need to ensure `JarvisOrchestrator` passes enriched context:

```python
# In orchestrator.py process_event(), ensure context includes:
enriched_context["entity_type"] = _classify_entity(event, enriched_context)
enriched_context["signal_type"] = _extract_signal_type(event)
```

**Prompt for Claude Code:**
```
In backend/src/intelligence/orchestrator.py, in the process_event() method, before calling ActionRouter.route_insight(), ensure the enriched_context dict includes:
1. entity_type - classify as "competitor", "prospect", "industry", or "own_company" based on context enrichment
2. signal_type - extract from the event (e.g., "funding", "leadership", "regulatory")
This will enable action_routing_rules to match correctly.
```

---

### P2 - Medium (Channels not consumed)

#### Fix 5: Wire pulse_signals to Briefing Generator
**File:** `backend/src/services/briefing.py` or `backend/src/jobs/daily_briefing_job.py`

Add code to query `pulse_signals` for morning_brief and check_in channels:

```python
# Get undelivered pulse signals for briefing
undelivered = (
    db.table("pulse_signals")
    .select("*")
    .eq("user_id", user_id)
    .eq("delivery_channel", "morning_brief")
    .is_("delivered_at", "null")
    .order("priority_score", desc=True)
    .limit(10)
    .execute()
)

# Mark as delivered after including in briefing
db.table("pulse_signals").update(
    {"delivered_at": datetime.now(UTC).isoformat()}
).in_("id", [s["id"] for s in undelivered.data]).execute()
```

**Prompt for Claude Code:**
```
In the daily briefing generation job (backend/src/jobs/daily_briefing_job.py), add a step that:
1. Queries pulse_signals for the user where delivery_channel = 'morning_brief' and delivered_at IS NULL
2. Includes these signals in the briefing content
3. Updates delivered_at for consumed signals
This ensures the 'morning_brief' delivery channel actually delivers to users.
```

---

#### Fix 6: Add Intelligence Delivered Tracking
**File:** `backend/src/intelligence/action_router.py`
**Location:** After each action execution in `route_insight()`

```python
# After successful action dispatch, log to intelligence_delivered
if insight.get("id") and actions_taken:
    self._db.table("intelligence_delivered").insert({
        "user_id": user_id,
        "insight_id": insight["id"],
        "delivery_channel": "action_router",
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
```

**Prompt for Claude Code:**
```
In backend/src/intelligence/action_router.py, in route_insight() method after successfully dispatching actions, insert a record into intelligence_delivered table with the insight_id, user_id, delivery_channel, and delivered_at timestamp. Do this inside the _log_execution method or after it.
```

---

## DATABASE STATE EVIDENCE

```sql
-- 10 entities, never scanned
SELECT COUNT(*) FROM monitored_entities WHERE last_checked_at IS NULL;  -- 10

-- 222 signals, most from exa_competitor_scan (only 5 competitors seeded)
SELECT source_name, COUNT(*) FROM market_signals GROUP BY source_name;
-- exa_competitor_scan: 112

-- 141 insights, none delivered
SELECT COUNT(*) FROM jarvis_insights WHERE delivered_at IS NULL;  -- 141

-- Empty tracking tables
SELECT COUNT(*) FROM intelligence_delivered;  -- 0
SELECT COUNT(*) FROM surfaced_insights;       -- 0
SELECT COUNT(*) FROM user_pulse_config;       -- 0
SELECT COUNT(*) FROM jarvis_engine_metrics;   -- 0

-- 8 rules that never fire
SELECT COUNT(*) FROM action_routing_rules;   -- 8
SELECT COUNT(*) FROM action_execution_log;   -- likely 0
```

---

## ARCHITECTURE DIAGRAM

```
                    ┌──────────────────────────────────────────────────────────┐
                    │                    SIGNAL DETECTION                       │
                    └──────────────────────────────────────────────────────────┘
                                              │
           ┌──────────────────────────────────┼──────────────────────────────────┐
           │                                  │                                  │
           ▼                                  ▼                                  ▼
   ┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
   │   ScoutAgent      │          │ SignalRadar       │          │  ExaCompetitor    │
   │   (scheduler)     │          │ (NOT SCHEDULED!)  │          │  Scan (seeded)    │
   │   ✅ Working      │          │   ❌ Orphaned     │          │   ✅ Working      │
   └─────────┬─────────┘          └─────────┬─────────┘          └─────────┬─────────┘
             │                              │                              │
             │                              │                              │
             └──────────────────────────────┼──────────────────────────────┘
                                            │
                                            ▼
                    ┌──────────────────────────────────────────────────────────┐
                    │                 market_signals TABLE                      │
                    │                    222 rows ✅                             │
                    └──────────────────────────────────────────────────────────┘
                                            │
                     ┌──────────────────────┴──────────────────────┐
                     │                                             │
                     ▼                                             ▼
   ┌───────────────────────────┐                 ┌───────────────────────────┐
   │  IntelligencePulseEngine  │                 │   JarvisOrchestrator      │
   │  ✅ Working               │                 │   ✅ Working               │
   │                           │                 │                           │
   │  - Scores salience        │                 │  - Runs 9 engines         │
   │  - Determines channel     │                 │  - Persists to DB         │
   │  - Delivers immediate     │                 │  - Routes to ActionRouter │
   └─────────────┬─────────────┘                 └─────────────┬─────────────┘
                 │                                             │
                 ▼                                             ▼
   ┌───────────────────────────┐                 ┌───────────────────────────┐
   │    pulse_signals TABLE    │                 │   jarvis_insights TABLE   │
   │    ⚠️ Partial             │                 │   ❌ delivered_at = NULL  │
   │                           │                 │                           │
   │  - Only "immediate"       │                 │  - 141 insights exist     │
   │    delivered              │                 │  - NONE delivered         │
   │  - morning_brief never    │                 │  - ActionRouter called    │
   │    consumed               │                 │    but rules don't match  │
   └───────────────────────────┘                 └───────────────────────────┘
                 │                                             │
                 │                                             │
                 ▼                                             ▼
   ┌───────────────────────────┐                 ┌───────────────────────────┐
   │   NOT IMPLEMENTED:        │                 │   ActionRouter            │
   │   Briefing/Digest query   │                 │   ⚠️ Partial              │
   │   of pulse_signals        │                 │                           │
   │                           │                 │  - 8 rules exist          │
   │   ❌ MISSING              │                 │  - Never fire (mismatch)  │
   └───────────────────────────┘                 │  - Creates proposals      │
                                                 │  - Creates notifications  │
                                                 └─────────────┬─────────────┘
                                                               │
                                                               ▼
                                                 ┌───────────────────────────┐
                                                 │   intelligence_delivered  │
                                                 │   ❌ EMPTY (0 rows)       │
                                                 │   Never written to        │
                                                 └───────────────────────────┘

```

---

## CONCLUSION

The Intelligence Pulse Engine has solid foundations:
- ✅ Scheduler is properly configured
- ✅ Signal detection works (ScoutAgent)
- ✅ Intelligence engines exist and run
- ✅ Storage tables are populated

But delivery is fundamentally broken:
- ❌ `jarvis_insights.delivered_at` never set
- ❌ `pulse_signals` non-immediate channels never consumed
- ❌ `intelligence_delivered` never written
- ❌ `monitored_entities.last_checked_at` never updated
- ❌ `SignalRadarCapability` is orphaned
- ❌ Action routing rules don't match

**The fix is straightforward:** Add delivery confirmation to the orchestrator, wire pulse_signals to briefings, and fix the entity tracking.

---

*Report generated: 2026-03-10*
*Auditor: Claude Code*
