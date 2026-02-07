import { apiClient } from "./client";

// Types
export interface DataExportResponse {
  export_date: string;
  user_id: string;
  user_profile: Record<string, unknown> | null;
  user_settings: Record<string, unknown> | null;
  onboarding_state: Array<Record<string, unknown>> | Record<string, unknown> | null;
  semantic_memory: Array<unknown> | null;
  prospective_memory: Array<unknown> | null;
  conversations: Array<unknown> | null;
  messages: Array<unknown> | null;
  documents: Array<unknown> | null;
  audit_log: Array<unknown> | null;
}

export interface DeleteDataRequest {
  confirmation: string;
}

export interface DeleteDataResponse {
  deleted: boolean;
  user_id: string;
  summary: Record<string, unknown>;
}

export interface DigitalTwinDeleteResponse {
  deleted: boolean;
  user_id: string;
  deleted_at: string;
}

export interface ConsentStatusResponse {
  email_analysis: boolean;
  document_learning: boolean;
  crm_processing: boolean;
  writing_style_learning: boolean;
}

export interface UpdateConsentRequest {
  category: "email_analysis" | "document_learning" | "crm_processing" | "writing_style_learning";
  granted: boolean;
}

export interface UpdateConsentResponse {
  category: string;
  granted: boolean;
  updated_at: string;
}

export interface RetentionPoliciesResponse {
  audit_query_logs: Record<string, unknown>;
  audit_write_logs: Record<string, unknown>;
  email_data: Record<string, unknown>;
  conversation_history: Record<string, unknown>;
  note: string | null;
}

// API functions
export async function getDataExport(): Promise<DataExportResponse> {
  const response = await apiClient.get<DataExportResponse>("/compliance/data/export");
  return response.data;
}

export async function deleteUserData(data: DeleteDataRequest): Promise<DeleteDataResponse> {
  const response = await apiClient.post<DeleteDataResponse>("/compliance/data/delete", data);
  return response.data;
}

export async function deleteDigitalTwin(): Promise<DigitalTwinDeleteResponse> {
  const response = await apiClient.delete<DigitalTwinDeleteResponse>("/compliance/data/digital-twin");
  return response.data;
}

export async function getConsentStatus(): Promise<ConsentStatusResponse> {
  const response = await apiClient.get<ConsentStatusResponse>("/compliance/consent");
  return response.data;
}

export async function updateConsent(data: UpdateConsentRequest): Promise<UpdateConsentResponse> {
  const response = await apiClient.patch<UpdateConsentResponse>("/compliance/consent", data);
  return response.data;
}

export async function getRetentionPolicies(): Promise<RetentionPoliciesResponse> {
  const response = await apiClient.get<RetentionPoliciesResponse>("/compliance/retention");
  return response.data;
}
