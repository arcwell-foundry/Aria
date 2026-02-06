# ARIA Design System v1.0

> **This document is the single source of truth for all ARIA UI/UX implementation.**
> It supersedes any generated design-system files from ui-ux-pro-max.
> Read this BEFORE writing any frontend code.

---

## Philosophy (The "Why")

ARIA is a $200K/year Digital Department Director for life sciences commercial teams. The design must communicate that value through restraint, precision, and craftsmanship — never through ostentation.

**The user should never feel they are operating software. They should feel they are collaborating with a mind.**

### The Five Principles

1. **Restraint Is Luxury** — Every element earns its place. The premium feeling comes from generous whitespace, precise alignment, and the discipline to leave things out.
2. **Intelligence, Not Information** — Where a typical dashboard shows 47 metrics, ARIA surfaces 3 insights. Information hierarchy does the heavy lifting.
3. **Presence Without Performance** — ARIA is always working. Convey this through subtle, living details — not notification barrages or blinking lights.
4. **Every Interaction Is Considered** — No click is accidental. No button exists without intent. Keyboard shortcuts for power users. Unhurried animations for transitions.
5. **One ARIA, Many Surfaces** — Text, voice, and video feel like the same colleague. Switching surfaces feels like continuing a conversation, not switching apps.

### Design DNA

- **Superhuman** — Speed as a feature. Dark, focused interfaces. Power user velocity.
- **Apple Health & macOS** — Complex data made personal and warm. System-level polish. Nothing feels "web app-ish."
- **Bloomberg Terminal × The Economist** — Information density married to typographic excellence. Authority without decoration.

### The Test

> Would a VP of Sales at a $500M biotech, who has used Salesforce for 10 years and trusts Apple with their personal life, look at this and think: *finally, someone built enterprise software that respects me*?

---

## Adaptive Theming

ARIA uses context-aware theming — not a user toggle. The interface shifts between dark and light based on the user's cognitive mode.

### Dark Surfaces (Consuming Intelligence)

| Surface | Rationale |
|---------|-----------|
| Daily Intel Briefing | Immersive — receiving intelligence |
| Competitive Battle Cards | War room — focused analysis |
| Agent Activity / OODA Loop | Command center — monitoring ARIA's work |
| Chat with ARIA | Conversational — Superhuman-like focus |
| Market Signal Dashboard | Surveillance — pattern recognition |

### Light Surfaces (Producing Work)

| Surface | Rationale |
|---------|-----------|
| Email Drafting | Composition — clarity and readability |
| Meeting Prep Documents | Review — paper-like comfort |
| Account / Contact Profiles | Reference — clean, scannable |
| Settings & Administration | Utility — macOS System Preferences feel |
| Onboarding / Setup | Welcoming — approachable first impression |

---

## Color System

Color is used for meaning, never for decoration. The system relies on a tonal range of muted slate-blues and warm neutrals.

### Dark Mode Palette

```css
--bg-primary:        #0F1117;   /* Primary dark surface */
--bg-elevated:       #161B2E;   /* Cards, panels, elevated elements */
--bg-subtle:         #1E2235;   /* Hover states, secondary panels */
--border:            #2A2F42;   /* Subtle dividers between surfaces */
--text-primary:      #E8E6E1;   /* Main content text (warm off-white) */
--text-secondary:    #8B92A5;   /* Labels, metadata, supporting text */
--interactive:       #7B8EAA;   /* Links, active states, selections */
--interactive-hover: #95A5BD;   /* Hover state for interactive elements */
```

### Light Mode Palette

```css
--bg-primary:        #FAFAF9;   /* Primary light surface (warm off-white) */
--bg-elevated:       #FFFFFF;   /* Cards, panels, elevated elements */
--bg-subtle:         #F5F5F0;   /* Secondary areas, sidebar backgrounds */
--border:            #E2E0DC;   /* Dividers and borders */
--text-primary:      #1A1D27;   /* Main content text */
--text-secondary:    #6B7280;   /* Labels, metadata, supporting text */
--interactive:       #5B6E8A;   /* Links, active states, selections */
--interactive-hover: #4A5D79;   /* Hover state for interactive elements */
```

### Semantic Colors (Both Modes — Desaturated, Never Neon)

```css
/* Dark Mode */
--success:           #6B8F71;   /* Completed actions, positive signals */
--warning:           #B8956A;   /* Attention needed, caution states */
--critical:          #A66B6B;   /* Errors, urgent items */
--info:              #6B7FA3;   /* Neutral informational states */
--new-intelligence:  #8B92A5;   /* Subtle pulse for new ARIA activity */

/* Light Mode */
--success:           #5A7D60;
--warning:           #A6845A;
--critical:          #945A5A;
--info:              #5B6E8A;
--new-intelligence:  #7B8EAA;
```

