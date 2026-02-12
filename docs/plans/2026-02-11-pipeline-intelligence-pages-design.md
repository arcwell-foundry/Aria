# Pipeline & Intelligence Pages Design

**Date:** 2026-02-11
**Status:** Approved
**Type:** Frontend Design Document

---

## Overview

This document defines the design for Layer 2 content pages: PipelinePage, LeadDetailPage, IntelligencePage, and BattleCardDetail. These pages display ARIA-curated data with the persistent Intel Panel on the right.

**Core Principle:** No CRUD. No "Add New" buttons. All content is produced by ARIA's agents. Empty states drive users back to conversation with ARIA.

---

## Data Architecture

### API Hooks Pattern

All pages use React Query hooks that call real backend endpoints. No mock data.

```typescript
// hooks/useLeads.ts
export function useLeads(filters?: LeadFilters) {
  return useQuery({
    queryKey: ['leads', filters],
    queryFn: () => leadsApi.getLeads(filters),
  });
}
```

### Required Backend Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /api/v1/leads` | `Lead[]` |
| `GET /api/v1/leads/:id` | `LeadDetail` |
| `GET /api/v1/intelligence/battle-cards` | `BattleCard[]` |
| `GET /api/v1/intelligence/battle-cards/:id` | `BattleCardDetail` |
| `GET /api/v1/intelligence/signals` | `Signal[]` |
| `GET /api/v1/alerts` | `Alert[]` |

### Empty State Pattern

When API returns empty array, show ARIA-personality empty state with suggestion chip:

```tsx
if (leads.length === 0) {
  return (
    <EmptyState
      title="ARIA hasn't discovered any leads yet."
      description="Approve a pipeline monitoring goal to start tracking your accounts automatically."
      suggestion="Set up pipeline monitoring"
      onSuggestion={() => sendToARIA("Set up pipeline monitoring for my accounts")}
    />
  );
}
```

---

## Icon System

**Use Lucide icons everywhere. No emoji characters.**

### Icon Mapping

| Context | Lucide Icon |
|---------|-------------|
| Strength | `<Zap />` |
| Positioning | `<Target />` |
| Quick Win | `<Clock />` |
| Defense | `<Shield />` |
| Strategic Advice | `<Lightbulb />` |
| Buying Signals | `<TrendingUp />` |
| Active Objections | `<AlertTriangle />` |
| Suggested Next Steps | `<ListChecks />` |
| Health Drop | `<AlertCircle />` |
| Lead Silent | `<UserX />` |
| Live Signals | `<Radio />` |
| News Alerts | `<Newspaper />` |
| Copy | `<Copy />` |
| Copied | `<CheckCheck />` |
| ARIA Advantage | `<CheckCircle2 />` |
| Competitor Advantage | `<XCircle />` |
| ARIA Leads | `<CircleCheck />` |
| Competitor Leads | `<AlertCircle />` |

---

## Page: PipelinePage

**Route:** `/pipeline`
**Theme:** Light

### Header

```
Lead Memory // Pipeline Overview
● Command Mode: Active monitoring of high-velocity leads.
```

- Title: `font-display` (Instrument Serif italic)
- Status dot: green = active monitoring
- Subtitle: `text-[var(--text-secondary)]`

### Controls Bar

- Search input with icon (filters company names)
- Filter chips: Status (dropdown), Health 0-100 (range slider), Owner (dropdown)
- Results count: "Showing 1-5 of 24 leads"

### Lead Table

| Column | Sortable | Default Sort |
|--------|----------|--------------|
| Company | Yes | - |
| Health Score | Yes | **Ascending** (worst first) |
| Last Activity | Yes | - |
| Expected Value | Yes | - |
| Stakeholders | No | - |

**Health Score Bar:**
- Green: >70%
- Orange/Amber: 40-70%
- Red: <40%

**Last Activity:**
- Relative time (e.g., "2 days ago")
- Warning indicator `<AlertCircle className="text-amber-500" />` if >14 days

**Stakeholders:**
- Avatar stack (max 3 visible)
- +N badge if more

