import { apiClient } from "./client";

// --- Types ---

export interface ProfileUser {
  id: string;
  full_name: string | null;
  title: string | null;
  department: string | null;
  linkedin_url: string | null;
  phone: string | null;
  avatar_url: string | null;
  company_id: string | null;
  role: string;
  communication_preferences: Record<string, unknown>;
  privacy_exclusions: string[];
  default_tone: string;
  tracked_competitors: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface ProfileCompany {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  sub_vertical: string | null;
  description: string | null;
  key_products: string[] | null;
  classification: string | null;
  last_enriched_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProfileIntegration {
  id: string;
  provider: string;
  category: string;
  status: string;
  last_sync_at: string | null;
  created_at: string | null;
}

export interface FullProfile {
  user: ProfileUser;
  company: ProfileCompany | null;
  integrations: ProfileIntegration[];
}

export interface ProfileDocument {
  id: string;
  name: string;
  file_type: string;
  file_size: number;
  quality_score: number | null;
  uploaded_by: string;
  created_at: string;
}

export interface ProfileDocuments {
  company_documents: ProfileDocument[];
  user_documents: ProfileDocument[];
}

export interface UpdateUserDetailsRequest {
  full_name?: string;
  title?: string;
  department?: string;
  linkedin_url?: string;
  avatar_url?: string;
  communication_preferences?: Record<string, unknown>;
  privacy_exclusions?: string[];
  default_tone?: "formal" | "friendly" | "urgent";
  tracked_competitors?: string[];
}

export interface UpdateCompanyDetailsRequest {
  name?: string;
  website?: string;
  industry?: string;
  sub_vertical?: string;
  description?: string;
  key_products?: string[];
}

export interface UpdatePreferencesRequest {
  communication_preferences?: Record<string, unknown>;
  default_tone?: "formal" | "friendly" | "urgent";
  tracked_competitors?: string[];
  privacy_exclusions?: string[];
}

// --- API Functions ---

export async function getFullProfile(): Promise<FullProfile> {
  const response = await apiClient.get<FullProfile>("/profile");
  return response.data;
}

export async function updateUserDetails(
  data: UpdateUserDetailsRequest,
): Promise<Record<string, unknown>> {
  const response = await apiClient.put<Record<string, unknown>>("/profile/user", data);
  return response.data;
}

export async function updateCompanyDetails(
  data: UpdateCompanyDetailsRequest,
): Promise<Record<string, unknown>> {
  const response = await apiClient.put<Record<string, unknown>>("/profile/company", data);
  return response.data;
}

export async function getProfileDocuments(): Promise<ProfileDocuments> {
  const response = await apiClient.get<ProfileDocuments>("/profile/documents");
  return response.data;
}

export async function updatePreferences(
  data: UpdatePreferencesRequest,
): Promise<Record<string, unknown>> {
  const response = await apiClient.put<Record<string, unknown>>("/profile/preferences", data);
  return response.data;
}
