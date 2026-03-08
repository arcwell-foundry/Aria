import { apiClient } from "./client";

// Enums matching backend
export type EmailDraftPurpose =
  | "intro"
  | "follow_up"
  | "proposal"
  | "thank_you"
  | "check_in"
  | "reply"
  | "other"
  | "competitive_displacement"
  | "conference_outreach"
  | "clinical_trial_outreach";

export type EmailDraftTone = "formal" | "friendly" | "urgent";

export type EmailDraftStatus =
  | "draft"
  | "sent"
  | "failed"
  | "pending_review"
  | "approved"
  | "dismissed"
  | "saved_to_client";

// Response types
export type ConfidenceTier = "HIGH" | "MEDIUM" | "LOW" | "MINIMAL";

export interface OriginalEmail {
  from: string;
  sender_name?: string;
  sender_email: string;
  date: string;
  subject: string;
  snippet: string;
}

export interface EmailDraft {
  id: string;
  user_id: string;
  recipient_email: string;
  recipient_name?: string;
  subject: string;
  body: string;
  purpose: EmailDraftPurpose;
  tone: EmailDraftTone;
  context?: {
    user_context?: string;
    lead_context?: unknown;
  };
  lead_memory_id?: string;
  style_match_score?: number;
  confidence_tier?: ConfidenceTier;
  status: EmailDraftStatus;
  sent_at?: string;
  error_message?: string;
  client_draft_id?: string;
  client_provider?: "gmail" | "outlook";
  saved_to_client_at?: string;
  created_at: string;
  updated_at: string;
  // Intelligence-generated draft fields
  draft_type?: string;
  aria_notes?: string;
  competitive_positioning?: Record<string, unknown>;
  insight_id?: string;
  aria_reasoning?: string;
  // Original email for reply drafts
  original_email?: OriginalEmail;
}

export interface EmailDraftListItem {
  id: string;
  recipient_email: string;
  recipient_name?: string;
  subject: string;
  body?: string;
  purpose: EmailDraftPurpose;
  tone: EmailDraftTone;
  status: EmailDraftStatus;
  style_match_score?: number;
  confidence_tier?: ConfidenceTier;
  created_at: string;
  // Intelligence-generated draft fields
  draft_type?: string;
  aria_notes?: string;
}

// Request types
export interface CreateEmailDraftRequest {
  recipient_email: string;
  recipient_name?: string;
  subject_hint?: string;
  purpose: EmailDraftPurpose;
  context?: string;
  tone?: EmailDraftTone;
  lead_memory_id?: string;
}

export interface UpdateEmailDraftRequest {
  recipient_email?: string;
  recipient_name?: string;
  subject?: string;
  body?: string;
  tone?: EmailDraftTone;
}

export interface RegenerateDraftRequest {
  tone?: EmailDraftTone;
  additional_context?: string;
}

export interface SendDraftResponse {
  id: string;
  status: EmailDraftStatus;
  sent_at?: string;
  error_message?: string;
}

// API functions
export async function listDrafts(
  status?: EmailDraftStatus,
  limit = 50
): Promise<EmailDraftListItem[]> {
  const params = new URLSearchParams();
  if (status) {
    params.append("status", status);
  }
  params.append("limit", limit.toString());
  const queryString = params.toString();
  const response = await apiClient.get<EmailDraftListItem[]>(
    `/drafts${queryString ? `?${queryString}` : ""}`
  );
  return response.data;
}

export async function getDraft(draftId: string): Promise<EmailDraft> {
  const response = await apiClient.get<EmailDraft>(`/drafts/${draftId}`);
  return response.data;
}

export async function createDraft(
  data: CreateEmailDraftRequest
): Promise<EmailDraft> {
  const response = await apiClient.post<EmailDraft>("/drafts/email", data);
  return response.data;
}

export async function updateDraft(
  draftId: string,
  data: UpdateEmailDraftRequest
): Promise<EmailDraft> {
  const response = await apiClient.put<EmailDraft>(`/drafts/${draftId}`, data);
  return response.data;
}

export async function deleteDraft(draftId: string): Promise<void> {
  await apiClient.delete(`/drafts/${draftId}`);
}

export async function regenerateDraft(
  draftId: string,
  data?: RegenerateDraftRequest
): Promise<EmailDraft> {
  const response = await apiClient.post<EmailDraft>(
    `/drafts/${draftId}/regenerate`,
    data ?? {}
  );
  return response.data;
}

export async function sendDraft(draftId: string): Promise<SendDraftResponse> {
  const response = await apiClient.post<SendDraftResponse>(
    `/drafts/${draftId}/send`
  );
  return response.data;
}

export interface SaveToClientResponse {
  success: boolean;
  saved_at: string;
  client_draft_id?: string;
  provider?: "gmail" | "outlook";
  already_saved: boolean;
}

export async function saveDraftToClient(
  draftId: string
): Promise<SaveToClientResponse> {
  const response = await apiClient.post<SaveToClientResponse>(
    `/drafts/${draftId}/save-to-client`
  );
  return response.data;
}

export interface ApproveDraftResponse {
  success: boolean;
  saved_at: string;
}

export async function approveDraft(
  draftId: string
): Promise<ApproveDraftResponse> {
  const response = await apiClient.post<ApproveDraftResponse>(
    `/drafts/${draftId}/approve`
  );
  return response.data;
}

export interface DismissDraftResponse {
  success: boolean;
}

export async function dismissDraft(
  draftId: string
): Promise<DismissDraftResponse> {
  const response = await apiClient.post<DismissDraftResponse>(
    `/drafts/${draftId}/dismiss`
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Draft Intelligence Context - Relevance-based signal matching
// ---------------------------------------------------------------------------

export interface MarketSignalItem {
  id: string;
  signal_type: string;
  company_name: string;
  content: string;
  source: string | null;
  created_at: string;
  relevance_source: "domain" | "subject" | "fallback";
}

export interface RelationshipContext {
  recipient_email: string;
  last_interaction_date: string | null;
  interaction_count: number;
  relationship_summary: string;
}

export interface DraftIntelligenceContextResponse {
  has_signals: boolean;
  signals: MarketSignalItem[];
  relationship_context: RelationshipContext | null;
  match_type: "domain" | "subject" | "relationship" | "empty";
}

export async function getDraftIntelligenceContext(
  draftId: string
): Promise<DraftIntelligenceContextResponse> {
  const response = await apiClient.get<DraftIntelligenceContextResponse>(
    `/drafts/${draftId}/intelligence-context`
  );
  return response.data;
}
