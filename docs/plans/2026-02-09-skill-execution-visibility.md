# Skill Execution Visibility — Frontend Components

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build three frontend components that make ARIA's skill execution transparent: an ExecutionPlanCard for approval workflows, activity feed integration for execution steps, and inline chat indicators for conversational skill invocation.

**Architecture:** Three new components integrate into existing patterns. ExecutionPlanCard is a standalone card used both in chat (inline) and in the approval queue. SkillActivityEntry extends the activity feed. SkillExecutionInline wraps around ChatMessage for in-chat progress. All use existing React Query polling (no WebSocket changes), existing API types from `api/skills.ts` and `api/activity.ts`, and ARIA design tokens from `index.css`.

**Tech Stack:** React 18, TypeScript, Tailwind CSS v4 (custom tokens), TanStack Query, Lucide React icons, Framer Motion (already in package.json)

---

### Task 1: API Types for Execution Plans

**Files:**
- Modify: `frontend/src/api/skills.ts`

**Step 1: Add execution plan types to the skills API client**

Add these interfaces after the existing `TrustInfo` interface (line ~70):

```typescript
export type DataAccessLevel = "public" | "internal" | "confidential" | "restricted" | "regulated";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type PlanStatus = "draft" | "pending_approval" | "approved" | "executing" | "completed" | "failed" | "cancelled";

export interface ExecutionStep {
  step_number: number;
  skill_id: string;
  skill_path: string;
  skill_name: string;
  depends_on: number[];
  status: StepStatus;
  agent_id: string | null;
  data_classes: DataAccessLevel[];
  estimated_seconds: number;
  started_at: string | null;
  completed_at: string | null;
  output_summary: string | null;
  error: string | null;
}

export interface ExecutionPlan {
  id: string;
  task_description: string;
  steps: ExecutionStep[];
  parallel_groups: number[][];
  estimated_duration_ms: number;
  risk_level: RiskLevel;
  approval_required: boolean;
  reasoning: string;
  status: PlanStatus;
  created_at: string;
  approved_at: string | null;
  completed_at: string | null;
}
```

**Step 2: Add API functions for execution plans**

Add after the existing `approveSkillGlobally` function (line ~147):

```typescript
export async function getExecutionPlan(planId: string): Promise<ExecutionPlan> {
  const response = await apiClient.get<ExecutionPlan>(`/skills/plans/${planId}`);
  return response.data;
}

export async function approveExecutionPlan(planId: string): Promise<ExecutionPlan> {
  const response = await apiClient.post<ExecutionPlan>(`/skills/plans/${planId}/approve`);
  return response.data;
}

export async function rejectExecutionPlan(planId: string): Promise<ExecutionPlan> {
  const response = await apiClient.post<ExecutionPlan>(`/skills/plans/${planId}/reject`);
  return response.data;
}

export async function listPendingPlans(): Promise<ExecutionPlan[]> {
  const response = await apiClient.get<ExecutionPlan[]>("/skills/plans?status=pending_approval");
  return response.data;
}
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors from skills.ts

**Step 4: Commit**

```bash
git add frontend/src/api/skills.ts
git commit -m "feat: add ExecutionPlan types and API functions to skills client"
```

---

### Task 2: React Query Hooks for Execution Plans

**Files:**
- Modify: `frontend/src/hooks/useSkills.ts`

**Step 1: Add execution plan hooks**

Add imports at the top of the file — add `getExecutionPlan`, `approveExecutionPlan`, `rejectExecutionPlan`, `listPendingPlans`, and `approveSkillGlobally` to the import from `@/api/skills`.

Add new query keys to `skillKeys`:

```typescript
export const skillKeys = {
  all: ["skills"] as const,
  available: () => [...skillKeys.all, "available"] as const,
  availableFiltered: (filters?: AvailableSkillsFilters) =>
    [...skillKeys.available(), { filters }] as const,
  installed: () => [...skillKeys.all, "installed"] as const,
  audit: () => [...skillKeys.all, "audit"] as const,
  auditFiltered: (skillId?: string) =>
    [...skillKeys.audit(), { skillId }] as const,
  plans: () => [...skillKeys.all, "plans"] as const,
  pendingPlans: () => [...skillKeys.plans(), "pending"] as const,
  plan: (planId: string) => [...skillKeys.plans(), planId] as const,
};
```

Add these hooks after the existing `useSkillAudit`:

```typescript
export function useExecutionPlan(planId: string | null) {
  return useQuery({
    queryKey: skillKeys.plan(planId ?? ""),
    queryFn: () => getExecutionPlan(planId!),
    enabled: !!planId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "executing" || status === "pending_approval") return 2_000;
      return false;
    },
  });
}

