# First Conversation & Morning Briefing — Design

**Date:** 2026-02-11
**Status:** Approved

## Overview

Build the two most critical "first impression" moments: the First Conversation Generator (ARIA's opening after onboarding) and the Morning Briefing flow (daily intelligence delivery via Dialogue Mode).

## Backend Enhancements

### FirstConversationGenerator (`backend/src/onboarding/first_conversation.py`)

**Current state:** Returns `FirstConversationMessage` with `content` (text), `memory_delta`, `suggested_next_action`, `facts_referenced`, `confidence_level`.

**Enhancements:**
- Add `rich_content: list[dict]`, `ui_commands: list[dict]`, `suggestions: list[str]` fields to `FirstConversationMessage`
- After composing the text message, add a second LLM call that proposes 3-4 goals as GoalPlanCard rich content items based on gathered facts, classification, gaps, role, and company info
- Each goal card: `{type: "goal_plan", data: {id, title, rationale, approach, agents, timeline, status: "proposed"}}`
- Add `ui_commands` for sidebar badges (e.g., `update_sidebar_badge` for Intelligence with competitor count)
- Add `suggestions` list: `["Tell me more about Goal 1", "What competitors did you find?", "Start with the pipeline goal"]`
- New method `_generate_goal_proposals()` — uses LLM to produce structured goal proposals
- New method `_deliver_via_websocket()` — calls `ws_manager.send_to_user()` with `AriaMessageEvent`

### BriefingService (`backend/src/services/briefing.py`)

**Current state:** Returns flat dict with `summary`, `calendar`, `leads`, `signals`, `tasks`. Uses raw Anthropic client instead of `LLMClient`.

**Enhancements:**
- Add `rich_content`, `ui_commands`, `suggestions` fields to briefing output
- Build `MeetingCard`, `SignalCard`, `AlertCard` rich content from gathered data
- Add goal progress gathering (query active goals)
- New method `_build_rich_content()` — converts raw data into typed rich content cards
- New method `_build_ui_commands()` — generates sidebar badge updates and intel panel content
- New route `POST /api/v1/briefings/deliver` — generates briefing AND pushes via WebSocket as `AriaMessageEvent`
- Switch from raw `anthropic.Anthropic` to `LLMClient` for consistency

### Goal Approval Endpoints

- `POST /api/v1/goals` — creates goal from GoalPlanCard approval data
- `POST /api/v1/goals/{id}/approve` — approves execution plan, triggers OODA loop
- Both return responses with `rich_content` (ExecutionPlanCard) delivered via WebSocket

## Frontend Components

### GoalPlanCard (`frontend/src/components/rich/GoalPlanCard.tsx`)

- Dark theme context (ARIA Workspace conversation)
- Title: `font-display italic` (Instrument Serif)
- Rationale: why ARIA recommends this goal
- Approach: agent badges (Hunter, Analyst, etc.) + strategy summary
- Timeline estimate: `font-mono` (JetBrains Mono)
- Buttons: `[Approve]` (accent blue), `[Modify]` (outline), `[Discuss]` (ghost)
- Approve → `POST /api/v1/goals` to create goal → ARIA responds with ExecutionPlanCard
- Discuss → injects "Tell me more about {title}" as user message
- Modify → injects "I'd like to adjust {title}" as user message

### ExecutionPlanCard (`frontend/src/components/rich/ExecutionPlanCard.tsx`)

- Phased timeline: vertical stepper with phase markers
- Each phase: name, timeline bar, agent badges, expected output text
- Autonomy indicator: what ARIA handles vs. what needs approval
- Buttons: `[Approve Plan]`, `[Modify]`, `[Discuss Further]`
- Approve Plan → `POST /api/v1/goals/{id}/approve` → starts OODA loop

### Briefing Cards

- **MeetingCard** (`frontend/src/components/rich/MeetingCard.tsx`): company name, time, attendees count, "View Brief" button
- **SignalCard** (`frontend/src/components/rich/SignalCard.tsx`): signal type badge, headline, health score delta, "Draft Outreach" button
- **AlertCard** (`frontend/src/components/rich/AlertCard.tsx`): severity indicator, competitor name, headline, "View Battle Card" button

### RichContentRenderer (`frontend/src/components/rich/RichContentRenderer.tsx`)

- Replaces the generic placeholder rendering in `MessageBubble` (lines 85-99)
- Switches on `rc.type`: `goal_plan` → GoalPlanCard, `execution_plan` → ExecutionPlanCard, `meeting_card` → MeetingCard, `signal_card` → SignalCard, `alert_card` → AlertCard
- Falls back to generic display for unknown types

### MessageBubble Enhancement

- Import and use `RichContentRenderer` in place of current generic rich_content rendering

## Wiring & Integration

### First Conversation Trigger
- Onboarding flow already calls `FirstConversationGenerator.generate()`
- After generate returns, push via `ws_manager.send_to_user()` with full `AriaMessageEvent`
- ARIAWorkspace already listens for `aria.message` — GoalPlanCards appear via RichContentRenderer

### Briefing Dialogue Mode Flow
1. User navigates to `/briefing` → `DialogueMode` mounts with `sessionType="briefing"`
2. Frontend calls `POST /api/v1/briefings/deliver`
3. Backend generates briefing + pushes via WebSocket as `AriaMessageEvent`
4. Briefing message streams into TranscriptPanel
5. Rich cards (MeetingCard, SignalCard) render inline in transcript
6. `avatar_script` field feeds Tavus TTS (existing `aria.speaking` handling)
7. BriefingControls (play/pause/rewind) already exist

### Goal Approval Flow
1. User clicks Approve on GoalPlanCard
2. `POST /api/v1/goals` creates the goal
3. Backend responds via WebSocket with ExecutionPlanCard
4. User clicks Approve Plan on ExecutionPlanCard
5. `POST /api/v1/goals/{id}/approve` triggers OODA loop execution

## Files to Create/Modify

**Create:**
- `frontend/src/components/rich/GoalPlanCard.tsx`
- `frontend/src/components/rich/ExecutionPlanCard.tsx`
- `frontend/src/components/rich/MeetingCard.tsx`
- `frontend/src/components/rich/SignalCard.tsx`
- `frontend/src/components/rich/AlertCard.tsx`
- `frontend/src/components/rich/RichContentRenderer.tsx`
- `frontend/src/api/goals.ts` (API client for goal approval)

**Modify:**
- `backend/src/onboarding/first_conversation.py` — add rich_content, ui_commands, suggestions, goal proposal generation, WebSocket delivery
- `backend/src/services/briefing.py` — add rich_content building, ui_commands, WebSocket delivery, switch to LLMClient
- `backend/src/api/routes/briefings.py` — add `/deliver` endpoint
- `backend/src/api/routes/goals.py` — add/enhance approval endpoint with WebSocket response
- `backend/src/models/ws_events.py` — no changes needed (AriaMessageEvent already supports all fields)
- `frontend/src/components/conversation/MessageBubble.tsx` — use RichContentRenderer
- `frontend/src/components/avatar/DialogueMode.tsx` — trigger briefing delivery on mount when sessionType="briefing"
