import { apiClient } from "./client";

// Types for company discovery API responses

export interface EmailValidationRequest {
  email: string;
}

export interface EmailValidationResponse {
  valid: boolean;
  reason: string | null;
}

export interface CompanyDiscoveryRequest {
  company_name: string;
  website: string;
  email: string;
}

export interface CompanyInfo {
  id: string;
  name: string;
  domain: string | null;
  is_existing: boolean;
}

export interface GateResult {
  is_life_sciences: boolean;
  confidence: number;
}

export interface CompanyDiscoverySuccessResponse {
  success: true;
  company: CompanyInfo;
  gate_result: GateResult;
  enrichment_status: string;
}

export interface CompanyDiscoveryErrorResponse {
  success: false;
  error: string;
  type: "email_validation" | "vertical_mismatch";
  message?: string;
  reasoning?: string;
}

export type CompanyDiscoveryResponse =
  | CompanyDiscoverySuccessResponse
  | CompanyDiscoveryErrorResponse;

// API functions

export async function validateEmail(
  email: string
): Promise<EmailValidationResponse> {
  const response = await apiClient.post<EmailValidationResponse>(
    "/onboarding/company-discovery/validate-email",
    { email }
  );
  return response.data;
}

export async function submitCompanyDiscovery(
  data: CompanyDiscoveryRequest
): Promise<CompanyDiscoveryResponse> {
  const response = await apiClient.post<CompanyDiscoveryResponse>(
    "/onboarding/company-discovery/submit",
    data
  );
  return response.data;
}
