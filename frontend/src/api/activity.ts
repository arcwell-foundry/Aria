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
  activities: ActivityItem[];
  count: number;
}

export interface ActivityFilters {
  agent?: string;
  activity_type?: string;
  date_start?: string;
  date_end?: string;
  search?: string;
  limit?: number;
  offset?: number;
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
  if (filters?.agent) params.append("agent", filters.agent);
  if (filters?.activity_type)
    params.append("activity_type", filters.activity_type);
  if (filters?.date_start) params.append("date_start", filters.date_start);
  if (filters?.date_end) params.append("date_end", filters.date_end);
  if (filters?.search) params.append("search", filters.search);
  if (filters?.limit) params.append("limit", filters.limit.toString());
  if (filters?.offset) params.append("offset", filters.offset.toString());

  const url = params.toString() ? `/activity?${params}` : "/activity";
  const response = await apiClient.get<ActivityFeedResponse>(url);
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