### The "Pop" — Reserved Luminance

ARIA does **not** have a bright accent color. Moments that matter are marked by a brief, subtle luminance shift — a gentle brightening of a surface, a momentary increase in contrast. The effect is felt, not seen.

**No neon. No gradients. No glowing borders. No teal. No violet. No gold.**

---

## Typography

Typography carries the "intellectual" weight of ARIA's identity.

### Font Stack

| Role | Typeface | Weights | Usage |
|------|----------|---------|-------|
| Display / Headings | **Instrument Serif** | Regular, Italic | Page titles, briefing headers, section names |
| UI / Body | **Satoshi** (primary) or **General Sans** (fallback) | Regular (400), Medium (500), Bold (700) | Interface labels, body text, navigation, buttons |
| Data / Monospace | **JetBrains Mono** | Regular (400) | Metrics, timestamps, technical data, code |

### Google Fonts Loading

```html
<!-- Instrument Serif -->
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">

<!-- Satoshi — load from Fontshare (not Google Fonts) -->
<link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap" rel="stylesheet">

<!-- JetBrains Mono -->
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
```

### Tailwind Config

```javascript
fontFamily: {
  display: ['"Instrument Serif"', 'Georgia', 'serif'],
  sans: ['Satoshi', '"General Sans"', 'system-ui', 'sans-serif'],
  mono: ['"JetBrains Mono"', 'monospace'],
}
```

### Type Scale

| Name | Size | Line Height | Font | Usage |
|------|------|-------------|------|-------|
| Display | 32px / 2rem | 1.2 | Instrument Serif | Page titles, briefing headlines |
| Title | 24px / 1.5rem | 1.3 | Instrument Serif | Section headers, card titles |
| Subtitle | 18px / 1.125rem | 1.4 | Satoshi Medium | Subsections, prominent labels |
| Body | 15px / 0.9375rem | 1.6 | Satoshi Regular | Primary content, paragraphs |
| Caption | 13px / 0.8125rem | 1.5 | Satoshi Regular | Metadata, timestamps, secondary labels |
| Micro | 11px / 0.6875rem | 1.4 | Satoshi Medium | Badges, status indicators |
| Data | 13px / 0.8125rem | 1.4 | JetBrains Mono | Numbers, metrics, technical values |

---

## Spacing & Layout

### Spacing Scale (Base: 4px)

```
4px  — micro gaps (icon-to-label)
8px  — tight spacing (within components)
12px — compact spacing (form elements)
16px — default spacing (between elements)
24px — comfortable spacing (between sections within a card)
32px — section spacing (between cards)
48px — major section spacing
64px — page section dividers
```

### Layout Architecture

Three-column layout adapted from command center patterns:

| Column | Purpose | Width | Behavior |
|--------|---------|-------|----------|
| Left Sidebar | Navigation + ARIA identity | 240px | Collapsible to 64px (icon-only). Shows ARIA's current state. |
| Center Workspace | Primary activity area | Fluid (min 600px) | Adapts to current task: briefing, chat, email draft, battle card. |
| Right Intelligence Panel | Contextual insights | 320px | Collapsible. Shows what ARIA thinks you should know. |

### Responsive Breakpoints

```css
/* Mobile */        @media (max-width: 767px)    — Single column, bottom nav
/* Tablet */        @media (min-width: 768px)    — Two columns (sidebar + main)
/* Desktop */       @media (min-width: 1024px)   — Full three-column layout
/* Wide Desktop */  @media (min-width: 1440px)   — Expanded content areas, more breathing room
```

### Density Modes

- **Briefing Mode** — Generous spacing, large typography, reading-optimized. Like a beautifully typeset morning paper.
- **Working Mode** — Balanced density. Content-forward with clear hierarchy. Like a dossier on your desk.
- **Command Mode** — Information-dense, compact. Multiple data streams visible simultaneously. Bloomberg with better taste.

---

## Motion & Interaction

Animation is purposeful and restrained. It creates a sense of life without drawing attention to itself.

### Timing

| Context | Duration | Easing | Example |
|---------|----------|--------|---------|
| Micro-interactions | 120–180ms | ease-out | Button press, toggle, hover state |
| Surface transitions | 200–300ms | ease-in-out | Panel open/close, card expansion |
| Content appearance | 300–400ms | ease-out | New content fading in, briefing load |
| Page transitions | 350–500ms | cubic-bezier(0.4, 0, 0.2, 1) | Route changes, major state shifts |
| ARIA "thinking" | Continuous | sine loop | Subtle ambient pulse, gentle luminance oscillation |

