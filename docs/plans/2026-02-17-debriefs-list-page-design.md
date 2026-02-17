# Debriefs List Page Design

**Date:** 2026-02-17
**Status:** Approved
**Route:** `/dashboard/debriefs`

## Overview

A browsable list of all meeting debriefs with pending debriefs prominently highlighted. Follows ARIA's core principle: ARIA surfaces what needs attention, user decides what to do.

## Page Structure

### Layout
- **Header**: "Debriefs" title with count subtitle
- **Pending banner**: Collapsible yellow section (when pending meetings exist)
- **Filter bar**: Date range picker + search input
- **Debriefs grid**: 2-column responsive grid of DebriefCards

### Pending Debriefs Banner

```
┌─────────────────────────────────────────────────────────┐
│ ⚠️ 3 meetings without debriefs                    [✕]  │
│                                                         │
│ • Moderna Discovery Call – Today at 2pm [Start debrief] │
│ • Lonza Pricing Discussion – Yesterday [Start debrief]  │
│ • Catalent Follow-up – Feb 14 [Start debrief]           │
└─────────────────────────────────────────────────────────┘
```

- Yellow/amber tinted background
- Dismiss button stores in localStorage (expires daily)
- "Start debrief" sends WebSocket `debrief:start` event
- ARIA initiates conversation with full meeting context

### Filtering

Minimal v1 approach:
- Date range picker (left side)
- Search input for meeting title/lead name (right side)

## DebriefCard Component

### Compact View
```
┌─────────────────────────────────────────────────────┐
│ Moderna Discovery Call              [Won]   Feb 14  │
│ with Sarah Chen                                     │
│                                                     │
│ 3 action items  │  2 insights                       │
└─────────────────────────────────────────────────────┘
```

### Expanded View (inline expansion)
```
┌─────────────────────────────────────────────────────┐
│ Moderna Discovery Call              [Won]   Feb 14  │
│ with Sarah Chen                              [collapse]│
├─────────────────────────────────────────────────────┤
│ Summary                                             │
│ "Strong interest in our cell therapy services.      │
│  Sarah wants a formal proposal by end of week."     │
│                                                     │
│ Our Commitments (2)                                 │
│ • Send pricing proposal by Feb 18                   │
│ • Schedule follow-up demo for team                  │
│                                                     │
│ Their Commitments (1)                               │
│ • Review internally and respond by Feb 21           │
│                                                     │
│ Insights (2)                                        │
│ • Decision maker: Sarah Chen (VP of R&D)            │
│ • Budget concern: Needs < $500K to avoid CFO signoff│
└─────────────────────────────────────────────────────┘
```

### Outcome Badges (typographic, no emojis)

| Status | Style |
|--------|-------|
| Won | slate-700 text on emerald-900/20 background |
| Lost | slate-700 text on red-900/20 background |
| Pending | slate-700 text on amber-900/20 background |
| No Decision | slate-500 text on slate-800/20 background |

## Start Debrief Flow

1. User clicks "Start debrief" on pending meeting
2. Frontend sends WebSocket event: `debrief:start` with `{ meeting_id }`
3. Backend triggers ARIA to open conversation with meeting context
4. ARIA initiates: "Let's debrief your Moderna meeting. I see it was a 30-minute call with Sarah Chen. How did it go?"
5. User responds naturally, ARIA extracts structured data

## API Integration

### Backend Endpoints (existing)
- `GET /debriefs` — paginated list with filters
- `GET /debriefs/pending` — meetings needing debriefs

### Frontend Additions

**API client** (`api/debriefs.ts`):
```typescript
listDebriefs(page, pageSize, startDate?, endDate?, search?)
getPendingDebriefs()
```

**Hooks** (`hooks/useDebriefs.ts`):
```typescript
useDebriefs(filters?)
usePendingDebriefs()
```

## Navigation

### Sidebar Addition
- Label: "Debriefs"
- Icon: FileText (lucide-react)
- Route: `/dashboard/debriefs`
- Position: After "Communications"

### Route
```typescript
<Route path="debriefs" element={<DebriefsListPage />} />
```

## Theming

- Page background: Light theme (`#F8FAFC`)
- Cards: Secondary background with subtle border
- Pending banner: Amber tint (`#FEF3C7` equivalent)
- No emojis anywhere on this page

## Files

### Create
- `frontend/src/components/pages/DebriefsListPage.tsx`
- `frontend/src/components/rich/DebriefCard.tsx`
- `frontend/src/components/debriefs/PendingDebriefBanner.tsx`
- `frontend/src/hooks/useDebriefs.ts`

### Update
- `frontend/src/api/debriefs.ts`
- `frontend/src/components/shell/Sidebar.tsx`
- `frontend/src/stores/navigationStore.ts`
- `frontend/src/app/routes.tsx`
- `frontend/src/components/pages/index.ts`
