# Skill Discovery Agent Design

**Date:** 2026-02-10
**File:** `backend/src/skills/discovery.py`

## Overview

Background service that analyzes user behavior to identify skill gaps and recommends marketplace skills to fill them. Runs weekly or on-demand.

## Data Models

- **GapReport** — Identified usage gap with evidence, frequency, keywords
- **SkillRecommendation** — Marketplace skill scored against a gap (relevance, security, community)
- **Recommendation** — Gap + matched skills + LLM-generated natural language message

## Methods

### `analyze_usage_gaps(user_id) -> list[GapReport]`

Queries three tables:
1. `skill_execution_plans` — slow/failed executions
2. `messages` — unhandled conversation requests
3. `aria_activity` — repeated manual workarounds

Single LLM call synthesizes raw evidence into structured GapReports with keywords.

### `search_marketplace(gap) -> list[SkillRecommendation]`

Searches `SkillIndex` using gap keywords. Scores candidates:
- 40% relevance (keyword overlap)
- 25% security compliance (trust level + data access)
- 20% community signal (install count)
- 15% life sciences bonus

No LLM call. Returns top 5 per gap.

### `recommend(user_id) -> list[Recommendation]`

Full pipeline: analyze gaps → search marketplace → generate messages → notify user.
- LLM generates conversational recommendation text
- Delivers via NotificationService
- Logs to aria_activity for dashboard
- Deduplicates against recent recommendations (7-day window)

### Entry Points

- `run_weekly(user_id)` — scheduler entry
- `run_on_demand(user_id)` — API entry
- `refresh_index()` — sync skills_index from skills.sh
