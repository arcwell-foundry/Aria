import { apiClient } from "./client";

// --- Types ---

export interface AccountListItem {
  id: string;
  company_name: string;
  lifecycle_stage: string;
  status: string;
  health_score: number;
  expected_value: number | null;
  last_activity_at: string | null;
  tags: string[];
  next_action: string | null;
}

export interface TerritoryStats {
  total_accounts: number;
  total_value: number;
  avg_health: number;
  stage_counts: Record<string, number>;
}

export interface TerritoryResponse {
  accounts: AccountListItem[];
  stats: TerritoryStats;
}

export interface AccountPlan {
  id: string;
  user_id: string;
  lead_memory_id: string;
  strategy: string;
  next_actions: Array<{
    action: string;
    priority: "high" | "medium" | "low";
    due_in_days?: number;
  }>;
  stakeholder_summary: {
    champion?: string | null;
    decision_maker?: string | null;
    key_risk?: string;
  };
  generated_at: string;
  updated_at: string;
}

export interface ForecastStage {
  stage: string;
  count: number;
  total_value: number;
  weighted_value: number;
}

export interface ForecastResponse {
  stages: ForecastStage[];
  total_pipeline: number;
  weighted_pipeline: number;
}

export interface Quota {
  id: string;
  user_id: string;
  period: string;
  target_value: number;
  actual_value: number;
  created_at: string;
  updated_at: string;
}

// --- API functions ---

export async function listAccounts(
  stage?: string,
  sortBy?: string,
  limit?: number
): Promise<AccountListItem[]> {
  const params = new URLSearchParams();
  if (stage) params.append("stage", stage);
  if (sortBy) params.append("sort_by", sortBy);
  if (limit) params.append("limit", limit.toString());
  const url = params.toString() ? `/accounts?${params}` : "/accounts";
  const response = await apiClient.get<AccountListItem[]>(url);
  return response.data;
}

export async function getTerritory(
  stage?: string,
  sortBy?: string,
  limit?: number
): Promise<TerritoryResponse> {
  const params = new URLSearchParams();
  if (stage) params.append("stage", stage);
  if (sortBy) params.append("sort_by", sortBy);
  if (limit) params.append("limit", limit.toString());
  const url = params.toString()
    ? `/accounts/territory?${params}`
    : "/accounts/territory";
  const response = await apiClient.get<TerritoryResponse>(url);
  return response.data;
}

export async function getAccountPlan(leadId: string): Promise<AccountPlan> {
  const response = await apiClient.get<AccountPlan>(
    `/accounts/${leadId}/plan`
  );
  return response.data;
}

export async function updateAccountPlan(
  leadId: string,
  strategy: string
): Promise<AccountPlan> {
  const response = await apiClient.put<AccountPlan>(
    `/accounts/${leadId}/plan`,
    { strategy }
  );
  return response.data;
}

export async function getForecast(): Promise<ForecastResponse> {
  const response = await apiClient.get<ForecastResponse>(
    "/accounts/forecast"
  );
  return response.data;
}

export async function getQuotas(period?: string): Promise<Quota[]> {
  const params = period ? `?period=${period}` : "";
  const response = await apiClient.get<Quota[]>(
    `/accounts/quota${params}`
  );
  return response.data;
}

export async function setQuota(
  period: string,
  targetValue: number
): Promise<Quota> {
  const response = await apiClient.post<Quota>("/accounts/quota", {
    period,
    target_value: targetValue,
  });
  return response.data;
}
