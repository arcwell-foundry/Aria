import { apiClient } from "./client";

export type DraftTiming = "overnight" | "realtime";

export interface EmailIntelligenceSettings {
  auto_draft_enabled: boolean;
  draft_timing: DraftTiming;
  vip_contacts: string[];
  excluded_senders: string[];
  learning_mode_active: boolean;
  learning_mode_day: number | null;
  email_provider: string | null;
  email_connected: boolean;
}

export interface UpdateEmailIntelligenceSettingsRequest {
  auto_draft_enabled?: boolean;
  draft_timing?: DraftTiming;
  vip_contacts?: string[];
  excluded_senders?: string[];
}

export async function getEmailIntelligenceSettings(): Promise<EmailIntelligenceSettings> {
  const response = await apiClient.get<EmailIntelligenceSettings>(
    "/settings/email-intelligence"
  );
  return response.data;
}

export async function updateEmailIntelligenceSettings(
  data: UpdateEmailIntelligenceSettingsRequest
): Promise<EmailIntelligenceSettings> {
  const response = await apiClient.patch<EmailIntelligenceSettings>(
    "/settings/email-intelligence",
    data
  );
  return response.data;
}
