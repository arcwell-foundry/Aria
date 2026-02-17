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

// Conversion Score types
export interface ConversionScoreSummary {
  probability: number;
  confidence: number;
  calculated_at: string | null;
}

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
  conversion_score: ConversionScoreSummary | null;
  created_at: string;
  updated_at: string;
}

// Feature driver for score explanation
export interface FeatureDriver {
  name: string;
  value: number;
  contribution: number;
  description: string;
}

// Full score explanation response
export interface ScoreExplanation {
  lead_memory_id: string;
  conversion_probability: number;
  confidence: number;
  summary: string;
  key_drivers: FeatureDriver[];
  key_risks: FeatureDriver[];
  recommendation: string;
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

// Stakeholder types
export type StakeholderRole = "decision_maker" | "influencer" | "champion" | "blocker" | "user";
export type Sentiment = "positive" | "neutral" | "negative" | "unknown";

export interface Stakeholder {
  id: string;
  lead_memory_id: string;
  contact_email: string;
  contact_name: string | null;
  title: string | null;
  role: StakeholderRole | null;
  influence_level: number;
  sentiment: Sentiment;
  last_contacted_at: string | null;
  notes: string | null;
  created_at: string;
}

export interface StakeholderCreate {
  contact_email: string;
  contact_name?: string;
  title?: string;
  role?: StakeholderRole;
  influence_level?: number;
  sentiment?: Sentiment;
  notes?: string;
}

export interface StakeholderUpdate {
  contact_name?: string;
  title?: string;
  role?: StakeholderRole;
  influence_level?: number;
  sentiment?: Sentiment;
  notes?: string;
}

// Insight types
export type InsightType = "objection" | "buying_signal" | "commitment" | "risk" | "opportunity";

export interface Insight {
  id: string;
  lead_memory_id: string;
  insight_type: InsightType;
  content: string;
  confidence: number;
  source_event_id: string | null;
  detected_at: string;
  addressed_at: string | null;
}

// Stage transition
export interface StageTransition {
  new_stage: LifecycleStage;
  reason?: string;
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

// Get lead timeline (events)
export async function getLeadTimeline(leadId: string): Promise<LeadEvent[]> {
  const response = await apiClient.get<LeadEvent[]>(`/leads/${leadId}/timeline`);
  return response.data;
}

// Add event to lead
export async function addLeadEvent(
  leadId: string,
  event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">
): Promise<LeadEvent> {
  const response = await apiClient.post<LeadEvent>(`/leads/${leadId}/events`, event);
  return response.data;
}

// Get lead stakeholders
export async function getLeadStakeholders(leadId: string): Promise<Stakeholder[]> {
  const response = await apiClient.get<Stakeholder[]>(`/leads/${leadId}/stakeholders`);
  return response.data;
}

// Add stakeholder
export async function addStakeholder(
  leadId: string,
  stakeholder: StakeholderCreate
): Promise<Stakeholder> {
  const response = await apiClient.post<Stakeholder>(
    `/leads/${leadId}/stakeholders`,
    stakeholder
  );
  return response.data;
}

// Update stakeholder
export async function updateStakeholder(
  leadId: string,
  stakeholderId: string,
  updates: StakeholderUpdate
): Promise<Stakeholder> {
  const response = await apiClient.patch<Stakeholder>(
    `/leads/${leadId}/stakeholders/${stakeholderId}`,
    updates
  );
  return response.data;
}

// Get lead insights
export async function getLeadInsights(leadId: string): Promise<Insight[]> {
  const response = await apiClient.get<Insight[]>(`/leads/${leadId}/insights`);
  return response.data;
}

// Transition lead stage
export async function transitionLeadStage(
  leadId: string,
  transition: StageTransition
): Promise<Lead> {
  const response = await apiClient.post<Lead>(`/leads/${leadId}/transition`, transition);
  return response.data;
}

// Get conversion score with explanation
export async function getConversionScore(
  leadId: string,
  forceRefresh = false
): Promise<ScoreExplanation> {
  const params = new URLSearchParams();
  if (forceRefresh) params.append("force_refresh", "true");
  const url = params.toString()
    ? `/leads/${leadId}/conversion-score?${params}`
    : `/leads/${leadId}/conversion-score`;
  const response = await apiClient.get<ScoreExplanation>(url);
  return response.data;
}
