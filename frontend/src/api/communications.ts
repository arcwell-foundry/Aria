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
