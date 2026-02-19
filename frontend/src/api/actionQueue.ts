import { apiClient } from "./client";

// Enums matching backend
export type ActionAgent = "scout" | "analyst" | "hunter" | "operator" | "scribe" | "strategist";
export type ActionType = "email_draft" | "crm_update" | "research" | "meeting_prep" | "lead_gen";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type ActionStatus =
  | "pending"
  | "approved"
  | "auto_approved"
  | "executing"
  | "completed"
  | "rejected"
  | "failed"
  | "undo_pending";

// Response types
export interface Action {
  id: string;
  user_id: string;
  agent: ActionAgent;
  action_type: ActionType;
  title: string;
  description: string | null;
  risk_level: RiskLevel;
  status: ActionStatus;
  payload: Record<string, unknown>;
  reasoning: string | null;
  result: Record<string, unknown>;
  approved_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

// Request types
export interface SubmitActionData {
  agent: ActionAgent;
  action_type: ActionType;
  title: string;
  description?: string;
  risk_level: RiskLevel;
  payload?: Record<string, unknown>;
  reasoning?: string;
}

export interface BatchApproveResponse {
  approved: Action[];
  count: number;
}

// API functions
export async function listActions(status?: ActionStatus, limit?: number): Promise<Action[]> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (limit) params.append("limit", limit.toString());

  const url = params.toString() ? `/actions?${params}` : "/actions";
  const response = await apiClient.get<Action[]>(url);
  return response.data;
}

export async function getAction(actionId: string): Promise<Action> {
  const response = await apiClient.get<Action>(`/actions/${actionId}`);
  return response.data;
}

export async function submitAction(data: SubmitActionData): Promise<Action> {
  const response = await apiClient.post<Action>("/actions", data);
  return response.data;
}

export async function approveAction(actionId: string): Promise<Action> {
  const response = await apiClient.post<Action>(`/actions/${actionId}/approve`);
  return response.data;
}

export async function rejectAction(actionId: string, reason?: string): Promise<Action> {
  const response = await apiClient.post<Action>(`/actions/${actionId}/reject`, {
    reason: reason ?? null,
  });
  return response.data;
}

export async function batchApproveActions(actionIds: string[]): Promise<BatchApproveResponse> {
  const response = await apiClient.post<BatchApproveResponse>("/actions/batch-approve", {
    action_ids: actionIds,
  });
  return response.data;
}

export async function getPendingCount(): Promise<number> {
  const response = await apiClient.get<{ count: number }>("/actions/pending-count");
  return response.data.count;
}

export async function executeAction(actionId: string): Promise<Action> {
  const response = await apiClient.post<Action>(`/actions/${actionId}/execute`);
  return response.data;
}

export interface UndoResponse {
  success: boolean;
  action_id: string;
  reversal?: Record<string, unknown>;
  reason?: string;
}

export async function undoAction(actionId: string): Promise<UndoResponse> {
  const response = await apiClient.post<UndoResponse>(`/actions/${actionId}/undo`);
  return response.data;
}