### Tailwind Defaults

```javascript
transitionDuration: {
  micro: '150ms',
  normal: '250ms',
  slow: '400ms',
},
transitionTimingFunction: {
  DEFAULT: 'cubic-bezier(0.4, 0, 0.2, 1)',
  bounce: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
}
```

### Signature Interactions

- **The Arrival** — New intelligence fades in line-by-line with staggered 50ms delay. Like someone writing to you.
- **The Pulse** — ARIA's presence indicator: a subtle, slow opacity oscillation. Never a loading spinner. A form that breathes.
- **The Settle** — When ARIA completes a task, the surface settles with a gentle ease-out. A moment of stillness that says "done."
- **The Depth Shift** — Moving between surfaces: subtle shadow change + scale (0.998 → 1.0). Spatial hierarchy without 3D transforms.

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

Always respect `prefers-reduced-motion`. All signature interactions must have static fallbacks.

---

## Components

### Cards

```
Dark mode:  bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6
Light mode: bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm
Hover:      subtle border color shift + shadow increase (no scale transform that shifts layout)
```

### Buttons

```
Primary:    bg-[#5B6E8A] text-white rounded-lg px-5 py-2.5 font-sans font-medium
            hover:bg-[#4A5D79] active:bg-[#3D5070] transition-colors duration-150
Secondary:  bg-transparent border border-[#5B6E8A] text-[#5B6E8A] rounded-lg px-5 py-2.5
            hover:bg-[#5B6E8A]/10 transition-colors duration-150
Ghost:      bg-transparent text-[#6B7280] rounded-lg px-4 py-2
            hover:bg-[#F5F5F0] (light) or hover:bg-[#1E2235] (dark)
Minimum touch target: 44x44px
Always: cursor-pointer, visible focus ring (ring-2 ring-[#7B8EAA] ring-offset-2)
```

### Form Inputs

```
Light:  bg-white border border-[#E2E0DC] rounded-lg px-4 py-3 text-[15px] font-sans
        focus:border-[#5B6E8A] focus:ring-1 focus:ring-[#5B6E8A]
Dark:   bg-[#1E2235] border border-[#2A2F42] rounded-lg px-4 py-3 text-[15px]
        focus:border-[#7B8EAA] focus:ring-1 focus:ring-[#7B8EAA]
Labels: font-sans text-[13px] font-medium text-secondary mb-1.5
Errors: text-[#A66B6B] (dark) or text-[#945A5A] (light), 13px, below input
```

### Navigation Sidebar

```
Width:      240px (expanded), 64px (collapsed)
Background: #0F1117 (always dark, regardless of page theme)
Items:      px-4 py-2.5 rounded-lg font-sans text-[14px]
Active:     bg-[#1E2235] text-[#E8E6E1]
Inactive:   text-[#8B92A5] hover:text-[#E8E6E1] hover:bg-[#161B2E]
Icons:      Lucide React, 20x20, stroke-width 1.5
ARIA state: Bottom of sidebar — subtle presence indicator (The Pulse)
```

### Data Visualization (Apple Health Inspired)

```
Chart library:    Recharts (already in stack)
Color palette:    Use semantic colors, desaturated. Never more than 5 colors per chart.
Border radius:    rounded corners on bars (radius: [4, 4, 0, 0])
Grid lines:       Subtle, dashed, color: #2A2F42 (dark) or #E2E0DC (light)
Labels:           JetBrains Mono, 11px, text-secondary
Tooltips:         bg-elevated, border, rounded-lg, shadow-lg, 13px
Animations:       Gentle ease-in on first render (800ms). No bouncing.
Empty state:      "ARIA is building this analysis. Check back in 24 hours."
```

---

## Icons

