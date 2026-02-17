import { apiClient } from "./client";

export type AutonomyTier = "guided" | "assisted" | "autonomous";

export interface AutonomyStats {
  total_actions: number;
  approval_rate: number;
  auto_executed: number;
  rejected: number;
}

export interface RecentAction {
  id: string;
  title: string;
  action_type: string;
  risk_level: string;
  status: string;
  agent: string;
  created_at: string;
}

export interface AutonomyStatus {
  current_level: number;
  current_tier: AutonomyTier;
  recommended_level: number;
  recommended_tier: AutonomyTier;
  can_select_tiers: AutonomyTier[];
  stats: AutonomyStats;
  recent_actions: RecentAction[];
}

export async function getAutonomyStatus(): Promise<AutonomyStatus> {
  const response = await apiClient.get<AutonomyStatus>("/autonomy/status");
  return response.data;
}

export async function setAutonomyTier(tier: AutonomyTier): Promise<AutonomyStatus> {
  const response = await apiClient.post<AutonomyStatus>("/autonomy/level", { tier });
  return response.data;
}
