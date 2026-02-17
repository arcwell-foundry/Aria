# Video Content Overlay Design

**Date:** 2026-02-17
**Status:** Approved

## Overview

When ARIA executes tools during video calls that produce visual results (lead cards, charts, battle cards), display them alongside the Tavus avatar. Uses a hybrid approach: full cards in the TranscriptPanel + floating toast indicators on the video pane.

## Architecture

### Hybrid Display Model

1. **Full card in TranscriptPanel** — New rich content card types (LeadCard, BattleCard, PipelineChart, etc.) render inline in the transcript via the existing `RichContentRenderer`.

2. **Floating toast/chip on video pane** — Small pill (icon + title) slides in from the bottom-right of `AvatarContainer`, stays ~8 seconds, fades out. Clicking scrolls the transcript to the corresponding card. Multiple toasts stack vertically.

### Content Delivery

WebSocket only. No new endpoints, no polling.

The `VideoToolExecutor` produces structured `rich_content` alongside spoken text. The webhook handler emits an `aria.message` WebSocket event with the `rich_content[]` payload. The frontend receives it through the existing WebSocket flow.

## Frontend Components

### New: `VideoContentToast.tsx`

Location: `frontend/src/components/video/VideoContentToast.tsx`

A single toast pill rendered on the video pane.

Props:
- `id: string` — unique content item ID
- `icon: string` — content type icon
- `title: string` — short label (e.g., "Battle Card: Lonza vs Catalent")
- `onDismiss: (id: string) => void`
- `onClick: (id: string) => void` — scrolls transcript to card

Styling:
- Semi-transparent dark background (`bg-[#0F1117]/80 backdrop-blur-sm`)
- Rounded pill shape, small text (Satoshi 500)
- Slide-in from right (200ms ease-out), fade-out on dismiss (300ms)
- Dismiss button (x) on the right

### New: `VideoToastStack.tsx`

Location: `frontend/src/components/video/VideoToastStack.tsx`

Container managing multiple toasts with stacking and animation.

Props:
- `toasts: Toast[]` — active toast items
- `onDismiss: (id: string) => void`
- `onToastClick: (id: string) => void`

Behavior:
- Positioned absolute, bottom-right of AvatarContainer
- Max 3 visible; oldest dismissed when 4th arrives
- Auto-dismiss after 8 seconds per toast
- Vertical stack with 8px gap

Layout within DialogueMode:
```
+-------------------------------------+
|                                     |
|         ARIA Avatar Video           |
|                                     |
|                                     |
|                   +----------------+|
|                   | Lead Card:     ||
|                   |   Lonza        ||
|                   +----------------+|
|                   | Battle Card:   ||
|                   |   Lonza v Cat  ||
|                   +----------------+|
+-------------------------------------+
```

### New: 5 Rich Content Card Components

Location: `frontend/src/components/rich/`

All cards follow existing patterns: dark background (`bg-[#1A1D27]`), rounded-lg, left accent border, padding, `data-aria-id` attribute.

#### 1. `LeadCard.tsx` (`content_type: "lead_card"`)

Triggered by: `search_companies`, `search_leads`, `get_lead_details`

Displays:
- Company name (heading)
- Key contacts: name + title (2-3 items)
- Fit score: progress bar with percentage
- Recent signals: bulleted list (2-3 items)

Action: "Add to Pipeline" button → calls `addLeadToPipeline()` API

#### 2. `BattleCard.tsx` (`content_type: "battle_card"`)

Triggered by: `get_battle_card`

Displays:
- Title: "[Company A] vs [Company B]"
- 2-column comparison table
- Rows: pricing, capabilities, strengths, weaknesses, recent wins
- Monospace data cells (JetBrains Mono)

No action buttons (informational only).

#### 3. `PipelineChart.tsx` (`content_type: "pipeline_chart"`)

Triggered by: `get_pipeline_summary`

Displays:
- Horizontal funnel bars: Prospect → Qualified → Proposal → Negotiation → Won
- Bars sized proportionally, count labels on each
- Pure CSS bars (no charting library)

No action buttons.

#### 4. `ResearchResultsCard.tsx` (`content_type: "research_results"`)

Triggered by: `search_pubmed`, `search_clinical_trials`

Displays:
- List of results (max 3 shown): title, authors/sponsor, date, brief excerpt
- "X more results" indicator if truncated
- Source links (PubMed URL, ClinicalTrials.gov link)

Action: "Save to Intelligence" button → calls existing API

