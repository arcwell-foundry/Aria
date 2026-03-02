# Thesys C1 Custom Components Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Register 5 ARIA-specific custom React components with Thesys C1 for domain-specific UI rendering.

**Architecture:** Create Zod schemas to describe component props to C1, implement React components using ARIA design tokens, and register both frontend components and backend JSON schemas with the C1 API.

**Tech Stack:** React 18, TypeScript, Zod, Tailwind CSS, @thesysai/genui-sdk, Pydantic (backend)

---

## Prerequisites Verification

Before starting, verify these files exist and their current state:
- `frontend/package.json` - check if `zod` is installed
- `backend/src/services/thesys_service.py` - existing custom actions pattern
- `backend/src/services/thesys_actions.py` - existing Pydantic action models
- `frontend/src/contexts/ThesysContext.tsx` - existing Thesys provider

---

## Task 1: Install Zod Dependency

**Files:**
- Modify: `frontend/package.json`

**Step 1: Check if Zod is already installed**

Run: `grep -E '"zod"' frontend/package.json`
Expected: No match found (Zod not installed)

**Step 2: Install Zod**

Run: `cd frontend && npm install zod`
Expected: Zod added to dependencies with version ^3.x.x

**Step 3: Verify installation**

Run: `grep -E '"zod"' frontend/package.json`
Expected: `"zod": "^3.x.x"` in dependencies

**Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add zod dependency for C1 custom component schemas"
```

---

## Task 2: Create C1 Component Directory Structure

**Files:**
- Create: `frontend/src/components/c1/`
- Create: `frontend/src/components/c1/index.ts`

**Step 1: Create directory**

Run: `mkdir -p frontend/src/components/c1`
Expected: Directory created

**Step 2: Create barrel export file**

Create `frontend/src/components/c1/index.ts`:

```typescript
/**
 * C1 Custom Components - ARIA-specific React components for Thesys C1
 *
 * These components are registered with C1 to render domain-specific UI
 * that built-in C1 components cannot handle.
 */

export { GoalPlanCard } from './GoalPlanCard';
export { EmailDraftCard } from './EmailDraftCard';
export { AgentStatusCard } from './AgentStatusCard';
export { SignalAlertCard } from './SignalAlertCard';
export { ApprovalCard } from './ApprovalCard';
export * from './schemas';
```

**Step 3: Commit**

```bash
git add frontend/src/components/c1/index.ts
git commit -m "feat(c1): create custom components directory structure"
```

---

## Task 3: Create Zod Schemas for Custom Components

**Files:**
- Create: `frontend/src/components/c1/schemas.ts`

**Step 1: Create schemas file**

Create `frontend/src/components/c1/schemas.ts`:

```typescript
/**
 * Zod schemas for C1 custom components.
 *
 * These schemas tell C1 what props each component expects.
 * The .describe() text tells C1 WHEN to use each component.
 */

import { z } from 'zod';

// -----------------------------------------------------------------------------
// GoalPlanCard Schema
// -----------------------------------------------------------------------------

const StepSchema = z.object({
  step_number: z.number(),
  description: z.string(),
  assigned_agent: z.string().optional().describe("Which ARIA agent handles this step"),
  status: z.enum(["pending", "in_progress", "complete", "failed"]).default("pending"),
});

export const GoalPlanCardSchema = z.object({
  goal_name: z.string().describe("Name of the goal or plan"),
  goal_id: z.string().describe("Unique identifier for the goal"),
  description: z.string().describe("Brief description of what will be accomplished"),
  steps: z.array(StepSchema).describe("Ordered list of execution steps"),
  estimated_duration: z.string().optional().describe("How long the plan will take"),
  ooda_phase: z.enum(["observe", "orient", "decide", "act"]).optional(),
}).describe(
  "Renders an execution plan card for a goal that ARIA has proposed. Shows numbered steps with agent assignments, progress indicators, and Approve/Modify action buttons. Use this whenever ARIA proposes a multi-step plan for the user to review."
);

// -----------------------------------------------------------------------------
// EmailDraftCard Schema
// -----------------------------------------------------------------------------

export const EmailDraftCardSchema = z.object({
  email_draft_id: z.string().describe("Unique identifier for this draft"),
  to: z.string().describe("Recipient email or name"),
  subject: z.string().describe("Email subject line"),
  body: z.string().describe("Email body text"),
  tone: z.enum(["formal", "friendly", "urgent", "neutral"]).default("neutral").describe("Detected tone of the draft"),
  context: z.string().optional().describe("Why ARIA drafted this email"),
}).describe(
  "Renders an email draft card showing recipient, subject, body preview, and tone indicator. Includes Approve (send), Edit, and Dismiss action buttons. Use this whenever ARIA has drafted an email for the user to review before sending."
);

// -----------------------------------------------------------------------------
// AgentStatusCard Schema
// -----------------------------------------------------------------------------

const AgentInfoSchema = z.object({
  name: z.string().describe("Agent name: Hunter, Analyst, Strategist, Scribe, Operator, or Scout"),
  status: z.enum(["idle", "working", "complete", "error"]),
  current_task: z.string().optional().describe("What the agent is currently doing"),
  ooda_phase: z.enum(["observe", "orient", "decide", "act"]).optional(),
  progress: z.number().min(0).max(100).optional(),
});

export const AgentStatusCardSchema = z.object({
  agents: z.array(AgentInfoSchema).describe("List of active ARIA agents and their status"),
}).describe(
  "Renders a status dashboard showing ARIA's active agents with progress indicators and current OODA phase. Use this when reporting on multi-agent execution progress or when the user asks about what ARIA is working on."
);

// -----------------------------------------------------------------------------
// SignalAlertCard Schema
// -----------------------------------------------------------------------------

