# UICommandExecutor & IntelPanel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give ARIA the ability to control the UI programmatically (navigate, highlight, update panels) and build the context-adaptive Intelligence Panel with route-aware modules.

**Architecture:** UICommandExecutor is a core service that processes `UICommand[]` arrays from ARIA's WebSocket messages. It uses React Router's navigate function and DOM APIs to execute commands sequentially with 150ms delays for visual feedback. The IntelPanel is upgraded from its current placeholder to render route-specific modules backed by an IntelPanelContext. All 14 stub modules render realistic placeholder data.

**Tech Stack:** React 18, TypeScript, Zustand, React Router v6, Framer Motion, Lucide icons, CSS custom properties (ARIA design system)

---

### Task 1: Expand UICommand Types

**Files:**
- Modify: `frontend/src/api/chat.ts:47-52`
- Modify: `frontend/src/types/chat.ts`

**Step 1: Update UICommand interface with typed action field**

In `frontend/src/api/chat.ts`, replace the loose `action: string` with a union type and add typed fields for each command:

```typescript
export type UICommandAction =
  | 'navigate'
  | 'highlight'
  | 'update_intel_panel'
  | 'scroll_to'
  | 'switch_mode'
  | 'show_notification'
  | 'update_sidebar_badge'
  | 'open_modal';

export type HighlightEffect = 'glow' | 'pulse' | 'outline';

export interface UICommand {
  action: UICommandAction;
  route?: string;
  element?: string;
  effect?: HighlightEffect;
  duration?: number;
  content?: Record<string, unknown>;
  mode?: 'workspace' | 'dialogue' | 'compact_avatar';
  badge_count?: number;
  sidebar_item?: string;
  notification_type?: 'signal' | 'alert' | 'success' | 'info';
  notification_message?: string;
  modal_id?: string;
  modal_data?: Record<string, unknown>;
}
```

**Step 2: Verify types re-export**

Confirm `frontend/src/types/chat.ts` re-exports correctly (it already does `export type { UICommand } from '@/api/chat'`). No changes needed there unless the re-export breaks.

**Step 3: Commit**

```bash
git add frontend/src/api/chat.ts
git commit -m "feat: expand UICommand types with typed actions and effect fields"
```

---

### Task 2: Add Highlight CSS Classes

**Files:**
- Modify: `frontend/src/index.css`

**Step 1: Add highlight effect keyframes and classes**

Append to `frontend/src/index.css` before the `@media (prefers-reduced-motion)` block:

```css
/* === ARIA Highlight Effects (UICommandExecutor) === */

@keyframes aria-highlight-glow-anim {
  0% { box-shadow: 0 0 0 0 rgba(46, 102, 255, 0); }
  20% { box-shadow: 0 0 20px 4px rgba(46, 102, 255, 0.4); }
  80% { box-shadow: 0 0 20px 4px rgba(46, 102, 255, 0.4); }
  100% { box-shadow: 0 0 0 0 rgba(46, 102, 255, 0); }
}

@keyframes aria-highlight-pulse-anim {
  0% { transform: scale(1); }
  15% { transform: scale(1.02); }
  30% { transform: scale(1); }
  45% { transform: scale(1.02); }
  60% { transform: scale(1); }
  100% { transform: scale(1); }
}

@keyframes aria-highlight-outline-anim {
  0% { outline-color: transparent; }
  20% { outline-color: rgba(46, 102, 255, 0.8); }
  80% { outline-color: rgba(46, 102, 255, 0.8); }
  100% { outline-color: transparent; }
}

.aria-highlight-glow {
  animation: aria-highlight-glow-anim 3s ease-out forwards;
  border-radius: inherit;
}

.aria-highlight-pulse {
  animation: aria-highlight-pulse-anim 3s ease-in-out forwards;
}

.aria-highlight-outline {
  outline: 2px solid transparent;
  outline-offset: 3px;
  animation: aria-highlight-outline-anim 3s ease-out forwards;
}
```

Also add to the `@media (prefers-reduced-motion)` block:

