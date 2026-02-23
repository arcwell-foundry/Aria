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

// US-936: Lifecycle types
export type GoalHealth = "on_track" | "at_risk" | "behind" | "blocked";
export type MilestoneStatus = "pending" | "in_progress" | "complete" | "skipped";

export interface Milestone {
  id: string;
  goal_id: string;
  title: string;
  description: string | null;
  due_date: string | null;
  completed_at: string | null;
  status: MilestoneStatus;
  sort_order: number;
  created_at: string;
}

export interface Retrospective {
  id: string;
  goal_id: string;
  summary: string;
  what_worked: string[];
  what_didnt: string[];
  time_analysis: Record<string, unknown>;
  agent_effectiveness: Record<string, unknown>;
  learnings: string[];
  created_at: string;
  updated_at: string;
}

export interface GoalDashboard extends Goal {
  goal_milestones?: Milestone[];
  milestone_total: number;
  milestone_complete: number;
}

export interface GoalDetail extends Goal {
  milestones: Milestone[];
  retrospective: Retrospective | null;
}

export interface ARIAGoalSuggestion {
  refined_title: string;
  refined_description: string;
  smart_score: number;
  sub_tasks: Array<{ title: string; description: string }>;
  agent_assignments: string[];
  suggested_timeline_days: number;
  reasoning: string;
}

export interface GoalTemplate {
  title: string;
  description: string;
  category: string;
  goal_type: GoalType;
  applicable_roles: string[];
}

export interface GoalProposalApproval {
  title: string;
  description?: string;
  goal_type: string;
  rationale: string;
  approach: string;
  agents: string[];
  timeline: string;
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

// US-936: Lifecycle API functions

export async function getDashboard(): Promise<GoalDashboard[]> {
  const response = await apiClient.get<GoalDashboard[]>("/goals/dashboard");
  return response.data;
}

export async function createWithARIA(
  title: string,
  description?: string
): Promise<ARIAGoalSuggestion> {
  const response = await apiClient.post<ARIAGoalSuggestion>(
    "/goals/create-with-aria",
    { title, description }
  );
  return response.data;
}

export async function getTemplates(role?: string): Promise<GoalTemplate[]> {
  const params = role ? `?role=${role}` : "";
  const response = await apiClient.get<GoalTemplate[]>(`/goals/templates${params}`);
  return response.data;
}

export async function getGoalDetail(goalId: string): Promise<GoalDetail> {
  const response = await apiClient.get<GoalDetail>(`/goals/${goalId}/detail`);
  return response.data;
}

export async function addMilestone(
  goalId: string,
  data: { title: string; description?: string; due_date?: string }
): Promise<Milestone> {
  const response = await apiClient.post<Milestone>(
    `/goals/${goalId}/milestone`,
    data
  );
  return response.data;
}

export async function generateRetrospective(
  goalId: string
): Promise<Retrospective> {
  const response = await apiClient.post<Retrospective>(
    `/goals/${goalId}/retrospective`
  );
  return response.data;
}

export async function approveGoalProposal(data: GoalProposalApproval): Promise<Goal> {
  const response = await apiClient.post<Goal>("/goals/approve-proposal", data);
  return response.data;
}

// --- Resource-aware planning ---

export interface PlanTaskResource {
  tool: string;
  connected: boolean;
}

export interface PlanTask {
  title: string;
  agent: string;
  dependencies: number[];
  tools_needed: string[];
  auth_required: string[];
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  estimated_minutes: number;
  auto_executable: boolean;
  resource_status: PlanTaskResource[];
}

export interface ExecutionPlanResponse {
  goal_id: string;
  title: string;
  status: string;
  tasks: PlanTask[];
  execution_mode: string;
  estimated_total_minutes: number;
  reasoning: string;
  readiness_score: number;
  missing_integrations: string[];
  connected_integrations: string[];
}

export interface PlanApprovalResponse {
  goal_id: string;
  status: string;
  started_at: string;
  message: string;
}

export async function getGoalPlan(goalId: string): Promise<ExecutionPlanResponse> {
  const response = await apiClient.get<ExecutionPlanResponse>(`/goals/${goalId}/plan`);
  return response.data;
}

export async function approveGoalPlan(goalId: string): Promise<PlanApprovalResponse> {
  const response = await apiClient.post<PlanApprovalResponse>(`/goals/${goalId}/approve`);
  return response.data;
}

export async function createGoalPlan(goalId: string): Promise<ExecutionPlanResponse> {
  const response = await apiClient.post<ExecutionPlanResponse>(`/goals/${goalId}/plan`);
  return response.data;
}
