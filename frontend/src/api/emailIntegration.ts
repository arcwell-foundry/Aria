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
