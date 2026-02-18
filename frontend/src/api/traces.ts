import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types — match backend DelegationTrace.to_dict() serialization
// ---------------------------------------------------------------------------

export type TraceStatus =
  | "dispatched"
  | "executing"
  | "completed"
  | "failed"
  | "cancelled"
  | "re_delegated";

export interface VerificationResult {
  passed: boolean;
  issues: string[];
  confidence: number;
  suggestions: string[];
}

export interface CapabilityToken {
  token_id: string;
  delegatee: string;
  goal_id: string;
  allowed_actions: string[];
  denied_actions: string[];
  data_scope: Record<string, unknown>;
  time_limit_seconds: number;
  created_at: string;
}

export interface TaskCharacteristics {
  complexity: number;
  criticality: number;
  uncertainty: number;
  reversibility: number;
  verifiability: number;
  subjectivity: number;
  contextuality: number;
}

export interface DelegationTrace {
  trace_id: string;
  goal_id: string | null;
  parent_trace_id: string | null;
  user_id: string;
  delegator: string;
  delegatee: string;
  task_description: string;
  task_characteristics: TaskCharacteristics | null;
  capability_token: CapabilityToken | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  thinking_trace: string | null;
  verification_result: VerificationResult | null;
  approval_record: Record<string, unknown> | null;
  cost_usd: number;
  status: TraceStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  created_at: string | null;
}

export interface TraceSummary {
  agent_count: number;
  unique_agents: string[];
  total_cost_usd: number;
  total_duration_ms: number;
  verification_passes: number;
  verification_failures: number;
  retries: number;
}

export interface TraceTreeResponse {
  traces: DelegationTrace[];
  summary: TraceSummary;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function getTraceTree(goalId: string): Promise<TraceTreeResponse> {
  const response = await apiClient.get<TraceTreeResponse>(
    `/traces/${goalId}/tree`
  );
  return response.data;
}

export async function getRecentTraces(
  limit?: number
): Promise<DelegationTrace[]> {
  const params = new URLSearchParams();
  if (limit) params.append("limit", limit.toString());

  const url = params.toString() ? `/traces/recent?${params}` : "/traces/recent";
  const response = await apiClient.get<DelegationTrace[]>(url);
  return response.data;
}
