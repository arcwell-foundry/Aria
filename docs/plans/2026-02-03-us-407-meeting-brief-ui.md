# US-407: Meeting Brief UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a premium, Apple-inspired Meeting Brief UI that displays pre-meeting research with attendee profiles, company intel, talking points, and exportable briefs.

**Architecture:** React components following existing ARIA patterns (CollapsibleSection, BriefingSkeleton). Two entry points: (1) MeetingBriefCard in dashboard CalendarSection linking to briefs, (2) dedicated `/dashboard/meetings/:id/brief` route for full brief view. Uses React Query for caching with polling for generating status.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, React Query v5, Lucide icons, existing ARIA design system

---

## Task 1: Create TypeScript Types for Meeting Briefs

**Files:**
- Create: `frontend/src/api/meetingBriefs.ts`

**Step 1: Write the API types and functions file**

```typescript
import { apiClient } from "./client";

// Status enum matching backend BriefStatus
export type MeetingBriefStatus = "pending" | "generating" | "completed" | "failed";

// Attendee profile with research data
export interface AttendeeProfile {
  email: string;
  name: string | null;
  title: string | null;
  company: string | null;
  linkedin_url: string | null;
  background: string | null;
  recent_activity: string[];
  talking_points: string[];
}

// Company research data
export interface CompanyResearch {
  name: string;
  industry: string | null;
  size: string | null;
  recent_news: string[];
  our_history: string | null;
}

// Full brief content structure
export interface MeetingBriefContent {
  summary: string;
  attendees: AttendeeProfile[];
  company: CompanyResearch | null;
  suggested_agenda: string[];
  risks_opportunities: string[];
}

// API response model
export interface MeetingBriefResponse {
  id: string;
  calendar_event_id: string;
  meeting_title: string | null;
  meeting_time: string;
  status: MeetingBriefStatus;
  brief_content: MeetingBriefContent | Record<string, never>;
  generated_at: string | null;
  error_message: string | null;
}

// Upcoming meeting with brief status
export interface UpcomingMeeting {
  calendar_event_id: string;
  meeting_title: string | null;
  meeting_time: string;
  attendees: string[];
  brief_status: MeetingBriefStatus | null;
  brief_id: string | null;
}

// Request to generate brief
export interface GenerateBriefRequest {
  meeting_title: string | null;
  meeting_time: string;
  attendee_emails: string[];
}

// User notes for a brief
export interface BriefNotes {
  content: string;
  updated_at: string;
}

// API functions
export async function getMeetingBrief(calendarEventId: string): Promise<MeetingBriefResponse> {
  const response = await apiClient.get<MeetingBriefResponse>(
    `/meetings/${encodeURIComponent(calendarEventId)}/brief`
  );
  return response.data;
}

export async function getUpcomingMeetings(limit = 10): Promise<UpcomingMeeting[]> {
  const response = await apiClient.get<UpcomingMeeting[]>(
    `/meetings/upcoming?limit=${limit}`
  );
  return response.data;
}

export async function generateMeetingBrief(
  calendarEventId: string,
  request: GenerateBriefRequest
): Promise<MeetingBriefResponse> {
  const response = await apiClient.post<MeetingBriefResponse>(
    `/meetings/${encodeURIComponent(calendarEventId)}/brief/generate`,
    request
  );
  return response.data;
}
```

**Step 2: Run typecheck to verify**

Run: `cd frontend && npm run typecheck`
Expected: PASS (no type errors)

**Step 3: Commit**

```bash
git add frontend/src/api/meetingBriefs.ts
git commit -m "feat(ui): add meeting brief API types and functions"
```

---

## Task 2: Create React Query Hooks for Meeting Briefs

**Files:**
- Create: `frontend/src/hooks/useMeetingBrief.ts`

**Step 1: Write the hooks file**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  generateMeetingBrief,
  getMeetingBrief,
  getUpcomingMeetings,
  type GenerateBriefRequest,
} from "@/api/meetingBriefs";

// Query keys factory
export const meetingBriefKeys = {
  all: ["meetingBriefs"] as const,
  brief: (calendarEventId: string) => [...meetingBriefKeys.all, "brief", calendarEventId] as const,
  upcoming: (limit: number) => [...meetingBriefKeys.all, "upcoming", { limit }] as const,
};

// Get meeting brief by calendar event ID
export function useMeetingBrief(calendarEventId: string) {
  return useQuery({
    queryKey: meetingBriefKeys.brief(calendarEventId),
    queryFn: () => getMeetingBrief(calendarEventId),
    enabled: !!calendarEventId,
    staleTime: 1000 * 60 * 2, // 2 minutes
    // Poll while generating
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "generating" || status === "pending") {
        return 3000; // Poll every 3 seconds while generating
      }
      return false;
    },
  });
}