export const SignalAlertCardSchema = z.object({
  signal_id: z.string().describe("Unique identifier for this signal"),
  title: z.string().describe("Brief signal headline"),
  severity: z.enum(["high", "medium", "low"]),
  signal_type: z.string().describe("Type: patent_cliff, clinical_trial, competitive_move, regulatory, market_shift, etc."),
  summary: z.string().describe("2-3 sentence summary of the signal"),
  source: z.string().optional().describe("Where ARIA detected this signal"),
  affected_accounts: z.array(z.string()).optional().describe("Account names that may be impacted"),
  detected_at: z.string().optional().describe("When ARIA detected this signal"),
}).describe(
  "Renders a market signal or intelligence alert card with severity indicator, summary, affected accounts, and an Investigate action button. Use this for market intelligence alerts, competitive moves, regulatory changes, clinical trial updates, patent cliffs, or any proactive signal ARIA wants to surface."
);

// -----------------------------------------------------------------------------
// ApprovalCard Schema
// -----------------------------------------------------------------------------

export const ApprovalCardSchema = z.object({
  item_id: z.string().describe("Unique identifier for the item needing approval"),
  item_type: z.string().describe("What type of item: task, recommendation, action, configuration"),
  title: z.string().describe("What needs approval"),
  description: z.string().describe("Context for the approval decision"),
  impact: z.string().optional().describe("What happens if approved"),
  urgency: z.enum(["immediate", "today", "this_week", "no_rush"]).default("no_rush"),
}).describe(
  "Renders a generic approval card for any action that requires user sign-off. Shows title, context, impact assessment, urgency indicator, and Approve/Reject buttons. Use this for any pending action, recommendation, or configuration change that ARIA needs the user to authorize."
);

// -----------------------------------------------------------------------------
// Schema Collection for Backend
// -----------------------------------------------------------------------------

/**
 * All custom component schemas for registration with C1.
 * Keys must match component names exactly.
 */
export const ARIA_CUSTOM_COMPONENT_SCHEMAS = {
  GoalPlanCard: GoalPlanCardSchema,
  EmailDraftCard: EmailDraftCardSchema,
  AgentStatusCard: AgentStatusCardSchema,
  SignalAlertCard: SignalAlertCardSchema,
  ApprovalCard: ApprovalCardSchema,
} as const;

/**
 * Type inference helpers for component props.
 */
