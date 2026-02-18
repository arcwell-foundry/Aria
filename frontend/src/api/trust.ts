import { apiClient } from "./client";

export type OverrideMode =
  | "always_approve"
  | "plan_approval"
  | "notify_only"
  | "full_auto"
  | "aria_decides";

export interface TrustProfile {
  action_category: string;
  trust_score: number;
  successful_actions: number;
  failed_actions: number;
  override_count: number;
  approval_level: string;
  approval_level_label: string;
  can_request_upgrade: boolean;
  override_mode: OverrideMode | null;
}

export interface TrustHistoryPoint {
  recorded_at: string;
  trust_score: number;
  change_type: string;
  action_category: string;
}

export async function getTrustProfiles(): Promise<TrustProfile[]> {
  const response = await apiClient.get<TrustProfile[]>("/trust/me");
  return response.data;
}

export async function getTrustHistory(
  category?: string,
  days: number = 30
): Promise<TrustHistoryPoint[]> {
  const params: Record<string, string | number> = { days };
  if (category) params.category = category;
  const response = await apiClient.get<TrustHistoryPoint[]>("/trust/me/history", { params });
  return response.data;
}

export async function setTrustOverride(
  category: string,
  mode: OverrideMode
): Promise<TrustProfile> {
  const response = await apiClient.put<TrustProfile>(
    `/trust/me/${encodeURIComponent(category)}/override`,
    { mode }
  );
  return response.data;
}