// Get upcoming meetings with brief status
export function useUpcomingMeetings(limit = 10) {
  return useQuery({
    queryKey: meetingBriefKeys.upcoming(limit),
    queryFn: () => getUpcomingMeetings(limit),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

// Generate or regenerate a meeting brief
export function useGenerateMeetingBrief() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      calendarEventId,
      request,
    }: {
      calendarEventId: string;
      request: GenerateBriefRequest;
    }) => generateMeetingBrief(calendarEventId, request),
    onSuccess: (data, { calendarEventId }) => {
      // Update the brief cache
      queryClient.setQueryData(meetingBriefKeys.brief(calendarEventId), data);
      // Invalidate upcoming meetings to refresh status
      queryClient.invalidateQueries({ queryKey: meetingBriefKeys.all });
    },
  });
}
```

**Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/hooks/useMeetingBrief.ts
git commit -m "feat(ui): add React Query hooks for meeting briefs"
```

---

## Task 3: Create MeetingBriefSkeleton Component

**Files:**
- Create: `frontend/src/components/meetingBrief/MeetingBriefSkeleton.tsx`
- Create: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the skeleton component**

```typescript
export function MeetingBriefSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="h-8 w-72 bg-slate-700/50 rounded-lg" />
          <div className="h-5 w-48 bg-slate-700/30 rounded" />
        </div>
        <div className="flex gap-2">
          <div className="h-10 w-24 bg-slate-700/30 rounded-lg" />
          <div className="h-10 w-10 bg-slate-700/30 rounded-lg" />
        </div>
      </div>

      {/* Summary skeleton */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
        <div className="space-y-3">
          <div className="h-4 w-full bg-slate-700/50 rounded" />
          <div className="h-4 w-5/6 bg-slate-700/50 rounded" />
          <div className="h-4 w-4/6 bg-slate-700/50 rounded" />
        </div>
      </div>

      {/* Attendees skeleton */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl">
        <div className="p-4 flex items-center gap-3">
          <div className="w-5 h-5 bg-slate-700/50 rounded" />
          <div className="h-5 w-24 bg-slate-700/50 rounded" />
          <div className="h-5 w-6 bg-slate-700/30 rounded-full" />
        </div>
        <div className="px-4 pb-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="bg-slate-700/30 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-slate-600/50 rounded-full" />
                <div className="space-y-2 flex-1">
                  <div className="h-4 w-32 bg-slate-600/50 rounded" />
                  <div className="h-3 w-24 bg-slate-600/30 rounded" />
                </div>
              </div>
              <div className="h-12 bg-slate-600/30 rounded" />
              <div className="flex gap-2">
                <div className="h-6 w-20 bg-slate-600/30 rounded-full" />
                <div className="h-6 w-24 bg-slate-600/30 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Company & Agenda skeletons */}
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-slate-800/50 border border-slate-700/50 rounded-xl">
          <div className="p-4 flex items-center gap-3">
            <div className="w-5 h-5 bg-slate-700/50 rounded" />
            <div className="h-5 w-32 bg-slate-700/50 rounded" />
          </div>
          <div className="px-4 pb-4 space-y-2">
            <div className="h-4 w-full bg-slate-700/30 rounded" />
            <div className="h-4 w-3/4 bg-slate-700/30 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Create barrel export**

```typescript
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add MeetingBriefSkeleton component"
```

---

## Task 4: Create MeetingBriefEmpty Component

**Files:**
- Create: `frontend/src/components/meetingBrief/MeetingBriefEmpty.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the empty state component**

```typescript
import { FileText, RefreshCw } from "lucide-react";

interface MeetingBriefEmptyProps {
  meetingTitle?: string | null;
  onGenerate: () => void;
  isGenerating?: boolean;
}

export function MeetingBriefEmpty({
  meetingTitle,
  onGenerate,
  isGenerating,
}: MeetingBriefEmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Illustration */}
      <div className="relative">
        <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
        <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
          <FileText className="w-12 h-12 text-primary-400" />
        </div>
      </div>

      {/* Text */}
      <h3 className="mt-6 text-xl font-semibold text-white">No brief yet</h3>
      <p className="mt-2 text-slate-400 text-center max-w-md">
        {meetingTitle ? (
          <>
            ARIA hasn't prepared your brief for <span className="text-white">{meetingTitle}</span>{" "}
            yet. Generate one to see attendee profiles, company intel, and talking points.
          </>
        ) : (
          <>
            ARIA hasn't prepared a brief for this meeting yet. Generate one to see attendee
            profiles, company intel, and talking points.
          </>
        )}
      </p>

      {/* CTA */}
      <button
        onClick={onGenerate}
        disabled={isGenerating}
        className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
      >
        <RefreshCw className={`w-5 h-5 ${isGenerating ? "animate-spin" : ""}`} />
        {isGenerating ? "Generating..." : "Generate brief"}
      </button>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add MeetingBriefEmpty component"
```

