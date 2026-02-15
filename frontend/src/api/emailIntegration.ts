import { apiClient } from "./client";

// Types for email integration API (US-907)

export type EmailProvider = "google" | "microsoft";

export interface PrivacyExclusion {
  type: "sender" | "domain" | "category";
  value: string;
  reason?: string;
}

export interface EmailIntegrationConfig {
  provider: EmailProvider;
  scopes: string[];
  privacy_exclusions: PrivacyExclusion[];
  ingestion_scope_days: number;
  attachment_ingestion: boolean;
}

export interface EmailConnectRequest {
  provider: EmailProvider;
}

export interface EmailConnectResponse {
  auth_url: string;
  connection_id: string;
  status: "pending" | "error";
  message?: string;
}

export interface ConnectionStatus {
  connected: boolean;
  provider: EmailProvider;
  connected_at?: string;
}

export interface EmailStatusResponse {
  google: ConnectionStatus;
  microsoft: ConnectionStatus;
}

export interface EmailPrivacyResponse {
  status: string;
  exclusions: number;
}

// API functions

export async function connectEmail(
  provider: EmailProvider
): Promise<EmailConnectResponse> {
  const response = await apiClient.post<EmailConnectResponse>(
    "/onboarding/email/connect",
    { provider }
  );
  return response.data;
}

export async function getEmailStatus(): Promise<EmailStatusResponse> {
  const response = await apiClient.get<EmailStatusResponse>(
    "/onboarding/email/status"
  );
  return response.data;
}

export async function saveEmailPrivacy(
  config: EmailIntegrationConfig
): Promise<EmailPrivacyResponse> {
  const response = await apiClient.post<EmailPrivacyResponse>(
    "/onboarding/email/privacy",
    config
  );
  return response.data;
}

export interface CommunicationPatterns {
  avg_response_time_hours: number;
  peak_send_hours: number[];
  peak_send_days: string[];
  emails_per_day_avg: number;
  follow_up_cadence_days: number;
  top_recipients: string[];
}

export interface BootstrapStatus {
  status: "not_started" | "processing" | "complete" | "error";
  emails_processed: number;
  contacts_discovered: number;
  active_threads: number;
  commitments_detected: number;
  writing_samples_extracted: number;
  communication_patterns: CommunicationPatterns | null;
  error_message?: string;
}

export interface SavedEmailPreferences {
  provider?: EmailProvider;
  privacy_exclusions?: PrivacyExclusion[];
  ingestion_scope_days?: number;
  attachment_ingestion?: boolean;
}

export async function disconnectEmail(): Promise<{ status: string }> {
  const response = await apiClient.post<{ status: string }>(
    "/onboarding/email/disconnect"
  );
  return response.data;
}

export async function getEmailPreferences(): Promise<SavedEmailPreferences> {
  const response = await apiClient.get<SavedEmailPreferences>(
    "/onboarding/email/preferences"
  );
  return response.data;
}

export async function getBootstrapStatus(): Promise<BootstrapStatus> {
  const response = await apiClient.get<BootstrapStatus>(
    "/onboarding/email/bootstrap/status"
  );
  return response.data;
}

export interface RecordConnectionRequest {
  integration_type: string; // "gmail" or "outlook"
  connection_id: string; // Composio connected_account_id
}

export interface RecordConnectionResponse {
  status: string;
  integration_type: string;
}

/**
 * Record a completed OAuth connection after Composio callback.
 * This explicitly saves the connection to user_integrations table.
 */
export async function recordEmailConnection(
  data: RecordConnectionRequest
): Promise<RecordConnectionResponse> {
  const response = await apiClient.post<RecordConnectionResponse>(
    "/onboarding/integrations/record-connection",
    data
  );
  return response.data;
}