**Row Interaction:**
- Click → navigate to `/pipeline/leads/:id`
- `data-aria-id="lead-{id}"` on each row

### Pagination

- "Showing 1-5 of 24 leads"
- 5 leads per page default
- Prev/next arrows

### Empty State

```
ARIA hasn't discovered any leads yet.
Approve a pipeline monitoring goal to start tracking your accounts automatically.
[Set up pipeline monitoring]
```

---

## Page: LeadDetailPage

**Route:** `/pipeline/leads/:leadId`
**Theme:** Light

### Header Section

```
Moderna                              ✓ Verified
┌─────────────────────────────────────────────────┐
│ Opportunity Stage: Discovery   Lead ID: LEA-0042│
└─────────────────────────────────────────────────┘
Health Score: ████████░░ 78%    Synced to Salesforce ↻
```

- Company name: `font-display` large
- Verified badge (if domain validated)
- Status tag: colored pill (Discovery/Evaluation/Negotiation/Closed)
- Health bar with color coding
- Salesforce sync indicator

### Layout: Two-Column + Intel Panel

| Left (280px) | Center (flex) | Right (320px) |
|--------------|---------------|---------------|
| Stakeholders | Timeline | ARIA Intelligence |

### Stakeholder Cards (Left)

```
┌─ STAKEHOLDERS (4) ─────────────────┐
│ <User /> Dr. Sarah Chen            │
│    VP of Manufacturing             │
│    Champion • Positive             │
├─────────────────────────────────────┤
│ <User /> Michael Torres            │
│    Director of Operations          │
│    Decision Maker • Neutral        │
└─────────────────────────────────────┘
```

- Name, title, role tag, sentiment
- `data-aria-id="stakeholder-{id}"`

### Relationship Timeline (Center)

Chronological event cards, newest first:

```
┌─ RELATIONSHIP TIMELINE ────────────────────┐
│ ● Feb 8, 2026                              │
│   Meeting: Demo of fill-finish line        │
│   Attended: S. Chen, M. Torres             │
│                                            │
│ ○ Jan 24, 2026                             │
│   Email: Follow-up on pricing              │
│   Sent by ARIA                             │
│                                            │
│ ○ Jan 10, 2026                             │
│   Signal: Downloaded capabilities PDF      │
│   Intent score: +8                         │
└────────────────────────────────────────────┘
```

### LeadDetail Intel Panel

