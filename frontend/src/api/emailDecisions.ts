import { apiClient } from "./client";

// Types matching backend ScanDecisionInfo / ScanDecisionsResponse

export type EmailCategory = "NEEDS_REPLY" | "FYI" | "SKIP";
export type EmailUrgency = "URGENT" | "NORMAL" | "LOW";

export interface PipelineContext {
  company_name: string | null;
  lead_name: string | null;
  lead_id: string | null;
  lifecycle_stage: string | null;
  health_score: number | null;
  relationship_type: string | null;
  source: string;
}

export interface ScanDecisionInfo {
  email_id: string;
  thread_id: string | null;
  sender_email: string;
  sender_name: string | null;
  subject: string | null;
  category: EmailCategory;
  urgency: EmailUrgency;
  needs_draft: boolean;
  reason: string;
  scanned_at: string;
  confidence: number | null;
  pipeline_context?: PipelineContext | null;
}

export interface ScanDecisionsResponse {
  decisions: ScanDecisionInfo[];
  total_count: number;
  filters_applied: Record<string, unknown>;
  scanned_after: string | null;
}

export interface GetEmailDecisionsParams {
  since_hours?: number;
  category?: EmailCategory;
  limit?: number;
}

export async function getEmailDecisions(
  params?: GetEmailDecisionsParams
): Promise<ScanDecisionsResponse> {
  const response = await apiClient.get<ScanDecisionsResponse>(
    "/email/decisions",
    { params }
  );
  return response.data;
}
