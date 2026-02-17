import { apiClient } from "./client";

// Enums matching backend
export type DefaultTone = "formal" | "friendly" | "urgent";
export type MeetingBriefLeadHours = 2 | 6 | 12 | 24;
export type BriefingMode = "video" | "text";
export type BriefingDuration = 2 | 5 | 10;

// Response type
export interface UserPreferences {
  id: string;
  user_id: string;
  briefing_time: string;
  briefing_mode: BriefingMode;
  briefing_duration: BriefingDuration;
  meeting_brief_lead_hours: MeetingBriefLeadHours;
  notification_email: boolean;
  notification_in_app: boolean;
  default_tone: DefaultTone;
  tracked_competitors: string[];
  timezone: string;
  created_at: string;
  updated_at: string;
}

// Request type for updates
export interface UpdatePreferencesRequest {
  briefing_time?: string;
  briefing_mode?: BriefingMode;
  briefing_duration?: BriefingDuration;
  meeting_brief_lead_hours?: MeetingBriefLeadHours;
  notification_email?: boolean;
  notification_in_app?: boolean;
  default_tone?: DefaultTone;
  tracked_competitors?: string[];
  timezone?: string;
}

// API functions
export async function getPreferences(): Promise<UserPreferences> {
  const response = await apiClient.get<UserPreferences>("/settings/preferences");
  return response.data;
}

export async function updatePreferences(
  data: UpdatePreferencesRequest
): Promise<UserPreferences> {
  const response = await apiClient.put<UserPreferences>("/settings/preferences", data);
  return response.data;
}

// Convenience export
export const preferencesApi = {
  getPreferences,
  updatePreferences,
};
