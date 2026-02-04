# Lead Detail View (US-509) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a premium lead detail page at `/dashboard/leads/{id}` with timeline, stakeholders, insights, and activity tabs following Apple-inspired luxury dark theme aesthetics.

**Architecture:** Single-page component with tab navigation, React Query for data fetching, and modal components for edit/add actions. API layer extensions for timeline, stakeholders, insights, and stage transitions. Design matches existing LeadsPage dark theme with refined typography and subtle animations.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, React Query, React Router, Lucide icons

---

## Task 1: Extend API Client with Lead Detail Endpoints

**Files:**
- Modify: `frontend/src/api/leads.ts`

**Step 1: Write the new type definitions**

Add after line 68 (after `ExportResult` interface):

```typescript
// Stakeholder types
export type StakeholderRole = "decision_maker" | "influencer" | "champion" | "blocker" | "user";
export type Sentiment = "positive" | "neutral" | "negative" | "unknown";

export interface Stakeholder {
  id: string;
  lead_memory_id: string;
  contact_email: string;
  contact_name: string | null;
  title: string | null;
  role: StakeholderRole | null;
  influence_level: number;
  sentiment: Sentiment;
  last_contacted_at: string | null;
  notes: string | null;
  created_at: string;
}

export interface StakeholderCreate {
  contact_email: string;
  contact_name?: string;
  title?: string;
  role?: StakeholderRole;
  influence_level?: number;
  sentiment?: Sentiment;
  notes?: string;
}

export interface StakeholderUpdate {
  contact_name?: string;
  title?: string;
  role?: StakeholderRole;
  influence_level?: number;
  sentiment?: Sentiment;
  notes?: string;
}

// Insight types
export type InsightType = "objection" | "buying_signal" | "commitment" | "risk" | "opportunity";

export interface Insight {
  id: string;
  lead_memory_id: string;
  insight_type: InsightType;
  content: string;
  confidence: number;
  source_event_id: string | null;
  detected_at: string;
  addressed_at: string | null;
}

// Stage transition
export interface StageTransition {
  new_stage: LifecycleStage;
  reason?: string;
}
```

**Step 2: Write the API functions**

Add after `downloadCsv` function:

```typescript
// Get lead timeline (events)
export async function getLeadTimeline(leadId: string): Promise<LeadEvent[]> {
  const response = await apiClient.get<LeadEvent[]>(`/leads/${leadId}/timeline`);
  return response.data;
}

// Add event to lead
export async function addLeadEvent(
  leadId: string,
  event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">
): Promise<LeadEvent> {
  const response = await apiClient.post<LeadEvent>(`/leads/${leadId}/events`, event);
  return response.data;
}

// Get lead stakeholders
export async function getLeadStakeholders(leadId: string): Promise<Stakeholder[]> {
  const response = await apiClient.get<Stakeholder[]>(`/leads/${leadId}/stakeholders`);
  return response.data;
}

// Add stakeholder
export async function addStakeholder(
  leadId: string,
  stakeholder: StakeholderCreate
): Promise<Stakeholder> {
  const response = await apiClient.post<Stakeholder>(
    `/leads/${leadId}/stakeholders`,
    stakeholder
  );
  return response.data;
}

// Update stakeholder
export async function updateStakeholder(
  leadId: string,
  stakeholderId: string,
  updates: StakeholderUpdate
): Promise<Stakeholder> {
  const response = await apiClient.patch<Stakeholder>(
    `/leads/${leadId}/stakeholders/${stakeholderId}`,
    updates
  );
  return response.data;
}

// Get lead insights
export async function getLeadInsights(leadId: string): Promise<Insight[]> {
  const response = await apiClient.get<Insight[]>(`/leads/${leadId}/insights`);
  return response.data;
}

// Transition lead stage
export async function transitionLeadStage(
  leadId: string,
  transition: StageTransition
): Promise<Lead> {
  const response = await apiClient.post<Lead>(`/leads/${leadId}/transition`, transition);
  return response.data;
}
```

**Step 3: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors related to leads.ts

**Step 4: Commit**

```bash
git add frontend/src/api/leads.ts
git commit -m "feat(leads): add API functions for lead detail view

- Add types for stakeholders, insights, stage transitions
- Add timeline, stakeholders, insights API functions
- Add stage transition endpoint

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Extend useLeads Hook with Detail Queries

**Files:**
- Modify: `frontend/src/hooks/useLeads.ts`

**Step 1: Add imports for new API functions**

Update the import statement to include new functions:

```typescript
import {
  addNote,
  addLeadEvent,
  addStakeholder,
  downloadCsv,
  exportLeads,
  getLead,
  getLeadInsights,
  getLeadStakeholders,
  getLeadTimeline,
  listLeads,
  transitionLeadStage,
  updateStakeholder,
  type Insight,
  type Lead,
  type LeadEvent,
  type LeadFilters,
  type NoteCreate,
  type Stakeholder,
  type StakeholderCreate,
  type StakeholderUpdate,
  type StageTransition,
} from "@/api/leads";
```

**Step 2: Add query key factories**

Update `leadKeys` object:

```typescript
export const leadKeys = {
  all: ["leads"] as const,
  lists: () => [...leadKeys.all, "list"] as const,
  list: (filters?: LeadFilters) => [...leadKeys.lists(), { filters }] as const,
  details: () => [...leadKeys.all, "detail"] as const,
  detail: (id: string) => [...leadKeys.details(), id] as const,
  timeline: (id: string) => [...leadKeys.detail(id), "timeline"] as const,
  stakeholders: (id: string) => [...leadKeys.detail(id), "stakeholders"] as const,
  insights: (id: string) => [...leadKeys.detail(id), "insights"] as const,
};
```

**Step 3: Add new query hooks**

Add after `useLead` hook:

```typescript
// Lead timeline query
export function useLeadTimeline(leadId: string) {
  return useQuery({
    queryKey: leadKeys.timeline(leadId),
    queryFn: () => getLeadTimeline(leadId),
    enabled: !!leadId,
  });
}

// Lead stakeholders query
export function useLeadStakeholders(leadId: string) {
  return useQuery({
    queryKey: leadKeys.stakeholders(leadId),
    queryFn: () => getLeadStakeholders(leadId),
    enabled: !!leadId,
  });
}

// Lead insights query
export function useLeadInsights(leadId: string) {
  return useQuery({
    queryKey: leadKeys.insights(leadId),
    queryFn: () => getLeadInsights(leadId),
    enabled: !!leadId,
  });
}
```

**Step 4: Add mutation hooks**

Add after the query hooks:

```typescript
// Add event mutation
export function useAddEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      event,
    }: {
      leadId: string;
      event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">;
    }) => addLeadEvent(leadId, event),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.timeline(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
    },
  });
}

// Add stakeholder mutation
export function useAddStakeholder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      stakeholder,
    }: {
      leadId: string;
      stakeholder: StakeholderCreate;
    }) => addStakeholder(leadId, stakeholder),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.stakeholders(leadId) });
    },
  });
}

// Update stakeholder mutation
export function useUpdateStakeholder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      stakeholderId,
      updates,
    }: {
      leadId: string;
      stakeholderId: string;
      updates: StakeholderUpdate;
    }) => updateStakeholder(leadId, stakeholderId, updates),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.stakeholders(leadId) });
    },
  });
}

// Transition stage mutation
export function useTransitionStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      transition,
    }: {
      leadId: string;
      transition: StageTransition;
    }) => transitionLeadStage(leadId, transition),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}
```

**Step 5: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 6: Commit**

```bash
git add frontend/src/hooks/useLeads.ts
git commit -m "feat(leads): add React Query hooks for lead detail

