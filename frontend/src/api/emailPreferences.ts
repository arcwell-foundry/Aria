import { apiClient } from "./client";

export interface EmailPreferences {
  weekly_summary: boolean;
  feature_announcements: boolean;
  security_alerts: boolean;
}

export interface UpdateEmailPreferencesRequest {
  weekly_summary?: boolean;
  feature_announcements?: boolean;
  security_alerts?: boolean;
}

export async function getEmailPreferences(): Promise<EmailPreferences> {
  const response = await apiClient.get<EmailPreferences>("/settings/email-preferences");
  return response.data;
}

export async function updateEmailPreferences(
  data: UpdateEmailPreferencesRequest
): Promise<EmailPreferences> {
  const response = await apiClient.patch<EmailPreferences>("/settings/email-preferences", data);
  return response.data;
}
