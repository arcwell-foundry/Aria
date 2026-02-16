# Jarvis Intelligence Frontend Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surface 4 Jarvis intelligence engines in the frontend so users can see daily briefings, market signals, pre-meeting research, and email drafting intelligence.

**Architecture:** Each integration adds a new component that calls existing React Query hooks (already wired to backend APIs). No new backend work. Components follow ARIA Design System v1.0 — light theme on content pages, dark on workspace, CSS variables for colors, Tailwind for layout.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, React Query (TanStack), Lucide icons, CSS variables

---

### Task 1: BriefingCard Rich Content Component

**Files:**
- Create: `frontend/src/components/rich/BriefingCard.tsx`
- Modify: `frontend/src/components/rich/RichContentRenderer.tsx:24-48`

**Step 1: Create BriefingCard component**

Create `frontend/src/components/rich/BriefingCard.tsx`:

```tsx
import { useState } from 'react';
import { Calendar, Users, TrendingUp, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';

export interface BriefingCardData {
  summary: string;
  calendar: {
    meeting_count: number;
    key_meetings: { time: string; title: string; attendees: string[] }[];
  };
  leads: {
    hot_leads: { id: string; name: string; company: string; health_score?: number }[];
    needs_attention: { id: string; name: string; company: string; health_score?: number }[];
  };
  signals: {
    company_news: { id: string; title: string; summary: string }[];
    market_trends: { id: string; title: string; summary: string }[];
    competitive_intel: { id: string; title: string; summary: string }[];
  };
  tasks: {
    overdue: { id: string; title: string; due_date?: string }[];
    due_today: { id: string; title: string; due_date?: string }[];
  };
}

function Section({
  icon: Icon,
  title,
  badge,
  children,
  defaultOpen = false,
}: {
  icon: typeof Calendar;
  title: string;
  badge?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-[var(--border-muted)] first:border-t-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 py-2 text-left cursor-pointer"
      >
        {open ? <ChevronDown size={12} className="text-[var(--text-secondary)]" /> : <ChevronRight size={12} className="text-[var(--text-secondary)]" />}
        <Icon size={14} style={{ color: 'var(--accent)' }} />
        <span className="font-sans text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{title}</span>
        {badge !== undefined && badge > 0 && (
          <span className="ml-auto font-mono text-[10px] px-1.5 py-0.5 rounded-full" style={{ backgroundColor: 'var(--accent)', color: 'white' }}>
            {badge}
          </span>
        )}
      </button>
      {open && <div className="pb-2 pl-6">{children}</div>}
    </div>
  );
}

export function BriefingCard({ data }: { data: BriefingCardData }) {
  const totalSignals =
    data.signals.company_news.length +
    data.signals.market_trends.length +
    data.signals.competitive_intel.length;
  const totalTasks = data.tasks.overdue.length + data.tasks.due_today.length;

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="briefing-card"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
        <p className="font-mono text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--accent)' }}>
          Daily Intelligence Briefing
        </p>
        <p className="font-sans text-[12px] leading-relaxed" style={{ color: 'var(--text-primary)' }}>
          {data.summary}
        </p>
      </div>

      {/* Sections */}
      <div className="px-4 py-1">
        <Section icon={Calendar} title="Calendar" badge={data.calendar.meeting_count} defaultOpen={data.calendar.meeting_count > 0}>
          {data.calendar.key_meetings.length === 0 ? (
            <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>No meetings today.</p>
          ) : (
            <div className="space-y-1.5">
              {data.calendar.key_meetings.map((m, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="font-mono text-[11px] flex-shrink-0" style={{ color: 'var(--accent)' }}>{m.time}</span>
                  <span className="text-[11px] truncate" style={{ color: 'var(--text-primary)' }}>{m.title}</span>
                  <span className="font-mono text-[10px] flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>
                    {m.attendees.length} attendee{m.attendees.length !== 1 ? 's' : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Section>

        <Section icon={Users} title="Leads" badge={data.leads.hot_leads.length + data.leads.needs_attention.length} defaultOpen={data.leads.needs_attention.length > 0}>
          {data.leads.hot_leads.length === 0 && data.leads.needs_attention.length === 0 ? (
            <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>No lead activity today.</p>
          ) : (
            <div className="space-y-1.5">
              {data.leads.needs_attention.map((l) => (
                <div key={l.id} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: 'var(--critical)' }} />
                  <span className="text-[11px] truncate" style={{ color: 'var(--text-primary)' }}>{l.name}</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{l.company}</span>
                </div>
              ))}
              {data.leads.hot_leads.map((l) => (
                <div key={l.id} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: 'var(--success)' }} />
                  <span className="text-[11px] truncate" style={{ color: 'var(--text-primary)' }}>{l.name}</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{l.company}</span>
                </div>
              ))}
            </div>
          )}
        </Section>

        <Section icon={TrendingUp} title="Signals" badge={totalSignals}>
          {totalSignals === 0 ? (
            <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>No new signals.</p>
          ) : (
            <div className="space-y-1.5">
              {[...data.signals.company_news, ...data.signals.market_trends, ...data.signals.competitive_intel].slice(0, 5).map((s) => (
                <div key={s.id}>
                  <p className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>{s.title}</p>
                  <p className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>{s.summary}</p>
                </div>
              ))}
            </div>
          )}
        </Section>

        <Section icon={AlertCircle} title="Tasks" badge={totalTasks} defaultOpen={data.tasks.overdue.length > 0}>
          {totalTasks === 0 ? (
            <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>No pending tasks.</p>
          ) : (
            <div className="space-y-1.5">
              {data.tasks.overdue.map((t) => (
                <div key={t.id} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: 'var(--critical)' }} />
                  <span className="text-[11px]" style={{ color: 'var(--text-primary)' }}>{t.title}</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--critical)' }}>overdue</span>
                </div>
              ))}
              {data.tasks.due_today.map((t) => (
                <div key={t.id} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: 'var(--warning)' }} />
                  <span className="text-[11px]" style={{ color: 'var(--text-primary)' }}>{t.title}</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>today</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
```

