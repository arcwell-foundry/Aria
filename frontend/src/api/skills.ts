import { apiClient } from "./client";

// Types matching backend Pydantic models

export type TrustLevel = "core" | "verified" | "community" | "user";

export interface AvailableSkill {
  id: string;
  skill_path: string;
  skill_name: string;
  description: string | null;
  author: string | null;
  version: string | null;
  tags: string[];
  trust_level: TrustLevel;
  life_sciences_relevant: boolean;
}

export interface InstalledSkill {
  id: string;
  skill_id: string;
  skill_path: string;
  trust_level: TrustLevel;
  execution_count: number;
  success_count: number;
  installed_at: string;
  last_used_at: string | null;
}

export interface SkillExecution {
  skill_id: string;
  skill_path: string;
  trust_level: TrustLevel;
  success: boolean;
  result: unknown;
  error: string | null;
  execution_time_ms: number;
  sanitized: boolean;
}

export interface AuditEntry {
  id: string;
  user_id: string;
  skill_id: string;
  skill_path: string;
  skill_trust_level: TrustLevel;
  trigger_reason: string;
  data_classes_requested: string[];
  data_classes_granted: string[];
  input_hash: string;
  output_hash: string | null;
  execution_time_ms: number;
  success: boolean;
  error: string | null;
  data_redacted: boolean;
  tokens_used: string[];
  task_id: string | null;
  agent_id: string | null;
  security_flags: string[];
  created_at: string;
}

export interface TrustInfo {
  skill_id: string;
  successful_executions: number;
  failed_executions: number;
  session_trust_granted: boolean;
  globally_approved: boolean;
  globally_approved_at: string | null;
}

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

export interface AvailableSkillsFilters {
  query?: string;
  trust_level?: TrustLevel;
  life_sciences?: boolean;
  limit?: number;
}

export interface SkillPerformance {
  skill_id: string;
  success_rate: number;
  total_executions: number;
  avg_execution_time_ms: number;
  satisfaction: { positive: number; negative: number; ratio: number };
  trust_level: TrustLevel;
  recent_failures: number;
}

export interface CustomSkill {
  id: string;
  skill_name: string;
  description: string | null;
  skill_type: string;
  definition: Record<string, unknown>;
  trust_level: TrustLevel;
  performance_metrics: Record<string, unknown>;
  is_published: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface UpdateCustomSkillData {
  skill_name?: string;
  description?: string;
  definition?: Record<string, unknown>;
}

// API functions

export async function listAvailableSkills(
  filters?: AvailableSkillsFilters
): Promise<AvailableSkill[]> {
  const params = new URLSearchParams();
  if (filters?.query) params.append("query", filters.query);
  if (filters?.trust_level) params.append("trust_level", filters.trust_level);
  if (filters?.life_sciences !== undefined)
    params.append("life_sciences", String(filters.life_sciences));
  if (filters?.limit) params.append("limit", String(filters.limit));

  const url = params.toString() ? `/skills/available?${params}` : "/skills/available";
  const response = await apiClient.get<AvailableSkill[]>(url);
  return response.data;
}

export async function listInstalledSkills(): Promise<InstalledSkill[]> {
  const response = await apiClient.get<InstalledSkill[]>("/skills/installed");
  return response.data;
}

export async function installSkill(skillId: string): Promise<InstalledSkill> {
  const response = await apiClient.post<InstalledSkill>("/skills/install", {
    skill_id: skillId,
  });
  return response.data;
}

export async function uninstallSkill(skillId: string): Promise<void> {
  await apiClient.delete(`/skills/${skillId}`);
}

export async function executeSkill(
  skillId: string,
  inputData: Record<string, unknown> = {}
): Promise<SkillExecution> {
  const response = await apiClient.post<SkillExecution>("/skills/execute", {
    skill_id: skillId,
    input_data: inputData,
  });
  return response.data;
}

export async function getSkillAudit(
  skillId?: string,
  limit = 50,
  offset = 0
): Promise<AuditEntry[]> {
  const params = new URLSearchParams();
  if (skillId) params.append("skill_id", skillId);
  params.append("limit", String(limit));
  params.append("offset", String(offset));

  const response = await apiClient.get<AuditEntry[]>(`/skills/audit?${params}`);
  return response.data;
}

export async function getSkillTrust(skillId: string): Promise<TrustInfo> {
  const response = await apiClient.get<TrustInfo>(`/skills/autonomy/${skillId}`);
  return response.data;
}

export async function approveSkillGlobally(skillId: string): Promise<TrustInfo> {
  const response = await apiClient.post<TrustInfo>(
    `/skills/autonomy/${skillId}/approve`
  );
  return response.data;
}

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

export async function getSkillPerformance(
  skillId: string
): Promise<SkillPerformance> {
  const response = await apiClient.get<SkillPerformance>(
    `/skills/performance/${skillId}`
  );
  return response.data;
}

export async function submitSkillFeedback(
  executionId: string,
  feedback: "positive" | "negative"
): Promise<void> {
  await apiClient.post(`/skills/${executionId}/feedback`, { feedback });
}

export async function listCustomSkills(): Promise<CustomSkill[]> {
  const response = await apiClient.get<CustomSkill[]>("/skills/custom");
  return response.data;
}

export async function updateCustomSkill(
  skillId: string,
  data: UpdateCustomSkillData
): Promise<CustomSkill> {
  const response = await apiClient.put<CustomSkill>(
    `/skills/custom/${skillId}`,
    data
  );
  return response.data;
}

export async function deleteCustomSkill(skillId: string): Promise<void> {
  await apiClient.delete(`/skills/custom/${skillId}`);
}
