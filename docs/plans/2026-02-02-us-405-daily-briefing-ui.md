# US-405: Daily Briefing UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a premium, Apple-inspired daily briefing UI that makes ARIA feel like a trusted colleague starting your day.

**Architecture:** React Query for data fetching with auto-refresh, collapsible section components with smooth animations, time-based greeting, skeleton loading states. The dashboard becomes the briefing-centric home for ARIA users.

**Tech Stack:** React 18, TypeScript, Tailwind CSS v4, React Query (TanStack Query), Lucide React icons

---

## Task 1: Create Briefing API Client

**Files:**
- Create: `frontend/src/api/briefings.ts`

**Step 1: Create the briefings API module with types and functions**

```typescript
import { apiClient } from "./client";

// Briefing content types matching backend schema
export interface BriefingMeeting {
  time: string;
  title: string;
  attendees: string[];
}

export interface BriefingCalendar {
  meeting_count: number;
  key_meetings: BriefingMeeting[];
}

export interface BriefingLead {
  id: string;
  name: string;
  company: string;
  status?: string;
  last_contact?: string;
  health_score?: number;
}

export interface BriefingLeads {
  hot_leads: BriefingLead[];
  needs_attention: BriefingLead[];
  recently_active: BriefingLead[];
}

export interface BriefingSignal {
  id: string;
  type: "company_news" | "market_trend" | "competitive_intel";
  title: string;
  summary: string;
  source?: string;
  relevance?: number;
}

export interface BriefingSignals {
  company_news: BriefingSignal[];
  market_trends: BriefingSignal[];
  competitive_intel: BriefingSignal[];
}

export interface BriefingTask {
  id: string;
  title: string;
  due_date?: string;
  priority?: "high" | "medium" | "low";
  related_lead_id?: string;
}

export interface BriefingTasks {
  overdue: BriefingTask[];
  due_today: BriefingTask[];
}

export interface BriefingContent {
  summary: string;
  calendar: BriefingCalendar;
  leads: BriefingLeads;
  signals: BriefingSignals;
  tasks: BriefingTasks;
  generated_at: string;
}

export interface BriefingListItem {
  id: string;
  briefing_date: string;
  content: BriefingContent;
}

export interface BriefingResponse {
  id: string;
  user_id: string;
  briefing_date: string;
  content: BriefingContent;
}

// API functions
export async function getTodayBriefing(regenerate = false): Promise<BriefingContent> {
  const params = regenerate ? "?regenerate=true" : "";
  const response = await apiClient.get<BriefingContent>(`/briefings/today${params}`);
  return response.data;
}

export async function listBriefings(limit = 7): Promise<BriefingListItem[]> {
  const response = await apiClient.get<BriefingListItem[]>(`/briefings?limit=${limit}`);
  return response.data;
}

export async function getBriefingByDate(briefingDate: string): Promise<BriefingResponse> {
  const response = await apiClient.get<BriefingResponse>(`/briefings/${briefingDate}`);
  return response.data;
}

export async function generateBriefing(briefingDate?: string): Promise<BriefingContent> {
  const response = await apiClient.post<BriefingContent>("/briefings/generate", {
    briefing_date: briefingDate ?? null,
  });
  return response.data;
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors related to `briefings.ts`

**Step 3: Commit**

```bash
git add frontend/src/api/briefings.ts
git commit -m "feat(briefing): add briefing API client with types"
```

---

## Task 2: Create Briefing React Query Hooks

**Files:**
- Create: `frontend/src/hooks/useBriefing.ts`

**Step 1: Create the briefing hooks module**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  generateBriefing,
  getBriefingByDate,
  getTodayBriefing,
  listBriefings,
} from "@/api/briefings";

// Query keys
export const briefingKeys = {
  all: ["briefings"] as const,
  today: () => [...briefingKeys.all, "today"] as const,
  lists: () => [...briefingKeys.all, "list"] as const,
  list: (limit: number) => [...briefingKeys.lists(), { limit }] as const,
  byDate: (date: string) => [...briefingKeys.all, "date", date] as const,
};

// Today's briefing query
export function useTodayBriefing() {
  return useQuery({
    queryKey: briefingKeys.today(),
    queryFn: () => getTodayBriefing(),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

// List recent briefings query
export function useBriefingList(limit = 7) {
  return useQuery({
    queryKey: briefingKeys.list(limit),
    queryFn: () => listBriefings(limit),
  });
}

// Briefing by date query
export function useBriefingByDate(date: string) {
  return useQuery({
    queryKey: briefingKeys.byDate(date),
    queryFn: () => getBriefingByDate(date),
    enabled: !!date,
  });
}

// Regenerate briefing mutation
export function useRegenerateBriefing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => getTodayBriefing(true),
    onSuccess: (data) => {
      queryClient.setQueryData(briefingKeys.today(), data);
      queryClient.invalidateQueries({ queryKey: briefingKeys.lists() });
    },
  });
}

// Generate briefing for specific date mutation
export function useGenerateBriefing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (date?: string) => generateBriefing(date),
    onSuccess: (data, date) => {
      if (!date) {
        queryClient.setQueryData(briefingKeys.today(), data);
      }
      queryClient.invalidateQueries({ queryKey: briefingKeys.lists() });
    },
  });
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors related to `useBriefing.ts`

**Step 3: Commit**

```bash
git add frontend/src/hooks/useBriefing.ts
git commit -m "feat(briefing): add React Query hooks for briefings"
```

---

## Task 3: Create Collapsible Section Component

**Files:**
- Create: `frontend/src/components/ui/CollapsibleSection.tsx`

**Step 1: Create the reusable collapsible section component**

```typescript
import { ChevronDown } from "lucide-react";
import { type ReactNode, useState } from "react";

