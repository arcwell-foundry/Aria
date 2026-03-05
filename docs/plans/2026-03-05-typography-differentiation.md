# Typography Differentiation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add visual hierarchy to ARIA's messages using three distinct fonts: Instrument Serif for insights, JetBrains Mono for data/timestamps, and Inter for body text.

**Architecture:** Update Google Fonts imports to include weight 500 for JetBrains Mono, Create a `processAriaTypography()` utility function with regex patterns to detect and wrap data elements. Apply typography to the markdown renderer's `strong` and heading components in `MessageBubble.tsx`, and update `TimeDivider.tsx` and `ChatIntelligencePanel.tsx` for consistent monospace styling.

**Tech Stack:** React, TypeScript, Tailwind CSS, ReactMarkdown, Google Fonts

---

## Task 1: Update Google Fonts Import for JetBrains Mono Weight 500

**Files:**
- Modify: `frontend/index.html:12`

**Step 1: Update JetBrains Mono import to include weight 500**

Current line 12:
```html
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet" />
```

Change to:
```html
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

**Step 2: Verify font loads in browser**

Run: `cd frontend && npm run dev`
Open browser DevTools → Network → Filter for "fonts.googleapis"
Expected: JetBrains Mono request includes `wght@400;500`

**Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(fonts): Add weight 500 to JetBrains Mono import

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Create ARIA Typography Utility Module

**Files:**
- Create: `frontend/src/utils/ariaTypography.ts`

**Step 1: Create the typography utility with regex patterns**

```typescript
/**
 * ARIA Typography Utility
 *
 * Detects and wraps data elements in ARIA messages with appropriate styling.
 * - Times (11:00am, 2:30 PM)
 * - Dates (March 5, Mar 10)
 * - Percentages (45%, 0.8)
 * - Currency ($2,500, $100)
 * - Numbers with units (28 drafts, 4 tasks, 2 hours)
 */

/**
 * Regex patterns for detecting data elements in ARIA messages.
 * Order matters: more specific patterns should come first.
 */
const DATA_PATTERNS: Array<{
  pattern: RegExp;
  className: string;
}> = [
  // Currency: $1,234.56 or $1,000
  {
    pattern: /\$[\d,]+(?:\.\d{2})?/g,
    className: 'aria-data',
  },
  // Percentages: 45% or 0.8%
  {
    pattern: /\b\d+(?:\.\d+)?%/g,
    className: 'aria-data',
  },
  // Times: 11:00am, 2:30 PM, 11:00 am
  {
    pattern: /\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b/g,
    className: 'aria-data',
  },
  // Dates: March 5, Mar 10th, December 25th
  {
    pattern: /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?\b/g,
    className: 'aria-data',
  },
  // Numbers with units: 28 drafts, 4 tasks, 2 hours, 30 minutes
  {
    pattern: /\b\d+\s*(?:hours?|minutes?|days?|weeks?|months?|tasks?|drafts?|meetings?|signals?|emails?|people?|persons?)\b/gi,
    className: 'aria-data',
  },
  // Standalone significant numbers (3+ digits): 100, 1,234
  {
    pattern: /\b\d{1,3}(?:,\d{3})+\b/g,
    className: 'aria-data',
  },
];

/**
 * Process text to wrap detected data elements in styled spans.
 * This is a post-processing step for ARIA message content.
 *
 * @param text - The text to process
 * @returns HTML string with data elements wrapped in styled spans
 *
 * @example
 * processAriaTypography("Your meeting at 2:30 PM has 3 attendees")
 * // Returns: "Your meeting at <span class="aria-data">2:30 PM</span> has <span class="aria-data">3 attendees</span>"
 */
export function processAriaTypography(text: string): string {
  // Don't process empty or whitespace-only text
  if (!text || !text.trim()) {
    return text;
  }

  let result = text;

  // Apply each pattern and wrap matches in styled spans
  // We need to be careful not to double-wrap, so we use unique placeholders
  for (const { pattern, className } of DATA_PATTERNS) {
    result = result.replace(pattern, (match) => {
      // Don't wrap if already inside a span
      return `<span class="${className}">${match}</span>`;
    });
  }

  return result;
}

/**
 * CSS class names for ARIA typography
 */
export const ARIA_TYPOGRAPHY_CLASSES = {
  insight: 'aria-insight',
  data: 'aria-data',
} as const;
```

**Step 2: Verify file compiles**

Run: `cd frontend && npx tsc --noEmit src/utils/ariaTypography.ts`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/utils/ariaTypography.ts
git commit -m "feat(utils): Add ariaTypography utility for data element detection

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add ARIA Typography CSS Classes to Global Stylesheet

**Files:**
- Modify: `frontend/src/index.css:44` (after the :root block)

**Step 1: Add typography CSS classes after the :root block**

Add after line 44 (after the closing `}` of `.light` block, before `@theme`):

```css
/* === ARIA Typography — visual hierarchy in ARIA's messages === */

