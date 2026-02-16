import { apiClient } from "./client";

// Intelligence insight types from backend
export interface IntelligenceInsight {
  id: string;
  user_id: string;
  insight_type: string;
  trigger_event: string;
  content: string;
  classification: "opportunity" | "threat" | "neutral";
  impact_score: number;
  confidence: number;
  urgency: number;
  combined_score: number;
  causal_chain: Record<string, unknown>[];
  affected_goals: string[];
  recommended_actions: string[];
  status: string;
  time_horizon: "immediate" | "short_term" | "medium_term" | "long_term" | null;
  created_at: string;
  updated_at: string;
}

export interface InsightsListResponse {
  insights: IntelligenceInsight[];
  total: number;
}

export interface ProactiveInsight {
  id: string;
  insight_type: string;
  content: string;
  priority: number;
  context: Record<string, unknown>;
  created_at: string;
}

export interface ProactiveInsightsResponse {
  insights: ProactiveInsight[];
}

export interface InsightFilters {
  limit?: number;
  status?: string;
  classification?: string;
}

// API functions
export async function listInsights(filters?: InsightFilters): Promise<IntelligenceInsight[]> {
  const params = new URLSearchParams();
  if (filters?.limit) params.append("limit", filters.limit.toString());
  if (filters?.status) params.append("status", filters.status);
  if (filters?.classification) params.append("classification", filters.classification);

  const url = params.toString() ? `/intelligence/insights?${params}` : "/intelligence/insights";
  const response = await apiClient.get<IntelligenceInsight[] | InsightsListResponse>(url);
  // Handle both array and object response shapes
  if (Array.isArray(response.data)) {
    return response.data;
  }
  return (response.data as InsightsListResponse).insights ?? [];
}

export async function getInsight(insightId: string): Promise<IntelligenceInsight> {
  const response = await apiClient.get<IntelligenceInsight>(`/intelligence/insights/${insightId}`);
  return response.data;
}

export async function updateInsightFeedback(
  insightId: string,
  feedback: { status?: string; feedback?: string }
): Promise<IntelligenceInsight> {
  const response = await apiClient.patch<IntelligenceInsight>(
    `/intelligence/insights/${insightId}`,
    feedback
  );
  return response.data;
}

export async function getProactiveInsights(): Promise<ProactiveInsight[]> {
  const response = await apiClient.get<ProactiveInsightsResponse>("/insights/proactive");
  return response.data.insights ?? [];
}

export async function engageInsight(insightId: string): Promise<void> {
  await apiClient.post(`/insights/${insightId}/engage`);
}

export async function dismissInsight(insightId: string): Promise<void> {
  await apiClient.post(`/insights/${insightId}/dismiss`);
}