#### 5. `EmailDraftCard.tsx` (`content_type: "email_draft"`)

Triggered by: `draft_email`

Displays:
- To, Subject fields
- Body preview (first 3-4 lines), expandable to full body
- Plain text rendering with line breaks preserved

Actions:
- "Send" → calls send email API
- "Edit" → navigates to Communications page with draft loaded

### Modified: `RichContentRenderer.tsx`

Add new type mappings:
```typescript
case "lead_card": return <LeadCard data={content.data} />
case "battle_card": return <BattleCard data={content.data} />
case "pipeline_chart": return <PipelineChart data={content.data} />
case "research_results": return <ResearchResultsCard data={content.data} />
case "email_draft": return <EmailDraftCard data={content.data} />
```

### Modified: `DialogueMode.tsx`

Changes:
- Import `VideoToastStack`
- Add local state: `toasts: Toast[]`
- On incoming `aria.message` with `rich_content[]`, for each item:
  - Let existing flow render the card in transcript (no change)
  - Push a toast to local state: `{ id, icon, title }` derived from content type and data
- Render `VideoToastStack` as absolute-positioned overlay on the avatar container div
- `onToastClick` scrolls the transcript panel to the card (via ref or scrollIntoView)

## Backend Changes

### Modified: `tavus_tool_executor.py`

Change return type from `str` to structured result:

```python
@dataclass
class ToolResult:
    spoken_text: str           # What ARIA says aloud
    rich_content: dict | None  # Structured card data, or None
```

Each `_handle_*` method returns `ToolResult`. The `rich_content` dict follows the format:
```python
{
    "type": "battle_card",  # matches RichContentRenderer type
    "data": {
        "company_a": "Lonza",
        "company_b": "Catalent",
        "rows": [...]
    }
}
```

Tool-to-content-type mapping:
| Tool | Content Type |
|------|-------------|
| `search_companies`, `search_leads`, `get_lead_details` | `lead_card` |
| `get_battle_card` | `battle_card` |
| `get_pipeline_summary` | `pipeline_chart` |
| `search_pubmed`, `search_clinical_trials` | `research_results` |
| `draft_email` | `email_draft` |
| `schedule_meeting`, `get_meeting_brief`, `get_market_signals`, `add_lead_to_pipeline` | None (spoken only) |

### Modified: `webhooks.py` (_handle_tool_call)

After executing the tool via `VideoToolExecutor`:
1. Return `tool_result.spoken_text` to Tavus (existing echo flow)
2. If `tool_result.rich_content` is not None, emit WebSocket event:
   ```python
   await ws_manager.send_event(
       user_id=user_id,
       event="aria.message",
       data={
           "message": "",  # spoken text handled by avatar
           "rich_content": [tool_result.rich_content],
           "ui_commands": [],
           "suggestions": []
       }
   )
   ```

## Data Flow

```
Tavus CVI tool_call webhook
  → POST /webhooks/tavus (webhooks.py)
  → _handle_tool_call()
  → VideoToolExecutor.execute() returns ToolResult(spoken_text, rich_content)
  → spoken_text → echoed back to Tavus conversation (avatar speaks)
  → rich_content → WebSocket aria.message event
  → Frontend DialogueMode receives event
    → TranscriptPanel renders full card via RichContentRenderer
    → VideoToastStack shows floating pill on avatar pane
    → User clicks pill → transcript scrolls to card
    → User clicks action button on card → API call
```

## Files Changed

**New files:**
- `frontend/src/components/video/VideoContentToast.tsx`
- `frontend/src/components/video/VideoToastStack.tsx`
- `frontend/src/components/rich/LeadCard.tsx`
- `frontend/src/components/rich/BattleCard.tsx`
- `frontend/src/components/rich/PipelineChart.tsx`
- `frontend/src/components/rich/ResearchResultsCard.tsx`
- `frontend/src/components/rich/EmailDraftCard.tsx`

**Modified files:**
- `frontend/src/components/rich/RichContentRenderer.tsx` — new card type mappings
- `frontend/src/components/rich/index.ts` — exports
- `frontend/src/components/avatar/DialogueMode.tsx` — toast state + overlay
- `frontend/src/components/video/index.ts` — exports
- `backend/src/integrations/tavus_tool_executor.py` — ToolResult return type + rich_content generation
- `backend/src/api/routes/webhooks.py` — WebSocket emission after tool execution

## Not Included

- No new REST endpoints
- No Redis cache for content items
- No polling mechanism
- No Raven-1 screen share changes (already enabled by default)
- No new database tables