```css
.aria-highlight-glow,
.aria-highlight-pulse,
.aria-highlight-outline {
  animation: none;
}
```

**Step 2: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat: add ARIA highlight effect CSS classes for UICommandExecutor"
```

---

### Task 3: Build UICommandExecutor

**Files:**
- Create: `frontend/src/core/UICommandExecutor.ts`

**Step 1: Create the executor**

```typescript
/**
 * UICommandExecutor - Processes UICommand[] from ARIA's messages
 *
 * Executes commands sequentially with 150ms delay between each for visual
 * feedback. Uses React Router navigate, DOM APIs for highlights/scrolling,
 * and store updates for panel/sidebar/notification changes.
 *
 * Initialized by useUICommands hook with the router navigate function.
 */

import type { UICommand, HighlightEffect } from '@/api/chat';
import { useNavigationStore } from '@/stores/navigationStore';
import { useNotificationsStore } from '@/stores/notificationsStore';

type NavigateFunction = (to: string) => void;

const COMMAND_DELAY_MS = 150;
const DEFAULT_HIGHLIGHT_DURATION_MS = 3000;

class UICommandExecutorImpl {
  private navigateFn: NavigateFunction | null = null;
  private intelPanelUpdateHandler: ((content: Record<string, unknown>) => void) | null = null;

  /**
   * Must be called once by useUICommands with the React Router navigate function.
   */
  setNavigate(fn: NavigateFunction): void {
    this.navigateFn = fn;
  }

  /**
   * Register callback for intel panel updates.
   */
  setIntelPanelHandler(handler: (content: Record<string, unknown>) => void): void {
    this.intelPanelUpdateHandler = handler;
  }

  /**
   * Execute an array of UICommands sequentially with delays.
   */
  async executeCommands(commands: UICommand[]): Promise<void> {
    if (!commands.length) return;

    for (let i = 0; i < commands.length; i++) {
      await this.executeCommand(commands[i]);
      if (i < commands.length - 1) {
        await this.delay(COMMAND_DELAY_MS);
      }
    }
  }

  private async executeCommand(cmd: UICommand): Promise<void> {
    switch (cmd.action) {
      case 'navigate':
        this.handleNavigate(cmd);
        break;
      case 'highlight':
        this.handleHighlight(cmd);
        break;
      case 'update_intel_panel':
        this.handleUpdateIntelPanel(cmd);
        break;
      case 'scroll_to':
        this.handleScrollTo(cmd);
        break;
      case 'switch_mode':
        this.handleSwitchMode(cmd);
        break;
      case 'show_notification':
        this.handleShowNotification(cmd);
        break;
      case 'update_sidebar_badge':
        this.handleUpdateSidebarBadge(cmd);
        break;
      case 'open_modal':
        this.handleOpenModal(cmd);
        break;
      default:
        console.warn(`[UICommandExecutor] Unknown command action: ${cmd.action}`);
    }
  }

  private handleNavigate(cmd: UICommand): void {
    if (!cmd.route || !this.navigateFn) return;
    this.navigateFn(cmd.route);
    useNavigationStore.getState().setCurrentRoute(cmd.route);
  }

  private handleHighlight(cmd: UICommand): void {
    if (!cmd.element) return;

    const el = document.querySelector(`[data-aria-id="${cmd.element}"]`);
    if (!el) return;

    const effect: HighlightEffect = cmd.effect || 'glow';
    const className = `aria-highlight-${effect}`;
    const duration = cmd.duration || DEFAULT_HIGHLIGHT_DURATION_MS;

    el.classList.add(className);
    setTimeout(() => {
      el.classList.remove(className);
    }, duration);
  }

  private handleUpdateIntelPanel(cmd: UICommand): void {
    if (!cmd.content) return;
    this.intelPanelUpdateHandler?.(cmd.content);
  }

