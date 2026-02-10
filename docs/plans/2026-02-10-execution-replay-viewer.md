# Execution Replay Viewer Design

**Date:** 2026-02-10
**Feature:** Full execution replay for skill audit log entries
**Status:** Validated

## Overview

A detailed execution replay page that makes every ARIA skill action fully transparent. Accessed from the Activity Feed, Skill Audit Log, or Skill Activity entries. Includes server-side PDF export for compliance.

## Backend

### New Endpoint: `GET /api/skills/audit/{execution_id}/replay`

Assembles full execution context by joining:
- `skill_audit_log` — primary audit record (hashes, data classes, security flags, timing, agent, trigger)
- `skill_execution_plans` — plan DAG, risk level, reasoning, status, timing
- `skill_working_memory` — per-step details (input/output summaries, artifacts, extracted facts, timing)

**Response model** `ExecutionReplayResponse`:
- `audit_entry` — full audit log record
- `plan` — execution plan (if multi-step, else null)
- `steps` — working memory entries ordered by step_number
- `trust_impact` — `{before: string, after: string, delta: "increased" | "decreased" | "unchanged"}`
- `data_access_audit` — `{requested: string[], granted: string[], redacted_fields: string[]}`
- `user_clearance` — `"admin" | "manager" | "rep"`

### Role-Based Redaction (3-tier)

- **Admin:** Full raw input/output data, all fields visible
- **Manager:** Data for granted classes only, denied classes redacted
- **Rep:** Summaries only (input_summary, output_summary from working memory), no raw data

Role derived from existing `CurrentUser` dependency (user metadata / tenant role).

### PDF Export: `GET /api/skills/audit/{execution_id}/replay/pdf`

Server-side PDF generation using WeasyPrint. Renders a Jinja2 HTML template with the same role-based redaction applied. Returns `application/pdf` content type.

## Frontend

### Route

`/dashboard/skills/audit/:executionId` — nested under existing dashboard layout.

### Component: `ExecutionReplayViewer.tsx`

**Layout (top to bottom):**

1. **Header bar** — Skill name, execution ID (truncated), timestamp, status badge (success/fail), "Download Audit Report" button
2. **Summary strip** — Four metric cards:
   - Execution time (color: green <500ms, yellow <2s, red >2s)
   - Agent (with agent color from ActivityFeed palette)
   - Trigger reason (user-initiated / scheduled / autonomous)
   - Risk level badge (low/medium/high/critical)
3. **Execution Timeline** — Vertical timeline with expandable step nodes:
   - Step number + skill name, status icon, execution time
   - Expandable: input data (redacted per clearance), prompt (LLM skills), API calls (capabilities), output data, extracted facts
4. **Trust Impact Panel** — Before/after trust level labels with colored delta arrow (green up, red down, gray neutral)
5. **Data Access Audit Panel** — Two columns:
   - Requested data classes (neutral pills)
   - Granted (green) vs Denied (red + lock icon)
   - Redaction notice if applicable
6. **Hash Chain Verification** — Collapsible section showing previous_hash → entry_hash

### Activity Feed Integration

- **SkillActivityEntry.tsx** — Add "View Replay" link → `/dashboard/skills/audit/{execution_id}`
- **SkillAuditLog.tsx** — Make rows clickable → navigate to replay viewer
- **ActivityFeedPage.tsx** — Add "View full replay" link in expanded skill execution entries

## Files to Create

- `backend/src/api/routes/skill_replay.py` — Replay + PDF endpoints
- `backend/src/skills/replay_service.py` — Data assembly + role-based redaction
- `backend/src/skills/replay_pdf.py` — HTML template + WeasyPrint rendering
- `frontend/src/components/skills/ExecutionReplayViewer.tsx` — Main component

## Files to Modify

- `backend/src/api/routes/skills.py` — Include replay router
- `frontend/src/api/skills.ts` — Add replay API functions + types
- `frontend/src/hooks/useSkills.ts` — Add `useExecutionReplay` hook
- `frontend/src/App.tsx` — Add replay route
- `frontend/src/components/skills/SkillActivityEntry.tsx` — Add replay link
- `frontend/src/components/skills/SkillAuditLog.tsx` — Make rows clickable
- `frontend/src/pages/ActivityFeedPage.tsx` — Add replay link for skill activities