- Add timeline, stakeholders, insights query hooks
- Add mutation hooks for events, stakeholders, stage transitions
- Extend query key factory for cache management

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create Shared UI Components for Lead Detail

**Files:**
- Create: `frontend/src/components/leads/HealthScoreBadge.tsx`
- Create: `frontend/src/components/leads/StagePill.tsx`
- Create: `frontend/src/components/leads/StatusIndicator.tsx`

**Step 1: Create HealthScoreBadge component**

```typescript
// frontend/src/components/leads/HealthScoreBadge.tsx
interface HealthScoreBadgeProps {
  score: number;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export function HealthScoreBadge({ score, size = "md", showLabel = true }: HealthScoreBadgeProps) {
  const getHealthConfig = (score: number) => {
    if (score >= 70) {
      return {
        indicator: "bg-emerald-500",
        bg: "bg-emerald-500/10",
        border: "border-emerald-500/20",
        text: "text-emerald-400",
        glow: "shadow-emerald-500/20",
        label: "Healthy",
      };
    }
    if (score >= 40) {
      return {
        indicator: "bg-amber-500",
        bg: "bg-amber-500/10",
        border: "border-amber-500/20",
        text: "text-amber-400",
        glow: "shadow-amber-500/20",
        label: "Attention",
      };
    }
    return {
      indicator: "bg-red-500",
      bg: "bg-red-500/10",
      border: "border-red-500/20",
      text: "text-red-400",
      glow: "shadow-red-500/20",
      label: "At Risk",
    };
  };

  const config = getHealthConfig(score);

  const sizeClasses = {
    sm: {
      container: "px-2 py-0.5 gap-1",
      indicator: "w-1.5 h-1.5",
      score: "text-xs",
      label: "text-[10px]",
    },
    md: {
      container: "px-2.5 py-1 gap-1.5",
      indicator: "w-2 h-2",
      score: "text-sm",
      label: "text-xs",
    },
    lg: {
      container: "px-3 py-1.5 gap-2",
      indicator: "w-2.5 h-2.5",
      score: "text-base",
      label: "text-xs",
    },
  };

  const s = sizeClasses[size];

  return (
    <div
      className={`inline-flex items-center ${s.container} rounded-full ${config.bg} ${config.border} border shadow-sm ${config.glow}`}
    >
      <span className={`${s.indicator} rounded-full ${config.indicator} animate-pulse`} />
      <span className={`font-semibold ${s.score} ${config.text}`}>{score}</span>
      {showLabel && (
        <span className={`${s.label} ${config.text} opacity-80`}>{config.label}</span>
      )}
    </div>
  );
}
```

**Step 2: Create StagePill component**

```typescript
// frontend/src/components/leads/StagePill.tsx
import type { LifecycleStage } from "@/api/leads";

interface StagePillProps {
  stage: LifecycleStage;
  size?: "sm" | "md" | "lg";
}

export function StagePill({ stage, size = "md" }: StagePillProps) {
  const stageConfig: Record<LifecycleStage, { bg: string; text: string; border: string }> = {
    lead: {
      bg: "bg-slate-500/10",
      text: "text-slate-300",
      border: "border-slate-500/20",
    },
    opportunity: {
      bg: "bg-primary-500/10",
      text: "text-primary-400",
      border: "border-primary-500/20",
    },
    account: {
      bg: "bg-accent-500/10",
      text: "text-accent-400",
      border: "border-accent-500/20",
    },
  };

  const config = stageConfig[stage];

  const sizeClasses = {
    sm: "px-2 py-0.5 text-[10px]",
    md: "px-2.5 py-1 text-xs",
    lg: "px-3 py-1.5 text-sm",
  };

  return (
    <span
      className={`inline-flex items-center ${sizeClasses[size]} rounded-full font-medium capitalize ${config.bg} ${config.text} ${config.border} border`}
    >
      {stage}
    </span>
  );
}
```

**Step 3: Create StatusIndicator component**

```typescript
// frontend/src/components/leads/StatusIndicator.tsx
import type { LeadStatus } from "@/api/leads";

interface StatusIndicatorProps {
  status: LeadStatus;
  showLabel?: boolean;
}

export function StatusIndicator({ status, showLabel = true }: StatusIndicatorProps) {
  const statusConfig: Record<LeadStatus, { color: string; label: string }> = {
    active: { color: "text-emerald-400", label: "Active" },
    won: { color: "text-primary-400", label: "Won" },
    lost: { color: "text-red-400", label: "Lost" },
    dormant: { color: "text-slate-500", label: "Dormant" },
  };

  const config = statusConfig[status];

  return (
    <span className={`text-xs font-medium capitalize ${config.color}`}>
      {showLabel ? config.label : status}
    </span>
  );
}
```

**Step 4: Update barrel export**

Update `frontend/src/components/leads/index.ts`:

```typescript
export { AddNoteModal } from "./AddNoteModal";
export { EmptyLeads } from "./EmptyLeads";
export { HealthScoreBadge } from "./HealthScoreBadge";
export { LeadCard } from "./LeadCard";
export { LeadsSkeleton } from "./LeadsSkeleton";
export { LeadTableRow } from "./LeadTableRow";
export { StagePill } from "./StagePill";
export { StatusIndicator } from "./StatusIndicator";
```

**Step 5: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 6: Commit**

```bash
git add frontend/src/components/leads/HealthScoreBadge.tsx frontend/src/components/leads/StagePill.tsx frontend/src/components/leads/StatusIndicator.tsx frontend/src/components/leads/index.ts
git commit -m "feat(leads): add shared UI components for lead detail

- HealthScoreBadge with size variants and glow effect
- StagePill with lifecycle stage styling
- StatusIndicator for lead status display

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Timeline Tab Component

**Files:**
- Create: `frontend/src/components/leads/detail/TimelineTab.tsx`

**Step 1: Create TimelineTab component**

```typescript
// frontend/src/components/leads/detail/TimelineTab.tsx
import {
  Calendar,
  Mail,
  MailOpen,
  MessageSquare,
  Phone,
  Signal,
  Video,
} from "lucide-react";
import type { LeadEvent, EventType } from "@/api/leads";

interface TimelineTabProps {
  events: LeadEvent[];
  isLoading: boolean;
}

const eventIcons: Record<EventType, React.ReactNode> = {
  email_sent: <Mail className="w-4 h-4" />,
  email_received: <MailOpen className="w-4 h-4" />,
  meeting: <Video className="w-4 h-4" />,
  call: <Phone className="w-4 h-4" />,
  note: <MessageSquare className="w-4 h-4" />,
  signal: <Signal className="w-4 h-4" />,
};

const eventColors: Record<EventType, { bg: string; icon: string; line: string }> = {
  email_sent: {
    bg: "bg-blue-500/10",
    icon: "text-blue-400",
    line: "bg-blue-500/30",
  },
  email_received: {
    bg: "bg-cyan-500/10",
    icon: "text-cyan-400",
    line: "bg-cyan-500/30",
  },
  meeting: {
    bg: "bg-violet-500/10",
    icon: "text-violet-400",
    line: "bg-violet-500/30",
  },
  call: {
    bg: "bg-emerald-500/10",
    icon: "text-emerald-400",
    line: "bg-emerald-500/30",
  },
  note: {
    bg: "bg-amber-500/10",
    icon: "text-amber-400",
    line: "bg-amber-500/30",
  },
  signal: {
    bg: "bg-rose-500/10",
    icon: "text-rose-400",
    line: "bg-rose-500/30",
  },
};