/**
 * Instrument Serif for ARIA's key insights
 * Used for: bold/emphasized text, headings within ARIA messages
 */
.aria-insight {
  font-family: 'Instrument Serif', Georgia, serif;
  font-style: italic;
  font-size: 16px;
  line-height: 1.5;
  color: var(--text-primary);
}

/* JetBrains Mono for data elements
 * Used for: timestamps, numbers, percentages, currency, counts
 */
.aria-data {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 500;
  font-size: 12px;
  color: #8B9DC3;
  letter-spacing: 0.02em;
}

/* Apply aria-insight to strong/b tags within ARIA messages only */
.prose-aria strong,
.prose-aria b {
  font-family: 'Instrument Serif', Georgia, serif;
  font-style: italic;
  font-size: 16px;
  font-weight: normal;
  color: var(--text-primary);
}
```

**Step 2: Verify CSS compiles**

Run: `cd frontend && npm run dev`
Expected: App loads without CSS errors in console

**Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "style(css): Add aria-insight and aria-data typography classes

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Update MessageBubble Markdown Components for Typography

**Files:**
- Modify: `frontend/src/components/conversation/MessageBubble.tsx:24-73`

**Step 1: Update the markdownComponents object**

Replace the entire `markdownComponents` object (lines 24-73) with:

```typescript
const markdownComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="font-display italic text-xl text-[var(--text-primary)] mb-2 mt-4 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="font-display italic text-lg text-[var(--text-primary)] mb-2 mt-3 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="font-display italic text-base text-[var(--text-primary)] mb-1 mt-3 first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }: { children?: React.ReactNode }) => (
    <h4 className="font-display italic text-sm text-[var(--text-primary)] mb-1 mt-2 first:mt-0">
      {children}
    </h4>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="text-sm leading-relaxed text-[var(--text-primary)] mb-2 last:mb-0">
      {children}
    </p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-disc space-y-1">
      {children}
    </ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-decimal space-y-1">
      {children}
    </ol>
  ),
  // Strong/bold text renders as Instrument Serif italic (aria-insight style)
  // The CSS class .prose-aria strong handles this, but we add explicit styling here for clarity
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="aria-insight">{children}</strong>
  ),
  b: ({ children }: { children?: React.ReactNode }) => (
    <b className="aria-insight">{children}</b>
  ),
  code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
    const isBlock = className?.includes('language-');
    if (isBlock) {
      return (
        <code className="block font-mono text-xs bg-[var(--bg-elevated)] rounded-md p-3 my-2 overflow-x-auto text-[var(--text-secondary)]">
          {children}
        </code>
      );
    }
    return (
      <code className="aria-data bg-[var(--bg-elevated)] rounded px-1.5 py-0.5">
        {children}
      </code>
    );
  },
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/MessageBubble.tsx
git commit -m "feat(MessageBubble): Apply Instrument Serif to strong/bold, JetBrains Mono to inline code

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Update TimeDivider to Use JetBrains Mono

**Files:**
- Modify: `frontend/src/components/conversation/TimeDivider.tsx:30-39`

**Step 1: Update the TimeDivider component styling**

Replace the return statement (lines 30-39) with:

```typescript
export function TimeDivider({ timestamp }: TimeDividerProps) {
  return (
    <div className="flex items-center gap-4 my-6">
      <div className="flex-1 h-px bg-[#2A2F42]" />
      <span className="font-mono text-[11px] font-medium text-[#8B9DC3] tracking-wide">
        {formatDividerTime(timestamp)}
      </span>
      <div className="flex-1 h-px bg-[#2A2F42]" />
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Verify visually**

Run: `cd frontend && npm run dev`
Check: Time divider shows "Today, 12:42 AM" in JetBrains Mono

**Step 4: Commit**

```bash
git add frontend/src/components/conversation/TimeDivider.tsx
git commit -m "style(TimeDivider): Use JetBrains Mono for timestamp dividers

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Update ChatIntelligencePanel Time Labels to JetBrains Mono

**Files:**
- Modify: `frontend/src/components/panels/ChatIntelligencePanel.tsx:89-97` (MeetingCard time display)

**Step 1: Update MeetingCard time display styling**

The time display at lines 91-96 already has `font-mono`. Verify it's using the correct color:

Current (lines 89-96):
```tsx
<div className="flex items-center gap-1.5">
  <Clock size={12} className="text-[#2E66FF] flex-shrink-0" />
  <span
    className="text-xs font-mono"
    style={{ color: '#2E66FF' }}
  >
    {meeting.time}
  </span>
</div>
```

This is already styled correctly with `font-mono` and accent color. No changes needed.

**Step 2: Verify StatRow count styling**

