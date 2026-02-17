import { apiClient } from "./client";

// --- Types ---

export interface ActivityItem {
  id: string;
  user_id: string;
  agent: string | null;
  activity_type: string;
  title: string;
  description: string;
  reasoning: string;
  confidence: number;
  related_entity_type: string | null;
  related_entity_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ActivityFeedResponse {
  items: ActivityItem[];
  total: number;
  page: number;
}

export interface ActivityFilters {
  type?: string;
  agent?: string;
  entity_type?: string;
  entity_id?: string;
  since?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface ActivityPollResponse {
  items: ActivityItem[];
  count: number;
}

export interface ActivityStatsResponse {
  total: number;
  by_type: Record<string, number>;
  by_agent: Record<string, number>;
  period: string;
  since: string;
}

export interface AgentStatusItem {
  status: string;
  last_activity: string | null;
  last_activity_type: string | null;
  last_time: string | null;
}

export interface AgentStatusResponse {
  agents: Record<string, AgentStatusItem>;
}

// --- API functions ---

export async function getActivityFeed(
  filters?: ActivityFilters
): Promise<ActivityFeedResponse> {
  const params = new URLSearchParams();
  if (filters?.type) params.append("type", filters.type);
  if (filters?.agent) params.append("agent", filters.agent);
  if (filters?.entity_type) params.append("entity_type", filters.entity_type);
  if (filters?.entity_id) params.append("entity_id", filters.entity_id);
  if (filters?.since) params.append("since", filters.since);
  if (filters?.page) params.append("page", filters.page.toString());
  if (filters?.page_size)
    params.append("page_size", filters.page_size.toString());

  const url = params.toString() ? `/activity?${params}` : "/activity";
  const response = await apiClient.get<ActivityFeedResponse>(url);
  return response.data;
}

export async function pollActivity(
  since: string
): Promise<ActivityPollResponse> {
  const response = await apiClient.get<ActivityPollResponse>(
    `/activity/poll?since=${encodeURIComponent(since)}`
  );
  return response.data;
}

export async function getActivityStats(
  period = "7d"
): Promise<ActivityStatsResponse> {
  const response = await apiClient.get<ActivityStatsResponse>(
    `/activity/stats?period=${encodeURIComponent(period)}`
  );
  return response.data;
}

export async function getAgentStatus(): Promise<AgentStatusResponse> {
  const response = await apiClient.get<AgentStatusResponse>(
    "/activity/agents"
  );
  return response.data;
}

export async function getActivityDetail(
  activityId: string
): Promise<ActivityItem> {
  const response = await apiClient.get<ActivityItem>(
    `/activity/${activityId}`
  );
  return response.data;
}