**Step 2: Register BriefingCard in RichContentRenderer**

In `frontend/src/components/rich/RichContentRenderer.tsx`, add the import and case:

Add import:
```tsx
import { BriefingCard, type BriefingCardData } from './BriefingCard';
```

Add case in the switch (before `default`):
```tsx
case 'briefing':
  return <BriefingCard data={item.data as unknown as BriefingCardData} />;
```

**Step 3: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors related to BriefingCard

**Step 4: Commit**

```bash
git add frontend/src/components/rich/BriefingCard.tsx frontend/src/components/rich/RichContentRenderer.tsx
git commit -m "feat(rich): add BriefingCard component for daily intelligence briefing"
```

---

### Task 2: Inject Daily Briefing into ARIA Workspace

**Files:**
- Modify: `frontend/src/components/pages/ARIAWorkspace.tsx:1-252`

**Step 1: Add briefing injection logic**

In `ARIAWorkspace.tsx`, add imports at the top (after existing imports):

```tsx
import { useTodayBriefing, useGenerateBriefing } from '@/hooks/useBriefing';
```

Inside the `ARIAWorkspace` component, after the existing refs (after line 33), add:

```tsx
const briefingInjectedRef = useRef(false);
const { data: briefing, isLoading: briefingLoading } = useTodayBriefing();
const generateBriefing = useGenerateBriefing();
```

Add a new `useEffect` after the "Load most recent conversation" useEffect (after line 79):

