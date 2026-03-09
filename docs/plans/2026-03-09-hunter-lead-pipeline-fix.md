# Hunter Lead Pipeline Fix Design

## Problem Statement

The Hunter agent exists but has NEVER run automatically. Both `leads` and `discovered_leads` tables are empty (0 rows). The entire lead pipeline is broken because:

1. No scheduled job triggers Hunter agent execution
2. Goal progress jumps from 0% to 100% with no incremental updates
3. Outbound email drafts are not saved to users' email client draft folders

## Solution: Scheduled Hunter Job (Option B)

A single scheduled job `_run_hunter_lead_generation()` runs every 30 minutes, queries for ALL active lead generation goals across ALL users, and processes each one in isolation.

### Architecture

```
scheduler.py
    └── _run_hunter_lead_generation() [every 30 min]
            │
            ├── Query active lead_gen goals across all users
            │
            └── For each goal (isolated per user_id):
                    │
                    ├── Run HunterAgent for that user
                    │
                    ├── Write leads to discovered_leads (user-scoped)
                    │
                    ├── For each lead:
                    │       ├── Generate outbound email draft
                    │       └── Save to user's connected email client
                    │           (check user_integrations for active provider)
                    │
                    └── Update goal progress_percentage incrementally
```

## Implementation Plan

### Step 1: Create Hunter Lead Generation Job

**File:** `backend/src/jobs/hunter_lead_job.py`

Creates `run_hunter_lead_generation_job()` that:
1. Queries active lead generation goals (filtered by title/metadata)
2. Only processes users with active email integrations
3. For each goal, runs HunterAgent scoped to that user
4. Writes discovered leads to `discovered_leads` table
5. Generates outbound drafts and saves to email client

### Step 2: Wire Job into Scheduler

**File:** `backend/src/services/scheduler.py`

Add `_run_hunter_lead_generation()` async function and register it with APScheduler to run every 30 minutes.

### Step 3: Implement Email Client Draft Saving

**File:** `backend/src/services/email_client_writer.py` (extend existing)

Create `save_outbound_draft_to_client()`:
1. Queries `user_integrations` for user's active email providers
2. Calls appropriate Composio action (`GMAIL_CREATE_DRAFT` or `OUTLOOK_CREATE_DRAFT`)
3. Updates `email_drafts.saved_to_client = true` on success
4. Handles both providers if both are connected

### Step 4: Add Incremental Goal Progress Tracking

Update goal progress after each lead batch:
- Lead gen goal with target = 10 leads
- Each lead found = +10% progress
- Update `goals.progress_percentage` after each batch

### Step 5: Wire Goal Updates into Daily Briefing

**File:** `backend/src/jobs/daily_briefing_job.py` (extend existing)

Ensure briefing includes goal progress data:
- Title
- progress_percentage
- leads_found count (if lead gen goal)
- Last run timestamp

## Database Queries

### Find Active Lead Gen Goals

```sql
SELECT g.id, g.user_id, g.title, g.description,
       g.progress_percentage, g.metadata
FROM goals g
WHERE g.status = 'active'
AND (
  g.title ILIKE '%lead%'
  OR g.title ILIKE '%find%compan%'
  OR g.title ILIKE '%prospect%'
  OR g.metadata->>'goal_type' IN ('lead_gen', 'prospecting', 'outreach')
)
AND g.user_id IN (
  SELECT DISTINCT user_id FROM user_integrations
  WHERE status = 'active'
);
```

### Check User's Active Email Providers

```sql
SELECT integration_type
FROM user_integrations
WHERE user_id = $1
AND status = 'active'
AND integration_type IN ('gmail', 'outlook', 'outlook_email');
```

## Key Design Decisions

1. **No dynamic per-user scheduling**: Single job processes all users, scales better
2. **User isolation**: Each Hunter run is scoped to a specific user_id
3. **Provider-agnostic**: Check user_integrations, don't assume specific email provider
4. **Incremental progress**: Update progress after each lead, not just at completion
5. **Graceful degradation**: Skip users without email integrations, log but don't fail

## Verification Queries

After fix, these should return real data:

```sql
-- Discovered leads after job runs
SELECT id, source, company_name, created_at
FROM discovered_leads
ORDER BY created_at DESC LIMIT 5;

-- Email drafts saved to client
SELECT id, saved_to_client, source, created_at
FROM email_drafts
ORDER BY created_at DESC LIMIT 5;
```

## Files to Modify/Create

1. **Create:** `backend/src/jobs/hunter_lead_job.py`
2. **Modify:** `backend/src/services/scheduler.py` - add job registration
3. **Extend:** `backend/src/services/email_client_writer.py` - add multi-provider draft saving
4. **Modify:** `backend/src/services/goal_execution.py` - add incremental progress updates