  private handleScrollTo(cmd: UICommand): void {
    if (!cmd.element) return;

    const el = document.querySelector(`[data-aria-id="${cmd.element}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  private handleSwitchMode(cmd: UICommand): void {
    if (!cmd.mode || !this.navigateFn) return;

    const modeRoutes: Record<string, string> = {
      workspace: '/',
      dialogue: '/dialogue',
      compact_avatar: '/',
    };
    const route = modeRoutes[cmd.mode];
    if (route) {
      this.navigateFn(route);
      useNavigationStore.getState().setCurrentRoute(route);
    }
  }

  private handleShowNotification(cmd: UICommand): void {
    const store = useNotificationsStore.getState();
    const typeMap: Record<string, 'info' | 'success' | 'warning' | 'error'> = {
      signal: 'info',
      alert: 'warning',
      success: 'success',
      info: 'info',
    };
    store.addNotification({
      type: typeMap[cmd.notification_type || 'info'] || 'info',
      title: cmd.notification_message || 'ARIA Notification',
      message: typeof cmd.content?.detail === 'string' ? cmd.content.detail : undefined,
    });
  }

  private handleUpdateSidebarBadge(cmd: UICommand): void {
    // Badge counts are managed through the navigation store.
    // The Sidebar component reads badge counts from here.
    // For now, we emit a custom event that the Sidebar can listen to.
    if (!cmd.sidebar_item || cmd.badge_count === undefined) return;
    window.dispatchEvent(
      new CustomEvent('aria:sidebar-badge', {
        detail: { item: cmd.sidebar_item, count: cmd.badge_count },
      }),
    );
  }

  private handleOpenModal(cmd: UICommand): void {
    if (!cmd.modal_id) return;
    window.dispatchEvent(
      new CustomEvent('aria:open-modal', {
        detail: { id: cmd.modal_id, data: cmd.modal_data || cmd.content },
      }),
    );
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

/** Singleton instance */
export const uiCommandExecutor = new UICommandExecutorImpl();
```

**Step 2: Commit**

```bash
git add frontend/src/core/UICommandExecutor.ts
git commit -m "feat: add UICommandExecutor core service for ARIA-driven UI control"
```

---

### Task 4: Build useUICommands Hook

**Files:**
- Create: `frontend/src/hooks/useUICommands.ts`

**Step 1: Create the hook**

```typescript
/**
 * useUICommands - React hook wrapping UICommandExecutor
 *
 * Auto-initializes with React Router's navigate function.
 * Listens for aria.message and aria.metadata events to auto-execute ui_commands.
 * Also exposes executeUICommands() for manual execution.
 */

import { useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { uiCommandExecutor } from '@/core/UICommandExecutor';
import { wsManager } from '@/core/WebSocketManager';
import type { UICommand } from '@/api/chat';
import type { AriaMessagePayload } from '@/types/chat';

export function useUICommands() {
  const navigate = useNavigate();
  const initializedRef = useRef(false);

  // Initialize executor with navigate function
  useEffect(() => {
    if (!initializedRef.current) {
      uiCommandExecutor.setNavigate(navigate);
      initializedRef.current = true;
    }
  }, [navigate]);

  // Listen for aria.message events and auto-execute ui_commands
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = payload as AriaMessagePayload;
      if (data.ui_commands?.length) {
        void uiCommandExecutor.executeCommands(data.ui_commands as UICommand[]);
      }
    };

    const handleMetadata = (payload: unknown) => {
      const data = payload as { ui_commands?: UICommand[] };
      if (data.ui_commands?.length) {
        void uiCommandExecutor.executeCommands(data.ui_commands);
      }
    };

    wsManager.on('aria.message', handleAriaMessage);
    wsManager.on('aria.metadata', handleMetadata);

    return () => {
      wsManager.off('aria.message', handleAriaMessage);
      wsManager.off('aria.metadata', handleMetadata);
    };
  }, []);

  const executeUICommands = useCallback((commands: UICommand[]) => {
    return uiCommandExecutor.executeCommands(commands);
  }, []);

  return { executeUICommands };
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useUICommands.ts
git commit -m "feat: add useUICommands hook for auto-executing ARIA UI commands"
```

---

### Task 5: Wire useUICommands into ARIAWorkspace

**Files:**
- Modify: `frontend/src/components/pages/ARIAWorkspace.tsx`

**Step 1: Add the hook call**

Import and call `useUICommands()` at the top of the ARIAWorkspace component. The hook auto-registers WebSocket listeners, so no other wiring is needed.

Add after existing imports:
```typescript
import { useUICommands } from '@/hooks/useUICommands';
```

Add inside the component function body (after the existing hooks):
```typescript
useUICommands();
```

**Step 2: Commit**

```bash
git add frontend/src/components/pages/ARIAWorkspace.tsx
git commit -m "feat: wire useUICommands into ARIAWorkspace for ARIA-driven UI control"
```

---

### Task 6: Build IntelPanelContext

**Files:**
- Create: `frontend/src/contexts/IntelPanelContext.tsx`

**Step 1: Create the context**

```typescript
/**
 * IntelPanelContext - State for the ARIA Intelligence Panel
 *
 * Stores current panel content that can be updated by:
 * 1. Route changes (auto-selects appropriate modules)
 * 2. ARIA via update_intel_panel UICommand
 * 3. Direct programmatic updates
 */

import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { uiCommandExecutor } from '@/core/UICommandExecutor';

export interface IntelPanelState {
  /** Current panel title override (null = use route default) */
  titleOverride: string | null;
  /** Custom content pushed by ARIA via update_intel_panel */
  ariaContent: Record<string, unknown> | null;
  /** Timestamp of last ARIA update */
  lastAriaUpdate: string | null;
}

interface IntelPanelContextValue {
  state: IntelPanelState;
  /** Push custom content from ARIA */
  updateFromAria: (content: Record<string, unknown>) => void;
  /** Clear ARIA override and revert to route-based defaults */
  clearAriaContent: () => void;
  /** Get the current route for module selection */
  currentRoute: string;
}

const IntelPanelCtx = createContext<IntelPanelContextValue | null>(null);

export function IntelPanelProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [state, setState] = useState<IntelPanelState>({
    titleOverride: null,
    ariaContent: null,
    lastAriaUpdate: null,
  });

  const updateFromAria = useCallback((content: Record<string, unknown>) => {
    setState({
      titleOverride: typeof content.title === 'string' ? content.title : null,
      ariaContent: content,
      lastAriaUpdate: new Date().toISOString(),
    });
  }, []);

  const clearAriaContent = useCallback(() => {
    setState({
      titleOverride: null,
      ariaContent: null,
      lastAriaUpdate: null,
    });
  }, []);

  // Register the handler on the UICommandExecutor
  uiCommandExecutor.setIntelPanelHandler(updateFromAria);

  const value = useMemo(
    () => ({
      state,
      updateFromAria,
      clearAriaContent,
      currentRoute: location.pathname,
    }),
    [state, updateFromAria, clearAriaContent, location.pathname],
  );

  return <IntelPanelCtx.Provider value={value}>{children}</IntelPanelCtx.Provider>;
}

export function useIntelPanel(): IntelPanelContextValue {
  const ctx = useContext(IntelPanelCtx);
  if (!ctx) {
    throw new Error('useIntelPanel must be used within IntelPanelProvider');
  }
  return ctx;
}
```

**Step 2: Commit**

```bash
git add frontend/src/contexts/IntelPanelContext.tsx
git commit -m "feat: add IntelPanelContext for ARIA-driven panel content updates"
```

---

### Task 7: Build IntelPanel Modules (Stubs)

**Files:**
- Create: `frontend/src/components/shell/intel-modules/AlertsModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/BuyingSignalsModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/CompetitiveIntelModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/NewsAlertsModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/WhyIWroteThisModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/ToneModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/AnalysisModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/NextBestActionModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/StrategicAdviceModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/ObjectionsModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/NextStepsModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/AgentStatusModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/CRMSnapshotModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/ChatInputModule.tsx`
- Create: `frontend/src/components/shell/intel-modules/index.ts`

Each module follows this pattern:
- Named export component
- Typed props interface
- Realistic placeholder data showing what ARIA would actually surface
- Uses ARIA design system CSS variables
- `data-aria-id` attribute for UICommandExecutor targeting
- Lucide icons for visual richness

**Step 1: Create all module files**

See full module code below. All modules use a shared `ModuleCard` wrapper pattern for consistency:

```typescript
// Shared pattern used in each module:
interface ModuleCardProps {
  children: React.ReactNode;
  className?: string;
}

function ModuleCard({ children, className }: ModuleCardProps) {
  return (
    <div
      className={`rounded-lg border p-3 ${className ?? ''}`}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-subtle)',
      }}
    >
      {children}
    </div>
  );
}
```

Each module's specific content and interfaces are defined in the plan's appendix (Task 7 Appendix).

**Step 2: Create barrel export**

`frontend/src/components/shell/intel-modules/index.ts`:
```typescript
export { AlertsModule } from './AlertsModule';
export { BuyingSignalsModule } from './BuyingSignalsModule';
export { CompetitiveIntelModule } from './CompetitiveIntelModule';
export { NewsAlertsModule } from './NewsAlertsModule';
export { WhyIWroteThisModule } from './WhyIWroteThisModule';
export { ToneModule } from './ToneModule';
export { AnalysisModule } from './AnalysisModule';
export { NextBestActionModule } from './NextBestActionModule';
export { StrategicAdviceModule } from './StrategicAdviceModule';
export { ObjectionsModule } from './ObjectionsModule';
export { NextStepsModule } from './NextStepsModule';
export { AgentStatusModule } from './AgentStatusModule';
export { CRMSnapshotModule } from './CRMSnapshotModule';
export { ChatInputModule } from './ChatInputModule';
```

**Step 3: Commit**

```bash
git add frontend/src/components/shell/intel-modules/
git commit -m "feat: add 14 IntelPanel stub modules with realistic placeholder data"
```

---

### Task 8: Rewrite IntelPanel with Module Rendering

**Files:**
- Modify: `frontend/src/components/shell/IntelPanel.tsx`

**Step 1: Rewrite IntelPanel**

Replace the entire file. The new version:
- Uses `useIntelPanel()` context for ARIA-driven content
- Route-based module selection (maps pathname to module sets)
- Renders actual module components instead of string lists
- Supports ARIA content overrides via `update_intel_panel` command
- Keeps same 320px width, header with title + menu, scrollable content
- Adds a `ChatInputModule` at the bottom of every non-ARIA-workspace panel

Route → Module mapping:
- `/pipeline*` → AlertsModule, BuyingSignalsModule, CRMSnapshotModule
- `/intelligence*` → CompetitiveIntelModule, NewsAlertsModule, NextBestActionModule
- `/communications*` → WhyIWroteThisModule, ToneModule, AnalysisModule
- `/pipeline/leads/:id` → StrategicAdviceModule, ObjectionsModule, NextStepsModule, CRMSnapshotModule
- `/actions*` → AgentStatusModule, NextBestActionModule
- default (briefing, settings) → AlertsModule, NextBestActionModule

**Step 2: Commit**

```bash
git add frontend/src/components/shell/IntelPanel.tsx
git commit -m "feat: rewrite IntelPanel with route-based module rendering and ARIA control"
```

---

### Task 9: Wire IntelPanelProvider into App

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add IntelPanelProvider inside the Router**

Import `IntelPanelProvider` and wrap it inside `BrowserRouter` but around `AppRoutes`. It needs to be inside the Router because it uses `useLocation`.

```typescript
import { IntelPanelProvider } from '@/contexts/IntelPanelContext';
```

Wrap inside the provider stack:
```tsx
<BrowserRouter>
  <AuthProvider>
    <ThemeProvider>
      <SessionProvider>
        <IntelPanelProvider>
          <AppRoutes />
        </IntelPanelProvider>
      </SessionProvider>
    </ThemeProvider>
  </AuthProvider>
</BrowserRouter>
```

**Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire IntelPanelProvider into app provider stack"
```

---

### Task 10: Verify Build

**Step 1: Run TypeScript check**

```bash
cd frontend && npm run typecheck
```

Expected: No type errors.

**Step 2: Run lint**

```bash
npm run lint
```

Expected: No errors (warnings acceptable).

**Step 3: Run build**

```bash
npm run build
```

Expected: Successful build.

**Step 4: Fix any issues and commit**

```bash
git add -A && git commit -m "fix: resolve build issues from UICommandExecutor and IntelPanel integration"
```

---

## Task 7 Appendix: Module Implementations

Each module below is the complete file content.

### AlertsModule.tsx
- Shows 3 pipeline alerts with severity indicators (dot colors)
- Items: "Lonza deal velocity dropped 40%", "Catalent RFP deadline in 3 days", "BioConnect champion went silent (14 days)"
- Severity dots: critical (red), warning (amber), info (blue)

### BuyingSignalsModule.tsx
- Shows 3 buying signals detected by Scout agent
- Items: "Lonza posted Sr. Dir. Process Dev role", "Catalent visited pricing page 3x this week", "BioConnect downloaded whitepaper on GMP compliance"
- Each with a signal strength indicator (high/medium/low)

### CompetitiveIntelModule.tsx
- Shows 2-3 competitor movements
- Items: "Thermo Fisher launched new CDMO pricing tier", "Sartorius acquired BioProcess Solutions Ltd", "Catalent competitor hired away from Lonza"
- Source labels (news, job boards, SEC filings)

### NewsAlertsModule.tsx
- Shows 2-3 industry news items
- Items: "FDA approves new biologics pathway — impact on CMO demand", "Life Sciences M&A activity up 23% QoQ"
- Timestamps and source

### WhyIWroteThisModule.tsx
- Shows ARIA's reasoning for a draft communication
- "Based on Lonza's recent silence (14 days) and their Q2 budget cycle starting March 1, this follow-up targets re-engagement before budget lock."
- Key factors listed as bullet points

### ToneModule.tsx
- Shows tone analysis/recommendation
- Current tone: "Professional, consultative"
- Recommendation: "Consider warmer opening — Dr. Chen responds better to relationship-first messaging"
- Tone spectrum visual (formal ←→ casual slider)

### AnalysisModule.tsx
- Shows communication effectiveness stats
- Open rate: 68%, Reply rate: 34%, Avg response time: 4.2 hours
- Trend: "Reply rates up 12% since adopting ARIA's suggestions"

### NextBestActionModule.tsx
- Shows ARIA's top recommended action
- "Send follow-up to Dr. Sarah Chen at Lonza RE: Q2 capacity planning"
- Priority level, estimated impact, agent source (Strategist)

### StrategicAdviceModule.tsx
- Shows strategic advice for a specific lead/account
- "Lonza is evaluating 3 CDMOs. Your differentiator: regulatory expertise. Lead with compliance case studies."
- Confidence score

### ObjectionsModule.tsx
- Shows predicted objections and recommended responses
- "Pricing concern" → "Emphasize total cost of ownership — our compliance support saves $200K/yr avg"
- "Timeline" → "Reference Catalent project delivered 2 weeks early"

### NextStepsModule.tsx
- Shows prioritized next steps for a lead
- Checklist: "Schedule technical review (by Feb 15)", "Send updated proposal (pending)", "Introduce VP Engineering (not started)"
- Status indicators per step

### AgentStatusModule.tsx
- Shows status of ARIA's 6 agents
- Hunter: "Scanning 12 job boards", Analyst: "Processing Lonza financials", Strategist: "Idle"
- Activity dots (active/idle/error)

### CRMSnapshotModule.tsx
- Shows CRM summary for current context
- Deal stage, amount, close date, last activity
- "Lonza — $450K — Proposal Sent — Close: Mar 15"

### ChatInputModule.tsx
- Mini chat input for contextual questions
- "Ask ARIA about this..." placeholder
- Small send button
- Sends via WebSocket with context metadata
