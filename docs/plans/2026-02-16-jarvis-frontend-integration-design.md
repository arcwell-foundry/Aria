# Jarvis Intelligence Frontend Integration Design

**Date:** 2026-02-16
**Status:** Approved
**Scope:** Surface Phase 7 Jarvis intelligence engines in the frontend UI

## Overview

Phase 7 built 10 intelligence engines in the backend (Jarvis). They are fully
implemented with API endpoints but have no frontend exposure. This design covers
the 4 minimum viable integrations that give users immediate access to Jarvis
intelligence.

## Integration 1: Daily Briefing as ARIA's First Message

**Location:** ARIA Workspace (`ARIAWorkspace.tsx`)

When a user opens ARIA Workspace on a new day, ARIA proactively sends the daily
briefing as a rich content message in the conversation thread.

### Data Flow

1. `ARIAWorkspace` mounts → calls `useTodayBriefing()` hook
2. If briefing exists and hasn't been shown in this session → inject it as an
   `aria` message with `rich_content[]` containing structured briefing cards
3. If no briefing exists → call `generateBriefing()`, show thinking indicator

### Rich Content Cards

- **Calendar card** — meeting count + key meetings list (time, title, attendees)
- **Leads card** — hot leads, needs-attention leads with health scores
- **Signals card** — company news, market trends, competitive intel items
- **Tasks card** — overdue + due today

### Implementation

- Add `useEffect` in `ARIAWorkspace` checking `useTodayBriefing()` data
- Session-scoped ref prevents re-injection on re-renders
- Inject via `addMessage()` with role `'aria'` and structured `rich_content[]`
- New `BriefingCard` component renders each section (calendar, leads, signals,
  tasks) as expandable sub-cards within the message

### Backend Endpoints Used

- `GET /briefings/today` — fetch today's briefing
- `POST /briefings/generate` — generate if missing

---

## Integration 2: Market Signals Feed on Intelligence Page

**Location:** Intelligence Page (`IntelligencePage.tsx`)

Replace the "coming soon" empty state in the Market Signals section with a live
signal feed.

### Data Flow

1. New `MarketSignalsFeed` component
2. Uses `useSignals()` hook (calls `GET /signals`)
3. Renders scrollable list with type filtering and read/dismiss actions

### Signal Card Design

- Left: type icon (color-coded by signal_type)
- Center: company name (bold) + content (2-line clamp) + source
- Right: relative timestamp (font-mono) + read/dismiss buttons
- Unread signals get left-border accent

### Signal Type Colors

| Type | Color | Icon |
|------|-------|------|
| funding | green | DollarSign |
| fda_approval | blue | Shield |
| clinical_trial | purple | FlaskConical |
| patent | amber | FileText |
| leadership | slate | UserCog |
| earnings | emerald | TrendingUp |
| partnership | indigo | Handshake |
| regulatory | orange | Scale |
| product | cyan | Package |
| hiring | pink | Users |

### Filters

- Signal type chip row (All + each type)
- Unread-only toggle

### Header

- Unread count badge next to "Market Signals" heading
- "Mark all read" action link

### Implementation

- New `MarketSignalsFeed` component in `components/intelligence/`
- Replace `EmptyState` in `IntelligencePage` market signals section
- Add `useSignals` hook call with filter state

### Backend Endpoints Used

- `GET /signals` — list signals with filters
- `GET /signals/unread/count` — badge count
- `POST /signals/{id}/read` — mark read
- `POST /signals/read-all` — mark all read
- `POST /signals/{id}/dismiss` — dismiss

---

## Integration 3: Upcoming Meetings on Actions Page

**Location:** Actions Page (`ActionsPage.tsx`)

Add an "Upcoming Meetings" section at the top of the Actions page with
expandable pre-meeting research briefs.

### Data Flow

1. New `UpcomingMeetings` component
2. Uses `useUpcomingMeetings()` hook (calls `GET /meetings/upcoming`)
3. Each meeting expandable → loads full brief via `useMeetingBrief(eventId)`

### Meeting Card Design

**Collapsed:**
- Meeting time (font-mono), title, attendee count, brief status badge

