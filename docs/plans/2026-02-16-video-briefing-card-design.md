# Video Briefing Card - Design Document

**Date:** 2026-02-16
**Status:** Approved
**Scope:** v1 - Core video briefing experience with summary card

## Overview

Enable users to receive their daily briefing as a video delivered by ARIA via the Tavus avatar. When a user opens ARIA in the morning and a briefing is ready, ARIA proposes the briefing with a prominent card. User can watch, read instead, or dismiss. After viewing, a summary card appears in the conversation thread.

## Design Decisions

### 1. Card Placement
**Decision:** ARIA Workspace on app load, ARIA proposes but doesn't force
- When user opens ARIA and briefing is ready + not viewed → VideoBriefingCard appears
- If user dismisses → Card collapses into conversation thread, accessible later
- If user already viewed → Card never appears again for that briefing

### 2. Video Playback Experience
**Decision:** Full Dialogue Mode at `/briefing` route
- Navigate to existing DialogueMode component (avatar left, transcript right)
- Uses existing BriefingControls for pause/skip/speed
- Signals importance with dedicated full-screen experience
- When briefing ends → Navigate back to workspace with summary card in conversation

### 3. Settings Location
**Decision:** "Briefing Delivery" subsection in ARIA Persona settings
- Video toggle (video vs text)
- Preferred briefing time with timezone display
- Duration preference (2/5/10 min)
- No new settings section needed

### 4. Summary Card Content
**Decision:** Key points + action items + replay link (v1 scope)
- 3-5 bullet points from briefing
- Action items with status (pending/done)
- "Replay briefing" link
- No embedded data cards in v1 (v2 enhancement)

### 5. Briefing Ready Detection
**Decision:** REST on load + WebSocket push
- REST handles common case (open app, briefing waiting)
- WebSocket handles edge case (app open when briefing generates)
- Response: `{ ready, viewed, briefing_id, duration, topics }`

---

## Architecture

### Component Structure

```
frontend/src/components/briefing/
├── VideoBriefingCard.tsx      # Card shown when briefing is ready
├── BriefingSummaryCard.tsx    # Post-briefing summary in conversation
└── index.ts                   # Exports

frontend/src/components/settings/
├── BriefingDeliverySection.tsx  # Subsection for ARIA Persona
└── ...

frontend/src/hooks/
└── useBriefingStatus.ts       # Hook for REST check + WebSocket
```

### Data Flow

1. App loads → `useBriefingStatus` calls `GET /api/briefing/status`
2. If briefing ready + not viewed → `VideoBriefingCard` injected into ARIA Workspace
3. User clicks play → Navigate to `/briefing` (DialogueMode)
4. Briefing ends → Navigate back to `/`, `BriefingSummaryCard` in conversation
5. User dismisses card → Card collapses to conversation, accessible later

---

## Component Specifications

### VideoBriefingCard

**Visual:**
```
┌─────────────────────────────────────────────────────────┐
│  🌅 Good morning                                         │
│                                                         │
│  I've prepared your daily briefing                      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │     ▶  5 min briefing ready                     │   │
│  │     Today: 3 meetings, 2 signals, pipeline      │   │
│  │         [Play Video]                            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [Maybe later]                           [Read instead] │
└─────────────────────────────────────────────────────────┘
```

**Props:**
```typescript
interface VideoBriefingCardProps {
  briefingId: string;
  duration: number;        // 2, 5, or 10 minutes
  topics: string[];        // Top 3 topics preview
  onPlay: () => void;      // Navigate to /briefing
  onDismiss: () => void;   // Collapse to conversation
  onReadInstead: () => void; // Show text briefing
}
```

**Behavior:**
- Dark theme (matches ARIA Workspace)
- ARIA's avatar thumbnail with play overlay
- "Maybe later" marks as dismissed (session-only), collapses card
- "Read instead" fetches text briefing and shows inline
- `data-aria-id="video-briefing-card"` for UICommandExecutor

---

### BriefingSummaryCard

**Visual:**
```
┌─────────────────────────────────────────────────────────┐
│  ✓ Morning Briefing Complete                      8:32a │
├─────────────────────────────────────────────────────────┤
│  What ARIA covered:                                    │
│  • Q4 pipeline review — 12 opportunities in flight     │
│  • Lonza follow-up recommended by end of week          │
│  • 2 new intelligence signals on competitors           │
│                                                         │
│  Action items:                                          │
│  ○ Schedule Lonza call           [pending]              │
│  ✓ Review Q4 forecast            [done]                 │
│  ○ Check Catalent pricing        [pending]              │
│                                                         │
│  [↻ Replay briefing]                                    │
└─────────────────────────────────────────────────────────┘
```