See [Intel Panel: Lead Detail](#intel-panel-lead-detail)

---

## Page: IntelligencePage

**Route:** `/intelligence`
**Theme:** Light

### Header

```
Competitive Intelligence
ARIA monitors competitor movements, news, and market signals.
```

### Section 1: Battle Cards Grid

```
┌─ BATTLE CARDS ──────────────────────────────────────┐
│                                                     │
│ ┌─────────────────┐ ┌─────────────────┐            │
│ │ Lonza           │ │ Catalent        │            │
│ │ Gap: -$890M     │ │ Gap: -$1.2B     │            │
│ │ Win: 62%        │ │ Win: 48%        │            │
│ │ Last: 2d ago    │ │ Last: 5d ago    │            │
│ └─────────────────┘ └─────────────────┘            │
└─────────────────────────────────────────────────────┘
```

**Card Details:**
- Competitor name
- Market cap gap (red if negative, green if positive)
- Win rate against this competitor
- Last signal timestamp

**Grid Layout:**
- 2 columns on tablet
- 3-4 columns on desktop

**Interaction:**
- Click → `/intelligence/battle-cards/:competitorId`

**Empty State:**
```
ARIA hasn't researched any competitors yet.
Ask ARIA to analyze a competitor to generate a battle card.
[Research a competitor]
```

### Section 2: Market Signals Feed

```
┌─ MARKET SIGNALS ────────────────────────────────────┐
│ <Newspaper /> 2h ago • Lonza                        │
│ "Lonza announces $500M expansion of Swiss facility" │
│ Category: Capacity • Sentiment: Neutral             │
│                                                     │
│ <Newspaper /> 1d ago • Catalent                     │
│ "Catalent Q4 earnings show 12% revenue decline"     │
│ Category: Financial • Sentiment: Negative           │
│                                                     │
│ [View All Signals →]                                │
└─────────────────────────────────────────────────────┘
```

- Chronological feed, newest first
- Each signal: timestamp, competitor, headline, category, sentiment

---

## Page: BattleCardDetail

**Route:** `/intelligence/battle-cards/:competitorId`
**Theme:** Light

### Header

```
Battle Cards: Competitor Analysis
[▼ Lonza ●]  ← Competitor selector dropdown
```

**Competitor Dropdown Win Rate Dots:**
- Green: >60% (winning)
- Amber: 40-60% (competitive)
- Red: <40% (challenging)

### Top Metrics Bar

| Metric | Description |
|--------|-------------|
| Market Cap Gap | Negative = competitor smaller (good), positive = larger |
| Win Rate | ARIA's win rate against this competitor |
| Pricing Delta | How their pricing compares (+ = higher, - = lower) |
| Last Signal | Time since last intelligence signal |

- Red/green indicators for delta changes

### Section 1: How to Win

```
┌─ HOW TO WIN ───────────────────────────────────────────────────┐
│ Last updated by Strategist, 1d ago                              │
│                                                                 │
│ ┌────────────────────┐ ┌────────────────────┐                  │
│ │ <Zap /> Strength   │ │ <Target /> Positioning │               │
│ │ "Lead with our     │ │ "When they mention │                  │
│ │ fill-finish speed  │ │ scale, emphasize   │                  │
│ │ — 40% faster than  │ │ flexibility and    │                  │
│ │ Lonza's Swiss ops" │ │ responsiveness"    │                  │
│ └────────────────────┘ └────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

Four strategy cards: Strength, Positioning, Quick Win, Defense

### Section 2: Feature Gap Analysis

```
┌─ FEATURE GAP ANALYSIS ─────────────────────────────────────────┐
│ Last updated by Analyst, 6h ago                                 │
│                                                                 │
│ Sterile Manufacturing                                          │
│ ARIA    ████████████████████░░  92%  <AlertCircle />           │
│ Lonza   ██████████████████████  100%                           │
│                                                                 │
│ Fill-Finish Speed                                              │
│ ARIA    ██████████████████████  100%  <CircleCheck />          │
│ Lonza   ████████████████░░░░░░  75%                            │
└─────────────────────────────────────────────────────────────────┘
```

**Styling:**
- ARIA bars: `#2E66FF` (electric blue)
- Competitor bars: `#64748B` (neutral gray)
- `<CircleCheck className="text-green-500" />` when ARIA leads
- `<AlertCircle className="text-amber-500" />` when competitor leads
- Hover tooltip: delta text (e.g., "+15% faster")

### Section 3: Critical Gaps

```
┌─ CRITICAL GAPS ─────────────────────────────────────────────────┐
│ Last updated by Scout, 3h ago                                   │
│                                                                 │
│ ARIA ADVANTAGES                                                 │
│ <CheckCircle2 className="text-green-500" /> Faster fill-finish  │
│ <CheckCircle2 className="text-green-500" /> Flexible batches    │
│ <CheckCircle2 className="text-green-500" /> Dedicated PMs       │
│                                                                 │
│ COMPETITOR ADVANTAGES                                           │
│ <XCircle className="text-amber-500" /> Larger cold chain        │
│ <XCircle className="text-amber-500" /> Longer FDA track record  │
└─────────────────────────────────────────────────────────────────┘
```

- Advantages grouped first
- Gaps grouped after
- `data-aria-id="critical-gap-{index}"`

### Section 4: Objection Handling Scripts

```
┌─ OBJECTION HANDLING ────────────────────────────────────────────┐
│ Last updated by Strategist, 1d ago                               │
│                                                                  │
│ ▼ "Lonza has more FDA approvals"                    [Copy]      │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │ "That's true for legacy products, but our fill-finish    │  │
│   │ facility achieved FDA clearance in 18 months — 40%       │  │
│   │ faster than industry average. For new molecular entities,│  │
│   │ our speed to clinic is unmatched. Would you like to see  │  │
│   │ our regulatory timeline comparison?"                     │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ▶ "Their pricing is 20% lower"                                  │
│                                                                  │
│ ▶ "They have Swiss manufacturing quality"                       │
└──────────────────────────────────────────────────────────────────┘
```

**Copy Button Pattern:**
- Default: `<Copy />` icon button
- On click: copy to clipboard
- Show `<CheckCheck />` with "Copied" for 2 seconds
- Revert to `<Copy />`

**This is a core workflow — reps copy these scripts before calls.**

---

## Intel Panel Configurations

### Intel Panel: Pipeline Overview

**Route:** `/pipeline`

```
┌─ PROACTIVE ALERTS ─────────────────────────┐
│                                            │
│ <AlertCircle /> Health Drop                │
│ Lonza dropped from 78% to 52% in 3 days    │
│ [Investigate]                              │
│                                            │
│ <UserX /> Lead Silent                      │
│ Catalent hasn't been contacted in 21 days  │
│ [Suggest outreach]                         │
│                                            │
│ <TrendingUp /> Buying Signal               │
│ WuXi Biologics: +15 intent score           │
│ "evaluating CDMO partners" detected        │
│                                            │
│ <Calendar /> Upcoming Renewal              │
│ Samsung Biologics: $2.1M renewal in 45 days│
│                                            │
│ [View All Alerts →]                        │
└────────────────────────────────────────────┘
```

**Alert Types:**
- `health_drop` — significant health score decline
- `lead_silent` — no activity >14 days
- `buying_signal` — intent data trigger
- `upcoming_renewal` — contract renewal approaching

### Intel Panel: Lead Detail

**Route:** `/pipeline/leads/:leadId`

```
┌─ ARIA INTELLIGENCE ────────────────────────┐
│ Last updated by Analyst, 2h ago            │
│                                            │
│ <Lightbulb /> STRATEGIC ADVICE             │
│ "Moderna's expansion into mRNA             │
│  manufacturing creates urgency..."         │
│                                            │
│ <TrendingUp /> BUYING SIGNALS              │
│ • +12 intent: "sterile manufacturing"      │
│ • +8 intent: "CDMO comparison"             │
│                                            │
│ <AlertTriangle /> ACTIVE OBJECTIONS        │
│ 1. Price sensitivity                       │
│ 2. Timeline concerns                       │
│                                            │
│ <ListChecks /> SUGGESTED NEXT STEPS        │
│ 1. Schedule exec meeting with CFO          │
│ 2. Send ROI case study                     │
└────────────────────────────────────────────┘
```

### Intel Panel: Intelligence

**Route:** `/intelligence`

```
┌─ ARIA INTEL ───────────────────────────────┐
│ Last updated by Scout, 30m ago             │
│                                            │
│ <Radio /> LIVE SIGNALS                     │
│ • Lonza: Expansion announcement            │
│ • Catalent: Stock down 4%                  │
│                                            │
│ <Newspaper /> NEWS ALERTS                  │
│ • FDA approves new sterility guideline     │
│ • Industry consolidation trend             │
│                                            │
│ [Generate Comparison Deck]                 │
│                                            │
│ <MessageSquare /> Ask for competitive intel│
│ ┌─────────────────────────────────────┐    │
│ │                                     │    │
│ └─────────────────────────────────────┘    │
└────────────────────────────────────────────┘
```

### Intel Panel: Battle Card Detail

**Route:** `/intelligence/battle-cards/:competitorId`

```
┌─ ARIA INTEL ───────────────────────────────┐
│ Last updated by Scout, 30m ago             │
│                                            │
│ <Radio /> LIVE SIGNALS                     │
│ • Lonza: Expansion announcement detected   │
│ • New FDA guidance affects their facility  │
│                                            │
│ <Newspaper /> NEWS ALERTS                  │
│ • Swiss facility inspection passed         │
│ • Q1 earnings call scheduled Feb 15        │
│                                            │
│ [Generate Comparison Deck]                 │
│                                            │
│ <MessageSquare /> Ask about Lonza...       │
│ ┌─────────────────────────────────────┐    │
│ │                                     │    │
│ └─────────────────────────────────────┘    │
└────────────────────────────────────────────┘
```

---

## Section Update Timestamps

Every section with agent-generated content includes:

```tsx
<span className="font-mono text-xs text-[var(--text-muted)]">
  Updated by {agent}, {timeAgo}
</span>
```

- Font: JetBrains Mono
- Position: Top-right of section header
- Format: "Updated by Scout, 3h ago"

---

## data-aria-id Attributes

All key elements need `data-aria-id` for UICommandExecutor targeting:

| Element | Pattern |
|---------|---------|
| Lead row | `lead-{id}` |
| Stakeholder card | `stakeholder-{id}` |
| Timeline event | `timeline-{id}` |
| Battle card preview | `battle-card-{id}` |
| Critical gap | `critical-gap-{index}` |
| Objection script | `objection-{index}` |
| Intel panel | `intel-panel` |
| Feature gap | `feature-gap-{featureKey}` |

---

## File Structure

```
frontend/src/
├── components/pages/
│   ├── PipelinePage.tsx
│   ├── LeadDetailPage.tsx
│   ├── IntelligencePage.tsx
│   └── BattleCardDetail.tsx
│
├── components/intel/
│   ├── AlertsModule.tsx
│   ├── StrategicAdviceModule.tsx
│   ├── BuyingSignalsModule.tsx
│   ├── ObjectionsModule.tsx
│   ├── NextStepsModule.tsx
│   ├── LiveSignalsModule.tsx
│   ├── NewsAlertsModule.tsx
│   └── ChatInputModule.tsx
│
├── components/pipeline/
│   ├── LeadTable.tsx
│   ├── LeadRow.tsx
│   ├── HealthBar.tsx
│   └── StakeholderCard.tsx
│
├── components/intelligence/
│   ├── BattleCardGrid.tsx
│   ├── BattleCardPreview.tsx
│   ├── FeatureGapChart.tsx
│   ├── CriticalGapsList.tsx
│   ├── ObjectionAccordion.tsx
│   └── MarketSignalsFeed.tsx
│
├── components/common/
│   ├── EmptyState.tsx
│   ├── SortableHeader.tsx
│   └── CopyButton.tsx
│
├── hooks/
│   ├── useLeads.ts
│   ├── useLeadDetail.ts
│   ├── useBattleCards.ts
│   ├── useBattleCardDetail.ts
│   ├── useMarketSignals.ts
│   └── useAlerts.ts
│
├── api/
│   ├── leads.ts
│   └── intelligence.ts
│
└── types/
    ├── leads.ts
    └── intelligence.ts
```

---

## Route Updates

Add to `frontend/src/app/routes.tsx`:

```tsx
// Layer 2: Content Pages
{ path: 'pipeline', element: <PipelinePage /> },
{ path: 'pipeline/leads/:leadId', element: <LeadDetailPage /> },
{ path: 'intelligence', element: <IntelligencePage /> },
{ path: 'intelligence/battle-cards/:competitorId', element: <BattleCardDetail /> },
```

---

## Color Tokens

| Token | Value | Usage |
|-------|-------|-------|
| Electric Blue | `#2E66FF` | ARIA bars, primary accent |
| Neutral Gray | `#64748B` | Competitor bars |
| Green | `text-green-500` | Positive indicators, ARIA advantages |
| Amber | `text-amber-500` | Warnings, competitor advantages |
| Red | `text-red-500` | Critical issues, low win rate |

---

## Next Steps

1. Create TypeScript types for `leads.ts` and `intelligence.ts`
2. Create API client functions
3. Create React Query hooks
4. Build shared components (EmptyState, CopyButton, SortableHeader)
5. Build pipeline components (LeadTable, HealthBar, StakeholderCard)
6. Build intelligence components (BattleCardGrid, FeatureGapChart, ObjectionAccordion)
7. Build Intel Panel modules
8. Assemble page components
9. Update routes and Intel Panel context
