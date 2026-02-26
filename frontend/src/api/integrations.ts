import { apiClient } from "./client";

// Types matching backend models
export type IntegrationType =
  | "google_calendar"
  | "gmail"
  | "outlook"
  | "salesforce"
  | "hubspot";

export type IntegrationStatus = "active" | "disconnected" | "error" | "pending";
export type SyncStatus = "success" | "pending" | "failed";

export interface Integration {
  id: string;
  user_id: string;
  integration_type: IntegrationType;
  composio_connection_id: string;
  composio_account_id: string | null;
  display_name: string | null;
  status: IntegrationStatus;
  last_sync_at: string | null;
  sync_status: SyncStatus;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AvailableIntegration {
  integration_type: IntegrationType;
  display_name: string;
  description: string;
  icon: string;
  is_connected: boolean;
  status: string | null;
}

export interface AuthUrlResponse {
  authorization_url: string;
  integration_type: string;
  display_name: string;
}

export interface ConnectIntegrationRequest {
  code: string;
  state?: string;
  redirect_uri?: string;
}

export interface ConnectIntegrationResponse {
  integration: Integration;
  message: string;
}

export interface DisconnectIntegrationResponse {
  message: string;
}

// API functions
export async function listIntegrations(): Promise<Integration[]> {
  const response = await apiClient.get<Integration[]>("/integrations");
  return response.data;
}

export async function listAvailableIntegrations(): Promise<AvailableIntegration[]> {
  const response = await apiClient.get<AvailableIntegration[]>("/integrations/available");
  return response.data;
}

export async function getAuthUrl(
  integrationType: IntegrationType,
  redirectUri: string
): Promise<AuthUrlResponse> {
  const response = await apiClient.post<AuthUrlResponse>(
    `/integrations/${integrationType}/auth-url`,
    { redirect_uri: redirectUri }
  );
  return response.data;
}

export async function connectIntegration(
  integrationType: IntegrationType,
  data: ConnectIntegrationRequest
): Promise<ConnectIntegrationResponse> {
  const response = await apiClient.post<ConnectIntegrationResponse>(
    `/integrations/${integrationType}/connect`,
    data
  );
  return response.data;
}

export async function disconnectIntegration(
  integrationType: IntegrationType
): Promise<DisconnectIntegrationResponse> {
  const response = await apiClient.post<DisconnectIntegrationResponse>(
    `/integrations/${integrationType}/disconnect`
  );
  return response.data;
}

// Convenience object for imports
export const integrationsApi = {
  listIntegrations,
  listAvailableIntegrations,
  getAuthUrl,
  connectIntegration,
  disconnectIntegration,
};
