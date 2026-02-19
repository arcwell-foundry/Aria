/** Admin Dashboard API Client.
 *
 * TypeScript interfaces and API functions for the admin monitoring dashboard.
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DashboardOverview {
  active_users: number;
  cost_today: number;
  active_ooda: number;
  pass_rate: number;
  avg_trust: number;
  cost_alert: boolean;
}

export interface ActiveOODACycle {
  cycle_id: string;
  goal_id: string;
  user_id: string;
  current_phase: string;
  iteration: number;
  total_duration_ms: number;
  total_tokens: number;
  phases_completed: number;
  agents_dispatched: string[];
  started_at: string;
}

export interface AgentExecution {
  trace_id: string;
  delegatee: string;
  status: string;
  cost_usd: number;
  created_at: string;
  task_description: string;
  input_size: number;
  output_size: number;
  verification_passed: boolean | null;
}

export interface UserUsageSummary {
  user_id: string;
  total_cost: number;
  total_tokens: number;
  total_thinking_tokens: number;
  total_calls: number;
  days_active: number;
}

export interface DailyTotal {
  date: string;
  cost: number;
  tokens: number;
  thinking_tokens: number;
}

export interface UsageAlert {
  user_id: string;
  date: string;
  cost: number;
  message: string;
}

export interface TeamUsageResponse {
  users: UserUsageSummary[];
  daily_totals: DailyTotal[];
  alerts: UsageAlert[];
}

export interface TrustCategory {
  action_category: string;
  trust_score: number;
  successful_actions: number;
  failed_actions: number;
  override_count: number;
}

export interface UserTrustSummary {
  user_id: string;
  avg_trust: number;
  categories: TrustCategory[];
  is_stuck: boolean;
  total_actions: number;
}

export interface TrustEvolutionPoint {
  user_id: string;
  action_category: string;
  trust_score: number;
  change_type: string;
  recorded_at: string;
}

export interface AgentVerificationStats {
  agent: string;
  passed: number;
  failed: number;
  total: number;
  pass_rate: number;
}

export interface TaskTypeVerificationStats {
  task_type: string;
  passed: number;
  failed: number;
  total: number;
  pass_rate: number;
}

export interface VerificationStatsResponse {
  overall_pass_rate: number;
  total_verified: number;
  total_passed: number;
  worst_agent: string;
  by_agent: AgentVerificationStats[];
  by_task_type: TaskTypeVerificationStats[];
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

export async function getDashboardOverview(): Promise<DashboardOverview> {
  const response = await apiClient.get<DashboardOverview>("/admin/dashboard/overview");
  return response.data;
}

export async function getActiveOODACycles(
  limit: number = 50,
): Promise<ActiveOODACycle[]> {
  const response = await apiClient.get<ActiveOODACycle[]>("/admin/dashboard/ooda/active", {
    params: { limit },
  });
  return response.data;
}

export async function getAgentWaterfall(
  hours: number = 24,
  limit: number = 200,
): Promise<AgentExecution[]> {
  const response = await apiClient.get<AgentExecution[]>("/admin/dashboard/agents/waterfall", {
    params: { hours, limit },
  });
  return response.data;
}

export async function getTeamUsage(
  days: number = 30,
  granularity: string = "day",
): Promise<TeamUsageResponse> {
  const response = await apiClient.get<TeamUsageResponse>("/admin/dashboard/usage", {
    params: { days, granularity },
  });
  return response.data;
}

export async function getTrustSummaries(): Promise<UserTrustSummary[]> {
  const response = await apiClient.get<UserTrustSummary[]>("/admin/dashboard/trust/summaries");
  return response.data;
}

export async function getTrustEvolution(
  userId?: string,
  days: number = 30,
): Promise<TrustEvolutionPoint[]> {
  const response = await apiClient.get<TrustEvolutionPoint[]>("/admin/dashboard/trust/evolution", {
    params: { user_id: userId, days },
  });
  return response.data;
}

export async function getVerificationStats(
  days: number = 30,
): Promise<VerificationStatsResponse> {
  const response = await apiClient.get<VerificationStatsResponse>("/admin/dashboard/verification", {
    params: { days },
  });
  return response.data;
}