```tsx
// Inject daily briefing as ARIA's first message when available
useEffect(() => {
  if (briefingInjectedRef.current) return;
  if (briefingLoading) return;

  // If no briefing exists yet, generate one
  if (!briefing && !generateBriefing.isPending) {
    generateBriefing.mutate();
    return;
  }

  if (!briefing) return;

  briefingInjectedRef.current = true;

  const store = useConversationStore.getState();
  store.addMessage({
    role: 'aria',
    content: `Good morning. Here's your intelligence briefing for today.`,
    rich_content: [
      {
        type: 'briefing',
        data: briefing as unknown as Record<string, unknown>,
      },
    ],
    ui_commands: [],
    suggestions: ['Show me today\'s meetings', 'Any urgent signals?', 'Check pipeline health'],
  });

  store.setCurrentSuggestions(['Show me today\'s meetings', 'Any urgent signals?', 'Check pipeline health']);
}, [briefing, briefingLoading, generateBriefing]);
```

**Step 2: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Run dev server to verify visually**

Run: `cd frontend && npm run dev`
Verify: ARIA Workspace shows briefing as first message with expandable sections

**Step 4: Commit**

```bash
git add frontend/src/components/pages/ARIAWorkspace.tsx
git commit -m "feat(workspace): inject daily briefing as ARIA's first message"
```

---

### Task 3: Market Signals Feed on Intelligence Page

**Files:**
- Create: `frontend/src/components/intelligence/MarketSignalsFeed.tsx`
- Modify: `frontend/src/components/pages/IntelligencePage.tsx:147-169`
- Modify: `frontend/src/hooks/useIntelPanelData.ts` (add mutation hooks)

**Step 1: Add signal mutation hooks**

In `frontend/src/hooks/useIntelPanelData.ts`, add imports at the top (alongside existing signal imports):

```tsx
import { listSignals, markSignalRead, markAllRead, dismissSignal, getUnreadCount, type SignalFilters } from "@/api/signals";
```

Then add these hooks after the existing `useSignals` hook:

```tsx
// Signal mutation hooks (MarketSignalsFeed)
export function useUnreadSignalCount() {
  return useQuery({
    queryKey: [...intelKeys.all, "signalUnread"] as const,
    queryFn: () => getUnreadCount(),
    staleTime: 1000 * 60,
  });
}

export function useMarkSignalRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (signalId: string) => markSignalRead(signalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelKeys.all });
    },
  });
}

export function useMarkAllSignalsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelKeys.all });
    },
  });
}

