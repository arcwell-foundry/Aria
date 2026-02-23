/**
 * Execution Progress Types — Step-level execution tracking for live progress cards.
 *
 * Used by ExecutionProgressCard, executionStore, and WebSocket event handlers
 * to track goal execution in real-time.
 */

export type ExecutionStepStatus = 'pending' | 'active' | 'completed' | 'failed' | 'retrying';
export type ApprovalMode = 'AUTO_EXECUTE' | 'EXECUTE_AND_NOTIFY' | 'APPROVE_PLAN' | 'APPROVE_EACH';

export interface ExecutionStep {
  step_id: string;
  title: string;
  description?: string;
  agent: string;
  status: ExecutionStepStatus;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  retry_count?: number;
  result_summary?: string;
}

export interface ExecutionProgressData {
  goal_id: string;
  title: string;
  approval_mode: ApprovalMode;
  steps: ExecutionStep[];
  overall_status: 'pending' | 'executing' | 'completed' | 'failed';
  estimated_remaining_seconds?: number;
  trust_context?: string;
}

// --- WebSocket Payloads ---

export interface StepStartedPayload {
  goal_id: string;
  step_id: string;
  agent: string;
  title: string;
}

export interface StepCompletedPayload {
  goal_id: string;
  step_id: string;
  agent: string;
  success: boolean;
  result_summary?: string;
  error_message?: string;
}

export interface StepRetryingPayload {
  goal_id: string;
  step_id: string;
  agent: string;
  retry_count: number;
  reason: string;
}

export interface ExecutionCompletePayload {
  goal_id: string;
  title: string;
  success: boolean;
  steps_completed: number;
  steps_total: number;
  summary?: string;
}

// --- Additional WebSocket Payloads ---

export interface ProgressUpdatePayload {
  goal_id: string;
  progress: number;       // 0-100
  status: string;
  agent_name: string | null;
  message: string | null;
}

export interface ActionPendingPayload {
  action_id: string;
  title: string;
  agent: string;
  risk_level: string;
  description: string | null;
  payload: Record<string, unknown>;
}

export interface SignalPayload {
  signal_type: string;
  title: string;
  severity: string;
  data: Record<string, unknown>;
}
