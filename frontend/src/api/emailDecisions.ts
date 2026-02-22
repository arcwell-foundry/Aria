import { apiClient } from "./client";

// Types matching backend ScanDecisionInfo / ScanDecisionsResponse

export type EmailCategory = "NEEDS_REPLY" | "FYI" | "SKIP";
export type EmailUrgency = "URGENT" | "NORMAL" | "LOW";

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