---

## Task 5: Create MeetingBriefHeader Component

**Files:**
- Create: `frontend/src/components/meetingBrief/MeetingBriefHeader.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the header component**

```typescript
import { ArrowLeft, Calendar, Clock, Printer, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import type { MeetingBriefStatus } from "@/api/meetingBriefs";

interface MeetingBriefHeaderProps {
  meetingTitle: string | null;
  meetingTime: string;
  status: MeetingBriefStatus;
  generatedAt: string | null;
  onRefresh: () => void;
  onPrint: () => void;
  isRefreshing?: boolean;
}

function formatMeetingTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatGeneratedTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function StatusBadge({ status }: { status: MeetingBriefStatus }) {
  const styles = {
    pending: "bg-slate-600/50 text-slate-300",
    generating: "bg-amber-500/20 text-amber-400",
    completed: "bg-green-500/20 text-green-400",
    failed: "bg-red-500/20 text-red-400",
  };

  const labels = {
    pending: "Pending",
    generating: "Generating...",
    completed: "Ready",
    failed: "Failed",
  };

  return (
    <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

export function MeetingBriefHeader({
  meetingTitle,
  meetingTime,
  status,
  generatedAt,
  onRefresh,
  onPrint,
  isRefreshing,
}: MeetingBriefHeaderProps) {
  return (
    <div className="space-y-4">
      {/* Back link */}
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </Link>

      {/* Title row */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white">
              {meetingTitle || "Meeting Brief"}
            </h1>
            <StatusBadge status={status} />
          </div>
          <div className="flex items-center gap-4 text-sm text-slate-400">
            <span className="flex items-center gap-1.5">
              <Calendar className="w-4 h-4" />
              {formatMeetingTime(meetingTime)}
            </span>
            {generatedAt && (
              <span className="flex items-center gap-1.5">
                <Clock className="w-4 h-4" />
                Updated {formatGeneratedTime(generatedAt)}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={onPrint}
            className="p-2.5 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
            title="Print brief"
          >
            <Printer className="w-5 h-5" />
          </button>
          <button
            onClick={onRefresh}
            disabled={isRefreshing || status === "generating"}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700/50 hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg border border-slate-600/50 transition-colors"
          >
            <RefreshCw
              className={`w-4 h-4 ${isRefreshing || status === "generating" ? "animate-spin" : ""}`}
            />
            <span className="hidden sm:inline">
              {status === "generating" ? "Generating..." : "Regenerate"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add MeetingBriefHeader component"
```

---

## Task 6: Create BriefSummary Component

**Files:**
- Create: `frontend/src/components/meetingBrief/BriefSummary.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the summary component**

```typescript
import { FileText } from "lucide-react";

interface BriefSummaryProps {
  summary: string;
}

export function BriefSummary({ summary }: BriefSummaryProps) {
  if (!summary) return null;

  return (
    <div className="relative overflow-hidden bg-gradient-to-br from-slate-800/80 via-slate-800/60 to-primary-900/30 border border-slate-700/50 rounded-xl p-6">
      {/* Subtle gradient overlay */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />

      <div className="relative">
        <div className="flex items-center gap-2 mb-3">
          <FileText className="w-5 h-5 text-primary-400" />
          <h2 className="text-sm font-medium text-primary-400 uppercase tracking-wider">
            Meeting Context
          </h2>
        </div>
        <p className="text-lg text-white leading-relaxed">{summary}</p>
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { BriefSummary } from "./BriefSummary";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add BriefSummary component"
```

---

## Task 7: Create AttendeeCard Component

**Files:**
- Create: `frontend/src/components/meetingBrief/AttendeeCard.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the attendee card component**

```typescript
import { Building2, ExternalLink, MessageCircle, User } from "lucide-react";
import type { AttendeeProfile } from "@/api/meetingBriefs";

interface AttendeeCardProps {
  attendee: AttendeeProfile;
}

function getInitials(name: string | null, email: string): string {
  if (name) {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  }
  return email[0].toUpperCase();
}

function getAvatarColor(email: string): string {
  const colors = [
    "from-blue-500 to-blue-600",
    "from-purple-500 to-purple-600",
    "from-emerald-500 to-emerald-600",
    "from-amber-500 to-amber-600",
    "from-rose-500 to-rose-600",
    "from-cyan-500 to-cyan-600",
  ];
  const index = email.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[index % colors.length];
}

export function AttendeeCard({ attendee }: AttendeeCardProps) {
  const { name, email, title, company, linkedin_url, background, recent_activity, talking_points } =
    attendee;

  return (
    <div className="bg-slate-700/30 border border-slate-600/30 rounded-xl p-5 space-y-4 hover:border-slate-500/50 transition-colors">
      {/* Header with avatar */}
      <div className="flex items-start gap-4">
        <div
          className={`flex-shrink-0 w-14 h-14 rounded-full bg-gradient-to-br ${getAvatarColor(email)} flex items-center justify-center shadow-lg`}
        >
          <span className="text-lg font-semibold text-white">{getInitials(name, email)}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-white font-semibold truncate">{name || email}</h4>
            {linkedin_url && (
              <a
                href={linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-slate-400 hover:text-primary-400 transition-colors"
                title="View LinkedIn profile"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
          </div>
          {title && (
            <div className="flex items-center gap-1.5 mt-0.5 text-sm text-slate-400">
              <User className="w-3.5 h-3.5" />
              <span className="truncate">{title}</span>
            </div>
          )}
          {company && (
            <div className="flex items-center gap-1.5 mt-0.5 text-sm text-slate-400">
              <Building2 className="w-3.5 h-3.5" />
              <span className="truncate">{company}</span>
            </div>
          )}
        </div>
      </div>

      {/* Background */}
      {background && (
        <div className="text-sm text-slate-300 leading-relaxed">{background}</div>
      )}

      {/* Recent activity */}
      {recent_activity.length > 0 && (
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            Recent Activity
          </h5>
          <ul className="space-y-1.5">
            {recent_activity.slice(0, 3).map((activity, i) => (
              <li key={i} className="text-sm text-slate-300 flex items-start gap-2">
                <span className="text-primary-400 mt-1.5">•</span>
                {activity}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Talking points */}
      {talking_points.length > 0 && (
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            <MessageCircle className="w-3.5 h-3.5" />
            Talking Points
          </h5>
          <div className="flex flex-wrap gap-2">
            {talking_points.map((point, i) => (
              <span
                key={i}
                className="px-3 py-1.5 text-sm bg-primary-500/10 text-primary-300 border border-primary-500/20 rounded-full"
              >
                {point}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { AttendeeCard } from "./AttendeeCard";
export { BriefSummary } from "./BriefSummary";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add AttendeeCard component with avatar and talking points"
```

---

## Task 8: Create AttendeesSection Component

**Files:**
- Create: `frontend/src/components/meetingBrief/AttendeesSection.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the attendees section component**

```typescript
import { Users } from "lucide-react";
import type { AttendeeProfile } from "@/api/meetingBriefs";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { AttendeeCard } from "./AttendeeCard";

interface AttendeesSectionProps {
  attendees: AttendeeProfile[];
}

export function AttendeesSection({ attendees }: AttendeesSectionProps) {
  if (attendees.length === 0) {
    return (
      <CollapsibleSection
        title="Attendees"
        icon={<Users className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No attendee information available</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Attendees"
      icon={<Users className="w-5 h-5" />}
      badge={attendees.length}
      badgeColor="primary"
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {attendees.map((attendee) => (
          <AttendeeCard key={attendee.email} attendee={attendee} />
        ))}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { AttendeeCard } from "./AttendeeCard";
export { AttendeesSection } from "./AttendeesSection";
export { BriefSummary } from "./BriefSummary";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add AttendeesSection component"
```

---

## Task 9: Create CompanySection Component

**Files:**
- Create: `frontend/src/components/meetingBrief/CompanySection.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the company section component**

```typescript
import { Building2, Newspaper, Users2 } from "lucide-react";
import type { CompanyResearch } from "@/api/meetingBriefs";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface CompanySectionProps {
  company: CompanyResearch | null;
}

export function CompanySection({ company }: CompanySectionProps) {
  if (!company) {
    return null;
  }

  const { name, industry, size, recent_news, our_history } = company;

  return (
    <CollapsibleSection
      title="Company Intel"
      icon={<Building2 className="w-5 h-5" />}
      badge={name}
      badgeColor="primary"
    >
      <div className="space-y-5">
        {/* Company overview */}
        <div className="flex items-start gap-4 p-4 bg-slate-700/30 border border-slate-600/30 rounded-xl">
          <div className="flex-shrink-0 w-12 h-12 bg-slate-600/50 rounded-xl flex items-center justify-center">
            <Building2 className="w-6 h-6 text-slate-300" />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-lg font-semibold text-white">{name}</h4>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-slate-400">
              {industry && (
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-primary-400 rounded-full" />
                  {industry}
                </span>
              )}
              {size && (
                <span className="flex items-center gap-1.5">
                  <Users2 className="w-3.5 h-3.5" />
                  {size} employees
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Our history with this company */}
        {our_history && (
          <div className="space-y-2">
            <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Our History
            </h5>
            <p className="text-sm text-slate-300 leading-relaxed">{our_history}</p>
          </div>
        )}

        {/* Recent news */}
        {recent_news.length > 0 && (
          <div className="space-y-3">
            <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Newspaper className="w-3.5 h-3.5" />
              Recent News
            </h5>
            <ul className="space-y-2">
              {recent_news.slice(0, 5).map((news, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 p-3 bg-slate-700/20 border border-slate-600/20 rounded-lg"
                >
                  <span className="flex-shrink-0 w-1.5 h-1.5 mt-2 bg-amber-400 rounded-full" />
                  <span className="text-sm text-slate-300">{news}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { AttendeeCard } from "./AttendeeCard";
export { AttendeesSection } from "./AttendeesSection";
export { BriefSummary } from "./BriefSummary";
export { CompanySection } from "./CompanySection";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add CompanySection component"
```

---

## Task 10: Create AgendaSection Component

**Files:**
- Create: `frontend/src/components/meetingBrief/AgendaSection.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the agenda section component**

```typescript
import { ListChecks } from "lucide-react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface AgendaSectionProps {
  agenda: string[];
}

export function AgendaSection({ agenda }: AgendaSectionProps) {
  if (agenda.length === 0) {
    return null;
  }

  return (
    <CollapsibleSection
      title="Suggested Agenda"
      icon={<ListChecks className="w-5 h-5" />}
      badge={agenda.length}
      badgeColor="green"
    >
      <ol className="space-y-3">
        {agenda.map((item, i) => (
          <li key={i} className="flex items-start gap-4 p-3 bg-slate-700/30 border border-slate-600/30 rounded-lg">
            <span className="flex-shrink-0 w-7 h-7 bg-green-500/20 text-green-400 rounded-full flex items-center justify-center text-sm font-semibold">
              {i + 1}
            </span>
            <span className="text-slate-200 pt-0.5">{item}</span>
          </li>
        ))}
      </ol>
    </CollapsibleSection>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { AgendaSection } from "./AgendaSection";
export { AttendeeCard } from "./AttendeeCard";
export { AttendeesSection } from "./AttendeesSection";
export { BriefSummary } from "./BriefSummary";
export { CompanySection } from "./CompanySection";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add AgendaSection component"
```

---

## Task 11: Create RisksOpportunitiesSection Component

**Files:**
- Create: `frontend/src/components/meetingBrief/RisksOpportunitiesSection.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the risks/opportunities section component**

```typescript
import { AlertTriangle, Lightbulb } from "lucide-react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface RisksOpportunitiesSectionProps {
  items: string[];
}

export function RisksOpportunitiesSection({ items }: RisksOpportunitiesSectionProps) {
  if (items.length === 0) {
    return null;
  }

  // Simple heuristic: items with warning keywords are risks, others are opportunities
  const riskKeywords = ["risk", "concern", "challenge", "issue", "problem", "caution", "careful", "avoid", "don't", "not"];

  const categorized = items.map((item) => {
    const lowerItem = item.toLowerCase();
    const isRisk = riskKeywords.some((keyword) => lowerItem.includes(keyword));
    return { text: item, isRisk };
  });

  return (
    <CollapsibleSection
      title="Risks & Opportunities"
      icon={<Lightbulb className="w-5 h-5" />}
      badge={items.length}
      badgeColor="amber"
    >
      <div className="space-y-3">
        {categorized.map((item, i) => (
          <div
            key={i}
            className={`flex items-start gap-3 p-3 rounded-lg border ${
              item.isRisk
                ? "bg-red-500/10 border-red-500/20"
                : "bg-emerald-500/10 border-emerald-500/20"
            }`}
          >
            {item.isRisk ? (
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            ) : (
              <Lightbulb className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
            )}
            <span className={item.isRisk ? "text-red-200" : "text-emerald-200"}>
              {item.text}
            </span>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { AgendaSection } from "./AgendaSection";
export { AttendeeCard } from "./AttendeeCard";
export { AttendeesSection } from "./AttendeesSection";
export { BriefSummary } from "./BriefSummary";
export { CompanySection } from "./CompanySection";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
export { RisksOpportunitiesSection } from "./RisksOpportunitiesSection";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add RisksOpportunitiesSection component"
```

---

## Task 12: Create BriefNotesSection Component

**Files:**
- Create: `frontend/src/components/meetingBrief/BriefNotesSection.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the notes section component**

```typescript
import { Edit3, StickyNote } from "lucide-react";
import { useState } from "react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface BriefNotesSectionProps {
  initialNotes?: string;
  onSave?: (notes: string) => void;
}

export function BriefNotesSection({ initialNotes = "", onSave }: BriefNotesSectionProps) {
  const [notes, setNotes] = useState(initialNotes);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    if (onSave) {
      setIsSaving(true);
      try {
        await onSave(notes);
      } finally {
        setIsSaving(false);
      }
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setNotes(initialNotes);
    setIsEditing(false);
  };

  return (
    <CollapsibleSection
      title="Your Notes"
      icon={<StickyNote className="w-5 h-5" />}
      badgeColor="slate"
      defaultExpanded={!!initialNotes}
    >
      <div className="space-y-3">
        {isEditing ? (
          <>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add your notes for this meeting..."
              className="w-full h-32 px-4 py-3 bg-slate-700/50 border border-slate-600/50 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none"
              autoFocus
            />
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="px-4 py-2 text-sm bg-primary-600 hover:bg-primary-500 disabled:opacity-60 text-white font-medium rounded-lg transition-colors"
              >
                {isSaving ? "Saving..." : "Save notes"}
              </button>
            </div>
          </>
        ) : (
          <div
            onClick={() => setIsEditing(true)}
            className="group cursor-pointer p-4 bg-slate-700/30 border border-slate-600/30 hover:border-primary-500/30 rounded-lg transition-colors"
          >
            {notes ? (
              <p className="text-slate-300 whitespace-pre-wrap">{notes}</p>
            ) : (
              <div className="flex items-center gap-2 text-slate-400 group-hover:text-primary-400 transition-colors">
                <Edit3 className="w-4 h-4" />
                <span>Click to add notes...</span>
              </div>
            )}
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { AgendaSection } from "./AgendaSection";
export { AttendeeCard } from "./AttendeeCard";
export { AttendeesSection } from "./AttendeesSection";
export { BriefNotesSection } from "./BriefNotesSection";
export { BriefSummary } from "./BriefSummary";
export { CompanySection } from "./CompanySection";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
export { RisksOpportunitiesSection } from "./RisksOpportunitiesSection";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add BriefNotesSection component with inline editing"
```

---

## Task 13: Create GeneratingOverlay Component

**Files:**
- Create: `frontend/src/components/meetingBrief/GeneratingOverlay.tsx`
- Modify: `frontend/src/components/meetingBrief/index.ts`

**Step 1: Write the generating overlay component**

```typescript
import { Loader2 } from "lucide-react";

export function GeneratingOverlay() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Animated spinner */}
      <div className="relative">
        <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full animate-pulse" />
        <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
          <Loader2 className="w-12 h-12 text-primary-400 animate-spin" />
        </div>
      </div>

      {/* Text */}
      <h3 className="mt-6 text-xl font-semibold text-white">Generating your brief</h3>
      <p className="mt-2 text-slate-400 text-center max-w-md">
        ARIA is researching attendees, gathering company intel, and preparing talking points.
        This usually takes 15-30 seconds.
      </p>

      {/* Progress indicators */}
      <div className="mt-8 space-y-3 w-full max-w-sm">
        {["Researching attendees", "Gathering company intel", "Analyzing relationships", "Preparing talking points"].map(
          (step, i) => (
            <div key={step} className="flex items-center gap-3">
              <div
                className={`w-2 h-2 rounded-full ${
                  i < 2 ? "bg-primary-400" : "bg-slate-600"
                } ${i === 1 ? "animate-pulse" : ""}`}
              />
              <span className={`text-sm ${i < 2 ? "text-slate-300" : "text-slate-500"}`}>
                {step}
              </span>
            </div>
          )
        )}
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
export { AgendaSection } from "./AgendaSection";
export { AttendeeCard } from "./AttendeeCard";
export { AttendeesSection } from "./AttendeesSection";
export { BriefNotesSection } from "./BriefNotesSection";
export { BriefSummary } from "./BriefSummary";
export { CompanySection } from "./CompanySection";
export { GeneratingOverlay } from "./GeneratingOverlay";
export { MeetingBriefEmpty } from "./MeetingBriefEmpty";
export { MeetingBriefHeader } from "./MeetingBriefHeader";
export { MeetingBriefSkeleton } from "./MeetingBriefSkeleton";
export { RisksOpportunitiesSection } from "./RisksOpportunitiesSection";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/meetingBrief/
git commit -m "feat(ui): add GeneratingOverlay component"
```

---

## Task 14: Create MeetingBriefPage Component

**Files:**
- Create: `frontend/src/pages/MeetingBrief.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Write the page component**

```typescript
import { useCallback } from "react";
import { useParams } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  AgendaSection,
  AttendeesSection,
  BriefNotesSection,
  BriefSummary,
  CompanySection,
  GeneratingOverlay,
  MeetingBriefEmpty,
  MeetingBriefHeader,
  MeetingBriefSkeleton,
  RisksOpportunitiesSection,
} from "@/components/meetingBrief";
import { useMeetingBrief, useGenerateMeetingBrief } from "@/hooks/useMeetingBrief";
import type { MeetingBriefContent } from "@/api/meetingBriefs";

function isBriefContentPopulated(content: MeetingBriefContent | Record<string, never>): content is MeetingBriefContent {
  return "summary" in content && typeof content.summary === "string" && content.summary.length > 0;
}

export function MeetingBriefPage() {
  const { id: calendarEventId } = useParams<{ id: string }>();
  const { data: brief, isLoading, error } = useMeetingBrief(calendarEventId || "");
  const generateBrief = useGenerateMeetingBrief();

  const handleGenerate = useCallback(() => {
    if (!calendarEventId || !brief) return;

    generateBrief.mutate({
      calendarEventId,
      request: {
        meeting_title: brief.meeting_title,
        meeting_time: brief.meeting_time,
        attendee_emails: [], // Backend will use existing attendees
      },
    });
  }, [calendarEventId, brief, generateBrief]);

  const handleRefresh = useCallback(() => {
    handleGenerate();
  }, [handleGenerate]);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  if (!calendarEventId) {
    return (
      <DashboardLayout>
        <div className="p-4 lg:p-8">
          <div className="max-w-4xl mx-auto text-center py-16">
            <p className="text-slate-400">No meeting ID provided</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8">
        <div className="max-w-4xl mx-auto">
          {isLoading ? (
            <MeetingBriefSkeleton />
          ) : error ? (
            <MeetingBriefEmpty
              onGenerate={handleGenerate}
              isGenerating={generateBrief.isPending}
            />
          ) : brief ? (
            <>
              {/* Header */}
              <MeetingBriefHeader
                meetingTitle={brief.meeting_title}
                meetingTime={brief.meeting_time}
                status={brief.status}
                generatedAt={brief.generated_at}
                onRefresh={handleRefresh}
                onPrint={handlePrint}
                isRefreshing={generateBrief.isPending}
              />

              {/* Content */}
              <div className="mt-6 space-y-6">
                {brief.status === "generating" || brief.status === "pending" ? (
                  <GeneratingOverlay />
                ) : brief.status === "failed" ? (
                  <div className="text-center py-12">
                    <p className="text-red-400 mb-2">Failed to generate brief</p>
                    {brief.error_message && (
                      <p className="text-sm text-slate-400 mb-4">{brief.error_message}</p>
                    )}
                    <button
                      onClick={handleRefresh}
                      disabled={generateBrief.isPending}
                      className="px-4 py-2 bg-primary-600 hover:bg-primary-500 disabled:opacity-60 text-white font-medium rounded-lg transition-colors"
                    >
                      Try again
                    </button>
                  </div>
                ) : isBriefContentPopulated(brief.brief_content) ? (
                  <>
                    <BriefSummary summary={brief.brief_content.summary} />
                    <div className="space-y-4">
                      <AttendeesSection attendees={brief.brief_content.attendees} />
                      <CompanySection company={brief.brief_content.company} />
                      <AgendaSection agenda={brief.brief_content.suggested_agenda} />
                      <RisksOpportunitiesSection items={brief.brief_content.risks_opportunities} />
                      <BriefNotesSection />
                    </div>
                  </>
                ) : (
                  <MeetingBriefEmpty
                    meetingTitle={brief.meeting_title}
                    onGenerate={handleGenerate}
                    isGenerating={generateBrief.isPending}
                  />
                )}
              </div>
            </>
          ) : (
            <MeetingBriefEmpty
              onGenerate={handleGenerate}
              isGenerating={generateBrief.isPending}
            />
          )}
        </div>
      </div>

      {/* Print styles */}
      <style>{`
        @media print {
          nav, button, [data-print-hide] {
            display: none !important;
          }
          body {
            background: white !important;
          }
          .bg-slate-800, .bg-slate-700, .bg-slate-900 {
            background: white !important;
            border-color: #e5e7eb !important;
          }
          .text-white, .text-slate-200, .text-slate-300 {
            color: black !important;
          }
          .text-slate-400 {
            color: #6b7280 !important;
          }
        }
      `}</style>
    </DashboardLayout>
  );
}
```

**Step 2: Update pages barrel export**

```typescript
export { AriaChatPage } from "./AriaChat";
export { BattleCardsPage } from "./BattleCards";
export { DashboardPage } from "./Dashboard";
export { GoalsPage } from "./Goals";
export { IntegrationsCallbackPage } from "./IntegrationsCallback";
export { IntegrationsSettingsPage } from "./IntegrationsSettings";
export { LoginPage } from "./Login";
export { MeetingBriefPage } from "./MeetingBrief";
export { SignupPage } from "./Signup";
```

**Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/pages/MeetingBrief.tsx frontend/src/pages/index.ts
git commit -m "feat(ui): add MeetingBriefPage with full brief display"
```

---

## Task 15: Add Route to App Router

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add the meeting brief route**

Find this section in App.tsx:
```typescript
import {
  AriaChatPage,
  BattleCardsPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LoginPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
} from "@/pages";
```

Replace with:
```typescript
import {
  AriaChatPage,
  BattleCardsPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LoginPage,
  MeetingBriefPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
} from "@/pages";
```

Then find this section:
```typescript
            <Route
              path="/dashboard/battlecards"
              element={
                <ProtectedRoute>
                  <BattleCardsPage />
                </ProtectedRoute>
              }
            />
```

Add BEFORE it:
```typescript
            <Route
              path="/dashboard/meetings/:id/brief"
              element={
                <ProtectedRoute>
                  <MeetingBriefPage />
                </ProtectedRoute>
              }
            />
```

**Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(ui): add meeting brief route to app router"
```

---

## Task 16: Add Meeting Brief Link to CalendarSection

**Files:**
- Modify: `frontend/src/components/briefing/CalendarSection.tsx`

**Step 1: Update CalendarSection to link to brief page**

Replace the entire file content:

```typescript
import { Calendar, Clock, FileText, Users } from "lucide-react";
import { Link } from "react-router-dom";
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
        {key_meetings.map((meeting, index) => {
          // Generate a calendar event ID from meeting data for linking
          const calendarEventId = meeting.title
            ? encodeURIComponent(meeting.title.toLowerCase().replace(/\s+/g, "-"))
            : `meeting-${index}`;

          return (
            <div
              key={index}
              className="flex items-start gap-4 p-3 bg-slate-700/30 border border-slate-600/30 rounded-lg group"
            >
              <div className="flex-shrink-0 flex items-center justify-center w-12 h-12 bg-primary-500/10 border border-primary-500/20 rounded-lg">
                <Clock className="w-5 h-5 text-primary-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-primary-400">{meeting.time}</span>
                </div>
                <h4 className="text-white font-medium truncate">{meeting.title}</h4>
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
              {/* Brief link */}
              <Link
                to={`/dashboard/meetings/${calendarEventId}/brief`}
                className="flex-shrink-0 p-2 text-slate-500 hover:text-primary-400 hover:bg-primary-500/10 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                title="View meeting brief"
              >
                <FileText className="w-5 h-5" />
              </Link>
            </div>
          );
        })}
      </div>
    </CollapsibleSection>
  );
}
```

**Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/briefing/CalendarSection.tsx
git commit -m "feat(ui): add meeting brief links to calendar section"
```

---

## Task 17: Run Full Type Check and Lint

**Files:**
- None (verification only)

**Step 1: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: PASS (or fixable warnings only)

**Step 3: Fix any lint issues**

Run: `cd frontend && npm run lint -- --fix`

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix lint issues in meeting brief components"
```

---

## Task 18: Manual Testing Verification

**Files:**
- None (manual verification)

**Step 1: Start the development server**

Run: `cd frontend && npm run dev`
Expected: Server starts without errors

**Step 2: Navigate to a meeting brief page**

Open browser to: `http://localhost:5173/dashboard/meetings/test-meeting/brief`
Expected: Should see empty state or skeleton loading

**Step 3: Verify dashboard calendar links**

Navigate to: `http://localhost:5173/dashboard`
Expected: Calendar items should show brief icon on hover

**Step 4: Document any issues found**

Create issue list if needed for follow-up fixes

---

## Task 19: Final Commit and Summary

**Step 1: Verify all changes are committed**

Run: `git status`
Expected: Clean working directory

**Step 2: Create summary commit if needed**

```bash
git log --oneline -10
```

Review commits are in good order.

---

## Summary

This plan creates a complete Meeting Brief UI with:

1. **API Layer** (`api/meetingBriefs.ts`): TypeScript types and API functions
2. **Hooks Layer** (`hooks/useMeetingBrief.ts`): React Query hooks with polling for generating status
3. **Components** (`components/meetingBrief/`):
   - `MeetingBriefSkeleton` - Loading state
   - `MeetingBriefEmpty` - Empty/error state
   - `MeetingBriefHeader` - Title, status, actions
   - `BriefSummary` - Meeting context summary
   - `AttendeeCard` - Individual attendee profile
   - `AttendeesSection` - Attendee grid
   - `CompanySection` - Company intel
   - `AgendaSection` - Suggested agenda
   - `RisksOpportunitiesSection` - Risks & opportunities
   - `BriefNotesSection` - User notes with inline editing
   - `GeneratingOverlay` - Progress indicator
4. **Page** (`pages/MeetingBrief.tsx`): Full page with print support
5. **Routing**: `/dashboard/meetings/:id/brief` route
6. **Integration**: Brief links in dashboard CalendarSection

All components follow existing ARIA design patterns with Apple-inspired styling, using the existing CollapsibleSection UI component and Tailwind CSS conventions.