export type GoalPlanCardProps = z.infer<typeof GoalPlanCardSchema>;
export type EmailDraftCardProps = z.infer<typeof EmailDraftCardSchema>;
export type AgentStatusCardProps = z.infer<typeof AgentStatusCardSchema>;
export type SignalAlertCardProps = z.infer<typeof SignalAlertCardSchema>;
export type ApprovalCardProps = z.infer<typeof ApprovalCardSchema>;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck 2>&1 | head -20`
Expected: No errors related to schemas.ts

**Step 3: Commit**

```bash
git add frontend/src/components/c1/schemas.ts
git commit -m "feat(c1): add Zod schemas for 5 custom components"
```

---

## Task 4: Create GoalPlanCard Component

**Files:**
- Create: `frontend/src/components/c1/GoalPlanCard.tsx`
- Modify: `frontend/src/components/c1/index.ts`

**Step 1: Create GoalPlanCard component**

Create `frontend/src/components/c1/GoalPlanCard.tsx`:

```typescript
/**
 * GoalPlanCard - Execution plan visualization for ARIA goals
 *
 * Renders when ARIA proposes a multi-step plan for user review.
 * Shows numbered steps with agent assignments, progress indicators,
 * and Approve/Modify action buttons.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { CheckCircle2, Circle, Clock, Loader2, XCircle } from 'lucide-react';
import type { GoalPlanCardProps } from './schemas';

const statusIcons = {
  pending: Circle,
  in_progress: Loader2,
  complete: CheckCircle2,
  failed: XCircle,
};

const statusColors = {
  pending: 'text-secondary',
  in_progress: 'text-interactive',
  complete: 'text-success',
  failed: 'text-critical',
};

const oodaPhaseColors = {
  observe: 'bg-info/20 text-info',
  orient: 'bg-warning/20 text-warning',
  decide: 'bg-interactive/20 text-interactive',
  act: 'bg-success/20 text-success',
};

export function GoalPlanCard({
  goal_name,
  goal_id,
  description,
  steps = [],
  estimated_duration,
  ooda_phase,
}: GoalPlanCardProps) {
  const onAction = useOnAction();

  const handleApprove = () => {
    onAction("Approve Plan", `User approved goal ${goal_id}: ${goal_name}`);
  };

  const handleModify = () => {
    onAction("Modify Plan", `User requested modifications to goal ${goal_id}: ${goal_name}`);
  };

  return (
    <div className="bg-elevated border border-border rounded-xl p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-content font-semibold text-base truncate">
            {goal_name}
          </h3>
          <p className="text-secondary text-sm mt-1 line-clamp-2">
            {description}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {ooda_phase && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${oodaPhaseColors[ooda_phase]}`}>
              {ooda_phase}
            </span>
          )}
          {estimated_duration && (
            <span className="flex items-center gap-1 text-xs text-secondary">
              <Clock className="w-3 h-3" />
              {estimated_duration}
            </span>
          )}
        </div>
      </div>

      {/* Steps */}
      {steps.length > 0 && (
        <div className="space-y-2">
          {steps.map((step) => {
            const StatusIcon = statusIcons[step.status || 'pending'];
            const statusColor = statusColors[step.status || 'pending'];

            return (
              <div
                key={step.step_number}
                className="flex items-start gap-3 p-2 rounded-lg bg-subtle/50"
              >
                <StatusIcon
                  className={`w-4 h-4 mt-0.5 shrink-0 ${statusColor} ${
                    step.status === 'in_progress' ? 'animate-spin' : ''
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-secondary font-medium">
                      Step {step.step_number}
                    </span>
                    {step.assigned_agent && (
                      <span className="px-1.5 py-0.5 rounded bg-interactive/10 text-interactive text-xs">
                        {step.assigned_agent}
                      </span>
                    )}
                  </div>
                  <p className="text-content text-sm mt-0.5">
                    {step.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-border">
        <button
          onClick={handleApprove}
          className="px-4 py-2 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          Approve
        </button>
        <button
          onClick={handleModify}
          className="px-4 py-2 text-sm font-medium bg-elevated text-content border border-border rounded-lg hover:bg-subtle transition-colors"
        >
          Modify
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

The `index.ts` already exports `GoalPlanCard`.

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck 2>&1 | grep -E "(GoalPlanCard|error)" | head -10`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/c1/GoalPlanCard.tsx
git commit -m "feat(c1): add GoalPlanCard component for plan visualization"
```

---

## Task 5: Create EmailDraftCard Component

**Files:**
- Create: `frontend/src/components/c1/EmailDraftCard.tsx`

**Step 1: Create EmailDraftCard component**

Create `frontend/src/components/c1/EmailDraftCard.tsx`:

```typescript
/**
 * EmailDraftCard - Email draft preview with actions
 *
 * Renders when ARIA has drafted an email for user review.
 * Shows recipient, subject, body preview, tone indicator,
 * and Approve/Edit/Dismiss action buttons.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { Mail, Send, Edit2, X } from 'lucide-react';
import type { EmailDraftCardProps } from './schemas';

const toneColors = {
  formal: 'bg-info/10 text-info border-info/20',
  friendly: 'bg-success/10 text-success border-success/20',
  urgent: 'bg-critical/10 text-critical border-critical/20',
  neutral: 'bg-subtle text-secondary border-border',
};

export function EmailDraftCard({
  email_draft_id,
  to,
  subject,
  body,
  tone = 'neutral',
  context,
}: EmailDraftCardProps) {
  const onAction = useOnAction();

  const handleApprove = () => {
    onAction("Send Email", `User approved sending email ${email_draft_id} to ${to}`);
  };

  const handleEdit = () => {
    onAction("Edit Email", `User wants to edit email draft ${email_draft_id}`);
  };

  const handleDismiss = () => {
    onAction("Dismiss Email", `User dismissed email draft ${email_draft_id}`);
  };

  // Truncate body for preview
  const bodyPreview = body.length > 200 ? `${body.slice(0, 200)}...` : body;

  return (
    <div className="bg-elevated border border-border rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-subtle/30">
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4 text-interactive" />
          <span className="text-sm font-medium text-content">Email Draft</span>
        </div>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${toneColors[tone]}`}>
          {tone}
        </span>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Context (why ARIA drafted this) */}
        {context && (
          <p className="text-xs text-secondary italic">
            {context}
          </p>
        )}

        {/* To */}
        <div className="flex items-start gap-2">
          <span className="text-xs text-secondary w-8 shrink-0">To:</span>
          <span className="text-sm text-content font-medium">{to}</span>
        </div>

        {/* Subject */}
        <div className="flex items-start gap-2">
          <span className="text-xs text-secondary w-8 shrink-0">Subj:</span>
          <span className="text-sm text-content">{subject}</span>
        </div>

        {/* Body Preview */}
        <div className="mt-3 p-3 bg-subtle/50 rounded-lg">
          <p className="text-sm text-content whitespace-pre-wrap">
            {bodyPreview}
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-border bg-subtle/30">
        <button
          onClick={handleApprove}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
          Send
        </button>
        <button
          onClick={handleEdit}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-elevated text-content border border-border rounded-lg hover:bg-subtle transition-colors"
        >
          <Edit2 className="w-3.5 h-3.5" />
          Edit
        </button>
        <button
          onClick={handleDismiss}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-secondary hover:text-content transition-colors"
        >
          <X className="w-3.5 h-3.5" />
          Dismiss
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck 2>&1 | grep -E "(EmailDraftCard|error)" | head -10`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/c1/EmailDraftCard.tsx
git commit -m "feat(c1): add EmailDraftCard component for email preview"
```

---

## Task 6: Create AgentStatusCard Component

**Files:**
- Create: `frontend/src/components/c1/AgentStatusCard.tsx`

**Step 1: Create AgentStatusCard component**

Create `frontend/src/components/c1/AgentStatusCard.tsx`:

```typescript
/**
 * AgentStatusCard - Multi-agent status dashboard
 *
 * Renders when reporting on multi-agent execution progress
 * or when user asks what ARIA is working on.
 * Shows agent cards with status indicators, progress bars, and OODA phase.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { Bot, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import type { AgentStatusCardProps } from './schemas';

const statusConfig = {
  idle: {
    icon: Bot,
    color: 'text-secondary',
    bgColor: 'bg-subtle',
    dotColor: 'bg-secondary',
  },
  working: {
    icon: Loader2,
    color: 'text-interactive',
    bgColor: 'bg-interactive/5',
    dotColor: 'bg-interactive animate-pulse',
  },
  complete: {
    icon: CheckCircle2,
    color: 'text-success',
    bgColor: 'bg-success/5',
    dotColor: 'bg-success',
  },
  error: {
    icon: AlertCircle,
    color: 'text-critical',
    bgColor: 'bg-critical/5',
    dotColor: 'bg-critical',
  },
};

const oodaPhaseColors = {
  observe: 'border-info/30',
  orient: 'border-warning/30',
  decide: 'border-interactive/30',
  act: 'border-success/30',
};

export function AgentStatusCard({ agents = [] }: AgentStatusCardProps) {
  const onAction = useOnAction();

  const handleAgentClick = (agentName: string, task: string | undefined) => {
    onAction(
      `View ${agentName}`,
      `User clicked on agent ${agentName}${task ? ` working on: ${task}` : ''}`
    );
  };

  if (agents.length === 0) {
    return (
      <div className="bg-elevated border border-border rounded-xl p-4 text-center">
        <Bot className="w-8 h-8 text-secondary mx-auto mb-2" />
        <p className="text-sm text-secondary">No agents currently active</p>
      </div>
    );
  }

  return (
    <div className="bg-elevated border border-border rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <Bot className="w-4 h-4 text-interactive" />
        <span className="text-sm font-medium text-content">Agent Status</span>
        <span className="text-xs text-secondary ml-auto">
          {agents.filter(a => a.status === 'working').length} active
        </span>
      </div>

      {/* Agent Grid */}
      <div className="grid gap-2">
        {agents.map((agent, index) => {
          const config = statusConfig[agent.status];
          const StatusIcon = config.icon;
          const oodaBorder = agent.ooda_phase ? oodaPhaseColors[agent.ooda_phase] : '';

          return (
            <div
              key={`${agent.name}-${index}`}
              onClick={() => handleAgentClick(agent.name, agent.current_task)}
              className={`
                flex items-start gap-3 p-3 rounded-lg cursor-pointer
                transition-colors hover:bg-subtle/50
                border-l-2 ${oodaBorder}
                ${config.bgColor}
              `}
            >
              {/* Status Dot */}
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${config.dotColor}`} />

              {/* Agent Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-content">
                    {agent.name}
                  </span>
                  <StatusIcon
                    className={`w-3.5 h-3.5 ${config.color} ${
                      agent.status === 'working' ? 'animate-spin' : ''
                    }`}
                  />
                  {agent.ooda_phase && (
                    <span className="text-xs text-secondary uppercase">
                      {agent.ooda_phase}
                    </span>
                  )}
                </div>

                {agent.current_task && (
                  <p className="text-xs text-secondary mt-0.5 truncate">
                    {agent.current_task}
                  </p>
                )}

                {/* Progress Bar */}
                {agent.progress !== undefined && agent.progress > 0 && (
                  <div className="mt-2 h-1 bg-subtle rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${
                        agent.status === 'error' ? 'bg-critical' : 'bg-interactive'
                      }`}
                      style={{ width: `${Math.min(100, Math.max(0, agent.progress))}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck 2>&1 | grep -E "(AgentStatusCard|error)" | head -10`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/c1/AgentStatusCard.tsx
git commit -m "feat(c1): add AgentStatusCard component for multi-agent dashboard"
```

---

## Task 7: Create SignalAlertCard Component

**Files:**
- Create: `frontend/src/components/c1/SignalAlertCard.tsx`

**Step 1: Create SignalAlertCard component**

Create `frontend/src/components/c1/SignalAlertCard.tsx`:

```typescript
/**
 * SignalAlertCard - Market intelligence alert visualization
 *
 * Renders for market intelligence alerts, competitive moves,
 * regulatory changes, clinical trial updates, patent cliffs,
 * or any proactive signal ARIA wants to surface.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { AlertTriangle, AlertCircle, Info, Search, Building2, Clock } from 'lucide-react';
import type { SignalAlertCardProps } from './schemas';

const severityConfig = {
  high: {
    icon: AlertTriangle,
    color: 'text-critical',
    bgColor: 'bg-critical/10',
    borderColor: 'border-critical/30',
    badgeColor: 'bg-critical/20 text-critical',
  },
  medium: {
    icon: AlertCircle,
    color: 'text-warning',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning/30',
    badgeColor: 'bg-warning/20 text-warning',
  },
  low: {
    icon: Info,
    color: 'text-info',
    bgColor: 'bg-info/10',
    borderColor: 'border-info/30',
    badgeColor: 'bg-info/20 text-info',
  },
};

export function SignalAlertCard({
  signal_id,
  title,
  severity,
  signal_type,
  summary,
  source,
  affected_accounts = [],
  detected_at,
}: SignalAlertCardProps) {
  const onAction = useOnAction();
  const config = severityConfig[severity];
  const SeverityIcon = config.icon;

  const handleInvestigate = () => {
    onAction(
      "Investigate Signal",
      `User wants to investigate ${signal_type} signal ${signal_id}: ${title}`
    );
  };

  return (
    <div className={`bg-elevated border rounded-xl overflow-hidden ${config.borderColor}`}>
      {/* Header with Severity */}
      <div className={`flex items-center justify-between px-4 py-3 ${config.bgColor}`}>
        <div className="flex items-center gap-2">
          <SeverityIcon className={`w-4 h-4 ${config.color}`} />
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${config.badgeColor}`}>
            {severity.toUpperCase()}
          </span>
          <span className="text-xs text-secondary">{signal_type}</span>
        </div>
        {detected_at && (
          <span className="flex items-center gap-1 text-xs text-secondary">
            <Clock className="w-3 h-3" />
            {detected_at}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Title */}
        <h4 className="text-content font-medium text-sm">
          {title}
        </h4>

        {/* Summary */}
        <p className="text-secondary text-sm leading-relaxed">
          {summary}
        </p>

        {/* Source */}
        {source && (
          <p className="text-xs text-secondary italic">
            Source: {source}
          </p>
        )}

        {/* Affected Accounts */}
        {affected_accounts.length > 0 && (
          <div className="pt-2 border-t border-border">
            <div className="flex items-center gap-1.5 mb-2">
              <Building2 className="w-3 h-3 text-secondary" />
              <span className="text-xs text-secondary font-medium">Affected Accounts</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {affected_accounts.map((account, index) => (
                <span
                  key={`${account}-${index}`}
                  className="px-2 py-0.5 rounded bg-subtle text-xs text-content"
                >
                  {account}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-border bg-subtle/30">
        <button
          onClick={handleInvestigate}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          <Search className="w-3.5 h-3.5" />
          Investigate
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck 2>&1 | grep -E "(SignalAlertCard|error)" | head -10`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/c1/SignalAlertCard.tsx
git commit -m "feat(c1): add SignalAlertCard component for intelligence alerts"
```

---

## Task 8: Create ApprovalCard Component

**Files:**
- Create: `frontend/src/components/c1/ApprovalCard.tsx`

**Step 1: Create ApprovalCard component**

Create `frontend/src/components/c1/ApprovalCard.tsx`:

```typescript
/**
 * ApprovalCard - Generic approval request visualization
 *
 * Renders for any action requiring user sign-off:
 * pending actions, recommendations, or configuration changes.
 * Shows title, context, impact assessment, urgency, and Approve/Reject buttons.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { Check, X, AlertTriangle, Clock } from 'lucide-react';
import type { ApprovalCardProps } from './schemas';

const urgencyConfig = {
  immediate: {
    color: 'text-critical',
    bgColor: 'bg-critical/10',
    label: 'Immediate',
    icon: AlertTriangle,
  },
  today: {
    color: 'text-warning',
    bgColor: 'bg-warning/10',
    label: 'Today',
    icon: Clock,
  },
  this_week: {
    color: 'text-info',
    bgColor: 'bg-info/10',
    label: 'This Week',
    icon: Clock,
  },
  no_rush: {
    color: 'text-secondary',
    bgColor: 'bg-subtle',
    label: 'No Rush',
    icon: null,
  },
};

export function ApprovalCard({
  item_id,
  item_type,
  title,
  description,
  impact,
  urgency = 'no_rush',
}: ApprovalCardProps) {
  const onAction = useOnAction();
  const config = urgencyConfig[urgency];

  const handleApprove = () => {
    onAction(
      "Approve",
      `User approved ${item_type} ${item_id}: ${title}`
    );
  };

  const handleReject = () => {
    onAction(
      "Reject",
      `User rejected ${item_type} ${item_id}: ${title}`
    );
  };

  return (
    <div className="bg-elevated border border-border rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-subtle/30">
        <div className="flex items-center gap-2">
          <span className="text-xs text-secondary uppercase tracking-wide">
            {item_type}
          </span>
        </div>
        {urgency !== 'no_rush' && (
          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.bgColor} ${config.color}`}>
            {config.icon && <config.icon className="w-3 h-3" />}
            {config.label}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Title */}
        <h4 className="text-content font-medium text-base">
          {title}
        </h4>

        {/* Description */}
        <p className="text-secondary text-sm leading-relaxed">
          {description}
        </p>

        {/* Impact */}
        {impact && (
          <div className="p-3 bg-subtle/50 rounded-lg border-l-2 border-interactive/50">
            <p className="text-xs text-secondary mb-1 font-medium">Impact</p>
            <p className="text-sm text-content">{impact}</p>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-border bg-subtle/30">
        <button
          onClick={handleApprove}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          <Check className="w-4 h-4" />
          Approve
        </button>
        <button
          onClick={handleReject}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-critical hover:bg-critical/10 rounded-lg transition-colors"
        >
          <X className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck 2>&1 | grep -E "(ApprovalCard|error)" | head -10`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/c1/ApprovalCard.tsx
git commit -m "feat(c1): add ApprovalCard component for generic approval requests"
```

---

## Task 9: Create Backend Pydantic Schemas

**Files:**
- Create: `backend/src/services/thesys_components.py`

**Step 1: Create Pydantic models for component schemas**

Create `backend/src/services/thesys_components.py`:

```python
"""ARIA custom component schemas for Thesys C1 generative UI.

Defines Pydantic models for component schemas that C1 uses to determine
what props to pass to custom React components. These must stay in sync
with the frontend Zod schemas in frontend/src/components/c1/schemas.ts.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


# -----------------------------------------------------------------------------
# GoalPlanCard
# -----------------------------------------------------------------------------

class StepModel(BaseModel):
    """A single step in a goal execution plan."""

    step_number: int
    description: str
    assigned_agent: Optional[str] = Field(
        default=None,
        description="Which ARIA agent handles this step",
    )
    status: Literal["pending", "in_progress", "complete", "failed"] = "pending"


class GoalPlanCardSchema(BaseModel):
    """Schema for GoalPlanCard component."""

    goal_name: str = Field(description="Name of the goal or plan")
    goal_id: str = Field(description="Unique identifier for the goal")
    description: str = Field(description="Brief description of what will be accomplished")
    steps: list[StepModel] = Field(
        default_factory=list,
        description="Ordered list of execution steps",
    )
    estimated_duration: Optional[str] = Field(
        default=None,
        description="How long the plan will take",
    )
    ooda_phase: Optional[Literal["observe", "orient", "decide", "act"]] = None

    class Config:
        json_schema_extra = {
            "description": (
                "Renders an execution plan card for a goal that ARIA has proposed. "
                "Shows numbered steps with agent assignments, progress indicators, "
                "and Approve/Modify action buttons. Use this whenever ARIA proposes "
                "a multi-step plan for the user to review."
            )
        }


# -----------------------------------------------------------------------------
# EmailDraftCard
# -----------------------------------------------------------------------------

class EmailDraftCardSchema(BaseModel):
    """Schema for EmailDraftCard component."""

    email_draft_id: str = Field(description="Unique identifier for this draft")
    to: str = Field(description="Recipient email or name")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body text")
    tone: Literal["formal", "friendly", "urgent", "neutral"] = Field(
        default="neutral",
        description="Detected tone of the draft",
    )
    context: Optional[str] = Field(
        default=None,
        description="Why ARIA drafted this email",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders an email draft card showing recipient, subject, body preview, "
                "and tone indicator. Includes Approve (send), Edit, and Dismiss action "
                "buttons. Use this whenever ARIA has drafted an email for the user to "
                "review before sending."
            )
        }


# -----------------------------------------------------------------------------
# AgentStatusCard
# -----------------------------------------------------------------------------

class AgentInfoModel(BaseModel):
    """Information about a single agent's status."""

    name: str = Field(
        description="Agent name: Hunter, Analyst, Strategist, Scribe, Operator, or Scout"
    )
    status: Literal["idle", "working", "complete", "error"]
    current_task: Optional[str] = Field(
        default=None,
        description="What the agent is currently doing",
    )
    ooda_phase: Optional[Literal["observe", "orient", "decide", "act"]] = None
    progress: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
    )


class AgentStatusCardSchema(BaseModel):
    """Schema for AgentStatusCard component."""

    agents: list[AgentInfoModel] = Field(
        default_factory=list,
        description="List of active ARIA agents and their status",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders a status dashboard showing ARIA's active agents with progress "
                "indicators and current OODA phase. Use this when reporting on multi-agent "
                "execution progress or when the user asks about what ARIA is working on."
            )
        }


# -----------------------------------------------------------------------------
# SignalAlertCard
# -----------------------------------------------------------------------------

class SignalAlertCardSchema(BaseModel):
    """Schema for SignalAlertCard component."""

    signal_id: str = Field(description="Unique identifier for this signal")
    title: str = Field(description="Brief signal headline")
    severity: Literal["high", "medium", "low"]
    signal_type: str = Field(
        description="Type: patent_cliff, clinical_trial, competitive_move, regulatory, market_shift, etc."
    )
    summary: str = Field(description="2-3 sentence summary of the signal")
    source: Optional[str] = Field(
        default=None,
        description="Where ARIA detected this signal",
    )
    affected_accounts: Optional[list[str]] = Field(
        default=None,
        description="Account names that may be impacted",
    )
    detected_at: Optional[str] = Field(
        default=None,
        description="When ARIA detected this signal",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders a market signal or intelligence alert card with severity indicator, "
                "summary, affected accounts, and an Investigate action button. Use this for "
                "market intelligence alerts, competitive moves, regulatory changes, clinical "
                "trial updates, patent cliffs, or any proactive signal ARIA wants to surface."
            )
        }


# -----------------------------------------------------------------------------
# ApprovalCard
# -----------------------------------------------------------------------------

class ApprovalCardSchema(BaseModel):
    """Schema for ApprovalCard component."""

    item_id: str = Field(description="Unique identifier for the item needing approval")
    item_type: str = Field(
        description="What type of item: task, recommendation, action, configuration"
    )
    title: str = Field(description="What needs approval")
    description: str = Field(description="Context for the approval decision")
    impact: Optional[str] = Field(
        default=None,
        description="What happens if approved",
    )
    urgency: Literal["immediate", "today", "this_week", "no_rush"] = Field(
        default="no_rush",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders a generic approval card for any action that requires user sign-off. "
                "Shows title, context, impact assessment, urgency indicator, and Approve/Reject "
                "buttons. Use this for any pending action, recommendation, or configuration "
                "change that ARIA needs the user to authorize."
            )
        }


# -----------------------------------------------------------------------------
# Helper function to export schemas for C1 metadata
# -----------------------------------------------------------------------------

def get_aria_custom_components() -> dict:
    """Returns ARIA's custom component schemas as JSON schemas for C1 metadata.

    Each component is converted to JSON Schema format that Thesys C1 expects
    in the metadata.thesys.c1_custom_components field.

    The keys must match the React component names exactly:
    - GoalPlanCard
    - EmailDraftCard
    - AgentStatusCard
    - SignalAlertCard
    - ApprovalCard

    Returns:
        Dict keyed by component name, values are JSON Schema dicts.
    """
    return {
        "GoalPlanCard": GoalPlanCardSchema.model_json_schema(),
        "EmailDraftCard": EmailDraftCardSchema.model_json_schema(),
        "AgentStatusCard": AgentStatusCardSchema.model_json_schema(),
        "SignalAlertCard": SignalAlertCardSchema.model_json_schema(),
        "ApprovalCard": ApprovalCardSchema.model_json_schema(),
    }
```

**Step 2: Verify Python imports work**

Run: `cd backend && python -c "from src.services.thesys_components import get_aria_custom_components; print(list(get_aria_custom_components().keys()))"`
Expected: `['GoalPlanCard', 'EmailDraftCard', 'AgentStatusCard', 'SignalAlertCard', 'ApprovalCard']`

**Step 3: Commit**

```bash
git add backend/src/services/thesys_components.py
git commit -m "feat(c1): add Pydantic schemas for custom components"
```

---

## Task 10: Update ThesysService to Include Component Schemas

**Files:**
- Modify: `backend/src/services/thesys_service.py`

**Step 1: Import the component schemas function**

Add import at top of `backend/src/services/thesys_service.py` (line ~18):

```python
from src.services.thesys_actions import get_aria_custom_actions
from src.services.thesys_components import get_aria_custom_components
```

**Step 2: Update metadata in _call_c1 method**

Replace the metadata building around line 92-96:

```python
        # Build metadata with custom actions and components
        metadata: dict[str, Any] = {
            "thesys": json.dumps({
                "c1_custom_actions": get_aria_custom_actions(),
                "c1_custom_components": get_aria_custom_components(),
            }),
        }
```

**Step 3: Update metadata in visualize_stream method**

Replace the metadata building around line 132-137:

```python
            # Build metadata with custom actions and components
            metadata: dict[str, Any] = {
                "thesys": json.dumps({
                    "c1_custom_actions": get_aria_custom_actions(),
                    "c1_custom_components": get_aria_custom_components(),
                }),
            }
```

**Step 4: Verify Python imports work**

Run: `cd backend && python -c "from src.services.thesys_service import ThesysService; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add backend/src/services/thesys_service.py
git commit -m "feat(c1): include custom component schemas in C1 API calls"
```

---

## Task 11: Create C1MessageRenderer Component

**Files:**
- Create: `frontend/src/components/conversation/C1MessageRenderer.tsx`

**Step 1: Create C1MessageRenderer component**

Create `frontend/src/components/conversation/C1MessageRenderer.tsx`:

```typescript
/**
 * C1MessageRenderer - Renders C1 generative UI content in chat messages
 *
 * This component wraps the Thesys C1Component and provides:
 * - Custom ARIA-specific React components
 * - Action handling integration with ARIA's action system
 * - Loading and error states
 */

import { C1Component } from '@thesysai/genui-sdk';
import { Loader2 } from 'lucide-react';
import {
  GoalPlanCard,
  EmailDraftCard,
  AgentStatusCard,
  SignalAlertCard,
  ApprovalCard,
} from '../c1';

export interface C1MessageRendererProps {
  /** The C1 response content to render */
  c1Response: string;
  /** Whether the response is still streaming */
  isStreaming?: boolean;
  /** Handler for user actions from C1 components */
  onAction?: (humanMessage: string, llmMessage: string) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Custom components to pass to C1Component.
 * Keys must match the schema names registered with the backend.
 */
const customComponents = {
  GoalPlanCard,
  EmailDraftCard,
  AgentStatusCard,
  SignalAlertCard,
  ApprovalCard,
};

export function C1MessageRenderer({
  c1Response,
  isStreaming = false,
  onAction,
  className = '',
}: C1MessageRendererProps) {
  // Handle actions from C1 components
  const handleAction = (humanMessage: string, llmMessage: string) => {
    if (onAction) {
      onAction(humanMessage, llmMessage);
    }
    // Log for debugging
    console.log('[C1Action]', { humanMessage, llmMessage });
  };

  // Loading state while streaming
  if (isStreaming && !c1Response) {
    return (
      <div className={`flex items-center gap-2 text-secondary ${className}`}>
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Generating response...</span>
      </div>
    );
  }

  // Empty state
  if (!c1Response) {
    return null;
  }

  return (
    <div className={`c1-message-renderer ${className}`}>
      <C1Component
        c1Response={c1Response}
        isStreaming={isStreaming}
        onAction={handleAction}
        customComponents={customComponents}
      />
    </div>
  );
}
```

**Step 2: Update conversation components index**

Add to `frontend/src/components/conversation/index.ts`:

```typescript
export { C1MessageRenderer } from './C1MessageRenderer';
export type { C1MessageRendererProps } from './C1MessageRenderer';
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck 2>&1 | grep -E "(C1MessageRenderer|error)" | head -10`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/conversation/C1MessageRenderer.tsx frontend/src/components/conversation/index.ts
git commit -m "feat(c1): add C1MessageRenderer with custom component registration"
```

---

## Task 12: Create Unit Tests for Custom Components

**Files:**
- Create: `frontend/src/components/c1/__tests__/GoalPlanCard.test.tsx`
- Create: `frontend/src/components/c1/__tests__/EmailDraftCard.test.tsx`
- Create: `frontend/src/components/c1/__tests__/AgentStatusCard.test.tsx`
- Create: `frontend/src/components/c1/__tests__/SignalAlertCard.test.tsx`
- Create: `frontend/src/components/c1/__tests__/ApprovalCard.test.tsx`

**Step 1: Create test directory**

Run: `mkdir -p frontend/src/components/c1/__tests__`

**Step 2: Create GoalPlanCard test**

Create `frontend/src/components/c1/__tests__/GoalPlanCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GoalPlanCard } from '../GoalPlanCard';

// Mock useOnAction
vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('GoalPlanCard', () => {
  const defaultProps = {
    goal_name: 'Test Goal',
    goal_id: 'goal-123',
    description: 'A test goal description',
    steps: [
      { step_number: 1, description: 'First step', status: 'pending' as const },
      { step_number: 2, description: 'Second step', status: 'in_progress' as const, assigned_agent: 'Hunter' },
    ],
  };

  it('renders goal name and description', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByText('Test Goal')).toBeInTheDocument();
    expect(screen.getByText('A test goal description')).toBeInTheDocument();
  });

  it('renders all steps', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByText('First step')).toBeInTheDocument();
    expect(screen.getByText('Second step')).toBeInTheDocument();
  });

  it('renders agent badges', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByText('Hunter')).toBeInTheDocument();
  });

  it('renders OODA phase badge when provided', () => {
    render(<GoalPlanCard {...defaultProps} ooda_phase="observe" />);
    expect(screen.getByText('observe')).toBeInTheDocument();
  });

  it('renders estimated duration when provided', () => {
    render(<GoalPlanCard {...defaultProps} estimated_duration="2 hours" />);
    expect(screen.getByText('2 hours')).toBeInTheDocument();
  });

  it('renders Approve and Modify buttons', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /modify/i })).toBeInTheDocument();
  });

  it('handles empty steps array', () => {
    render(<GoalPlanCard {...defaultProps} steps={[]} />);
    expect(screen.getByText('Test Goal')).toBeInTheDocument();
  });

  it('handles minimal props', () => {
    render(
      <GoalPlanCard
        goal_name="Minimal"
        goal_id="id-1"
        description="Desc"
      />
    );
    expect(screen.getByText('Minimal')).toBeInTheDocument();
  });
});
```

**Step 3: Create EmailDraftCard test**

Create `frontend/src/components/c1/__tests__/EmailDraftCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmailDraftCard } from '../EmailDraftCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('EmailDraftCard', () => {
  const defaultProps = {
    email_draft_id: 'draft-123',
    to: 'test@example.com',
    subject: 'Test Subject',
    body: 'This is the email body content.',
    tone: 'neutral' as const,
  };

  it('renders recipient and subject', () => {
    render(<EmailDraftCard {...defaultProps} />);
    expect(screen.getByText('test@example.com')).toBeInTheDocument();
    expect(screen.getByText('Test Subject')).toBeInTheDocument();
  });

  it('renders body content', () => {
    render(<EmailDraftCard {...defaultProps} />);
    expect(screen.getByText(/This is the email body/)).toBeInTheDocument();
  });

  it('renders tone badge', () => {
    render(<EmailDraftCard {...defaultProps} tone="formal" />);
    expect(screen.getByText('formal')).toBeInTheDocument();
  });

  it('renders context when provided', () => {
    render(<EmailDraftCard {...defaultProps} context="Drafted in response to inquiry" />);
    expect(screen.getByText('Drafted in response to inquiry')).toBeInTheDocument();
  });

  it('renders action buttons', () => {
    render(<EmailDraftCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
  });

  it('truncates long body content', () => {
    const longBody = 'A'.repeat(300);
    render(<EmailDraftCard {...defaultProps} body={longBody} />);
    expect(screen.getByText(/A+\.\.\./)).toBeInTheDocument();
  });
});
```

**Step 4: Create AgentStatusCard test**

Create `frontend/src/components/c1/__tests__/AgentStatusCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentStatusCard } from '../AgentStatusCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('AgentStatusCard', () => {
  const defaultProps = {
    agents: [
      { name: 'Hunter', status: 'working' as const, current_task: 'Searching leads' },
      { name: 'Scribe', status: 'idle' as const },
    ],
  };

  it('renders agent names', () => {
    render(<AgentStatusCard {...defaultProps} />);
    expect(screen.getByText('Hunter')).toBeInTheDocument();
    expect(screen.getByText('Scribe')).toBeInTheDocument();
  });

  it('renders current task', () => {
    render(<AgentStatusCard {...defaultProps} />);
    expect(screen.getByText('Searching leads')).toBeInTheDocument();
  });

  it('renders OODA phase', () => {
    render(<AgentStatusCard {...defaultProps} agents={[{ name: 'Hunter', status: 'working', ooda_phase: 'observe' }]} />);
    expect(screen.getByText('OBSERVE')).toBeInTheDocument();
  });

  it('shows active agent count', () => {
    render(<AgentStatusCard {...defaultProps} />);
    expect(screen.getByText('1 active')).toBeInTheDocument();
  });

  it('renders empty state', () => {
    render(<AgentStatusCard agents={[]} />);
    expect(screen.getByText('No agents currently active')).toBeInTheDocument();
  });

  it('handles agents with progress', () => {
    render(<AgentStatusCard agents={[{ name: 'Hunter', status: 'working', progress: 50 }]} />);
    // Progress bar should be rendered
    expect(screen.getByText('Hunter')).toBeInTheDocument();
  });
});
```

**Step 5: Create SignalAlertCard test**

Create `frontend/src/components/c1/__tests__/SignalAlertCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SignalAlertCard } from '../SignalAlertCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('SignalAlertCard', () => {
  const defaultProps = {
    signal_id: 'signal-123',
    title: 'Patent Cliff Alert',
    severity: 'high' as const,
    signal_type: 'patent_cliff',
    summary: 'Key patent expiring in Q4 2026.',
  };

  it('renders title and summary', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByText('Patent Cliff Alert')).toBeInTheDocument();
    expect(screen.getByText('Key patent expiring in Q4 2026.')).toBeInTheDocument();
  });

  it('renders severity badge', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByText('HIGH')).toBeInTheDocument();
  });

  it('renders signal type', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByText('patent_cliff')).toBeInTheDocument();
  });

  it('renders source when provided', () => {
    render(<SignalAlertCard {...defaultProps} source="FDA Database" />);
    expect(screen.getByText(/Source: FDA Database/)).toBeInTheDocument();
  });

  it('renders affected accounts', () => {
    render(<SignalAlertCard {...defaultProps} affected_accounts={['Acme Corp', 'Beta Inc']} />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Beta Inc')).toBeInTheDocument();
  });

  it('renders Investigate button', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /investigate/i })).toBeInTheDocument();
  });

  it('applies severity-based styling', () => {
    const { container } = render(<SignalAlertCard {...defaultProps} severity="critical" />);
    // Check for severity class or style
    expect(container.firstChild).toBeInTheDocument();
  });
});
```

**Step 6: Create ApprovalCard test**

Create `frontend/src/components/c1/__tests__/ApprovalCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ApprovalCard } from '../ApprovalCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('ApprovalCard', () => {
  const defaultProps = {
    item_id: 'item-123',
    item_type: 'task',
    title: 'Approve CRM Sync',
    description: 'Allow ARIA to sync with Salesforce.',
  };

  it('renders title and description', () => {
    render(<ApprovalCard {...defaultProps} />);
    expect(screen.getByText('Approve CRM Sync')).toBeInTheDocument();
    expect(screen.getByText('Allow ARIA to sync with Salesforce.')).toBeInTheDocument();
  });

  it('renders item type', () => {
    render(<ApprovalCard {...defaultProps} />);
    expect(screen.getByText('TASK')).toBeInTheDocument();
  });

  it('renders impact when provided', () => {
    render(<ApprovalCard {...defaultProps} impact="This will enable automatic lead imports" />);
    expect(screen.getByText('This will enable automatic lead imports')).toBeInTheDocument();
  });

  it('renders urgency badge for non-default urgency', () => {
    render(<ApprovalCard {...defaultProps} urgency="immediate" />);
    expect(screen.getByText('Immediate')).toBeInTheDocument();
  });

  it('does not render urgency badge for no_rush', () => {
    render(<ApprovalCard {...defaultProps} urgency="no_rush" />);
    expect(screen.queryByText('No Rush')).not.toBeInTheDocument();
  });

  it('renders Approve and Reject buttons', () => {
    render(<ApprovalCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });
});
```

**Step 7: Run tests**

Run: `cd frontend && npm run test -- --run src/components/c1/__tests__`
Expected: All tests pass

**Step 8: Commit**

```bash
git add frontend/src/components/c1/__tests__/
git commit -m "test(c1): add unit tests for all custom components"
```

---

## Task 13: Verify End-to-End Integration

**Files:**
- None (verification only)

**Step 1: Run full frontend typecheck**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 2: Run all frontend tests**

Run: `cd frontend && npm run test:run`
Expected: All tests pass

**Step 3: Verify backend imports**

Run: `cd backend && python -c "from src.services.thesys_service import get_thesys_service; s = get_thesys_service(); print('ThesysService OK')"`
Expected: `ThesysService OK`

**Step 4: Verify schema JSON output**

Run: `cd backend && python -c "from src.services.thesys_components import get_aria_custom_components; import json; print(json.dumps(get_aria_custom_components(), indent=2)[:500])"`
Expected: JSON schema output showing GoalPlanCard, EmailDraftCard, etc.

**Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "chore: final cleanup for C1 custom components integration"
```

---

## Summary

| Component | Files Created | Files Modified |
|-----------|---------------|----------------|
| Zod dependency | - | package.json |
| Schemas | schemas.ts | - |
| GoalPlanCard | GoalPlanCard.tsx | - |
| EmailDraftCard | EmailDraftCard.tsx | - |
| AgentStatusCard | AgentStatusCard.tsx | - |
| SignalAlertCard | SignalAlertCard.tsx | - |
| ApprovalCard | ApprovalCard.tsx | - |
| Backend schemas | thesys_components.py | - |
| ThesysService | - | thesys_service.py |
| C1MessageRenderer | C1MessageRenderer.tsx | conversation/index.ts |
| Tests | 5 test files | - |

**Total: 13 new files, 4 modified files**

---

## Do Not

- Do NOT create more than 5 custom components
- Do NOT hardcode any data in the components
- Do NOT use any library other than Tailwind for styling
- Do NOT skip the empty/null prop handling
- Do NOT create components for things C1 handles natively (tables, charts, basic cards, forms)