export function usePendingPlans() {
  return useQuery({
    queryKey: skillKeys.pendingPlans(),
    queryFn: () => listPendingPlans(),
    refetchInterval: 10_000,
  });
}

export function useApproveExecutionPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => approveExecutionPlan(planId),
    onSuccess: (plan) => {
      queryClient.setQueryData(skillKeys.plan(plan.id), plan);
      queryClient.invalidateQueries({ queryKey: skillKeys.pendingPlans() });
    },
  });
}

export function useRejectExecutionPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => rejectExecutionPlan(planId),
    onSuccess: (plan) => {
      queryClient.setQueryData(skillKeys.plan(plan.id), plan);
      queryClient.invalidateQueries({ queryKey: skillKeys.pendingPlans() });
    },
  });
}

export function useApproveSkillGlobally() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) => approveSkillGlobally(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useSkills.ts
git commit -m "feat: add React Query hooks for execution plan polling, approval, and rejection"
```

---

### Task 3: ExecutionPlanCard Component

**Files:**
- Create: `frontend/src/components/skills/ExecutionPlanCard.tsx`
- Modify: `frontend/src/components/skills/index.ts`

**Step 1: Build the ExecutionPlanCard component**

Create `frontend/src/components/skills/ExecutionPlanCard.tsx`:

```tsx
import { useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
  Shield,
  AlertTriangle,
  Zap,
  Bot,
  SkipForward,
} from "lucide-react";
import type {
  ExecutionPlan,
  ExecutionStep,
  RiskLevel,
  StepStatus,
  DataAccessLevel,
} from "@/api/skills";
import { TrustLevelBadge } from "./TrustLevelBadge";
import {
  useApproveExecutionPlan,
  useRejectExecutionPlan,
  useApproveSkillGlobally,
} from "@/hooks/useSkills";

// --- Config maps ---

const riskConfig: Record<RiskLevel, { label: string; classes: string; icon: typeof Shield }> = {
  low: { label: "Low Risk", classes: "bg-success/15 text-success border-success/25", icon: Shield },
  medium: { label: "Medium Risk", classes: "bg-warning/15 text-warning border-warning/25", icon: Shield },
  high: { label: "High Risk", classes: "bg-critical/15 text-critical border-critical/25", icon: AlertTriangle },
  critical: { label: "Critical Risk", classes: "bg-critical/20 text-critical border-critical/40", icon: AlertTriangle },
};

const stepStatusConfig: Record<StepStatus, { label: string; classes: string; icon: typeof Clock }> = {
  pending: { label: "Pending", classes: "text-slate-500", icon: Clock },
  running: { label: "Running", classes: "text-primary-400", icon: Loader2 },
  completed: { label: "Done", classes: "text-success", icon: CheckCircle2 },
  failed: { label: "Failed", classes: "text-critical", icon: XCircle },
  skipped: { label: "Skipped", classes: "text-slate-500", icon: SkipForward },
};

const dataAccessConfig: Record<DataAccessLevel, { label: string; classes: string }> = {
  public: { label: "PUBLIC", classes: "bg-success/10 text-success border-success/20" },
  internal: { label: "INTERNAL", classes: "bg-info/10 text-info border-info/20" },
  confidential: { label: "CONFIDENTIAL", classes: "bg-warning/10 text-warning border-warning/20" },
  restricted: { label: "RESTRICTED", classes: "bg-critical/10 text-critical border-critical/20" },
  regulated: { label: "REGULATED", classes: "bg-critical/15 text-critical border-critical/30" },
};

const agentConfig: Record<string, { label: string; color: string }> = {
  hunter: { label: "Hunter", color: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" },
  analyst: { label: "Analyst", color: "bg-blue-500/15 text-blue-400 border-blue-500/25" },
  strategist: { label: "Strategist", color: "bg-violet-500/15 text-violet-400 border-violet-500/25" },
  scribe: { label: "Scribe", color: "bg-amber-500/15 text-amber-400 border-amber-500/25" },
  operator: { label: "Operator", color: "bg-rose-500/15 text-rose-400 border-rose-500/25" },
  scout: { label: "Scout", color: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25" },
};

// --- Sub-components ---

function DataAccessBadge({ level }: { level: DataAccessLevel }) {
  const config = dataAccessConfig[level];
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold tracking-wider rounded border ${config.classes}`}>
      {config.label}
    </span>
  );
}

function AgentBadge({ agentId }: { agentId: string }) {
  const config = agentConfig[agentId] ?? { label: agentId, color: "bg-slate-500/15 text-slate-400 border-slate-500/25" };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border ${config.color}`}>
      <Bot className="w-3 h-3" />
      {config.label}
    </span>
  );
}

function RiskBadge({ level }: { level: RiskLevel }) {
  const config = riskConfig[level];
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${config.classes}`}>
      <Icon className="w-3.5 h-3.5" />
      {config.label}
    </span>
  );
}

function StepStatusIcon({ status }: { status: StepStatus }) {
  const config = stepStatusConfig[status];
  const Icon = config.icon;
  return (
    <Icon
      className={`w-4 h-4 ${config.classes} ${status === "running" ? "animate-spin" : ""}`}
    />
  );
}

function formatDuration(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return remaining > 0 ? `${minutes}m ${remaining}s` : `${minutes}m`;
}

interface StepRowProps {
  step: ExecutionStep;
  isLast: boolean;
}

function StepRow({ step, isLast }: StepRowProps) {
  return (
    <div className="relative flex gap-3">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-800 border border-slate-700 z-10">
          <StepStatusIcon status={step.status} />
        </div>
        {!isLast && (
          <div className={`w-px flex-1 min-h-[24px] ${
            step.status === "completed" ? "bg-success/40" :
            step.status === "running" ? "bg-primary-400/40" :
            "bg-slate-700"
          }`} />
        )}
      </div>

      {/* Step content */}
      <div className="flex-1 pb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-white">{step.skill_name || step.skill_path}</span>
          {step.agent_id && <AgentBadge agentId={step.agent_id} />}
        </div>

        <div className="mt-1.5 flex items-center gap-2 flex-wrap">
          {step.data_classes.map((dc) => (
            <DataAccessBadge key={dc} level={dc} />
          ))}
          <span className="text-xs text-slate-500 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            ~{formatDuration(step.estimated_seconds * 1000)}
          </span>
        </div>

        {/* Output or error */}
        {step.status === "completed" && step.output_summary && (
          <p className="mt-1.5 text-xs text-slate-400 line-clamp-2">
            {step.output_summary}
          </p>
        )}
        {step.status === "failed" && step.error && (
          <p className="mt-1.5 text-xs text-critical line-clamp-2">
            {step.error}
          </p>
        )}
      </div>
    </div>
  );
}

// --- Main component ---

interface ExecutionPlanCardProps {
  plan: ExecutionPlan;
  /** Compact mode for inline chat display */
  compact?: boolean;
  /** Called after approve/reject mutation completes */
  onAction?: () => void;
  /** Show the "trust this skill always" checkbox (only for single-skill plans) */
  showTrustCheckbox?: boolean;
}

export function ExecutionPlanCard({
  plan,
  compact = false,
  onAction,
  showTrustCheckbox = false,
}: ExecutionPlanCardProps) {
  const [reasoningExpanded, setReasoningExpanded] = useState(false);
  const [trustAlways, setTrustAlways] = useState(false);

  const approveMutation = useApproveExecutionPlan();
  const rejectMutation = useRejectExecutionPlan();
  const trustMutation = useApproveSkillGlobally();

  const isPending = plan.status === "pending_approval";
  const isExecuting = plan.status === "executing";
  const isComplete = plan.status === "completed";
  const isFailed = plan.status === "failed";

  const completedSteps = plan.steps.filter((s) => s.status === "completed").length;
  const progress = plan.steps.length > 0 ? (completedSteps / plan.steps.length) * 100 : 0;

  function handleApprove() {
    approveMutation.mutate(plan.id, {
      onSuccess: () => {
        if (trustAlways && plan.steps.length === 1) {
          trustMutation.mutate(plan.steps[0].skill_id);
        }
        onAction?.();
      },
    });
  }

  function handleReject() {
    rejectMutation.mutate(plan.id, {
      onSuccess: () => onAction?.(),
    });
  }

  // Auto-approved flash: if plan transitions to approved/executing without user action
  const autoApproved = plan.status === "approved" || (isExecuting && !plan.approved_at);

  return (
    <div
      className={`relative bg-slate-800/50 border rounded-xl transition-all duration-300 ${
        autoApproved ? "animate-pulse border-success/50 shadow-success/10 shadow-lg" :
        isPending ? "border-primary-500/30 shadow-primary-500/5 shadow-md" :
        isComplete ? "border-success/20" :
        isFailed ? "border-critical/30" :
        "border-slate-700"
      } ${compact ? "p-4" : "p-5"}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Zap className="w-4 h-4 text-primary-400 flex-shrink-0" />
            <h3
              className={`font-semibold text-white truncate ${compact ? "text-sm" : "text-base"}`}
              style={{ fontFamily: "var(--font-serif)" }}
            >
              {plan.task_description}
            </h3>
          </div>
          <div className="mt-1.5 flex items-center gap-2 flex-wrap">
            <RiskBadge level={plan.risk_level} />
            <span className="text-xs text-slate-500">
              {plan.steps.length} step{plan.steps.length !== 1 ? "s" : ""} · ~{formatDuration(plan.estimated_duration_ms)}
            </span>
          </div>
        </div>

        {/* Status indicator */}
        {isExecuting && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-primary-400 bg-primary-500/10 rounded-full border border-primary-500/20">
            <Loader2 className="w-3 h-3 animate-spin" />
            {completedSteps}/{plan.steps.length}
          </div>
        )}
        {isComplete && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-success bg-success/10 rounded-full border border-success/20">
            <CheckCircle2 className="w-3 h-3" />
            Done
          </div>
        )}
        {isFailed && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-critical bg-critical/10 rounded-full border border-critical/20">
            <XCircle className="w-3 h-3" />
            Failed
          </div>
        )}
      </div>

      {/* Progress bar (when executing) */}
      {isExecuting && (
        <div className="mt-3 h-1 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary-500 to-primary-400 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Reasoning (expandable) */}
      {plan.reasoning && (
        <div className="mt-3">
          <button
            onClick={() => setReasoningExpanded(!reasoningExpanded)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            {reasoningExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {reasoningExpanded ? "Hide reasoning" : "View reasoning"}
          </button>
          {reasoningExpanded && (
            <p className="mt-2 text-xs text-slate-400 leading-relaxed bg-slate-900/50 rounded-lg p-3 border border-slate-700/50">
              {plan.reasoning}
            </p>
          )}
        </div>
      )}

      {/* Steps timeline */}
      {!compact && (
        <div className="mt-4">
          {plan.steps.map((step, index) => (
            <StepRow
              key={step.step_number}
              step={step}
              isLast={index === plan.steps.length - 1}
            />
          ))}
        </div>
      )}

      {/* Compact: collapsed step summary */}
      {compact && plan.steps.length > 0 && (
        <div className="mt-3 flex items-center gap-1.5">
          {plan.steps.map((step) => (
            <div
              key={step.step_number}
              className={`w-2 h-2 rounded-full ${
                step.status === "completed" ? "bg-success" :
                step.status === "running" ? "bg-primary-400 animate-pulse" :
                step.status === "failed" ? "bg-critical" :
                "bg-slate-600"
              }`}
              title={`${step.skill_name}: ${stepStatusConfig[step.status].label}`}
            />
          ))}
        </div>
      )}

      {/* Action buttons (pending approval only) */}
      {isPending && (
        <div className="mt-4 pt-4 border-t border-slate-700/50">
          {showTrustCheckbox && plan.steps.length === 1 && (
            <label className="flex items-center gap-2 mb-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={trustAlways}
                onChange={(e) => setTrustAlways(e.target.checked)}
                className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-primary-500 focus:ring-primary-500/30 focus:ring-2 focus:ring-offset-0"
              />
              <span className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors">
                Trust this skill always
              </span>
            </label>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={handleApprove}
              disabled={approveMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-success/20 border border-success/30 rounded-lg hover:bg-success/30 transition-colors disabled:opacity-50"
            >
              {approveMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle2 className="w-4 h-4" />
              )}
              Approve
            </button>
            <button
              onClick={handleReject}
              disabled={rejectMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-slate-300 bg-critical/10 border border-critical/20 rounded-lg hover:bg-critical/20 hover:text-white transition-colors disabled:opacity-50"
            >
              {rejectMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <XCircle className="w-4 h-4" />
              )}
              Reject
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Add export to barrel file**

In `frontend/src/components/skills/index.ts`, add:

```typescript
export { ExecutionPlanCard } from "./ExecutionPlanCard";
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/skills/ExecutionPlanCard.tsx frontend/src/components/skills/index.ts
git commit -m "feat: add ExecutionPlanCard with timeline steps, risk badges, and approval actions"
```

---

### Task 4: SkillActivityEntry Component (Activity Feed Integration)

**Files:**
- Create: `frontend/src/components/skills/SkillActivityEntry.tsx`
- Modify: `frontend/src/components/skills/index.ts`

**Step 1: Build the SkillActivityEntry component**

This component renders a single skill execution step as an activity feed entry. It's designed to slot into the existing `ActivityFeedPage` alongside normal activity items.

Create `frontend/src/components/skills/SkillActivityEntry.tsx`:

```tsx
import { useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
  Bot,
  Zap,
} from "lucide-react";
import type { ActivityItem } from "@/api/activity";

// Agent color mapping (same as ExecutionPlanCard)
const agentColors: Record<string, string> = {
  hunter: "from-emerald-500 to-emerald-600",
  analyst: "from-blue-500 to-blue-600",
  strategist: "from-violet-500 to-violet-600",
  scribe: "from-amber-500 to-amber-600",
  operator: "from-rose-500 to-rose-600",
  scout: "from-cyan-500 to-cyan-600",
};

function AgentIcon({ agent }: { agent: string | null }) {
  const gradient = agent ? agentColors[agent] ?? "from-slate-500 to-slate-600" : "from-primary-500 to-primary-600";
  return (
    <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${gradient} flex items-center justify-center flex-shrink-0`}>
      {agent ? (
        <Bot className="w-4 h-4 text-white" />
      ) : (
        <Zap className="w-4 h-4 text-white" />
      )}
    </div>
  );
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMins / 60);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface SkillActivityEntryProps {
  activity: ActivityItem;
  onClick?: () => void;
}

export function SkillActivityEntry({ activity, onClick }: SkillActivityEntryProps) {
  const [expanded, setExpanded] = useState(false);

  const isSkillExecution = activity.activity_type === "skill_execution" ||
    activity.activity_type === "skill_step_completed" ||
    activity.activity_type === "skill_step_failed";

  const metadata = activity.metadata as Record<string, unknown>;
  const skillName = (metadata.skill_name as string) ?? null;
  const stepNumber = (metadata.step_number as number) ?? null;
  const executionTimeMs = (metadata.execution_time_ms as number) ?? null;
  const planId = (metadata.plan_id as string) ?? null;

  const isRunning = activity.activity_type === "skill_execution" && !metadata.completed;
  const isFailed = activity.activity_type === "skill_step_failed";

  return (
    <div
      className={`group bg-slate-800/50 border border-slate-700 rounded-xl p-4 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600 ${
        onClick ? "cursor-pointer" : ""
      }`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <AgentIcon agent={activity.agent} />

        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-white truncate">
              {activity.title}
            </span>
            {isSkillExecution && skillName && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold tracking-wider text-primary-400 bg-primary-500/10 rounded border border-primary-500/20">
                <Zap className="w-2.5 h-2.5" />
                {skillName}
              </span>
            )}
            {isRunning && (
              <Loader2 className="w-3.5 h-3.5 text-primary-400 animate-spin flex-shrink-0" />
            )}
            {isFailed && (
              <XCircle className="w-3.5 h-3.5 text-critical flex-shrink-0" />
            )}
          </div>

          {/* Description */}
          {activity.description && (
            <p className={`mt-1 text-xs text-slate-400 ${expanded ? "" : "line-clamp-2"}`}>
              {activity.description}
            </p>
          )}

          {/* Meta row */}
          <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatRelativeTime(activity.created_at)}
            </span>
            {stepNumber !== null && (
              <span>Step {stepNumber}</span>
            )}
            {executionTimeMs !== null && (
              <span>{Math.round(executionTimeMs)}ms</span>
            )}
            {activity.confidence > 0 && (
              <span className="flex items-center gap-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    activity.confidence >= 0.8 ? "bg-success" :
                    activity.confidence >= 0.5 ? "bg-warning" :
                    "bg-critical"
                  }`}
                />
                {Math.round(activity.confidence * 100)}%
              </span>
            )}
          </div>

          {/* Expandable detail */}
          {(activity.reasoning || planId) && (
            <div className="mt-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setExpanded(!expanded);
                }}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                {expanded ? "Less" : "Details"}
              </button>
              {expanded && (
                <div className="mt-2 space-y-2">
                  {activity.reasoning && (
                    <p className="text-xs text-slate-400 bg-slate-900/50 rounded-lg p-2.5 border border-slate-700/50 leading-relaxed">
                      {activity.reasoning}
                    </p>
                  )}
                  {planId && (
                    <p className="text-xs text-slate-500">
                      Plan: <span className="font-mono text-slate-400">{planId.slice(0, 8)}</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Status icon (right side) */}
        <div className="flex-shrink-0 mt-0.5">
          {activity.activity_type === "skill_step_completed" && (
            <CheckCircle2 className="w-4 h-4 text-success" />
          )}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Add export to barrel file**

In `frontend/src/components/skills/index.ts`, add:

```typescript
export { SkillActivityEntry } from "./SkillActivityEntry";
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/skills/SkillActivityEntry.tsx frontend/src/components/skills/index.ts
git commit -m "feat: add SkillActivityEntry for skill execution steps in activity feed"
```

---

### Task 5: SkillExecutionInline Component (Chat Integration)

**Files:**
- Create: `frontend/src/components/skills/SkillExecutionInline.tsx`
- Modify: `frontend/src/components/skills/index.ts`

**Step 1: Build the SkillExecutionInline component**

This is the conversational skill invocation component (Enhancement 5). It renders inline within the chat flow — NOT a separate page. For simple single-skill executions, it shows a compact inline indicator. For multi-step plans needing approval, it embeds a compact ExecutionPlanCard.

Create `frontend/src/components/skills/SkillExecutionInline.tsx`:

```tsx
import { useState } from "react";
import {
  Zap,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  Eye,
} from "lucide-react";
import type { ExecutionPlan, StepStatus } from "@/api/skills";
import { useExecutionPlan } from "@/hooks/useSkills";
import { ExecutionPlanCard } from "./ExecutionPlanCard";

// --- Simple skill execution indicator (1 skill, auto-approved) ---

interface SimpleExecutionProps {
  skillName: string;
  status: StepStatus;
  resultSummary?: string | null;
  executionTimeMs?: number | null;
}

function SimpleExecution({ skillName, status, resultSummary, executionTimeMs }: SimpleExecutionProps) {
  const [detailVisible, setDetailVisible] = useState(false);

  const isRunning = status === "running";
  const isDone = status === "completed";
  const isFailed = status === "failed";

  return (
    <div className="my-2">
      {/* Inline indicator */}
      <div
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-300 ${
          isRunning
            ? "bg-primary-500/10 text-primary-400 border border-primary-500/20"
            : isDone
              ? "bg-success/10 text-success border border-success/20"
              : isFailed
                ? "bg-critical/10 text-critical border border-critical/20"
                : "bg-slate-800/50 text-slate-400 border border-slate-700"
        }`}
      >
        {isRunning && <Loader2 className="w-3 h-3 animate-spin" />}
        {isDone && <CheckCircle2 className="w-3 h-3" />}
        {isFailed && <XCircle className="w-3 h-3" />}
        {!isRunning && !isDone && !isFailed && <Zap className="w-3 h-3" />}

        <span>
          {isRunning ? `Running ${skillName}...` :
           isDone ? `Used ${skillName}` :
           isFailed ? `${skillName} failed` :
           skillName}
        </span>

        {executionTimeMs !== null && executionTimeMs !== undefined && isDone && (
          <span className="text-slate-500">{Math.round(executionTimeMs)}ms</span>
        )}
      </div>

      {/* "View what ARIA did" disclosure link */}
      {(isDone || isFailed) && resultSummary && (
        <div className="mt-1">
          <button
            onClick={() => setDetailVisible(!detailVisible)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            {detailVisible ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <Eye className="w-3 h-3" />
            )}
            {detailVisible ? "Hide details" : "View what ARIA did"}
          </button>
          {detailVisible && (
            <div className="mt-1.5 text-xs text-slate-400 bg-slate-900/50 rounded-lg p-3 border border-slate-700/50 leading-relaxed">
              {resultSummary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --- Multi-step execution with plan card ---

interface PlanExecutionProps {
  planId: string;
  onAction?: () => void;
}

function PlanExecution({ planId, onAction }: PlanExecutionProps) {
  const { data: plan, isLoading } = useExecutionPlan(planId);

  if (isLoading || !plan) {
    return (
      <div className="my-2 flex items-center gap-2 text-xs text-slate-500">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading execution plan...
      </div>
    );
  }

  return (
    <div className="my-3">
      <ExecutionPlanCard
        plan={plan}
        compact={plan.status !== "pending_approval"}
        onAction={onAction}
        showTrustCheckbox={plan.steps.length === 1}
      />
    </div>
  );
}

// --- Main component ---

export interface SkillExecutionData {
  type: "simple" | "plan";
  /** For simple: the skill being executed */
  skillName?: string;
  status?: StepStatus;
  resultSummary?: string | null;
  executionTimeMs?: number | null;
  /** For plan: the plan ID to fetch and render */
  planId?: string;
}

interface SkillExecutionInlineProps {
  execution: SkillExecutionData;
  onAction?: () => void;
}

export function SkillExecutionInline({ execution, onAction }: SkillExecutionInlineProps) {
  if (execution.type === "simple" && execution.skillName) {
    return (
      <SimpleExecution
        skillName={execution.skillName}
        status={execution.status ?? "pending"}
        resultSummary={execution.resultSummary}
        executionTimeMs={execution.executionTimeMs}
      />
    );
  }

  if (execution.type === "plan" && execution.planId) {
    return <PlanExecution planId={execution.planId} onAction={onAction} />;
  }

  return null;
}
```

**Step 2: Add export to barrel file**

In `frontend/src/components/skills/index.ts`, add:

```typescript
export { SkillExecutionInline } from "./SkillExecutionInline";
export type { SkillExecutionData } from "./SkillExecutionInline";
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/skills/SkillExecutionInline.tsx frontend/src/components/skills/index.ts
git commit -m "feat: add SkillExecutionInline for conversational skill progress in chat"
```

---

### Task 6: Wire SkillExecutionInline into ChatMessage

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx`
- Modify: `frontend/src/components/chat/index.ts`

**Step 1: Extend the ChatMessage type**

In `frontend/src/api/chat.ts`, add an optional field to `ChatMessage`:

```typescript
export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  /** Skill execution data attached to this message (Enhancement 5) */
  skill_execution?: {
    type: "simple" | "plan";
    skill_name?: string;
    status?: "pending" | "running" | "completed" | "failed" | "skipped";
    result_summary?: string | null;
    execution_time_ms?: number | null;
    plan_id?: string;
  } | null;
}
```

**Step 2: Integrate SkillExecutionInline into ChatMessage**

In `frontend/src/components/chat/ChatMessage.tsx`:

Add import at the top:

```typescript
import { SkillExecutionInline } from "@/components/skills";
import type { SkillExecutionData } from "@/components/skills";
```

Inside the `ChatMessage` component, after the `{/* Content */}` section (after line ~127, before the streaming cursor), add:

```tsx
          {/* Skill execution inline (Enhancement 5) */}
          {!isUser && message.skill_execution && (
            <SkillExecutionInline
              execution={{
                type: message.skill_execution.type,
                skillName: message.skill_execution.skill_name,
                status: message.skill_execution.status,
                resultSummary: message.skill_execution.result_summary,
                executionTimeMs: message.skill_execution.execution_time_ms,
                planId: message.skill_execution.plan_id,
              } as SkillExecutionData}
            />
          )}
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/api/chat.ts frontend/src/components/chat/ChatMessage.tsx
git commit -m "feat: wire SkillExecutionInline into ChatMessage for in-chat skill visibility"
```

---

### Task 7: CSS Animations for Auto-Approve Flash

**Files:**
- Modify: `frontend/src/index.css`

**Step 1: Add skill execution animations**

Add these keyframes alongside the existing ARIA animations in `index.css` (after `@keyframes card-lift`):

```css
@keyframes skill-auto-approve {
  0% { border-color: var(--success); box-shadow: 0 0 0 0 rgba(107, 143, 113, 0.4); }
  50% { border-color: var(--success); box-shadow: 0 0 20px 4px rgba(107, 143, 113, 0.2); }
  100% { border-color: var(--border); box-shadow: none; }
}

@keyframes skill-step-complete {
  0% { transform: scale(1); }
  50% { transform: scale(1.15); }
  100% { transform: scale(1); }
}
```

Add utility classes in the same `@theme` or `@utility` section:

```css
.animate-skill-auto-approve {
  animation: skill-auto-approve 1.5s ease-out forwards;
}

.animate-skill-step-complete {
  animation: skill-step-complete 0.3s ease-out;
}
```

**Step 2: Verify the build**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat: add CSS animations for skill auto-approve flash and step completion"
```

---

### Task 8: Integration Test — Lint and Type-Check All New Files

**Files:** All files from Tasks 1-7

**Step 1: Run full type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 2: Run linter**

Run: `cd frontend && npm run lint`
Expected: No errors in new files

**Step 3: Run build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 4: Fix any issues found**

If TypeScript or lint errors appear, fix them in the appropriate files.

**Step 5: Final commit if fixes were needed**

```bash
git add -A
git commit -m "fix: resolve lint and type-check issues in skill execution visibility components"
```
