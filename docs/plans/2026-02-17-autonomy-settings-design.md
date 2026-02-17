# Autonomy Settings & Trust Level Integration

**Date:** 2026-02-17
**Status:** Approved

## Overview

Wire ARIA's existing autonomy calibration backend into a visible, interactive frontend experience. Users see their trust level, can adjust it (downward only), see action history, and encounter approve/reject flows inline in conversation.

## Architecture

### 3-Tier Frontend Model (maps to backend 1-5)

| Frontend Tier | Backend Level | What ARIA Does |
|---|---|---|
| Guided | 1 | Asks before everything |
| Assisted | 3 | Auto-executes low-risk, asks for medium+ |
| Autonomous | 4 | Auto-executes low+medium, asks for high+ |

Level 5 (Full Trust) stays as "Coming Q3 2026" per existing pattern.

**Lower-only constraint:** User can only select tiers at or below ARIA's recommended level (from `calculate_autonomy_level()`).

## Components

### 1. Backend: `autonomy.py` route (NEW)

**`GET /autonomy/status`** returns:
```json
{
  "current_level": 1,
  "current_tier": "guided",
  "recommended_level": 3,
  "recommended_tier": "assisted",
  "can_select_tiers": ["guided", "assisted"],
  "stats": {
    "total_actions": 47,
    "approval_rate": 0.89,
    "auto_executed": 12,
    "rejected": 5
  },
  "recent_actions": [
    {
      "id": "...",
      "title": "Research Lonza pipeline",
      "action_type": "research",
      "risk_level": "low",
      "status": "completed",
      "created_at": "..."
    }
  ]
}
```

**`POST /autonomy/level`** accepts `{ "tier": "assisted" }`, validates against recommended, writes to `user_settings.preferences.autonomy_level`.

### 2. Backend: Fix `ActionQueueService.submit_action()`

Current behavior hardcodes LOW-only auto-approve. Change to fully defer to `AutonomyCalibrationService.should_auto_execute()` so it respects the user's actual stored autonomy level.

### 3. Frontend: `AutonomySettings.tsx` (REPLACES `AutonomySection.tsx`)

- Horizontal 3-step visual indicator with active tier highlighted
- Selectable tier cards with name + description + what auto-executes
- Disabled tiers above recommended (lower-only constraint)
- Stats: total actions, approval rate
- Last 10 actions table with outcome badges
- "Coming Q3 2026" indicator for Full Trust (Level 5)

### 4. Frontend: `ActionApprovalCard.tsx` (NEW)

- Inline conversation card rendered when `action.pending` WebSocket event arrives
- Shows: action title, agent, risk level badge, ARIA reasoning
- Approve / Reject buttons (sends WebSocket events)
- Updates in-place on resolution

### 5. Frontend: `autonomyStore.ts` (NEW Zustand store)

```typescript
interface AutonomyState {
  currentTier: 'guided' | 'assisted' | 'autonomous' | null
  recommendedTier: string | null
  stats: { totalActions: number; approvalRate: number } | null
  recentActions: Action[]
  loading: boolean
  fetchStatus: () => Promise<void>
  setTier: (tier: string) => Promise<void>
}
```

Fetched on app init. Refreshed on tier change and action completion.

### 6. Frontend: Trust Badge in Sidebar

- Below ARIA logo/status area
- Shield icon + "Trust: Guided" with colored dot
- Click navigates to `/settings/autonomy`
- Reads from `autonomyStore`

## Files Changed

**New files:**
- `backend/src/api/routes/autonomy.py`
- `frontend/src/stores/autonomyStore.ts`
- `frontend/src/api/autonomy.ts`
- `frontend/src/components/settings/AutonomySettings.tsx`
- `frontend/src/components/rich/ActionApprovalCard.tsx`

**Modified files:**
- `backend/src/api/routes/__init__.py` — register autonomy router
- `backend/src/services/action_queue_service.py` — defer to should_auto_execute()
- `frontend/src/components/pages/SettingsPage.tsx` — swap AutonomySection → AutonomySettings
- `frontend/src/components/shell/Sidebar.tsx` — add trust badge
- `frontend/src/components/conversation/ConversationThread.tsx` — render ActionApprovalCard for pending actions
