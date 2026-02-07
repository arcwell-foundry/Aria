import { apiClient } from "./client";

// Enums matching backend
export type ARIARole = "sales_ops" | "bd_sales" | "marketing" | "executive_support" | "custom";
export type NotificationFrequency = "minimal" | "balanced" | "aggressive";
export type ResponseDepth = "brief" | "moderate" | "detailed";

export interface PersonalityTraits {
  proactiveness: number;
  verbosity: number;
  formality: number;
  assertiveness: number;
}

export interface DomainFocus {
  therapeutic_areas: string[];
  modalities: string[];
  geographies: string[];
}

export interface CommunicationPrefs {
  preferred_channels: string[];
  notification_frequency: NotificationFrequency;
  response_depth: ResponseDepth;
  briefing_time: string;
}

export interface ARIAConfig {
  role: ARIARole;
  custom_role_description: string | null;
  personality: PersonalityTraits;
  domain_focus: DomainFocus;
  competitor_watchlist: string[];
  communication: CommunicationPrefs;
  personality_defaults: PersonalityTraits;
  updated_at: string | null;
}

export interface ARIAConfigUpdateRequest {
  role: ARIARole;
  custom_role_description?: string | null;
  personality: PersonalityTraits;
  domain_focus: DomainFocus;
  competitor_watchlist: string[];
  communication: CommunicationPrefs;
}

export interface PreviewResponse {
  preview_message: string;
  role_label: string;
}

export async function getAriaConfig(): Promise<ARIAConfig> {
  const response = await apiClient.get<ARIAConfig>("/aria-config");
  return response.data;
}

export async function updateAriaConfig(
  data: ARIAConfigUpdateRequest
): Promise<ARIAConfig> {
  const response = await apiClient.put<ARIAConfig>("/aria-config", data);
  return response.data;
}

export async function resetPersonality(): Promise<ARIAConfig> {
  const response = await apiClient.post<ARIAConfig>("/aria-config/reset-personality");
  return response.data;
}

export async function generatePreview(
  data: ARIAConfigUpdateRequest
): Promise<PreviewResponse> {
  const response = await apiClient.post<PreviewResponse>("/aria-config/preview", data);
  return response.data;
}