function TimelineEvent({ event, isLast }: { event: LeadEvent; isLast: boolean }) {
  const colors = eventColors[event.event_type];
  const icon = eventIcons[event.event_type];

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  };

  const getEventLabel = (type: EventType, direction: string | null) => {
    const labels: Record<EventType, string> = {
      email_sent: "Email Sent",
      email_received: "Email Received",
      meeting: "Meeting",
      call: "Call",
      note: "Note",
      signal: "Signal Detected",
    };
    return labels[type];
  };

  return (
    <div className="relative flex gap-4 pb-8 group">
      {/* Timeline line */}
      {!isLast && (
        <div
          className={`absolute left-5 top-10 w-0.5 h-[calc(100%-24px)] ${colors.line}`}
        />
      )}

      {/* Icon */}
      <div
        className={`relative z-10 flex-shrink-0 w-10 h-10 rounded-xl ${colors.bg} flex items-center justify-center ${colors.icon} transition-transform group-hover:scale-110`}
      >
        {icon}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-4 mb-1">
          <div>
            <h4 className="text-sm font-medium text-white">
              {getEventLabel(event.event_type, event.direction)}
            </h4>
            {event.subject && (
              <p className="text-sm text-slate-400 mt-0.5 truncate">
                {event.subject}
              </p>
            )}
          </div>
          <div className="flex-shrink-0 text-right">
            <p className="text-xs text-slate-500">{formatDate(event.occurred_at)}</p>
            <p className="text-xs text-slate-600">{formatTime(event.occurred_at)}</p>
          </div>
        </div>

        {event.content && (
          <div className="mt-2 p-3 bg-slate-800/40 rounded-lg border border-slate-700/30">
            <p className="text-sm text-slate-300 whitespace-pre-wrap line-clamp-3">
              {event.content}
            </p>
          </div>
        )}

        {event.participants.length > 0 && (
          <div className="flex items-center gap-1.5 mt-2">
            <span className="text-xs text-slate-500">with</span>
            <div className="flex flex-wrap gap-1">
              {event.participants.slice(0, 3).map((participant, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 text-xs bg-slate-700/50 rounded-full text-slate-400"
                >
                  {participant}
                </span>
              ))}
              {event.participants.length > 3 && (
                <span className="px-2 py-0.5 text-xs bg-slate-700/50 rounded-full text-slate-500">
                  +{event.participants.length - 3}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TimelineSkeleton() {
  return (
    <div className="space-y-6">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex gap-4 animate-pulse">
          <div className="w-10 h-10 rounded-xl bg-slate-700/50" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-32 bg-slate-700/50 rounded" />
            <div className="h-3 w-48 bg-slate-700/30 rounded" />
            <div className="h-16 w-full bg-slate-800/40 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyTimeline() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-800/50 flex items-center justify-center mb-4">
        <Calendar className="w-8 h-8 text-slate-600" />
      </div>
      <h3 className="text-lg font-medium text-slate-400 mb-1">No activity yet</h3>
      <p className="text-sm text-slate-500 max-w-xs">
        Events will appear here as you interact with this lead
      </p>
    </div>
  );
}

export function TimelineTab({ events, isLoading }: TimelineTabProps) {
  if (isLoading) {
    return <TimelineSkeleton />;
  }

  if (events.length === 0) {
    return <EmptyTimeline />;
  }

  return (
    <div className="space-y-0">
      {events.map((event, idx) => (
        <TimelineEvent
          key={event.id}
          event={event}
          isLast={idx === events.length - 1}
        />
      ))}
    </div>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/TimelineTab.tsx
git commit -m "feat(leads): add TimelineTab component for lead detail

- Chronological event display with color-coded icons
- Support for all event types (email, meeting, call, note, signal)
- Loading skeleton and empty state
- Participant badges and content preview

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create Stakeholders Tab Component

**Files:**
- Create: `frontend/src/components/leads/detail/StakeholdersTab.tsx`

**Step 1: Create StakeholdersTab component**

```typescript
// frontend/src/components/leads/detail/StakeholdersTab.tsx
import { Mail, Pencil, User, Users } from "lucide-react";
import type { Stakeholder, Sentiment, StakeholderRole } from "@/api/leads";

interface StakeholdersTabProps {
  stakeholders: Stakeholder[];
  isLoading: boolean;
  onEdit: (stakeholder: Stakeholder) => void;
}

const roleConfig: Record<StakeholderRole, { label: string; color: string }> = {
  decision_maker: { label: "Decision Maker", color: "text-violet-400 bg-violet-500/10" },
  influencer: { label: "Influencer", color: "text-blue-400 bg-blue-500/10" },
  champion: { label: "Champion", color: "text-emerald-400 bg-emerald-500/10" },
  blocker: { label: "Blocker", color: "text-red-400 bg-red-500/10" },
  user: { label: "User", color: "text-slate-400 bg-slate-500/10" },
};

const sentimentConfig: Record<Sentiment, { label: string; color: string; bg: string }> = {
  positive: { label: "Positive", color: "text-emerald-400", bg: "bg-emerald-500" },
  neutral: { label: "Neutral", color: "text-slate-400", bg: "bg-slate-500" },
  negative: { label: "Negative", color: "text-red-400", bg: "bg-red-500" },
  unknown: { label: "Unknown", color: "text-slate-500", bg: "bg-slate-600" },
};

function StakeholderCard({
  stakeholder,
  onEdit,
}: {
  stakeholder: Stakeholder;
  onEdit: () => void;
}) {
  const role = stakeholder.role ? roleConfig[stakeholder.role] : null;
  const sentiment = sentimentConfig[stakeholder.sentiment];

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Never";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div className="group relative bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 hover:bg-slate-800/60 hover:border-slate-600/50 transition-all duration-200">
      {/* Edit button */}
      <button
        onClick={onEdit}
        className="absolute top-4 right-4 p-2 rounded-lg bg-slate-700/50 text-slate-400 opacity-0 group-hover:opacity-100 hover:bg-primary-500/20 hover:text-primary-400 transition-all"
        title="Edit stakeholder"
      >
        <Pencil className="w-4 h-4" />
      </button>

      {/* Header */}
      <div className="flex items-start gap-4 mb-4">
        <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-slate-700 to-slate-800 rounded-xl flex items-center justify-center border border-slate-600/50">
          <User className="w-6 h-6 text-slate-400" />
        </div>
        <div className="flex-1 min-w-0 pr-8">
          <h4 className="text-base font-semibold text-white truncate">
            {stakeholder.contact_name || stakeholder.contact_email.split("@")[0]}
          </h4>
          {stakeholder.title && (
            <p className="text-sm text-slate-400 truncate">{stakeholder.title}</p>
          )}
        </div>
      </div>

      {/* Email */}
      <div className="flex items-center gap-2 mb-3 text-sm text-slate-400">
        <Mail className="w-4 h-4 text-slate-500" />
        <span className="truncate">{stakeholder.contact_email}</span>
      </div>

      {/* Role & Sentiment */}
      <div className="flex items-center gap-2 mb-3">
        {role && (
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${role.color}`}>
            {role.label}
          </span>
        )}
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${sentiment.bg}`} />
          <span className={`text-xs ${sentiment.color}`}>{sentiment.label}</span>
        </div>
      </div>

      {/* Influence level */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-slate-500">Influence</span>
          <span className="text-slate-400">{stakeholder.influence_level}/10</span>
        </div>
        <div className="h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary-600 to-primary-400 rounded-full transition-all"
            style={{ width: `${stakeholder.influence_level * 10}%` }}
          />
        </div>
      </div>

      {/* Last contacted */}
      <div className="pt-3 border-t border-slate-700/50 text-xs text-slate-500">
        Last contacted: {formatDate(stakeholder.last_contacted_at)}
      </div>

      {/* Notes */}
      {stakeholder.notes && (
        <div className="mt-3 pt-3 border-t border-slate-700/50">
          <p className="text-xs text-slate-400 line-clamp-2">{stakeholder.notes}</p>
        </div>
      )}
    </div>
  );
}

function StakeholdersSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {[1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 animate-pulse"
        >
          <div className="flex items-start gap-4 mb-4">
            <div className="w-12 h-12 rounded-xl bg-slate-700/50" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-32 bg-slate-700/50 rounded" />
              <div className="h-3 w-24 bg-slate-700/30 rounded" />
            </div>
          </div>
          <div className="h-3 w-48 bg-slate-700/30 rounded mb-3" />
          <div className="flex gap-2 mb-3">
            <div className="h-5 w-20 bg-slate-700/30 rounded" />
            <div className="h-5 w-16 bg-slate-700/30 rounded" />
          </div>
          <div className="h-1.5 w-full bg-slate-700/50 rounded-full" />
        </div>
      ))}
    </div>
  );
}

function EmptyStakeholders() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-800/50 flex items-center justify-center mb-4">
        <Users className="w-8 h-8 text-slate-600" />
      </div>
      <h3 className="text-lg font-medium text-slate-400 mb-1">No stakeholders yet</h3>
      <p className="text-sm text-slate-500 max-w-xs">
        Add stakeholders to track key contacts and their influence
      </p>
    </div>
  );
}

export function StakeholdersTab({ stakeholders, isLoading, onEdit }: StakeholdersTabProps) {
  if (isLoading) {
    return <StakeholdersSkeleton />;
  }

  if (stakeholders.length === 0) {
    return <EmptyStakeholders />;
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {stakeholders.map((stakeholder) => (
        <StakeholderCard
          key={stakeholder.id}
          stakeholder={stakeholder}
          onEdit={() => onEdit(stakeholder)}
        />
      ))}
    </div>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/StakeholdersTab.tsx
git commit -m "feat(leads): add StakeholdersTab component for lead detail

- Contact cards with role and sentiment indicators
- Influence level progress bar
- Edit button with hover reveal
- Loading skeleton and empty state

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create Insights Tab Component

**Files:**
- Create: `frontend/src/components/leads/detail/InsightsTab.tsx`

**Step 1: Create InsightsTab component**

```typescript
// frontend/src/components/leads/detail/InsightsTab.tsx
import {
  AlertTriangle,
  CheckCircle2,
  Lightbulb,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import type { Insight, InsightType } from "@/api/leads";

interface InsightsTabProps {
  insights: Insight[];
  isLoading: boolean;
}

const insightConfig: Record<
  InsightType,
  { label: string; icon: React.ReactNode; color: string; bg: string }
> = {
  objection: {
    label: "Objections",
    icon: <AlertTriangle className="w-5 h-5" />,
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/20",
  },
  buying_signal: {
    label: "Buying Signals",
    icon: <TrendingUp className="w-5 h-5" />,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/20",
  },
  commitment: {
    label: "Commitments",
    icon: <CheckCircle2 className="w-5 h-5" />,
    color: "text-primary-400",
    bg: "bg-primary-500/10 border-primary-500/20",
  },
  risk: {
    label: "Risks",
    icon: <ShieldAlert className="w-5 h-5" />,
    color: "text-red-400",
    bg: "bg-red-500/10 border-red-500/20",
  },
  opportunity: {
    label: "Opportunities",
    icon: <Sparkles className="w-5 h-5" />,
    color: "text-violet-400",
    bg: "bg-violet-500/10 border-violet-500/20",
  },
};

function InsightCard({ insight }: { insight: Insight }) {
  const config = insightConfig[insight.insight_type];

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div
      className={`p-4 rounded-xl border ${config.bg} transition-all duration-200 hover:scale-[1.02]`}
    >
      <div className="flex items-start gap-3">
        <div className={`flex-shrink-0 ${config.color}`}>{config.icon}</div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white leading-relaxed">{insight.content}</p>
          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs text-slate-500">
              {formatDate(insight.detected_at)}
            </span>
            <span className="text-xs text-slate-600">
              {Math.round(insight.confidence * 100)}% confidence
            </span>
            {insight.addressed_at && (
              <span className="text-xs text-emerald-400/70">Addressed</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function InsightGroup({
  type,
  insights,
}: {
  type: InsightType;
  insights: Insight[];
}) {
  const config = insightConfig[type];

  if (insights.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className={config.color}>{config.icon}</span>
        <h3 className="text-sm font-semibold text-white">{config.label}</h3>
        <span className="px-1.5 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400">
          {insights.length}
        </span>
      </div>
      <div className="space-y-2">
        {insights.map((insight) => (
          <InsightCard key={insight.id} insight={insight} />
        ))}
      </div>
    </div>
  );
}

function InsightsSkeleton() {
  return (
    <div className="space-y-6">
      {[1, 2, 3].map((i) => (
        <div key={i} className="space-y-3 animate-pulse">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-slate-700/50" />
            <div className="h-4 w-24 bg-slate-700/50 rounded" />
          </div>
          <div className="space-y-2">
            {[1, 2].map((j) => (
              <div
                key={j}
                className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/30"
              >
                <div className="h-4 w-full bg-slate-700/30 rounded mb-2" />
                <div className="h-3 w-3/4 bg-slate-700/20 rounded" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyInsights() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-800/50 flex items-center justify-center mb-4">
        <Lightbulb className="w-8 h-8 text-slate-600" />
      </div>
      <h3 className="text-lg font-medium text-slate-400 mb-1">No insights yet</h3>
      <p className="text-sm text-slate-500 max-w-xs">
        ARIA will detect objections, signals, and commitments as interactions occur
      </p>
    </div>
  );
}

export function InsightsTab({ insights, isLoading }: InsightsTabProps) {
  if (isLoading) {
    return <InsightsSkeleton />;
  }

  if (insights.length === 0) {
    return <EmptyInsights />;
  }

  // Group insights by type
  const groupedInsights = insights.reduce(
    (acc, insight) => {
      if (!acc[insight.insight_type]) {
        acc[insight.insight_type] = [];
      }
      acc[insight.insight_type].push(insight);
      return acc;
    },
    {} as Record<InsightType, Insight[]>
  );

  // Order: objections, risks, buying_signals, commitments, opportunities
  const orderedTypes: InsightType[] = [
    "objection",
    "risk",
    "buying_signal",
    "commitment",
    "opportunity",
  ];

  return (
    <div className="space-y-8">
      {orderedTypes.map((type) => (
        <InsightGroup
          key={type}
          type={type}
          insights={groupedInsights[type] || []}
        />
      ))}
    </div>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/InsightsTab.tsx
git commit -m "feat(leads): add InsightsTab component for lead detail

- Group insights by type (objections, signals, commitments, risks, opportunities)
- Color-coded cards with confidence indicator
- Addressed status badge
- Loading skeleton and empty state

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Create Activity Tab Component

**Files:**
- Create: `frontend/src/components/leads/detail/ActivityTab.tsx`

**Step 1: Create ActivityTab component**

```typescript
// frontend/src/components/leads/detail/ActivityTab.tsx
import {
  Activity,
  Calendar,
  Mail,
  MailOpen,
  MessageSquare,
  Phone,
  Signal,
  Video,
} from "lucide-react";
import type { LeadEvent, EventType } from "@/api/leads";

interface ActivityTabProps {
  events: LeadEvent[];
  isLoading: boolean;
}

const eventIcons: Record<EventType, React.ReactNode> = {
  email_sent: <Mail className="w-3.5 h-3.5" />,
  email_received: <MailOpen className="w-3.5 h-3.5" />,
  meeting: <Video className="w-3.5 h-3.5" />,
  call: <Phone className="w-3.5 h-3.5" />,
  note: <MessageSquare className="w-3.5 h-3.5" />,
  signal: <Signal className="w-3.5 h-3.5" />,
};

const eventLabels: Record<EventType, string> = {
  email_sent: "Sent email",
  email_received: "Received email",
  meeting: "Had meeting",
  call: "Made call",
  note: "Added note",
  signal: "Signal detected",
};

function ActivityRow({ event }: { event: LeadEvent }) {
  const icon = eventIcons[event.event_type];
  const label = eventLabels[event.event_type];

  const formatDateTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return date.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
      });
    }
    if (diffDays === 1) {
      return "Yesterday";
    }
    if (diffDays < 7) {
      return date.toLocaleDateString("en-US", { weekday: "short" });
    }
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div className="flex items-center gap-3 py-3 px-4 hover:bg-slate-800/30 rounded-lg transition-colors group">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-slate-800/60 flex items-center justify-center text-slate-400 group-hover:text-slate-300 transition-colors">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-sm text-slate-300">{label}</span>
          {event.subject && (
            <span className="text-sm text-slate-500 truncate">
              — {event.subject}
            </span>
          )}
        </div>
        {event.participants.length > 0 && (
          <p className="text-xs text-slate-500 truncate">
            {event.participants.join(", ")}
          </p>
        )}
      </div>
      <span className="flex-shrink-0 text-xs text-slate-500">
        {formatDateTime(event.occurred_at)}
      </span>
    </div>
  );
}

function ActivitySkeleton() {
  return (
    <div className="space-y-1">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <div key={i} className="flex items-center gap-3 py-3 px-4 animate-pulse">
          <div className="w-8 h-8 rounded-lg bg-slate-700/50" />
          <div className="flex-1 space-y-1">
            <div className="h-4 w-48 bg-slate-700/50 rounded" />
            <div className="h-3 w-32 bg-slate-700/30 rounded" />
          </div>
          <div className="h-3 w-12 bg-slate-700/30 rounded" />
        </div>
      ))}
    </div>
  );
}

function EmptyActivity() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-800/50 flex items-center justify-center mb-4">
        <Activity className="w-8 h-8 text-slate-600" />
      </div>
      <h3 className="text-lg font-medium text-slate-400 mb-1">No activity yet</h3>
      <p className="text-sm text-slate-500 max-w-xs">
        All interactions with this lead will appear here
      </p>
    </div>
  );
}

function groupEventsByDate(events: LeadEvent[]): Map<string, LeadEvent[]> {
  const groups = new Map<string, LeadEvent[]>();

  events.forEach((event) => {
    const date = new Date(event.occurred_at);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    let key: string;
    if (date.toDateString() === today.toDateString()) {
      key = "Today";
    } else if (date.toDateString() === yesterday.toDateString()) {
      key = "Yesterday";
    } else {
      key = date.toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: date.getFullYear() !== today.getFullYear() ? "numeric" : undefined,
      });
    }

    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(event);
  });

  return groups;
}

export function ActivityTab({ events, isLoading }: ActivityTabProps) {
  if (isLoading) {
    return <ActivitySkeleton />;
  }

  if (events.length === 0) {
    return <EmptyActivity />;
  }

  const groupedEvents = groupEventsByDate(events);

  return (
    <div className="space-y-6">
      {Array.from(groupedEvents.entries()).map(([date, dateEvents]) => (
        <div key={date}>
          <div className="flex items-center gap-3 mb-2 px-4">
            <Calendar className="w-4 h-4 text-slate-500" />
            <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              {date}
            </h3>
            <div className="flex-1 h-px bg-slate-700/30" />
          </div>
          <div className="space-y-0.5">
            {dateEvents.map((event) => (
              <ActivityRow key={event.id} event={event} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/ActivityTab.tsx
git commit -m "feat(leads): add ActivityTab component for lead detail

- Compact list view of all interactions
- Group events by date (Today, Yesterday, date)
- Relative time formatting
- Loading skeleton and empty state

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Create Edit Stakeholder Modal

**Files:**
- Create: `frontend/src/components/leads/detail/EditStakeholderModal.tsx`

**Step 1: Create EditStakeholderModal component**

```typescript
// frontend/src/components/leads/detail/EditStakeholderModal.tsx
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import type {
  Stakeholder,
  StakeholderRole,
  StakeholderUpdate,
  Sentiment,
} from "@/api/leads";

interface EditStakeholderModalProps {
  stakeholder: Stakeholder | null;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (updates: StakeholderUpdate) => void;
  isLoading: boolean;
}

const roleOptions: { value: StakeholderRole; label: string }[] = [
  { value: "decision_maker", label: "Decision Maker" },
  { value: "influencer", label: "Influencer" },
  { value: "champion", label: "Champion" },
  { value: "blocker", label: "Blocker" },
  { value: "user", label: "User" },
];

const sentimentOptions: { value: Sentiment; label: string }[] = [
  { value: "positive", label: "Positive" },
  { value: "neutral", label: "Neutral" },
  { value: "negative", label: "Negative" },
  { value: "unknown", label: "Unknown" },
];

export function EditStakeholderModal({
  stakeholder,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: EditStakeholderModalProps) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [role, setRole] = useState<StakeholderRole | "">("");
  const [sentiment, setSentiment] = useState<Sentiment>("neutral");
  const [influence, setInfluence] = useState(5);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (stakeholder) {
      setName(stakeholder.contact_name || "");
      setTitle(stakeholder.title || "");
      setRole(stakeholder.role || "");
      setSentiment(stakeholder.sentiment);
      setInfluence(stakeholder.influence_level);
      setNotes(stakeholder.notes || "");
    }
  }, [stakeholder]);

  if (!isOpen || !stakeholder) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      contact_name: name || undefined,
      title: title || undefined,
      role: role || undefined,
      sentiment,
      influence_level: influence,
      notes: notes || undefined,
    });
  };

  const handleClose = () => {
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/95 backdrop-blur-sm">
          <div>
            <h2 className="text-lg font-semibold text-white">Edit Stakeholder</h2>
            <p className="text-sm text-slate-400 mt-0.5">{stakeholder.contact_email}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Name */}
          <div>
            <label
              htmlFor="stakeholder-name"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Name
            </label>
            <input
              id="stakeholder-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Contact name"
              className="w-full px-4 py-2.5 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            />
          </div>

          {/* Title */}
          <div>
            <label
              htmlFor="stakeholder-title"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Title
            </label>
            <input
              id="stakeholder-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Job title"
              className="w-full px-4 py-2.5 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            />
          </div>

          {/* Role */}
          <div>
            <label
              htmlFor="stakeholder-role"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Role
            </label>
            <select
              id="stakeholder-role"
              value={role}
              onChange={(e) => setRole(e.target.value as StakeholderRole | "")}
              className="w-full px-4 py-2.5 bg-slate-900/50 border border-slate-700 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            >
              <option value="">No role assigned</option>
              {roleOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Sentiment */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Sentiment
            </label>
            <div className="flex gap-2">
              {sentimentOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setSentiment(opt.value)}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-all ${
                    sentiment === opt.value
                      ? "bg-primary-500/20 border-primary-500/30 text-primary-400"
                      : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white hover:border-slate-600/50"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Influence */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Influence Level: {influence}/10
            </label>
            <input
              type="range"
              min="1"
              max="10"
              value={influence}
              onChange={(e) => setInfluence(parseInt(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary-500 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:cursor-pointer"
            />
            <div className="flex justify-between text-xs text-slate-500 mt-1">
              <span>Low</span>
              <span>High</span>
            </div>
          </div>

          {/* Notes */}
          <div>
            <label
              htmlFor="stakeholder-notes"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              Notes
            </label>
            <textarea
              id="stakeholder-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add notes about this stakeholder..."
              rows={3}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Saving...
                </span>
              ) : (
                "Save Changes"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/EditStakeholderModal.tsx
git commit -m "feat(leads): add EditStakeholderModal component

- Form fields for name, title, role, sentiment, influence, notes
- Sentiment selection with toggle buttons
- Influence range slider with visual feedback
- Loading state and form validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Create Stage Transition Modal

**Files:**
- Create: `frontend/src/components/leads/detail/StageTransitionModal.tsx`

**Step 1: Create StageTransitionModal component**

```typescript
// frontend/src/components/leads/detail/StageTransitionModal.tsx
import { ArrowRight, X } from "lucide-react";
import { useState } from "react";
import type { LifecycleStage, StageTransition } from "@/api/leads";

interface StageTransitionModalProps {
  currentStage: LifecycleStage;
  companyName: string;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (transition: StageTransition) => void;
  isLoading: boolean;
}

const stageOrder: LifecycleStage[] = ["lead", "opportunity", "account"];

const stageConfig: Record<LifecycleStage, { label: string; description: string }> = {
  lead: {
    label: "Lead",
    description: "Initial contact, exploring fit",
  },
  opportunity: {
    label: "Opportunity",
    description: "Qualified prospect, active pursuit",
  },
  account: {
    label: "Account",
    description: "Customer, ongoing relationship",
  },
};

export function StageTransitionModal({
  currentStage,
  companyName,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: StageTransitionModalProps) {
  const [selectedStage, setSelectedStage] = useState<LifecycleStage | null>(null);
  const [reason, setReason] = useState("");

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedStage && selectedStage !== currentStage) {
      onSubmit({
        new_stage: selectedStage,
        reason: reason || undefined,
      });
    }
  };

  const handleClose = () => {
    setSelectedStage(null);
    setReason("");
    onClose();
  };

  const currentIndex = stageOrder.indexOf(currentStage);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-white">Transition Stage</h2>
            <p className="text-sm text-slate-400 mt-0.5">{companyName}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6">
          {/* Stage progression */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-slate-300 mb-3">
              Select new stage
            </label>
            <div className="space-y-2">
              {stageOrder.map((stage, idx) => {
                const config = stageConfig[stage];
                const isCurrent = stage === currentStage;
                const isSelected = stage === selectedStage;
                const isPast = idx < currentIndex;

                return (
                  <button
                    key={stage}
                    type="button"
                    onClick={() => !isCurrent && setSelectedStage(stage)}
                    disabled={isCurrent}
                    className={`w-full flex items-center gap-4 p-4 rounded-xl border transition-all ${
                      isCurrent
                        ? "bg-primary-500/10 border-primary-500/30 cursor-default"
                        : isSelected
                          ? "bg-slate-700/50 border-primary-500/50 ring-1 ring-primary-500/30"
                          : "bg-slate-800/50 border-slate-700/50 hover:bg-slate-800 hover:border-slate-600/50"
                    }`}
                  >
                    <div
                      className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-semibold ${
                        isCurrent
                          ? "bg-primary-500 text-white"
                          : isPast
                            ? "bg-slate-600 text-slate-300"
                            : "bg-slate-700 text-slate-400"
                      }`}
                    >
                      {idx + 1}
                    </div>
                    <div className="flex-1 text-left">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-medium ${isCurrent ? "text-primary-400" : "text-white"}`}
                        >
                          {config.label}
                        </span>
                        {isCurrent && (
                          <span className="px-2 py-0.5 text-xs rounded-full bg-primary-500/20 text-primary-400">
                            Current
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-500">{config.description}</p>
                    </div>
                    {!isCurrent && (
                      <ArrowRight
                        className={`w-5 h-5 transition-colors ${
                          isSelected ? "text-primary-400" : "text-slate-600"
                        }`}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Reason */}
          {selectedStage && (
            <div className="mb-6 animate-in fade-in slide-in-from-top-2 duration-200">
              <label
                htmlFor="transition-reason"
                className="block text-sm font-medium text-slate-300 mb-2"
              >
                Reason (optional)
              </label>
              <textarea
                id="transition-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why are you transitioning this lead?"
                rows={2}
                className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!selectedStage || selectedStage === currentStage || isLoading}
              className="px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Transitioning...
                </span>
              ) : (
                "Confirm Transition"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/StageTransitionModal.tsx
git commit -m "feat(leads): add StageTransitionModal component

- Visual stage progression with numbered steps
- Current stage indicator
- Optional reason field
- Loading state and confirmation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Create Add Event Modal

**Files:**
- Create: `frontend/src/components/leads/detail/AddEventModal.tsx`

**Step 1: Create AddEventModal component**

```typescript
// frontend/src/components/leads/detail/AddEventModal.tsx
import { X } from "lucide-react";
import { useState } from "react";
import type { EventType, LeadEvent } from "@/api/leads";

interface AddEventModalProps {
  leadId: string;
  companyName: string;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">) => void;
  isLoading: boolean;
}

const eventTypeOptions: { value: EventType; label: string }[] = [
  { value: "note", label: "Note" },
  { value: "email_sent", label: "Email Sent" },
  { value: "email_received", label: "Email Received" },
  { value: "meeting", label: "Meeting" },
  { value: "call", label: "Call" },
  { value: "signal", label: "Signal" },
];

export function AddEventModal({
  companyName,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: AddEventModalProps) {
  const [eventType, setEventType] = useState<EventType>("note");
  const [subject, setSubject] = useState("");
  const [content, setContent] = useState("");
  const [participants, setParticipants] = useState("");

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (content.trim()) {
      onSubmit({
        event_type: eventType,
        direction: eventType === "email_sent" ? "outbound" : eventType === "email_received" ? "inbound" : null,
        subject: subject.trim() || null,
        content: content.trim(),
        participants: participants
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        occurred_at: new Date().toISOString(),
        source: "manual",
      });
    }
  };

  const handleClose = () => {
    setEventType("note");
    setSubject("");
    setContent("");
    setParticipants("");
    onClose();
  };

  const showSubject = ["email_sent", "email_received", "meeting"].includes(eventType);
  const showParticipants = ["email_sent", "email_received", "meeting", "call"].includes(eventType);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-white">Add Event</h2>
            <p className="text-sm text-slate-400 mt-0.5">{companyName}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Event Type */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Event Type
            </label>
            <div className="flex flex-wrap gap-2">
              {eventTypeOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setEventType(opt.value)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium border transition-all ${
                    eventType === opt.value
                      ? "bg-primary-500/20 border-primary-500/30 text-primary-400"
                      : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white hover:border-slate-600/50"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Subject */}
          {showSubject && (
            <div className="animate-in fade-in slide-in-from-top-2 duration-200">
              <label
                htmlFor="event-subject"
                className="block text-sm font-medium text-slate-300 mb-2"
              >
                Subject
              </label>
              <input
                id="event-subject"
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Subject line"
                className="w-full px-4 py-2.5 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />
            </div>
          )}

          {/* Content */}
          <div>
            <label
              htmlFor="event-content"
              className="block text-sm font-medium text-slate-300 mb-2"
            >
              {eventType === "note" ? "Note" : "Details"}
            </label>
            <textarea
              id="event-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={
                eventType === "note"
                  ? "Add your note..."
                  : "Add event details..."
              }
              rows={4}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
              autoFocus
            />
          </div>

          {/* Participants */}
          {showParticipants && (
            <div className="animate-in fade-in slide-in-from-top-2 duration-200">
              <label
                htmlFor="event-participants"
                className="block text-sm font-medium text-slate-300 mb-2"
              >
                Participants
              </label>
              <input
                id="event-participants"
                type="text"
                value={participants}
                onChange={(e) => setParticipants(e.target.value)}
                placeholder="email@example.com, another@example.com"
                className="w-full px-4 py-2.5 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />
              <p className="mt-1 text-xs text-slate-500">Separate multiple emails with commas</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!content.trim() || isLoading}
              className="px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Adding...
                </span>
              ) : (
                "Add Event"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/AddEventModal.tsx
git commit -m "feat(leads): add AddEventModal component

- Event type selection with toggle buttons
- Dynamic fields based on event type
- Participant input with comma separation
- Loading state and validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Create Detail Components Barrel Export

**Files:**
- Create: `frontend/src/components/leads/detail/index.ts`

**Step 1: Create barrel export file**

```typescript
// frontend/src/components/leads/detail/index.ts
export { ActivityTab } from "./ActivityTab";
export { AddEventModal } from "./AddEventModal";
export { EditStakeholderModal } from "./EditStakeholderModal";
export { InsightsTab } from "./InsightsTab";
export { StageTransitionModal } from "./StageTransitionModal";
export { StakeholdersTab } from "./StakeholdersTab";
export { TimelineTab } from "./TimelineTab";
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/leads/detail/index.ts
git commit -m "feat(leads): add barrel export for lead detail components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Create LeadDetail Page Component

**Files:**
- Create: `frontend/src/pages/LeadDetail.tsx`

**Step 1: Create LeadDetail page component**

```typescript
// frontend/src/pages/LeadDetail.tsx
import {
  Activity,
  ArrowLeft,
  Building2,
  ChevronRight,
  Lightbulb,
  MessageSquarePlus,
  RefreshCw,
  Timeline,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { LeadEvent, Stakeholder, StakeholderUpdate, StageTransition } from "@/api/leads";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  HealthScoreBadge,
  StagePill,
  StatusIndicator,
} from "@/components/leads";
import {
  ActivityTab,
  AddEventModal,
  EditStakeholderModal,
  InsightsTab,
  StageTransitionModal,
  StakeholdersTab,
  TimelineTab,
} from "@/components/leads/detail";
import {
  useAddEvent,
  useLead,
  useLeadInsights,
  useLeadStakeholders,
  useLeadTimeline,
  useTransitionStage,
  useUpdateStakeholder,
} from "@/hooks/useLeads";

type Tab = "timeline" | "stakeholders" | "insights" | "activity";

const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "timeline", label: "Timeline", icon: <Timeline className="w-4 h-4" /> },
  { id: "stakeholders", label: "Stakeholders", icon: <Users className="w-4 h-4" /> },
  { id: "insights", label: "Insights", icon: <Lightbulb className="w-4 h-4" /> },
  { id: "activity", label: "Activity", icon: <Activity className="w-4 h-4" /> },
];

function LeadDetailSkeleton() {
  return (
    <div className="animate-pulse">
      {/* Header skeleton */}
      <div className="mb-8">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-16 h-16 rounded-2xl bg-slate-700/50" />
          <div className="flex-1 space-y-2">
            <div className="h-7 w-64 bg-slate-700/50 rounded" />
            <div className="flex gap-2">
              <div className="h-5 w-20 bg-slate-700/30 rounded-full" />
              <div className="h-5 w-16 bg-slate-700/30 rounded-full" />
            </div>
          </div>
        </div>
      </div>

      {/* Tabs skeleton */}
      <div className="flex gap-1 mb-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-10 w-28 bg-slate-700/30 rounded-lg" />
        ))}
      </div>

      {/* Content skeleton */}
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 bg-slate-800/40 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-20 h-20 rounded-2xl bg-slate-800/50 flex items-center justify-center mb-6">
        <Building2 className="w-10 h-10 text-slate-600" />
      </div>
      <h2 className="text-xl font-semibold text-white mb-2">Lead not found</h2>
      <p className="text-slate-400 mb-6">
        This lead may have been deleted or you don't have access to it.
      </p>
      <Link
        to="/dashboard/leads"
        className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Leads
      </Link>
    </div>
  );
}

export function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState<Tab>("timeline");

  // Modal state
  const [showAddEvent, setShowAddEvent] = useState(false);
  const [showTransition, setShowTransition] = useState(false);
  const [editingStakeholder, setEditingStakeholder] = useState<Stakeholder | null>(null);

  // Queries
  const { data: lead, isLoading: leadLoading, error: leadError } = useLead(id || "");
  const { data: timeline = [], isLoading: timelineLoading } = useLeadTimeline(id || "");
  const { data: stakeholders = [], isLoading: stakeholdersLoading } = useLeadStakeholders(id || "");
  const { data: insights = [], isLoading: insightsLoading } = useLeadInsights(id || "");

  // Mutations
  const addEventMutation = useAddEvent();
  const updateStakeholderMutation = useUpdateStakeholder();
  const transitionStageMutation = useTransitionStage();

  // Handlers
  const handleAddEvent = (event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">) => {
    if (id) {
      addEventMutation.mutate(
        { leadId: id, event },
        {
          onSuccess: () => setShowAddEvent(false),
        }
      );
    }
  };

  const handleUpdateStakeholder = (updates: StakeholderUpdate) => {
    if (id && editingStakeholder) {
      updateStakeholderMutation.mutate(
        { leadId: id, stakeholderId: editingStakeholder.id, updates },
        {
          onSuccess: () => setEditingStakeholder(null),
        }
      );
    }
  };

  const handleTransitionStage = (transition: StageTransition) => {
    if (id) {
      transitionStageMutation.mutate(
        { leadId: id, transition },
        {
          onSuccess: () => setShowTransition(false),
        }
      );
    }
  };

  return (
    <DashboardLayout>
      <div className="relative min-h-screen">
        {/* Subtle gradient background */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-5xl mx-auto px-4 py-8 lg:px-8">
          {/* Back link */}
          <Link
            to="/dashboard/leads"
            className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-6 transition-colors group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
            Back to Leads
          </Link>

          {leadLoading && <LeadDetailSkeleton />}

          {leadError && <NotFound />}

          {lead && (
            <>
              {/* Header */}
              <div className="mb-8">
                <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-16 h-16 bg-gradient-to-br from-slate-700 to-slate-800 rounded-2xl flex items-center justify-center border border-slate-600/50 shadow-lg">
                      <Building2 className="w-8 h-8 text-slate-400" />
                    </div>
                    <div>
                      <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mb-2">
                        {lead.company_name}
                      </h1>
                      <div className="flex flex-wrap items-center gap-3">
                        <HealthScoreBadge score={lead.health_score} size="lg" />
                        <StagePill stage={lead.lifecycle_stage} size="md" />
                        <StatusIndicator status={lead.status} />
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setShowAddEvent(true)}
                      className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-800/50 border border-slate-700/50 hover:bg-slate-800 hover:border-slate-600/50 text-slate-300 hover:text-white font-medium rounded-lg transition-all"
                    >
                      <MessageSquarePlus className="w-4 h-4" />
                      Add Event
                    </button>
                    <button
                      onClick={() => setShowTransition(true)}
                      className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
                    >
                      <RefreshCw className="w-4 h-4" />
                      Transition Stage
                    </button>
                  </div>
                </div>

                {/* Breadcrumb */}
                <div className="flex items-center gap-2 mt-4 text-sm text-slate-500">
                  <span>Lead Memory</span>
                  <ChevronRight className="w-4 h-4" />
                  <span className="text-slate-300">{lead.company_name}</span>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 mb-6 p-1 bg-slate-800/30 border border-slate-700/30 rounded-xl overflow-x-auto">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${
                      activeTab === tab.id
                        ? "bg-slate-700/50 text-white shadow-sm"
                        : "text-slate-400 hover:text-white hover:bg-slate-800/50"
                    }`}
                  >
                    {tab.icon}
                    {tab.label}
                    {tab.id === "insights" && insights.length > 0 && (
                      <span className="px-1.5 py-0.5 text-xs rounded-full bg-primary-500/20 text-primary-400">
                        {insights.length}
                      </span>
                    )}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="bg-slate-800/20 border border-slate-700/30 rounded-2xl p-6">
                {activeTab === "timeline" && (
                  <TimelineTab events={timeline} isLoading={timelineLoading} />
                )}
                {activeTab === "stakeholders" && (
                  <StakeholdersTab
                    stakeholders={stakeholders}
                    isLoading={stakeholdersLoading}
                    onEdit={setEditingStakeholder}
                  />
                )}
                {activeTab === "insights" && (
                  <InsightsTab insights={insights} isLoading={insightsLoading} />
                )}
                {activeTab === "activity" && (
                  <ActivityTab events={timeline} isLoading={timelineLoading} />
                )}
              </div>
            </>
          )}
        </div>

        {/* Modals */}
        {lead && (
          <>
            <AddEventModal
              leadId={id || ""}
              companyName={lead.company_name}
              isOpen={showAddEvent}
              onClose={() => setShowAddEvent(false)}
              onSubmit={handleAddEvent}
              isLoading={addEventMutation.isPending}
            />

            <StageTransitionModal
              currentStage={lead.lifecycle_stage}
              companyName={lead.company_name}
              isOpen={showTransition}
              onClose={() => setShowTransition(false)}
              onSubmit={handleTransitionStage}
              isLoading={transitionStageMutation.isPending}
            />

            <EditStakeholderModal
              stakeholder={editingStakeholder}
              isOpen={editingStakeholder !== null}
              onClose={() => setEditingStakeholder(null)}
              onSubmit={handleUpdateStakeholder}
              isLoading={updateStakeholderMutation.isPending}
            />
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/pages/LeadDetail.tsx
git commit -m "feat(leads): add LeadDetailPage component

- Header with company name, health score, stage, status
- Tab navigation for timeline, stakeholders, insights, activity
- Action buttons for add event and transition stage
- Modal integration for all edit actions
- Loading skeleton and not found states

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Register Route and Update Exports

**Files:**
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Update pages index export**

Add export for LeadDetailPage:

```typescript
export { AriaChatPage } from "./AriaChat";
export { BattleCardsPage } from "./BattleCards";
export { DashboardPage } from "./Dashboard";
export { EmailDraftsPage } from "./EmailDrafts";
export { GoalsPage } from "./Goals";
export { IntegrationsCallbackPage } from "./IntegrationsCallback";
export { LeadDetailPage } from "./LeadDetail";
export { LeadsPage } from "./Leads";
export { IntegrationsSettingsPage } from "./IntegrationsSettings";
export { LoginPage } from "./Login";
export { MeetingBriefPage } from "./MeetingBrief";
export { NotificationsPage } from "./NotificationsPage";
export { PreferencesSettingsPage } from "./PreferencesSettings";
export { SignupPage } from "./Signup";
```

**Step 2: Add route to App.tsx**

Add import for `LeadDetailPage`:

```typescript
import {
  AriaChatPage,
  BattleCardsPage,
  EmailDraftsPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LeadDetailPage,
  LeadsPage,
  LoginPage,
  MeetingBriefPage,
  NotificationsPage,
  PreferencesSettingsPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
} from "@/pages";
```

Add route after `/dashboard/leads` route (around line 69):

```typescript
<Route
  path="/dashboard/leads/:id"
  element={
    <ProtectedRoute>
      <LeadDetailPage />
    </ProtectedRoute>
  }
/>
```

**Step 3: Verify no TypeScript errors**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(leads): register /dashboard/leads/:id route

- Export LeadDetailPage from pages index
- Add protected route for lead detail view

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 14: Run Lint and Fix Any Issues

**Files:**
- All modified/created files

**Step 1: Run linter**

Run: `cd /Users/dhruv/aria/frontend && npm run lint`
Expected: No errors (or fix any that appear)

**Step 2: Run type checker again**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix(leads): lint and type check fixes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 15: Manual Testing Checklist

**Files:** None (manual verification)

**Step 1: Start frontend dev server**

Run: `cd /Users/dhruv/aria/frontend && npm run dev`

**Step 2: Verify routes**

- [ ] Navigate to `/dashboard/leads` - should show list page
- [ ] Click on a lead card - should navigate to `/dashboard/leads/{id}`
- [ ] Verify back button returns to list

**Step 3: Verify tabs**

- [ ] Timeline tab displays events or empty state
- [ ] Stakeholders tab displays contacts or empty state
- [ ] Insights tab displays grouped insights or empty state
- [ ] Activity tab displays events or empty state
- [ ] Tab switching is smooth with no flicker

**Step 4: Verify modals**

- [ ] "Add Event" button opens modal
- [ ] Event type toggles work correctly
- [ ] "Transition Stage" button opens modal
- [ ] Current stage is highlighted
- [ ] Edit stakeholder button opens modal (if stakeholders exist)

**Step 5: Verify responsive design**

- [ ] Header stacks properly on mobile
- [ ] Tabs scroll horizontally on small screens
- [ ] Cards resize appropriately

**Step 6: Commit final verification**

```bash
git add -A
git commit -m "docs(leads): complete US-509 Lead Detail View implementation

Implements:
- /dashboard/leads/{id} route
- Header with company name, health score badge, lifecycle stage pill
- Timeline tab with chronological events and icons
- Stakeholders tab with contact cards and role/sentiment
- Insights tab with objections, signals, commitments grouped
- Activity tab with all interactions feed
- Inline add note/event modal
- Edit stakeholder details modal
- Transition stage button with confirmation modal
- React Query for data fetching
- Responsive layout with Apple-inspired dark theme

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan implements US-509: Lead Memory UI - Detail View with:

1. **API Layer** (Tasks 1-2): Extended types and hooks for timeline, stakeholders, insights, stage transitions
2. **Shared Components** (Task 3): HealthScoreBadge, StagePill, StatusIndicator
3. **Tab Components** (Tasks 4-7): TimelineTab, StakeholdersTab, InsightsTab, ActivityTab
4. **Modal Components** (Tasks 8-10): EditStakeholderModal, StageTransitionModal, AddEventModal
5. **Page Component** (Task 12): LeadDetailPage with full tab navigation
6. **Routing** (Task 13): Route registration at `/dashboard/leads/:id`
7. **Quality** (Tasks 14-15): Lint, type check, manual testing

Design follows Apple-inspired luxury dark theme matching the existing LeadsPage with:
- Subtle gradient backgrounds
- Smooth transitions and hover effects
- Consistent color coding for health, stages, sentiments
- Loading skeletons and empty states
- Responsive layout
