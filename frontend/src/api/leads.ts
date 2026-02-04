import { apiClient } from "./client";

// Enums matching backend
export type LifecycleStage = "lead" | "opportunity" | "account";
export type LeadStatus = "active" | "won" | "lost" | "dormant";
export type EventType =
  | "email_sent"
  | "email_received"
  | "meeting"
  | "call"
  | "note"
  | "signal";

// Response types
export interface Lead {
  id: string;
  user_id: string;
  company_name: string;
  company_id: string | null;
  lifecycle_stage: LifecycleStage;
  status: LeadStatus;
  health_score: number;
  crm_id: string | null;
  crm_provider: string | null;
  first_touch_at: string | null;
  last_activity_at: string | null;
  expected_close_date: string | null;
  expected_value: number | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface LeadEvent {
  id: string;
  lead_memory_id: string;
  event_type: EventType;
  direction: "inbound" | "outbound" | null;
  subject: string | null;
  content: string | null;
  participants: string[];
  occurred_at: string;
  source: string | null;
  created_at: string;
}

export interface NoteCreate {
  content: string;
  subject?: string;
  occurred_at?: string;
}

export interface LeadFilters {
  status?: LeadStatus;
  stage?: LifecycleStage;
  minHealth?: number;
  maxHealth?: number;
  search?: string;
  sortBy?: "health" | "last_activity" | "name" | "value";
  sortOrder?: "asc" | "desc";
  limit?: number;
}

export interface ExportResult {
  filename: string;
  content: string;
  content_type: string;
}

// API functions
export async function listLeads(filters?: LeadFilters): Promise<Lead[]> {
  const params = new URLSearchParams();
  if (filters?.status) params.append("status", filters.status);
  if (filters?.stage) params.append("stage", filters.stage);
  if (filters?.minHealth !== undefined)
    params.append("min_health", filters.minHealth.toString());
  if (filters?.maxHealth !== undefined)
    params.append("max_health", filters.maxHealth.toString());
  if (filters?.search) params.append("search", filters.search);
  if (filters?.sortBy) params.append("sort_by", filters.sortBy);
  if (filters?.sortOrder) params.append("sort_order", filters.sortOrder);
  if (filters?.limit) params.append("limit", filters.limit.toString());

  const url = params.toString() ? `/leads?${params}` : "/leads";
  const response = await apiClient.get<Lead[]>(url);
  return response.data;
}

export async function getLead(leadId: string): Promise<Lead> {
  const response = await apiClient.get<Lead>(`/leads/${leadId}`);
  return response.data;
}

export async function addNote(
  leadId: string,
  note: NoteCreate
): Promise<LeadEvent> {
  const response = await apiClient.post<LeadEvent>(`/leads/${leadId}/notes`, {
    event_type: "note",
    content: note.content,
    subject: note.subject,
    occurred_at: note.occurred_at || new Date().toISOString(),
  });
  return response.data;
}

export async function exportLeads(leadIds: string[]): Promise<ExportResult> {
  const response = await apiClient.post<ExportResult>("/leads/export", leadIds);
  return response.data;
}

// Helper to trigger CSV download
export function downloadCsv(result: ExportResult): void {
  const blob = new Blob([result.content], { type: result.content_type });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = result.filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
