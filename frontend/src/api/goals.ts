import { apiClient } from "./client";

// Enums matching backend
export type GoalType = "lead_gen" | "research" | "outreach" | "analysis" | "custom";
export type GoalStatus = "draft" | "active" | "paused" | "complete" | "failed";
export type AgentStatus = "pending" | "running" | "complete" | "failed";

// Request types
export interface CreateGoalData {
  title: string;
  description?: string;
  goal_type: GoalType;
  config?: Record<string, unknown>;
}

export interface UpdateGoalData {
  title?: string;
  description?: string;
  status?: GoalStatus;
  progress?: number;
  config?: Record<string, unknown>;
}

// Response types
export interface GoalAgent {
  id: string;
  goal_id: string;
  agent_type: string;
  agent_config: Record<string, unknown>;
  status: AgentStatus;
  created_at: string;
}

export interface AgentExecution {
  id: string;
  goal_agent_id: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  status: string;
  tokens_used: number;
  execution_time_ms: number | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface Goal {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  goal_type: GoalType;
  status: GoalStatus;
  strategy: Record<string, unknown> | null;
  config: Record<string, unknown>;
  progress: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  goal_agents?: GoalAgent[];
}

export interface GoalWithProgress extends Goal {
  recent_executions: AgentExecution[];
}

// API functions
export async function createGoal(data: CreateGoalData): Promise<Goal> {
  const response = await apiClient.post<Goal>("/goals", data);
  return response.data;
}

export async function listGoals(status?: GoalStatus, limit?: number): Promise<Goal[]> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (limit) params.append("limit", limit.toString());

  const url = params.toString() ? `/goals?${params}` : "/goals";
  const response = await apiClient.get<Goal[]>(url);
  return response.data;
}

export async function getGoal(goalId: string): Promise<Goal> {
  const response = await apiClient.get<Goal>(`/goals/${goalId}`);
  return response.data;
}

export async function updateGoal(goalId: string, data: UpdateGoalData): Promise<Goal> {
  const response = await apiClient.patch<Goal>(`/goals/${goalId}`, data);
  return response.data;
}

export async function deleteGoal(goalId: string): Promise<void> {
  await apiClient.delete(`/goals/${goalId}`);
}

export async function startGoal(goalId: string): Promise<Goal> {
  const response = await apiClient.post<Goal>(`/goals/${goalId}/start`);
  return response.data;
}

export async function pauseGoal(goalId: string): Promise<Goal> {
  const response = await apiClient.post<Goal>(`/goals/${goalId}/pause`);
  return response.data;
}

export async function completeGoal(goalId: string): Promise<Goal> {
  const response = await apiClient.post<Goal>(`/goals/${goalId}/complete`);
  return response.data;
}

export async function getGoalProgress(goalId: string): Promise<GoalWithProgress> {
  const response = await apiClient.get<GoalWithProgress>(`/goals/${goalId}/progress`);
  return response.data;
}