**Props:**
```typescript
interface BriefingSummaryCardProps {
  briefingId: string;
  completedAt: string;        // ISO timestamp
  keyPoints: string[];        // 3-5 bullets from briefing
  actionItems: ActionItem[];  // Actions extracted from briefing
  onReplay: () => void;       // Navigate back to /briefing
}

interface ActionItem {
  id: string;
  text: string;
  status: 'pending' | 'done';
}
```

**Behavior:**
- Light theme (matches conversation thread)
- Action items are clickable — click sends contextual message to ARIA:
  - "I'll help you schedule a call with Lonza. Based on your briefing, this is about [topic]."
- "Replay briefing" navigates to `/briefing?replay=true`
- Persisted in conversation history

---

### BriefingDeliverySection (Settings)

**Visual:**
```
┌─────────────────────────────────────────────────────────┐
│  Briefing Delivery                                      │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  Receive briefings as video                    [Toggle] │
│                                                         │
│  Preferred briefing time                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │  8:00 AM EST                                      │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  Briefing duration                                      │
│  ○ Quick (2 min)   ● Standard (5 min)   ○ Deep (10 min)│
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**State:**
```typescript
interface BriefingPreferences {
  mode: 'video' | 'text';
  time: string;        // "08:00" format
  duration: 2 | 5 | 10;
}
```

**Behavior:**
- Toggle switches between video/text mode
- Time picker shows common options with timezone from user profile
- Duration selection regenerates next briefing at chosen length
- Changes persist immediately (no save button)
- Inserted as collapsible subsection in AriaPersonaSection

---

## API & Hook Integration

### REST Endpoints

```
GET  /api/briefing/status
Response: {
  ready: boolean,
  viewed: boolean,
  briefing_id: string | null,
  duration: number,
  topics: string[]
}

POST /api/briefing/{id}/view
Marks briefing as viewed, returns summary data
Response: {
  key_points: string[],
  action_items: ActionItem[],
  completed_at: string
}

GET  /api/settings/briefing
Response: BriefingPreferences

PUT  /api/settings/briefing
Body: Partial<BriefingPreferences>
```

### WebSocket Events

```
briefing.ready    → Pushed when morning briefing generates
                   Payload: { briefing_id, duration, topics }

briefing.complete → Pushed when user finishes watching
                   Payload: { key_points, action_items }
```

### useBriefingStatus Hook

```typescript
interface UseBriefingStatusReturn {
  // State from REST
  ready: boolean;
  viewed: boolean;
  briefingId: string | null;
  duration: number;
  topics: string[];

  // Loading state
  isLoading: boolean;

  // Actions
  markViewed: () => Promise<void>;
  dismiss: () => void;  // Session-only, doesn't mark viewed

  // For text fallback
  fetchTextBriefing: () => Promise<string>;
}
```

**Implementation:**
1. On mount, call `GET /api/briefing/status`
2. Subscribe to `briefing.ready` WebSocket event
3. `viewed: true` → never show VideoBriefingCard this session
4. `dismiss()` → hide card in Zustand, doesn't call API
5. `markViewed()` → call `POST /api/briefing/{id}/view`

---

## Implementation Approach

### File Creation Order

1. `useBriefingStatus.ts` — Hook with REST + WebSocket
2. `BriefingDeliverySection.tsx` — Settings subsection
3. `VideoBriefingCard.tsx` — Morning greeting card
4. `BriefingSummaryCard.tsx` — Post-briefing summary
5. Update `ARIAWorkspace.tsx` — Inject VideoBriefingCard on load
6. Update `AriaPersonaSection.tsx` — Add BriefingDelivery subsection
7. Update `routes.tsx` — Ensure `/briefing` route handles replay

### Backend Requirements

- `GET/POST /api/briefing/status` endpoint
- `POST /api/briefing/{id}/view` endpoint
- `GET/PUT /api/settings/briefing` endpoint
- WebSocket `briefing.ready` and `briefing.complete` events

### Testing Checklist

- [ ] VideoBriefingCard renders when `ready: true, viewed: false`
- [ ] Card does NOT render when `viewed: true`
- [ ] "Play" navigates to `/briefing` route
- [ ] "Read instead" fetches and displays text briefing
- [ ] "Maybe later" dismisses card for session
- [ ] BriefingSummaryCard appears after briefing ends
- [ ] Action item click sends contextual message to ARIA
- [ ] Settings toggle persists video/text preference
- [ ] Time picker shows user's timezone
- [ ] Duration selection persists (2/5/10 min)
- [ ] WebSocket `briefing.ready` updates hook state in real-time

### Error Handling

- API failures → fall back gracefully, show text briefing
- Missing briefing data → show generic "Briefing ready" without topics
- WebSocket disconnect → REST polling fallback (every 5 min)

---

## Future Enhancements (v2+)

- Embedded data cards in summary (BattleCards, contact cards)
- Briefing scheduling (choose specific days)
- Briefing history browser
- Custom briefing topics selection
- Multiple briefings per day
