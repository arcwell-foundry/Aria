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
  steps: z.array(StepSchema).optional().default([]).describe("Ordered list of execution steps"),
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
  urgency: z.enum(["immediate", "today", "this_week", "no_rush"]).optional().default("no_rush"),
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