interface CollapsibleSectionProps {
  title: string;
  icon?: ReactNode;
  badge?: string | number;
  badgeColor?: "primary" | "amber" | "red" | "green" | "slate";
  defaultExpanded?: boolean;
  children: ReactNode;
}

const badgeColors = {
  primary: "bg-primary-500/20 text-primary-400",
  amber: "bg-amber-500/20 text-amber-400",
  red: "bg-red-500/20 text-red-400",
  green: "bg-green-500/20 text-green-400",
  slate: "bg-slate-600/50 text-slate-400",
};

export function CollapsibleSection({
  title,
  icon,
  badge,
  badgeColor = "slate",
  defaultExpanded = true,
  children,
}: CollapsibleSectionProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-slate-800/80 transition-colors"
      >
        <div className="flex items-center gap-3">
          {icon && <span className="text-slate-400">{icon}</span>}
          <h3 className="text-base font-semibold text-white">{title}</h3>
          {badge !== undefined && (
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${badgeColors[badgeColor]}`}
            >
              {badge}
            </span>
          )}
        </div>
        <ChevronDown
          className={`w-5 h-5 text-slate-400 transition-transform duration-200 ${
            isExpanded ? "rotate-180" : ""
          }`}
        />
      </button>
      <div
        className={`transition-all duration-200 ease-in-out ${
          isExpanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
        } overflow-hidden`}
      >
        <div className="px-4 pb-4">{children}</div>
      </div>
    </div>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/ui/CollapsibleSection.tsx
git commit -m "feat(ui): add CollapsibleSection component with animations"
```

---

## Task 4: Create Briefing Skeleton Loader

**Files:**
- Create: `frontend/src/components/briefing/BriefingSkeleton.tsx`

**Step 1: Create the skeleton loading component**

```typescript
export function BriefingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Greeting skeleton */}
      <div className="space-y-3">
        <div className="h-10 w-64 bg-slate-700/50 rounded-lg" />
        <div className="h-5 w-96 bg-slate-700/30 rounded" />
      </div>

      {/* Summary card skeleton */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
        <div className="space-y-3">
          <div className="h-4 w-full bg-slate-700/50 rounded" />
          <div className="h-4 w-5/6 bg-slate-700/50 rounded" />
          <div className="h-4 w-4/6 bg-slate-700/50 rounded" />
        </div>
      </div>

      {/* Section skeletons */}
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="bg-slate-800/50 border border-slate-700/50 rounded-xl">
          <div className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 bg-slate-700/50 rounded" />
              <div className="h-5 w-32 bg-slate-700/50 rounded" />
              <div className="h-5 w-8 bg-slate-700/30 rounded-full" />
            </div>
            <div className="w-5 h-5 bg-slate-700/30 rounded" />
          </div>
          <div className="px-4 pb-4 space-y-3">
            <div className="h-16 bg-slate-700/30 rounded-lg" />
            <div className="h-16 bg-slate-700/30 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/BriefingSkeleton.tsx
git commit -m "feat(briefing): add skeleton loading component"
```

---

## Task 5: Create Briefing Empty State Component

**Files:**
- Create: `frontend/src/components/briefing/BriefingEmpty.tsx`

**Step 1: Create the empty state component**

```typescript
import { Sparkles, RefreshCw } from "lucide-react";

interface BriefingEmptyProps {
  onGenerate: () => void;
  isGenerating?: boolean;
}

export function BriefingEmpty({ onGenerate, isGenerating }: BriefingEmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Illustration */}
      <div className="relative">
        <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
        <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
          <Sparkles className="w-12 h-12 text-primary-400" />
        </div>
      </div>

      {/* Text */}
      <h3 className="mt-6 text-xl font-semibold text-white">No briefing yet</h3>
      <p className="mt-2 text-slate-400 text-center max-w-md">
        ARIA hasn't generated your daily briefing yet. Generate one now to see your calendar,
        priority leads, and market signals.
      </p>

      {/* CTA */}
      <button
        onClick={onGenerate}
        disabled={isGenerating}
        className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
      >
        <RefreshCw className={`w-5 h-5 ${isGenerating ? "animate-spin" : ""}`} />
        {isGenerating ? "Generating..." : "Generate briefing"}
      </button>
    </div>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/BriefingEmpty.tsx
git commit -m "feat(briefing): add empty state component"
```

---

## Task 6: Create Calendar Section Component

**Files:**
- Create: `frontend/src/components/briefing/CalendarSection.tsx`

**Step 1: Create the calendar briefing section**

```typescript
import { Calendar, Clock, Users } from "lucide-react";
import type { BriefingCalendar } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface CalendarSectionProps {
  calendar: BriefingCalendar;
}

export function CalendarSection({ calendar }: CalendarSectionProps) {
  const { meeting_count, key_meetings } = calendar;

  if (meeting_count === 0) {
    return (
      <CollapsibleSection
        title="Calendar"
        icon={<Calendar className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Calendar className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No meetings scheduled for today</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Calendar"
      icon={<Calendar className="w-5 h-5" />}
      badge={meeting_count}
      badgeColor="primary"
    >
      <div className="space-y-3">
        {key_meetings.map((meeting, index) => (
          <button
            key={index}
            className="w-full flex items-start gap-4 p-3 bg-slate-700/30 hover:bg-slate-700/50 border border-slate-600/30 rounded-lg transition-colors text-left group"
          >
            <div className="flex-shrink-0 flex items-center justify-center w-12 h-12 bg-primary-500/10 border border-primary-500/20 rounded-lg">
              <Clock className="w-5 h-5 text-primary-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-primary-400">{meeting.time}</span>
              </div>
              <h4 className="text-white font-medium truncate group-hover:text-primary-300 transition-colors">
                {meeting.title}
              </h4>
              {meeting.attendees && meeting.attendees.length > 0 && (
                <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
                  <Users className="w-3.5 h-3.5" />
                  <span className="truncate">
                    {meeting.attendees.slice(0, 3).join(", ")}
                    {meeting.attendees.length > 3 && ` +${meeting.attendees.length - 3} more`}
                  </span>
                </div>
              )}
            </div>
          </button>
        ))}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/CalendarSection.tsx
git commit -m "feat(briefing): add calendar section component"
```

---

## Task 7: Create Leads Section Component

**Files:**
- Create: `frontend/src/components/briefing/LeadsSection.tsx`

**Step 1: Create the leads briefing section**

```typescript
import { Flame, AlertTriangle, Activity, Users } from "lucide-react";
import { Link } from "react-router-dom";
import type { BriefingLead, BriefingLeads } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface LeadsSectionProps {
  leads: BriefingLeads;
}

function LeadCard({ lead, variant }: { lead: BriefingLead; variant: "hot" | "attention" | "active" }) {
  const variantStyles = {
    hot: {
      border: "border-orange-500/30 hover:border-orange-500/50",
      icon: <Flame className="w-4 h-4 text-orange-400" />,
      bg: "bg-orange-500/10",
    },
    attention: {
      border: "border-amber-500/30 hover:border-amber-500/50",
      icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
      bg: "bg-amber-500/10",
    },
    active: {
      border: "border-green-500/30 hover:border-green-500/50",
      icon: <Activity className="w-4 h-4 text-green-400" />,
      bg: "bg-green-500/10",
    },
  };

  const style = variantStyles[variant];

  return (
    <Link
      to={`/leads/${lead.id}`}
      className={`block p-3 bg-slate-700/30 border ${style.border} rounded-lg transition-colors group`}
    >
      <div className="flex items-start gap-3">
        <div className={`flex-shrink-0 p-2 ${style.bg} rounded-lg`}>{style.icon}</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-white font-medium truncate group-hover:text-primary-300 transition-colors">
            {lead.name}
          </h4>
          <p className="text-sm text-slate-400 truncate">{lead.company}</p>
          {lead.health_score !== undefined && (
            <div className="mt-1 flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-slate-600 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    lead.health_score >= 70
                      ? "bg-green-500"
                      : lead.health_score >= 40
                        ? "bg-amber-500"
                        : "bg-red-500"
                  }`}
                  style={{ width: `${lead.health_score}%` }}
                />
              </div>
              <span className="text-xs text-slate-400">{lead.health_score}%</span>
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

export function LeadsSection({ leads }: LeadsSectionProps) {
  const { hot_leads, needs_attention, recently_active } = leads;
  const totalCount = hot_leads.length + needs_attention.length + recently_active.length;

  if (totalCount === 0) {
    return (
      <CollapsibleSection
        title="Leads"
        icon={<Users className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No lead activity to report</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Leads"
      icon={<Users className="w-5 h-5" />}
      badge={totalCount}
      badgeColor={hot_leads.length > 0 ? "amber" : "primary"}
    >
      <div className="space-y-4">
        {hot_leads.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-orange-400 uppercase tracking-wider mb-2">
              Hot Leads
            </h4>
            <div className="space-y-2">
              {hot_leads.map((lead) => (
                <LeadCard key={lead.id} lead={lead} variant="hot" />
              ))}
            </div>
          </div>
        )}

        {needs_attention.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-amber-400 uppercase tracking-wider mb-2">
              Needs Attention
            </h4>
            <div className="space-y-2">
              {needs_attention.map((lead) => (
                <LeadCard key={lead.id} lead={lead} variant="attention" />
              ))}
            </div>
          </div>
        )}

        {recently_active.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-green-400 uppercase tracking-wider mb-2">
              Recently Active
            </h4>
            <div className="space-y-2">
              {recently_active.map((lead) => (
                <LeadCard key={lead.id} lead={lead} variant="active" />
              ))}
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/LeadsSection.tsx
git commit -m "feat(briefing): add leads section component with health scores"
```

---

## Task 8: Create Signals Section Component

**Files:**
- Create: `frontend/src/components/briefing/SignalsSection.tsx`

**Step 1: Create the market signals briefing section**

```typescript
import { Radio, Building2, TrendingUp, Swords } from "lucide-react";
import type { BriefingSignal, BriefingSignals } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface SignalsSectionProps {
  signals: BriefingSignals;
}

function SignalCard({ signal }: { signal: BriefingSignal }) {
  const typeConfig = {
    company_news: {
      icon: <Building2 className="w-4 h-4 text-blue-400" />,
      bg: "bg-blue-500/10",
      border: "border-blue-500/30",
    },
    market_trend: {
      icon: <TrendingUp className="w-4 h-4 text-emerald-400" />,
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/30",
    },
    competitive_intel: {
      icon: <Swords className="w-4 h-4 text-purple-400" />,
      bg: "bg-purple-500/10",
      border: "border-purple-500/30",
    },
  };

  const config = typeConfig[signal.type];

  return (
    <div
      className={`p-3 bg-slate-700/30 border ${config.border} rounded-lg hover:bg-slate-700/50 transition-colors`}
    >
      <div className="flex items-start gap-3">
        <div className={`flex-shrink-0 p-2 ${config.bg} rounded-lg`}>{config.icon}</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-white font-medium">{signal.title}</h4>
          <p className="mt-1 text-sm text-slate-400 line-clamp-2">{signal.summary}</p>
          {signal.source && (
            <p className="mt-2 text-xs text-slate-500">Source: {signal.source}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function SignalsSection({ signals }: SignalsSectionProps) {
  const { company_news, market_trends, competitive_intel } = signals;
  const totalCount = company_news.length + market_trends.length + competitive_intel.length;

  if (totalCount === 0) {
    return (
      <CollapsibleSection
        title="Market Signals"
        icon={<Radio className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Radio className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No signals detected today</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Market Signals"
      icon={<Radio className="w-5 h-5" />}
      badge={totalCount}
      badgeColor="green"
    >
      <div className="space-y-4">
        {company_news.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-blue-400 uppercase tracking-wider mb-2">
              Company News
            </h4>
            <div className="space-y-2">
              {company_news.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          </div>
        )}

        {market_trends.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-emerald-400 uppercase tracking-wider mb-2">
              Market Trends
            </h4>
            <div className="space-y-2">
              {market_trends.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          </div>
        )}

        {competitive_intel.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-purple-400 uppercase tracking-wider mb-2">
              Competitive Intel
            </h4>
            <div className="space-y-2">
              {competitive_intel.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/SignalsSection.tsx
git commit -m "feat(briefing): add market signals section component"
```

---

## Task 9: Create Tasks Section Component

**Files:**
- Create: `frontend/src/components/briefing/TasksSection.tsx`

**Step 1: Create the tasks briefing section**

```typescript
import { CheckSquare, AlertCircle, Clock } from "lucide-react";
import type { BriefingTask, BriefingTasks } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface TasksSectionProps {
  tasks: BriefingTasks;
}

function TaskCard({
  task,
  variant,
}: {
  task: BriefingTask;
  variant: "overdue" | "today";
}) {
  const isOverdue = variant === "overdue";

  return (
    <button className="w-full flex items-center gap-3 p-3 bg-slate-700/30 hover:bg-slate-700/50 border border-slate-600/30 rounded-lg transition-colors text-left group">
      <div
        className={`flex-shrink-0 p-2 rounded-lg ${
          isOverdue ? "bg-red-500/10" : "bg-slate-600/50"
        }`}
      >
        {isOverdue ? (
          <AlertCircle className="w-4 h-4 text-red-400" />
        ) : (
          <Clock className="w-4 h-4 text-slate-400" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="text-white font-medium truncate group-hover:text-primary-300 transition-colors">
          {task.title}
        </h4>
        {task.due_date && (
          <p className={`text-xs ${isOverdue ? "text-red-400" : "text-slate-400"}`}>
            {isOverdue ? "Overdue: " : "Due: "}
            {new Date(task.due_date).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })}
          </p>
        )}
      </div>
      {task.priority && (
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            task.priority === "high"
              ? "bg-red-500/20 text-red-400"
              : task.priority === "medium"
                ? "bg-amber-500/20 text-amber-400"
                : "bg-slate-600/50 text-slate-400"
          }`}
        >
          {task.priority}
        </span>
      )}
    </button>
  );
}

export function TasksSection({ tasks }: TasksSectionProps) {
  const { overdue, due_today } = tasks;
  const totalCount = overdue.length + due_today.length;
  const hasOverdue = overdue.length > 0;

  if (totalCount === 0) {
    return (
      <CollapsibleSection
        title="Tasks"
        icon={<CheckSquare className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <CheckSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No tasks for today</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Tasks"
      icon={<CheckSquare className="w-5 h-5" />}
      badge={totalCount}
      badgeColor={hasOverdue ? "red" : "primary"}
    >
      <div className="space-y-4">
        {overdue.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-red-400 uppercase tracking-wider mb-2">
              Overdue
            </h4>
            <div className="space-y-2">
              {overdue.map((task) => (
                <TaskCard key={task.id} task={task} variant="overdue" />
              ))}
            </div>
          </div>
        )}

        {due_today.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Due Today
            </h4>
            <div className="space-y-2">
              {due_today.map((task) => (
                <TaskCard key={task.id} task={task} variant="today" />
              ))}
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/TasksSection.tsx
git commit -m "feat(briefing): add tasks section component with priority badges"
```

---

## Task 10: Create Briefing Header Component

**Files:**
- Create: `frontend/src/components/briefing/BriefingHeader.tsx`

**Step 1: Create the header with time-based greeting and refresh button**

```typescript
import { RefreshCw, History } from "lucide-react";

interface BriefingHeaderProps {
  userName?: string;
  generatedAt?: string;
  onRefresh: () => void;
  onViewHistory: () => void;
  isRefreshing?: boolean;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function formatGeneratedTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  if (isToday) {
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function BriefingHeader({
  userName,
  generatedAt,
  onRefresh,
  onViewHistory,
  isRefreshing,
}: BriefingHeaderProps) {
  const greeting = getGreeting();
  const displayName = userName?.split(" ")[0] || "there";

  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold text-white">
          {greeting}, {displayName}
        </h1>
        <p className="mt-1 text-slate-400">
          Here's your daily briefing
          {generatedAt && (
            <span className="text-slate-500">
              {" "}
              · Updated {formatGeneratedTime(generatedAt)}
            </span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onViewHistory}
          className="p-2.5 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
          title="View past briefings"
        >
          <History className="w-5 h-5" />
        </button>
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700/50 hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg border border-slate-600/50 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
          <span className="hidden sm:inline">{isRefreshing ? "Refreshing..." : "Refresh"}</span>
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/BriefingHeader.tsx
git commit -m "feat(briefing): add header component with time-based greeting"
```

---

## Task 11: Create Executive Summary Component

**Files:**
- Create: `frontend/src/components/briefing/ExecutiveSummary.tsx`

**Step 1: Create the executive summary card**

```typescript
import { Sparkles } from "lucide-react";

interface ExecutiveSummaryProps {
  summary: string;
}

export function ExecutiveSummary({ summary }: ExecutiveSummaryProps) {
  return (
    <div className="relative overflow-hidden bg-gradient-to-br from-slate-800/80 via-slate-800/60 to-primary-900/30 border border-slate-700/50 rounded-xl p-6">
      {/* Subtle gradient overlay */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />

      <div className="relative">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-5 h-5 text-primary-400" />
          <h2 className="text-sm font-medium text-primary-400 uppercase tracking-wider">
            Today's Summary
          </h2>
        </div>
        <p className="text-lg text-white leading-relaxed">{summary}</p>
      </div>
    </div>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/ExecutiveSummary.tsx
git commit -m "feat(briefing): add executive summary card component"
```

---

## Task 12: Create Briefing Index File

**Files:**
- Create: `frontend/src/components/briefing/index.ts`

**Step 1: Create barrel export for briefing components**

```typescript
export { BriefingEmpty } from "./BriefingEmpty";
export { BriefingHeader } from "./BriefingHeader";
export { BriefingSkeleton } from "./BriefingSkeleton";
export { CalendarSection } from "./CalendarSection";
export { ExecutiveSummary } from "./ExecutiveSummary";
export { LeadsSection } from "./LeadsSection";
export { SignalsSection } from "./SignalsSection";
export { TasksSection } from "./TasksSection";
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/index.ts
git commit -m "feat(briefing): add barrel export for briefing components"
```

---

## Task 13: Create Briefing History Modal

**Files:**
- Create: `frontend/src/components/briefing/BriefingHistoryModal.tsx`

**Step 1: Create the history modal for viewing past briefings**

```typescript
import { X, Calendar } from "lucide-react";
import { useBriefingList } from "@/hooks/useBriefing";

interface BriefingHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectDate: (date: string) => void;
}

export function BriefingHistoryModal({
  isOpen,
  onClose,
  onSelectDate,
}: BriefingHistoryModalProps) {
  const { data: briefings, isLoading } = useBriefingList(14);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md bg-slate-800 border border-slate-700 rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Past Briefings</h2>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 max-h-96 overflow-y-auto">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-14 bg-slate-700/50 rounded-lg animate-pulse"
                />
              ))}
            </div>
          ) : briefings && briefings.length > 0 ? (
            <div className="space-y-2">
              {briefings.map((briefing) => {
                const date = new Date(briefing.briefing_date);
                const isToday =
                  date.toDateString() === new Date().toDateString();

                return (
                  <button
                    key={briefing.id}
                    onClick={() => {
                      onSelectDate(briefing.briefing_date);
                      onClose();
                    }}
                    className="w-full flex items-center gap-3 p-3 bg-slate-700/30 hover:bg-slate-700/50 border border-slate-600/30 rounded-lg transition-colors text-left"
                  >
                    <div className="flex-shrink-0 p-2 bg-slate-600/50 rounded-lg">
                      <Calendar className="w-4 h-4 text-slate-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-white font-medium">
                        {date.toLocaleDateString("en-US", {
                          weekday: "long",
                          month: "short",
                          day: "numeric",
                        })}
                        {isToday && (
                          <span className="ml-2 text-xs text-primary-400">
                            Today
                          </span>
                        )}
                      </h4>
                      <p className="text-sm text-slate-400 truncate">
                        {briefing.content.summary?.slice(0, 60)}...
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-slate-400">
              <Calendar className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No past briefings found</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-4 border-t border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Add export to barrel file**

In `frontend/src/components/briefing/index.ts`, add:
```typescript
export { BriefingHistoryModal } from "./BriefingHistoryModal";
```

**Step 3: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/briefing/BriefingHistoryModal.tsx frontend/src/components/briefing/index.ts
git commit -m "feat(briefing): add history modal for past briefings"
```

---

## Task 14: Update Dashboard Page with Briefing UI

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Replace the placeholder dashboard with the briefing UI**

```typescript
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  BriefingEmpty,
  BriefingHeader,
  BriefingHistoryModal,
  BriefingSkeleton,
  CalendarSection,
  ExecutiveSummary,
  LeadsSection,
  SignalsSection,
  TasksSection,
} from "@/components/briefing";
import { useTodayBriefing, useRegenerateBriefing, useBriefingByDate } from "@/hooks/useBriefing";
import { useAuth } from "@/hooks/useAuth";

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const {
    data: todayBriefing,
    isLoading: isTodayLoading,
    error: todayError,
  } = useTodayBriefing();

  const { data: historicalBriefing, isLoading: isHistoricalLoading } =
    useBriefingByDate(selectedDate || "");

  const regenerateMutation = useRegenerateBriefing();

  // Use historical briefing if selected, otherwise today's
  const briefing = selectedDate ? historicalBriefing?.content : todayBriefing;
  const isLoading = selectedDate ? isHistoricalLoading : isTodayLoading;

  const handleRefresh = () => {
    setSelectedDate(null); // Clear historical selection
    regenerateMutation.mutate();
  };

  const handleSelectHistoricalDate = (date: string) => {
    const today = new Date().toISOString().split("T")[0];
    if (date === today) {
      setSelectedDate(null);
    } else {
      setSelectedDate(date);
    }
  };

  const handleViewHistory = () => {
    setIsHistoryOpen(true);
  };

  // Refetch on window focus
  // useEffect(() => {
  //   const handleFocus = () => {
  //     if (!selectedDate) {
  //       queryClient.invalidateQueries({ queryKey: briefingKeys.today() });
  //     }
  //   };
  //   window.addEventListener("focus", handleFocus);
  //   return () => window.removeEventListener("focus", handleFocus);
  // }, [selectedDate, queryClient]);

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <BriefingHeader
            userName={user?.full_name}
            generatedAt={briefing?.generated_at}
            onRefresh={handleRefresh}
            onViewHistory={handleViewHistory}
            isRefreshing={regenerateMutation.isPending}
          />

          {/* Historical indicator */}
          {selectedDate && (
            <div className="mt-4 flex items-center gap-2 px-4 py-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
              <span className="text-amber-400 text-sm">
                Viewing briefing from{" "}
                {new Date(selectedDate).toLocaleDateString("en-US", {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })}
              </span>
              <button
                onClick={() => setSelectedDate(null)}
                className="ml-auto text-xs text-amber-400 hover:text-amber-300 underline"
              >
                Return to today
              </button>
            </div>
          )}

          {/* Content */}
          <div className="mt-6 space-y-6">
            {isLoading ? (
              <BriefingSkeleton />
            ) : todayError && !selectedDate ? (
              <BriefingEmpty
                onGenerate={() => regenerateMutation.mutate()}
                isGenerating={regenerateMutation.isPending}
              />
            ) : briefing ? (
              <>
                {/* Executive Summary */}
                <ExecutiveSummary summary={briefing.summary} />

                {/* Collapsible Sections */}
                <div className="space-y-4">
                  <CalendarSection calendar={briefing.calendar} />
                  <LeadsSection leads={briefing.leads} />
                  <SignalsSection signals={briefing.signals} />
                  <TasksSection tasks={briefing.tasks} />
                </div>
              </>
            ) : (
              <BriefingEmpty
                onGenerate={() => regenerateMutation.mutate()}
                isGenerating={regenerateMutation.isPending}
              />
            )}
          </div>
        </div>
      </div>

      {/* History Modal */}
      <BriefingHistoryModal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        onSelectDate={handleSelectHistoricalDate}
      />
    </DashboardLayout>
  );
}
```

**Step 2: Verify file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): integrate daily briefing as hero content"
```

---

## Task 15: Install Lucide React Icons

**Files:**
- Modify: `frontend/package.json`

**Step 1: Check if lucide-react is already installed**

Run: `cd frontend && grep lucide package.json`

**Step 2: If not installed, install it**

Run: `cd frontend && npm install lucide-react`

**Step 3: Verify installation**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 4: Commit if changes were made**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add lucide-react icons library"
```

---

## Task 16: Run Full TypeScript Check and Fix Any Errors

**Files:**
- Potentially multiple files if type errors exist

**Step 1: Run full typecheck**

Run: `cd frontend && npm run typecheck`

**Step 2: Fix any errors reported**

Review each error and fix as needed. Common fixes:
- Missing imports
- Type mismatches
- Undefined properties

**Step 3: Run lint check**

Run: `cd frontend && npm run lint`

**Step 4: Fix any lint errors**

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve typecheck and lint errors in briefing components"
```

---

## Task 17: Test the UI Manually

**Files:** None (manual testing)

**Step 1: Start the backend server**

Run: `cd backend && uvicorn src.main:app --reload --port 8000`

**Step 2: Start the frontend dev server**

Run: `cd frontend && npm run dev`

**Step 3: Test the following scenarios**

1. Navigate to `/dashboard` - should see briefing or empty state
2. Click "Generate briefing" if empty state shown
3. Verify executive summary displays
4. Expand/collapse each section (Calendar, Leads, Signals, Tasks)
5. Click refresh button - should regenerate briefing
6. Open history modal - should list past briefings
7. Select a past briefing - should display historical content
8. Click "Return to today" - should go back to current briefing

**Step 4: Verify responsive design**

- Test on mobile viewport width (< 640px)
- Test on tablet viewport width (640px - 1024px)
- Test on desktop viewport width (> 1024px)

**Step 5: Document any issues found**

If issues are found, create additional fix commits.

---

## Task 18: Final Commit and Summary

**Files:** None

**Step 1: Verify all changes are committed**

Run: `git status`
Expected: Clean working tree

**Step 2: Review commit history**

Run: `git log --oneline -15`
Expected: All briefing-related commits visible

**Step 3: Create summary of changes**

The US-405 Daily Briefing UI implementation includes:
- `api/briefings.ts` - API client with full TypeScript types
- `hooks/useBriefing.ts` - React Query hooks for data fetching
- `components/ui/CollapsibleSection.tsx` - Reusable collapsible section
- `components/briefing/` - All briefing-specific components:
  - `BriefingHeader.tsx` - Time-based greeting with refresh/history buttons
  - `ExecutiveSummary.tsx` - Highlighted summary card
  - `CalendarSection.tsx` - Meetings with attendees
  - `LeadsSection.tsx` - Hot/attention/active leads with health scores
  - `SignalsSection.tsx` - Company news/trends/competitive intel
  - `TasksSection.tsx` - Overdue and due-today tasks
  - `BriefingSkeleton.tsx` - Loading state
  - `BriefingEmpty.tsx` - Empty state with CTA
  - `BriefingHistoryModal.tsx` - Historical briefings browser
- `pages/Dashboard.tsx` - Updated to display briefing as hero content

---

Plan complete and saved to `docs/plans/2026-02-02-us-405-daily-briefing-ui.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