export function useDismissSignal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (signalId: string) => dismissSignal(signalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelKeys.all });
    },
  });
}
```

**Step 2: Create MarketSignalsFeed component**

Create `frontend/src/components/intelligence/MarketSignalsFeed.tsx`:

```tsx
import { useState } from 'react';
import {
  DollarSign, Shield, FlaskConical, FileText, UserCog,
  TrendingUp, Handshake, Scale, Package, Users,
  Eye, EyeOff, X, CheckCheck,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import {
  useSignals,
  useUnreadSignalCount,
  useMarkSignalRead,
  useMarkAllSignalsRead,
  useDismissSignal,
} from '@/hooks/useIntelPanelData';
import { formatRelativeTime } from '@/hooks/useIntelPanelData';
import type { Signal } from '@/api/signals';

const SIGNAL_TYPE_CONFIG: Record<string, { icon: typeof DollarSign; color: string; label: string }> = {
  funding: { icon: DollarSign, color: '#22c55e', label: 'Funding' },
  fda_approval: { icon: Shield, color: '#3b82f6', label: 'FDA' },
  clinical_trial: { icon: FlaskConical, color: '#a855f7', label: 'Trial' },
  patent: { icon: FileText, color: '#f59e0b', label: 'Patent' },
  leadership: { icon: UserCog, color: '#64748b', label: 'Leadership' },
  earnings: { icon: TrendingUp, color: '#10b981', label: 'Earnings' },
  partnership: { icon: Handshake, color: '#6366f1', label: 'Partnership' },
  regulatory: { icon: Scale, color: '#f97316', label: 'Regulatory' },
  product: { icon: Package, color: '#06b6d4', label: 'Product' },
  hiring: { icon: Users, color: '#ec4899', label: 'Hiring' },
};

const ALL_TYPES = Object.keys(SIGNAL_TYPE_CONFIG);

function SignalItem({ signal, onRead, onDismiss }: {
  signal: Signal;
  onRead: () => void;
  onDismiss: () => void;
}) {
  const config = SIGNAL_TYPE_CONFIG[signal.signal_type] ?? {
    icon: TrendingUp,
    color: 'var(--text-secondary)',
    label: signal.signal_type,
  };
  const Icon = config.icon;
  const isUnread = !signal.read_at;

  return (
    <div
      className={cn(
        'border rounded-lg p-4 transition-all duration-200',
        'hover:border-[var(--accent)]/50 hover:shadow-sm'
      )}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
        borderLeftWidth: isUnread ? '3px' : '1px',
        borderLeftColor: isUnread ? config.color : 'var(--border)',
      }}
      data-aria-id={`signal-${signal.id}`}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: `${config.color}15` }}
        >
          <Icon size={16} style={{ color: config.color }} />
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            {signal.company_name && (
              <span
                className="font-medium text-sm"
                style={{ color: 'var(--text-primary)' }}
              >
                {signal.company_name}
              </span>
            )}
            <span
              className="font-mono text-[10px] px-1.5 py-0.5 rounded uppercase"
              style={{ color: config.color, backgroundColor: `${config.color}15` }}
            >
              {config.label}
            </span>
          </div>
          <p
            className="text-sm leading-relaxed"
            style={{
              color: 'var(--text-primary)',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {signal.content}
          </p>
          <div className="flex items-center gap-3 mt-2">
            {signal.source && (
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                {signal.source}
              </span>
            )}
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
              {formatRelativeTime(signal.created_at)}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {isUnread && (
            <button
              onClick={onRead}
              className="p-1.5 rounded transition-colors hover:bg-[var(--bg-subtle)]"
              style={{ color: 'var(--text-secondary)' }}
              title="Mark as read"
            >
              <Eye size={14} />
            </button>
          )}
          <button
            onClick={onDismiss}
            className="p-1.5 rounded transition-colors hover:bg-[var(--bg-subtle)]"
            style={{ color: 'var(--text-secondary)' }}
            title="Dismiss"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

export function MarketSignalsFeed() {
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);

  const { data: signals, isLoading } = useSignals({
    signal_type: typeFilter ?? undefined,
    unread_only: unreadOnly || undefined,
    limit: 50,
  });
  const { data: unreadCount } = useUnreadSignalCount();
  const markRead = useMarkSignalRead();
  const markAllRead = useMarkAllSignalsRead();
  const dismiss = useDismissSignal();

  const visibleSignals = (signals ?? []).filter((s) => !s.dismissed_at);

  if (isLoading) {
    return (
      <div className="space-y-3 animate-pulse">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="border border-[var(--border)] rounded-lg p-4" style={{ backgroundColor: 'var(--bg-elevated)' }}>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-[var(--border)]" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-32 bg-[var(--border)] rounded" />
                <div className="h-3 w-full bg-[var(--border)] rounded" />
                <div className="h-3 w-2/3 bg-[var(--border)] rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div>
      {/* Filter bar */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setTypeFilter(null)}
            className={cn(
              'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
              !typeFilter ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
            )}
            style={{ color: !typeFilter ? 'white' : 'var(--text-secondary)' }}
          >
            All
          </button>
          {ALL_TYPES.map((type) => {
            const config = SIGNAL_TYPE_CONFIG[type];
            return (
              <button
                key={type}
                onClick={() => setTypeFilter(typeFilter === type ? null : type)}
                className={cn(
                  'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                  typeFilter === type ? 'text-white' : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
                )}
                style={{
                  color: typeFilter === type ? 'white' : 'var(--text-secondary)',
                  backgroundColor: typeFilter === type ? config.color : undefined,
                }}
              >
                {config.label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setUnreadOnly(!unreadOnly)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
              unreadOnly ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
            )}
            style={{ color: unreadOnly ? 'white' : 'var(--text-secondary)' }}
          >
            {unreadOnly ? <EyeOff size={12} /> : <Eye size={12} />}
            Unread
          </button>
          {(unreadCount?.count ?? 0) > 0 && (
            <button
              onClick={() => markAllRead.mutate()}
              className="flex items-center gap-1.5 text-xs transition-colors hover:opacity-80"
              style={{ color: 'var(--accent)' }}
            >
              <CheckCheck size={12} />
              Mark all read
            </button>
          )}
        </div>
      </div>

      {/* Signal list */}
      {visibleSignals.length === 0 ? (
        <div
          className="text-center py-8 rounded-xl border"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <TrendingUp className="w-8 h-8 mx-auto mb-2 opacity-30" style={{ color: 'var(--text-secondary)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {unreadOnly ? 'No unread signals.' : 'No signals detected yet.'}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            ARIA monitors funding rounds, FDA approvals, trials, patents, and more.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {visibleSignals.map((signal) => (
            <SignalItem
              key={signal.id}
              signal={signal}
              onRead={() => markRead.mutate(signal.id)}
              onDismiss={() => dismiss.mutate(signal.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 3: Wire MarketSignalsFeed into IntelligencePage**

In `frontend/src/components/pages/IntelligencePage.tsx`:

Add import at top:
```tsx
import { MarketSignalsFeed } from '@/components/intelligence/MarketSignalsFeed';
import { useUnreadSignalCount } from '@/hooks/useIntelPanelData';
```

Inside the `IntelligenceOverview` component, add after the `useBattleCards` hook:
```tsx
const { data: unreadCount } = useUnreadSignalCount();
```

Replace the entire Market Signals section (lines 147-169) — the `<section>` block containing the EmptyState — with:

```tsx
<section>
  <h2
    className="text-base font-medium mb-4 flex items-center gap-2"
    style={{ color: 'var(--text-primary)' }}
  >
    <TrendingUp className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
    Market Signals
    {(unreadCount?.count ?? 0) > 0 && (
      <span
        className="px-2 py-0.5 rounded-full text-xs font-medium"
        style={{ backgroundColor: 'var(--accent)', color: 'white' }}
      >
        {unreadCount?.count} new
      </span>
    )}
  </h2>
  <MarketSignalsFeed />
</section>
```

**Step 4: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/components/intelligence/MarketSignalsFeed.tsx frontend/src/components/pages/IntelligencePage.tsx frontend/src/hooks/useIntelPanelData.ts
git commit -m "feat(intelligence): add market signals feed replacing empty state"
```

---

### Task 4: Upcoming Meetings Section on Actions Page

**Files:**
- Create: `frontend/src/components/actions/UpcomingMeetings.tsx`
- Modify: `frontend/src/components/pages/ActionsPage.tsx:11-12,402-403`

**Step 1: Create UpcomingMeetings component**

Create `frontend/src/components/actions/UpcomingMeetings.tsx`:

```tsx
import { useState } from 'react';
import {
  Calendar, ChevronDown, ChevronRight, Users, Loader2,
  FileText, AlertTriangle, Lightbulb, Settings,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useUpcomingMeetings, useMeetingBrief, useGenerateMeetingBrief } from '@/hooks/useMeetingBrief';
import type { UpcomingMeeting, MeetingBriefResponse } from '@/api/meetingBriefs';

// Format meeting time as readable string
function formatMeetingTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow = date.toDateString() === tomorrow.toDateString();

  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (isToday) return `Today ${time}`;
  if (isTomorrow) return `Tomorrow ${time}`;
  return `${date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })} ${time}`;
}

const STATUS_STYLES: Record<string, { label: string; color: string }> = {
  completed: { label: 'Ready', color: 'var(--success)' },
  generating: { label: 'Generating...', color: 'var(--accent)' },
  pending: { label: 'Pending', color: 'var(--warning)' },
  failed: { label: 'Failed', color: 'var(--critical)' },
};

function MeetingBriefContent({ brief }: { brief: MeetingBriefResponse }) {
  if (brief.status === 'generating' || brief.status === 'pending') {
    return (
      <div className="flex items-center gap-2 py-4">
        <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--accent)' }} />
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Generating research brief...
        </span>
      </div>
    );
  }

  if (brief.status === 'failed') {
    return (
      <div className="flex items-center gap-2 py-4">
        <AlertTriangle className="w-4 h-4" style={{ color: 'var(--critical)' }} />
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {brief.error_message ?? 'Brief generation failed.'}
        </span>
      </div>
    );
  }

  const content = brief.brief_content;
  if (!content || !('summary' in content)) return null;

  return (
    <div className="space-y-4 py-3">
      {/* Summary */}
      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>
        {content.summary}
      </p>

      {/* Attendees */}
      {content.attendees && content.attendees.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
            Attendees
          </p>
          <div className="space-y-2">
            {content.attendees.map((att, i) => (
              <div key={i} className="border rounded-lg p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                    {att.name ?? att.email}
                  </span>
                  {att.title && (
                    <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{att.title}</span>
                  )}
                </div>
                {att.background && (
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{att.background}</p>
                )}
                {att.talking_points.length > 0 && (
                  <div className="mt-2">
                    <p className="font-mono text-[10px] mb-1" style={{ color: 'var(--accent)' }}>Talking points:</p>
                    <ul className="space-y-0.5">
                      {att.talking_points.map((tp, j) => (
                        <li key={j} className="text-xs flex items-start gap-1.5" style={{ color: 'var(--text-primary)' }}>
                          <span className="w-1 h-1 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: 'var(--accent)' }} />
                          {tp}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Suggested Agenda */}
      {content.suggested_agenda && content.suggested_agenda.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
            <Lightbulb size={12} /> Suggested Agenda
          </p>
          <ol className="space-y-1">
            {content.suggested_agenda.map((item, i) => (
              <li key={i} className="text-xs flex items-start gap-2" style={{ color: 'var(--text-primary)' }}>
                <span className="font-mono text-[10px] mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }}>{i + 1}.</span>
                {item}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Risks & Opportunities */}
      {content.risks_opportunities && content.risks_opportunities.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
            <AlertTriangle size={12} /> Risks & Opportunities
          </p>
          <ul className="space-y-1">
            {content.risks_opportunities.map((item, i) => (
              <li key={i} className="text-xs flex items-start gap-1.5" style={{ color: 'var(--text-primary)' }}>
                <span className="w-1 h-1 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: 'var(--warning)' }} />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MeetingCard({ meeting }: { meeting: UpcomingMeeting }) {
  const [expanded, setExpanded] = useState(false);
  const { data: brief } = useMeetingBrief(expanded ? meeting.calendar_event_id : '');
  const generateBrief = useGenerateMeetingBrief();

  const statusInfo = meeting.brief_status
    ? STATUS_STYLES[meeting.brief_status] ?? STATUS_STYLES.pending
    : null;

  const handleGenerate = () => {
    generateBrief.mutate({
      calendarEventId: meeting.calendar_event_id,
      request: {
        meeting_title: meeting.meeting_title,
        meeting_time: meeting.meeting_time,
        attendee_emails: meeting.attendees,
      },
    });
  };

  return (
    <div
      className="border rounded-lg overflow-hidden"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 text-left cursor-pointer hover:bg-[var(--bg-subtle)] transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} style={{ color: 'var(--text-secondary)' }} />
        ) : (
          <ChevronRight size={14} style={{ color: 'var(--text-secondary)' }} />
        )}

        <span
          className="font-mono text-sm flex-shrink-0"
          style={{ color: 'var(--accent)' }}
        >
          {formatMeetingTime(meeting.meeting_time)}
        </span>

        <span
          className="font-medium text-sm truncate flex-1"
          style={{ color: 'var(--text-primary)' }}
        >
          {meeting.meeting_title ?? 'Untitled Meeting'}
        </span>

        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="flex items-center gap-1 font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
            <Users size={12} /> {meeting.attendees.length}
          </span>
          {statusInfo && (
            <span
              className="px-2 py-0.5 rounded-full font-mono text-[10px]"
              style={{ backgroundColor: `${statusInfo.color}20`, color: statusInfo.color }}
            >
              {statusInfo.label}
            </span>
          )}
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t px-4 pb-4" style={{ borderColor: 'var(--border)' }}>
          {brief ? (
            <MeetingBriefContent brief={brief} />
          ) : !meeting.brief_status ? (
            <div className="flex items-center justify-between py-4">
              <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                No research brief generated yet.
              </span>
              <button
                onClick={handleGenerate}
                disabled={generateBrief.isPending}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                  generateBrief.isPending && 'opacity-50 cursor-not-allowed'
                )}
                style={{ backgroundColor: 'var(--accent)', color: 'white' }}
              >
                {generateBrief.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <FileText className="w-4 h-4" />
                )}
                Generate Brief
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 py-4">
              <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--accent)' }} />
              <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>Loading brief...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function UpcomingMeetings() {
  const { data: meetings, isLoading } = useUpcomingMeetings(5);

  if (isLoading) {
    return (
      <section className="mb-8">
        <h2 className="font-sans text-sm font-medium mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          <Calendar className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          Upcoming Meetings
        </h2>
        <div className="space-y-3 animate-pulse">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="border border-[var(--border)] rounded-lg p-4" style={{ backgroundColor: 'var(--bg-elevated)' }}>
              <div className="flex items-center gap-3">
                <div className="h-4 w-4 bg-[var(--border)] rounded" />
                <div className="h-4 w-24 bg-[var(--border)] rounded" />
                <div className="h-4 w-48 bg-[var(--border)] rounded flex-1" />
              </div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (!meetings || meetings.length === 0) {
    return (
      <section className="mb-8">
        <h2 className="font-sans text-sm font-medium mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          <Calendar className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          Upcoming Meetings
        </h2>
        <div
          className="text-center py-6 rounded-lg border"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <Calendar className="w-6 h-6 mx-auto mb-2 opacity-30" style={{ color: 'var(--text-secondary)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>No upcoming meetings.</p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            Connect your calendar in{' '}
            <a href="/settings" className="underline" style={{ color: 'var(--accent)' }}>Settings</a>
            {' '}to see upcoming meetings with pre-meeting research.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="mb-8" data-aria-id="upcoming-meetings">
      <h2 className="font-sans text-sm font-medium mb-1 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
        <Calendar className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        Upcoming Meetings
      </h2>
      <p className="text-xs mb-4 ml-6" style={{ color: 'var(--text-secondary)' }}>
        Pre-meeting research from ARIA&apos;s Scout agent
      </p>
      <div className="space-y-3">
        {meetings.map((meeting) => (
          <MeetingCard key={meeting.calendar_event_id} meeting={meeting} />
        ))}
      </div>
    </section>
  );
}
```

**Step 2: Wire UpcomingMeetings into ActionsPage**

In `frontend/src/components/pages/ActionsPage.tsx`:

Add import at top (after existing imports):
```tsx
import { UpcomingMeetings } from '@/components/actions/UpcomingMeetings';
```

Insert `<UpcomingMeetings />` right before the "Active Goals" section. Find line 402 (just after the `</p>` closing the subtitle "Monitor goals..."):

```tsx
        {/* Upcoming Meetings Section */}
        <UpcomingMeetings />

        {/* Active Goals Section */}
```

This goes between the header `</div>` (after line 401) and the `<section className="mb-8">` for Active Goals (line 403).

**Step 3: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/actions/UpcomingMeetings.tsx frontend/src/components/pages/ActionsPage.tsx
git commit -m "feat(actions): add upcoming meetings section with expandable research briefs"
```

---

### Task 5: Draft Intelligence Context on DraftDetailPage

**Files:**
- Create: `frontend/src/components/communications/DraftIntelligenceContext.tsx`
- Modify: `frontend/src/components/pages/DraftDetailPage.tsx:146-150`

**Step 1: Create DraftIntelligenceContext component**

Create `frontend/src/components/communications/DraftIntelligenceContext.tsx`:

```tsx
import { useState } from 'react';
import { Zap, ChevronDown, ChevronRight, TrendingUp, Shield, Clock } from 'lucide-react';
import { useIntelligenceInsights, useSignals } from '@/hooks/useIntelPanelData';

interface DraftIntelligenceContextProps {
  leadId?: string;
  companyName?: string;
}

const CLASSIFICATION_COLORS: Record<string, string> = {
  opportunity: 'var(--success)',
  threat: 'var(--critical)',
  neutral: 'var(--text-secondary)',
};

const CLASSIFICATION_ICONS: Record<string, typeof TrendingUp> = {
  opportunity: TrendingUp,
  threat: Shield,
  neutral: Zap,
};

const HORIZON_LABELS: Record<string, string> = {
  immediate: 'Immediate',
  short_term: 'Short-term',
  medium_term: 'Medium-term',
  long_term: 'Long-term',
};

export function DraftIntelligenceContext({ leadId, companyName }: DraftIntelligenceContextProps) {
  const [expanded, setExpanded] = useState(false);

  const { data: insights } = useIntelligenceInsights({ limit: 5 });
  const { data: signals } = useSignals({
    company: companyName ?? undefined,
    limit: 5,
  });

  // Filter insights relevant to this lead/company
  const relevantInsights = (insights ?? []).filter((i) => {
    if (leadId && i.affected_goals?.length) return true;
    if (companyName && i.trigger_event?.toLowerCase().includes(companyName.toLowerCase())) return true;
    return false;
  }).slice(0, 3);

  const relevantSignals = (signals ?? []).filter((s) => !s.dismissed_at).slice(0, 3);

  const hasContent = relevantInsights.length > 0 || relevantSignals.length > 0;

  if (!hasContent) return null;

  return (
    <div
      className="border rounded-lg overflow-hidden mb-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="draft-intelligence-context"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left cursor-pointer hover:bg-[var(--bg-subtle)] transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} style={{ color: 'var(--text-secondary)' }} />
        ) : (
          <ChevronRight size={14} style={{ color: 'var(--text-secondary)' }} />
        )}
        <Zap size={14} style={{ color: 'var(--accent)' }} />
        <span className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Intelligence Context
        </span>
        <span className="font-mono text-[10px] ml-auto" style={{ color: 'var(--text-secondary)' }}>
          {relevantInsights.length + relevantSignals.length} items
        </span>
      </button>

      {expanded && (
        <div className="border-t px-4 py-3 space-y-4" style={{ borderColor: 'var(--border)' }}>
          {/* Insights */}
          {relevantInsights.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Jarvis Insights
              </p>
              <div className="space-y-2">
                {relevantInsights.map((insight) => {
                  const color = CLASSIFICATION_COLORS[insight.classification] ?? CLASSIFICATION_COLORS.neutral;
                  const Icon = CLASSIFICATION_ICONS[insight.classification] ?? Zap;
                  return (
                    <div
                      key={insight.id}
                      className="rounded-lg border p-3"
                      style={{
                        borderColor: 'var(--border)',
                        backgroundColor: 'var(--bg-subtle)',
                        borderLeftWidth: '3px',
                        borderLeftColor: color,
                      }}
                    >
                      <div className="flex items-start gap-2">
                        <Icon size={12} className="mt-0.5 flex-shrink-0" style={{ color }} />
                        <div className="min-w-0 flex-1">
                          <span className="font-mono text-[10px] uppercase font-medium" style={{ color }}>
                            {insight.classification}
                          </span>
                          <p
                            className="text-[12px] leading-[1.5] mt-0.5"
                            style={{
                              color: 'var(--text-primary)',
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden',
                            }}
                          >
                            {insight.content}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            {insight.time_horizon && (
                              <span className="flex items-center gap-0.5">
                                <Clock size={10} style={{ color: 'var(--text-secondary)' }} />
                                <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                                  {HORIZON_LABELS[insight.time_horizon] ?? insight.time_horizon}
                                </span>
                              </span>
                            )}
                            <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                              {(insight.confidence * 100).toFixed(0)}% conf
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Signals */}
          {relevantSignals.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Market Signals {companyName ? `\u2014 ${companyName}` : ''}
              </p>
              <div className="space-y-2">
                {relevantSignals.map((signal) => (
                  <div
                    key={signal.id}
                    className="rounded-lg border p-3"
                    style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
                  >
                    <div className="flex items-start gap-2">
                      <TrendingUp size={12} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
                      <div className="min-w-0">
                        <span className="font-mono text-[10px] uppercase" style={{ color: 'var(--accent)' }}>
                          {signal.signal_type.replace('_', ' ')}
                        </span>
                        <p
                          className="text-[12px] leading-[1.5] mt-0.5"
                          style={{
                            color: 'var(--text-primary)',
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}
                        >
                          {signal.content}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Wire into DraftDetailPage**

In `frontend/src/components/pages/DraftDetailPage.tsx`:

Add import at top:
```tsx
import { DraftIntelligenceContext } from '@/components/communications/DraftIntelligenceContext';
```

Insert the component right after the breadcrumb navigation (line 160, after `</button>` for "Drafts" breadcrumb) and before the Header section. Find the closing `</button>` for the breadcrumb (line ~160), and insert after it:

```tsx
        {/* Intelligence Context */}
        <DraftIntelligenceContext
          leadId={draft.lead_memory_id}
          companyName={draft.recipient_name?.split(' ').pop()}
        />
```

This goes between the breadcrumb `</button>` and the `{/* Header */}` comment.

**Step 3: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/communications/DraftIntelligenceContext.tsx frontend/src/components/pages/DraftDetailPage.tsx
git commit -m "feat(communications): add intelligence context to draft detail page"
```

---

### Task 6: Final Verification

**Step 1: Run full typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: Zero errors

**Step 2: Run linter**

Run: `cd frontend && npm run lint`
Expected: No new errors from our changes

**Step 3: Run build**

Run: `cd frontend && npm run build`
Expected: Successful build

**Step 4: Commit any fixes needed**

If typecheck/lint/build revealed issues, fix them and commit:
```bash
git add -A
git commit -m "fix: address typecheck and lint issues in Jarvis frontend integration"
```

**Step 5: Push all commits**

```bash
git push origin main
```
