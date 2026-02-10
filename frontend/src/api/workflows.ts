import { apiClient } from "./client";

// Types matching backend Pydantic models

export type TriggerType = "time" | "event" | "condition";

export type ActionType =
  | "run_skill"
  | "send_notification"
  | "create_task"
  | "draft_email";

export type FailurePolicy = "skip" | "stop" | "retry";

export type WorkflowCategory = "productivity" | "follow_up" | "monitoring";

export type WorkflowStatus =
  | "pending"
  | "running"
  | "paused_for_approval"
  | "completed"
  | "failed";

export interface WorkflowTrigger {
  type: TriggerType;
  cron_expression?: string;
  timezone?: string;
  event_type?: string;
  event_filter?: Record<string, unknown>;
  condition_field?: string;
  condition_operator?: string;
  condition_value?: unknown;
}

export interface WorkflowAction {
  step_id: string;
  action_type: ActionType;
  config: Record<string, unknown>;
  requires_approval?: boolean;
  timeout_seconds?: number;
  on_failure?: FailurePolicy;
}

export interface WorkflowMetadata {
  category: WorkflowCategory;
  icon: string;
  color: string;
  enabled?: boolean;
  last_run_at?: string;
  run_count?: number;
}

export interface WorkflowResponse {
  id: string;
  name: string;
  description: string;
  trigger: WorkflowTrigger;
  actions: WorkflowAction[];
  metadata: WorkflowMetadata;
  is_shared: boolean;
  enabled: boolean;
  success_count: number;
  failure_count: number;
  version: number;
}

export interface WorkflowRunStatus {
  workflow_id: string;
  status: WorkflowStatus;
  current_step: string | null;
  steps_completed: number;
  steps_total: number;
  step_outputs: Record<string, unknown>;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface CreateWorkflowData {
  name: string;
  description: string;
  trigger: WorkflowTrigger;
  actions: WorkflowAction[];
  metadata: WorkflowMetadata;
  is_shared?: boolean;
  enabled?: boolean;
}

export interface UpdateWorkflowData {
  name?: string;
  description?: string;
  trigger?: WorkflowTrigger;
  actions?: WorkflowAction[];
  metadata?: WorkflowMetadata;
  is_shared?: boolean;
  enabled?: boolean;
}

// API functions

export async function listWorkflows(
  includeShared?: boolean
): Promise<WorkflowResponse[]> {
  const params = new URLSearchParams();
  if (includeShared !== undefined)
    params.append("include_shared", String(includeShared));

  const url = params.toString() ? `/workflows?${params}` : "/workflows";
  const response = await apiClient.get<WorkflowResponse[]>(url);
  return response.data;
}

export async function listPrebuiltWorkflows(): Promise<WorkflowResponse[]> {
  const response = await apiClient.get<WorkflowResponse[]>(
    "/workflows/prebuilt"
  );
  return response.data;
}

export async function getWorkflow(
  workflowId: string
): Promise<WorkflowResponse> {
  const response = await apiClient.get<WorkflowResponse>(
    `/workflows/${workflowId}`
  );
  return response.data;
}

export async function createWorkflow(
  data: CreateWorkflowData
): Promise<WorkflowResponse> {
  const response = await apiClient.post<WorkflowResponse>("/workflows", data);
  return response.data;
}

export async function updateWorkflow(
  workflowId: string,
  data: UpdateWorkflowData
): Promise<WorkflowResponse> {
  const response = await apiClient.put<WorkflowResponse>(
    `/workflows/${workflowId}`,
    data
  );
  return response.data;
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  await apiClient.delete(`/workflows/${workflowId}`);
}

export async function executeWorkflow(
  workflowId: string,
  triggerContext?: Record<string, unknown>
): Promise<WorkflowRunStatus> {
  const response = await apiClient.post<WorkflowRunStatus>(
    `/workflows/${workflowId}/execute`,
    triggerContext ? { trigger_context: triggerContext } : undefined
  );
  return response.data;
}
