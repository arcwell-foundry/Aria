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

export interface AvailableSkillsFilters {
  query?: string;
  trust_level?: TrustLevel;
  life_sciences?: boolean;
  limit?: number;
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