- **Library:** Lucide React (`lucide-react`)
- **Size:** 20x20 default, 16x16 compact, 24x24 feature/display
- **Stroke width:** 1.5 (matches Apple's SF Symbols weight)
- **Color:** Inherit from text color (currentColor)
- **NEVER use emojis as icons.** No exceptions.
- **NEVER use Font Awesome or similar icon fonts.** SVG only.

---

## Multi-Surface Communication

### Text Chat
- Clean, message-based. ARIA's messages: slightly different bg, Instrument Serif for key insights inline.
- User messages: standard bg, Satoshi.
- Streaming text animation for ARIA responses (The Arrival pattern).

### Voice
- Minimal visual interface. ARIA's presence: abstract breathing waveform (not graphic equalizer).
- Real-time transcript below in Caption size.
- Seamless context carry from text chat.

### Video Avatar (Tavus)
- ARIA occupies a focused frame with neutral, adaptive background.
- Side panel shows referenced documents/data ARIA is discussing.
- Transition from text feels like turning to face someone.

### ARIA's Ambient Presence Mark
- When not in video: an abstract, evolving form. Not a static icon, not a cartoon.
- Shifts gently when processing, settles when listening, becomes more defined when presenting.
- Think light moving through water. Organic, unhurried, intelligent.
- Never a loading spinner. Never bouncing dots.

---

## Accessibility

### Requirements (Non-Negotiable)

- Color contrast: 4.5:1 minimum for normal text, 3:1 for large text (WCAG AA)
- Focus states: Visible focus ring on all interactive elements (`ring-2 ring-[#7B8EAA] ring-offset-2`)
- Alt text: Descriptive alt text for all meaningful images
- ARIA labels: `aria-label` on all icon-only buttons
- Keyboard navigation: Tab order matches visual order. All functionality accessible via keyboard.
- Form labels: Proper `<label>` with `htmlFor` attribute
- Touch targets: Minimum 44x44px
- Reduced motion: Respect `prefers-reduced-motion`
- Screen reader: Semantic HTML. Use headings properly. Live regions for dynamic content.
- Color is never the only indicator — always pair with text, icon, or pattern.

---

## Pre-Delivery Checklist

Before shipping any UI, verify:

### Visual Quality
- [ ] No emojis used as icons (SVG only — Lucide React)
- [ ] All icons consistent size and stroke weight
- [ ] Hover states don't cause layout shift (no scale transforms on cards)
- [ ] Using design system colors directly, not arbitrary hex values
- [ ] Instrument Serif for headings, Satoshi for UI, JetBrains Mono for data

### Interaction
- [ ] All clickable elements have `cursor-pointer`
- [ ] Hover states provide clear visual feedback
- [ ] Transitions are smooth (150–300ms)
- [ ] Focus states visible for keyboard navigation
- [ ] Keyboard shortcuts work (if applicable)

### Theming
- [ ] Correct theme applied (dark for intelligence, light for composition)
- [ ] Text has sufficient contrast in both modes
- [ ] Borders visible in current mode
- [ ] Semantic colors are desaturated (no neon)

### Layout
- [ ] No content hidden behind fixed elements
- [ ] Responsive at 375px, 768px, 1024px, 1440px
- [ ] No horizontal scroll on mobile
- [ ] Proper spacing from design system scale (multiples of 4px)

### Accessibility
- [ ] All images have alt text
- [ ] Form inputs have labels
- [ ] Color is not the only indicator
- [ ] `prefers-reduced-motion` respected
- [ ] Touch targets ≥ 44x44px

### ARIA Intelligence
- [ ] Empty states explain what ARIA is doing, not just "No data"
- [ ] Loading states use considered skeleton screens (not generic shimmer)
- [ ] ARIA's messages have personality, not robotic confirmations
- [ ] Progressive disclosure — don't dump everything at once

---

## Anti-Patterns (What ARIA Must Never Look Like)

| Anti-Pattern | Why It Fails | ARIA's Alternative |
|---|---|---|
| Sci-fi aesthetic (neon glows, circuit motifs) | Performs intelligence rather than embodying it | Understated tonal color system |
| Dashboard overload (dozens of metrics) | Confuses data with insight | Curated insights — ARIA decides what matters |
| Chatbot UI (centered bubble, generic avatar) | Signals a simple tool, not a $200K colleague | Rich multi-surface communication with presence |
| Enterprise gray (Salesforce/SAP aesthetic) | Boring and institutional | Warm neutrals with considered typography |
| Startup playful (rounded everything, bright colors) | Undermines enterprise credibility | Refined geometry, muted palette, serif authority |
| Glassmorphism / Liquid Glass | Accessibility issues, looks like a tech demo | Solid surfaces with subtle depth via shadow and spacing |
| Gold/violet/teal accents | Tacky when overdone | Muted slate-blue tonal system only |

---

## File Structure for Styles

```
src/
  styles/
    tokens.css          — CSS custom properties (colors, spacing, typography)
    tailwind.config.ts  — Tailwind theme extension with design system tokens
  components/
    ui/                 — Shared primitives (Button, Card, Input, etc.)
    layout/             — Shell components (Sidebar, Workspace, IntelPanel)
    aria/               — ARIA-specific (PresenceMark, ArrivalText, Pulse)
```

---

*ARIA Design System v1.0 — LuminOne — February 2026*
*This document is the north star. When in doubt, refer to the Five Principles.*