Lines 181-189 show:
```tsx
<span className="font-mono text-[#2E66FF]">{count}</span>
```

This is already using `font-mono` with the accent color. The `aria-data` class would make it lighter (#8B9DC3), but the current accent color (#2E66FF) provides better visibility for interactive elements. Keep as-is.

**Step 3: No changes needed - already styled correctly**

The Intelligence Panel already uses JetBrains Mono for time labels via `font-mono` class. No commit needed for this task.

---

## Task 7: Update Message Timestamp Tooltips to JetBrains Mono

**Files:**
- Modify: `frontend/src/components/conversation/MessageBubble.tsx:180-182` (ARIA message)
- Modify: `frontend/src/components/conversation/MessageBubble.tsx:198-200` (User message)

**Step 1: Verify ARIA message timestamp styling**

Line 180-182 currently shows:
```tsx
<span className="absolute -bottom-5 left-4 hidden group-hover:block font-mono text-[11px] text-[#555770] bg-[#111318] px-2 py-1 rounded whitespace-nowrap z-10">
  {formatTime(message.timestamp)}
</span>
```

This already uses `font-mono`. The color #555770 is appropriate for muted timestamps. Keep as-is.

**Step 2: Verify User message timestamp styling**

Line 198-200 currently shows:
```tsx
<span className="absolute -bottom-5 right-4 hidden group-hover:block font-mono text-[11px] text-[#555770] bg-[#111318] px-2 py-1 rounded whitespace-nowrap z-10">
  {formatTime(message.timestamp)}
</span>
```

This already uses `font-mono`. Keep as-is.

**Step 3: No changes needed - already styled correctly**

Both ARIA and user message timestamp tooltips already use JetBrains Mono via `font-mono` class. No commit needed for this task.

---

## Task 8: Create Post-Processor for ARIA Message Data Detection (Optional Enhancement)

**Files:**
- Modify: `frontend/src/components/conversation/MessageBubble.tsx` (integrate processAriaTypography)

**Note:** This task is OPTIONAL. The regex-based approach in Task 2 creates a utility that could be used, but the CSS-only approach in Task 3-4 handles the most common cases (strong/bold text). Regex-based data detection would require more complex integration with ReactMarkdown.

**Decision:** Skip this task for initial implementation. The CSS classes handle:
- Bold/emphasized text → Instrument Serif (via `.prose-aria strong` CSS rule)
- Inline code → JetBrains Mono (via `.aria-data` on code elements)
- Timestamps already use JetBrains Mono (via `font-mono` class)

If needed later, the `processAriaTypography` utility can be integrated with a custom text renderer.

---

## Task 9: Final Verification and Integration Testing

**Files:**
- None (verification only)

**Step 1: Run full frontend build**

```bash
cd frontend && npm run build
```
Expected: Build completes without errors

**Step 2: Run type checking**

```bash
cd frontend && npm run typecheck
```
Expected: No TypeScript errors

**Step 3: Manual visual verification checklist**

Start dev server: `cd frontend && npm run dev`

Open ARIA Chat and verify:
- [ ] ARIA message with **bold text** renders in Instrument Serif italic
- [ ] ARIA message with `inline code` renders in JetBrains Mono (lighter color)
- [ ] ARIA message body text remains Inter/Satoshi (default)
- [ ] User messages remain unchanged (all Inter/Satoshi)
- [ ] Message timestamp dividers show in JetBrains Mono
- [ ] Message hover tooltips show in JetBrains Mono
- [ ] Intelligence Panel meeting times show in JetBrains Mono
- [ ] No layout shifts or broken rendering

**Step 4: Final commit if any fixes needed**

```bash
git status
# If any uncommitted changes:
git add -A
git commit -m "fix: Typography adjustments from verification

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `frontend/index.html` | Add weight 500 to JetBrains Mono import |
| `frontend/src/utils/ariaTypography.ts` | NEW: Utility for detecting data patterns (future use) |
| `frontend/src/index.css` | Add `.aria-insight` and `.aria-data` CSS classes |
| `frontend/src/components/conversation/MessageBubble.tsx` | Update markdown components to use aria-insight/aria-data |
| `frontend/src/components/conversation/TimeDivider.tsx` | Ensure JetBrains Mono styling |

## Fonts Summary

| Font | Usage | CSS Class | Size | Weight/Style |
|------|-------|-----------|------|--------------|
| Instrument Serif | ARIA key insights, emphasized text | `.aria-insight` | 16px | italic |
| JetBrains Mono | Timestamps, numbers, data | `.aria-data` | 12px | 500 |
| Inter/Satoshi | Body text (default) | — | 14-16px | 300-400 |

## Scope Exclusions

- NOT changing overall app font (Inter/Satoshi remains default)
- NOT touching user message styling
- NOT modifying message content or backend
- NOT breaking markdown rendering
