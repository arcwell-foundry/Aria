/**
 * API client for the Communications page.
 *
 * Provides functions for:
 * - Contact history: Unified timeline of all communications with a specific contact
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * A single entry in the contact history timeline.
 */
export interface ContactHistoryEntry {
  type: "received" | "draft" | "sent" | "dismissed";
  timestamp: string;
  subject: string | null;
  snippet: string | null;
  status: string | null;
  email_id: string | null;
  draft_id: string | null;
  category: "NEEDS_REPLY" | "FYI" | "SKIP" | null;
  urgency: "URGENT" | "NORMAL" | "LOW" | null;
  confidence: number | null;
}

/**
 * Response from the contact history endpoint.
 */
export interface ContactHistoryResponse {
  contact_email: string;
  contact_name: string | null;
  entries: ContactHistoryEntry[];
  total_count: number;
  received_count: number;
  sent_count: number;
  draft_count: number;
}

/**
 * Single day's email volume data for the 7-day trend.
 */
export interface VolumeDay {
  date: string;
  received: number;
  drafted: number;
  sent: number;
}

/**
 * Response from the communications analytics endpoint.
 */
export interface CommunicationsAnalyticsResponse {
  has_data: boolean;
  avg_response_hours: number | null;
  fastest_response_hours: number | null;
  slowest_response_hours: number | null;
  draft_coverage_pct: number | null;
  draft_coverage_count: number;
  needs_reply_count: number;
  volume_7d: VolumeDay[];
  classification: {
    NEEDS_REPLY: number;
    FYI: number;
    SKIP: number;
  };
  classification_pct: {
    NEEDS_REPLY: number;
    FYI: number;
    SKIP: number;
  };
  response_by_contact_type: Record<string, number>;
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

/**
 * Fetch the unified communication history with a specific contact.
 *
 * Merges data from both email_scan_log (incoming emails) and email_drafts
 * (outgoing drafts/sent emails) to provide a complete timeline.
 *
 * @param email - The contact's email address
 * @param limit - Maximum number of entries to return (default: 50)
 * @returns Contact history with merged timeline sorted by timestamp (newest first)
 */
export async function fetchContactHistory(
  email: string,
  limit: number = 50
): Promise<ContactHistoryResponse> {
  const params = new URLSearchParams({
    email,
    limit: limit.toString(),
  });

  const response = await apiClient.get<ContactHistoryResponse>(
    `/communications/contact-history?${params.toString()}`
  );

  return response.data;
}

/**
 * Fetch communication analytics metrics for the authenticated user.
 *
 * Provides comprehensive email analytics including:
 * - Response time analytics (avg, fastest, slowest in hours)
 * - Draft coverage rate (% NEEDS_REPLY emails with drafts)
 * - Email volume trends (7-day: received, drafted, sent counts)
 * - Classification distribution (NEEDS_REPLY/FYI/SKIP counts and percentages)
 * - Response time by contact type
 *
 * @param daysBack - Number of days to look back (default: 7, max: 90)
 * @returns Analytics metrics or has_data=false if no data available
 */
export async function fetchCommunicationsAnalytics(
  daysBack: number = 7
): Promise<CommunicationsAnalyticsResponse> {
  const params = new URLSearchParams({
    days_back: daysBack.toString(),
  });

  const response = await apiClient.get<CommunicationsAnalyticsResponse>(
    `/communications/analytics?${params.toString()}`
  );

  return response.data;
}