**Expanded:**
- Summary paragraph
- Attendee profiles (name, title, company, talking points)
- Suggested agenda items
- Risks & opportunities

**Actions:**
- "Generate Brief" button for meetings without briefs
- Generating state: skeleton pulse, polls every 3 seconds

### Edge Cases

- No calendar integration → empty state directing to Settings
- No upcoming meetings → informational message
- Brief generating → automatic polling via hook

### Implementation

- New `UpcomingMeetings` + `MeetingCard` components in `components/actions/`
- Wire into `ActionsPage.tsx` above "Active Goals" section

### Backend Endpoints Used

- `GET /meetings/upcoming` — list meetings
- `GET /meetings/{id}/brief` — get brief
- `POST /meetings/{id}/brief/generate` — generate brief

---

## Integration 4: Intelligence Context on Draft Detail

**Location:** Draft Detail Page (`DraftDetailPage.tsx`)

Add a collapsible "Intelligence Context" section showing Jarvis insights
relevant to the email draft's recipient.

### Data Flow

1. Load draft → extract `lead_id` from metadata
2. If lead exists → `useIntelLeadInsights(leadId)` for Jarvis insights
3. Also `useSignals({ company })` for relevant signals
4. Render as collapsible panel above email body

### Section Design

- Collapsible panel, starts collapsed
- Title: "Intelligence Context" with Zap icon
- When expanded:
  - Lead insights (opportunities/threats with classification colors)
  - Relevant market signals for the company
  - Suggested talking points from meeting briefs (if applicable)
- Styled consistently with `JarvisInsightsModule`

### Implementation

- New `DraftIntelligenceContext` component in `components/communications/`
- Integrate into `DraftDetailPage.tsx` as collapsible section
- Reuses `useIntelLeadInsights`, `useSignals` hooks

### Backend Endpoints Used

- `GET /intelligence/insights` — filtered by lead/entity
- `GET /signals` — filtered by company

---

## Files to Create

1. `frontend/src/components/conversation/BriefingCard.tsx`
2. `frontend/src/components/intelligence/MarketSignalsFeed.tsx`
3. `frontend/src/components/actions/UpcomingMeetings.tsx`
4. `frontend/src/components/actions/MeetingCard.tsx`
5. `frontend/src/components/communications/DraftIntelligenceContext.tsx`

## Files to Modify

1. `frontend/src/components/pages/ARIAWorkspace.tsx` — inject briefing message
2. `frontend/src/components/pages/IntelligencePage.tsx` — replace signals empty state
3. `frontend/src/components/pages/ActionsPage.tsx` — add meetings section
4. `frontend/src/components/pages/DraftDetailPage.tsx` — add intelligence context
5. `frontend/src/hooks/useIntelPanelData.ts` — add signal mutation hooks if needed

## Existing Hooks/APIs Reused (No New Backend Work)

- `useTodayBriefing()`, `useGenerateBriefing()` — briefings
- `useSignals()` — signals
- `useUpcomingMeetings()`, `useMeetingBrief()`, `useGenerateMeetingBrief()` — meetings
- `useIntelLeadInsights()` — lead insights
- `useInsightFeedback()` — feedback on insights

## Engines Surfaced

| Engine | Where Visible | How Accessed |
|--------|--------------|--------------|
| Daily Intel Briefings | ARIA Workspace first message | Auto on new day |
| Market Signal Monitoring | Intelligence page signal feed | Browse + filter |
| Pre-Meeting Research | Actions page meetings section | Expand meeting card |
| Email Drafting Intelligence | Draft detail intel context | Expand on draft review |
| Competitive Battle Cards | Already on Intelligence page | Existing (verified) |
| Jarvis Orchestrator | Intel Panel (JarvisInsightsModule) | Existing (verified) |

### Not Yet Surfaced (Future Work)

| Engine | Suggested Location |
|--------|--------------------|
| Calendar Management | Dedicated calendar view or sidebar widget |
| Territory Planning | Pipeline page territory section |
| Document Intelligence | Actions page or dedicated documents view |
| KOL Mapping | Intelligence page KOL section |
| Compliance Guardian | Settings or inline warnings |
